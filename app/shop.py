"""Cart, orders, gift codes and the contact form.

A film is a digital product, so the cart works like this:
- each line is one film, either rented (48 hours) or bought (kept forever);
- the quantity is the number of copies. The first copy goes to the buyer's own
  Library unless they can already watch it; every other copy becomes a gift
  code they can send to a friend (redeemed at /redeem);
- guests can fill a cart too. It lives in their session and moves into their
  account when they sign in or register.

Order life cycle: pending (waiting for payment) -> paid -> delivered (films in
the Library and gift codes issued). A pending order can be cancelled; a paid
or delivered order can be refunded by an admin, which takes the films back.
"""
import random
import re
import string

from flask import (Blueprint, abort, flash, g, jsonify, redirect, render_template, request, session,
                   url_for)

from . import catalog
from .auth import EMAIL_RE, PHONE_RE, login_required
from .billing import METHODS, PAY_FIELDS, create_transaction, validate_payment
from .db import get_db, now
from .insights import track

bp = Blueprint("shop", __name__)

MAX_QTY = 10
STATUSES = ["pending", "paid", "delivered", "cancelled", "refunded"]
STATUS_LABELS = {
    "pending": "Waiting for payment",
    "paid": "Paid, preparing delivery",
    "delivered": "Delivered to your Library",
    "cancelled": "Cancelled",
    "refunded": "Refunded",
}
# What an admin may change an order to, from each status.
TRANSITIONS = {
    "pending": ["cancelled"],
    "paid": ["delivered", "refunded"],
    "delivered": ["refunded"],
    "cancelled": [],
    "refunded": [],
}
TOPICS = ["Payment or order", "Watching a film", "My account", "Filmmakers & partnerships", "Something else"]


def wants_json():
    return request.headers.get("X-Requested-With") == "fetch"


# ---------------------------------------------------------------- cart storage
def _raw_cart():
    """Return {movie_id: (kind, qty)} for the signed-in user or the guest session."""
    if g.user:
        rows = get_db().execute("SELECT movie_id, kind, qty FROM cart_items WHERE user_id=? ORDER BY added_at",
                                (g.user["id"],))
        return {r["movie_id"]: (r["kind"], r["qty"]) for r in rows}
    return {int(k): (v[0], v[1]) for k, v in session.get("cart", {}).items()}


def _save_line(movie_id, kind, qty):
    if g.user:
        db = get_db()
        if qty <= 0:
            db.execute("DELETE FROM cart_items WHERE user_id=? AND movie_id=?", (g.user["id"], movie_id))
        else:
            db.execute(
                """INSERT INTO cart_items (user_id, movie_id, kind, qty, added_at) VALUES (?,?,?,?,?)
                   ON CONFLICT(user_id, movie_id) DO UPDATE SET kind=excluded.kind, qty=excluded.qty""",
                (g.user["id"], movie_id, kind, qty, now()))
        db.commit()
    else:
        cart = dict(session.get("cart", {}))
        if qty <= 0:
            cart.pop(str(movie_id), None)
        else:
            cart[str(movie_id)] = [kind, qty]
        session["cart"] = cart


def merge_guest_cart(user_id, guest_cart):
    """Called at sign-in / sign-up: move what a guest put in their cart into their account."""
    if not guest_cart:
        return
    db = get_db()
    for movie_id, (kind, qty) in guest_cart.items():
        db.execute(
            """INSERT INTO cart_items (user_id, movie_id, kind, qty, added_at) VALUES (?,?,?,?,?)
               ON CONFLICT(user_id, movie_id) DO UPDATE SET kind=excluded.kind,
               qty=MIN(?, cart_items.qty + excluded.qty)""",
            (user_id, int(movie_id), kind, min(MAX_QTY, int(qty)), now(), MAX_QTY))
    db.commit()


def cart_count():
    return sum(qty for _, qty in _raw_cart().values())


def self_copy(access, kind):
    """Does the first copy of this line go to the buyer, or are they all gifts?"""
    if kind == "buy":
        return access["reason"] not in ("owned", "admin")
    return not access["can_watch"]


def cart_lines():
    raw = _raw_cart()
    if not raw:
        return []
    by_id = {m["id"]: m for m in catalog.movies(f"m.id IN ({','.join('?' * len(raw))})", tuple(raw))}
    lines = []
    for movie_id, (kind, qty) in raw.items():
        movie = by_id.get(movie_id)
        if movie is None:  # deleted, or hidden by a Kids profile
            continue
        access = catalog.access_for(movie)
        unit = access["rent_price"] if kind == "rent" else access["buy_price"]
        list_unit = movie["rent_price"] if kind == "rent" else movie["buy_price"]
        mine = self_copy(access, kind)
        note = None
        if not movie["available"]:
            note = "No longer available. Remove it to check out."
        elif not mine and access["reason"] == "subscription":
            note = "Already included in your plan, so every copy will be a gift code."
        elif not mine:
            note = "You can already watch this, so every copy will be a gift code."
        lines.append({
            "movie": movie, "kind": kind, "qty": qty, "unit": unit, "list_unit": list_unit,
            "line": unit * qty, "mine": mine, "gifts": qty - (1 if mine else 0), "note": note,
            "available": bool(movie["available"]),
        })
    return lines


def cart_totals(lines, promo=None):
    subtotal = sum(l["line"] for l in lines)
    savings = sum((l["list_unit"] - l["unit"]) * l["qty"] for l in lines)
    discount = subtotal * promo["percent"] // 100 if promo else 0
    return {"subtotal": subtotal, "savings": savings, "discount": discount, "total": subtotal - discount,
            "items": sum(l["qty"] for l in lines), "gifts": sum(l["gifts"] for l in lines)}


@bp.app_context_processor
def inject_cart():
    return {"cart_count": cart_count, "ORDER_STATUS": STATUS_LABELS}


def _cart_response(message=None, kind="success"):
    if wants_json():
        lines = cart_lines()
        return jsonify(ok=True, message=message, count=cart_count(),
                       html=render_template("shop/_cart_body.html", lines=lines, totals=cart_totals(lines)))
    if message:
        flash(message, kind)
    return redirect(request.form.get("next") or url_for("shop.cart"))


def _cart_error(message, status=400):
    if wants_json():
        return jsonify(ok=False, error=message), status
    flash(message, "error")
    return redirect(request.referrer or url_for("shop.cart"))


def _qty(value, default=1):
    try:
        return max(0, min(MAX_QTY, int(value)))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- cart routes
@bp.route("/cart")
def cart():
    lines = cart_lines()
    suggestions = []
    if not lines:
        suggestions = catalog.movies("m.access != 'free' AND m.available = 1", limit=8)
    return render_template("shop/cart.html", lines=lines, totals=cart_totals(lines), suggestions=suggestions)


@bp.route("/cart/add", methods=["POST"])
def add():
    movie = catalog.movie_by_slug(request.form.get("movie", ""))
    kind = request.form.get("kind", "buy")
    if movie is None or kind not in ("rent", "buy"):
        return _cart_error("That film isn't in the catalogue.", 404)
    if movie["access"] == "free":
        return _cart_error(f"{movie['title']} is free to watch, no need to buy it.")
    if not movie["available"]:
        return _cart_error(f"{movie['title']} is coming soon. Add it to My List and we'll tell you when it's out.")
    current = _raw_cart().get(movie["id"])
    qty = _qty(request.form.get("qty"), 1) or 1
    if current and current[0] == kind:
        qty = min(MAX_QTY, current[1] + qty)
        message = f"{movie['title']}: {qty} copies in your cart"
    elif current:
        qty = current[1]
        message = f"{movie['title']} switched to {'rent' if kind == 'rent' else 'buy'}"
    else:
        message = f"{movie['title']} added to your cart"
    _save_line(movie["id"], kind, qty)
    track("add_to_cart", movie["id"], kind)
    return _cart_response(message)


@bp.route("/cart/update", methods=["POST"])
def update():
    movie = catalog.movie_by_slug(request.form.get("movie", ""))
    current = _raw_cart().get(movie["id"]) if movie else None
    if current is None:
        return _cart_error("That film isn't in your cart any more.", 404)
    kind = request.form.get("kind", current[0])
    if kind not in ("rent", "buy"):
        kind = current[0]
    qty = _qty(request.form.get("qty"), current[1])
    _save_line(movie["id"], kind, qty)
    return _cart_response(f"{movie['title']} removed from your cart" if qty == 0 else None, "info")


@bp.route("/cart/remove", methods=["POST"])
def remove():
    movie = catalog.movie_by_slug(request.form.get("movie", ""))
    if movie:
        _save_line(movie["id"], None, 0)
    return _cart_response(f"{movie['title']} removed from your cart" if movie else None, "info")


@bp.route("/cart/save-for-later", methods=["POST"])
def save_for_later():
    movie = catalog.movie_by_slug(request.form.get("movie", ""))
    if movie is None:
        return _cart_error("That film isn't in your cart any more.", 404)
    if not g.get("profile"):
        return _cart_error("Sign in to save films to My List.", 401)
    get_db().execute("INSERT OR IGNORE INTO watchlist (profile_id, movie_id, added_at) VALUES (?,?,?)",
                     (g.profile["id"], movie["id"], now()))
    _save_line(movie["id"], None, 0)
    return _cart_response(f"{movie['title']} moved to My List")


@bp.route("/cart/clear", methods=["POST"])
def clear():
    if g.user:
        get_db().execute("DELETE FROM cart_items WHERE user_id=?", (g.user["id"],))
        get_db().commit()
    session.pop("cart", None)
    return _cart_response("Your cart is empty.", "info")


@bp.route("/api/cart")
def api_cart():
    return jsonify(count=cart_count())


# ---------------------------------------------------------------- checkout
def _contact_errors(form):
    errors = {}
    if len(form["contact_name"]) < 2:
        errors["contact_name"] = "Who is this order for? At least 2 letters."
    if not EMAIL_RE.match(form["email"]):
        errors["email"] = "We send your receipt and gift codes here, e.g. you@example.com"
    if not PHONE_RE.match(re.sub(r"[\s-]", "", form["contact_phone"])):
        errors["contact_phone"] = "Use a Rwandan number like 0788123456 for the SMS confirmation."
    if len(form["gift_note"]) > 200:
        errors["gift_note"] = "Keep the gift message under 200 characters."
    return errors


def new_order_ref():
    db = get_db()
    while True:
        ref = "ORD-" + "".join(random.choices(string.digits, k=6))
        if not db.execute("SELECT 1 FROM orders WHERE ref=?", (ref,)).fetchone():
            return ref


def log_event(order_id, status, note="", actor="system"):
    get_db().execute("INSERT INTO order_events (order_id, status, note, actor, created_at) VALUES (?,?,?,?,?)",
                     (order_id, status, note, actor, now()))


@bp.route("/cart/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    if g.user["role"] == "admin":
        flash("Admin accounts can already watch every film. Use a customer account to test the cart.", "info")
        return redirect(url_for("shop.cart"))
    lines = cart_lines()
    if not lines:
        flash("Your cart is empty. Add a film first.", "info")
        return redirect(url_for("shop.cart"))
    if any(not l["available"] for l in lines):
        flash("One of the films in your cart is no longer available. Remove it to continue.", "error")
        return redirect(url_for("shop.cart"))

    form = {"contact_name": g.user["name"], "email": g.user["email"], "contact_phone": g.user["phone"] or "",
            "gift_note": "", "method": "mtn", "phone": g.user["phone"] or "", "promo": "", "card": "", "expiry": "",
            "cvc": ""}
    errors = {}
    if request.method == "POST":
        form.update({k: request.form.get(k, "").strip() for k in form})
        form["email"] = form["email"].lower()
        errors = _contact_errors(form)
        pay_errors, promo, method, account = validate_payment(form)
        errors.update(pay_errors)
        if not errors:
            totals = cart_totals(lines, promo)
            db = get_db()
            stamp = now()
            order_id = db.execute(
                """INSERT INTO orders (ref, user_id, contact_name, email, phone, gift_note, subtotal, discount, total,
                   promo_code, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (new_order_ref(), g.user["id"], form["contact_name"], form["email"],
                 re.sub(r"[\s-]", "", form["contact_phone"]), form["gift_note"], totals["subtotal"], totals["discount"],
                 totals["total"], promo["code"] if promo else None, "pending", stamp, stamp)).lastrowid
            db.executemany(
                "INSERT INTO order_items (order_id, movie_id, title, kind, qty, unit_price, line_total) VALUES (?,?,?,?,?,?,?)",
                [(order_id, l["movie"]["id"], l["movie"]["title"], l["kind"], l["qty"], l["unit"], l["line"])
                 for l in lines])
            log_event(order_id, "pending", f"Order placed: {totals['items']} cop{'y' if totals['items'] == 1 else 'ies'}")
            ref = create_transaction("order", totals["total"], totals["discount"], promo, method, account,
                                     order_id=order_id)
            return redirect(url_for("billing.pay", ref=ref))
    if request.method == "GET":
        track("checkout", detail=f"{len(lines)} films")
    promo = None
    totals = cart_totals(lines, promo)
    return render_template("shop/checkout.html", lines=lines, totals=totals, form=form, errors=errors,
                           methods=METHODS, order=None), (400 if errors else 200)


# ---------------------------------------------------------------- fulfilment
def _gift_code():
    db = get_db()
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, so codes are easy to read out
    while True:
        code = "MBONI-" + "".join(random.choices(alphabet, k=4)) + "-" + "".join(random.choices(alphabet, k=4))
        if not db.execute("SELECT 1 FROM gift_codes WHERE code=?", (code,)).fetchone():
            return code


def _grant(user_id, movie_id, kind, price, order_id):
    from datetime import datetime, timedelta
    expires = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S") if kind == "rent" else None
    get_db().execute(
        "INSERT INTO purchases (user_id, movie_id, kind, price, expires_at, order_id, created_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, movie_id, kind, price, expires, order_id, now()))


def deliver(order, actor="system"):
    """Put the films in the buyer's Library and issue gift codes for the extra copies."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (order["user_id"],)).fetchone()
    items = db.execute("SELECT * FROM order_items WHERE order_id=?", (order["id"],)).fetchall()
    mine = gifts = 0
    for item in items:
        movie = db.execute("SELECT * FROM movies WHERE id=?", (item["movie_id"],)).fetchone()
        if movie is None:
            continue
        copies = item["qty"]
        if self_copy(catalog.access_for(movie, user), item["kind"]):
            _grant(user["id"], movie["id"], item["kind"], item["unit_price"], order["id"])
            copies -= 1
            mine += 1
        for _ in range(copies):
            db.execute("INSERT INTO gift_codes (code, order_id, movie_id, kind, created_at) VALUES (?,?,?,?,?)",
                       (_gift_code(), order["id"], movie["id"], item["kind"], now()))
            gifts += 1
    parts = []
    if mine:
        parts.append(f"{mine} film{'s' if mine > 1 else ''} added to the Library")
    if gifts:
        parts.append(f"{gifts} gift code{'s' if gifts > 1 else ''} sent to {order['email']}")
    db.execute("UPDATE orders SET status='delivered', updated_at=? WHERE id=?", (now(), order["id"]))
    log_event(order["id"], "delivered", " · ".join(parts) or "Nothing to deliver", actor)


def payment_received(order_id, note):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if order is None or order["status"] != "pending":
        return
    db.execute("UPDATE orders SET status='paid', updated_at=? WHERE id=?", (now(), order_id))
    track("purchase", detail=f"cart order {order['ref']}")
    log_event(order_id, "paid", f"Payment confirmed: {note}")
    # Films are digital, so delivery happens straight away.
    deliver(order)
    movie_ids = [r["movie_id"] for r in db.execute("SELECT movie_id FROM order_items WHERE order_id=?", (order_id,))]
    db.executemany("DELETE FROM cart_items WHERE user_id=? AND movie_id=?", [(order["user_id"], m) for m in movie_ids])


def change_status(order, new_status, actor, note=""):
    """Apply an admin (or customer) status change. Returns an error message or None."""
    if new_status not in TRANSITIONS.get(order["status"], []):
        return f"An order that is {order['status']} can't be marked {new_status}."
    db = get_db()
    if new_status == "delivered":
        deliver(order, actor)
        if note:
            log_event(order["id"], "delivered", note, actor)
        return None
    if new_status == "cancelled":
        db.execute("UPDATE transactions SET status='failed' WHERE order_id=? AND status='pending'", (order["id"],))
    if new_status == "refunded":
        # Take the films back, stop unused gift codes and mark the payment refunded.
        db.execute("DELETE FROM purchases WHERE order_id=?", (order["id"],))
        db.execute("UPDATE gift_codes SET void=1 WHERE order_id=?", (order["id"],))
        db.execute("UPDATE transactions SET status='refunded' WHERE order_id=? AND status='paid'", (order["id"],))
    db.execute("UPDATE orders SET status=?, updated_at=? WHERE id=?", (new_status, now(), order["id"]))
    log_event(order["id"], new_status, note, actor)
    return None


def order_bundle(order):
    db = get_db()
    items = db.execute(
        """SELECT i.*, m.slug, m.c1, m.c2, m.c3, m.pattern, m.country, m.access, m.is_kids
           FROM order_items i LEFT JOIN movies m ON m.id = i.movie_id WHERE i.order_id=? ORDER BY i.id""",
        (order["id"],)).fetchall()
    events = db.execute("SELECT * FROM order_events WHERE order_id=? ORDER BY id", (order["id"],)).fetchall()
    gifts = db.execute(
        """SELECT gc.*, m.title, u.name AS redeemer FROM gift_codes gc JOIN movies m ON m.id = gc.movie_id
           LEFT JOIN users u ON u.id = gc.redeemed_by WHERE gc.order_id=? ORDER BY m.title, gc.code""",
        (order["id"],)).fetchall()
    payments = db.execute("SELECT * FROM transactions WHERE order_id=? ORDER BY created_at DESC, id DESC",
                          (order["id"],)).fetchall()
    reached = {e["status"]: e["created_at"] for e in events}
    return {"items": items, "events": events, "gifts": gifts, "payments": payments, "reached": reached}


# ---------------------------------------------------------------- customer orders
def own_order(ref):
    order = get_db().execute("SELECT * FROM orders WHERE ref=? AND user_id=?", (ref, g.user["id"])).fetchone()
    if order is None:
        abort(404)
    return order


@bp.route("/orders")
@login_required
def orders():
    rows = get_db().execute(
        """SELECT o.*, (SELECT SUM(qty) FROM order_items WHERE order_id=o.id) AS copies,
                  (SELECT GROUP_CONCAT(title, ', ') FROM order_items WHERE order_id=o.id) AS titles
           FROM orders o WHERE o.user_id=? ORDER BY o.created_at DESC, o.id DESC""", (g.user["id"],)).fetchall()
    return render_template("shop/orders.html", orders=rows)


@bp.route("/orders/<ref>")
@login_required
def order(ref):
    o = own_order(ref)
    return render_template("shop/order.html", order=o, methods=METHODS, celebrate=request.args.get("paid") == "1",
                           **order_bundle(o))


@bp.route("/orders/<ref>/pay", methods=["GET", "POST"])
@login_required
def pay_order(ref):
    """Try paying again for an order whose first payment failed or was cancelled."""
    o = own_order(ref)
    if o["status"] != "pending":
        return redirect(url_for("shop.order", ref=ref))
    bundle = order_bundle(o)
    form = {"contact_name": o["contact_name"], "email": o["email"], "contact_phone": o["phone"],
            "gift_note": o["gift_note"], "method": "mtn", "phone": o["phone"], "promo": o["promo_code"] or "", "card": "", "expiry": "", "cvc": ""}
    errors = {}
    if request.method == "POST":
        form.update({k: request.form.get(k, "").strip() for k in PAY_FIELDS if k != "promo"})
        errors, _, method, account = validate_payment(form)
        if not errors:
            promo = {"code": o["promo_code"]} if o["promo_code"] else None
            tx = create_transaction("order", o["total"], o["discount"], promo, method, account, order_id=o["id"])
            return redirect(url_for("billing.pay", ref=tx))
    totals = {"subtotal": o["subtotal"], "discount": o["discount"], "total": o["total"], "savings": 0,
              "items": sum(i["qty"] for i in bundle["items"]), "gifts": 0}
    return render_template("shop/checkout.html", lines=None, items=bundle["items"], totals=totals, form=form,
                           errors=errors, methods=METHODS, order=o), (400 if errors else 200)


@bp.route("/orders/<ref>/cancel", methods=["POST"])
@login_required
def cancel_order(ref):
    o = own_order(ref)
    error = change_status(o, "cancelled", g.user["name"], "Cancelled by the customer")
    get_db().commit()
    flash(error or f"Order {ref} cancelled. Nothing was charged.", "error" if error else "info")
    return redirect(url_for("shop.order", ref=ref))


# ---------------------------------------------------------------- gift codes
@bp.route("/redeem", methods=["GET", "POST"])
def redeem():
    code = (request.values.get("code") or "").strip().upper()
    error = None
    if request.method == "POST":
        if g.user is None:
            return redirect(url_for("auth.login", next=url_for("shop.redeem", code=code)))
        db = get_db()
        gift = db.execute(
            """SELECT gc.*, m.title, m.slug, o.status AS order_status FROM gift_codes gc
               JOIN movies m ON m.id = gc.movie_id JOIN orders o ON o.id = gc.order_id WHERE gc.code=?""",
            (code,)).fetchone()
        if not re.match(r"^MBONI-[A-Z0-9]{4}-[A-Z0-9]{4}$", code):
            error = "Gift codes look like MBONI-AB12-CD34."
        elif gift is None:
            error = "We couldn't find that code. Check it letter by letter."
        elif gift["void"] or gift["order_status"] == "refunded":
            error = "This code was cancelled because its order was refunded."
        elif gift["redeemed_by"]:
            error = "This code has already been used."
        else:
            movie = db.execute("SELECT * FROM movies WHERE id=?", (gift["movie_id"],)).fetchone()
            access = catalog.access_for(movie)
            if gift["kind"] == "buy" and access["reason"] == "owned" or gift["kind"] == "rent" and access["can_watch"]:
                error = f"You can already watch {gift['title']}. Pass this code to someone else!"
            else:
                _grant(g.user["id"], movie["id"], gift["kind"], 0, gift["order_id"])
                db.execute("UPDATE gift_codes SET redeemed_by=?, redeemed_at=? WHERE code=?", (g.user["id"], now(), code))
                db.commit()
                flash(f"Gift unlocked! {gift['title']} is in your Library"
                      f"{' for 48 hours' if gift['kind'] == 'rent' else ' forever'}.", "success")
                return redirect(url_for("main.detail", slug=gift["slug"]))
    return render_template("shop/redeem.html", code=code, error=error), (400 if error else 200)


# ---------------------------------------------------------------- help & contact
@bp.route("/help", methods=["GET", "POST"])
def contact():
    form = {"name": g.user["name"] if g.user else "", "email": g.user["email"] if g.user else "",
            "topic": request.args.get("topic", TOPICS[0]), "body": ""}
    if form["topic"] not in TOPICS:
        form["topic"] = TOPICS[0]
    errors = {}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        if len(form["name"]) < 2:
            errors["name"] = "Tell us your name."
        if not EMAIL_RE.match(form["email"]):
            errors["email"] = "We need an email to reply to, e.g. you@example.com"
        if form["topic"] not in TOPICS:
            errors["topic"] = "Pick a topic."
        if not 10 <= len(form["body"]) <= 2000:
            errors["body"] = "Write between 10 and 2,000 characters so we can help."
        if not errors:
            get_db().execute("INSERT INTO messages (user_id, name, email, topic, body, created_at) VALUES (?,?,?,?,?,?)",
                             (g.user["id"] if g.user else None, form["name"], form["email"].lower(), form["topic"],
                              form["body"], now()))
            get_db().commit()
            flash(f"Murakoze, {form['name'].split()[0]}! We'll reply to {form['email']} within a day.", "success")
            return redirect(url_for("shop.contact"))
    return render_template("shop/help.html", form=form, errors=errors, topics=TOPICS), (400 if errors else 200)

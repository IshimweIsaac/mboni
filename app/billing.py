"""Plans, rentals, purchases and the (simulated) mobile money / card checkout.

No real money moves. The flow mirrors MTN MoMo and Airtel Money: a pending
transaction is created, the customer approves on their phone, then the
payment is confirmed. Test failures: a phone ending in 0000, or the card
4000 0000 0000 0002.
"""
import random
import re
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from . import catalog
from .auth import login_required
from .db import get_db, now
from .insights import track

bp = Blueprint("billing", __name__)

PHONE_RE = re.compile(r"^07[2389]\d{7}$")
MTN_PREFIXES = ("078", "079")
AIRTEL_PREFIXES = ("072", "073")
DECLINED_CARD = "4000000000000002"
METHODS = {"mtn": "MTN MoMo", "airtel": "Airtel Money", "card": "Visa / Mastercard"}


def luhn_ok(number):
    digits = [int(d) for d in number][::-1]
    total = sum(digits[0::2]) + sum(sum(divmod(2 * d, 10)) for d in digits[1::2])
    return total % 10 == 0


def promo_lookup(code):
    if not code:
        return None
    return get_db().execute("SELECT * FROM promo_codes WHERE code = ? AND active = 1", (code.strip().upper(),)).fetchone()


def build_order(args):
    """Work out what is being bought and its price from query/form args."""
    kind = args.get("kind")
    db = get_db()
    if kind == "subscription":
        plan = db.execute("SELECT * FROM plans WHERE code = ?", (args.get("plan", ""),)).fetchone()
        if plan is None:
            return None
        return {"kind": kind, "plan": plan, "movie": None, "amount": plan["price"],
                "title": f"Mboni {plan['name']} plan", "subtitle": "30 days · cancel anytime"}
    if kind in ("rent", "buy"):
        movie = catalog.movie_by_slug(args.get("movie", ""))
        if movie is None or movie["access"] == "free" or not movie["available"]:
            return None
        access = catalog.access_for(movie)
        amount = access["rent_price"] if kind == "rent" else access["buy_price"]
        subtitle = "48 hours to finish once you press play" if kind == "rent" else "Yours forever · download to keep"
        return {"kind": kind, "plan": None, "movie": movie, "amount": amount, "access": access,
                "title": f"{'Rent' if kind == 'rent' else 'Buy'} · {movie['title']}", "subtitle": subtitle}
    return None


PAY_FIELDS = ("method", "phone", "promo", "card", "expiry", "cvc")


def validate_payment(form):
    """Check the payment part of a checkout form. Returns (errors, promo, method, account)."""
    errors = {}
    promo = promo_lookup(form.get("promo"))
    if form.get("promo") and promo is None:
        errors["promo"] = "That code isn't valid. Try STUDENT50."
    method, account = form.get("method"), ""
    if method not in METHODS:
        errors["method"] = "Choose a payment method."
    elif method in ("mtn", "airtel"):
        phone = re.sub(r"[\s-]", "", form.get("phone", ""))
        prefixes = MTN_PREFIXES if method == "mtn" else AIRTEL_PREFIXES
        if not PHONE_RE.match(phone):
            errors["phone"] = "Enter a 10-digit Rwandan number, e.g. 0788123456."
        elif not phone.startswith(prefixes):
            errors["phone"] = f"{METHODS[method]} numbers start with {' or '.join(prefixes)}."
        account = phone
    else:
        card = re.sub(r"\D", "", form.get("card", ""))
        if not (13 <= len(card) <= 19) or not luhn_ok(card):
            errors["card"] = "That card number isn't valid. For testing, use 4242 4242 4242 4242."
        expiry = form.get("expiry", "")
        if not re.match(r"^(0[1-9]|1[0-2])/\d{2}$", expiry):
            errors["expiry"] = "Use MM/YY."
        else:
            mm, yy = expiry.split("/")
            if (2000 + int(yy), int(mm)) < (datetime.now().year, datetime.now().month):
                errors["expiry"] = "This card has expired."
        if not re.match(r"^\d{3,4}$", form.get("cvc", "")):
            errors["cvc"] = "3 or 4 digits on the back."
        account = card
    return errors, promo, method, account


def create_transaction(kind, amount, discount, promo, method, account, movie_id=None, plan_code=None, order_id=None):
    """Insert a pending payment and return its reference. Card numbers are masked before they are stored."""
    ref = f"NY{datetime.now().strftime('%y%m%d')}{random.randint(100000, 999999)}"
    if method == "card":
        # Only the last four digits are kept; "!" marks the test card that the bank will decline.
        account = f"**** {account[-4:]}" + ("!" if account == DECLINED_CARD else "")
    db = get_db()
    db.execute(
        """INSERT INTO transactions (ref, user_id, kind, movie_id, plan_code, order_id, amount, discount, promo_code,
           method, account, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ref, g.user["id"], kind, movie_id, plan_code, order_id, amount, discount, promo["code"] if promo else None,
         method, account, "pending", now()))
    if method != "card" and not g.user["phone"]:
        db.execute("UPDATE users SET phone=? WHERE id=?", (account, g.user["id"]))
    db.commit()
    return ref


@bp.route("/plans")
def plans():
    db = get_db()
    rows = db.execute("SELECT * FROM plans ORDER BY price").fetchall()
    sub = catalog.active_subscription(g.user["id"]) if g.user else None
    return render_template("billing/plans.html", plans=rows, sub=sub, welcome=request.args.get("welcome"))


@bp.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    source = request.form if request.method == "POST" else request.args
    order = build_order(source)
    if order is None:
        abort(404)
    if order["movie"] and order["kind"] == "rent" and order["access"]["reason"] in ("owned", "rented"):
        flash("You can already watch this film.", "info")
        return redirect(url_for("main.detail", slug=order["movie"]["slug"]))
    if order["movie"] and order["access"]["reason"] == "owned":
        flash("You already own this film.", "info")
        return redirect(url_for("main.detail", slug=order["movie"]["slug"]))

    form = {"method": "mtn", "phone": g.user["phone"] or "", "promo": "", "card": "", "expiry": "", "cvc": ""}
    errors = {}
    if request.method == "GET":
        track("checkout", order["movie"]["id"] if order["movie"] else None, order["kind"])
    if request.method == "POST":
        form.update({k: request.form.get(k, "").strip() for k in form})
        errors, promo, method, account = validate_payment(form)
        if not errors:
            discount = order["amount"] * promo["percent"] // 100 if promo else 0
            ref = create_transaction(order["kind"], order["amount"] - discount, discount, promo, method, account,
                                     movie_id=order["movie"]["id"] if order["movie"] else None,
                                     plan_code=order["plan"]["code"] if order["plan"] else None)
            return redirect(url_for("billing.pay", ref=ref))
    return render_template("billing/checkout.html", order=order, form=form, errors=errors, methods=METHODS), (400 if errors else 200)


@bp.route("/api/promo")
def api_promo():
    promo = promo_lookup(request.args.get("code", ""))
    if promo is None:
        return jsonify(ok=False, error="That code isn't valid.")
    return jsonify(ok=True, percent=promo["percent"], label=promo["label"], code=promo["code"])


def own_transaction(ref):
    tx = get_db().execute(
        """SELECT t.*, m.title, m.slug, p.name AS plan_name FROM transactions t
           LEFT JOIN movies m ON m.id = t.movie_id LEFT JOIN plans p ON p.code = t.plan_code
           WHERE t.ref = ? AND t.user_id = ?""", (ref, g.user["id"])).fetchone()
    if tx is None:
        abort(404)
    return tx


@bp.route("/pay/<ref>")
@login_required
def pay(ref):
    tx = own_transaction(ref)
    if tx["status"] != "pending":
        return redirect(url_for("billing.receipt", ref=ref))
    return render_template("billing/pay.html", tx=tx, methods=METHODS)


@bp.route("/pay/<ref>/confirm", methods=["POST"])
@login_required
def confirm(ref):
    tx = own_transaction(ref)
    if tx["status"] != "pending":
        return redirect(url_for("billing.receipt", ref=ref))
    db = get_db()
    declined = tx["account"].endswith("0000") or tx["account"].endswith("!")
    masked = tx["account"].rstrip("!")
    if tx["method"] != "card":
        masked = f"{masked[:3]}****{masked[-3:]}"
    if declined or request.form.get("action") == "cancel":
        db.execute("UPDATE transactions SET status='failed', account=? WHERE id=?", (masked, tx["id"]))
        db.commit()
        if tx["kind"] == "order":
            flash("Payment didn't go through. Nothing was charged and your order is still saved.", "error")
        return redirect(url_for("billing.receipt", ref=ref))
    if tx["kind"] == "order":
        from . import shop
        db.execute("UPDATE transactions SET status='paid', account=? WHERE id=?", (masked, tx["id"]))
        shop.payment_received(tx["order_id"], f"{METHODS[tx['method']]} {masked} · {tx['ref']}")
        db.commit()
        return redirect(url_for("billing.receipt", ref=ref))

    stamp = now()
    if tx["kind"] == "subscription":
        current = catalog.active_subscription(g.user["id"])
        start = datetime.now()
        if current and current["plan_code"] == tx["plan_code"]:
            # Renewing the same plan stacks the new 30 days on top of what is left.
            start = datetime.strptime(current["expires_at"], "%Y-%m-%d %H:%M:%S")
        elif current:
            # Switching plans ends the old one now.
            db.execute("UPDATE subscriptions SET expires_at=?, auto_renew=0 WHERE id=?", (stamp, current["id"]))
        db.execute("INSERT INTO subscriptions (user_id, plan_code, started_at, expires_at) VALUES (?,?,?,?)",
                   (g.user["id"], tx["plan_code"], stamp, (start + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")))
    else:
        expires = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S") if tx["kind"] == "rent" else None
        db.execute("INSERT INTO purchases (user_id, movie_id, kind, price, expires_at, created_at) VALUES (?,?,?,?,?,?)",
                   (g.user["id"], tx["movie_id"], tx["kind"], tx["amount"], expires, stamp))
    db.execute("UPDATE transactions SET status='paid', account=? WHERE id=?", (masked, tx["id"]))
    db.commit()
    track("purchase", tx["movie_id"], tx["kind"])
    return redirect(url_for("billing.receipt", ref=ref))


@bp.route("/receipt/<ref>")
@login_required
def receipt(ref):
    tx = own_transaction(ref)
    if tx["kind"] == "order":
        ref = get_db().execute("SELECT ref FROM orders WHERE id=?", (tx["order_id"],)).fetchone()["ref"]
        return redirect(url_for("shop.order", ref=ref, paid=1 if tx["status"] == "paid" else None))
    return render_template("billing/receipt.html", tx=tx, methods=METHODS)


@bp.route("/subscription/cancel", methods=["POST"])
@login_required
def cancel():
    sub = catalog.active_subscription(g.user["id"])
    if sub:
        get_db().execute("UPDATE subscriptions SET auto_renew=0 WHERE id=?", (sub["id"],))
        get_db().commit()
        flash(f"Auto-renew is off. You keep full access until {sub['expires_at'][:10]}.", "info")
    return redirect(url_for("main.settings"))


@bp.route("/subscription/resume", methods=["POST"])
@login_required
def resume():
    sub = catalog.active_subscription(g.user["id"])
    if sub:
        get_db().execute("UPDATE subscriptions SET auto_renew=1 WHERE id=?", (sub["id"],))
        get_db().commit()
        flash("Auto-renew is back on.", "success")
    return redirect(url_for("main.settings"))

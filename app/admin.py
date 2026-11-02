import csv
import io
import re
from datetime import datetime, timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .auth import admin_required
from .catalog import movies
from .db import get_db, now

bp = Blueprint("admin", __name__, url_prefix="/admin")

CREATOR_SHARE = 60  # percent of every rental and purchase paid to the film's makers
PATTERNS = ["kente", "imigongo", "mudcloth", "adinkra", "waves", "rays"]
MOVIE_FIELDS = ["title", "tagline", "year", "country", "language", "genres", "runtime", "age", "synopsis",
                "director", "cast_list", "c1", "c2", "c3", "pattern", "access", "rent_price", "buy_price", "award"]


@bp.route("/")
@admin_required
def dashboard():
    db = get_db()
    since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    paid = "status='paid' AND created_at >= ?"
    by_kind = {r["kind"]: r for r in db.execute(
        f"SELECT kind, SUM(amount) total, COUNT(*) n FROM transactions WHERE {paid} GROUP BY kind", (since,))}
    revenue = sum(r["total"] for r in by_kind.values())
    pay_per_view = sum(by_kind[k]["total"] for k in ("rent", "buy", "order") if k in by_kind)
    daily = {(datetime.now() - timedelta(days=d)).strftime("%Y-%m-%d"): 0 for d in range(29, -1, -1)}
    for r in db.execute(f"SELECT substr(created_at,1,10) d, SUM(amount) s FROM transactions WHERE {paid} GROUP BY d", (since,)):
        if r["d"] in daily:
            daily[r["d"]] = r["s"]
    methods = db.execute(
        f"SELECT method, COUNT(*) n, SUM(amount) total FROM transactions WHERE {paid} GROUP BY method ORDER BY total DESC",
        (since,)).fetchall()
    top = db.execute(
        """SELECT m.title, m.slug, m.country, m.views, COALESCE(SUM(t.amount),0) earned
           FROM movies m LEFT JOIN transactions t ON t.movie_id = m.id AND t.status='paid'
           GROUP BY m.id ORDER BY m.views DESC LIMIT 8""").fetchall()
    countries = db.execute(
        "SELECT country, SUM(views) v, COUNT(*) n FROM movies GROUP BY country ORDER BY v DESC").fetchall()
    stats = {
        "revenue": revenue,
        "subs": db.execute("SELECT COUNT(DISTINCT user_id) FROM subscriptions WHERE expires_at > ?", (now(),)).fetchone()[0],
        "users": db.execute("SELECT COUNT(*) FROM users WHERE role='viewer'").fetchone()[0],
        "rentals": db.execute("SELECT COUNT(*) FROM purchases WHERE kind='rent' AND expires_at > ?", (now(),)).fetchone()[0],
        "failed": db.execute("SELECT COUNT(*) FROM transactions WHERE status='failed' AND created_at >= ?", (since,)).fetchone()[0],
        "creator_payout": pay_per_view * CREATOR_SHARE // 100,
        "movies": db.execute("SELECT COUNT(*) FROM movies").fetchone()[0],
        "to_deliver": db.execute("SELECT COUNT(*) FROM orders WHERE status='paid'").fetchone()[0],
        "awaiting": db.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0],
        "orders": db.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (since,)).fetchone()[0],
        "messages": db.execute("SELECT COUNT(*) FROM messages WHERE status='open'").fetchone()[0],
    }
    recent = db.execute(
        """SELECT t.*, u.name, m.title, o.ref AS order_ref FROM transactions t JOIN users u ON u.id=t.user_id
           LEFT JOIN movies m ON m.id=t.movie_id LEFT JOIN orders o ON o.id=t.order_id
           ORDER BY t.created_at DESC LIMIT 8""").fetchall()
    recent_orders = db.execute(
        """SELECT o.*, (SELECT SUM(qty) FROM order_items WHERE order_id=o.id) copies FROM orders o
           ORDER BY CASE o.status WHEN 'paid' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, o.created_at DESC LIMIT 6""").fetchall()
    return render_template("admin/dashboard.html", recent_orders=recent_orders, stats=stats, by_kind=by_kind, daily=daily, methods=methods,
                           top=top, countries=countries, recent=recent, creator_share=CREATOR_SHARE)


@bp.route("/movies")
@admin_required
def movie_list():
    return render_template("admin/movies.html", movies=movies(order="m.created_at DESC"))


def movie_form_values(form):
    values = {f: form.get(f, "").strip() for f in MOVIE_FIELDS}
    errors = {}
    if len(values["title"]) < 2:
        errors["title"] = "Title is required."
    for f in ("year", "runtime", "rent_price", "buy_price"):
        if not values[f].isdigit():
            errors[f] = "Whole number please."
    if values["year"].isdigit() and not 1950 <= int(values["year"]) <= 2030:
        errors["year"] = "Between 1950 and 2030."
    for f in ("c1", "c2", "c3"):
        if not re.match(r"^#[0-9a-fA-F]{6}$", values[f]):
            errors[f] = "Hex colour like #d97706."
    if values["pattern"] not in PATTERNS:
        errors["pattern"] = "Pick a pattern."
    if values["access"] not in ("sub", "premiere", "free"):
        errors["access"] = "Pick an access type."
    for f in ("country", "language", "genres", "synopsis", "director", "cast_list"):
        if not values[f]:
            errors[f] = "Required."
    values["is_kids"] = 1 if form.get("is_kids") else 0
    values["featured"] = 1 if form.get("featured") else 0
    values["available"] = 0 if form.get("coming_soon") else 1
    values["award"] = values["award"] or None
    return values, errors


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "film"


@bp.route("/movies/new", methods=["GET", "POST"])
@bp.route("/movies/<int:mid>/edit", methods=["GET", "POST"])
@admin_required
def movie_edit(mid=None):
    db = get_db()
    movie = None
    if mid is not None:
        movie = db.execute("SELECT * FROM movies WHERE id=?", (mid,)).fetchone()
        if movie is None:
            abort(404)
    if request.method == "POST":
        values, errors = movie_form_values(request.form)
        if errors:
            return render_template("admin/movie_form.html", movie=values, errors=errors, patterns=PATTERNS, mid=mid), 400
        cols = MOVIE_FIELDS + ["is_kids", "featured", "available"]
        if movie:
            db.execute(f"UPDATE movies SET {', '.join(c + '=?' for c in cols)} WHERE id=?",
                       [values[c] for c in cols] + [mid])
            slug = movie["slug"]
        else:
            slug = base = slugify(values["title"])
            n = 2
            while db.execute("SELECT 1 FROM movies WHERE slug=?", (slug,)).fetchone():
                slug, n = f"{base}-{n}", n + 1
            db.execute(f"INSERT INTO movies (slug, {', '.join(cols)}) VALUES (?{', ?' * len(cols)})",
                       [slug] + [values[c] for c in cols])
        db.commit()
        flash(f"{values['title']} saved.", "success")
        return redirect(url_for("admin.movie_list"))
    blank = {f: "" for f in MOVIE_FIELDS} | {"c1": "#d97706", "c2": "#1c1917", "c3": "#fde68a", "pattern": "kente",
                                            "access": "sub", "rent_price": 1000, "buy_price": 5000, "age": "13+",
                                            "year": datetime.now().year, "is_kids": 0, "featured": 0,
                                            "available": 1}
    return render_template("admin/movie_form.html", movie=movie or blank, errors={}, patterns=PATTERNS, mid=mid)


@bp.route("/movies/<int:mid>/delete", methods=["POST"])
@admin_required
def movie_delete(mid):
    db = get_db()
    movie = db.execute("SELECT title FROM movies WHERE id=?", (mid,)).fetchone()
    if movie is None:
        abort(404)
    db.execute("DELETE FROM movies WHERE id=?", (mid,))
    db.commit()
    flash(f"{movie['title']} removed from the catalogue.", "info")
    return redirect(url_for("admin.movie_list"))


@bp.route("/users")
@admin_required
def users():
    rows = get_db().execute(
        """SELECT u.*,
             (SELECT plan_code FROM subscriptions s WHERE s.user_id=u.id AND s.expires_at > ? ORDER BY expires_at DESC LIMIT 1) plan,
             (SELECT COALESCE(SUM(amount),0) FROM transactions t WHERE t.user_id=u.id AND t.status='paid') spent,
             (SELECT COUNT(*) FROM profiles p WHERE p.user_id=u.id) profiles
           FROM users u ORDER BY u.created_at DESC, u.id DESC""", (now(),)).fetchall()
    return render_template("admin/users.html", users=rows)


def transaction_rows(args):
    where, params = ["1=1"], []
    if args.get("status") in ("paid", "pending", "failed"):
        where.append("t.status=?")
        params.append(args["status"])
    if args.get("kind") in ("subscription", "rent", "buy", "order"):
        where.append("t.kind=?")
        params.append(args["kind"])
    return get_db().execute(
        f"""SELECT t.*, u.name, u.email, m.title, o.ref AS order_ref FROM transactions t JOIN users u ON u.id=t.user_id
            LEFT JOIN movies m ON m.id=t.movie_id LEFT JOIN orders o ON o.id=t.order_id WHERE {' AND '.join(where)} ORDER BY t.created_at DESC""",
        params).fetchall()


@bp.route("/transactions")
@admin_required
def transactions():
    return render_template("admin/transactions.html", rows=transaction_rows(request.args), args=request.args)


@bp.route("/transactions.csv")
@admin_required
def transactions_csv():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ref", "date", "customer", "email", "type", "item", "amount_rwf", "discount_rwf", "promo",
                     "method", "status"])
    for t in transaction_rows(request.args):
        writer.writerow([t["ref"], t["created_at"], t["name"], t["email"], t["kind"], t["title"] or t["order_ref"] or t["plan_code"],
                         t["amount"], t["discount"], t["promo_code"] or "", t["method"], t["status"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=mboni-transactions.csv"})


# ---------------------------------------------------------------- customers (online consumer behaviour)
@bp.route("/customers")
@admin_required
def customers():
    from .insights import report
    days = request.args.get("days", "30")
    return render_template("admin/customers.html", r=report(int(days) if days in ("7", "30", "90") else 30))


# ---------------------------------------------------------------- orders
@bp.route("/orders")
@admin_required
def orders():
    from .shop import STATUSES
    where, params = ["1=1"], []
    status = request.args.get("status", "")
    if status in STATUSES:
        where.append("o.status=?")
        params.append(status)
    q = request.args.get("q", "").strip()
    if q:
        where.append("(o.ref LIKE ? OR o.contact_name LIKE ? OR o.email LIKE ? OR o.phone LIKE ?)")
        params += [f"%{q}%"] * 4
    db = get_db()
    rows = db.execute(
        f"""SELECT o.*, u.name AS account_name,
                   (SELECT SUM(qty) FROM order_items WHERE order_id=o.id) AS copies,
                   (SELECT GROUP_CONCAT(title, ', ') FROM order_items WHERE order_id=o.id) AS titles
            FROM orders o JOIN users u ON u.id=o.user_id WHERE {' AND '.join(where)}
            ORDER BY o.created_at DESC, o.id DESC""", params).fetchall()
    counts = {r["status"]: r["n"] for r in db.execute("SELECT status, COUNT(*) n FROM orders GROUP BY status")}
    return render_template("admin/orders.html", orders=rows, counts=counts, statuses=STATUSES, status=status, q=q)


@bp.route("/orders/<ref>", methods=["GET", "POST"])
@admin_required
def order_detail(ref):
    from .shop import TRANSITIONS, change_status, order_bundle
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE ref=?", (ref,)).fetchone()
    if order is None:
        abort(404)
    if request.method == "POST":
        note = request.form.get("note", "").strip()[:300]
        new_status = request.form.get("status", "")
        if new_status == "note":
            if note:
                db.execute("INSERT INTO order_events (order_id, status, note, actor, created_at) VALUES (?,?,?,?,?)",
                           (order["id"], order["status"], note, g.user["name"], now()))
                db.commit()
                flash("Note added to the order.", "success")
            else:
                flash("Write a note first.", "error")
        else:
            error = change_status(order, new_status, g.user["name"], note)
            db.commit()
            flash(error or f"Order {ref} is now {new_status}.", "error" if error else "success")
        return redirect(url_for("admin.order_detail", ref=ref))
    customer = db.execute("SELECT * FROM users WHERE id=?", (order["user_id"],)).fetchone()
    return render_template("admin/order.html", order=order, customer=customer,
                           next_statuses=TRANSITIONS[order["status"]], **order_bundle(order))


# ---------------------------------------------------------------- messages
@bp.route("/messages")
@admin_required
def messages():
    status = request.args.get("status", "open")
    where = "WHERE status=?" if status in ("open", "answered") else ""
    rows = get_db().execute(f"SELECT * FROM messages {where} ORDER BY created_at DESC",
                            (status,) if where else ()).fetchall()
    counts = {r["status"]: r["n"] for r in get_db().execute("SELECT status, COUNT(*) n FROM messages GROUP BY status")}
    return render_template("admin/messages.html", messages=rows, status=status, counts=counts)


@bp.route("/messages/<int:mid>", methods=["POST"])
@admin_required
def message_update(mid):
    status = "answered" if request.form.get("status") == "answered" else "open"
    get_db().execute("UPDATE messages SET status=? WHERE id=?", (status, mid))
    get_db().commit()
    flash("Message marked answered." if status == "answered" else "Message reopened.", "success")
    return redirect(url_for("admin.messages", status=request.form.get("back", "open")))

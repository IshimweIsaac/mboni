import re
from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
PHONE_RE = re.compile(r"^07[2389]\d{7}$")
PROFILE_COLORS = ["#f59e0b", "#ef4444", "#22c55e", "#3b82f6", "#a855f7", "#ec4899"]


def load_user():
    g.user = g.profile = None
    uid = session.get("user_id")
    if uid is None:
        return
    db = get_db()
    g.user = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if g.user is None:
        session.clear()
        return
    pid = session.get("profile_id")
    if pid:
        g.profile = db.execute("SELECT * FROM profiles WHERE id = ? AND user_id = ?", (pid, uid)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Sign in to continue.", "info")
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapped


def profile_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.profile is None:
            return redirect(url_for("main.profiles", next=request.full_path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "admin":
            from flask import abort
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def safe_next(target, fallback):
    # Only follow local paths so the login form cannot be used as an open redirect.
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return fallback


@bp.route("/register", methods=["GET", "POST"])
def register():
    from .insights import AGE_RANGES, COMMUNITIES, GENDERS, SOURCES
    form = {"name": "", "email": "", "phone": "", "age_range": "", "gender": "", "community": "", "heard_from": ""}
    about = {"age_range": AGE_RANGES, "gender": GENDERS, "community": COMMUNITIES, "heard_from": SOURCES}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        for key, allowed in about.items():  # optional answers: keep only known values
            if form[key] not in allowed:
                form[key] = ""
        password = request.form.get("password", "")
        errors = {}
        if len(form["name"]) < 2:
            errors["name"] = "Tell us your name (at least 2 letters)."
        if not EMAIL_RE.match(form["email"]):
            errors["email"] = "That email doesn't look right, e.g. you@example.com"
        if form["phone"] and not PHONE_RE.match(form["phone"]):
            errors["phone"] = "Use a Rwandan number like 0788123456."
        if len(password) < 8:
            errors["password"] = "Use at least 8 characters."
        db = get_db()
        if not errors and db.execute("SELECT 1 FROM users WHERE email = ?", (form["email"].lower(),)).fetchone():
            errors["email"] = "An account with this email already exists. Sign in instead?"
        if errors:
            return render_template("auth/register.html", form=form, errors=errors, about=about), 400
        cur = db.execute(
            """INSERT INTO users (name, email, phone, password_hash, lang, age_range, gender, community, heard_from)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (form["name"], form["email"].lower(), form["phone"] or None, generate_password_hash(password),
             session.get("lang", "en"), form["age_range"] or None, form["gender"] or None, form["community"] or None,
             form["heard_from"] or None),
        )
        pid = db.execute("INSERT INTO profiles (user_id, name, color) VALUES (?,?,?)",
                         (cur.lastrowid, form["name"].split()[0], PROFILE_COLORS[cur.lastrowid % 6])).lastrowid
        db.commit()
        guest_cart, vid = session.get("cart"), session.get("vid")
        session.clear()
        session["user_id"], session["profile_id"] = cur.lastrowid, pid
        if vid:
            session["vid"] = vid  # keep the same clickstream from guest to member
        if guest_cart:
            from .shop import merge_guest_cart
            merge_guest_cart(cur.lastrowid, {int(k): v for k, v in guest_cart.items()})
            flash("We saved the films in your cart.", "info")
        flash(f"Karibu, {form['name'].split()[0]}! Pick a plan or rent a single film. Nyungwe is free to watch.", "success")
        return redirect(url_for("billing.plans", welcome=1))
    return render_template("auth/register.html", form=form, errors={}, about=about)


@bp.route("/login", methods=["GET", "POST"])
def login():
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], request.form.get("password", "")):
            return render_template("auth/login.html", email=email,
                                   error="Email or password is wrong. Check for typos and try again."), 401
        lang = session.get("lang")
        guest_cart, vid = session.get("cart"), session.get("vid")
        session.clear()
        session["user_id"] = user["id"]
        if vid:
            session["vid"] = vid  # keep the same clickstream from guest to member
        if guest_cart and user["role"] != "admin":
            from .shop import merge_guest_cart
            merge_guest_cart(user["id"], {int(k): v for k, v in guest_cart.items()})
        if lang:
            session["lang"] = lang
        if user["role"] == "admin":
            return redirect(safe_next(request.args.get("next"), url_for("admin.dashboard")))
        return redirect(url_for("main.profiles", next=safe_next(request.args.get("next"), "")))
    return render_template("auth/login.html", email=email, error=None)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You're signed out. See you at the next premiere!", "info")
    return redirect(url_for("main.index"))

import random

from flask import (Blueprint, abort, flash, g, jsonify, redirect, render_template, request, session,
                   url_for)

from . import catalog
from .auth import PROFILE_COLORS, login_required, profile_required, safe_next
from .catalog import COUNTRY_CODES, COVERS, MOODS, access_for, movie_by_slug, movies
from .db import get_db, now
from .i18n import LANGS
from .insights import social_proof, track, verified_reviewers

bp = Blueprint("main", __name__)

QUALITIES = {
    "240p": {"src": "media/feature-240.mp4", "mb_per_hour": 180, "label": "Data saver"},
    "480p": {"src": "media/feature-480.mp4", "mb_per_hour": 450, "label": "Standard"},
}


@bp.app_context_processor
def helpers():
    return {"access_for": access_for, "COUNTRY_CODES": COUNTRY_CODES, "COVERS": COVERS, "all_movies": lambda: movies(limit=16)}


@bp.route("/")
def index():
    if g.user:
        return redirect(url_for("main.browse"))
    track("visit")
    db = get_db()
    plans = db.execute("SELECT * FROM plans ORDER BY price").fetchall()
    trust = db.execute("SELECT (SELECT COUNT(*) FROM users WHERE role='viewer') members, "
                       "(SELECT ROUND(AVG(stars), 1) FROM reviews) rating, (SELECT COUNT(*) FROM reviews) reviews").fetchone()
    return render_template("landing.html", trust=trust, featured=movies("m.featured = 1"),
                           popular=movies(limit=12), plans=plans,
                           countries=sorted({m["country"] for m in movies()}))


@bp.route("/browse")
@profile_required
def browse():
    pid = g.profile["id"]
    db = get_db()
    track("visit")
    continuing = db.execute(
        """SELECT m.*, p.position, p.duration FROM progress p JOIN movies m ON m.id = p.movie_id
           WHERE p.profile_id = ? AND p.position < p.duration - 5 ORDER BY p.updated_at DESC""", (pid,)
    ).fetchall()
    last = db.execute(
        "SELECT m.* FROM progress p JOIN movies m ON m.id = p.movie_id WHERE p.profile_id = ? ORDER BY p.updated_at DESC LIMIT 1",
        (pid,)).fetchone()
    because = []
    if last:
        genre = last["genres"].split(",")[0]
        because = movies("m.genres LIKE ? AND m.id != ?", (f"%{genre}%", last["id"]), limit=10)

    rows = [
        ("continue", "continue_watching", continuing),
        ("top10", "top10", movies(limit=10)),
        ("new", "new_releases", movies("m.access = 'premiere' OR m.year >= 2026", order="m.created_at DESC")),
        ("because", f"Because you watched {last['title']}" if last else None, because),
        ("rwanda", "made_in_rwanda", movies("m.country = 'Rwanda'")),
        ("critics", "Critics' picks", movies("m.critic_quote IS NOT NULL")),
        ("award", "award", movies("m.award IS NOT NULL")),
        ("kids", "kids", movies("m.is_kids = 1")),
        ("music", "Music & rhythm", movies("m.genres LIKE '%Music%'")),
        ("thrill", "After dark: thrillers & crime", movies("m.genres LIKE '%Thriller%' OR m.genres LIKE '%Crime%' OR m.genres LIKE '%Horror%'")),
    ]
    rows = [r for r in rows if r[1] and r[2]]
    featured = movies("m.featured = 1") or movies(limit=5)
    in_cart = db.execute("SELECT COUNT(*) n, COALESCE(SUM(qty), 0) q FROM cart_items WHERE user_id=?", (g.user["id"],)).fetchone()
    return render_template("browse.html", rows=rows, featured=featured, in_cart=in_cart,
                           watchlist=catalog.watchlist_ids(pid), progress=catalog.progress_map(pid),
                           countries=sorted({m["country"] for m in movies()}), moods=MOODS)


@bp.route("/movie/<slug>")
def detail(slug):
    movie = movie_by_slug(slug)
    if movie is None:
        abort(404)
    db = get_db()
    reviews = db.execute(
        """SELECT r.*, u.name FROM reviews r JOIN users u ON u.id = r.user_id
           WHERE r.movie_id = ? ORDER BY r.created_at DESC, r.id DESC LIMIT 20""", (movie["id"],)).fetchall()
    genre = movie["genres"].split(",")[0]
    similar = movies("(m.genres LIKE ? OR m.country = ?) AND m.id != ?", (f"%{genre}%", movie["country"], movie["id"]), limit=12)
    ctx = {"in_list": False, "progress": 0, "my_review": None, "downloaded": False}
    if g.profile:
        pid = g.profile["id"]
        ctx["in_list"] = movie["id"] in catalog.watchlist_ids(pid)
        ctx["progress"] = catalog.progress_map(pid).get(movie["id"], 0)
        ctx["downloaded"] = bool(db.execute("SELECT 1 FROM downloads WHERE profile_id=? AND movie_id=?", (pid, movie["id"])).fetchone())
    if g.user:
        ctx["my_review"] = next((r for r in reviews if r["user_id"] == g.user["id"]), None)
    stars = {s: 0 for s in range(5, 0, -1)}
    for r in db.execute("SELECT stars, COUNT(*) c FROM reviews WHERE movie_id=? GROUP BY stars", (movie["id"],)):
        stars[r["stars"]] = r["c"]
    access = access_for(movie)
    if access["rental"]:
        access["hours_left"] = catalog.hours_left(access["rental"]["expires_at"])
    track("view_film", movie["id"])
    return render_template("detail.html", movie=movie, reviews=reviews, similar=similar, access=access,
                           stars=stars, qualities=QUALITIES, verified=verified_reviewers(movie["id"]),
                           proof=social_proof(movie["id"]), **ctx)


@bp.route("/watch/<slug>")
def watch(slug):
    movie = movie_by_slug(slug)
    if movie is None:
        abort(404)
    trailer = request.args.get("trailer") == "1"
    access = access_for(movie)
    if not trailer and not access["can_watch"]:
        if g.user is None:
            return redirect(url_for("auth.login", next=url_for("main.watch", slug=slug)))
        flash("Choose how you'd like to watch this film.", "info")
        return redirect(url_for("main.detail", slug=slug, _anchor="watch-options"))
    if not trailer and g.user and g.profile is None:
        return redirect(url_for("main.profiles", next=request.full_path))
    position = 0
    if g.profile and not trailer:
        row = get_db().execute("SELECT position, duration FROM progress WHERE profile_id=? AND movie_id=?",
                               (g.profile["id"], movie["id"])).fetchone()
        if row and row["position"] < row["duration"] - 5:
            position = row["position"]
        get_db().execute("UPDATE movies SET views = views + 1 WHERE id = ?", (movie["id"],))
        get_db().commit()
    track("trailer" if trailer else "watch", movie["id"])
    data_saver = bool(g.user and g.user["data_saver"])
    up_next = movies("m.genres LIKE ? AND m.id != ?", (f"%{movie['genres'].split(',')[0]}%", movie["id"]), limit=1)
    return render_template("watch.html", movie=movie, trailer=trailer, position=position, qualities=QUALITIES,
                           default_quality="240p" if data_saver else "480p", up_next=up_next[0] if up_next else None,
                           access=access)


@bp.route("/api/progress", methods=["POST"])
@profile_required
def save_progress():
    data = request.get_json(silent=True) or {}
    movie = get_db().execute("SELECT id FROM movies WHERE slug = ?", (data.get("slug", ""),)).fetchone()
    try:
        position, duration = float(data.get("position", 0)), float(data.get("duration", 0))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="bad numbers"), 400
    if movie is None or duration <= 0 or not 0 <= position <= duration:
        return jsonify(ok=False, error="bad input"), 400
    db = get_db()
    db.execute(
        """INSERT INTO progress VALUES (?,?,?,?,?) ON CONFLICT(profile_id, movie_id)
           DO UPDATE SET position=excluded.position, duration=excluded.duration, updated_at=excluded.updated_at""",
        (g.profile["id"], movie["id"], position, duration, now()))
    db.commit()
    return jsonify(ok=True)


@bp.route("/api/watchlist/<slug>", methods=["POST"])
@profile_required
def toggle_watchlist(slug):
    movie = movie_by_slug(slug)
    if movie is None:
        abort(404)
    db = get_db()
    pid = g.profile["id"]
    if db.execute("SELECT 1 FROM watchlist WHERE profile_id=? AND movie_id=?", (pid, movie["id"])).fetchone():
        db.execute("DELETE FROM watchlist WHERE profile_id=? AND movie_id=?", (pid, movie["id"]))
        added = False
    else:
        db.execute("INSERT INTO watchlist (profile_id, movie_id) VALUES (?,?)", (pid, movie["id"]))
        added = True
    db.commit()
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True, added=added, title=movie["title"])
    return redirect(request.referrer or url_for("main.detail", slug=slug))


@bp.route("/api/download/<slug>", methods=["POST"])
@profile_required
def download(slug):
    movie = movie_by_slug(slug)
    if movie is None:
        abort(404)
    access = access_for(movie)
    if not access["can_watch"]:
        return jsonify(ok=False, error="Rent, buy or subscribe to download this film."), 403
    if access["reason"] == "rented":
        return jsonify(ok=False, error="Rentals stream only. Buy the film to keep it offline."), 403
    db = get_db()
    sub = catalog.active_subscription(g.user["id"])
    limit = sub["downloads"] if sub else 5
    count = db.execute("SELECT COUNT(*) FROM downloads WHERE profile_id=?", (g.profile["id"],)).fetchone()[0]
    exists = db.execute("SELECT 1 FROM downloads WHERE profile_id=? AND movie_id=?", (g.profile["id"], movie["id"])).fetchone()
    if request.args.get("remove"):
        db.execute("DELETE FROM downloads WHERE profile_id=? AND movie_id=?", (g.profile["id"], movie["id"]))
        db.commit()
        return jsonify(ok=True, removed=True)
    if not exists and count >= limit:
        return jsonify(ok=False, error=f"Your plan allows {limit} downloads. Remove one in Library first."), 403
    quality = "240p" if g.user["data_saver"] else "480p"
    if not exists:
        db.execute("INSERT INTO downloads VALUES (?,?,?,?)", (g.profile["id"], movie["id"], quality, now()))
        db.commit()
    return jsonify(ok=True, src=url_for("static", filename=QUALITIES[quality]["src"]), quality=quality)


@bp.route("/movie/<slug>/review", methods=["POST"])
@login_required
def review(slug):
    movie = movie_by_slug(slug)
    if movie is None:
        abort(404)
    try:
        stars = int(request.form.get("stars", 0))
    except ValueError:
        stars = 0
    body = request.form.get("body", "").strip()[:600]
    if not 1 <= stars <= 5:
        flash("Pick between 1 and 5 stars.", "error")
        return redirect(url_for("main.detail", slug=slug, _anchor="reviews"))
    db = get_db()
    db.execute(
        """INSERT INTO reviews (user_id, movie_id, stars, body, created_at) VALUES (?,?,?,?,?)
           ON CONFLICT(user_id, movie_id) DO UPDATE SET stars=excluded.stars, body=excluded.body,
           created_at=excluded.created_at""", (g.user["id"], movie["id"], stars, body, now()))
    db.commit()
    track("review", movie["id"])
    flash("Thanks! Your review is live.", "success")
    return redirect(url_for("main.detail", slug=slug, _anchor="reviews"))


def search_movies(args):
    where, params = ["1=1"], []
    q = args.get("q", "").strip()
    if q:
        like = f"%{q}%"
        where.append("(m.title LIKE ? OR m.cast_list LIKE ? OR m.director LIKE ? OR m.country LIKE ? "
                     "OR m.language LIKE ? OR m.genres LIKE ? OR m.synopsis LIKE ?)")
        params += [like] * 7
    for field, column in [("country", "m.country"), ("genre", "m.genres"), ("language", "m.language")]:
        value = args.get(field, "").strip()
        if value:
            where.append(f"{column} LIKE ?")
            params.append(f"%{value}%")
    mood = args.get("mood")
    if mood in MOODS:
        where.append("m.genres LIKE ?")
        params.append(f"%{MOODS[mood][1]}%")
    access = args.get("access")
    if access in ("sub", "premiere", "free"):
        where.append("m.access = ?")
        params.append(access)
    order = {"new": "m.year DESC, m.created_at DESC", "rating": "score DESC", "price": "m.rent_price ASC"}.get(
        args.get("sort"), "m.views DESC")
    return movies(" AND ".join(where), params, order=order)


@bp.route("/search")
def search():
    results = search_movies(request.args)
    if request.args.get("q", "").strip():
        track("search", detail=request.args["q"].strip().lower())
    everything = movies()
    facets = {
        "country": sorted({m["country"] for m in everything}),
        "genre": sorted({g_ for m in everything for g_ in m["genres"].split(",")}),
        "language": sorted({l.strip() for m in everything for l in m["language"].split(",")}),
    }
    pid = g.profile["id"] if g.profile else None
    return render_template("search.html", results=results, facets=facets, args=request.args, moods=MOODS,
                           watchlist=catalog.watchlist_ids(pid) if pid else set(),
                           progress=catalog.progress_map(pid) if pid else {})


@bp.route("/api/search")
def api_search():
    results = search_movies(request.args)[:8]
    return jsonify([{
        "slug": m["slug"], "title": m["title"], "year": m["year"], "country": m["country"],
        "genres": m["genres"].replace(",", " · "), "c1": m["c1"], "c2": m["c2"], "c3": m["c3"],
        "pattern": m["pattern"], "url": url_for("main.detail", slug=m["slug"]),
        "cover": url_for("static", filename=COVERS[m["slug"]]["file"]) if m["slug"] in COVERS else None,
    } for m in results])


@bp.route("/surprise")
def surprise():
    pool = movies()
    return redirect(url_for("main.detail", slug=random.choice(pool)["slug"]))


@bp.route("/my-list")
@profile_required
def my_list():
    rows = get_db().execute(
        "SELECT movie_id FROM watchlist WHERE profile_id=? ORDER BY added_at DESC", (g.profile["id"],)).fetchall()
    ids = [r["movie_id"] for r in rows]
    by_id = {m["id"]: m for m in movies()}
    items = [by_id[i] for i in ids if i in by_id]
    return render_template("my_list.html", items=items, watchlist=set(ids),
                           progress=catalog.progress_map(g.profile["id"]))


@bp.route("/library")
@profile_required
def library():
    db = get_db()
    uid = g.user["id"]
    rentals = db.execute(
        """SELECT m.*, p.expires_at, p.created_at AS rented_at FROM purchases p JOIN movies m ON m.id = p.movie_id
           WHERE p.user_id=? AND p.kind='rent' AND p.expires_at > ? ORDER BY p.expires_at""", (uid, now())).fetchall()
    owned = db.execute(
        """SELECT m.*, p.created_at AS bought_at FROM purchases p JOIN movies m ON m.id = p.movie_id
           WHERE p.user_id=? AND p.kind='buy' ORDER BY p.created_at DESC""", (uid,)).fetchall()
    downloads = db.execute(
        """SELECT m.*, d.quality, d.created_at AS saved_at FROM downloads d JOIN movies m ON m.id = d.movie_id
           WHERE d.profile_id=? ORDER BY d.created_at DESC""", (g.profile["id"],)).fetchall()
    history = db.execute(
        """SELECT m.*, p.position, p.duration, p.updated_at FROM progress p JOIN movies m ON m.id = p.movie_id
           WHERE p.profile_id=? ORDER BY p.updated_at DESC""", (g.profile["id"],)).fetchall()
    return render_template("library.html", rentals=rentals, owned=owned, downloads=downloads, history=history,
                           hours_left=catalog.hours_left, sub=catalog.active_subscription(uid),
                           watched_minutes=int(sum(h["position"] for h in history) // 60))


@bp.route("/profiles", methods=["GET", "POST"])
@login_required
def profiles():
    db = get_db()
    uid = g.user["id"]
    sub = catalog.active_subscription(uid)
    max_profiles = sub["max_profiles"] if sub else 2
    existing = db.execute("SELECT * FROM profiles WHERE user_id=? ORDER BY id", (uid,)).fetchall()
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:20]
        if not name:
            flash("Give the profile a name.", "error")
        elif len(existing) >= max_profiles:
            flash(f"Your plan allows {max_profiles} profiles. Upgrade for more.", "error")
        else:
            db.execute("INSERT INTO profiles (user_id, name, color, is_kids) VALUES (?,?,?,?)",
                       (uid, name, PROFILE_COLORS[len(existing) % len(PROFILE_COLORS)],
                        1 if request.form.get("is_kids") else 0))
            db.commit()
            flash(f"Profile {name} created.", "success")
        return redirect(url_for("main.profiles", next=request.args.get("next", "")))
    return render_template("profiles.html", profiles=existing, max_profiles=max_profiles,
                           next=request.args.get("next", ""))


@bp.route("/profiles/<int:pid>/use", methods=["POST"])
@login_required
def use_profile(pid):
    row = get_db().execute("SELECT * FROM profiles WHERE id=? AND user_id=?", (pid, g.user["id"])).fetchone()
    if row is None:
        abort(404)
    session["profile_id"] = row["id"]
    return redirect(safe_next(request.form.get("next"), url_for("main.browse")))


@bp.route("/profiles/<int:pid>/delete", methods=["POST"])
@login_required
def delete_profile(pid):
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM profiles WHERE user_id=?", (g.user["id"],)).fetchone()[0]
    if count <= 1:
        flash("You need at least one profile.", "error")
    else:
        db.execute("DELETE FROM profiles WHERE id=? AND user_id=?", (pid, g.user["id"]))
        db.commit()
        if session.get("profile_id") == pid:
            session.pop("profile_id")
    return redirect(url_for("main.profiles"))


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    db = get_db()
    if request.method == "POST":
        lang = request.form.get("lang", "en")
        phone = request.form.get("phone", "").strip()
        from .auth import PHONE_RE
        if phone and not PHONE_RE.match(phone):
            flash("Use a Rwandan number like 0788123456.", "error")
            return redirect(url_for("main.settings"))
        db.execute("UPDATE users SET lang=?, data_saver=?, phone=? WHERE id=?",
                   (lang if lang in LANGS else "en", 1 if request.form.get("data_saver") else 0,
                    phone or None, g.user["id"]))
        db.commit()
        session["lang"] = lang if lang in LANGS else "en"
        flash("Settings saved.", "success")
        return redirect(url_for("main.settings"))
    uid = g.user["id"]
    sub = catalog.active_subscription(uid)
    transactions = db.execute(
        """SELECT t.*, m.title FROM transactions t LEFT JOIN movies m ON m.id = t.movie_id
           WHERE t.user_id=? ORDER BY t.created_at DESC LIMIT 20""", (uid,)).fetchall()
    return render_template("settings.html", sub=sub, transactions=transactions,
                           plans=db.execute("SELECT * FROM plans ORDER BY price").fetchall())


@bp.route("/lang/<code>")
def set_lang(code):
    if code in LANGS:
        session["lang"] = code
        if g.user:
            get_db().execute("UPDATE users SET lang=? WHERE id=?", (code, g.user["id"]))
            get_db().commit()
    return redirect(safe_next(request.args.get("next"), url_for("main.index")))


@bp.route("/credits")
def credits():
    titles = {m["slug"]: m["title"] for m in get_db().execute("SELECT slug, title FROM movies")}
    return render_template("credits.html", covers=COVERS, titles=titles)


@bp.route("/offline")
def offline():
    return render_template("offline.html")


@bp.route("/sw.js")
def service_worker():
    from flask import current_app, send_from_directory
    response = send_from_directory(current_app.static_folder, "js/sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response

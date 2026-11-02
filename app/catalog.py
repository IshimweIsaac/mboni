"""Who can watch what, and the queries the browse pages are built from."""
import json
import os
from datetime import datetime

from flask import g

from .db import get_db, now

PREMIERE_SUB_DISCOUNT = 20  # subscribers pay 20% less to rent or buy a premiere

MOODS = {
    "laugh": ("Make me laugh", "Comedy"),
    "cry": ("I want to feel something", "Drama"),
    "thrill": ("Edge of my seat", "Thriller"),
    "love": ("Date night", "Romance"),
    "learn": ("Teach me something", "Documentary"),
    "family": ("Family movie night", "Family"),
}

COUNTRY_CODES = {
    "Rwanda": "RW", "Nigeria": "NG", "Ghana": "GH", "Kenya": "KE", "South Africa": "ZA", "Senegal": "SN",
    "Tanzania": "TZ", "Burundi": "BI", "Uganda": "UG", "DR Congo": "CD", "Ethiopia": "ET", "Egypt": "EG",
    "Cameroon": "CM", "Benin": "BJ", "Niger": "NE",
}


# Real cover photos (free licences, from Wikimedia Commons). Films without one fall back to generated patterns.
_CREDITS = os.path.join(os.path.dirname(__file__), "static", "covers", "credits.json")
COVERS = json.load(open(_CREDITS, encoding="utf-8")) if os.path.exists(_CREDITS) else {}


def active_subscription(user_id):
    return get_db().execute(
        """SELECT s.*, p.name AS plan_name, p.quality, p.downloads, p.profiles AS max_profiles, p.price
           FROM subscriptions s JOIN plans p ON p.code = s.plan_code
           WHERE s.user_id = ? AND s.expires_at > ? ORDER BY s.expires_at DESC LIMIT 1""",
        (user_id, now()),
    ).fetchone()


def ownership(user_id, movie_id):
    """Return ('buy', row), ('rent', row) for a live rental, or (None, None)."""
    rows = get_db().execute(
        "SELECT * FROM purchases WHERE user_id = ? AND movie_id = ? ORDER BY kind = 'buy' DESC, expires_at DESC",
        (user_id, movie_id),
    ).fetchall()
    for row in rows:
        if row["kind"] == "buy":
            return "buy", row
        if row["expires_at"] and row["expires_at"] > now():
            return "rent", row
    return None, None


def access_for(movie, user=None):
    """Explain how the current user can (or could) watch a movie.

    Returns a dict the templates use directly: can_watch, reason, and the
    prices to show when they cannot watch yet.
    """
    user = user if user is not None else g.get("user")
    info = {"can_watch": False, "reason": None, "rental": None, "rent_price": movie["rent_price"],
            "buy_price": movie["buy_price"], "discount": 0, "subscribed": False}
    if movie["access"] == "free":
        info.update(can_watch=True, reason="free")
        return info
    if user is None:
        return info
    if user["role"] == "admin":
        info.update(can_watch=True, reason="admin")
        return info
    kind, row = ownership(user["id"], movie["id"])
    sub = active_subscription(user["id"])
    info["subscribed"] = bool(sub)
    if sub and movie["access"] == "premiere":
        info["discount"] = PREMIERE_SUB_DISCOUNT
        info["rent_price"] = movie["rent_price"] * (100 - PREMIERE_SUB_DISCOUNT) // 100
        info["buy_price"] = movie["buy_price"] * (100 - PREMIERE_SUB_DISCOUNT) // 100
    if kind == "buy":
        info.update(can_watch=True, reason="owned")
    elif kind == "rent":
        info.update(can_watch=True, reason="rented", rental=row)
    elif sub and movie["access"] == "sub":
        info.update(can_watch=True, reason="subscription")
    return info


def hours_left(expires_at):
    delta = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S") - datetime.now()
    return max(0, int(delta.total_seconds() // 3600))


def kids_filter():
    return "AND m.is_kids = 1" if g.get("profile") and g.profile["is_kids"] else ""


def movies(where="1=1", params=(), order="m.views DESC", limit=None):
    sql = f"""SELECT m.*, ROUND(AVG(r.stars), 1) AS score, COUNT(r.id) AS review_count
              FROM movies m LEFT JOIN reviews r ON r.movie_id = m.id
              WHERE ({where}) {kids_filter()} GROUP BY m.id ORDER BY {order}"""
    if limit:
        sql += f" LIMIT {int(limit)}"
    return get_db().execute(sql, params).fetchall()


def movie_by_slug(slug):
    rows = movies("m.slug = ?", (slug,))
    return rows[0] if rows else None


def progress_map(profile_id):
    rows = get_db().execute("SELECT movie_id, position, duration FROM progress WHERE profile_id = ?", (profile_id,))
    return {r["movie_id"]: min(100, int(100 * r["position"] / r["duration"])) if r["duration"] else 0 for r in rows}


def watchlist_ids(profile_id):
    return {r["movie_id"] for r in get_db().execute("SELECT movie_id FROM watchlist WHERE profile_id = ?", (profile_id,))}

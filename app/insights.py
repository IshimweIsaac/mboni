"""Understanding the online consumer: clickstream tracking and the analytics built on it.

Every important step a visitor takes is stored in the `events` table (the clickstream):

    visit -> search / view_film -> trailer / add_to_cart / checkout -> purchase -> watch / review

Those steps map onto the five stages of the online purchasing decision:

    1. Awareness of need       a visit to the home or browse page
    2. Search for information  a search, or opening a film page
    3. Evaluation              watching a trailer, adding to the cart, starting checkout
    4. Purchase decision       a paid rental, purchase, subscription or cart order
    5. Post-purchase contact   watching what they paid for, or writing a review

Members can also tell us (optionally) their age range, gender, community and how they heard about
Mboni, which gives the audience, reference-group and opinion-leader breakdowns on the admin page.
"""
import re
import secrets
from datetime import datetime, timedelta

from flask import g, request, session

from .db import get_db, now

AGE_RANGES = ["Under 18", "18–24", "25–34", "35–44", "45+"]
GENDERS = ["Female", "Male", "Prefer not to say"]
COMMUNITIES = ["Kigali city", "Other town", "Rural area", "Outside Rwanda"]
SOURCES = {
    "friends": "Friends or family (reference group)",
    "whatsapp": "WhatsApp group",
    "influencer": "Influencer or critic (opinion leader)",
    "social": "Social media ad",
    "search": "Search engine",
    "radio_tv": "Radio or TV (traditional media)",
    "poster": "Poster or event",
}
STAGES = [
    ("awareness", "Awareness of need", "Visited Mboni", ("visit",)),
    ("search", "Search for information", "Searched or opened a film page", ("search", "view_film")),
    ("evaluation", "Evaluation of alternatives", "Watched a trailer, added to cart or started checkout", ("trailer", "add_to_cart", "checkout")),
    ("purchase", "Purchase decision", "Paid for a film, plan or cart", ("purchase",)),
    ("post", "Post-purchase contact", "Watched what they paid for or wrote a review", ("watch", "review")),
]
EVENT_TYPES = {t for stage in STAGES for t in stage[3]}
SMALL_TICKET = 3000  # RWF: rentals and the Mobile plan are "small-ticket"; purchases and bigger plans "big-ticket"

MOBILE_RE = re.compile(r"Mobile|Android|iPhone|iPad|Opera Mini|KaiOS", re.I)


def device_of(user_agent):
    return "mobile" if MOBILE_RE.search(user_agent or "") else "desktop"


def visitor_id():
    if "vid" not in session:
        session["vid"] = secrets.token_hex(8)
    return session["vid"]


def track(kind, movie_id=None, detail=None):
    """Record one step of the clickstream. Admin activity is not counted."""
    if kind not in EVENT_TYPES:
        raise ValueError(kind)
    user = g.get("user")
    if user is not None and user["role"] == "admin":
        return
    get_db().execute(
        "INSERT INTO events (visitor, user_id, type, movie_id, detail, device, created_at) VALUES (?,?,?,?,?,?,?)",
        (visitor_id(), user["id"] if user else None, kind, movie_id, (detail or "")[:80] or None,
         device_of(request.headers.get("User-Agent")), now()))
    get_db().commit()


def verified_reviewers(movie_id):
    """User ids whose review counts as 'verified': they rented, bought or subscribed."""
    rows = get_db().execute(
        """SELECT DISTINCT r.user_id FROM reviews r WHERE r.movie_id = ? AND (
             EXISTS (SELECT 1 FROM purchases p WHERE p.user_id = r.user_id AND p.movie_id = r.movie_id)
             OR EXISTS (SELECT 1 FROM transactions t WHERE t.user_id = r.user_id AND t.status = 'paid'))""",
        (movie_id,))
    return {r["user_id"] for r in rows}


def social_proof(movie_id):
    """Plays this week and the age group that watches it most (for the film page)."""
    db = get_db()
    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    week = db.execute("SELECT COUNT(DISTINCT visitor) FROM events WHERE movie_id=? AND type IN ('view_film','watch','trailer') AND created_at >= ?",
                      (movie_id, since)).fetchone()[0]
    top = db.execute(
        """SELECT u.age_range, COUNT(*) n FROM events e JOIN users u ON u.id = e.user_id
           WHERE e.movie_id = ? AND u.age_range IS NOT NULL GROUP BY u.age_range ORDER BY n DESC LIMIT 1""",
        (movie_id,)).fetchone()
    return {"week": week, "top_age": top["age_range"] if top else None}


def _pct(part, whole):
    return round(100 * part / whole, 1) if whole else 0


def report(days=30):
    """Everything on the admin 'Customers' page."""
    db = get_db()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    # 1. The five-stage funnel, counted in unique visitors
    reached = {}
    for key, *_rest, types in STAGES:
        marks = ",".join("?" * len(types))
        reached[key] = db.execute(
            f"SELECT COUNT(DISTINCT visitor) FROM events WHERE type IN ({marks}) AND created_at >= ?", (*types, since)).fetchone()[0]
    top = reached["awareness"] or 1
    funnel, previous = [], None
    for key, name, means, _types in STAGES:
        n = reached[key]
        funnel.append({"key": key, "name": name, "means": means, "n": n, "of_all": _pct(n, top),
                       "from_prev": _pct(n, previous) if previous is not None else 100.0,
                       "lost": (previous - n) if previous is not None else 0})
        previous = n

    # 2. Browsers versus buyers (members), and devices
    members = db.execute("SELECT COUNT(*) FROM users WHERE role='viewer'").fetchone()[0]
    buyers = db.execute("SELECT COUNT(DISTINCT user_id) FROM transactions WHERE status='paid'").fetchone()[0]
    repeat = db.execute("SELECT COUNT(*) FROM (SELECT user_id FROM transactions WHERE status='paid' GROUP BY user_id HAVING COUNT(*) > 1)").fetchone()[0]
    devices = {r["device"]: r["n"] for r in db.execute(
        "SELECT device, COUNT(DISTINCT visitor) n FROM events WHERE created_at >= ? GROUP BY device", (since,))}
    mobile_buy = db.execute("SELECT COUNT(DISTINCT visitor) FROM events WHERE type='purchase' AND device='mobile' AND created_at >= ?", (since,)).fetchone()[0]
    desktop_buy = db.execute("SELECT COUNT(DISTINCT visitor) FROM events WHERE type='purchase' AND device='desktop' AND created_at >= ?", (since,)).fetchone()[0]

    # 3. Audience: members by segment, and how many of each segment buy
    def segment(column, order):
        rows = {r["v"]: r for r in db.execute(
            f"""SELECT COALESCE(u.{column}, 'Not given') v, COUNT(*) n,
                       SUM(EXISTS (SELECT 1 FROM transactions t WHERE t.user_id=u.id AND t.status='paid')) b
                FROM users u WHERE u.role='viewer' GROUP BY v""")}
        out = []
        for label in order + ["Not given"]:
            r = rows.get(label)
            if r:
                out.append({"label": label, "n": r["n"], "buyers": r["b"], "rate": _pct(r["b"], r["n"])})
        return out

    audience = {
        "Age": segment("age_range", AGE_RANGES),
        "Gender": segment("gender", GENDERS),
        "Community": segment("community", COMMUNITIES),
    }
    sources = []
    for code, label in SOURCES.items():
        row = db.execute(
            """SELECT COUNT(*) n, SUM(EXISTS (SELECT 1 FROM transactions t WHERE t.user_id=u.id AND t.status='paid')) b
               FROM users u WHERE u.role='viewer' AND u.heard_from=?""", (code,)).fetchone()
        sources.append({"code": code, "label": label, "n": row["n"], "buyers": row["b"] or 0, "rate": _pct(row["b"] or 0, row["n"])})
    sources.sort(key=lambda s: -s["n"])

    # 4. What they buy: small-ticket versus big-ticket
    tickets = db.execute(
        f"""SELECT SUM(amount <= {SMALL_TICKET}) small_n, SUM(CASE WHEN amount <= {SMALL_TICKET} THEN amount ELSE 0 END) small_v,
                   SUM(amount > {SMALL_TICKET}) big_n, SUM(CASE WHEN amount > {SMALL_TICKET} THEN amount ELSE 0 END) big_v
            FROM transactions WHERE status='paid' AND created_at >= ?""", (since,)).fetchone()

    # 5. Trust and utility signals
    reviews = db.execute("SELECT COUNT(*) n, ROUND(AVG(stars), 2) avg FROM reviews").fetchone()
    verified = db.execute(
        """SELECT COUNT(*) FROM reviews r WHERE EXISTS (SELECT 1 FROM purchases p WHERE p.user_id=r.user_id AND p.movie_id=r.movie_id)
           OR EXISTS (SELECT 1 FROM transactions t WHERE t.user_id=r.user_id AND t.status='paid')""").fetchone()[0]
    tx = db.execute("SELECT COUNT(*) n, SUM(status='failed') failed FROM transactions WHERE created_at >= ?", (since,)).fetchone()
    orders = db.execute("SELECT COUNT(*) n, SUM(status='refunded') refunded FROM orders").fetchone()
    abandoned = db.execute("SELECT COUNT(DISTINCT user_id) FROM cart_items").fetchone()[0]

    searches = db.execute(
        """SELECT LOWER(detail) term, COUNT(*) n FROM events WHERE type='search' AND detail IS NOT NULL AND created_at >= ?
           GROUP BY term ORDER BY n DESC LIMIT 8""", (since,)).fetchall()

    # 6. A few recent clickstreams (one line per visitor, in order)
    recent = db.execute("SELECT visitor, MAX(created_at) last FROM events GROUP BY visitor ORDER BY last DESC LIMIT 8").fetchall()
    streams = []
    for r in recent:
        steps = db.execute(
            """SELECT e.type, e.detail, e.device, e.created_at, m.title, u.name FROM events e
               LEFT JOIN movies m ON m.id = e.movie_id LEFT JOIN users u ON u.id = e.user_id
               WHERE e.visitor = ? ORDER BY e.created_at, e.id LIMIT 12""", (r["visitor"],)).fetchall()
        streams.append({"visitor": r["visitor"], "who": next((s["name"] for s in steps if s["name"]), "Guest"),
                        "device": steps[-1]["device"] if steps else "", "last": r["last"], "steps": steps,
                        "bought": any(s["type"] == "purchase" for s in steps)})

    visitors = reached["awareness"]
    return {
        "days": days, "funnel": funnel, "visitors": visitors,
        "conversion": _pct(reached["purchase"], visitors),
        "members": members, "buyers": buyers, "browsers": members - buyers, "buyer_rate": _pct(buyers, members),
        "repeat": repeat, "repeat_rate": _pct(repeat, buyers),
        "devices": devices, "mobile_share": _pct(devices.get("mobile", 0), sum(devices.values())),
        "device_conv": {"mobile": _pct(mobile_buy, devices.get("mobile", 0)), "desktop": _pct(desktop_buy, devices.get("desktop", 0))},
        "audience": audience, "sources": sources,
        "tickets": {"small_n": tickets["small_n"] or 0, "small_v": tickets["small_v"] or 0,
                    "big_n": tickets["big_n"] or 0, "big_v": tickets["big_v"] or 0},
        "trust": {"reviews": reviews["n"], "avg": reviews["avg"] or 0, "verified": _pct(verified, reviews["n"]),
                  "failed": _pct(tx["failed"] or 0, tx["n"]), "refunds": _pct(orders["refunded"] or 0, orders["n"]),
                  "abandoned": abandoned},
        "searches": searches, "streams": streams, "small_ticket": SMALL_TICKET,
    }

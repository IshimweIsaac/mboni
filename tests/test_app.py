import os
import tempfile
import unittest

from app import create_app
from app.billing import luhn_ok
from app.db import get_db


class MboniTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path})
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    # helpers -------------------------------------------------------------
    def csrf(self):
        self.client.get("/login")
        with self.client.session_transaction() as s:
            return s["csrf"]

    def post(self, url, data=None, **kw):
        data = dict(data or {})
        data["csrf"] = self.csrf()
        return self.client.post(url, data=data, **kw)

    def login(self, email="demo@mboni.rw", password="demo1234", profile=True):
        r = self.post("/login", {"email": email, "password": password})
        if profile:
            with self.app.app_context():
                pid = get_db().execute(
                    "SELECT p.id FROM profiles p JOIN users u ON u.id = p.user_id WHERE u.email=? AND p.is_kids=0",
                    (email,)).fetchone()["id"]
            self.post(f"/profiles/{pid}/use")
        return r

    def register(self, email="new@example.rw"):
        return self.post("/register", {"name": "Keza Uwase", "email": email, "password": "goodpass1", "phone": "0788000111"})

    def pay(self, data, action="approve"):
        r = self.post("/checkout", data)
        self.assertEqual(r.status_code, 302, r.data[:500])
        ref = r.location.rsplit("/", 1)[-1]
        self.post(f"/pay/{ref}/confirm", {"action": action})
        with self.app.app_context():
            return get_db().execute("SELECT * FROM transactions WHERE ref=?", (ref,)).fetchone()


class PublicPages(MboniTestCase):
    def test_landing_and_public_pages_render(self):
        for url in ["/", "/plans", "/search", "/movie/nyungwe", "/login", "/register", "/offline"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_unknown_movie_is_404(self):
        self.assertEqual(self.client.get("/movie/not-a-film").status_code, 404)

    def test_free_film_plays_without_account(self):
        self.assertEqual(self.client.get("/watch/nyungwe").status_code, 200)

    def test_paid_film_redirects_guest_to_login(self):
        r = self.client.get("/watch/amas-gold")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.location)

    def test_trailer_is_open_to_everyone(self):
        r = self.client.get("/watch/queen-of-dahomey?trailer=1")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'data-trailer="true"', r.data)

    def test_search_by_country_language_and_text(self):
        r = self.client.get("/search?country=Rwanda")
        self.assertIn(b"Kigali in Bloom", r.data)
        self.assertNotIn(b"Lagos After Midnight</strong>", r.data)
        self.assertIn(b"Matatu Kings", self.client.get("/search?language=Sheng").data)
        data = self.client.get("/api/search?q=kora").get_json()
        self.assertEqual(data[0]["slug"], "griot-de-dakar")

    def test_mood_filter(self):
        r = self.client.get("/search?mood=laugh")
        self.assertIn(b"Matatu Kings", r.data)
        self.assertNotIn(b"Nyungwe</strong>", r.data)

    def test_language_switch(self):
        self.client.get("/lang/rw")
        self.assertIn(b"Iyandikishe", self.client.get("/").data)
        self.client.get("/lang/fr")
        self.assertIn(b"S&#39;inscrire", self.client.get("/").data)


class Security(MboniTestCase):
    def test_post_without_csrf_is_rejected(self):
        r = self.client.post("/login", data={"email": "demo@mboni.rw", "password": "demo1234"})
        self.assertEqual(r.status_code, 400)

    def test_open_redirect_blocked(self):
        r = self.post("/login?next=//evil.example", {"email": "admin@mboni.rw", "password": "admin123"})
        self.assertNotIn("evil", r.location)

    def test_admin_pages_need_admin(self):
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.login()
        self.assertEqual(self.client.get("/admin/").status_code, 403)

    def test_cannot_view_someone_elses_receipt(self):
        self.login()
        self.assertEqual(self.client.get("/receipt/NYDEMO000001").status_code, 200)
        self.post("/logout")
        self.login("viewer1@example.rw", "password1")
        self.assertEqual(self.client.get("/receipt/NYDEMO000001").status_code, 404)

    def test_passwords_are_hashed(self):
        with self.app.app_context():
            h = get_db().execute("SELECT password_hash FROM users WHERE email='demo@mboni.rw'").fetchone()[0]
        self.assertNotIn("demo1234", h)


class Accounts(MboniTestCase):
    def test_register_creates_user_and_profile(self):
        r = self.register()
        self.assertEqual(r.status_code, 302)
        self.assertIn("/plans", r.location)
        with self.app.app_context():
            n = get_db().execute("SELECT COUNT(*) FROM profiles p JOIN users u ON u.id=p.user_id WHERE u.email='new@example.rw'").fetchone()[0]
        self.assertEqual(n, 1)

    def test_register_validation(self):
        r = self.post("/register", {"name": "K", "email": "bad", "password": "short", "phone": "123"})
        self.assertEqual(r.status_code, 400)
        for msg in [b"at least 2 letters", b"doesn&#39;t look right", b"Rwandan number", b"at least 8"]:
            self.assertIn(msg, r.data)

    def test_duplicate_email(self):
        r = self.post("/register", {"name": "Someone", "email": "demo@mboni.rw", "password": "goodpass1"})
        self.assertIn(b"already exists", r.data)

    def test_wrong_password(self):
        r = self.post("/login", {"email": "demo@mboni.rw", "password": "nope"})
        self.assertEqual(r.status_code, 401)

    def test_kids_profile_only_sees_kids_films(self):
        self.login(profile=False)
        with self.app.app_context():
            kid = get_db().execute("SELECT id FROM profiles WHERE name='Kids'").fetchone()["id"]
        self.post(f"/profiles/{kid}/use")
        r = self.client.get("/browse")
        self.assertIn(b"Imigongo", r.data)
        self.assertNotIn(b"Night Bus to Nakuru", r.data)
        self.assertEqual(self.client.get("/movie/night-bus-nakuru").status_code, 404)

    def test_profile_limit_follows_plan(self):
        self.register()
        self.post("/profiles", {"name": "Second"})
        r = self.post("/profiles", {"name": "Third"}, follow_redirects=True)
        self.assertIn(b"allows 2 profiles", r.data)


class Access(MboniTestCase):
    def test_subscriber_can_watch_catalogue_but_not_premiere(self):
        self.login()
        self.assertEqual(self.client.get("/watch/amas-gold").status_code, 200)
        self.assertEqual(self.client.get("/watch/queen-of-dahomey").status_code, 302)

    def test_subscriber_gets_premiere_discount(self):
        self.login()
        r = self.client.get("/checkout?kind=rent&movie=queen-of-dahomey")
        self.assertIn(b"2,400 RWF", r.data)  # 3,000 less 20%

    def test_active_rental_unlocks_premiere(self):
        self.login()
        self.assertEqual(self.client.get("/watch/lagos-after-midnight").status_code, 200)

    def test_new_user_without_plan_is_sent_to_options(self):
        self.register()
        r = self.client.get("/watch/amas-gold")
        self.assertEqual(r.status_code, 302)
        self.assertIn("watch-options", r.location)


class Payments(MboniTestCase):
    def test_luhn(self):
        self.assertTrue(luhn_ok("4242424242424242"))
        self.assertFalse(luhn_ok("4242424242424241"))

    def test_rent_with_momo_and_promo(self):
        self.register()
        tx = self.pay({"kind": "rent", "movie": "amas-gold", "method": "mtn", "phone": "0788123456", "promo": "student50"})
        self.assertEqual(tx["status"], "paid")
        self.assertEqual(tx["amount"], 500)
        self.assertEqual(tx["discount"], 500)
        self.assertEqual(tx["account"], "078****456")
        self.assertEqual(self.client.get("/watch/amas-gold").status_code, 200)

    def test_subscribe_unlocks_catalogue(self):
        self.register()
        tx = self.pay({"kind": "subscription", "plan": "mobile", "method": "airtel", "phone": "0731234567"})
        self.assertEqual(tx["status"], "paid")
        self.assertEqual(self.client.get("/watch/soweto-skies").status_code, 200)

    def test_buy_with_card_never_stores_full_number(self):
        self.register()
        tx = self.pay({"kind": "buy", "movie": "matatu-kings", "method": "card", "card": "4242 4242 4242 4242",
                       "expiry": "12/30", "cvc": "123"})
        self.assertEqual(tx["status"], "paid")
        self.assertEqual(tx["account"], "**** 4242")

    def test_declined_card_and_phone(self):
        self.register()
        tx = self.pay({"kind": "buy", "movie": "matatu-kings", "method": "card", "card": "4000000000000002",
                       "expiry": "12/30", "cvc": "123"})
        self.assertEqual(tx["status"], "failed")
        tx = self.pay({"kind": "rent", "movie": "matatu-kings", "method": "mtn", "phone": "0788120000"})
        self.assertEqual(tx["status"], "failed")
        self.assertEqual(self.client.get("/watch/matatu-kings").status_code, 302)

    def test_customer_cancels_payment(self):
        self.register()
        tx = self.pay({"kind": "rent", "movie": "matatu-kings", "method": "mtn", "phone": "0788123456"}, action="cancel")
        self.assertEqual(tx["status"], "failed")

    def test_checkout_validation(self):
        self.register()
        r = self.post("/checkout", {"kind": "rent", "movie": "amas-gold", "method": "airtel", "phone": "0788123456"})
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"start with 072 or 073", r.data)
        r = self.post("/checkout", {"kind": "rent", "movie": "amas-gold", "method": "card", "card": "1234",
                                    "expiry": "01/20", "cvc": "1"})
        for msg in [b"isn&#39;t valid", b"expired", b"3 or 4 digits"]:
            self.assertIn(msg, r.data)
        r = self.post("/checkout", {"kind": "rent", "movie": "amas-gold", "method": "mtn", "phone": "0788123456", "promo": "FAKE"})
        self.assertIn(b"code isn&#39;t valid", r.data)

    def test_free_films_cannot_be_sold(self):
        self.register()
        self.assertEqual(self.client.get("/checkout?kind=rent&movie=nyungwe").status_code, 404)

    def test_cancel_keeps_access_until_expiry(self):
        self.login()
        self.post("/subscription/cancel")
        with self.app.app_context():
            sub = get_db().execute("SELECT auto_renew FROM subscriptions s JOIN users u ON u.id=s.user_id WHERE u.email='demo@mboni.rw'").fetchone()
        self.assertEqual(sub["auto_renew"], 0)
        self.assertEqual(self.client.get("/watch/amas-gold").status_code, 200)


class Viewing(MboniTestCase):
    def test_watchlist_toggle(self):
        self.login()
        r = self.client.post("/api/watchlist/amas-gold", headers={"X-CSRF": self.csrf(), "X-Requested-With": "fetch"})
        self.assertTrue(r.get_json()["added"])
        self.assertIn(b"Ama&#39;s Gold", self.client.get("/my-list").data)
        r = self.client.post("/api/watchlist/amas-gold", headers={"X-CSRF": self.csrf(), "X-Requested-With": "fetch"})
        self.assertFalse(r.get_json()["added"])

    def test_progress_saved_and_resumed(self):
        self.login()
        r = self.client.post("/api/progress", json={"slug": "amas-gold", "position": 42, "duration": 150},
                             headers={"X-CSRF": self.csrf()})
        self.assertTrue(r.get_json()["ok"])
        self.assertIn(b'data-start="42.0"', self.client.get("/watch/amas-gold").data)
        r = self.client.post("/api/progress", json={"slug": "amas-gold", "position": 400, "duration": 150},
                             headers={"X-CSRF": self.csrf()})
        self.assertEqual(r.status_code, 400)

    def test_rentals_cannot_be_downloaded(self):
        self.login()
        r = self.client.post("/api/download/lagos-after-midnight", headers={"X-CSRF": self.csrf()})
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/download/amas-gold", headers={"X-CSRF": self.csrf()})
        self.assertTrue(r.get_json()["ok"])

    def test_review_upsert(self):
        self.login()
        self.post("/movie/amas-gold/review", {"stars": "4", "body": "Lovely"})
        self.post("/movie/amas-gold/review", {"stars": "5", "body": "Even better the second time"})
        with self.app.app_context():
            rows = get_db().execute("SELECT stars FROM reviews r JOIN users u ON u.id=r.user_id WHERE u.email='demo@mboni.rw' AND r.movie_id=(SELECT id FROM movies WHERE slug='amas-gold')").fetchall()
        self.assertEqual([r["stars"] for r in rows], [5])

    def test_data_saver_picks_240p(self):
        self.login()
        self.post("/settings", {"lang": "en", "data_saver": "on", "phone": ""})
        self.assertIn(b'data-quality="240p"', self.client.get("/watch/amas-gold").data)


class Admin(MboniTestCase):
    def setUp(self):
        super().setUp()
        self.login("admin@mboni.rw", "admin123")

    def test_dashboard_and_lists(self):
        for url in ["/admin/", "/admin/movies", "/admin/users", "/admin/transactions", "/admin/movies/new"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_csv_export(self):
        r = self.client.get("/admin/transactions.csv?status=paid")
        self.assertEqual(r.mimetype, "text/csv")
        lines = r.data.decode().strip().splitlines()
        self.assertTrue(lines[0].startswith("ref,date"))
        self.assertTrue(all(line.endswith(",paid") for line in lines[1:]))

    def test_add_edit_delete_movie(self):
        data = {"title": "Rubavu Nights", "tagline": "Lake Kivu after dark", "year": "2026", "country": "Rwanda",
                "language": "Kinyarwanda", "genres": "Drama", "runtime": "95", "age": "13+", "synopsis": "A story.",
                "director": "A. Director", "cast_list": "Someone", "c1": "#112233", "c2": "#000000", "c3": "#ffffff",
                "pattern": "waves", "access": "sub", "rent_price": "1000", "buy_price": "4000", "award": ""}
        self.assertEqual(self.post("/admin/movies/new", data).status_code, 302)
        self.assertEqual(self.client.get("/movie/rubavu-nights").status_code, 200)
        with self.app.app_context():
            mid = get_db().execute("SELECT id FROM movies WHERE slug='rubavu-nights'").fetchone()["id"]
        data["title"] = "Rubavu Nights (Director's Cut)"
        self.post(f"/admin/movies/{mid}/edit", data)
        self.assertIn(b"Director&#39;s Cut", self.client.get("/movie/rubavu-nights").data)
        self.post(f"/admin/movies/{mid}/delete")
        self.assertEqual(self.client.get("/movie/rubavu-nights").status_code, 404)

    def test_movie_form_validation(self):
        r = self.post("/admin/movies/new", {"title": "", "year": "abc", "c1": "red", "pattern": "x", "access": "y"})
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"Title is required", r.data)


class Cart(MboniTestCase):
    """The e-commerce flow: cart -> checkout -> payment -> order status -> delivery."""

    def cart_rows(self, email="demo@mboni.rw"):
        with self.app.app_context():
            return {r["slug"]: (r["kind"], r["qty"]) for r in get_db().execute(
                """SELECT m.slug, c.kind, c.qty FROM cart_items c JOIN movies m ON m.id=c.movie_id
                   JOIN users u ON u.id=c.user_id WHERE u.email=?""", (email,))}

    def checkout(self, **extra):
        data = {"contact_name": "Isaac Ishimwe", "email": "demo@mboni.rw", "contact_phone": "0788123456",
                "method": "mtn", "phone": "0788123456"}
        data.update(extra)
        return self.post("/cart/checkout", data)

    def order(self, ref=None):
        with self.app.app_context():
            db = get_db()
            row = (db.execute("SELECT * FROM orders WHERE ref=?", (ref,)) if ref else
                   db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 1")).fetchone()
            return dict(row)

    def test_add_change_quantity_and_remove(self):
        self.login()
        self.post("/cart/add", {"movie": "amas-gold", "kind": "rent"})
        self.post("/cart/add", {"movie": "matatu-kings", "kind": "buy"})
        self.assertEqual(self.cart_rows(), {"amas-gold": ("rent", 1), "matatu-kings": ("buy", 1)})
        self.post("/cart/add", {"movie": "amas-gold", "kind": "rent"})          # same film again: one more copy
        self.post("/cart/update", {"movie": "matatu-kings", "qty": "3"})
        self.post("/cart/update", {"movie": "amas-gold", "kind": "buy"})        # switch rent -> buy
        self.assertEqual(self.cart_rows(), {"amas-gold": ("buy", 2), "matatu-kings": ("buy", 3)})
        self.post("/cart/update", {"movie": "matatu-kings", "qty": "99"})       # capped at 10
        self.assertEqual(self.cart_rows()["matatu-kings"], ("buy", 10))
        self.post("/cart/remove", {"movie": "matatu-kings"})
        self.post("/cart/update", {"movie": "amas-gold", "qty": "0"})           # 0 removes
        self.assertEqual(self.cart_rows(), {})

    def test_cart_totals_update(self):
        self.login()
        self.post("/cart/add", {"movie": "amas-gold", "kind": "buy", "qty": "2"})
        self.post("/cart/add", {"movie": "matatu-kings", "kind": "rent"})
        r = self.client.post("/cart/update", data={"movie": "matatu-kings", "qty": "2", "csrf": self.csrf()},
                             headers={"X-Requested-With": "fetch"})
        data = r.get_json()
        self.assertEqual(data["count"], 4)
        with self.app.app_context():
            db = get_db()
            buy = db.execute("SELECT buy_price FROM movies WHERE slug='amas-gold'").fetchone()[0]
            rent = db.execute("SELECT rent_price FROM movies WHERE slug='matatu-kings'").fetchone()[0]
        self.assertIn(f"{2 * buy + 2 * rent:,} RWF", data["html"])

    def test_free_and_coming_soon_films_cannot_be_added(self):
        self.login()
        self.post("/cart/add", {"movie": "nyungwe", "kind": "buy"})
        self.post("/cart/add", {"movie": "douala-express", "kind": "buy"})
        self.assertEqual(self.cart_rows(), {})
        self.assertIn(b"Coming soon", self.client.get("/movie/douala-express").data)
        self.assertEqual(self.client.get("/checkout?kind=rent&movie=douala-express").status_code, 404)

    def test_guest_cart_moves_into_account_on_login(self):
        self.post("/cart/add", {"movie": "amas-gold", "kind": "buy"})
        self.assertIn(b"Ama", self.client.get("/cart").data)
        self.assertEqual(self.client.get("/cart/checkout").status_code, 302)  # must sign in to pay
        self.login()
        self.assertEqual(self.cart_rows(), {"amas-gold": ("buy", 1)})

    def test_checkout_validates_contact_and_payment(self):
        self.login()
        self.post("/cart/add", {"movie": "amas-gold", "kind": "buy"})
        r = self.checkout(contact_name="", email="nope", contact_phone="123", phone="0721234567")
        self.assertEqual(r.status_code, 400)
        for msg in (b"At least 2 letters", b"you@example.com", b"0788123456 for the SMS", b"start with 078 or 079"):
            self.assertIn(msg, r.data)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM orders WHERE user_id=2").fetchone()[0], 2)  # seeded only

    def test_full_order_pending_paid_delivered_with_gift_codes(self):
        self.login()
        self.post("/cart/add", {"movie": "amas-gold", "kind": "buy", "qty": "3"})
        self.post("/cart/add", {"movie": "matatu-kings", "kind": "rent"})
        r = self.checkout(promo="STUDENT50", gift_note="Enjoy!")
        self.assertEqual(r.status_code, 302)
        order = self.order()
        self.assertEqual(order["status"], "pending")
        with self.app.app_context():
            db = get_db()
            prices = db.execute("SELECT buy_price, rent_price FROM movies WHERE slug IN ('amas-gold', 'matatu-kings') ORDER BY slug").fetchall()
        subtotal = 3 * prices[0]["buy_price"] + prices[1]["rent_price"]
        self.assertEqual((order["subtotal"], order["total"]), (subtotal, subtotal - subtotal // 2))
        ref = r.location.rsplit("/", 1)[-1]
        r = self.post(f"/pay/{ref}/confirm", {"action": "approve"})
        r = self.client.get(r.location)
        self.assertEqual(r.status_code, 302)  # receipt sends order payments to the order page
        order = self.order(order["ref"])
        self.assertEqual(order["status"], "delivered")
        with self.app.app_context():
            db = get_db()
            self.assertEqual([e["status"] for e in db.execute("SELECT status FROM order_events WHERE order_id=? ORDER BY id", (order["id"],))],
                             ["pending", "paid", "delivered"])
            codes = db.execute("SELECT code FROM gift_codes WHERE order_id=?", (order["id"],)).fetchall()
            # 3 copies of Ama's Gold: 1 for me + 2 gifts. Matatu Kings is already in the demo user's plan,
            # so renting it for themselves would be pointless: that copy becomes a gift code too.
            self.assertEqual(len(codes), 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM purchases WHERE order_id=?", (order["id"],)).fetchone()[0], 1)
        self.assertEqual(self.cart_rows(), {})  # paid items leave the cart
        page = self.client.get(f"/orders/{order['ref']}").data
        self.assertIn(codes[0]["code"].encode(), page)
        self.assertEqual(self.client.get("/watch/amas-gold").status_code, 200)

        # A friend redeems one gift code.
        self.client.post("/logout", data={"csrf": self.csrf()})
        self.register("friend@example.rw")
        r = self.post("/redeem", {"code": codes[0]["code"]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/watch/amas-gold").status_code, 200)
        r = self.post("/redeem", {"code": codes[0]["code"]})
        self.assertIn(b"already been used", r.data)

    def test_failed_payment_keeps_order_pending_and_can_be_retried(self):
        self.login()
        self.post("/cart/add", {"movie": "amas-gold", "kind": "rent"})
        r = self.checkout(phone="0788120000")  # numbers ending 0000 are declined
        ref = r.location.rsplit("/", 1)[-1]
        self.post(f"/pay/{ref}/confirm", {"action": "approve"})
        order = self.order()
        self.assertEqual(order["status"], "pending")
        self.assertEqual(self.cart_rows(), {"amas-gold": ("rent", 1)})  # cart kept, nothing charged
        r = self.post(f"/orders/{order['ref']}/pay", {"method": "card", "card": "4242424242424242", "expiry": "12/30", "cvc": "123"})
        ref = r.location.rsplit("/", 1)[-1]
        self.post(f"/pay/{ref}/confirm", {"action": "approve"})
        self.assertEqual(self.order(order["ref"])["status"], "delivered")

    def test_customer_can_cancel_pending_order_only(self):
        self.login()
        self.post("/cart/add", {"movie": "amas-gold", "kind": "rent"})
        self.checkout()
        order = self.order()
        self.post(f"/orders/{order['ref']}/cancel")
        self.assertEqual(self.order(order["ref"])["status"], "cancelled")
        self.post(f"/orders/{order['ref']}/cancel")
        self.assertEqual(self.order(order["ref"])["status"], "cancelled")

    def test_orders_are_private(self):
        self.login()
        self.post("/cart/add", {"movie": "amas-gold", "kind": "rent"})
        self.checkout()
        ref = self.order()["ref"]
        self.client.post("/logout", data={"csrf": self.csrf()})
        self.register("other@example.rw")
        self.assertEqual(self.client.get(f"/orders/{ref}").status_code, 404)
        self.assertEqual(self.client.get("/admin/orders").status_code, 403)

    def test_admin_delivers_and_refunds(self):
        with self.app.app_context():
            paid = get_db().execute("SELECT ref FROM orders WHERE status='paid' LIMIT 1").fetchone()["ref"]
        self.login("admin@mboni.rw", "admin123", profile=False)
        self.assertIn(paid.encode(), self.client.get("/admin/orders?status=paid").data)
        self.assertEqual(self.client.get(f"/admin/orders/{paid}").status_code, 200)
        self.post(f"/admin/orders/{paid}", {"status": "cancelled"})          # not allowed from paid
        self.assertEqual(self.order(paid)["status"], "paid")
        self.post(f"/admin/orders/{paid}", {"status": "delivered", "note": "Licence confirmed"})
        order = self.order(paid)
        self.assertEqual(order["status"], "delivered")
        with self.app.app_context():
            db = get_db()
            self.assertGreater(db.execute("SELECT COUNT(*) FROM purchases WHERE order_id=?", (order["id"],)).fetchone()[0], 0)
        self.post(f"/admin/orders/{paid}", {"status": "refunded"})
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM purchases WHERE order_id=?", (order["id"],)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM gift_codes WHERE order_id=? AND void=0", (order["id"],)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT status FROM transactions WHERE order_id=?", (order["id"],)).fetchone()[0], "refunded")
        self.assertEqual(self.order(paid)["status"], "refunded")


class HelpAndContact(MboniTestCase):
    def test_contact_form_validates_and_reaches_admin_inbox(self):
        r = self.post("/help", {"name": "", "email": "x", "topic": "Hacking", "body": "hi"})
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"between 10 and 2,000", r.data)
        r = self.post("/help", {"name": "Keza", "email": "keza@example.rw", "topic": "Watching a film",
                                "body": "Subtitles don't show on my TV."})
        self.assertEqual(r.status_code, 302)
        self.login("admin@mboni.rw", "admin123", profile=False)
        page = self.client.get("/admin/messages").data
        self.assertIn(b"Subtitles don&#39;t show on my TV.", page)
        with self.app.app_context():
            mid = get_db().execute("SELECT id FROM messages WHERE email='keza@example.rw'").fetchone()["id"]
        self.post(f"/admin/messages/{mid}", {"status": "answered"})
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT status FROM messages WHERE id=?", (mid,)).fetchone()[0], "answered")

    def test_footer_has_contact_details(self):
        page = self.client.get("/").data
        self.assertIn(b"hello@mboni.rw", page)
        self.assertIn(b"Kigali", page)


class OnlineConsumer(MboniTestCase):
    """Clickstream tracking, the five-stage funnel, audience segments and trust signals."""

    def events(self, kind):
        with self.app.app_context():
            return get_db().execute("SELECT * FROM events WHERE type=? AND visitor NOT LIKE 'seed%' ORDER BY id", (kind,)).fetchall()

    def test_clickstream_follows_the_buying_stages(self):
        self.client.get("/", headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13) Mobile"})
        self.client.get("/search?q=Kigali")
        self.client.get("/movie/amas-gold")
        self.login()
        self.client.get("/watch/amas-gold?trailer=1")
        self.post("/cart/add", {"movie": "queen-of-dahomey", "kind": "rent"})
        self.client.get("/cart/checkout")
        r = self.post("/cart/checkout", {"contact_name": "Isaac", "email": "demo@mboni.rw", "contact_phone": "0788123456",
                                         "method": "mtn", "phone": "0788123456"})
        self.post(f"/pay/{r.location.rsplit('/', 1)[-1]}/confirm", {"action": "approve"})
        self.client.get("/watch/queen-of-dahomey")
        self.assertEqual(self.events("visit")[0]["device"], "mobile")
        self.assertEqual(self.events("search")[0]["detail"], "kigali")
        for kind in ["view_film", "trailer", "add_to_cart", "checkout", "purchase", "watch"]:
            self.assertTrue(self.events(kind), kind)
        # the same visitor id follows the guest into their account
        with self.app.app_context():
            visitors = {r[0] for r in get_db().execute("SELECT DISTINCT visitor FROM events WHERE visitor NOT LIKE 'seed%'")}
        self.assertEqual(len(visitors), 1)

    def test_admin_activity_is_not_tracked(self):
        self.login("admin@mboni.rw", "admin123", profile=False)
        self.client.get("/movie/amas-gold")
        self.assertEqual(self.events("view_film"), [])

    def test_customers_page_shows_funnel_and_segments(self):
        self.login("admin@mboni.rw", "admin123", profile=False)
        r = self.client.get("/admin/customers?days=90")
        self.assertEqual(r.status_code, 200)
        for text in [b"Awareness of need", b"Search for information", b"Evaluation of alternatives", b"Purchase decision",
                     b"Post-purchase contact", b"reference group", b"opinion leader", b"small-ticket", b"verified viewers", b"Clickstream"]:
            self.assertIn(text, r.data)
        with self.app.app_context():
            from app.insights import report
            funnel = report(90)["funnel"]
        counts = [s["n"] for s in funnel]
        self.assertEqual(counts, sorted(counts, reverse=True))  # each stage keeps fewer people than the last

    def test_customers_page_is_admin_only(self):
        self.login()
        self.assertEqual(self.client.get("/admin/customers").status_code, 403)

    def test_register_with_optional_about_you(self):
        self.post("/register", {"name": "Keza Uwase", "email": "keza@example.rw", "password": "goodpass1",
                                "age_range": "18–24", "gender": "Female", "community": "Rural area", "heard_from": "whatsapp"})
        self.post("/register", {"name": "Eric M", "email": "eric@example.rw", "password": "goodpass1", "age_range": "<script>"})
        with self.app.app_context():
            db = get_db()
            keza = db.execute("SELECT * FROM users WHERE email='keza@example.rw'").fetchone()
            eric = db.execute("SELECT * FROM users WHERE email='eric@example.rw'").fetchone()
        self.assertEqual((keza["age_range"], keza["community"], keza["heard_from"]), ("18–24", "Rural area", "whatsapp"))
        self.assertIsNone(eric["age_range"])  # unknown values are dropped, the questions are optional

    def test_trust_signals_on_film_page(self):
        r = self.client.get("/movie/inzira-yamahoro")
        self.assertIn(b"Kigali Film Critics", r.data)        # opinion leader
        self.assertIn(b"Refund if it won", r.data)            # trust promise
        self.assertIn(b"people looked at this film this week", r.data)  # social proof


if __name__ == "__main__":
    unittest.main()

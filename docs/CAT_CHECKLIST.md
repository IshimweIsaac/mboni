# E-commerce CAT: where each requirement is

The brief says services such as streaming should adapt the features: the **catalogue is the list of films** and the **cart is the selection of films to rent or buy**. This is how Mboni covers every module.

| # | Module | Where to show it in the demo | Code |
|---|---|---|---|
| 1 | **Home page & branding** | `/`: Mboni name and star logo, menu, featured films in the hero, footer with address, phone, email and opening hours | `templates/landing.html`, `templates/base.html` |
| 2 | **Catalogue** | `/search`: categories (genre, country, language), filters and sort. Each film has a name, a real photo, a description, a price (rent and buy, in RWF) and availability ("Available now" or "Coming soon", e.g. *Douala Express*) | `main.py` (search, detail), `templates/detail.html` |
| 3 | **Shopping cart** | "Add to cart" on any film page → `/cart`: switch Rent/Buy, change quantity with − / +, remove, save for later, empty cart. Subtotal and total update without reloading. Extra copies become gift codes. Guests can fill a cart too; it is kept when they sign in | `shop.py` (cart routes), `templates/shop/_cart_body.html`, `static/js/app.js` (Cart) |
| 4 | **User accounts** | Register, sign in, sign out. Two roles: **viewer** (customer) and **admin**. Demo: `demo@mboni.rw / demo1234`, `admin@mboni.rw / admin123` | `auth.py` |
| 5 | **Checkout & orders** | `/cart/checkout`: contact and delivery details (name, email, phone, gift message), order summary. The order is saved in the `orders` and `order_items` tables. Statuses: **pending → paid → delivered**, plus cancelled and refunded. Customers see them under *My orders* with a timeline | `shop.py` (checkout, orders), `templates/shop/order.html` |
| 6 | **Payment** | Simulated MTN MoMo, Airtel Money and card. USSD approval screen, then a confirmation page with confetti. A declined payment (number ending 0000, or card 4000 0000 0000 0002) keeps the order pending so the customer can pay again. No real money | `billing.py` |
| 7 | **Admin dashboard** | `/admin`: KPIs and charts. *Films*: add, edit, delete (with "coming soon"). *Orders*: filter by status, search, open an order, **change its status** (deliver, cancel, refund) with a note. *Messages*, *Members*, *Payments* (CSV export) | `admin.py`, `templates/admin/` |
| 8 | **Customer interaction** | All four: **contact form** at `/help` (saved, answered from *Admin → Messages*), **reviews** with stars on every film, **FAQ** on `/help` and the home page, phone and email links in the footer | `shop.py` (contact), `main.py` (reviews) |
| 9 | **Design & usability** | Works on phones (bottom tab bar, stacked cart lines) and computers. Light/dark, high contrast, three languages | `static/css/app.css`, `docs/HCI_DESIGN.md` |
| 10 | **Basic security** | Passwords hashed (`werkzeug` scrypt), CSRF token on every form, server-side validation on every form, admin pages return 403 to customers, customers can only see their own orders (404 otherwise), only the last 4 card digits are stored | `auth.py`, `app/__init__.py`, tests |

## Suggested 15-minute demo order

1. Home page as a guest: branding, featured films, footer contact details (1 min)
2. Catalogue: filter by genre and country, open a film, point out price and availability (2 min)
3. Add two films to the cart as a guest, change rent/buy and quantity, then sign in: the cart is kept (2 min)
4. Checkout with promo `STUDENT50`, pay with MoMo, show the order timeline and gift codes (3 min)
5. Show a declined payment (number ending 0000) and paying again from *My orders* (1 min)
6. Redeem a gift code from another account (1 min)
7. Admin: dashboard, add a film, deliver a *paid* order, refund one, answer a message (4 min)
8. Phone view and the security points (1 min)

## Deliverables checklist

- [x] Working system: `python3 run.py`, then http://localhost:5070
- [x] Database export: `database/mboni.sql` (regenerate with `python3 -m flask --app run export-db`)
- [x] Source code + database in one zip: `./make_submission.sh <group-number>`
- [x] Report: `docs/report/Mboni_CAT_Report.docx` and `.pdf` (fill in the group number and lecturer on the cover)
- [ ] Demo rehearsal: every member should be able to explain any part

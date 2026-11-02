# Mboni: African cinema, streaming

Mboni (Swahili for "the pupil of the eye", and "the apple of my eye") is a streaming platform for African films. Viewers can **subscribe**, **rent for 48 hours**, or **buy and keep** a film, and pay with **MTN MoMo, Airtel Money or card**. It works on phones first, saves data, and can be installed as an app.

## Run it

```bash
cd ~/Documents/nyota
pip install -r requirements.txt     # just Flask
python3 run.py                      # http://localhost:5070
```

The database (`instance/mboni.db`) is created and seeded on first run. To start fresh: `python3 -m flask --app run init-db --reset`.

| Account | Email | Password |
|---|---|---|
| Viewer (Standard plan, one live rental) | demo@mboni.rw | demo1234 |
| Admin | admin@mboni.rw | admin123 |

The sign-in page has one-click buttons for both.

**Payment test values** (no real money moves):

| What | Value | Result |
|---|---|---|
| MTN number | 078xxxxxxx / 079xxxxxxx | approved |
| Airtel number | 072xxxxxxx / 073xxxxxxx | approved |
| Any number ending in `0000` | e.g. 0788120000 | declined |
| Card | 4242 4242 4242 4242, any future date, any CVC | approved |
| Card | 4000 0000 0000 0002 | declined |
| Promo codes | `STUDENT50`, `KWIBOHORA`, `MBONI10` | 50% / 30% / 10% off |

## Team workflow

The code lives on GitHub. Anyone with access can open it in VS Code in the browser (nothing to install):
`https://vscode.dev/github/<owner>/<repo>`, or press `.` on the GitHub page.

Every push to `main` runs the 53+ automated tests on GitHub Actions; if they pass, the site is deployed to Railway
automatically (`.github/workflows/deploy.yml`). Railway runs `gunicorn run:app` (see `Procfile` / `railway.json`) and
seeds a fresh demo database on start.

## Tests

```bash
python3 -m unittest -v      # 59 tests
```

They cover the cart (add, quantity, rent/buy switch, remove, guest cart kept at sign-in), checkout validation, the order life cycle (pending, paid, delivered, cancelled, refunded) and gift codes, the contact form, sign-up validation, CSRF, open-redirect protection, access rules (subscription, rental, purchase, premiere, free, kids), every payment path including declines and cancellations, card numbers never being stored, progress saving, downloads, reviews, and the admin CRUD and CSV export.

## E-commerce CAT

See **[docs/CAT_CHECKLIST.md](docs/CAT_CHECKLIST.md)** for where each of the 10 required modules is, a 15-minute demo script, and the deliverables.

- Database export: `database/mboni.sql` (`python3 -m flask --app run export-db`)
- Submission zip: `./make_submission.sh <group-number>`

## Features

**Cart & orders**
- Add films to a cart from any film page or poster; choose Rent (48h) or Buy for each, change copies with − / +, remove, save for later; totals update without reloading
- Guests can shop too; the cart moves into the account at sign-in
- Extra copies become gift codes (`MBONI-XXXX-XXXX`) that friends redeem at `/redeem`
- Checkout with contact and delivery details and an optional gift message; one payment for the whole cart
- Orders saved with status **pending → paid → delivered** (or cancelled / refunded), shown as a timeline under *My orders*; failed payments keep the order so it can be paid again
- Admin *Orders*: filter, search, deliver, cancel, refund (takes films back and voids gift codes), add notes
- Help centre with FAQ and a contact form; messages land in *Admin → Messages*
- Films can be marked *Coming soon* (not yet for rent or sale)


**Watching**
- Home with an auto-rotating hero (swipe on phones), Continue watching, Top 10 in Rwanda, Fresh premieres, "Because you watched…", Made in Rwanda, Award winners, Kids, Music, After dark
- "What's the vibe tonight?" mood picker and a Surprise me button
- Explore by country (15 countries)
- Instant search overlay (press `/`) with **voice search**, plus a full search page with country, genre, language, access and sort filters
- Film page: synopsis, cast, awards, rating breakdown, reviews, similar films, **data estimate for the film's runtime**, share button
- Custom player: resume where you left off, 240p data saver / 480p quality switch with MB/hour shown, subtitles in **English, Kinyarwanda and French**, speed, picture in picture, skip intro, up-next countdown, keyboard shortcuts, double-tap to skip on phones
- Trailers for every film (first 30 seconds) with a rent/watch call to action
- My List, Library (rentals with live countdown, owned films, downloads, history, minutes watched)
- **Offline downloads**: the film is stored with the Cache API and the service worker serves it, including seeking, with no internet

**Paying**
- Three plans (Mobile 3,000 / Standard 6,000 / Premium 9,000 RWF), each shown with its daily cost and USD
- Rent (48 hours) or buy any film; new premieres are pay-per-view with 20% off for subscribers
- Checkout with MoMo / Airtel phone validation (correct prefixes per network), card Luhn check, expiry and CVC checks, live promo code
- Simulated USSD approval screen, auto-approves after 6 seconds
- Receipt page with confetti, printable; full payment history in Settings
- Cancel subscription (keeps access until the paid period ends), resume auto-renew, switch plans

**Accounts**
- Register with live password strength meter, sign in, sign out
- Profiles (limit depends on the plan) including **Kids profiles** that only show family films
- Settings: data saver, language, mobile money number, dark/light theme, high contrast, reduce motion, install app

**Admin**
- Dashboard: revenue, active subscribers, live rentals, **money owed to filmmakers (60%)**, failed payments, 30-day revenue chart, revenue mix donut, payment methods, plays by country, most watched
- Add / edit / delete films with a live generated poster preview
- Members list with plan and total spent
- Payments with filters and CSV export

**Platform**
- Installable PWA (manifest, icons, offline page, service worker)
- CSRF protection on every form and API call, hashed passwords, no open redirects, only masked card numbers stored
- Covers are real photographs from Wikimedia Commons under free licences (CC BY, CC BY-SA, CC0), credited on each film page and at `/credits`. Films added later without a photo get a generated poster from traditional patterns (kente, imigongo, mudcloth, adinkra)

## Project layout

```
app/
  __init__.py   app factory, CSRF, template helpers
  db.py         schema + seed data (24 films, 15 countries, 33 users, a month of payments)
  catalog.py    access rules: who can watch what, and why
  auth.py       register / login / roles
  main.py       browse, film, player, search, list, library, profiles, settings
  billing.py    plans, checkout, mobile money / card simulation, receipts
  shop.py       cart, cart checkout, orders and statuses, gift codes, help/contact form
  admin.py      dashboard, films CRUD, orders, messages, members, payments, CSV
  i18n.py       English / Kinyarwanda / French strings
  templates/    Jinja pages
  static/       css, js (app, player, service worker), subtitles, icons, video
tests/          unittest suite
database/       SQL export of the database (for submission)
docs/           HCI design justification
```

Cover photos: see `app/static/covers/credits.json` or the `/credits` page. The demo clip is from *Sintel* © Blender Foundation, licensed CC BY 3.0. All film titles, people and reviews in the catalogue are fictional.

import random
import sqlite3
from datetime import datetime, timedelta

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('viewer', 'admin')),
    lang TEXT NOT NULL DEFAULT 'en',
    data_saver INTEGER NOT NULL DEFAULT 0,
    age_range TEXT,
    gender TEXT,
    community TEXT,
    heard_from TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT NOT NULL,
    is_kids INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS plans (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price INTEGER NOT NULL,
    quality TEXT NOT NULL,
    screens INTEGER NOT NULL,
    downloads INTEGER NOT NULL,
    profiles INTEGER NOT NULL,
    blurb TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_code TEXT NOT NULL REFERENCES plans(code),
    started_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    auto_renew INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    tagline TEXT NOT NULL DEFAULT '',
    year INTEGER NOT NULL,
    country TEXT NOT NULL,
    language TEXT NOT NULL,
    genres TEXT NOT NULL,
    runtime INTEGER NOT NULL,
    age TEXT NOT NULL DEFAULT '13+',
    synopsis TEXT NOT NULL,
    director TEXT NOT NULL,
    cast_list TEXT NOT NULL,
    c1 TEXT NOT NULL, c2 TEXT NOT NULL, c3 TEXT NOT NULL,
    pattern TEXT NOT NULL DEFAULT 'kente',
    access TEXT NOT NULL DEFAULT 'sub' CHECK (access IN ('sub', 'premiere', 'free')),
    rent_price INTEGER NOT NULL DEFAULT 1000,
    buy_price INTEGER NOT NULL DEFAULT 5000,
    is_kids INTEGER NOT NULL DEFAULT 0,
    featured INTEGER NOT NULL DEFAULT 0,
    award TEXT,
    views INTEGER NOT NULL DEFAULT 0,
    available INTEGER NOT NULL DEFAULT 1,
    critic_quote TEXT,
    critic_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('rent', 'buy')),
    price INTEGER NOT NULL,
    expires_at TEXT,
    order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('subscription', 'rent', 'buy', 'order')),
    movie_id INTEGER REFERENCES movies(id) ON DELETE SET NULL,
    plan_code TEXT,
    order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    amount INTEGER NOT NULL,
    discount INTEGER NOT NULL DEFAULT 0,
    promo_code TEXT,
    method TEXT NOT NULL CHECK (method IN ('mtn', 'airtel', 'card')),
    account TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'failed', 'refunded')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watchlist (
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (profile_id, movie_id)
);
CREATE TABLE IF NOT EXISTS progress (
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    position REAL NOT NULL,
    duration REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, movie_id)
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    stars INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (user_id, movie_id)
);
CREATE TABLE IF NOT EXISTS downloads (
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    quality TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, movie_id)
);
CREATE TABLE IF NOT EXISTS promo_codes (
    code TEXT PRIMARY KEY,
    percent INTEGER NOT NULL CHECK (percent BETWEEN 1 AND 100),
    label TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS cart_items (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('rent', 'buy')),
    qty INTEGER NOT NULL DEFAULT 1 CHECK (qty BETWEEN 1 AND 10),
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, movie_id)
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contact_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    gift_note TEXT NOT NULL DEFAULT '',
    subtotal INTEGER NOT NULL,
    discount INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL,
    promo_code TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'delivered', 'cancelled', 'refunded')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    movie_id INTEGER REFERENCES movies(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('rent', 'buy')),
    qty INTEGER NOT NULL CHECK (qty >= 1),
    unit_price INTEGER NOT NULL,
    line_total INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gift_codes (
    code TEXT PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('rent', 'buy')),
    redeemed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    redeemed_at TEXT,
    void INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visitor TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    movie_id INTEGER REFERENCES movies(id) ON DELETE SET NULL,
    detail TEXT,
    device TEXT NOT NULL DEFAULT 'desktop',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_type_time ON events (type, created_at);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    topic TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'answered')),
    created_at TEXT NOT NULL
);
"""

TABLES = ["events", "messages", "gift_codes", "order_events", "order_items", "cart_items", "downloads", "reviews", "progress",
          "watchlist", "transactions", "purchases", "orders", "movies", "subscriptions", "plans", "profiles", "users",
          "promo_codes"]

PLANS = [
    ("mobile", "Mobile", 3000, "480p", 1, 2, 1, "One phone, low data, all the stories."),
    ("standard", "Standard", 6000, "1080p", 2, 10, 3, "Full HD on any screen for you and family."),
    ("premium", "Premium", 9000, "4K + 5.1 audio", 4, 30, 5, "The best picture, four screens, early premieres."),
]

PROMOS = [
    ("KWIBOHORA", 30, "Liberation Day special"),
    ("STUDENT50", 50, "Students: half price"),
    ("MBONI10", 10, "Welcome discount"),
]

# slug, title, tagline, year, country, language, genres, runtime, age, director, cast,
# colours, pattern, access, rent, buy, kids, featured, award, synopsis
MOVIES = [
    ("inzira-yamahoro", "Inzira y'Amahoro", "Some roads are walked home.", 2025, "Rwanda", "Kinyarwanda",
     "Drama,Family", 112, "13+", "Aline Uwase", "Eric Ntwari, Grace Mukamana, Jean Bosco Habimana",
     "#d97706", "#7c2d12", "#fde68a", "imigongo", "sub", 1000, 5000, 0, 1, "Best Film, Mashariki Festival",
     "Twenty years after leaving her hillside village, Keza returns to Musanze to bury her father and finds a letter that rewrites everything she believed about her family. A tender story of forgiveness told across three generations."),
    ("lagos-after-midnight", "Lagos After Midnight", "The city never sleeps. Neither does Tunde.", 2026, "Nigeria", "English, Pidgin",
     "Thriller,Crime", 124, "16+", "Kunle Adebayo", "Tobi Bakare, Ada Okafor, Femi Lawal",
     "#16a34a", "#052e16", "#bef264", "rays", "premiere", 2500, 7000, 0, 1, None,
     "A danfo driver picks up a passenger carrying a briefcase that half of Lagos is looking for. One long night across Third Mainland Bridge, Ikoyi rooftops and Makoko waters."),
    ("amas-gold", "Ama's Gold", "What the river gives, the river remembers.", 2024, "Ghana", "Twi, English",
     "Drama", 104, "13+", "Efua Mensah", "Akosua Boateng, Kwame Asante, Yaw Darko",
     "#eab308", "#713f12", "#fef08a", "kente", "sub", 1000, 4500, 0, 0, "Audience Award, Accra Film Week",
     "When a small-scale miner strikes gold on her grandmother's land, Ama must choose between the fortune that could save her family and the river that has fed her village for centuries."),
    ("matatu-kings", "Matatu Kings", "Fast routes. Loud music. Bigger dreams.", 2025, "Kenya", "Swahili, Sheng",
     "Comedy", 96, "13+", "Wanjiru Kamau", "Brian Otieno, Mercy Wairimu, Kevo Mwangi",
     "#ec4899", "#4c0519", "#fbcfe8", "waves", "sub", 1000, 4000, 0, 0, None,
     "Two rival matatu crews on the Nairobi to Rongai route are forced to share one bus for a week. Graffiti, bass speakers and a wedding nobody planned."),
    ("soweto-skies", "Soweto Skies", "Her voice was the only thing they could not ban.", 2023, "South Africa", "isiZulu, English",
     "Drama,Music", 118, "13+", "Thandiwe Nkosi", "Lerato Dube, Sipho Zulu, Naledi Khumalo",
     "#3b82f6", "#172554", "#bfdbfe", "rays", "sub", 1200, 5000, 0, 1, "Best Score, Durban Film Festival",
     "In 1976 a choir girl in Orlando West writes the song that will carry a generation. A musical drama about courage, harmony and the sky above Soweto."),
    ("griot-de-dakar", "Le Griot de Dakar", "Every family has a song. His holds a secret.", 2024, "Senegal", "Wolof, French",
     "Drama,Music", 101, "13+", "Mamadou Diallo", "Ousmane Ndiaye, Aïssatou Fall, Ibrahima Sarr",
     "#f97316", "#431407", "#fed7aa", "mudcloth", "sub", 1000, 4500, 0, 0, None,
     "An old kora player in the Medina agrees to teach his grandson the family songs, but only if the boy deletes his phone for forty days."),
    ("kilimanjaro-rising", "Kilimanjaro Rising", "5,895 metres. One chance.", 2025, "Tanzania", "Swahili, English",
     "Adventure", 109, "PG", "Neema Mollel", "Baraka Massawe, Zawadi Lyimo, Juma Kisanga",
     "#0ea5e9", "#082f49", "#e0f2fe", "waves", "sub", 1000, 4500, 0, 0, None,
     "A porter who has carried tourists to the summit forty times finally climbs Kilimanjaro for himself, guiding a blind marathon runner to the roof of Africa."),
    ("nyungwe", "Nyungwe", "The forest is listening.", 2024, "Rwanda", "Kinyarwanda, English",
     "Documentary,Nature", 88, "PG", "Patrick Mugisha", "Narrated by Diane Uwimana",
     "#22c55e", "#052e16", "#dcfce7", "adinkra", "free", 0, 3000, 1, 0, "Best Documentary, Rwanda Film Festival",
     "A year inside one of Africa's oldest rainforests: chimpanzees, 300 bird species and the rangers who walk the canopy walkway every dawn. Free for everyone."),
    ("owo-blow", "Owo Blow", "Money talks. In Lagos it shouts.", 2023, "Nigeria", "Yoruba, English",
     "Crime,Comedy", 115, "16+", "Seun Ogunleye", "Damilola Ajayi, Chinedu Eze, Bisi Alade",
     "#a855f7", "#2e1065", "#e9d5ff", "kente", "sub", 1000, 4500, 0, 0, None,
     "Three cousins from Mushin run the most ambitious owambe scam in history, until the bride turns out to be the daughter of the man they owe."),
    ("bujumbura-blues", "Bujumbura Blues", "Love on the shores of Tanganyika.", 2024, "Burundi", "Kirundi, French",
     "Romance,Music", 97, "13+", "Claudine Niyonzima", "Arsène Ndayishimiye, Ornella Iradukunda",
     "#06b6d4", "#083344", "#cffafe", "waves", "sub", 1000, 4000, 0, 0, None,
     "A drummer from Gitega and a jazz singer from Kinshasa share a stage on Lake Tanganyika for one summer season."),
    ("kampala-hustle", "Kampala Hustle", "Seven hills. Seven side hustles.", 2025, "Uganda", "Luganda, English",
     "Comedy", 93, "13+", "Daniel Ssempala", "Martha Nakato, Ivan Kato, Joan Achieng",
     "#facc15", "#422006", "#fef9c3", "mudcloth", "sub", 1000, 4000, 0, 0, None,
     "Boda boda rider by day, wedding MC by night, mobile money agent on weekends: Kato has a plan to make it, and his grandmother has a better one."),
    ("congo-rumba", "Congo Rumba", "The rhythm that crossed a continent.", 2023, "DR Congo", "Lingala, French",
     "Documentary,Music", 92, "PG", "Jean-Pierre Mbuyi", "Featuring the bands of Matonge",
     "#ef4444", "#450a0a", "#fecaca", "rays", "sub", 1000, 4000, 0, 0, "UNESCO Heritage Spotlight",
     "From the bars of 1950s Léopoldville to the streets of Paris, the story of Congolese rumba told by the musicians who still play it every night in Kinshasa."),
    ("lalibela", "Lalibela", "Carved from a single stone. Built by a single faith.", 2024, "Ethiopia", "Amharic",
     "History,Drama", 128, "13+", "Selamawit Tesfaye", "Dawit Alemu, Hanna Girma, Yonas Bekele",
     "#b45309", "#1c1917", "#fcd34d", "adinkra", "sub", 1200, 5000, 0, 0, None,
     "Twelfth-century Ethiopia. A stonecutter's apprentice is chosen to carve the last of the rock churches and must finish before the rains."),
    ("nile-at-dusk", "Nile at Dusk", "Some love stories take a lifetime to arrive.", 2025, "Egypt", "Arabic",
     "Romance,Drama", 106, "13+", "Mona El-Sayed", "Karim Fawzy, Laila Hassan",
     "#f59e0b", "#3f1d0b", "#fde68a", "rays", "sub", 1000, 4500, 0, 0, None,
     "A felucca captain in Aswan and a widowed architect from Cairo meet on the same river, forty years after they first did."),
    ("douala-express", "Douala Express", "One train. Two borders. No brakes.", 2026, "Cameroon", "French, English",
     "Action,Thriller", 111, "16+", "Serge Ekotto", "Blaise Mbarga, Christelle Ngono, Paul Etoundi",
     "#dc2626", "#1f0505", "#fca5a5", "kente", "premiere", 2500, 7000, 0, 0, None,
     "A railway mechanic must stop a runaway cargo train between Douala and Yaoundé while a secret inside one of its containers changes everything."),
    ("anansi-sky-box", "Anansi and the Sky Box", "Every story in the world, in one little box.", 2024, "Ghana", "English",
     "Animation,Family", 82, "All", "Kofi Owusu", "Voices of Abena Owusu, Kojo Ansah",
     "#8b5cf6", "#1e1b4b", "#fde047", "adinkra", "sub", 800, 3500, 1, 0, None,
     "The clever spider Anansi climbs a silk thread to the sky god to win all the world's stories for his village. A vibrant animated folk tale."),
    ("simba-mdogo", "Simba Mdogo", "Small lion. Big roar.", 2025, "Tanzania", "Swahili, English",
     "Animation,Family", 79, "All", "Halima Said", "Voices of Ali Kiba Jr., Rehema Juma",
     "#f97316", "#7c2d12", "#fef3c7", "rays", "sub", 800, 3500, 1, 0, None,
     "The smallest lion cub in the Serengeti sets out to find his roar, with a lazy hippo and a very organised dung beetle as guides."),
    ("imigongo", "Imigongo", "Patterns that tell the way home.", 2025, "Rwanda", "Kinyarwanda",
     "Animation,Family", 74, "All", "Ange Ingabire", "Voices of Kevin Mugabo, Sandrine Uwera",
     "#000000", "#7f1d1d", "#fafafa", "imigongo", "sub", 800, 3500, 1, 1, None,
     "A young girl in Nyakarambi falls into her grandmother's cow-dung painting and must follow its zigzags to get home. Hand-painted animation."),
    ("queen-of-dahomey", "Queen of Dahomey", "History forgot her. Her army did not.", 2026, "Benin", "Fon, French",
     "History,Action", 134, "16+", "Rachidatou Adjovi", "Nadège Hounkpatin, Moïse Agbo",
     "#be123c", "#1c0510", "#fda4af", "kente", "premiere", 3000, 8000, 0, 1, None,
     "The rise of a warrior general in the kingdom of Dahomey, told from inside the ranks of the Agojie."),
    ("kigali-in-bloom", "Kigali in Bloom", "A city of a thousand hills. A love of one.", 2026, "Rwanda", "Kinyarwanda, English",
     "Romance,Comedy", 99, "13+", "Yvette Mutesi", "Christian Mugisha, Divine Ishimwe, Olivier Kamanzi",
     "#f472b6", "#500724", "#fce7f3", "imigongo", "premiere", 2000, 6000, 0, 0, None,
     "A florist in Kimironko and a tech founder in Kacyiru keep getting each other's deliveries during Kigali's busiest wedding season."),
    ("zanzibar-tide", "Zanzibar Tide", "The ocean keeps the island's secrets.", 2024, "Tanzania", "Swahili",
     "Thriller,Mystery", 103, "16+", "Omar Hamad", "Salma Ali, Rashid Mbarouk",
     "#14b8a6", "#042f2e", "#ccfbf1", "waves", "sub", 1000, 4500, 0, 0, None,
     "When a dhow washes up in Stone Town with no crew, a retired detective is pulled back for one last case."),
    ("harmattan", "Harmattan", "When the dust settles, the truth remains.", 2023, "Niger", "Hausa, French",
     "Drama", 95, "13+", "Abdoulaye Issa", "Amina Moussa, Ibrahim Garba",
     "#d6a35c", "#3d2a12", "#fef3c7", "mudcloth", "sub", 1000, 4000, 0, 0, "Golden Stallion nominee",
     "In a Sahel town during the dry season wind, a schoolteacher refuses to close the only girls' school, and the whole town has to choose a side."),
    ("night-bus-nakuru", "Night Bus to Nakuru", "Twelve passengers. Eleven arrive.", 2025, "Kenya", "Swahili, English",
     "Horror,Thriller", 90, "18+", "Otieno Ouma", "Faith Chebet, Kipchoge Rotich",
     "#64748b", "#020617", "#cbd5e1", "rays", "sub", 1000, 4500, 0, 0, None,
     "A late-night bus breaks down on the Rift Valley escarpment and the passengers realise one of them is not who they claim to be."),
    ("ubumwe-fc", "Ubumwe FC", "Eleven kids. One ball. A whole village watching.", 2025, "Rwanda", "Kinyarwanda",
     "Sport,Family", 102, "PG", "Fabrice Nshimiyimana", "Hirwa Cyusa, Ineza Keza, Coach Maniraguha",
     "#2563eb", "#0c1a3d", "#fde047", "kente", "sub", 1000, 4500, 1, 0, "Youth Jury Prize, FESPACO",
     "A team of kids from Rubavu who play with a banana-leaf ball enter the national under-13 cup, and their coach has never seen a match on television."),
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def drop_all(db):
    db.execute("PRAGMA foreign_keys = OFF")
    for table in TABLES:
        db.execute(f"DROP TABLE IF EXISTS {table}")
    db.execute("PRAGMA foreign_keys = ON")


def init_db(seed=True):
    db = get_db()
    cols = {r["name"] for r in db.execute("PRAGMA table_info(users)")}
    if cols and "heard_from" not in cols:
        # A database from before the cart existed: rebuild it (it only ever holds demo data).
        drop_all(db)
    db.executescript(SCHEMA)
    if seed and not db.execute("SELECT 1 FROM movies LIMIT 1").fetchone():
        seed_db(db)
    db.commit()


def seed_db(db):
    rng = random.Random(7)
    db.executemany("INSERT INTO plans VALUES (?,?,?,?,?,?,?,?)", PLANS)
    db.executemany("INSERT INTO promo_codes (code, percent, label) VALUES (?,?,?)", PROMOS)
    for i, m in enumerate(MOVIES):
        (slug, title, tagline, year, country, language, genres, runtime, age, director, cast,
         c1, c2, c3, pattern, access, rent, buy, kids, featured, award, synopsis) = m
        created = (datetime.now() - timedelta(days=len(MOVIES) - i)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """INSERT INTO movies (slug, title, tagline, year, country, language, genres, runtime, age,
               synopsis, director, cast_list, c1, c2, c3, pattern, access, rent_price, buy_price,
               is_kids, featured, award, views, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (slug, title, tagline, year, country, language, genres, runtime, age, synopsis, director,
             cast, c1, c2, c3, pattern, access, rent, buy, kids, featured, award,
             rng.randint(800, 25000), created),
        )
    # One premiere is announced but not out yet, so the catalogue shows "coming soon" availability.
    db.execute("UPDATE movies SET available = 0 WHERE slug = 'douala-express'")

    hashes = {}  # hashing is slow on purpose, so the 30 sample viewers share one hash

    def add_user(name, email, password, role="viewer", phone=None):
        if password not in hashes:
            hashes[password] = generate_password_hash(password)
        cur = db.execute(
            "INSERT INTO users (name, email, phone, password_hash, role) VALUES (?,?,?,?,?)",
            (name, email, phone, hashes[password], role),
        )
        return cur.lastrowid

    colors = ["#f59e0b", "#ef4444", "#22c55e", "#3b82f6", "#a855f7"]
    add_user("Mboni Admin", "admin@mboni.rw", "admin123", "admin")
    db.execute("INSERT INTO profiles (user_id, name, color) VALUES (1, 'Admin', '#f59e0b')")

    demo = add_user("Isaac Ishimwe", "demo@mboni.rw", "demo1234", phone="0788123456")
    db.execute("INSERT INTO profiles (user_id, name, color) VALUES (?, 'Isaac', '#f59e0b')", (demo,))
    db.execute("INSERT INTO profiles (user_id, name, color, is_kids) VALUES (?, 'Kids', '#22c55e', 1)", (demo,))

    # Thirty other viewers with a month of payments so the admin dashboard has a story to tell.
    first = ["Aline", "Eric", "Grace", "Jean", "Divine", "Kevin", "Sandrine", "Olivier", "Ange", "Patrick",
             "Keza", "Hirwa", "Ineza", "Fabrice", "Yvette", "Moses", "Ruth", "David", "Esther", "Samuel"]
    last = ["Uwase", "Mugisha", "Habimana", "Mukamana", "Niyonzima", "Ishimwe", "Kamanzi", "Uwera", "Ndayisaba"]
    movie_rows = db.execute("SELECT id, rent_price, buy_price, access FROM movies").fetchall()
    paid_movies = [m for m in movie_rows if m["access"] != "free"]
    for n in range(30):
        name = f"{rng.choice(first)} {rng.choice(last)}"
        uid = add_user(name, f"viewer{n + 1}@example.rw", "password1", phone=f"078{rng.randint(1000000, 9999999)}")
        db.execute("INSERT INTO profiles (user_id, name, color) VALUES (?,?,?)",
                   (uid, name.split()[0], rng.choice(colors)))
        for _ in range(rng.randint(1, 4)):
            day = datetime.now() - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 23))
            stamp = day.strftime("%Y-%m-%d %H:%M:%S")
            roll = rng.random()
            method = rng.choice(["mtn", "mtn", "mtn", "airtel", "card"])
            account = "**** 4242" if method == "card" else f"078****{rng.randint(100, 999)}"
            ref = f"NY{day.strftime('%y%m%d')}{rng.randint(100000, 999999)}"
            if roll < 0.45:
                plan = rng.choice(PLANS)
                db.execute(
                    "INSERT INTO transactions (ref, user_id, kind, plan_code, amount, method, account, status, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (ref, uid, "subscription", plan[0], plan[2], method, account, "paid", stamp))
                db.execute(
                    "INSERT INTO subscriptions (user_id, plan_code, started_at, expires_at) VALUES (?,?,?,?)",
                    (uid, plan[0], stamp, (day + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")))
            else:
                m = rng.choice(paid_movies)
                kind = "rent" if roll < 0.85 else "buy"
                price = m["rent_price"] if kind == "rent" else m["buy_price"]
                status = "failed" if rng.random() < 0.06 else "paid"
                db.execute(
                    "INSERT INTO transactions (ref, user_id, kind, movie_id, amount, method, account, status, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (ref, uid, kind, m["id"], price, method, account, status, stamp))
                if status == "paid":
                    expires = (day + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S") if kind == "rent" else None
                    db.execute(
                        "INSERT INTO purchases (user_id, movie_id, kind, price, expires_at, created_at) VALUES (?,?,?,?,?,?)",
                        (uid, m["id"], kind, price, expires, stamp))

    # The demo account: Standard plan, one live rental, things in progress and on the list.
    started = datetime.now() - timedelta(days=6)
    db.execute("INSERT INTO subscriptions (user_id, plan_code, started_at, expires_at) VALUES (?,?,?,?)",
               (demo, "standard", started.strftime("%Y-%m-%d %H:%M:%S"),
                (started + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")))
    db.execute("INSERT INTO transactions (ref, user_id, kind, plan_code, amount, method, account, status, created_at)"
               " VALUES (?,?,?,?,?,?,?,?,?)",
               ("NYDEMO000001", demo, "subscription", "standard", 6000, "mtn", "078****456", "paid",
                started.strftime("%Y-%m-%d %H:%M:%S")))
    lagos = db.execute("SELECT id FROM movies WHERE slug='lagos-after-midnight'").fetchone()["id"]
    rented = datetime.now() - timedelta(hours=20)
    db.execute("INSERT INTO purchases (user_id, movie_id, kind, price, expires_at, created_at) VALUES (?,?,?,?,?,?)",
               (demo, lagos, "rent", 2500, (rented + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S"),
                rented.strftime("%Y-%m-%d %H:%M:%S")))
    db.execute("INSERT INTO transactions (ref, user_id, kind, movie_id, amount, method, account, status, created_at)"
               " VALUES (?,?,?,?,?,?,?,?,?)",
               ("NYDEMO000002", demo, "rent", lagos, 2500, "mtn", "078****456", "paid", rented.strftime("%Y-%m-%d %H:%M:%S")))
    profile = db.execute("SELECT id FROM profiles WHERE user_id=? AND is_kids=0", (demo,)).fetchone()["id"]
    for slug, pos in [("inzira-yamahoro", 62), ("matatu-kings", 104), ("lagos-after-midnight", 31)]:
        mid = db.execute("SELECT id FROM movies WHERE slug=?", (slug,)).fetchone()["id"]
        db.execute("INSERT INTO progress VALUES (?,?,?,?,?)", (profile, mid, pos, 150, now()))
    for slug in ["soweto-skies", "queen-of-dahomey", "nyungwe"]:
        mid = db.execute("SELECT id FROM movies WHERE slug=?", (slug,)).fetchone()["id"]
        db.execute("INSERT INTO watchlist (profile_id, movie_id) VALUES (?,?)", (profile, mid))

    # A few reviews so every page has social proof.
    lines = ["Beautiful. I cried twice.", "Proud to see our stories told like this!", "The music alone is worth it.",
             "Watched it with my whole family.", "A bit slow in the middle but the ending is powerful.",
             "Best thing I have streamed this year.", "Cinematography is world class."]
    viewers = [r["id"] for r in db.execute("SELECT id FROM users WHERE role='viewer' AND id != ?", (demo,))]
    for m in movie_rows:
        for uid in rng.sample(viewers, rng.randint(2, 5)):
            db.execute("INSERT INTO reviews (user_id, movie_id, stars, body, created_at) VALUES (?,?,?,?,?)",
                       (uid, m["id"], rng.choice([3, 4, 4, 5, 5, 5]), rng.choice(lines), now()))
    seed_orders(db, rng, demo)
    seed_consumers(db, rng, demo)


def seed_orders(db, rng, demo):
    """Cart orders in every status, so the admin Orders page and the demo account have history."""
    movies_ = db.execute("SELECT id, title, rent_price, buy_price FROM movies WHERE access != 'free' AND available = 1").fetchall()
    viewers = db.execute("SELECT id, name, email, phone FROM users WHERE role='viewer' AND id != ?", (demo,)).fetchall()
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    statuses = ["delivered"] * 9 + ["paid", "paid", "pending", "pending", "cancelled", "refunded"]
    notes = ["Happy birthday! Enjoy the film.", "For the family movie night.", "", "", "Murakoze for everything!"]

    def code():
        return "MBONI-" + "".join(rng.choices(alphabet, k=4)) + "-" + "".join(rng.choices(alphabet, k=4))

    def make(user, status, picks, day, note=""):
        stamp = day.strftime("%Y-%m-%d %H:%M:%S")
        items = []
        for m, kind, qty in picks:
            unit = m["rent_price"] if kind == "rent" else m["buy_price"]
            items.append((m, kind, qty, unit))
        subtotal = sum(unit * qty for _, _, qty, unit in items)
        promo = rng.choice([None, None, None, ("STUDENT50", 50), ("MBONI10", 10)])
        discount = subtotal * promo[1] // 100 if promo else 0
        ref = f"ORD-{rng.randint(100000, 999999)}"
        oid = db.execute(
            """INSERT INTO orders (ref, user_id, contact_name, email, phone, gift_note, subtotal, discount, total,
               promo_code, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ref, user["id"], user["name"], user["email"], user["phone"] or "0788123456", note, subtotal, discount,
             subtotal - discount, promo[0] if promo else None, status, stamp, stamp)).lastrowid
        for m, kind, qty, unit in items:
            db.execute("INSERT INTO order_items (order_id, movie_id, title, kind, qty, unit_price, line_total) VALUES (?,?,?,?,?,?,?)",
                       (oid, m["id"], m["title"], kind, qty, unit, unit * qty))
        event = lambda st, text, actor="system", at=stamp: db.execute(
            "INSERT INTO order_events (order_id, status, note, actor, created_at) VALUES (?,?,?,?,?)", (oid, st, text, actor, at))
        copies = sum(q for _, _, q, _ in items)
        event("pending", f"Order placed: {copies} cop{'y' if copies == 1 else 'ies'}")
        method = rng.choice(["mtn", "mtn", "airtel", "card"])
        account = "**** 4242" if method == "card" else f"078****{rng.randint(100, 999)}"
        tx_status = {"pending": "failed", "cancelled": "failed", "refunded": "refunded"}.get(status, "paid")
        db.execute(
            """INSERT INTO transactions (ref, user_id, kind, order_id, amount, discount, promo_code, method, account,
               status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (f"NY{day.strftime('%y%m%d')}{rng.randint(100000, 999999)}", user["id"], "order", oid, subtotal - discount,
             discount, promo[0] if promo else None, method, account, tx_status, stamp))
        if status == "pending":
            event("pending", "Payment declined by the network. Waiting for the customer to try again.")
        if status == "cancelled":
            event("cancelled", "Cancelled by the customer", user["name"])
        if status in ("paid", "delivered", "refunded"):
            event("paid", f"Payment confirmed: {method.upper()} {account}")
        if status in ("delivered", "refunded"):
            gifts = 0
            for m, kind, qty, unit in items:
                expires = (day + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S") if kind == "rent" else None
                if status == "delivered":
                    db.execute("INSERT INTO purchases (user_id, movie_id, kind, price, expires_at, order_id, created_at) VALUES (?,?,?,?,?,?,?)",
                               (user["id"], m["id"], kind, unit, expires, oid, stamp))
                for _ in range(qty - 1):
                    db.execute("INSERT INTO gift_codes (code, order_id, movie_id, kind, void, created_at) VALUES (?,?,?,?,?,?)",
                               (code(), oid, m["id"], kind, 1 if status == "refunded" else 0, stamp))
                    gifts += 1
            event("delivered", f"{len(items)} film{'s' if len(items) > 1 else ''} added to the Library"
                  + (f" · {gifts} gift code{'s' if gifts > 1 else ''} sent to {user['email']}" if gifts else ""))
        if status == "refunded":
            event("refunded", "Customer bought the wrong film. Refunded to their wallet.", "Mboni Admin")
        if status == "paid":
            event("paid", "Waiting for delivery: the admin needs to confirm the filmmaker's licence.", "Mboni Admin")
        return oid

    for n, status in enumerate(statuses):
        user = rng.choice(viewers)
        day = datetime.now() - timedelta(days=rng.randint(0, 20), hours=rng.randint(1, 23))
        picks = [(m, rng.choice(["rent", "buy", "buy"]), rng.choice([1, 1, 1, 2, 3])) for m in rng.sample(movies_, rng.randint(1, 3))]
        make(user, status, picks, day, rng.choice(notes))

    # The demo viewer bought two copies of Soweto Skies (one gift already used) and has one unpaid order.
    demo_user = db.execute("SELECT * FROM users WHERE id=?", (demo,)).fetchone()
    by_slug = {r["slug"]: r for r in db.execute("SELECT id, slug, title, rent_price, buy_price FROM movies")}
    oid = make(demo_user, "delivered", [(by_slug["soweto-skies"], "buy", 2), (by_slug["kampala-hustle"], "rent", 1)],
               datetime.now() - timedelta(days=3), "For Mama, who loves a good musical.")
    friend = viewers[0]
    first_gift = db.execute("SELECT code FROM gift_codes WHERE order_id=? LIMIT 1", (oid,)).fetchone()["code"]
    db.execute("UPDATE gift_codes SET redeemed_by=?, redeemed_at=? WHERE code=?", (friend["id"], now(), first_gift))
    make(demo_user, "pending", [(by_slug["congo-rumba"], "buy", 1), (by_slug["lalibela"], "rent", 2)],
         datetime.now() - timedelta(hours=5))

    messages = [
        ("Aline Uwase", "aline@example.rw", "Payment or order", "I paid with MoMo but the order still says pending. Ref ORD on my account. Can you check?", "open"),
        ("Eric Mugisha", "eric@example.rw", "Watching a film", "The film stops on my phone when I switch from Wi-Fi to data. Is there a fix?", "open"),
        ("Grace Mukamana", "grace@example.rw", "Filmmakers & partnerships", "I directed a short film in Huye. How can I get it on Mboni?", "open"),
        ("Jean Habimana", "jean@example.rw", "My account", "How do I add a Kids profile for my daughter?", "answered"),
    ]
    for i, (name, email, topic, body, status) in enumerate(messages):
        stamp = (datetime.now() - timedelta(hours=6 + 20 * i)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute("INSERT INTO messages (name, email, topic, body, status, created_at) VALUES (?,?,?,?,?,?)",
                   (name, email, topic, body, status, stamp))


def seed_consumers(db, rng, demo):
    """Who the viewers are, what critics say, and a month of clickstream (see app/insights.py)."""
    from .insights import AGE_RANGES, COMMUNITIES, GENDERS, SOURCES

    def weighted(pairs):
        return rng.choices([p[0] for p in pairs], [p[1] for p in pairs])[0]

    # Buyers (the 30 sample viewers who paid) lean towards word of mouth and the city...
    buyer_mix = (list(zip(AGE_RANGES, [3, 40, 34, 15, 8])), list(zip(GENDERS, [47, 50, 3])),
                 list(zip(COMMUNITIES, [58, 22, 8, 12])), list(zip(SOURCES, [34, 20, 22, 8, 10, 4, 2])))
    # ...while members who only browse lean towards ads, radio, rural areas (data is expensive) and under-18s (no MoMo).
    browser_mix = (list(zip(AGE_RANGES, [16, 34, 22, 14, 14])), list(zip(GENDERS, [46, 49, 5])),
                   list(zip(COMMUNITIES, [38, 24, 30, 8])), list(zip(SOURCES, [12, 14, 8, 30, 16, 14, 6])))
    first = ["Aline", "Eric", "Grace", "Jean", "Divine", "Kevin", "Sandrine", "Olivier", "Ange", "Patrick", "Keza", "Hirwa",
             "Ineza", "Fabrice", "Yvette", "Moses", "Ruth", "David", "Esther", "Samuel", "Gloria", "Cedric", "Nadine", "Emmy"]
    last = ["Uwase", "Mugisha", "Habimana", "Mukamana", "Niyonzima", "Ishimwe", "Kamanzi", "Uwera", "Ndayisaba", "Iradukunda"]
    pw = db.execute("SELECT password_hash FROM users WHERE email='viewer1@example.rw'").fetchone()[0]
    for n in range(70):
        joined = (datetime.now() - timedelta(days=rng.randint(0, 60))).strftime("%Y-%m-%d %H:%M:%S")
        uid = db.execute("INSERT INTO users (name, email, phone, password_hash, created_at) VALUES (?,?,?,?,?)",
                         (f"{rng.choice(first)} {rng.choice(last)}", f"member{n + 1}@example.rw",
                          f"07{rng.choice('2389')}{rng.randint(1000000, 9999999)}", pw, joined)).lastrowid
        db.execute("INSERT INTO profiles (user_id, name, color) VALUES (?, 'Me', '#3b82f6')", (uid,))
    payers = {r[0] for r in db.execute("SELECT DISTINCT user_id FROM transactions WHERE status='paid'")}
    viewers = [r["id"] for r in db.execute("SELECT id FROM users WHERE role='viewer'")]
    for uid in viewers:
        if uid == demo:
            db.execute("UPDATE users SET age_range='18–24', gender='Male', community='Kigali city', heard_from='friends' WHERE id=?", (uid,))
        elif rng.random() < 0.9:  # the questions are optional, so some people skip them
            ages, genders, places, sources = buyer_mix if uid in payers else browser_mix
            db.execute("UPDATE users SET age_range=?, gender=?, community=?, heard_from=? WHERE id=?",
                       (weighted(ages), weighted(genders), weighted(places), weighted(sources), uid))
    buyers_list = [u for u in viewers if u in payers]
    browsers_list = [u for u in viewers if u not in payers]

    critics = {
        "inzira-yamahoro": ("The most honest film about coming home I have seen this decade.", "Aline Mutesi, Kigali Film Critics' Circle"),
        "lagos-after-midnight": ("Nollywood at its most stylish. Lagos never looked this good.", "Tunde Bakare, film blogger"),
        "soweto-skies": ("A voice you will hear long after the credits roll.", "Nomsa Dlamini, The Jozi Review"),
        "queen-of-dahomey": ("Epic, fierce and long overdue.", "Kwame Ofori, AfroCine podcast"),
        "kigali-in-bloom": ("Kigali has its own romantic comedy, and it is delightful.", "@kigalicinephile, 120k followers"),
    }
    for slug, (quote, name) in critics.items():
        db.execute("UPDATE movies SET critic_quote=?, critic_name=? WHERE slug=?", (quote, name, slug))

    movies = [r["id"] for r in db.execute("SELECT id FROM movies")]
    terms = ["kigali", "comedy", "nollywood", "rwanda", "love", "kinyarwanda", "action", "kids", "music", "lagos", "swahili", "documentary"]
    rows = []
    for n in range(520):
        visitor = f"seed{n:04d}"
        device = "mobile" if rng.random() < 0.76 else "desktop"
        member = rng.random() < 0.45
        user = (rng.choice(buyers_list) if rng.random() < 0.5 else rng.choice(browsers_list)) if member else None
        t = datetime.now() - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        film = rng.choice(movies)

        def add(kind, movie=None, detail=None, minutes=1):
            nonlocal t
            t += timedelta(minutes=minutes)
            rows.append((visitor, user, kind, movie, detail, device, t.strftime("%Y-%m-%d %H:%M:%S")))

        add("visit")
        if rng.random() > 0.70 + (0.06 if device == "desktop" else 0):
            continue                                   # left after the home page (browsers)
        if rng.random() < 0.45:
            add("search", detail=rng.choice(terms))
        add("view_film", film, minutes=rng.randint(1, 4))
        if rng.random() > 0.55:
            continue
        add("trailer" if rng.random() < 0.6 else "add_to_cart", film, minutes=2)
        if rng.random() < 0.5:
            add("checkout", minutes=3)
        if user is None or user not in payers or rng.random() > 0.8:
            continue                                   # evaluated but did not buy
        add("purchase", film, minutes=2)
        if rng.random() < 0.8:
            add("watch", film, minutes=5)
        if rng.random() < 0.3:
            add("review", film, minutes=120)
    db.executemany("INSERT INTO events (visitor, user_id, type, movie_id, detail, device, created_at) VALUES (?,?,?,?,?,?,?)", rows)


@click.command("init-db")
@click.option("--reset", is_flag=True, help="Delete everything and reseed.")
def init_db_command(reset):
    if reset:
        drop_all(get_db())
    init_db()
    click.echo("Database ready.")


@click.command("export-db")
@click.argument("path", default="database/mboni.sql")
def export_db_command(path):
    """Write the whole database (schema + data) as SQL, for the CAT submission."""
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as out:
        for line in get_db().iterdump():
            out.write(f"{line}\n")
    click.echo(f"Exported to {path}")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(export_db_command)
    with app.app_context():
        init_db()

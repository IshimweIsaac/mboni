"""Interface strings in English, Kinyarwanda and French.

Only navigation and the most-used actions are translated; movie data stays in
its original form. Missing keys fall back to English, then to the key itself.
"""

LANGS = {"en": "English", "rw": "Kinyarwanda", "fr": "Français"}

STRINGS = {
    "home": {"en": "Home", "rw": "Ahabanza", "fr": "Accueil"},
    "search": {"en": "Search", "rw": "Shakisha", "fr": "Rechercher"},
    "my_list": {"en": "My List", "rw": "Urutonde rwanjye", "fr": "Ma liste"},
    "library": {"en": "Library", "rw": "Ibyanjye", "fr": "Bibliothèque"},
    "account": {"en": "Account", "rw": "Konti", "fr": "Compte"},
    "plans": {"en": "Plans", "rw": "Ifatabuguzi", "fr": "Abonnements"},
    "sign_in": {"en": "Sign in", "rw": "Injira", "fr": "Se connecter"},
    "sign_up": {"en": "Join free", "rw": "Iyandikishe", "fr": "S'inscrire"},
    "sign_out": {"en": "Sign out", "rw": "Sohoka", "fr": "Se déconnecter"},
    "watch": {"en": "Watch", "rw": "Reba", "fr": "Regarder"},
    "watch_now": {"en": "Watch now", "rw": "Reba nonaha", "fr": "Regarder"},
    "resume": {"en": "Resume", "rw": "Komereza", "fr": "Reprendre"},
    "rent": {"en": "Rent", "rw": "Kodesha", "fr": "Louer"},
    "buy": {"en": "Buy", "rw": "Gura", "fr": "Acheter"},
    "subscribe": {"en": "Subscribe", "rw": "Gura ifatabuguzi", "fr": "S'abonner"},
    "trailer": {"en": "Trailer", "rw": "Incamake", "fr": "Bande-annonce"},
    "more_info": {"en": "More info", "rw": "Ibisobanuro", "fr": "Plus d'infos"},
    "add_list": {"en": "My List", "rw": "Bika", "fr": "Ma liste"},
    "continue_watching": {"en": "Continue watching", "rw": "Komeza kureba", "fr": "Reprendre la lecture"},
    "trending": {"en": "Trending now", "rw": "Ibikunzwe ubu", "fr": "Tendances"},
    "top10": {"en": "Top 10 in Rwanda today", "rw": "10 bya mbere mu Rwanda uyu munsi", "fr": "Top 10 au Rwanda aujourd'hui"},
    "new_releases": {"en": "Fresh premieres", "rw": "Ibishya", "fr": "Nouveautés"},
    "made_in_rwanda": {"en": "Made in Rwanda", "rw": "Byakorewe mu Rwanda", "fr": "Made in Rwanda"},
    "kids": {"en": "For the little ones", "rw": "Iby'abana", "fr": "Pour les enfants"},
    "award": {"en": "Award winners", "rw": "Ibyatsindiye ibihembo", "fr": "Films primés"},
    "data_saver": {"en": "Data saver", "rw": "Kuzigama interineti", "fr": "Économie de données"},
    "language": {"en": "Language", "rw": "Ururimi", "fr": "Langue"},
    "included": {"en": "Included with your plan", "rw": "Biri mu ifatabuguzi ryawe", "fr": "Inclus dans votre abonnement"},
    "downloads": {"en": "Downloads", "rw": "Ibyo wakuruye", "fr": "Téléchargements"},
    "settings": {"en": "Settings", "rw": "Igenamiterere", "fr": "Paramètres"},
    "whos_watching": {"en": "Who's watching?", "rw": "Ni nde ugiye kureba?", "fr": "Qui regarde ?"},
    "explore_africa": {"en": "Explore Africa", "rw": "Zenguruka Afurika", "fr": "Explorer l'Afrique"},
    "mood": {"en": "What's the vibe tonight?", "rw": "Wumva ushaka iki iri joro?", "fr": "Quelle ambiance ce soir ?"},
    "surprise": {"en": "Surprise me", "rw": "Ntungure", "fr": "Surprends-moi"},
}


def t(key, lang="en"):
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry["en"]

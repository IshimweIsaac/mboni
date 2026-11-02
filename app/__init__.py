import os
import secrets

from flask import Flask, abort, g, request, session

from . import db
from .i18n import LANGS, t


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "mboni-dev-secret-change-me"),
        DATABASE=os.environ.get("DATABASE", os.path.join(app.instance_path, "mboni.db")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        WTF_CSRF=True,
        # On the live server (behind Cloudflare's HTTPS) the login cookie is only ever sent over HTTPS.
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)
    if os.environ.get("BEHIND_PROXY") == "1":
        # Trust the scheme/host that the Cloudflare Tunnel forwards, so redirects and links stay on https.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)

    from .auth import bp as auth_bp, load_user
    from .main import bp as main_bp
    from .billing import bp as billing_bp
    from .admin import bp as admin_bp
    from .shop import bp as shop_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(shop_bp)

    @app.before_request
    def before():
        load_user()
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        if request.method == "POST" and app.config["WTF_CSRF"]:
            token = request.form.get("csrf") or request.headers.get("X-CSRF")
            if token != session["csrf"]:
                abort(400, "Your session expired. Go back, refresh the page and try again.")

    @app.context_processor
    def inject():
        lang = session.get("lang") or (g.user["lang"] if g.get("user") else None) or "en"
        return {
            "csrf_token": session.get("csrf", ""),
            "lang": lang,
            "LANGS": LANGS,
            "t": lambda key: t(key, lang),
            "money": money,
        }

    app.jinja_env.filters["money"] = money
    app.jinja_env.filters["runtime"] = lambda m: f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def error(e):
        from flask import render_template
        return render_template("error.html", error=e), e.code

    return app


def money(value):
    return f"{int(value):,} RWF"

from flask import Flask, flash, redirect, request, url_for, session
from app.routes.auth import AuthRoutes
from app.routes.HomeRoutes import HomeRoutes
from app.routes.ThreadRoutes import ThreadRoutes
from app.routes.ChatRoutes import ChatRoutes
from app.routes.UserRoutes import UserRoutes
from app.routes.NotificationRoutes import NotificationRoutes
from .models.database import Database
from app.notifications import unread_count
import os
from app.utils.word_censor import WordCensor

# Load configuration object if available; otherwise fall back to environment
# variables. Importing top-level `config` can fail when the package is
# executed in certain ways, so we try both locations.
try:
    import config as project_config
except Exception:
    try:
        from app import config as project_config
    except Exception:
        project_config = None

def create_app():
    app = Flask(__name__)
    if project_config:
        app.config.from_object(project_config)
    else:
        # Minimal fallbacks if no config module is present
        app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'random-secret-key')

    # Cap upload size (images/videos attached to posts & threads) at 50 MB.
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

    # Best-effort schema setup. If MySQL isn't running we still boot the server
    # so the live scoreboard (/live, /api/live) — which needs no database — keeps
    # working; the forum features will surface their own errors if used.
    try:
        Database.create_tables()
    except Exception as exc:
        print(f"[startup] Skipping create_tables (database unavailable): {exc}")
    
    # Configure word censor with banned words
    WordCensor.BANNED_WORDS = [
    "badword1",
    "badword2",
    "offensive",
    "inappropriate",
    
    # Common Profanity & Swear Words
    "fuck",
    "shit",
    "bitch",
    "asshole",
    "dick",
    "pussy",
    "bastard",
    "crap",
    "damn",
    
    # Toxic Language & Insults
    "idiot",
    "stupid",
    "loser",
    "retard",
    "nigger",
    
    # Common Forum Spam & Scam Terms
    "crypto scam",
    "free money",
    "buy bitcoin",
    "casino online",
    "earn cash fast",
    "click here to win"
]


    # Register Auth Routes
    auth_routes = AuthRoutes()
    app.register_blueprint(auth_routes.register())

    # Register Home Routes
    home_routes = HomeRoutes()
    app.register_blueprint(home_routes.register())

    # Register Thread Routes
    thread_routes = ThreadRoutes()
    app.register_blueprint(thread_routes.register())

    # Register Chat Routes
    chat_routes = ChatRoutes()
    app.register_blueprint(chat_routes.register())

    # Register User profile / follow Routes
    user_routes = UserRoutes()
    app.register_blueprint(user_routes.register())

    # Register Notification Routes
    notification_routes = NotificationRoutes()
    app.register_blueprint(notification_routes.register())

    # Make the unread-notification count available to every template so the
    # bell badge in base.html renders correctly on first paint (the JS poller
    # then keeps it live). Best-effort: a DB hiccup must not break rendering.
    @app.context_processor
    def inject_notification_count():
        user_id = session.get("user_id")
        if not user_id:
            return {"notif_unread_count": 0}
        try:
            db = Database()
            count = unread_count(db, user_id)
            db.close()
        except Exception:
            count = 0
        return {"notif_unread_count": count}

    @app.errorhandler(404)
    def page_not_found(e):
        return "PAGE NOT FOUND", 404

    @app.errorhandler(413)
    def file_too_large(e):
        flash("That file is too large. Please upload media under 50 MB.", "danger")
        return redirect(request.referrer or url_for("Home.home"))

    return app
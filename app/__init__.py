from flask import Flask, flash, redirect, request, url_for
from app.routes.auth import AuthRoutes
from app.routes.HomeRoutes import HomeRoutes
from app.routes.ThreadRoutes import ThreadRoutes
from .models.database import Database
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

    Database.create_tables()
    
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

    @app.errorhandler(404)
    def page_not_found(e):
        return "PAGE NOT FOUND", 404

    @app.errorhandler(413)
    def file_too_large(e):
        flash("That file is too large. Please upload media under 50 MB.", "danger")
        return redirect(request.referrer or url_for("Home.home"))

    return app
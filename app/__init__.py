from flask import Flask
from app.routes.auth import AuthRoutes
from app.routes.HomeRoutes import HomeRoutes
from app.routes.ThreadRoutes import ThreadRoutes
from .models.database import Database
import config

def create_app():
    app = Flask(__name__)
    app.config.from_object(config)
    
    Database.create_tables()

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
    
    return app
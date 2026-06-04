from flask import Flask, render_template
from app.routes.authroute import Authroutes
from app.routes.mainroute import MainRoutes
from .modals.database import Database
import config
import os

def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    
    Database.create_tables()
    
    auth_routes = Authroutes()
    app.register_blueprint(auth_routes.register())

    main_routes = MainRoutes()
    app.register_blueprint(main_routes.register())

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("notfound.html"), 404
    
    return app

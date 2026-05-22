from flask import Flask
from app.routes.authroute import Authroutes
from app.modals.database import Database
def create_app():
    app = Flask(__name__)
    Database.create_tables()
   

    auth_routes = Authroutes()
    app.register_blueprint(auth_routes.register())

    @app.errorhandler(404)
    def page_not_found(e):
        return "Page not found", 404

    return app
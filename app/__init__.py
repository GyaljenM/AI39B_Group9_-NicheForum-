from flask import Flask
from app.routes.auth import AuthRoutes
from app.routes.ProductRoutes import ProductRoutes


def create_app():
    app = Flask(__name__)
    auth_routes = AuthRoutes()
    app.register_blueprint(auth_routes.register())
    product_routes = ProductRoutes()
    app.register_blueprint(product_routes.register())

    @app.errorhandler(404)
    def page_not_found(e):
        return "PAGE NOT FOUND",404
    
    return app
from flask import Blueprint
from app.controllers.productcontroller import productController

class ProductRoutes:
    def __init__(self):
        self.bp = Blueprint('product', __name__)
        self.product_controller = productController()
        self.register_routes()

    def register_routes(self):
        self.bp.add_url_rule(
            "/products", 
            view_func=self.product_controller.get_products, 
            methods=['GET']
        )
        self.bp.add_url_rule(
            "/products/<int:id>", 
            view_func=self.product_controller.get_product, 
            methods=['GET']
        )
        return self.bp
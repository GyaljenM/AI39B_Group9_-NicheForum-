from flask import Blueprint
from app.controllers.ProductController import ProductController as ProductPageController


class ProductRoutes:
    def __init__(self):
        self.bp = Blueprint("Prod", __name__)
        self.controller = ProductPageController()

    def register(self):
        self.bp.route("/product", methods=["GET", "POST"])(
            self.controller.product
        )
        return self.bp
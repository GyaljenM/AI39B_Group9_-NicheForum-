from flask import render_template

class ProductController:
    def product(self):
        return render_template("product.html")
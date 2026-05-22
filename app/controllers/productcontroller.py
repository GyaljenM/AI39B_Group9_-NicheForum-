from flask import Blueprint, render_template
product_bp = Blueprint('products', __name__)

class ProductController:
    
    @product_bp.route('/products')
    def list_products(self):
        return render_template('products.html')

    @product_bp.route('/product/<int:id>')
    def get_product(self, id):
        return render_template('product_detail.html', id=id)
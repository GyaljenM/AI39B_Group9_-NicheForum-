from flask import Blueprint, render_template

class MainRoutes:
    def __init__(self):
        self.bp = Blueprint("main", __name__)
    
    def register(self):
        @self.bp.route("/")
        def home():
            return render_template("home.html")
        
        @self.bp.route("/about")
        def about():
            return render_template("about.html")
        
        @self.bp.route("/contact")
        def contact():
            return render_template("contact.html")
            
        return self.bp

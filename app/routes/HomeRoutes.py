from flask import Blueprint, render_template


class HomeRoutes:
    def __init__(self):
        self.bp = Blueprint("Home", __name__)

    def register(self):
        self.bp.route("/", methods=["GET"])(self.home)
        return self.bp

    def home(self):
        return render_template("index.html")

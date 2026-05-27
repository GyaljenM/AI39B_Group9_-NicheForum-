from flask import Blueprint, render_template, session


class HomeRoutes:
    def __init__(self):
        self.bp = Blueprint("Home", __name__)

    def register(self):
        self.bp.route("/", methods=["GET"])(self.home)
        return self.bp

    def home(self):
        if session.get("user_id"):
            return render_template("dashboard.html", user_name=session.get("user_name"))
        return render_template("index.html")

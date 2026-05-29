from flask import Blueprint, render_template, session


class HomeRoutes:
    def __init__(self):
        self.bp = Blueprint("Home", __name__)

    def register(self):
        self.bp.route("/", methods=["GET"])(self.home)
        self.bp.route("/trending", methods=["GET"])(self.trending)
        self.bp.route("/communities", methods=["GET"])(self.communities)
        self.bp.route("/live", methods=["GET"])(self.live)
        return self.bp

    def home(self):
        return render_template("index.html")

    def trending(self):
        return render_template("trending.html")

    def communities(self):
        return render_template("communities.html")

    def live(self):
        return render_template("live.html")
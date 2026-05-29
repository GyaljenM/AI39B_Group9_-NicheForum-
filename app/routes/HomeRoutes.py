from flask import Blueprint, render_template, session


class HomeRoutes:
    def __init__(self):
        self.bp = Blueprint("Home", __name__)

    def register(self):
        self.bp.route("/", methods=["GET"])(self.home)
        self.bp.route("/communities", methods=["GET"])(self.communities)
        self.bp.route("/trending", methods=["GET"])(self.trending)
        self.bp.route("/live", methods=["GET"])(self.live)
        return self.bp

    def home(self):
        if session.get("user_id"):
            return render_template("dashboard.html", user_name=session.get("user_name"))
        return render_template("index.html")

    def communities(self):
        user_name = session.get("user_name") if session.get("user_id") else None
        return render_template("communities.html", user_name=user_name)

    def trending(self):
        user_name = session.get("user_name") if session.get("user_id") else None
        return render_template("trending.html", user_name=user_name)

    def live(self):
        user_name = session.get("user_name") if session.get("user_id") else None
        return render_template("live.html", user_name=user_name)

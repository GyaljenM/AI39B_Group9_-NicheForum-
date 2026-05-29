from flask import Blueprint, render_template, session
from app.models.database import Database


class HomeRoutes:
    def __init__(self):
        self.bp = Blueprint("Home", __name__)

    def register(self):
        self.bp.route("/", methods=["GET"])(self.home)
        return self.bp

    def home(self):
        db = Database()
        # Fetch all threads for the global feed
        threads = db.fetch_all("SELECT * FROM threads ORDER BY votes DESC, created_at DESC")
        
        # Fetch replies for each thread
        for thread in threads:
            thread['replies'] = db.fetch_all("SELECT * FROM replies WHERE thread_id = %s ORDER BY created_at ASC", (thread['id'],))
        
        db.close()

        if session.get("user_id"):
            return render_template("dashboard.html", user_name=session.get("user_name"), threads=threads)
        return render_template("index.html", threads=threads)

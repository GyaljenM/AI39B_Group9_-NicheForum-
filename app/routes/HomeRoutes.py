from flask import Blueprint, render_template, session, request, redirect, url_for, flash
from app.models.database import Database
from app.auth import login_required


class HomeRoutes:
    def __init__(self):
        self.bp = Blueprint("Home", __name__)

    def register(self):
        self.bp.route("/", methods=["GET"])(self.home)
        self.bp.route("/communities", methods=["GET"])(self.communities)
        self.bp.route("/trending", methods=["GET"])(self.trending)
        self.bp.route("/live", methods=["GET"])(self.live)
        self.bp.route("/community/<int:community_id>", methods=["GET"])(self.community_detail)
        self.bp.route("/community/<int:community_id>/join", methods=["POST"])(self.join_community)
        self.bp.route("/community/<int:community_id>/post", methods=["POST"])(self.create_post)
        return self.bp

    def home(self):
        db = Database()
        posts = db.fetch_all("""
            SELECT p.*, u.name as user_name, c.name as community_name 
            FROM posts p 
            JOIN users u ON p.user_id = u.id 
            JOIN communities c ON p.community_id = c.id 
            ORDER BY p.created_at DESC LIMIT 10
        """)
        communities = db.fetch_all("SELECT * FROM communities LIMIT 5")
        db.close()
        
        if session.get("user_id"):
            return render_template("dashboard.html", user_name=session.get("user_name"), posts=posts, communities=communities)
        return render_template("index.html", posts=posts, communities=communities)

    def communities(self):
        db = Database()
        communities = db.fetch_all("SELECT * FROM communities")
        user_id = session.get("user_id")
        user_communities = []
        if user_id:
            user_memberships = db.fetch_all("SELECT community_id FROM community_members WHERE user_id = %s", (user_id,))
            user_communities = [m["community_id"] for m in user_memberships]
        db.close()
        user_name = session.get("user_name") if user_id else None
        return render_template("communities.html", communities=communities, user_communities=user_communities, user_name=user_name)

    def community_detail(self, community_id):
        db = Database()
        community = db.fetch_one("SELECT * FROM communities WHERE id = %s", (community_id,))
        if not community:
            db.close()
            return "Community not found", 404
        
        posts = db.fetch_all("""
            SELECT p.*, u.name as user_name 
            FROM posts p 
            JOIN users u ON p.user_id = u.id 
            WHERE p.community_id = %s 
            ORDER BY p.created_at DESC
        """, (community_id,))
        
        is_member = False
        user_id = session.get("user_id")
        if user_id:
            membership = db.fetch_one("SELECT * FROM community_members WHERE user_id = %s AND community_id = %s", (user_id, community_id))
            is_member = membership is not None
            
        db.close()
        user_name = session.get("user_name") if user_id else None
        return render_template("community_detail.html", community=community, posts=posts, is_member=is_member, user_name=user_name)

    @login_required
    def join_community(self, community_id):
        user_id = session.get("user_id")
        db = Database()
        # Check if already a member
        exists = db.fetch_one("SELECT * FROM community_members WHERE user_id = %s AND community_id = %s", (user_id, community_id))
        if not exists:
            db.execute("INSERT INTO community_members (user_id, community_id) VALUES (%s, %s)", (user_id, community_id))
            flash("You have joined the community!", "success")
        else:
            flash("You are already a member of this community.", "info")
        db.close()
        return redirect(url_for("Home.community_detail", community_id=community_id))

    @login_required
    def create_post(self, community_id):
        user_id = session.get("user_id")
        db = Database()
        # Check if member
        is_member = db.fetch_one("SELECT * FROM community_members WHERE user_id = %s AND community_id = %s", (user_id, community_id))
        
        if not is_member:
            db.close()
            flash("You must join the community before posting.", "danger")
            return redirect(url_for("Home.community_detail", community_id=community_id))
            
        title = request.form.get("title")
        content = request.form.get("content")
        
        if not title or not content:
            flash("Title and content are required.", "warning")
            db.close()
            return redirect(url_for("Home.community_detail", community_id=community_id))
            
        db.execute("INSERT INTO posts (user_id, community_id, title, content) VALUES (%s, %s, %s, %s)", (user_id, community_id, title, content))
        db.close()
        flash("Post created successfully!", "success")
        return redirect(url_for("Home.community_detail", community_id=community_id))

    def trending(self):
        user_name = session.get("user_name") if session.get("user_id") else None
        return render_template("trending.html", user_name=user_name)

    def live(self):
        user_name = session.get("user_name") if session.get("user_id") else None
        return render_template("live.html", user_name=user_name)

from flask import Blueprint, render_template, session, request, redirect, url_for, flash
from app.models.database import Database
from app.auth import login_required
import os
from werkzeug.utils import secure_filename


class HomeRoutes:
    def __init__(self):
        self.bp = Blueprint("Home", __name__)
        self.upload_folder = 'app/static/uploads/profile_pics'
        if not os.path.exists(self.upload_folder):
            os.makedirs(self.upload_folder, exist_ok=True)

    def register(self):
        self.bp.route("/", methods=["GET"])(self.home)
        self.bp.route("/communities", methods=["GET"])(self.communities)
        self.bp.route("/trending", methods=["GET"])(self.trending)
        self.bp.route("/live", methods=["GET"])(self.live)
        self.bp.route("/profile", methods=["GET"])(self.profile)
        self.bp.route("/profile/update", methods=["POST"])(self.update_profile)
        self.bp.route("/community/<int:community_id>", methods=["GET"])(self.community_detail)
        self.bp.route("/community/<int:community_id>/join", methods=["POST"])(self.join_community)
        self.bp.route("/community/<int:community_id>/post", methods=["POST"])(self.create_post)
        self.bp.route("/post/delete/<int:post_id>", methods=["POST"])(self.delete_post)
        self.bp.route("/post/<int:post_id>/vote", methods=["POST"])(self.vote_post)
        self.bp.route("/post/<int:post_id>/comment", methods=["POST"])(self.comment_post)
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
        
        # Also fetch threads for the home page (index.html)
        threads = db.fetch_all("SELECT * FROM threads ORDER BY created_at DESC LIMIT 10")
        for thread in threads:
            thread['replies'] = db.fetch_all("SELECT * FROM replies WHERE thread_id = %s", (thread['id'],))
            
        communities = db.fetch_all("SELECT * FROM communities LIMIT 5")
        db.close()
        
        if session.get("user_id"):
            return render_template("dashboard.html", user_name=session.get("user_name"), posts=posts, communities=communities)
        return render_template("index.html", posts=posts, threads=threads, communities=communities)

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

        # Attach like/dislike counts, the current user's vote, and comments to
        # each post so the template can render them.
        for post in posts:
            likes = db.fetch_one(
                "SELECT COUNT(*) AS c FROM post_votes WHERE post_id = %s AND vote_type = 'like'",
                (post['id'],))
            dislikes = db.fetch_one(
                "SELECT COUNT(*) AS c FROM post_votes WHERE post_id = %s AND vote_type = 'dislike'",
                (post['id'],))
            post['like_count'] = likes['c'] if likes else 0
            post['dislike_count'] = dislikes['c'] if dislikes else 0

            post['user_vote'] = None
            if user_id:
                my_vote = db.fetch_one(
                    "SELECT vote_type FROM post_votes WHERE post_id = %s AND user_id = %s",
                    (post['id'], user_id))
                if my_vote:
                    post['user_vote'] = my_vote['vote_type']

            post['comments'] = db.fetch_all("""
                SELECT pc.*, u.name AS user_name
                FROM post_comments pc
                JOIN users u ON pc.user_id = u.id
                WHERE pc.post_id = %s
                ORDER BY pc.created_at ASC
            """, (post['id'],))

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

    @login_required
    def profile(self):
        user_id = session.get("user_id")
        db = Database()
        user = db.fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))
        # Fetch user's posts
        posts = db.fetch_all("""
            SELECT p.*, u.name as user_name, c.name as community_name 
            FROM posts p 
            JOIN users u ON p.user_id = u.id 
            JOIN communities c ON p.community_id = c.id 
            WHERE p.user_id = %s
            ORDER BY p.created_at DESC
        """, (user_id,))
        db.close()
        return render_template("activity_feed.html", user=user, posts=posts, user_name=session.get("user_name"))

    @login_required
    def update_profile(self):
        user_id = session.get("user_id")
        name = request.form.get("name")
        bio = request.form.get("bio")
        profile_pic = request.files.get("profile_pic")
        
        db = Database()
        if name:
            db.execute("UPDATE users SET name = %s, bio = %s WHERE id = %s", (name, bio, user_id))
            session["user_name"] = name
            
            if profile_pic and profile_pic.filename != '':
                filename = secure_filename(f"user_{user_id}_{profile_pic.filename}")
                filepath = os.path.join(self.upload_folder, filename)
                profile_pic.save(filepath)
                
                # Store relative path for template use
                rel_path = f"uploads/profile_pics/{filename}"
                db.execute("UPDATE users SET profile_pic = %s WHERE id = %s", 
                           (rel_path, user_id))
                session["profile_pic"] = rel_path
            
            flash("Profile updated successfully!", "success")
        else:
            flash("Name cannot be empty.", "warning")
            
        db.close()
        return redirect(url_for("Home.profile"))

    @login_required
    def delete_post(self, post_id):
        user_id = session.get("user_id")
        db = Database()
        # Verify ownership
        post = db.fetch_one("SELECT * FROM posts WHERE id = %s", (post_id,))
        if post and post['user_id'] == user_id:
            db.execute("DELETE FROM posts WHERE id = %s", (post_id,))
            flash("Post deleted successfully.", "success")
        else:
            flash("You do not have permission to delete this post.", "danger")
        db.close()
        return redirect(request.referrer or url_for("Home.home"))

    @login_required
    def vote_post(self, post_id):
        """Like or dislike a post. Voting the same way again removes the vote
        (toggle); voting the other way switches it."""
        user_id = session.get("user_id")
        vote_type = request.form.get("vote_type")
        if vote_type not in ("like", "dislike"):
            flash("Invalid vote.", "warning")
            return redirect(request.referrer or url_for("Home.home"))

        db = Database()
        post = db.fetch_one("SELECT * FROM posts WHERE id = %s", (post_id,))
        if not post:
            db.close()
            flash("Post not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        existing = db.fetch_one(
            "SELECT * FROM post_votes WHERE post_id = %s AND user_id = %s",
            (post_id, user_id))

        if existing is None:
            db.execute(
                "INSERT INTO post_votes (user_id, post_id, vote_type) VALUES (%s, %s, %s)",
                (user_id, post_id, vote_type))
        elif existing['vote_type'] == vote_type:
            # Clicking the same button again removes the vote.
            db.execute("DELETE FROM post_votes WHERE id = %s", (existing['id'],))
        else:
            # Switch like <-> dislike.
            db.execute("UPDATE post_votes SET vote_type = %s WHERE id = %s",
                       (vote_type, existing['id']))
        db.close()
        return redirect(request.referrer or url_for("Home.community_detail", community_id=post['community_id']))

    @login_required
    def comment_post(self, post_id):
        """Add a reply/comment to a post."""
        user_id = session.get("user_id")
        content = request.form.get("content", "").strip()

        db = Database()
        post = db.fetch_one("SELECT * FROM posts WHERE id = %s", (post_id,))
        if not post:
            db.close()
            flash("Post not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        if not content:
            db.close()
            flash("Reply cannot be empty.", "warning")
            return redirect(request.referrer or url_for("Home.community_detail", community_id=post['community_id']))

        db.execute(
            "INSERT INTO post_comments (post_id, user_id, content) VALUES (%s, %s, %s)",
            (post_id, user_id, content))
        db.close()
        flash("Reply posted!", "success")
        return redirect(request.referrer or url_for("Home.community_detail", community_id=post['community_id']))

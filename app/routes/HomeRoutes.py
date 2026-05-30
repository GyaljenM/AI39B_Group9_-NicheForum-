from flask import Blueprint, render_template, session, request, redirect, url_for, flash
from app.models.database import Database


class HomeRoutes:
    def __init__(self):
        self.bp = Blueprint("Home", __name__)

    def register(self):
        self.bp.route("/", methods=["GET"])(self.home)
        # Communities listing
        self.bp.route("/communities", methods=["GET"])(self.communities)
        # Community detail & actions
        self.bp.route("/community/<int:community_id>", methods=["GET"])(self.community_detail)
        self.bp.route("/community/<int:community_id>/join", methods=["POST"])(self.join_community)
        self.bp.route("/community/<int:community_id>/create_post", methods=["POST"])(self.create_post)
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

    def communities(self):
        db = Database()
        # Use categories as communities
        communities = db.fetch_all("SELECT * FROM categories ORDER BY name ASC")
        db.close()

        user_communities = session.get('communities', [])
        return render_template("communities.html", communities=communities, user_communities=user_communities, user_name=session.get('user_name'))

    def community_detail(self, community_id):
        db = Database()
        community = db.fetch_one("SELECT * FROM categories WHERE id = %s", (community_id,))
        if not community:
            db.close()
            flash('Community not found.', 'danger')
            return redirect(url_for('Home.communities'))

        posts = db.fetch_all("SELECT t.*, u.name as user_name FROM threads t LEFT JOIN users u ON u.id = t.author WHERE t.category_id = %s ORDER BY t.created_at DESC", (community_id,))
        # Fallback: threads where category_id is null but category name matches
        if not posts:
            posts = db.fetch_all("SELECT t.*, u.name as user_name FROM threads t LEFT JOIN users u ON u.id = t.author WHERE t.category_id = %s OR t.category = %s ORDER BY t.created_at DESC", (community_id, community['name']))

        db.close()
        user_communities = session.get('communities', [])
        is_member = community_id in user_communities
        return render_template('community_detail.html', community=community, posts=posts, is_member=is_member, user_name=session.get('user_name'), user_communities=user_communities)

    def join_community(self, community_id):
        # Store membership in session for simplicity
        communities = session.get('communities', [])
        if community_id not in communities:
            communities.append(community_id)
            session['communities'] = communities
            flash('Joined community successfully.', 'success')
        else:
            flash('Already a member.', 'warning')
        return redirect(request.referrer or url_for('Home.community_detail', community_id=community_id))

    def create_post(self, community_id):
        title = request.form.get('title')
        content = request.form.get('content')
        author = session.get('user_name', 'Guest')
        if not title or not content:
            flash('Title and content are required.', 'warning')
            return redirect(request.referrer or url_for('Home.community_detail', community_id=community_id))

        db = Database()
        community = db.fetch_one("SELECT * FROM categories WHERE id = %s", (community_id,))
        category_name = community['name'] if community else 'Sports'
        try:
            db.execute("INSERT INTO threads (title, content, author, category_id, category) VALUES (%s, %s, %s, %s, %s)", (title, content, author, community_id, category_name))
        except Exception as e:
            flash('Error creating post: ' + str(e), 'danger')
        db.close()
        flash('Post created.', 'success')
        return redirect(url_for('Home.community_detail', community_id=community_id))

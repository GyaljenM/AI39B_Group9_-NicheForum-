from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify, current_app
from app.models.database import Database
from app.auth import login_required, admin_required
from app.follows import following_ids, get_followers, get_following
from app.notifications import notify_community_members, notify_admins_of_report
from app.services.worldcup import get_match_manager
from app.utils.word_censor import WordCensor
import os
import uuid
from werkzeug.utils import secure_filename


# Allowed upload types, shared by HomeRoutes (posts) and ThreadRoutes (threads).
ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_VIDEO_EXT = {'mp4', 'webm', 'mov', 'ogg'}

# A community note is only promoted to the public "Readers added context" banner
# once its helpful ratings outweigh its not-helpful ones by at least this much.
NOTE_PROMOTE_THRESHOLD = 2

# Standard content-report reasons, shared by posts and threads. (value, label)
# pairs: `value` is stored, `label` is shown in the report dialog.
REPORT_REASONS = [
    ("misinformation", "Misinformation or false information"),
    ("spam", "Spam or misleading"),
    ("harassment", "Harassment or bullying"),
    ("hate", "Hate speech or symbols"),
    ("violence", "Violence or dangerous behaviour"),
    ("sexual", "Adult or sexual content"),
    ("other", "Something else"),
]
REPORT_REASON_VALUES = {value for value, _ in REPORT_REASONS}


def save_media(file, folder, url_prefix):
    """Save an uploaded image/video with a collision-proof name.

    Returns a (media_type, relative_path) tuple where media_type is
    'image' or 'video' and relative_path is relative to the static folder
    (e.g. 'uploads/posts/<uuid>.jpg'). Returns None if the file is missing
    or its extension is not an allowed image/video type.
    """
    if not file or not file.filename:
        return None
    safe = secure_filename(file.filename)
    if '.' not in safe:
        return None
    ext = safe.rsplit('.', 1)[1].lower()
    if ext in ALLOWED_IMAGE_EXT:
        media_type = 'image'
    elif ext in ALLOWED_VIDEO_EXT:
        media_type = 'video'
    else:
        return None
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(folder, exist_ok=True)
    file.save(os.path.join(folder, stored_name))
    return media_type, f"{url_prefix}/{stored_name}"


def attach_media_and_poll(db, item, kind, user_id):
    """Attach media list and (for polls) option tallies to a post/thread dict.

    `kind` is 'post' or 'thread'. Adds item['media']; for poll items also adds
    item['poll_options'] (each with vote_count + pct), item['poll_total'],
    item['user_poll_vote'] and item['show_results'] (results stay hidden until
    the current user has voted).
    """
    id_field = "post_id" if kind == "post" else "thread_id"
    type_field = "post_type" if kind == "post" else "thread_type"
    media_table = f"{kind}_media"
    options_table = f"{kind}_poll_options"
    votes_table = f"{kind}_poll_votes"

    item["media"] = db.fetch_all(
        f"SELECT * FROM {media_table} WHERE {id_field} = %s ORDER BY id",
        (item["id"],),
    )

    if item.get(type_field) != "poll":
        return

    options = db.fetch_all(
        f"""
        SELECT o.id, o.option_text, COUNT(v.id) AS vote_count
        FROM {options_table} o
        LEFT JOIN {votes_table} v ON v.option_id = o.id
        WHERE o.{id_field} = %s
        GROUP BY o.id, o.option_text, o.position
        ORDER BY o.position, o.id
        """,
        (item["id"],),
    )
    total = sum(o["vote_count"] for o in options)
    for o in options:
        o["pct"] = round((o["vote_count"] / total) * 100) if total else 0

    user_vote = None
    if user_id:
        row = db.fetch_one(
            f"SELECT option_id FROM {votes_table} WHERE {id_field} = %s AND user_id = %s",
            (item["id"], user_id),
        )
        if row:
            user_vote = row["option_id"]

    item["poll_options"] = options
    item["poll_total"] = total
    item["user_poll_vote"] = user_vote
    item["show_results"] = user_vote is not None


def attach_notes(db, item, kind, user_id):
    """Attach community notes (and their helpful/not-helpful tallies) to a post/thread.

    `kind` is 'post' or 'thread'. Adds:
      item['notes']    — every note, each with author_name, helpful_count,
                         not_helpful_count, net_score, promoted, and (if user_id)
                         user_rating ('helpful'/'not_helpful'/None).
      item['top_note'] — the single highest-rated promoted note, or None. This is
                         what surfaces publicly as "Readers added context".
    """
    id_field = f"{kind}_id"
    notes_table = f"{kind}_notes"
    votes_table = f"{kind}_note_votes"

    notes = db.fetch_all(
        f"""
        SELECT n.*, u.name AS author_name,
               SUM(CASE WHEN v.rating = 'helpful' THEN 1 ELSE 0 END) AS helpful_count,
               SUM(CASE WHEN v.rating = 'not_helpful' THEN 1 ELSE 0 END) AS not_helpful_count
        FROM {notes_table} n
        JOIN users u ON n.user_id = u.id
        LEFT JOIN {votes_table} v ON v.note_id = n.id
        WHERE n.{id_field} = %s
        GROUP BY n.id
        ORDER BY (SUM(CASE WHEN v.rating = 'helpful' THEN 1 ELSE 0 END)
                  - SUM(CASE WHEN v.rating = 'not_helpful' THEN 1 ELSE 0 END)) DESC,
                 n.created_at DESC
        """,
        (item["id"],),
    )

    # Map of note_id -> this user's rating, so the template can highlight buttons.
    my_ratings = {}
    if user_id and notes:
        ids = tuple(n["id"] for n in notes)
        placeholders = ", ".join(["%s"] * len(ids))
        rows = db.fetch_all(
            f"SELECT note_id, rating FROM {votes_table} "
            f"WHERE user_id = %s AND note_id IN ({placeholders})",
            (user_id, *ids),
        )
        my_ratings = {r["note_id"]: r["rating"] for r in rows}

    top_note = None
    for n in notes:
        # SUM() returns Decimal/None depending on driver; coerce to plain ints.
        helpful = int(n["helpful_count"] or 0)
        not_helpful = int(n["not_helpful_count"] or 0)
        n["helpful_count"] = helpful
        n["not_helpful_count"] = not_helpful
        n["net_score"] = helpful - not_helpful
        n["promoted"] = n["net_score"] >= NOTE_PROMOTE_THRESHOLD and helpful > not_helpful
        n["user_rating"] = my_ratings.get(n["id"])
        # Notes come back ordered by net score desc, so the first promoted one wins.
        if top_note is None and n["promoted"]:
            top_note = n

    item["notes"] = notes
    item["top_note"] = top_note


def is_community_moderator(db, community_id, user_id):
    """True if `user_id` is an appointed moderator of this community."""
    if not user_id:
        return False
    row = db.fetch_one(
        "SELECT 1 FROM community_moderators WHERE community_id = %s AND user_id = %s",
        (community_id, user_id),
    )
    return row is not None


def can_moderate_community(db, community_id):
    """True if the current session may moderate this community — i.e. a site
    admin (users.role='admin') or an appointed moderator of the community."""
    if session.get("user_role") == "admin":
        return True
    return is_community_moderator(db, community_id, session.get("user_id"))


def is_community_owner(db, community_id, user_id):
    """True if the current user is the creator/leader of this community."""
    if not user_id:
        return False
    row = db.fetch_one(
        "SELECT 1 FROM communities WHERE id = %s AND owner_id = %s",
        (community_id, user_id),
    )
    return row is not None


def can_manage_community(db, community_id):
    """True if the current session may manage this community (owner or admin)."""
    if session.get("user_role") == "admin":
        return True
    return is_community_owner(db, community_id, session.get("user_id"))


def is_user_banned(db, community_id, user_id):
    """True if `user_id` is banned from this community."""
    if not user_id:
        return False
    row = db.fetch_one(
        "SELECT 1 FROM community_bans WHERE community_id = %s AND user_id = %s",
        (community_id, user_id),
    )
    return row is not None


class HomeRoutes:
    def __init__(self):
        self.bp = Blueprint("Home", __name__)
        self.upload_folder = 'app/static/uploads/profile_pics'
        if not os.path.exists(self.upload_folder):
            os.makedirs(self.upload_folder, exist_ok=True)
        # Folder for images/videos attached to community posts.
        self.posts_upload_folder = 'app/static/uploads/posts'
        if not os.path.exists(self.posts_upload_folder):
            os.makedirs(self.posts_upload_folder, exist_ok=True)

    def register(self):
        self.bp.route("/", methods=["GET"])(self.home)
        self.bp.route("/communities", methods=["GET"])(self.communities)
        self.bp.route("/communities/create", methods=["GET", "POST"])(self.create_community)
        self.bp.route("/search", methods=["GET"])(self.search_communities)
        self.bp.route("/trending", methods=["GET"])(self.trending)
        self.bp.route("/live", methods=["GET"])(self.live)
        self.bp.route("/api/live", methods=["GET"])(self.api_live)
        self.bp.route("/profile", methods=["GET"])(self.profile)
        self.bp.route("/profile/update", methods=["POST"])(self.update_profile)
        self.bp.route("/community/<int:community_id>", methods=["GET"])(self.community_detail)
        self.bp.route("/community/<int:community_id>/join", methods=["POST"])(self.join_community)
        self.bp.route("/community/<int:community_id>/delete", methods=["POST"])(self.delete_community)
        self.bp.route("/community/<int:community_id>/post", methods=["POST"])(self.create_post)
        self.bp.route("/post/delete/<int:post_id>", methods=["POST"])(self.delete_post)
        self.bp.route("/post/<int:post_id>/edit", methods=["GET", "POST"])(self.edit_post)
        self.bp.route("/post/<int:post_id>/vote", methods=["POST"])(self.vote_post)
        self.bp.route("/post/<int:post_id>/comment", methods=["POST"])(self.comment_post)
        self.bp.route("/post/<int:post_id>/poll-vote", methods=["POST"])(self.vote_poll)
        self.bp.route("/post/<int:post_id>/note", methods=["POST"])(self.add_post_note)
        self.bp.route("/note/<int:note_id>/rate", methods=["POST"])(self.rate_post_note)
        self.bp.route("/post/<int:post_id>/report", methods=["POST"])(self.report_post)
        self.bp.route("/admin/reports", methods=["GET"])(self.admin_reports)
        self.bp.route("/report/post/<int:report_id>/resolve", methods=["POST"])(self.resolve_post_report)
        # Per-community moderation panel
        self.bp.route("/community/<int:community_id>/admin", methods=["GET"])(self.community_admin)
        self.bp.route("/community/<int:community_id>/admin/report/<int:report_id>/resolve", methods=["POST"])(self.community_resolve_report)
        self.bp.route("/community/<int:community_id>/admin/ban/<int:user_id>", methods=["POST"])(self.ban_member)
        self.bp.route("/community/<int:community_id>/admin/unban/<int:user_id>", methods=["POST"])(self.unban_member)
        self.bp.route("/community/<int:community_id>/admin/moderator/<int:user_id>/add", methods=["POST"])(self.add_moderator)
        self.bp.route("/community/<int:community_id>/admin/moderator/<int:user_id>/remove", methods=["POST"])(self.remove_moderator)
        return self.bp

    def home(self):
        db = Database()
        posts = db.fetch_all("""
            SELECT p.*, u.name as user_name, u.profile_pic as user_pic, c.name as community_name
            FROM posts p
            JOIN users u ON p.user_id = u.id
            JOIN communities c ON p.community_id = c.id
            ORDER BY p.created_at DESC LIMIT 10
        """)
        user_id = session.get("user_id")
        for post in posts:
            likes = db.fetch_one(
                "SELECT COUNT(*) AS c FROM post_votes WHERE post_id = %s AND vote_type = 'like'",
                (post['id'],)
            )
            dislikes = db.fetch_one(
                "SELECT COUNT(*) AS c FROM post_votes WHERE post_id = %s AND vote_type = 'dislike'",
                (post['id'],)
            )
            post['like_count'] = likes['c'] if likes else 0
            post['dislike_count'] = dislikes['c'] if dislikes else 0
            post['user_vote'] = None
            if user_id:
                my_vote = db.fetch_one(
                    "SELECT vote_type FROM post_votes WHERE post_id = %s AND user_id = %s",
                    (post['id'], user_id)
                )
                if my_vote:
                    post['user_vote'] = my_vote['vote_type']

            post['comments'] = db.fetch_all(
                """
                SELECT pc.*, u.name AS user_name, u.profile_pic AS user_pic
                FROM post_comments pc
                JOIN users u ON pc.user_id = u.id
                WHERE pc.post_id = %s
                ORDER BY pc.created_at ASC
                """,
                (post['id'],)
            )
            attach_media_and_poll(db, post, "post", user_id)
            attach_notes(db, post, "post", user_id)

        # Also fetch threads for the home page (index.html). Threads store the
        # author by name only, so we LEFT JOIN users on name for the avatar
        # (best-effort: falls back to initials when there's no match).
        threads = db.fetch_all("""
            SELECT t.*, u.profile_pic AS author_pic
            FROM threads t
            LEFT JOIN users u ON u.name = t.author
            ORDER BY t.created_at DESC LIMIT 10
        """)
        for thread in threads:
            thread['replies'] = db.fetch_all("""
                SELECT r.*, u.profile_pic AS author_pic
                FROM replies r
                LEFT JOIN users u ON u.name = r.user_email
                WHERE r.thread_id = %s
            """, (thread['id'],))
            attach_media_and_poll(db, thread, "thread", session.get("user_id"))
            attach_notes(db, thread, "thread", session.get("user_id"))

        recent_threads = db.fetch_all("""
            SELECT 'thread' as type, id, title, category, author, created_at, NULL as community_id 
            FROM threads
            UNION ALL
            SELECT 'post' as type, p.id, p.title, c.name as category, u.name as author, p.created_at, p.community_id 
            FROM posts p 
            JOIN users u ON p.user_id = u.id 
            JOIN communities c ON p.community_id = c.id
            ORDER BY created_at DESC LIMIT 10
        """)

        communities = db.fetch_all("SELECT * FROM communities LIMIT 5")
        
        # Fetch live stats for hero/banner sections
        total_communities = db.fetch_one("SELECT COUNT(*) AS count FROM communities")['count'] or 0
        total_members = db.fetch_one("SELECT COUNT(*) AS count FROM users")['count'] or 0
        online_now = db.fetch_one("SELECT COUNT(*) AS count FROM users WHERE is_active = 1")['count'] or 0
        
        db.close()
        
        if session.get("user_id"):
            return render_template("dashboard.html", user_name=session.get("user_name"), posts=posts, communities=communities, total_communities=total_communities, total_members=total_members, online_now=online_now)
        return render_template("index.html", posts=posts, threads=threads, communities=communities, total_communities=total_communities, total_members=total_members, online_now=online_now)

    def communities(self):
        db = Database()
        communities = db.fetch_all(
            """
            SELECT c.*, COALESCE(m.member_count, 0) AS member_count
            FROM communities c
            LEFT JOIN (
                SELECT community_id, COUNT(*) AS member_count
                FROM community_members
                GROUP BY community_id
            ) m ON m.community_id = c.id
            ORDER BY COALESCE(m.member_count, 0) DESC, c.name ASC
            """
        )
        user_id = session.get("user_id")
        user_communities = []
        if user_id:
            user_memberships = db.fetch_all("SELECT community_id FROM community_members WHERE user_id = %s", (user_id,))
            user_communities = [m["community_id"] for m in user_memberships]

        total_communities = db.fetch_one("SELECT COUNT(*) AS count FROM communities")['count'] or 0
        total_members = db.fetch_one("SELECT COUNT(*) AS count FROM users")['count'] or 0
        total_posts = db.fetch_one("SELECT COUNT(*) AS count FROM posts")['count'] or 0
        online_now = db.fetch_one("SELECT COUNT(*) AS count FROM users WHERE is_active = 1")['count'] or 0

        db.close()
        user_name = session.get("user_name") if user_id else None
        # Ensure a few popular sport communities show a Join button prominently
        featured_join_names = ['Football', 'Basketball', 'Tennis', 'Cricket']
        return render_template(
            "communities.html",
            communities=communities,
            user_communities=user_communities,
            user_name=user_name,
            featured_join_names=featured_join_names,
            total_communities=total_communities,
            total_members=total_members,
            total_posts=total_posts,
            online_now=online_now,
        )

    @login_required
    def create_community(self):
        """Render a form to create a new community (GET) and handle creation (POST)."""
        user_name = session.get("user_name")
        allowed_categories = ['Football', 'Basketball', 'Tennis', 'Cricket', 'eSports', 'Combat Sports', 'Fitness']
        db = Database()

        if request.method == 'GET':
            return render_template('create_community.html', user_name=user_name, categories=allowed_categories)

        # POST: create the community
        name = (request.form.get('name') or '').strip()
        description = (request.form.get('description') or '').strip()
        category = (request.form.get('category') or 'Football').strip()
        if category not in allowed_categories:
            category = 'Football'

        if not name:
            flash('Community name is required.', 'warning')
            db.close()
            return redirect(url_for('Home.create_community'))

        try:
            exists = db.fetch_one('SELECT id FROM communities WHERE name = %s', (name,))
            if exists:
                flash('A community with that name already exists.', 'warning')
                db.close()
                return redirect(url_for('Home.create_community'))

            user_id = session.get('user_id')
            db.execute('INSERT INTO communities (name, description, category, owner_id) VALUES (%s, %s, %s, %s)', (name, description, category, user_id))
            new_id = db.fetch_one('SELECT LAST_INSERT_ID() AS id')['id']
            db.execute('INSERT INTO community_members (user_id, community_id) VALUES (%s, %s)', (user_id, new_id))
            db.close()
            flash('Community created successfully!', 'success')
            return redirect(url_for('Home.community_detail', community_id=new_id))
        except Exception as e:
            db.close()
            flash(f'Error creating community: {e}', 'danger')
            return redirect(url_for('Home.create_community'))

    def search_communities(self):
        """Instagram-style universal search: people, communities, and posts.

        Defaults to the People tab so users can find others to follow. The
        endpoint keeps its historical name (Home.search_communities) so existing
        url_for references stay valid.
        """
        query = (request.args.get("q") or "").strip()
        user_id = session.get("user_id")
        people = []
        communities = []
        posts = []
        user_communities = []
        followed_ids = set()

        db = Database()
        if query:
            like = f"%{query}%"

            # ── People (search by display name) ──────────────────────────
            people = db.fetch_all(
                """
                SELECT u.id, u.name, u.bio, u.profile_pic,
                       (SELECT COUNT(*) FROM user_follows f WHERE f.followee_id = u.id) AS follower_count
                FROM users u
                WHERE u.name LIKE %s AND (%s IS NULL OR u.id != %s)
                ORDER BY follower_count DESC, u.name ASC
                LIMIT 30
                """,
                (like, user_id, user_id),
            )

            # ── Communities (name or description) ────────────────────────
            communities = db.fetch_all(
                """
                SELECT c.*,
                       (SELECT COUNT(*) FROM community_members m WHERE m.community_id = c.id) AS member_count
                FROM communities c
                WHERE c.name LIKE %s OR c.description LIKE %s
                ORDER BY member_count DESC, c.name ASC
                """,
                (like, like),
            )

            # ── Posts (title or body) ────────────────────────────────────
            posts = db.fetch_all(
                """
                SELECT p.id, p.title, p.content, p.created_at, p.community_id,
                       u.name AS user_name, c.name AS community_name
                FROM posts p
                JOIN users u ON p.user_id = u.id
                JOIN communities c ON p.community_id = c.id
                WHERE p.title LIKE %s OR p.content LIKE %s
                ORDER BY p.created_at DESC
                LIMIT 30
                """,
                (like, like),
            )

            if user_id:
                memberships = db.fetch_all(
                    "SELECT community_id FROM community_members WHERE user_id = %s", (user_id,)
                )
                user_communities = [m["community_id"] for m in memberships]
                followed_ids = following_ids(db, user_id)
        db.close()

        user_name = session.get("user_name") if user_id else None
        return render_template(
            "search_results.html",
            query=query,
            people=people,
            communities=communities,
            posts=posts,
            user_communities=user_communities,
            followed_ids=followed_ids,
            current_user_id=user_id,
            user_name=user_name,
        )

    def community_detail(self, community_id):
        db = Database()
        community = db.fetch_one(
            "SELECT c.*, u.name AS owner_name FROM communities c "
            "LEFT JOIN users u ON c.owner_id = u.id "
            "WHERE c.id = %s",
            (community_id,),
        )
        if not community:
            db.close()
            return "Community not found", 404
        
        posts = db.fetch_all("""
            SELECT p.*, u.name as user_name, u.profile_pic as user_pic
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
                SELECT pc.*, u.name AS user_name, u.profile_pic AS user_pic
                FROM post_comments pc
                JOIN users u ON pc.user_id = u.id
                WHERE pc.post_id = %s
                ORDER BY pc.created_at ASC
            """, (post['id'],))

            attach_media_and_poll(db, post, "post", user_id)
            attach_notes(db, post, "post", user_id)

        can_moderate = can_moderate_community(db, community_id)
        is_owner = is_community_owner(db, community_id, user_id)
        can_delete = is_owner or session.get("user_role") == "admin"
        db.close()
        user_name = session.get("user_name") if user_id else None
        return render_template(
            "community_detail.html",
            community=community,
            posts=posts,
            is_member=is_member,
            user_name=user_name,
            can_moderate=can_moderate,
            can_delete=can_delete,
        )

    @login_required
    def join_community(self, community_id):
        user_id = session.get("user_id")
        db = Database()
        if is_user_banned(db, community_id, user_id):
            db.close()
            flash("You have been banned from this community and cannot rejoin.", "danger")
            return redirect(url_for("Home.community_detail", community_id=community_id))
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
    def delete_community(self, community_id):
        db = Database()
        if not can_manage_community(db, community_id):
            db.close()
            flash("You don't have permission to delete this community.", "danger")
            return redirect(url_for("Home.community_detail", community_id=community_id))

        community = db.fetch_one("SELECT name FROM communities WHERE id = %s", (community_id,))
        if not community:
            db.close()
            return "Community not found", 404

        db.execute("DELETE FROM communities WHERE id = %s", (community_id,))
        db.close()
        flash(f"Community '{community['name']}' has been deleted.", "success")
        return redirect(url_for("Home.communities"))

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

        post_type = request.form.get("post_type", "text")
        if post_type not in ("text", "media", "poll"):
            post_type = "text"
        title = (request.form.get("title") or "").strip()
        content = (request.form.get("content") or "").strip()

        if not title:
            db.close()
            flash("A title is required.", "warning")
            return redirect(url_for("Home.community_detail", community_id=community_id))

        # Text posts must have a body; media/poll posts may have an empty body.
        if post_type == "text" and not content:
            db.close()
            flash("Please write something in the body of your post.", "warning")
            return redirect(url_for("Home.community_detail", community_id=community_id))

        # Validate + pre-save media so we don't insert an empty post on failure.
        saved_media = []
        if post_type in ("text", "media"):
            for f in request.files.getlist("media"):
                if not f or not f.filename:
                    continue
                result = save_media(f, self.posts_upload_folder, "uploads/posts")
                if result is None:
                    flash(f"Skipped '{f.filename}': unsupported file type.", "warning")
                    continue
                saved_media.append(result)
            if post_type == "media" and not saved_media:
                db.close()
                flash("Please attach at least one image or video.", "warning")
                return redirect(url_for("Home.community_detail", community_id=community_id))

        # Validate poll options.
        poll_options = []
        if post_type == "poll":
            poll_options = [o.strip() for o in request.form.getlist("poll_options") if o.strip()]
            if len(poll_options) < 2:
                db.close()
                flash("A poll needs at least two options.", "warning")
                return redirect(url_for("Home.community_detail", community_id=community_id))

        # Mask banned words in anything the author wrote before it is stored.
        title = WordCensor.censor_text(title)
        content = WordCensor.censor_text(content)

        db.execute(
            "INSERT INTO posts (user_id, community_id, title, content, post_type) VALUES (%s, %s, %s, %s, %s)",
            (user_id, community_id, title, content, post_type),
        )
        post_id = db.fetch_one("SELECT LAST_INSERT_ID() AS id")["id"]

        for media_type, rel_path in saved_media:
            db.execute(
                "INSERT INTO post_media (post_id, media_type, file_path) VALUES (%s, %s, %s)",
                (post_id, media_type, rel_path),
            )

        for position, option_text in enumerate(poll_options):
            db.execute(
                "INSERT INTO post_poll_options (post_id, option_text, position) VALUES (%s, %s, %s)",
                (post_id, WordCensor.censor_text(option_text), position),
            )

        # Create notifications for all community members about this new post
        try:
            community = db.fetch_one(
                "SELECT id, name FROM communities WHERE id = %s",
                (community_id,),
            )
            if community:
                notify_community_members(
                    db,
                    community_id,
                    "community_post",
                    f"New post in c/{community['name']}: {title}",
                    url=url_for("Home.community_detail", community_id=community_id),
                    actor_id=user_id
                )
        except Exception as e:
            print(f"Error creating community post notification: {e}")

        db.close()
        flash("Post created successfully!", "success")
        return redirect(url_for("Home.community_detail", community_id=community_id))

    @login_required
    def vote_poll(self, post_id):
        """Cast or change a vote on a poll post (one vote per member)."""
        user_id = session.get("user_id")
        option_id = request.form.get("option_id")

        db = Database()
        post = db.fetch_one("SELECT * FROM posts WHERE id = %s", (post_id,))
        if not post:
            db.close()
            flash("Post not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        # Voting on a community poll requires membership, like posting.
        is_member = db.fetch_one(
            "SELECT * FROM community_members WHERE user_id = %s AND community_id = %s",
            (user_id, post["community_id"]),
        )
        if not is_member:
            db.close()
            flash("Join the community to vote in its polls.", "danger")
            return redirect(request.referrer or url_for("Home.community_detail", community_id=post["community_id"]))

        # Validate the option belongs to this poll.
        option = db.fetch_one(
            "SELECT * FROM post_poll_options WHERE id = %s AND post_id = %s",
            (option_id, post_id),
        )
        if not option:
            db.close()
            flash("Invalid poll option.", "warning")
            return redirect(request.referrer or url_for("Home.community_detail", community_id=post["community_id"]))

        existing = db.fetch_one(
            "SELECT * FROM post_poll_votes WHERE post_id = %s AND user_id = %s",
            (post_id, user_id),
        )
        if existing is None:
            db.execute(
                "INSERT INTO post_poll_votes (option_id, post_id, user_id) VALUES (%s, %s, %s)",
                (option["id"], post_id, user_id),
            )
        elif existing["option_id"] != option["id"]:
            db.execute(
                "UPDATE post_poll_votes SET option_id = %s WHERE id = %s",
                (option["id"], existing["id"]),
            )
        db.close()
        return redirect(request.referrer or url_for("Home.community_detail", community_id=post["community_id"]))

    def trending(self):
        user_name = session.get("user_name") if session.get("user_id") else None

        # Time window (?range=today|week|all). Default: week.
        range_arg = (request.args.get("range") or "week").lower()
        if range_arg not in ("today", "week", "all"):
            range_arg = "week"
        if range_arg == "today":
            where = "WHERE p.created_at >= NOW() - INTERVAL 1 DAY"
        elif range_arg == "week":
            where = "WHERE p.created_at >= NOW() - INTERVAL 7 DAY"
        else:
            where = ""

        db = Database()

        # Real trending = posts ranked by likes (weighted) + comments.
        posts = db.fetch_all(f"""
            SELECT p.id, p.title, p.content, p.created_at, p.community_id,
                   u.name AS user_name, u.profile_pic,
                   c.name AS community_name,
                   (SELECT COUNT(*) FROM post_votes v
                      WHERE v.post_id = p.id AND v.vote_type = 'like')   AS like_count,
                   (SELECT COUNT(*) FROM post_comments pc
                      WHERE pc.post_id = p.id)                           AS comment_count
            FROM posts p
            JOIN users u ON p.user_id = u.id
            JOIN communities c ON p.community_id = c.id
            {where}
            ORDER BY (like_count * 2 + comment_count) DESC, p.created_at DESC
            LIMIT 20
        """)

        # Derive display fields so the template stays simple.
        for p in posts:
            ts = p.get("created_at")
            p["time_label"] = ts.strftime("%b %d, %Y") if hasattr(ts, "strftime") else (str(ts)[:10] if ts else "")
            body = (p.get("content") or "").strip()
            p["snippet"] = (body[:140] + "…") if len(body) > 140 else body
            title = (p.get("title") or "").strip()
            p["title_display"] = title or "Untitled post"
            p["score"] = (p.get("like_count") or 0) * 2 + (p.get("comment_count") or 0)

        # Real top communities (by member count) for the quick-jump pills.
        communities = db.fetch_all("""
            SELECT c.id, c.name,
                   (SELECT COUNT(*) FROM community_members m
                      WHERE m.community_id = c.id) AS member_count
            FROM communities c
            ORDER BY member_count DESC, c.name ASC
            LIMIT 6
        """)
        db.close()

        return render_template(
            "trending.html",
            user_name=user_name,
            posts=posts,
            communities=communities,
            active_range=range_arg,
        )

    def live(self):
        user_name = session.get("user_name") if session.get("user_id") else None
        # Point the "Discuss" buttons at a real Football community when one
        # exists; fall back to the communities directory. Best-effort: a DB
        # hiccup must not stop the live page (which needs no database) rendering.
        football_url = url_for("Home.communities")
        try:
            db = Database()
            row = db.fetch_one(
                "SELECT id FROM communities WHERE name = %s OR category = %s ORDER BY id LIMIT 1",
                ("Football", "Football"),
            )
            db.close()
            if row:
                football_url = url_for("Home.community_detail", community_id=row["id"])
        except Exception:
            pass
        return render_template("live.html", user_name=user_name, football_url=football_url)

    def api_live(self):
        """JSON feed of live World Cup scores (polled by the /live page).

        Acts as a server-side proxy to football-data.org: the browser polls this
        same-origin endpoint, so the API token stays on the server and there is
        no CORS problem. Backed by a process-wide MatchDataManager that caches
        upstream results for 30 seconds, so frequent client polling does not
        exhaust the free-tier rate limit. Always returns 200 with a JSON body;
        upstream problems are reported via the ``source``/``message`` fields
        rather than an error code.
        """
        token = current_app.config.get("FOOTBALL_DATA_TOKEN") or current_app.config.get("API_FOOTBALL_KEY")
        manager = get_match_manager(token=token)
        return jsonify(manager.get_scoreboard())

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
        # Follow graph: people who follow me, and people I follow.
        followers = get_followers(db, user_id)
        following = get_following(db, user_id)
        db.close()
        return render_template(
            "activity_feed.html",
            user=user,
            posts=posts,
            followers=followers,
            following=following,
            follower_count=len(followers),
            following_count=len(following),
            user_name=session.get("user_name"),
        )

    @login_required
    def update_profile(self):
        user_id = session.get("user_id")
        name = request.form.get("name")
        bio = request.form.get("bio")
        profile_pic = request.files.get("profile_pic")
        
        # Active Status toggle: an unchecked checkbox is simply absent from the
        # form, so treat "missing" as off (0) and any present value as on (1).
        show_online = 1 if request.form.get("show_online_status") else 0

        db = Database()
        if name:
            db.execute(
                "UPDATE users SET name = %s, bio = %s, show_online_status = %s WHERE id = %s",
                (name, bio, show_online, user_id),
            )
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
        is_admin = session.get("user_role") == "admin"
        db = Database()
        # Verify ownership, site admin, or a moderator of the post's community
        # (e.g. removing reported/toxic content).
        post = db.fetch_one("SELECT * FROM posts WHERE id = %s", (post_id,))
        can_delete = post and (
            post['user_id'] == user_id
            or is_admin
            or is_community_moderator(db, post['community_id'], user_id)
        )
        if can_delete:
            db.execute("DELETE FROM posts WHERE id = %s", (post_id,))
            flash("Post deleted successfully.", "success")
        else:
            flash("You do not have permission to delete this post.", "danger")
        db.close()
        return redirect(request.referrer or url_for("Home.home"))

    @login_required
    def edit_post(self, post_id):
        user_id = session.get("user_id")
        db = Database()
        post = db.fetch_one("SELECT * FROM posts WHERE id = %s", (post_id,))
        if not post:
            db.close()
            flash("Post not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        if post['user_id'] != user_id:
            db.close()
            flash("You do not have permission to edit this post.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        if request.method == 'POST':
            title = (request.form.get('title') or '').strip()
            content = (request.form.get('content') or '').strip()

            if not title:
                db.close()
                flash("A title is required.", "warning")
                return redirect(url_for('Home.edit_post', post_id=post_id))

            if post['post_type'] == 'text' and not content:
                db.close()
                flash("Please write something in the body of your post.", "warning")
                return redirect(url_for('Home.edit_post', post_id=post_id))

            db.execute(
                "UPDATE posts SET title = %s, content = %s WHERE id = %s",
                (WordCensor.censor_text(title), WordCensor.censor_text(content), post_id),
            )
            db.close()
            flash("Post updated successfully!", "success")
            return redirect(url_for("Home.community_detail", community_id=post['community_id']))

        attach_media_and_poll(db, post, "post", user_id)
        db.close()
        return render_template("edit_post.html", post=post)

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
            (post_id, user_id, WordCensor.censor_text(content)))
        db.close()
        flash("Reply posted!", "success")
        return redirect(request.referrer or url_for("Home.community_detail", community_id=post['community_id']))

    @login_required
    def add_post_note(self, post_id):
        """Attach a community note (crowd-sourced context) to a post."""
        user_id = session.get("user_id")
        content = (request.form.get("content") or "").strip()
        source = (request.form.get("source") or "").strip() or None

        db = Database()
        post = db.fetch_one("SELECT * FROM posts WHERE id = %s", (post_id,))
        if not post:
            db.close()
            flash("Post not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        if not content:
            db.close()
            flash("A community note can't be empty.", "warning")
            return redirect(request.referrer or url_for("Home.community_detail", community_id=post['community_id']))

        db.execute(
            "INSERT INTO post_notes (post_id, user_id, content, source) VALUES (%s, %s, %s, %s)",
            (post_id, user_id, content, source))
        db.close()
        flash("Community note added. It becomes public once enough readers rate it helpful.", "success")
        return redirect(request.referrer or url_for("Home.community_detail", community_id=post['community_id']))

    @login_required
    def rate_post_note(self, note_id):
        """Rate a post's community note helpful/not-helpful (one rating per user).

        Re-clicking the same rating removes it (toggle); the other switches it."""
        user_id = session.get("user_id")
        rating = request.form.get("rating")
        if rating not in ("helpful", "not_helpful"):
            flash("Invalid rating.", "warning")
            return redirect(request.referrer or url_for("Home.home"))

        db = Database()
        note = db.fetch_one("SELECT * FROM post_notes WHERE id = %s", (note_id,))
        if not note:
            db.close()
            flash("Note not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        existing = db.fetch_one(
            "SELECT * FROM post_note_votes WHERE note_id = %s AND user_id = %s",
            (note_id, user_id))
        if existing is None:
            db.execute(
                "INSERT INTO post_note_votes (note_id, user_id, rating) VALUES (%s, %s, %s)",
                (note_id, user_id, rating))
        elif existing['rating'] == rating:
            db.execute("DELETE FROM post_note_votes WHERE id = %s", (existing['id'],))
        else:
            db.execute("UPDATE post_note_votes SET rating = %s WHERE id = %s",
                       (rating, existing['id']))
        db.close()
        return redirect(request.referrer or url_for("Home.home"))

    @login_required
    def report_post(self, post_id):
        """Flag a post for moderator review."""
        user_id = session.get("user_id")
        reason = request.form.get("reason")
        details = (request.form.get("details") or "").strip() or None

        if reason not in REPORT_REASON_VALUES:
            flash("Please choose a reason for your report.", "warning")
            return redirect(request.referrer or url_for("Home.home"))

        db = Database()
        post = db.fetch_one("SELECT * FROM posts WHERE id = %s", (post_id,))
        if not post:
            db.close()
            flash("Post not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        # One report per user per post; re-reporting refreshes the existing row.
        db.execute(
            """
            INSERT INTO post_reports (post_id, user_id, reason, details)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE reason = VALUES(reason),
                                    details = VALUES(details),
                                    status = 'open'
            """,
            (post_id, user_id, reason, details),
        )

        # Alert the moderation team (in-app to every admin + email to admin@admin.com).
        # Best-effort: a notification failure must not undo the recorded report.
        try:
            notify_admins_of_report(
                db,
                "post",
                post.get("title"),
                dict(REPORT_REASONS).get(reason, reason),
                session.get("user_name", "A member"),
                details=details,
                review_url=url_for("Home.admin_reports"),
            )
        except Exception as e:
            print(f"Error notifying admins of post report: {e}")

        db.close()
        flash("Thanks for reporting. Our moderators will review this post.", "success")
        return redirect(request.referrer or url_for("Home.community_detail", community_id=post['community_id']))

    @admin_required
    def admin_reports(self):
        """Moderator queue of open post + thread reports."""
        db = Database()
        post_reports = db.fetch_all("""
            SELECT r.*, u.name AS reporter_name,
                   p.title AS content_title, p.content AS content_body,
                   p.community_id, c.name AS community_name,
                   au.name AS author_name
            FROM post_reports r
            JOIN users u ON r.user_id = u.id
            JOIN posts p ON r.post_id = p.id
            JOIN communities c ON p.community_id = c.id
            JOIN users au ON p.user_id = au.id
            WHERE r.status = 'open'
            ORDER BY r.created_at DESC
        """)
        thread_reports = db.fetch_all("""
            SELECT r.*, u.name AS reporter_name,
                   t.title AS content_title, t.content AS content_body,
                   t.category, t.author AS author_name
            FROM thread_reports r
            JOIN users u ON r.user_id = u.id
            JOIN threads t ON r.thread_id = t.id
            WHERE r.status = 'open'
            ORDER BY r.created_at DESC
        """)
        total_open = len(post_reports) + len(thread_reports)
        db.close()
        return render_template(
            "admin_reports.html",
            post_reports=post_reports,
            thread_reports=thread_reports,
            total_open=total_open,
            reason_labels=dict(REPORT_REASONS),
            user_name=session.get("user_name"),
        )

    @admin_required
    def resolve_post_report(self, report_id):
        """Mark a post report reviewed (dismiss it from the open queue)."""
        db = Database()
        db.execute("UPDATE post_reports SET status = 'reviewed' WHERE id = %s", (report_id,))
        db.close()
        flash("Report dismissed.", "success")
        return redirect(url_for("Home.admin_reports"))

    # ── Per-community moderation panel ─────────────────────────────────────────
    def _require_moderator(self, db, community_id):
        """Guard for community-scoped moderation actions. Returns a redirect
        Response if the current user may not moderate `community_id`, else None."""
        if not session.get("user_id"):
            flash("Please login first.", "warning")
            return redirect(url_for("Auth.login"))
        if not can_moderate_community(db, community_id):
            flash("You don't have permission to moderate this community.", "danger")
            return redirect(url_for("Home.community_detail", community_id=community_id))
        return None

    def community_admin(self, community_id):
        """Per-community moderation dashboard (site admins + appointed mods)."""
        db = Database()
        community = db.fetch_one("SELECT * FROM communities WHERE id = %s", (community_id,))
        if not community:
            db.close()
            return "Community not found", 404

        guard = self._require_moderator(db, community_id)
        if guard:
            db.close()
            return guard

        stats = {
            "members": db.fetch_one("SELECT COUNT(*) AS c FROM community_members WHERE community_id = %s", (community_id,))["c"],
            "posts": db.fetch_one("SELECT COUNT(*) AS c FROM posts WHERE community_id = %s", (community_id,))["c"],
            "moderators": db.fetch_one("SELECT COUNT(*) AS c FROM community_moderators WHERE community_id = %s", (community_id,))["c"],
            "open_reports": db.fetch_one(
                "SELECT COUNT(*) AS c FROM post_reports r JOIN posts p ON r.post_id = p.id "
                "WHERE p.community_id = %s AND r.status = 'open'", (community_id,))["c"],
        }

        # Open reports for posts in this community; hate-speech reports first.
        reported_posts = db.fetch_all("""
            SELECT r.id AS report_id, r.reason, r.details, r.created_at,
                   u.name AS reporter_name,
                   p.id AS post_id, p.title, p.content,
                   au.id AS author_id, au.name AS author_name
            FROM post_reports r
            JOIN posts p ON r.post_id = p.id
            JOIN users u ON r.user_id = u.id
            JOIN users au ON p.user_id = au.id
            WHERE p.community_id = %s AND r.status = 'open'
            ORDER BY (r.reason = 'hate') DESC, r.created_at DESC
        """, (community_id,))

        posts = db.fetch_all("""
            SELECT p.id, p.title, p.created_at, u.id AS author_id, u.name AS author_name,
                   (SELECT COUNT(*) FROM post_reports r WHERE r.post_id = p.id AND r.status = 'open') AS report_count
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.community_id = %s
            ORDER BY p.created_at DESC
            LIMIT 100
        """, (community_id,))

        members = db.fetch_all("""
            SELECT u.id AS user_id, u.name, u.email, u.role AS site_role, cm.joined_at,
                   (SELECT 1 FROM community_moderators m
                    WHERE m.community_id = cm.community_id AND m.user_id = u.id) AS is_moderator
            FROM community_members cm
            JOIN users u ON cm.user_id = u.id
            WHERE cm.community_id = %s
            ORDER BY cm.joined_at ASC
        """, (community_id,))
        for m in members:
            m["is_moderator"] = bool(m["is_moderator"])

        banned = db.fetch_all("""
            SELECT u.id AS user_id, u.name, u.email, b.created_at
            FROM community_bans b
            JOIN users u ON b.user_id = u.id
            WHERE b.community_id = %s
            ORDER BY b.created_at DESC
        """, (community_id,))

        db.close()
        return render_template(
            "community_admin.html",
            community=community,
            stats=stats,
            reported_posts=reported_posts,
            posts=posts,
            members=members,
            banned=banned,
            is_site_admin=(session.get("user_role") == "admin"),
            reason_labels=dict(REPORT_REASONS),
            current_user_id=session.get("user_id"),
            user_name=session.get("user_name"),
        )

    def community_resolve_report(self, community_id, report_id):
        """Dismiss a report on a post in this community (admins + mods)."""
        db = Database()
        guard = self._require_moderator(db, community_id)
        if guard:
            db.close()
            return guard
        # Only resolve if the report really belongs to this community.
        row = db.fetch_one(
            "SELECT r.id FROM post_reports r JOIN posts p ON r.post_id = p.id "
            "WHERE r.id = %s AND p.community_id = %s", (report_id, community_id))
        if row:
            db.execute("UPDATE post_reports SET status = 'reviewed' WHERE id = %s", (report_id,))
            flash("Report dismissed.", "success")
        db.close()
        return redirect(url_for("Home.community_admin", community_id=community_id))

    def ban_member(self, community_id, user_id):
        """Remove a member and block them from rejoining/posting (admins + mods)."""
        db = Database()
        guard = self._require_moderator(db, community_id)
        if guard:
            db.close()
            return guard

        actor_id = session.get("user_id")
        target = db.fetch_one("SELECT id, name, role FROM users WHERE id = %s", (user_id,))
        if not target:
            db.close()
            flash("User not found.", "danger")
            return redirect(url_for("Home.community_admin", community_id=community_id))
        if user_id == actor_id:
            db.close()
            flash("You can't ban yourself.", "warning")
            return redirect(url_for("Home.community_admin", community_id=community_id))
        if target["role"] == "admin" or is_community_moderator(db, community_id, user_id):
            db.close()
            flash("You can't ban a site admin or a community moderator.", "danger")
            return redirect(url_for("Home.community_admin", community_id=community_id))

        db.execute("DELETE FROM community_members WHERE community_id = %s AND user_id = %s", (community_id, user_id))
        db.execute(
            "INSERT INTO community_bans (community_id, user_id, banned_by) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE banned_by = VALUES(banned_by)",
            (community_id, user_id, actor_id))
        db.close()
        flash(f"{target['name']} has been banned from this community.", "success")
        return redirect(url_for("Home.community_admin", community_id=community_id))

    def unban_member(self, community_id, user_id):
        """Lift a ban so the user may rejoin (admins + mods)."""
        db = Database()
        guard = self._require_moderator(db, community_id)
        if guard:
            db.close()
            return guard
        db.execute("DELETE FROM community_bans WHERE community_id = %s AND user_id = %s", (community_id, user_id))
        db.close()
        flash("Ban lifted.", "success")
        return redirect(url_for("Home.community_admin", community_id=community_id))

    @admin_required
    def add_moderator(self, community_id, user_id):
        """Appoint a community moderator (site admins only)."""
        db = Database()
        community = db.fetch_one("SELECT id FROM communities WHERE id = %s", (community_id,))
        target = db.fetch_one("SELECT id, name FROM users WHERE id = %s", (user_id,))
        if not community or not target:
            db.close()
            flash("Community or user not found.", "danger")
            return redirect(url_for("Home.community_admin", community_id=community_id))

        # A moderator should be a member and must not be banned.
        db.execute("DELETE FROM community_bans WHERE community_id = %s AND user_id = %s", (community_id, user_id))
        already_member = db.fetch_one(
            "SELECT 1 FROM community_members WHERE community_id = %s AND user_id = %s", (community_id, user_id))
        if not already_member:
            db.execute("INSERT INTO community_members (user_id, community_id) VALUES (%s, %s)", (user_id, community_id))
        db.execute(
            "INSERT IGNORE INTO community_moderators (community_id, user_id, appointed_by) VALUES (%s, %s, %s)",
            (community_id, user_id, session.get("user_id")))
        db.close()
        flash(f"{target['name']} is now a moderator of this community.", "success")
        return redirect(url_for("Home.community_admin", community_id=community_id))

    @admin_required
    def remove_moderator(self, community_id, user_id):
        """Revoke a community moderator (site admins only)."""
        db = Database()
        db.execute(
            "DELETE FROM community_moderators WHERE community_id = %s AND user_id = %s",
            (community_id, user_id))
        db.close()
        flash("Moderator removed.", "success")
        return redirect(url_for("Home.community_admin", community_id=community_id))

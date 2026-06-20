from flask import (
    Blueprint, render_template, session, request, redirect, url_for, flash,
)
from app.models.database import Database
from app.auth import login_required
from app.follows import (
    is_following, are_mutual_followers, follower_count, following_count,
    get_followers, get_following,
)
from app.blocks import is_blocked, has_block_between, get_blocked_users
from app.notifications import create_notification


class UserRoutes:
    """Public user profiles and the follow / unfollow actions.

    A profile shows the user's posts plus their followers and following lists
    (Instagram-style tabs). Following is instant — clicking Follow immediately
    creates the relationship. When two users follow each other a "Message"
    shortcut appears, since mutual follows are what unlock chat (ChatRoutes).
    """

    def __init__(self):
        self.bp = Blueprint("User", __name__)

    def register(self):
        self.bp.route("/user/<int:user_id>", methods=["GET"])(self.profile)
        self.bp.route("/user/<int:user_id>/follow", methods=["POST"])(self.follow)
        self.bp.route("/user/<int:user_id>/unfollow", methods=["POST"])(self.unfollow)
        self.bp.route("/user/<int:user_id>/block", methods=["POST"])(self.block)
        self.bp.route("/user/<int:user_id>/unblock", methods=["POST"])(self.unblock)
        self.bp.route("/blocked", methods=["GET"])(self.blocked_list)
        return self.bp

    def profile(self, user_id):
        viewer_id = session.get("user_id")
        # Viewing your own /user/<id> just sends you to the editable profile.
        if viewer_id and viewer_id == user_id:
            return redirect(url_for("Home.profile"))

        db = Database()
        user = db.fetch_one(
            "SELECT id, name, bio, profile_pic, created_at FROM users WHERE id = %s",
            (user_id,),
        )
        if not user:
            db.close()
            flash("User not found.", "danger")
            return redirect(url_for("Home.home"))

        posts = db.fetch_all(
            """
            SELECT p.*, c.name AS community_name
            FROM posts p
            JOIN communities c ON p.community_id = c.id
            WHERE p.user_id = %s
            ORDER BY p.created_at DESC
            """,
            (user_id,),
        )

        followers = get_followers(db, user_id)
        following = get_following(db, user_id)
        viewer_follows = is_following(db, viewer_id, user_id) if viewer_id else False
        is_mutual = are_mutual_followers(db, viewer_id, user_id) if viewer_id else False
        # Block state: did the viewer block this profile, and is there a block
        # in either direction (which hides Follow/Message entirely)?
        viewer_blocked = is_blocked(db, viewer_id, user_id) if viewer_id else False
        block_between = has_block_between(db, viewer_id, user_id) if viewer_id else False
        db.close()

        return render_template(
            "user_profile.html",
            profile_user=user,
            posts=posts,
            followers=followers,
            following=following,
            follower_count=len(followers),
            following_count=len(following),
            viewer_follows=viewer_follows,
            is_mutual=is_mutual,
            viewer_blocked=viewer_blocked,
            block_between=block_between,
            user_name=session.get("user_name"),
        )

    @login_required
    def follow(self, user_id):
        follower_id = session.get("user_id")
        if user_id == follower_id:
            flash("You can't follow yourself.", "warning")
            return redirect(request.referrer or url_for("Home.home"))

        db = Database()
        target = db.fetch_one("SELECT id, name FROM users WHERE id = %s", (user_id,))
        if not target:
            db.close()
            flash("User not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        # A block in either direction prevents following.
        if has_block_between(db, follower_id, user_id):
            db.close()
            flash("You can't follow this user.", "warning")
            return redirect(request.referrer or url_for("User.profile", user_id=user_id))

        # INSERT IGNORE so re-clicking Follow is a harmless no-op (unique key).
        db.execute(
            "INSERT IGNORE INTO user_follows (follower_id, followee_id) VALUES (%s, %s)",
            (follower_id, user_id),
        )
        
        # Create a notification for the followed user
        follower = db.fetch_one("SELECT id, name FROM users WHERE id = %s", (follower_id,))
        if follower:
            try:
                create_notification(
                    db,
                    user_id,
                    "follow",
                    f"{follower['name']} started following you",
                    url=url_for("User.profile", user_id=follower_id),
                    actor_id=follower_id
                )
            except Exception as e:
                print(f"Error creating follow notification: {e}")
        
        mutual = are_mutual_followers(db, follower_id, user_id)
        db.close()
        if mutual:
            flash(f"You and {target['name']} now follow each other — you can chat!", "success")
        else:
            flash(f"You are now following {target['name']}.", "success")
        return redirect(request.referrer or url_for("User.profile", user_id=user_id))

    @login_required
    def unfollow(self, user_id):
        follower_id = session.get("user_id")
        db = Database()
        db.execute(
            "DELETE FROM user_follows WHERE follower_id = %s AND followee_id = %s",
            (follower_id, user_id),
        )
        db.close()
        flash("Unfollowed.", "info")
        return redirect(request.referrer or url_for("User.profile", user_id=user_id))

    @login_required
    def block(self, user_id):
        """Block another user. Severs follows in both directions and stops any
        future follow / message / chat between the two accounts."""
        blocker_id = session.get("user_id")
        if user_id == blocker_id:
            flash("You can't block yourself.", "warning")
            return redirect(request.referrer or url_for("Home.home"))

        db = Database()
        target = db.fetch_one("SELECT id, name FROM users WHERE id = %s", (user_id,))
        if not target:
            db.close()
            flash("User not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        # Record the block (idempotent), then remove any follow either way.
        db.execute(
            "INSERT IGNORE INTO user_blocks (blocker_id, blocked_id) VALUES (%s, %s)",
            (blocker_id, user_id),
        )
        db.execute(
            """
            DELETE FROM user_follows
            WHERE (follower_id = %s AND followee_id = %s)
               OR (follower_id = %s AND followee_id = %s)
            """,
            (blocker_id, user_id, user_id, blocker_id),
        )
        db.close()
        flash(f"You blocked {target['name']}. They can no longer follow or message you.", "success")
        return redirect(request.referrer or url_for("User.profile", user_id=user_id))

    @login_required
    def unblock(self, user_id):
        """Lift a block. Does not restore the previous follow relationship."""
        blocker_id = session.get("user_id")
        db = Database()
        target = db.fetch_one("SELECT id, name FROM users WHERE id = %s", (user_id,))
        db.execute(
            "DELETE FROM user_blocks WHERE blocker_id = %s AND blocked_id = %s",
            (blocker_id, user_id),
        )
        db.close()
        flash(f"You unblocked {target['name']}." if target else "User unblocked.", "info")
        return redirect(request.referrer or url_for("User.profile", user_id=user_id))

    @login_required
    def blocked_list(self):
        """Manage blocked accounts: list everyone the current user has blocked."""
        user_id = session.get("user_id")
        db = Database()
        blocked = get_blocked_users(db, user_id)
        db.close()
        return render_template(
            "blocked_users.html",
            blocked=blocked,
            user_name=session.get("user_name"),
        )

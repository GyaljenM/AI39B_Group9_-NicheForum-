from flask import (
    Blueprint, render_template, session, request, redirect, url_for,
    flash, jsonify,
)
from app.models.database import Database
from app.auth import login_required
from app.follows import are_mutual_followers
from app.blocks import has_block_between
from app.notifications import create_notification
from app.utils.word_censor import WordCensor


class ChatRoutes:
    """1-to-1 direct-message chat between mutual followers.

    Chat is gated on the follow graph: you can only open a conversation with
    someone you BOTH follow (see app/follows.py). The left-hand chat tab lists
    only those mutual followers. Selecting one opens a private conversation.
    Clicking the other person's profile reveals only the communities BOTH users
    have joined, plus "Live match" and "Create thread" shortcuts that share a
    card (link) for one of YOUR joined communities into the conversation.
    """

    def __init__(self):
        self.bp = Blueprint("Chat", __name__)

    def register(self):
        self.bp.route("/chat", methods=["GET"])(self.chat_home)
        self.bp.route("/chat/<int:other_id>", methods=["GET"])(self.conversation)
        self.bp.route("/chat/<int:other_id>/send", methods=["POST"])(self.send_message)
        self.bp.route("/chat/<int:other_id>/share", methods=["POST"])(self.share_card)
        self.bp.route("/chat/<int:other_id>/messages", methods=["GET"])(self.poll_messages)
        return self.bp

    # ── Helpers ────────────────────────────────────────────────────────────
    def _conversation_list(self, db, user_id):
        """Mutual followers only, most recently messaged surfaced first.

        A user appears here only if they and the current user follow each other
        — that's the chat eligibility rule enforced across all the chat views.
        """
        return db.fetch_all(
            """
            SELECT u.id, u.name, u.profile_pic, u.show_online_status,
                   (SELECT MAX(dm.created_at) FROM direct_messages dm
                    WHERE (dm.sender_id = u.id AND dm.receiver_id = %s)
                       OR (dm.sender_id = %s AND dm.receiver_id = u.id)) AS last_at
            FROM users u
            JOIN user_follows f1 ON f1.follower_id = %s AND f1.followee_id = u.id
            JOIN user_follows f2 ON f2.follower_id = u.id AND f2.followee_id = %s
            WHERE u.id != %s
            ORDER BY last_at IS NULL, last_at DESC, u.name ASC
            """,
            (user_id, user_id, user_id, user_id, user_id),
        )

    def _fetch_messages(self, db, user_id, other_id):
        return db.fetch_all(
            """
            SELECT * FROM direct_messages
            WHERE (sender_id = %s AND receiver_id = %s)
               OR (sender_id = %s AND receiver_id = %s)
            ORDER BY created_at ASC, id ASC
            """,
            (user_id, other_id, other_id, user_id),
        )

    def _mutual_communities(self, db, user_id, other_id):
        """Communities that BOTH users have joined."""
        return db.fetch_all(
            """
            SELECT c.id, c.name, c.description
            FROM communities c
            JOIN community_members m1 ON m1.community_id = c.id AND m1.user_id = %s
            JOIN community_members m2 ON m2.community_id = c.id AND m2.user_id = %s
            ORDER BY c.name ASC
            """,
            (user_id, other_id),
        )

    def _my_communities(self, db, user_id):
        """Communities the current user has joined (for the share shortcuts)."""
        return db.fetch_all(
            """
            SELECT c.id, c.name
            FROM communities c
            JOIN community_members m ON m.community_id = c.id
            WHERE m.user_id = %s
            ORDER BY c.name ASC
            """,
            (user_id,),
        )

    # ── Views ──────────────────────────────────────────────────────────────
    @login_required
    def chat_home(self):
        """Chat landing: user list with no conversation selected yet."""
        user_id = session.get("user_id")
        db = Database()
        conversations = self._conversation_list(db, user_id)
        my_communities = self._my_communities(db, user_id)
        db.close()
        return render_template(
            "chat.html",
            conversations=conversations,
            other=None,
            messages=[],
            mutual_communities=[],
            my_communities=my_communities,
            user_name=session.get("user_name"),
        )

    @login_required
    def conversation(self, other_id):
        user_id = session.get("user_id")
        if other_id == user_id:
            flash("You can't open a chat with yourself.", "warning")
            return redirect(url_for("Chat.chat_home"))

        db = Database()
        other = db.fetch_one("SELECT id, name, profile_pic, bio, show_online_status FROM users WHERE id = %s", (other_id,))
        if not other:
            db.close()
            flash("User not found.", "danger")
            return redirect(url_for("Chat.chat_home"))

        # A block in either direction closes the conversation.
        if has_block_between(db, user_id, other_id):
            db.close()
            flash("You can't chat with this user.", "warning")
            return redirect(url_for("Chat.chat_home"))

        # Chat is restricted to mutual followers.
        if not are_mutual_followers(db, user_id, other_id):
            db.close()
            flash("You can only chat with people you both follow.", "warning")
            return redirect(url_for("User.profile", user_id=other_id))

        conversations = self._conversation_list(db, user_id)
        messages = self._fetch_messages(db, user_id, other_id)
        mutual_communities = self._mutual_communities(db, user_id, other_id)
        my_communities = self._my_communities(db, user_id)
        db.close()
        return render_template(
            "chat.html",
            conversations=conversations,
            other=other,
            messages=messages,
            mutual_communities=mutual_communities,
            my_communities=my_communities,
            user_name=session.get("user_name"),
        )

    @login_required
    def send_message(self, other_id):
        user_id = session.get("user_id")
        content = (request.form.get("content") or "").strip()

        db = Database()
        other = db.fetch_one("SELECT id, name FROM users WHERE id = %s", (other_id,))
        if not other or other_id == user_id:
            db.close()
            flash("Invalid conversation.", "danger")
            return redirect(url_for("Chat.chat_home"))

        if has_block_between(db, user_id, other_id):
            db.close()
            flash("You can't message this user.", "warning")
            return redirect(url_for("Chat.chat_home"))

        if not are_mutual_followers(db, user_id, other_id):
            db.close()
            flash("You can only chat with people you both follow.", "warning")
            return redirect(url_for("User.profile", user_id=other_id))

        if not content:
            db.close()
            return redirect(url_for("Chat.conversation", other_id=other_id))

        db.execute(
            "INSERT INTO direct_messages (sender_id, receiver_id, content) VALUES (%s, %s, %s)",
            (user_id, other_id, WordCensor.censor_text(content)),
        )
        
        # Create a notification for the message receiver
        sender = db.fetch_one("SELECT id, name FROM users WHERE id = %s", (user_id,))
        if sender:
            try:
                create_notification(
                    db,
                    other_id,
                    "message",
                    f"{sender['name']} sent you a message",
                    url=url_for("Chat.conversation", other_id=user_id),
                    actor_id=user_id
                )
            except Exception as e:
                print(f"Error creating message notification: {e}")
        
        db.close()
        return redirect(url_for("Chat.conversation", other_id=other_id))

    @login_required
    def share_card(self, other_id):
        """Share a community-linked card (live match or create thread) into the
        conversation. `share_type` is 'live' or 'thread'; `community_id` must be
        one the current user has joined."""
        user_id = session.get("user_id")
        share_type = request.form.get("share_type")
        community_id = request.form.get("community_id")

        if share_type not in ("live", "thread"):
            flash("Unknown share type.", "warning")
            return redirect(url_for("Chat.conversation", other_id=other_id))

        db = Database()
        other = db.fetch_one("SELECT id FROM users WHERE id = %s", (other_id,))
        if not other or other_id == user_id:
            db.close()
            flash("Invalid conversation.", "danger")
            return redirect(url_for("Chat.chat_home"))

        if has_block_between(db, user_id, other_id):
            db.close()
            flash("You can't message this user.", "warning")
            return redirect(url_for("Chat.chat_home"))

        if not are_mutual_followers(db, user_id, other_id):
            db.close()
            flash("You can only chat with people you both follow.", "warning")
            return redirect(url_for("User.profile", user_id=other_id))

        # The shared community must be one the sender actually joined.
        community = db.fetch_one(
            """
            SELECT c.id, c.name
            FROM communities c
            JOIN community_members m ON m.community_id = c.id AND m.user_id = %s
            WHERE c.id = %s
            """,
            (user_id, community_id),
        )
        if not community:
            db.close()
            flash("Pick one of the communities you've joined to share.", "warning")
            return redirect(url_for("Chat.conversation", other_id=other_id))

        if share_type == "live":
            label = f"Live match in c/{community['name']}"
            url = url_for("Home.live")
        else:
            label = f"Create a thread in c/{community['name']}"
            url = url_for("Home.community_detail", community_id=community["id"])

        db.execute(
            """
            INSERT INTO direct_messages
                (sender_id, receiver_id, content, share_type, share_label, share_url)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, other_id, None, share_type, label, url),
        )
        
        # Create a notification for the shared card
        sender = db.fetch_one("SELECT id, name FROM users WHERE id = %s", (user_id,))
        if sender:
            try:
                create_notification(
                    db,
                    other_id,
                    "message",
                    f"{sender['name']} shared: {label}",
                    url=url_for("Chat.conversation", other_id=user_id),
                    actor_id=user_id
                )
            except Exception as e:
                print(f"Error creating share notification: {e}")
        
        db.close()
        return redirect(url_for("Chat.conversation", other_id=other_id))

    @login_required
    def poll_messages(self, other_id):
        """JSON feed of the conversation, used by the auto-refresh poller."""
        user_id = session.get("user_id")
        db = Database()
        rows = self._fetch_messages(db, user_id, other_id)
        db.close()
        messages = [
            {
                "id": r["id"],
                "mine": r["sender_id"] == user_id,
                "content": r["content"],
                "share_type": r["share_type"],
                "share_label": r["share_label"],
                "share_url": r["share_url"],
                "created_at": r["created_at"].strftime("%H:%M") if r["created_at"] else "",
            }
            for r in rows
        ]
        return jsonify(messages=messages)

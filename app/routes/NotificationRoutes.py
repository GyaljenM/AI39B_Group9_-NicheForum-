"""In-app notification views.

Three endpoints back the bell in the top nav:
    GET  /notifications            full page list (also marks everything read)
    GET  /notifications/feed       JSON {count, items} for the dropdown + badge
    POST /notifications/mark-read  mark all read, returns the new count

The feed endpoint is polled by a small script in base.html so the unread badge
stays live without a page reload, mirroring the chat poller pattern.
"""

from flask import Blueprint, render_template, session, jsonify
from app.models.database import Database
from app.auth import login_required
from app.notifications import (
    get_notifications, unread_count, mark_all_read,
)


class NotificationRoutes:
    def __init__(self):
        self.bp = Blueprint("Notification", __name__)

    def register(self):
        self.bp.route("/notifications", methods=["GET"])(self.list_page)
        self.bp.route("/notifications/feed", methods=["GET"])(self.feed)
        self.bp.route("/notifications/mark-read", methods=["POST"])(self.mark_read)
        return self.bp

    @login_required
    def list_page(self):
        """Full-page history. Opening it clears the unread badge."""
        user_id = session.get("user_id")
        db = Database()
        notifications = get_notifications(db, user_id, limit=50)
        mark_all_read(db, user_id)
        db.close()
        return render_template(
            "notifications.html",
            notifications=notifications,
            user_name=session.get("user_name"),
        )

    @login_required
    def feed(self):
        """JSON feed for the dropdown + badge poller (recent 15, plus count)."""
        user_id = session.get("user_id")
        db = Database()
        rows = get_notifications(db, user_id, limit=15)
        count = unread_count(db, user_id)
        db.close()
        items = [
            {
                "id": r["id"],
                "type": r["type"],
                "message": r["message"],
                "url": r["url"],
                "is_read": bool(r["is_read"]),
                "actor_name": r["actor_name"],
                "actor_pic": r["actor_pic"],
                "created_at": r["created_at"].strftime("%b %d, %H:%M") if r["created_at"] else "",
            }
            for r in rows
        ]
        return jsonify(count=count, items=items)

    @login_required
    def mark_read(self):
        """Mark all notifications read (called when the dropdown is opened)."""
        user_id = session.get("user_id")
        db = Database()
        mark_all_read(db, user_id)
        db.close()
        return jsonify(count=0)

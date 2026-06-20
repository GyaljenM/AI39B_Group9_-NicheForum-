"""In-app notification helpers (notifications table).

Every alert is one row addressed to a single recipient (``user_id``). The rest
of the app creates notifications through these helpers so the insert shape and
the "never notify yourself" rule live in one place.

Like app/follows.py, each helper takes an already-open ``Database`` instance so
callers keep control of the connection lifecycle. Notifications are best-effort:
failing to create one must never break the action that triggered it, so the
route-level event hooks wrap these calls in try/except.

Notification types (drives the icon in the UI):
    'follow'          someone started following you
    'message'         someone sent you a direct message
    'community_post'  a new post in a community you're a member of
    'comment'         someone replied to your post
"""


def create_notification(db, user_id, type, message, url=None, actor_id=None):
    """Insert a single notification for ``user_id``.

    No-ops when there is no recipient or when the actor is the recipient (you
    never get notified about your own actions). Returns True if a row was
    written.
    """
    if not user_id:
        return False
    if actor_id and actor_id == user_id:
        return False
    db.execute(
        """
        INSERT INTO notifications (user_id, actor_id, type, message, url)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, actor_id, type, message, url),
    )
    return True


def notify_community_members(db, community_id, type, message, url=None, actor_id=None):
    """Fan a notification out to every member of a community.

    The actor (``actor_id``) is skipped so the poster doesn't get notified about
    their own post. Used when a new post lands in a community.
    """
    members = db.fetch_all(
        "SELECT user_id FROM community_members WHERE community_id = %s",
        (community_id,),
    )
    for m in members:
        if actor_id and m["user_id"] == actor_id:
            continue
        create_notification(
            db, m["user_id"], type, message, url=url, actor_id=actor_id
        )


# The moderation inbox. The default admin account seeded in
# Database.create_tables() owns this address; reports are emailed and sent
# in-app here so moderators see them whether or not email is configured.
ADMIN_EMAIL = "admin@admin.com"


def notify_admins_of_report(db, content_kind, content_title, reason_label,
                            reporter_name, details=None, review_url=None):
    """Alert moderators that content was reported: an in-app notification to
    every admin account plus a best-effort email to ADMIN_EMAIL.

    Best-effort by contract — callers wrap this in try/except so a failure here
    never blocks the report from being recorded. Returns True if at least the
    in-app notification step ran.
    """
    kind = "post" if content_kind == "post" else "thread"
    title = content_title or f"(untitled {kind})"
    message = f"{reporter_name} reported a {kind}: “{title}” ({reason_label})"

    # In-app notification to each admin account (this is what reliably reaches
    # admin@admin.com, which is a real user row).
    admins = db.fetch_all("SELECT id FROM users WHERE role = 'admin'")
    for a in admins:
        create_notification(db, a["id"], "report", message, url=review_url)

    # Best-effort email to the moderation inbox.
    try:
        from app.utils.email_utils import EmailService
        EmailService.send_report_notification(
            ADMIN_EMAIL, kind, title, reason_label, reporter_name,
            details=details, review_url=review_url,
        )
    except Exception as e:
        print(f"DEBUG: could not email report notification: {e}")

    return True


def unread_count(db, user_id):
    """How many unread notifications ``user_id`` has (0 when logged out)."""
    if not user_id:
        return 0
    row = db.fetch_one(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s AND is_read = 0",
        (user_id,),
    )
    return row["c"] if row else 0


def get_notifications(db, user_id, limit=20):
    """Most-recent notifications for ``user_id`` with the actor's name/avatar."""
    if not user_id:
        return []
    return db.fetch_all(
        """
        SELECT n.id, n.type, n.message, n.url, n.is_read, n.created_at,
               n.actor_id, u.name AS actor_name, u.profile_pic AS actor_pic
        FROM notifications n
        LEFT JOIN users u ON u.id = n.actor_id
        WHERE n.user_id = %s
        ORDER BY n.created_at DESC, n.id DESC
        LIMIT %s
        """,
        (user_id, int(limit)),
    )


def mark_all_read(db, user_id):
    """Mark every unread notification for ``user_id`` as read."""
    if not user_id:
        return
    db.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = %s AND is_read = 0",
        (user_id,),
    )

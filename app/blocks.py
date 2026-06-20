"""Helpers for user blocking (user_blocks table).

A block is directed — ``blocker_id`` blocks ``blocked_id`` — but it is enforced
mutually: if *either* user has blocked the other, they can't follow, message, or
chat. Blocking also severs any existing follow in both directions (done in the
block route, see app/routes/UserRoutes.py).

Like app/follows.py, every helper takes an already-open ``Database`` instance so
callers keep control of the connection lifecycle.
"""


def is_blocked(db, blocker_id, blocked_id):
    """True if ``blocker_id`` has blocked ``blocked_id`` (one direction)."""
    if not blocker_id or not blocked_id:
        return False
    row = db.fetch_one(
        "SELECT 1 FROM user_blocks WHERE blocker_id = %s AND blocked_id = %s",
        (blocker_id, blocked_id),
    )
    return row is not None


def has_block_between(db, user_a, user_b):
    """True if either user has blocked the other (the gate for all interaction)."""
    if not user_a or not user_b:
        return False
    row = db.fetch_one(
        """
        SELECT 1 FROM user_blocks
        WHERE (blocker_id = %s AND blocked_id = %s)
           OR (blocker_id = %s AND blocked_id = %s)
        """,
        (user_a, user_b, user_b, user_a),
    )
    return row is not None


def blocked_ids(db, blocker_id):
    """Set of user ids that ``blocker_id`` has blocked — handy for filtering
    people out of lists (search, suggestions)."""
    if not blocker_id:
        return set()
    rows = db.fetch_all(
        "SELECT blocked_id FROM user_blocks WHERE blocker_id = %s", (blocker_id,)
    )
    return {r["blocked_id"] for r in rows}


def get_blocked_users(db, user_id):
    """User rows (id, name, profile_pic, bio, blocked-at) for everyone
    ``user_id`` has blocked — most recently blocked first."""
    return db.fetch_all(
        """
        SELECT u.id, u.name, u.profile_pic, u.bio, b.created_at
        FROM user_blocks b
        JOIN users u ON u.id = b.blocked_id
        WHERE b.blocker_id = %s
        ORDER BY b.created_at DESC
        """,
        (user_id,),
    )

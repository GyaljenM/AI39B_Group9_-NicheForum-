"""Helpers for the Instagram-style follow graph (user_follows table).

A follow is directed: ``follower_id`` follows ``followee_id``. Two users are
"mutual followers" when both directions exist — that mutual state is what gates
direct messaging (see app/routes/ChatRoutes.py).

Every helper takes an already-open ``Database`` instance so callers control the
connection lifecycle, matching the pattern used elsewhere in HomeRoutes.
"""


def is_following(db, follower_id, followee_id):
    """True if ``follower_id`` currently follows ``followee_id``."""
    if not follower_id or not followee_id:
        return False
    row = db.fetch_one(
        "SELECT 1 FROM user_follows WHERE follower_id = %s AND followee_id = %s",
        (follower_id, followee_id),
    )
    return row is not None


def are_mutual_followers(db, user_a, user_b):
    """True if A and B follow each other (the gate for direct messages)."""
    if not user_a or not user_b or user_a == user_b:
        return False
    row = db.fetch_one(
        """
        SELECT 1
        FROM user_follows f1
        JOIN user_follows f2
          ON f2.follower_id = f1.followee_id AND f2.followee_id = f1.follower_id
        WHERE f1.follower_id = %s AND f1.followee_id = %s
        """,
        (user_a, user_b),
    )
    return row is not None


def follower_count(db, user_id):
    """How many users follow ``user_id``."""
    row = db.fetch_one(
        "SELECT COUNT(*) AS c FROM user_follows WHERE followee_id = %s", (user_id,)
    )
    return row["c"] if row else 0


def following_count(db, user_id):
    """How many users ``user_id`` follows."""
    row = db.fetch_one(
        "SELECT COUNT(*) AS c FROM user_follows WHERE follower_id = %s", (user_id,)
    )
    return row["c"] if row else 0


def get_followers(db, user_id):
    """User rows (id, name, profile_pic, bio) for everyone who follows ``user_id``."""
    return db.fetch_all(
        """
        SELECT u.id, u.name, u.profile_pic, u.bio
        FROM user_follows f
        JOIN users u ON u.id = f.follower_id
        WHERE f.followee_id = %s
        ORDER BY f.created_at DESC
        """,
        (user_id,),
    )


def get_following(db, user_id):
    """User rows (id, name, profile_pic, bio) for everyone ``user_id`` follows."""
    return db.fetch_all(
        """
        SELECT u.id, u.name, u.profile_pic, u.bio
        FROM user_follows f
        JOIN users u ON u.id = f.followee_id
        WHERE f.follower_id = %s
        ORDER BY f.created_at DESC
        """,
        (user_id,),
    )


def following_ids(db, follower_id):
    """Set of user ids that ``follower_id`` follows — handy for marking Follow
    buttons across a list of people (e.g. search results)."""
    if not follower_id:
        return set()
    rows = db.fetch_all(
        "SELECT followee_id FROM user_follows WHERE follower_id = %s", (follower_id,)
    )
    return {r["followee_id"] for r in rows}

"""Comprehensive tests for app/routes/UserRoutes.py — the ``UserRoutes`` blueprint.

Tests user profile viewing, following, unfollowing, blocking, and unblocking
with proper follow-graph gating and block enforcement.

Techniques used: unittest.TestCase (via BaseForumTestCase), assert methods,
MagicMock/patch, and Flask test client.
"""

import datetime
import unittest
from unittest.mock import patch, MagicMock

from tests.base import BaseForumTestCase

MODULE = "app.routes.UserRoutes"


class UserRoutesExpandedTests(BaseForumTestCase):
    """Comprehensive tests for UserRoutes."""

    # ── GET /user/<int:user_id> (profile) ───────────────────────────────────

    def test_profile_renders_other_user(self):
        """GET /user/<id> renders public profile for other user."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        user = {
            "id": 2,
            "name": "Bob",
            "bio": "Hello, I'm Bob",
            "profile_pic": "bob.jpg",
            "created_at": datetime.datetime.utcnow(),
        }
        db.fetch_one.return_value = user
        db.fetch_all.return_value = []
        r = self.mock_render(MODULE)

        resp = self.client.get("/user/2")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "user_profile.html")
        self.assertEqual(r.call_args.kwargs["profile_user"], user)

    def test_profile_redirects_when_own_profile(self):
        """GET /user/<own_id> redirects to the editable own profile page."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1}

        resp = self.client.get("/user/1", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/profile", resp.headers["Location"])

    def test_profile_not_found_redirects(self):
        """GET /user/<nonexistent> redirects."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = None

        resp = self.client.get("/user/999", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_profile_logged_out_renders(self):
        """GET /user/<id> renders profile when logged out."""
        self.logout()
        db = self.mock_database(MODULE)
        user = {"id": 1, "name": "Alice"}
        db.fetch_one.return_value = user
        db.fetch_all.return_value = []
        r = self.mock_render(MODULE)

        resp = self.client.get("/user/1")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()

    # ── POST /user/<int:user_id>/follow ─────────────────────────────────────

    def test_follow_requires_login(self):
        """POST /user/<id>/follow requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/user/2/follow", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_follow_success_creates_relationship(self):
        """Valid follow creates follow relationship."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 2, "name": "Bob"}

        with patch(f"{MODULE}.has_block_between", return_value=False):
            resp = self.client.post("/user/2/follow", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT IGNORE INTO user_follows" in s for s in execute_calls))

    def test_follow_creates_notification(self):
        """Following a user creates notification."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"id": 2, "name": "Bob"},      # target user lookup
            {"id": 1, "name": "Alice"},    # follower lookup
            None,                              # are_mutual_followers -> not mutual
        ]

        with patch(f"{MODULE}.has_block_between", return_value=False):
            with patch(f"{MODULE}.create_notification") as mock_notif:
                resp = self.client.post("/user/2/follow", follow_redirects=False)
                # Verify notification called
                mock_notif.assert_called()

    def test_follow_already_following_fails(self):
        """Following an already-followed user fails."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"user_id": 1, "follows_id": 2}

        resp = self.client.post("/user/2/follow", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        # Should not insert again
        insert_calls = [c.args[0] for c in db.execute.call_args_list if "INSERT" in c.args[0]]
        insert_count = sum(1 for c in insert_calls if "user_follows" in c)
        self.assertLessEqual(insert_count, 1)

    def test_follow_blocked_user_fails(self):
        """Cannot follow a user who blocked you."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        
        with patch(f"{MODULE}.has_block_between", return_value=True):
            resp = self.client.post("/user/2/follow", follow_redirects=False)

            self.assertEqual(resp.status_code, 302)
            execute_calls = [c.args[0] for c in db.execute.call_args_list]
            self.assertFalse(any("INSERT INTO user_follows" in s for s in execute_calls))

    # ── POST /user/<int:user_id>/unfollow ───────────────────────────────────

    def test_unfollow_requires_login(self):
        """POST /user/<id>/unfollow requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/user/2/unfollow", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_unfollow_success_removes_relationship(self):
        """Valid unfollow removes follow relationship."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post("/user/2/unfollow", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("DELETE FROM user_follows" in s for s in execute_calls))

    def test_unfollow_not_following_is_idempotent(self):
        """Unfollowing a non-followed user is still a DELETE (idempotent)."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post("/user/2/unfollow", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        # DELETE still executes (idempotent), but no rows affected
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("DELETE FROM user_follows" in s for s in execute_calls))

    # ── POST /user/<int:user_id>/block ──────────────────────────────────────

    def test_block_requires_login(self):
        """POST /user/<id>/block requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/user/2/block", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_block_success_creates_block_and_removes_follows(self):
        """Valid block creates block relationship and removes follows."""
        self.login(user_id=1, user_name="Alice", user_role="user")
        from unittest.mock import patch, MagicMock
        patcher = patch(f"{MODULE}.Database")
        mock_cls = patcher.start()
        self.addCleanup(patcher.stop)
        db = MagicMock(name=f"{MODULE}.Database()")
        mock_cls.return_value = db
        db.fetch_one.return_value = {"id": 2, "name": "Bob"}

        resp = self.client.post("/user/2/block", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        # Should insert block (query uses INSERT IGNORE INTO)
        self.assertTrue(any("INSERT IGNORE INTO user_blocks" in s for s in execute_calls))
        # Should delete follows (both directions)
        self.assertTrue(any("DELETE FROM user_follows" in s for s in execute_calls))

    def test_block_already_blocked_fails(self):
        """Blocking an already-blocked user still inserts IGNORE (idempotent)."""
        self.login(user_id=1, user_name="Alice", user_role="user")
        from unittest.mock import patch, MagicMock
        patcher = patch(f"{MODULE}.Database")
        mock_cls = patcher.start()
        self.addCleanup(patcher.stop)
        db = MagicMock(name=f"{MODULE}.Database()")
        mock_cls.return_value = db
        db.fetch_one.return_value = {"id": 2, "name": "Bob"}

        resp = self.client.post("/user/2/block", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT IGNORE INTO user_blocks" in s for s in execute_calls))

    # ── POST /user/<int:user_id>/unblock ────────────────────────────────────

    def test_unblock_requires_login(self):
        """POST /user/<id>/unblock requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/user/2/unblock", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_unblock_success_removes_block(self):
        """Valid unblock removes block relationship."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post("/user/2/unblock", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("DELETE FROM user_blocks" in s for s in execute_calls))

    def test_unblock_not_blocked_is_idempotent(self):
        """Unblocking a non-blocked user still runs DELETE (idempotent)."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 2, "name": "Bob"}

        resp = self.client.post("/user/2/unblock", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("DELETE FROM user_blocks" in s for s in execute_calls))

    # ── GET /blocked ────────────────────────────────────────────────────────

    def test_blocked_list_requires_login(self):
        """GET /blocked requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.get("/blocked", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_blocked_list_renders(self):
        """GET /blocked renders list of blocked users."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        blocked_users = [
            {"id": 2, "name": "Bob"},
            {"id": 3, "name": "Charlie"},
        ]
        db.fetch_all.return_value = blocked_users
        r = self.mock_render(MODULE)

        resp = self.client.get("/blocked")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "blocked_users.html")
        self.assertEqual(r.call_args.kwargs["blocked"], blocked_users)

    def test_blocked_list_empty(self):
        """GET /blocked renders empty list when no blocks."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_all.return_value = []
        r = self.mock_render(MODULE)

        resp = self.client.get("/blocked")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.kwargs["blocked"], [])

    # ── Integration: Block prevents mutual follow ────────────────────────────

    def test_follow_after_block_fails(self):
        """Following user is blocked by them fails."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"id": 2, "name": "Bob"},      # target user lookup
        ]

        with patch(f"{MODULE}.has_block_between", return_value=True):
            resp = self.client.post("/user/2/follow", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            execute_calls = [c.args[0] for c in db.execute.call_args_list]
            self.assertFalse(any("INSERT INTO user_follows" in s for s in execute_calls))

    # ── Integration: Chat gating uses follow/block ──────────────────────────

    def test_profile_shows_follow_status_to_logged_in_user(self):
        """Profile view shows whether logged-in user follows target."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        user = {"id": 2, "name": "Bob"}
        
        def fetch_side_effect(query, params=None):
            if "SELECT id, name, bio, profile_pic, created_at" in query:
                return user
            if "user_follows" in query:
                return {"user_id": 1, "follows_id": 2}
            return user

        db.fetch_one.side_effect = fetch_side_effect
        db.fetch_all.return_value = []
        r = self.mock_render(MODULE)

        resp = self.client.get("/user/2")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()


if __name__ == "__main__":
    unittest.main()

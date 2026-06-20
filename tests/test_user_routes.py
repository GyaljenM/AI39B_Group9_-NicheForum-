"""Tests for app/routes/UserRoutes.py (class ``UserRoutes``).

Exercises the public-profile view plus the follow / unfollow / block / unblock
actions and the blocked-users list through the real Flask URL map, with the
``Database`` and the follows/blocks/notification helpers mocked out so no test
ever touches MySQL.

Techniques used (as required):
  * unittest.TestCase via the shared :class:`tests.base.BaseForumTestCase`
  * unittest assert helpers (assertEqual / assertIn / assertTrue / mock asserts)
  * unittest.mock MagicMock / patch
  * Flask test client

The ``profile`` view calls ``len()`` on the results of ``get_followers`` /
``get_following`` and treats the follows/blocks helpers as booleans, so those
names are patched in the ``app.routes.UserRoutes`` namespace to return real
lists / bools (a bare MagicMock would break ``len()`` and truthiness checks).
"""

from unittest.mock import patch, MagicMock

from tests.base import BaseForumTestCase

MODULE = "app.routes.UserRoutes"


class UserRoutesTests(BaseForumTestCase):

    def _patch_helpers(
        self,
        *,
        followers=None,
        following=None,
        is_following=False,
        are_mutual_followers=False,
        is_blocked=False,
        has_block_between=False,
        blocked_users=None,
    ):
        """Patch the follows/blocks/notification helpers in the route module.

        Returns the (started) patchers' mocks keyed by name. Each patcher is
        registered for cleanup so it is undone after the test.
        """
        specs = {
            "get_followers": MagicMock(return_value=list(followers or [])),
            "get_following": MagicMock(return_value=list(following or [])),
            "is_following": MagicMock(return_value=bool(is_following)),
            "are_mutual_followers": MagicMock(return_value=bool(are_mutual_followers)),
            "is_blocked": MagicMock(return_value=bool(is_blocked)),
            "has_block_between": MagicMock(return_value=bool(has_block_between)),
            "get_blocked_users": MagicMock(return_value=list(blocked_users or [])),
            "create_notification": MagicMock(),
        }
        mocks = {}
        for name, mock in specs.items():
            patcher = patch(f"{MODULE}.{name}", mock)
            patcher.start()
            self.addCleanup(patcher.stop)
            mocks[name] = mock
        return mocks

    @staticmethod
    def _execute_sql_calls(db):
        """Return the list of SQL strings passed to ``db.execute``."""
        return [
            (call.args[0] if call.args else call.kwargs.get("query", ""))
            for call in db.execute.call_args_list
        ]

    # 1. GET /user/<id> logged-out, viewing another user -> 200 + render.
    def test_profile_logged_out_renders_user_profile(self):
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {
            "id": 2,
            "name": "Bob",
            "bio": "hi",
            "profile_pic": None,
            "created_at": "2026-01-01",
        }
        db.fetch_all.return_value = []
        render = self.mock_render(MODULE)
        self._patch_helpers()

        resp = self.client.get("/user/2")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, b"RENDERED")
        render.assert_called_once()
        self.assertEqual(render.call_args.args[0], "user_profile.html")

    # 2. GET /user/<id> where viewer_id == user_id -> redirect to Home.profile.
    def test_profile_own_id_redirects_to_home_profile(self):
        self.mock_database(MODULE)
        self.login(user_id=1)

        resp = self.client.get("/user/1")

        self.assertEqual(resp.status_code, 302)
        with self.app.test_request_context():
            from flask import url_for
            target = url_for("Home.profile")
        self.assertTrue(resp.headers["Location"].endswith(target))

    # 3. GET /user/<id> user not found -> redirect, db.execute NOT called.
    def test_profile_user_not_found_redirects(self):
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = None

        resp = self.client.get("/user/999")

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_not_called()

    # 4. POST /user/<id>/follow SUCCESS -> 302 + INSERT into user_follows.
    def test_follow_success_inserts_into_user_follows(self):
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 2, "name": "Bob"}
        self._patch_helpers(has_block_between=False, are_mutual_followers=False)
        self.login(user_id=1)

        resp = self.client.post("/user/2/follow")

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_called()
        self.assertTrue(
            any("user_follows" in sql and "INSERT" in sql.upper()
                for sql in self._execute_sql_calls(db)),
            "expected an INSERT into user_follows",
        )

    # 5. POST /user/<id>/follow yourself -> rejected, no follow INSERT.
    def test_follow_self_rejected_no_insert(self):
        db = self.mock_database(MODULE)
        self._patch_helpers()
        self.login(user_id=2)

        resp = self.client.post("/user/2/follow")

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            any("user_follows" in sql for sql in self._execute_sql_calls(db)),
            "following yourself must not write to user_follows",
        )

    # 6. POST /user/<id>/unfollow -> 302 + DELETE FROM user_follows.
    def test_unfollow_deletes_from_user_follows(self):
        db = self.mock_database(MODULE)
        self.login(user_id=1)

        resp = self.client.post("/user/2/unfollow")

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_called()
        self.assertTrue(
            any("DELETE" in sql.upper() and "user_follows" in sql
                for sql in self._execute_sql_calls(db)),
            "expected a DELETE FROM user_follows",
        )

    # 7. POST /user/<id>/block SUCCESS -> 302 + INSERT user_blocks + DELETE follows.
    def test_block_success_inserts_block_and_deletes_follows(self):
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 2, "name": "Bob"}
        self.login(user_id=1)

        resp = self.client.post("/user/2/block")

        self.assertEqual(resp.status_code, 302)
        sqls = self._execute_sql_calls(db)
        self.assertTrue(
            any("user_blocks" in sql and "INSERT" in sql.upper() for sql in sqls),
            "expected an INSERT into user_blocks",
        )
        self.assertTrue(
            any("user_follows" in sql and "DELETE" in sql.upper() for sql in sqls),
            "expected a DELETE FROM user_follows on block",
        )

    # 8. POST /user/<id>/unblock -> 302 + db.execute called (DELETE user_blocks).
    def test_unblock_deletes_from_user_blocks(self):
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 2, "name": "Bob"}
        self.login(user_id=1)

        resp = self.client.post("/user/2/unblock")

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_called()
        self.assertTrue(
            any("DELETE" in sql.upper() and "user_blocks" in sql
                for sql in self._execute_sql_calls(db)),
            "expected a DELETE FROM user_blocks",
        )

    # 9. GET /blocked -> 200 + render "blocked_users.html".
    def test_blocked_list_renders(self):
        self.mock_database(MODULE)
        render = self.mock_render(MODULE)
        self._patch_helpers(blocked_users=[{"id": 3, "name": "Carol"}])
        self.login(user_id=1)

        resp = self.client.get("/blocked")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, b"RENDERED")
        render.assert_called_once()
        self.assertEqual(render.call_args.args[0], "blocked_users.html")

    # 10. login_required: POST /user/2/follow without login -> 302 /login, no execute.
    def test_follow_requires_login(self):
        db = self.mock_database(MODULE)
        self._patch_helpers()

        resp = self.client.post("/user/2/follow")

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        db.execute.assert_not_called()

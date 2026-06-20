"""Tests for app/routes/ThreadRoutes.py (ThreadRoutes blueprint).

Every endpoint registered in ThreadRoutes.register() is exercised. The real
MySQL Database class is replaced by a MagicMock via the shared harness
(self.mock_database) so no test touches a live server. Helpers that operate on
results in ways a bare MagicMock would not survive (word censor, the
media/poll/note attachers, the admin-notifier) are patched in the
"app.routes.ThreadRoutes" namespace.
"""

import unittest
from unittest.mock import patch, MagicMock

from tests.base import BaseForumTestCase


class ThreadRoutesTestCase(BaseForumTestCase):
    """Full route-map coverage for the Thread blueprint."""

    def setUp(self):
        super().setUp()
        self.db = self.mock_database("app.routes.ThreadRoutes")
        # Word censor is a staticmethod that string-processes input; make it a
        # pass-through so assertions stay predictable.
        wc = patch("app.routes.ThreadRoutes.WordCensor")
        self.mock_censor = wc.start()
        self.addCleanup(wc.stop)
        self.mock_censor.censor_text.side_effect = lambda t: t
        # attach_media_and_poll / attach_notes mutate the row dict; harmless no-ops.
        for name in ("attach_media_and_poll", "attach_notes", "save_media",
                     "notify_admins_of_report"):
            p = patch(f"app.routes.ThreadRoutes.{name}", MagicMock())
            p.start()
            self.addCleanup(p.stop)

    # ── GET render endpoints ────────────────────────────────────────────────

    def test_view_thread_renders(self):
        render = self.mock_render("app.routes.ThreadRoutes")
        self.db.fetch_one.return_value = {
            "id": 5, "title": "Hi", "author": "tester", "author_pic": None,
            "thread_type": "text", "content": "body",
        }
        self.db.fetch_all.return_value = [
            {"id": 1, "content": "a reply", "user_email": "bob",
             "author_pic": None, "like_count": 2, "dislike_count": 0,
             "created_at": "now"},
        ]
        resp = self.client.get("/thread/5")
        self.assertEqual(resp.status_code, 200)
        render.assert_called_once()
        self.assertEqual(render.call_args.args[0], "thread_detail.html")

    def test_view_thread_not_found_redirects(self):
        self.mock_render("app.routes.ThreadRoutes")
        self.db.fetch_one.return_value = None
        resp = self.client.get("/thread/999")
        self.assertEqual(resp.status_code, 302)

    def test_view_community_renders(self):
        render = self.mock_render("app.routes.ThreadRoutes")
        self.db.fetch_all.side_effect = [
            [{"id": 7, "title": "T", "author": "tester", "author_pic": None,
              "category": "Sports"}],  # threads
            [],  # replies for thread 7
        ]
        resp = self.client.get("/community/Sports")
        self.assertEqual(resp.status_code, 200)
        render.assert_called_once()
        self.assertEqual(render.call_args.args[0], "community.html")
        self.assertEqual(render.call_args.kwargs["category_name"], "Sports")

    def test_edit_thread_get_renders(self):
        render = self.mock_render("app.routes.ThreadRoutes")
        self.login(user_name="tester")
        self.db.fetch_one.return_value = {
            "id": 3, "title": "Old", "content": "c", "author": "tester",
        }
        resp = self.client.get("/thread/3/edit")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(render.call_args.args[0], "edit_thread.html")

    def test_edit_reply_get_renders(self):
        render = self.mock_render("app.routes.ThreadRoutes")
        self.login(user_name="tester")
        self.db.fetch_one.return_value = {
            "id": 9, "content": "c", "user_email": "tester", "thread_id": 3,
        }
        resp = self.client.get("/thread/3/reply/9/edit")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(render.call_args.args[0], "edit_reply.html")

    # ── POST action endpoints ───────────────────────────────────────────────

    def test_create_thread_text(self):
        self.login()
        self.db.fetch_one.side_effect = [
            {"id": 2},          # category lookup
            {"id": 42},         # LAST_INSERT_ID
        ]
        resp = self.client.post("/create-thread", data={
            "thread_type": "text", "title": "Hello", "content": "World",
            "category": "Sports",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(self.db.execute.called)

    def test_create_thread_missing_title_redirects_no_insert(self):
        self.login()
        resp = self.client.post("/create-thread", data={
            "thread_type": "text", "title": "", "content": "body",
        })
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_not_called()

    def test_post_reply(self):
        self.login()
        resp = self.client.post("/thread/5/reply", data={"content": "nice"})
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called_once()

    def test_post_reply_ajax_json(self):
        self.login()
        resp = self.client.post(
            "/thread/5/reply", data={"content": "nice"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

    def test_edit_reply_post_updates(self):
        self.login(user_name="tester")
        self.db.fetch_one.return_value = {
            "id": 9, "content": "old", "user_email": "tester", "thread_id": 3,
        }
        resp = self.client.post("/thread/3/reply/9/edit", data={"content": "new"})
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called_once()

    def test_edit_thread_post_updates(self):
        self.login(user_name="tester")
        self.db.fetch_one.return_value = {
            "id": 3, "title": "Old", "content": "c", "author": "tester",
        }
        resp = self.client.post(
            "/thread/3/edit", data={"title": "New", "content": "body"})
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called_once()

    def test_vote_thread_json(self):
        # vote_thread reads request.json and returns JSON.
        self.db.fetch_one.return_value = {"votes": 6}
        resp = self.client.post("/thread/5/vote", json={"action": "up"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["votes"], 6)
        self.assertTrue(self.db.execute.called)

    def test_vote_reply_login_required_redirects(self):
        # No login -> login_required kicks in.
        resp = self.client.post("/thread/5/reply/9/vote",
                                data={"vote_type": "like"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_vote_reply_new_vote(self):
        self.login()
        self.db.fetch_one.side_effect = [
            {"id": 9, "thread_id": 5},   # reply exists
            None,                         # no existing vote
            {"c": 1},                     # like count
            {"c": 0},                     # dislike count
        ]
        resp = self.client.post(
            "/thread/5/reply/9/vote", data={"vote_type": "like"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["like_count"], 1)

    def test_vote_thread_poll(self):
        self.login()
        self.db.fetch_one.side_effect = [
            {"id": 5},                       # thread exists
            {"id": 11, "thread_id": 5},      # option exists
            None,                            # no existing vote
        ]
        resp = self.client.post("/thread/5/poll-vote", data={"option_id": "11"})
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called_once()

    def test_add_thread_note(self):
        self.login()
        self.db.fetch_one.return_value = {"id": 5}  # thread exists
        resp = self.client.post("/thread/5/note", data={"content": "context"})
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called_once()

    def test_rate_thread_note(self):
        self.login()
        self.db.fetch_one.side_effect = [
            {"id": 4, "thread_id": 5},   # note exists
            None,                         # no existing rating
        ]
        resp = self.client.post("/thread/note/4/rate", data={"rating": "helpful"})
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called_once()

    def test_report_thread(self):
        self.login()
        self.db.fetch_one.return_value = {"id": 5, "title": "T"}  # thread exists
        resp = self.client.post(
            "/thread/5/report",
            data={"reason": "spam", "details": "bad"},
        )
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called_once()

    def test_resolve_thread_report_admin_required(self):
        # Non-admin (plain user) is rejected by admin_required.
        self.login(user_role="user")
        resp = self.client.post("/report/thread/1/resolve")
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_not_called()

    def test_resolve_thread_report_admin_ok(self):
        self.login(user_role="admin")
        resp = self.client.post("/report/thread/1/resolve")
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called_once()

    def test_delete_thread_author(self):
        self.login(user_name="tester")
        self.db.fetch_one.return_value = {"author": "tester"}
        resp = self.client.post("/thread/delete/5")
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called_once()

    def test_delete_thread_not_author_no_delete(self):
        self.login(user_name="someoneelse")
        self.db.fetch_one.return_value = {"author": "tester"}
        resp = self.client.post("/thread/delete/5")
        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()

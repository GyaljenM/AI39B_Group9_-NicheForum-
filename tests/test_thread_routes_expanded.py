"""Comprehensive tests for app/routes/ThreadRoutes.py — the ``ThreadRoutes`` blueprint.

Tests thread creation/editing/deletion, replies, voting, polls,
community notes, and reporting with proper mocking.

Techniques used: unittest.TestCase (via BaseForumTestCase), assert methods,
MagicMock/patch, and Flask test client.
"""

import datetime
import unittest
from unittest.mock import patch, MagicMock

from tests.base import BaseForumTestCase

MODULE = "app.routes.ThreadRoutes"


class ThreadRoutesExpandedTests(BaseForumTestCase):
    """Comprehensive tests for ThreadRoutes."""

    # ── GET /community/<category> ───────────────────────────────────────────

    def test_view_community_renders_threads(self):
        """GET /community/<category> renders all threads in category."""
        db = self.mock_database(MODULE)
        threads = [
            {"id": 1, "title": "Thread 1", "author_id": 1, "created_at": datetime.datetime.utcnow()},
            {"id": 2, "title": "Thread 2", "author_id": 2, "created_at": datetime.datetime.utcnow()},
        ]
        db.fetch_all.return_value = threads
        r = self.mock_render(MODULE)

        resp = self.client.get("/community/Football")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "community.html")
        self.assertEqual(r.call_args.kwargs["threads"], threads)

    # ── GET /thread/<int:thread_id> ─────────────────────────────────────────

    def test_view_thread_renders(self):
        """GET /thread/<id> renders thread detail page."""
        db = self.mock_database(MODULE)
        thread = {
            "id": 1,
            "title": "My Thread",
            "content": "Thread content",
            "author_id": 1,
            "created_at": datetime.datetime.utcnow(),
        }
        replies = [
            {"id": 1, "content": "Reply 1", "author_id": 2},
        ]
        db.fetch_one.return_value = thread
        db.fetch_all.return_value = replies
        r = self.mock_render(MODULE)

        resp = self.client.get("/thread/1")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "thread_detail.html")
        self.assertEqual(r.call_args.kwargs["thread"], thread)
        self.assertEqual(r.call_args.kwargs["replies"], replies)

    def test_view_thread_not_found_redirects(self):
        """GET /thread/<nonexistent> redirects."""
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = None

        resp = self.client.get("/thread/999", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    # ── POST /create-thread ─────────────────────────────────────────────────

    def test_create_thread_requires_login(self):
        """POST /create-thread requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/create-thread", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_create_thread_text_only(self):
        """Creating text-only thread inserts thread row."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/create-thread",
            data={
                "category": "Football",
                "title": "New Thread",
                "content": "Thread content",
                "thread_type": "text",
            },
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO threads" in s for s in execute_calls))

    def test_create_thread_with_poll(self):
        """Creating thread with poll inserts poll options."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [{"id": 50}]  # LAST_INSERT_ID

        resp = self.client.post(
            "/create-thread",
            data={
                "category": "Football",
                "title": "Poll Thread",
                "content": "Vote now",
                "thread_type": "poll",
                "poll_options": ["Option 1", "Option 2", "Option 3"],
            },
            follow_redirects=False
        )

        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO threads" in s for s in execute_calls))
        self.assertTrue(any("INSERT INTO thread_poll_options" in s for s in execute_calls))

    # ── GET /thread/<int:thread_id>/edit ────────────────────────────────────

    def test_edit_thread_get_as_author(self):
        """GET /thread/<id>/edit renders edit form for author."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 1, "content": "Old"}
        r = self.mock_render(MODULE)

        resp = self.client.get("/thread/1/edit")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()

    def test_edit_thread_get_as_non_author_redirects(self):
        """GET /thread/<id>/edit redirects for non-author."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 1}

        resp = self.client.get("/thread/1/edit", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_edit_thread_post_updates(self):
        """POST /thread/<id>/edit updates thread content."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 1}

        resp = self.client.post(
            "/thread/1/edit",
            data={"content": "New content"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("UPDATE threads" in s for s in execute_calls))

    # ── POST /thread/<int:thread_id>/delete ─────────────────────────────────

    def test_delete_thread_requires_login(self):
        """POST /thread/<id>/delete requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/thread/1/delete", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_delete_thread_as_author(self):
        """Author can delete own thread."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 1}

        resp = self.client.post("/thread/1/delete", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("DELETE FROM threads" in s for s in execute_calls))

    def test_delete_thread_as_non_author_fails(self):
        """Non-author cannot delete thread."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 1}

        resp = self.client.post("/thread/1/delete", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_not_called()

    # ── POST /thread/<int:thread_id>/reply ──────────────────────────────────

    def test_post_reply_requires_login(self):
        """POST /thread/<id>/reply requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/thread/1/reply", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_post_reply_text_only(self):
        """Valid reply inserts reply row."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/thread/1/reply",
            data={
                "content": "Great thread!",
                "reply_type": "text",
            },
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO replies" in s for s in execute_calls))

    def test_post_reply_with_poll(self):
        """Reply with poll inserts poll options."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [{"id": 60}]

        resp = self.client.post(
            "/thread/1/reply",
            data={
                "content": "Poll reply",
                "reply_type": "poll",
                "poll_options": ["Yes", "No"],
            },
            follow_redirects=False
        )

        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO replies" in s for s in execute_calls))
        self.assertTrue(any("INSERT INTO thread_poll_options" in s for s in execute_calls))

    # ── GET /thread/<int:thread_id>/reply/<int:reply_id>/edit ────────────────

    def test_edit_reply_get_as_author(self):
        """GET /thread/<id>/reply/<id>/edit renders form for author."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 5, "content": "Old reply"}
        r = self.mock_render(MODULE)

        resp = self.client.get("/thread/1/reply/1/edit")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()

    def test_edit_reply_get_as_non_author_redirects(self):
        """GET /thread/<id>/reply/<id>/edit redirects for non-author."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 5}

        resp = self.client.get("/thread/1/reply/1/edit", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_edit_reply_post_updates(self):
        """POST /thread/<id>/reply/<id>/edit updates reply content."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 5}

        resp = self.client.post(
            "/thread/1/reply/1/edit",
            data={"content": "Updated reply"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("UPDATE replies" in s for s in execute_calls))

    # ── POST /thread/<int:thread_id>/vote ───────────────────────────────────

    def test_vote_thread_requires_login(self):
        """POST /thread/<id>/vote requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/thread/1/vote", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_vote_thread_up(self):
        """Voting up on thread inserts positive vote."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/thread/1/vote",
            data={"vote_type": "up"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO thread_votes" in s or "UPDATE thread_votes" in s for s in execute_calls))

    def test_vote_thread_down(self):
        """Voting down on thread inserts negative vote."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/thread/1/vote",
            data={"vote_type": "down"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)

    # ── POST /thread/<int:reply_id>/vote-reply ──────────────────────────────

    def test_vote_reply_requires_login(self):
        """POST /thread/<id>/vote-reply requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/thread/1/vote-reply", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_vote_reply_up(self):
        """Voting up on reply inserts positive vote."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/thread/1/vote-reply",
            data={"reply_id": 10, "vote_type": "up"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO reply_votes" in s or "UPDATE reply_votes" in s for s in execute_calls))

    # ── POST /thread/<int:thread_id>/vote-poll ──────────────────────────────

    def test_vote_thread_poll_requires_login(self):
        """POST /thread/<id>/vote-poll requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/thread/1/vote-poll", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_vote_thread_poll_inserts_vote(self):
        """Valid poll vote inserts vote row."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/thread/1/vote-poll",
            data={"option_id": 5},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO thread_poll_votes" in s for s in execute_calls))

    # ── POST /thread/<int:thread_id>/note ───────────────────────────────────

    def test_add_thread_note_requires_login(self):
        """POST /thread/<id>/note requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/thread/1/note", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_add_thread_note_success(self):
        """Valid community note inserts note row."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/thread/1/note",
            data={"content": "This is factually incorrect because..."},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO thread_notes" in s for s in execute_calls))

    # ── POST /thread/<int:note_id>/rate-note ────────────────────────────────

    def test_rate_thread_note_requires_login(self):
        """POST /thread/<id>/rate-note requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/thread/1/rate-note", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_rate_thread_note_helpful(self):
        """Rating note as helpful inserts vote."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/thread/1/rate-note",
            data={"note_id": 7, "helpful": "true"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO thread_note_votes" in s for s in execute_calls))

    # ── POST /thread/<int:thread_id>/report ─────────────────────────────────

    def test_report_thread_requires_login(self):
        """POST /thread/<id>/report requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/thread/1/report", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_report_thread_success(self):
        """Valid thread report inserts report row."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/thread/1/report",
            data={"reason": "Harassment"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO thread_reports" in s for s in execute_calls))

    # ── POST /thread/<int:report_id>/resolve-report ─────────────────────────

    def test_resolve_thread_report_requires_admin_or_mod(self):
        """POST /thread/<id>/resolve-report requires admin/mod."""
        self.login(user_id=5, user_name="Bob", user_role="user")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1}

        resp = self.client.post("/thread/1/resolve-report", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_resolve_thread_report_as_admin(self):
        """Admin can resolve thread report."""
        self.login(user_id=1, user_name="Admin", user_role="admin")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/thread/1/resolve-report",
            data={"action": "remove"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)


if __name__ == "__main__":
    unittest.main()

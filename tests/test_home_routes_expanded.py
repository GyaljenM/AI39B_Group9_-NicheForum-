"""Comprehensive tests for app/routes/HomeRoutes.py — the ``HomeRoutes`` blueprint.

Tests community CRUD, post creation/editing/deletion, voting, polls,
community notes, reporting, and moderation features with proper mocking.

Techniques used: unittest.TestCase (via BaseForumTestCase), assert methods,
MagicMock/patch, and Flask test client.
"""

import datetime
import unittest
from unittest.mock import patch, MagicMock

from tests.base import BaseForumTestCase

MODULE = "app.routes.HomeRoutes"


class HomeRoutesExpandedTests(BaseForumTestCase):
    """Comprehensive tests for HomeRoutes."""

    # ── GET / (home feed) ───────────────────────────────────────────────────

    def test_home_renders_recent_posts(self):
        """GET / renders home.html with recent posts."""
        db = self.mock_database(MODULE)
        posts = [
            {
                "id": 1,
                "content": "First post",
                "author_id": 1,
                "community_id": 1,
                "created_at": datetime.datetime.utcnow(),
            }
        ]
        db.fetch_all.return_value = posts
        r = self.mock_render(MODULE)

        resp = self.client.get("/")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "index.html")

    # ── GET /communities ────────────────────────────────────────────────────

    def test_communities_lists_all_communities(self):
        """GET /communities renders communities list."""
        db = self.mock_database(MODULE)
        communities = [
            {"id": 1, "name": "Football", "owner_id": 1},
            {"id": 2, "name": "Basketball", "owner_id": 2},
        ]
        db.fetch_all.return_value = communities
        r = self.mock_render(MODULE)

        resp = self.client.get("/communities")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "communities.html")
        self.assertEqual(r.call_args.kwargs["communities"], communities)

    # ── POST /create-community ──────────────────────────────────────────────

    def test_create_community_requires_login(self):
        """POST /create-community requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/create-community", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_create_community_success(self):
        """Valid community creation inserts row and redirects."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/create-community",
            data={"name": "New Community", "description": "About the new community"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO communities" in s for s in execute_calls))

    def test_create_community_duplicate_name_fails(self):
        """Duplicate community name prevents creation."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "name": "Existing"}

        resp = self.client.post(
            "/create-community",
            data={"name": "Existing", "description": "Duplicate"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        # execute should not have INSERT call
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertFalse(any("INSERT INTO communities" in s for s in execute_calls))

    # ── GET /search-communities ─────────────────────────────────────────────

    def test_search_communities_by_name(self):
        """GET /search-communities?q=football finds matching communities."""
        db = self.mock_database(MODULE)
        communities = [{"id": 1, "name": "Football League"}]
        db.fetch_all.return_value = communities
        r = self.mock_render(MODULE)

        resp = self.client.get("/search-communities", query_string={"q": "football"})

        self.assertEqual(resp.status_code, 200)
        r.assert_called()

    # ── GET /community/<int:community_id> ───────────────────────────────────

    def test_community_detail_renders(self):
        """GET /community/<id> renders community detail page."""
        db = self.mock_database(MODULE)
        community = {"id": 1, "name": "Football", "owner_id": 1}
        posts = [{"id": 1, "content": "Post 1"}]
        db.fetch_one.return_value = community
        db.fetch_all.return_value = posts
        r = self.mock_render(MODULE)

        resp = self.client.get("/community/1")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "community_detail.html")

    def test_community_detail_not_found_redirects(self):
        """GET /community/<nonexistent> redirects."""
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = None

        resp = self.client.get("/community/999", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    # ── POST /community/<int:community_id>/join ─────────────────────────────

    def test_join_community_requires_login(self):
        """POST /community/<id>/join requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/community/1/join", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_join_community_success(self):
        """Valid join inserts membership and redirects."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "name": "Football"}

        resp = self.client.post("/community/1/join", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO community_members" in s for s in execute_calls))

    def test_join_community_already_member_fails(self):
        """Joining as already-member is rejected."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"id": 1, "name": "Football"},  # community
            {"id": 1},  # already_member check
        ]

        resp = self.client.post("/community/1/join", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        # execute should not have INSERT
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertFalse(any("INSERT INTO community_members" in s for s in execute_calls))

    # ── POST /community/<int:community_id>/delete ───────────────────────────

    def test_delete_community_requires_ownership(self):
        """DELETE community fails if user is not owner."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "owner_id": 1}  # different owner

        resp = self.client.post("/community/1/delete", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_not_called()

    def test_delete_community_as_owner_succeeds(self):
        """DELETE community succeeds if user is owner."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "owner_id": 1}  # same owner

        resp = self.client.post("/community/1/delete", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("DELETE FROM communities" in s for s in execute_calls))

    # ── POST /post/create ───────────────────────────────────────────────────

    def test_create_post_requires_login(self):
        """POST /post/create requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/post/create", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_create_post_text_only(self):
        """Creating text-only post inserts post row."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1}

        resp = self.client.post(
            "/post/create",
            data={
                "community_id": 1,
                "content": "This is my post",
                "post_type": "text",
            },
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO posts" in s for s in execute_calls))

    def test_create_post_with_poll(self):
        """Creating post with poll options inserts poll options."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"id": 1},  # community
            {"id": 50},  # LAST_INSERT_ID for post
        ]

        resp = self.client.post(
            "/post/create",
            data={
                "community_id": 1,
                "content": "Poll post",
                "post_type": "poll",
                "poll_options": ["Option 1", "Option 2"],
            },
            follow_redirects=False
        )

        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO posts" in s for s in execute_calls))
        self.assertTrue(any("INSERT INTO post_poll_options" in s for s in execute_calls))

    # ── POST /post/<int:post_id>/vote ───────────────────────────────────────

    def test_vote_post_requires_login(self):
        """POST /post/<id>/vote requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/post/1/vote", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_vote_post_like(self):
        """Voting up on post inserts positive vote."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/post/1/vote",
            data={"vote_type": "up"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO post_votes" in s or "UPDATE post_votes" in s for s in execute_calls))

    def test_vote_post_dislike(self):
        """Voting down on post inserts negative vote."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/post/1/vote",
            data={"vote_type": "down"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO post_votes" in s or "UPDATE post_votes" in s for s in execute_calls))

    # ── POST /post/<int:post_id>/comment ────────────────────────────────────

    def test_comment_post_requires_login(self):
        """POST /post/<id>/comment requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/post/1/comment", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_comment_post_success(self):
        """Valid comment inserts comment row."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/post/1/comment",
            data={"content": "Great post!"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO post_comments" in s for s in execute_calls))

    # ── POST /post/<int:post_id>/delete ─────────────────────────────────────

    def test_delete_post_requires_login(self):
        """POST /post/<id>/delete requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/post/1/delete", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_delete_post_as_author(self):
        """Author can delete own post."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 1}

        resp = self.client.post("/post/1/delete", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("DELETE FROM posts" in s for s in execute_calls))

    def test_delete_post_as_non_author_fails(self):
        """Non-author cannot delete post."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 1}  # different author

        resp = self.client.post("/post/1/delete", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_not_called()

    # ── GET /post/<int:post_id>/edit ────────────────────────────────────────

    def test_edit_post_get_as_author(self):
        """GET /post/<id>/edit renders edit form for author."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 1, "content": "Old content"}
        r = self.mock_render(MODULE)

        resp = self.client.get("/post/1/edit")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()

    def test_edit_post_get_as_non_author_redirects(self):
        """GET /post/<id>/edit redirects for non-author."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 1}

        resp = self.client.get("/post/1/edit", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_edit_post_post_updates_content(self):
        """POST /post/<id>/edit updates post content."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "author_id": 1}

        resp = self.client.post(
            "/post/1/edit",
            data={"content": "New content"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("UPDATE posts" in s for s in execute_calls))

    # ── POST /post/<int:post_id>/report ─────────────────────────────────────

    def test_report_post_requires_login(self):
        """POST /post/<id>/report requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/post/1/report", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_report_post_success(self):
        """Valid post report inserts report row."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/post/1/report",
            data={"reason": "Spam"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO post_reports" in s for s in execute_calls))

    # ── GET /admin/reports ──────────────────────────────────────────────────

    def test_admin_reports_requires_admin_role(self):
        """GET /admin/reports requires admin role."""
        self.login(user_id=1, user_name="Alice", user_role="user")
        self.mock_database(MODULE)

        resp = self.client.get("/admin/reports", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_admin_reports_lists_all_reports(self):
        """GET /admin/reports renders all reports for admin."""
        self.login(user_id=1, user_name="Admin", user_role="admin")
        db = self.mock_database(MODULE)
        reports = [{"id": 1, "reason": "Spam"}]
        db.fetch_all.return_value = reports
        r = self.mock_render(MODULE)

        resp = self.client.get("/admin/reports")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()

    # ── POST /admin/report/<int:report_id>/resolve ──────────────────────────

    def test_resolve_post_report_requires_admin(self):
        """POST /admin/report/<id>/resolve requires admin."""
        self.login(user_id=1, user_name="User", user_role="user")
        self.mock_database(MODULE)

        resp = self.client.post("/admin/report/1/resolve", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_resolve_post_report_as_admin(self):
        """Admin can resolve report."""
        self.login(user_id=1, user_name="Admin", user_role="admin")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/admin/report/1/resolve",
            data={"action": "remove"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)

    # ── POST /community/<int:community_id>/ban/<int:member_id> ──────────────

    def test_ban_member_requires_community_mod(self):
        """POST /community/<id>/ban requires moderator permission."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "owner_id": 1}  # user is not owner

        resp = self.client.post("/community/1/ban/2", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_ban_member_as_owner(self):
        """Community owner can ban member."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "owner_id": 1}

        resp = self.client.post("/community/1/ban/2", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO community_bans" in s for s in execute_calls))

    # ── POST /community/<int:community_id>/unban/<int:member_id> ────────────

    def test_unban_member_as_owner(self):
        """Community owner can unban member."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "owner_id": 1}

        resp = self.client.post("/community/1/unban/2", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("DELETE FROM community_bans" in s for s in execute_calls))

    # ── GET /trending ──────────────────────────────────────────────────────

    def test_trending_renders_top_content(self):
        """GET /trending renders trending page with top posts."""
        db = self.mock_database(MODULE)
        posts = [{"id": 1, "content": "Popular"}]
        db.fetch_all.return_value = posts
        r = self.mock_render(MODULE)

        resp = self.client.get("/trending")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "trending.html")

    # ── GET /live ──────────────────────────────────────────────────────────

    def test_live_scores_renders(self):
        """GET /live renders live scores page."""
        db = self.mock_database(MODULE)
        r = self.mock_render(MODULE)

        resp = self.client.get("/live")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "live.html")


if __name__ == "__main__":
    unittest.main()

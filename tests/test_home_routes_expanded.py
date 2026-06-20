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
        """GET / renders index.html with recent posts (anonymous visitor)."""
        self.logout()
        db = self.mock_database(MODULE)
        # The home view loops over posts/threads and runs many per-item queries
        # via fetch_all (comments, media, notes, …). Returning [] keeps those
        # loops empty. The COUNT(*) hero-stat queries go through fetch_one.
        db.fetch_all.return_value = []
        db.fetch_one.return_value = {"count": 0}
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
        db.fetch_one.return_value = {"count": 0}
        r = self.mock_render(MODULE)

        resp = self.client.get("/communities")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "communities.html")
        self.assertEqual(r.call_args.kwargs["communities"], communities)

    # ── POST /communities/create ────────────────────────────────────────────

    def test_create_community_requires_login(self):
        """POST /communities/create requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/communities/create", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_create_community_success(self):
        """Valid community creation inserts row and redirects."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            None,        # duplicate-name check: no existing community
            {"id": 10},  # LAST_INSERT_ID() for the new community
        ]

        resp = self.client.post(
            "/communities/create",
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
            "/communities/create",
            data={"name": "Existing", "description": "Duplicate"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        # execute should not have INSERT call
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertFalse(any("INSERT INTO communities" in s for s in execute_calls))

    # ── GET /search ──────────────────────────────────────────────────────────

    def test_search_communities_by_name(self):
        """GET /search?q=football finds matching communities."""
        db = self.mock_database(MODULE)
        communities = [{"id": 1, "name": "Football League"}]
        db.fetch_all.return_value = communities
        r = self.mock_render(MODULE)

        resp = self.client.get("/search", query_string={"q": "football"})

        self.assertEqual(resp.status_code, 200)
        r.assert_called()

    # ── GET /community/<int:community_id> ───────────────────────────────────

    def test_community_detail_renders(self):
        """GET /community/<id> renders community detail page."""
        db = self.mock_database(MODULE)
        community = {"id": 1, "name": "Football", "owner_id": 1, "owner_name": "Alice"}
        db.fetch_one.return_value = community
        # No posts -> skip the per-post fan-out queries.
        db.fetch_all.return_value = []
        r = self.mock_render(MODULE)

        resp = self.client.get("/community/1")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "community_detail.html")

    def test_community_detail_not_found_returns_404(self):
        """GET /community/<nonexistent> returns 404."""
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = None

        resp = self.client.get("/community/999", follow_redirects=False)

        self.assertEqual(resp.status_code, 404)

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
        db.fetch_one.side_effect = [
            None,  # is_user_banned check -> not banned
            None,  # existing-membership check -> not a member yet
        ]

        resp = self.client.post("/community/1/join", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO community_members" in s for s in execute_calls))

    def test_join_community_already_member_fails(self):
        """Joining as already-member is rejected."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            None,        # is_user_banned check -> not banned
            {"id": 1},   # existing-membership check -> already a member
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
        # can_manage_community -> is_community_owner: no matching owner row.
        db.fetch_one.return_value = None

        resp = self.client.post("/community/1/delete", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertFalse(any("DELETE FROM communities" in s for s in execute_calls))

    def test_delete_community_as_owner_succeeds(self):
        """DELETE community succeeds if user is owner."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"1": 1},              # is_community_owner -> owner row found
            {"name": "Football"},  # community name lookup
        ]

        resp = self.client.post("/community/1/delete", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("DELETE FROM communities" in s for s in execute_calls))

    # ── POST /community/<int:community_id>/post ──────────────────────────────

    def test_create_post_requires_login(self):
        """POST /community/<id>/post requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/community/1/post", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_create_post_text_only(self):
        """Creating text-only post inserts post row."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"id": 1},                          # membership check
            {"id": 50},                         # LAST_INSERT_ID for post
            {"id": 1, "name": "Football"},      # community lookup for notification
        ]
        db.fetch_all.return_value = []          # members to notify

        resp = self.client.post(
            "/community/1/post",
            data={
                "title": "My title",
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
            {"id": 1},                          # membership check
            {"id": 50},                         # LAST_INSERT_ID for post
            {"id": 1, "name": "Football"},      # community lookup for notification
        ]
        db.fetch_all.return_value = []          # members to notify

        resp = self.client.post(
            "/community/1/post",
            data={
                "title": "Poll title",
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
        """Voting 'like' on a post records the vote."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"id": 1, "community_id": 1},  # post lookup
            None,                          # existing vote -> none yet
        ]

        resp = self.client.post(
            "/post/1/vote",
            data={"vote_type": "like"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO post_votes" in s or "UPDATE post_votes" in s for s in execute_calls))

    def test_vote_post_dislike(self):
        """Voting 'dislike' on a post records the vote."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"id": 1, "community_id": 1},  # post lookup
            None,                          # existing vote -> none yet
        ]

        resp = self.client.post(
            "/post/1/vote",
            data={"vote_type": "dislike"},
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
        db.fetch_one.return_value = {"id": 1, "community_id": 1}  # post lookup

        resp = self.client.post(
            "/post/1/comment",
            data={"content": "Great post!"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO post_comments" in s for s in execute_calls))

    # ── POST /post/delete/<int:post_id> ──────────────────────────────────────

    def test_delete_post_requires_login(self):
        """POST /post/delete/<id> requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/post/delete/1", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_delete_post_as_author(self):
        """Author can delete own post."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "user_id": 1, "community_id": 1}

        resp = self.client.post("/post/delete/1", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("DELETE FROM posts" in s for s in execute_calls))

    def test_delete_post_as_non_author_fails(self):
        """Non-author (non-admin, non-moderator) cannot delete post."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"id": 1, "user_id": 1, "community_id": 1},  # post (different author)
            None,                                        # is_community_moderator -> no
        ]

        resp = self.client.post("/post/delete/1", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertFalse(any("DELETE FROM posts" in s for s in execute_calls))

    # ── GET /post/<int:post_id>/edit ────────────────────────────────────────

    def test_edit_post_get_as_author(self):
        """GET /post/<id>/edit renders edit form for author."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {
            "id": 1, "user_id": 1, "content": "Old content", "post_type": "text",
        }
        db.fetch_all.return_value = []  # attach_media_and_poll media query
        r = self.mock_render(MODULE)

        resp = self.client.get("/post/1/edit")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()

    def test_edit_post_get_as_non_author_redirects(self):
        """GET /post/<id>/edit redirects for non-author."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "user_id": 1, "post_type": "text"}

        resp = self.client.get("/post/1/edit", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_edit_post_post_updates_content(self):
        """POST /post/<id>/edit updates post content."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {
            "id": 1, "user_id": 1, "community_id": 1, "post_type": "text",
        }

        resp = self.client.post(
            "/post/1/edit",
            data={"title": "New title", "content": "New content"},
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
        db.fetch_one.return_value = {"id": 1, "community_id": 1, "title": "A post"}

        resp = self.client.post(
            "/post/1/report",
            data={"reason": "spam"},
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
        reports = [{"id": 1, "reason": "spam"}]
        db.fetch_all.return_value = reports
        r = self.mock_render(MODULE)

        resp = self.client.get("/admin/reports")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()

    # ── POST /report/post/<int:report_id>/resolve ───────────────────────────

    def test_resolve_post_report_requires_admin(self):
        """POST /report/post/<id>/resolve requires admin."""
        self.login(user_id=1, user_name="User", user_role="user")
        self.mock_database(MODULE)

        resp = self.client.post("/report/post/1/resolve", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_resolve_post_report_as_admin(self):
        """Admin can resolve report."""
        self.login(user_id=1, user_name="Admin", user_role="admin")
        db = self.mock_database(MODULE)

        resp = self.client.post(
            "/report/post/1/resolve",
            data={"action": "remove"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("UPDATE post_reports" in s for s in execute_calls))

    # ── POST /community/<int:community_id>/admin/ban/<int:user_id> ───────────

    def test_ban_member_requires_community_mod(self):
        """POST /community/<id>/admin/ban requires moderator permission."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)
        # can_moderate_community -> is_community_moderator: no row -> not a mod.
        db.fetch_one.return_value = None

        resp = self.client.post("/community/1/admin/ban/2", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertFalse(any("INSERT INTO community_bans" in s for s in execute_calls))

    def test_ban_member_as_owner(self):
        """A site admin can ban a member."""
        self.login(user_id=1, user_name="Admin", user_role="admin")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"id": 2, "name": "Target", "role": "user"},  # target user lookup
            None,                                          # is_community_moderator(target) -> no
        ]

        resp = self.client.post("/community/1/admin/ban/2", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO community_bans" in s for s in execute_calls))

    # ── POST /community/<int:community_id>/admin/unban/<int:user_id> ─────────

    def test_unban_member_as_owner(self):
        """A site admin can unban a member."""
        self.login(user_id=1, user_name="Admin", user_role="admin")
        db = self.mock_database(MODULE)

        resp = self.client.post("/community/1/admin/unban/2", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("DELETE FROM community_bans" in s for s in execute_calls))

    # ── GET /trending ──────────────────────────────────────────────────────

    def test_trending_renders_top_content(self):
        """GET /trending renders trending page with top posts."""
        db = self.mock_database(MODULE)
        posts = [{
            "id": 1, "title": "Popular", "content": "Popular",
            "created_at": datetime.datetime(2024, 1, 1),
            "like_count": 5, "comment_count": 2,
        }]
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
        db.fetch_one.return_value = {"id": 1}  # Football community lookup
        r = self.mock_render(MODULE)

        resp = self.client.get("/live")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "live.html")


if __name__ == "__main__":
    unittest.main()

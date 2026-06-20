"""Tests for app/routes/HomeRoutes.py (class ``HomeRoutes``).

Built on the shared :class:`tests.base.BaseForumTestCase`, which gives every
test a real Flask app + test client with MySQL fully mocked out. Each test here:

  * uses the ``unittest`` framework (TestCase via BaseForumTestCase, ``test_*``
    methods),
  * uses ``unittest`` assert helpers (assertEqual / assertIn / assertTrue / the
    MagicMock ``assert_called*`` family) rather than bare ``assert``,
  * uses ``unittest.mock.MagicMock`` (via ``self.mock_database`` /
    ``self.mock_render`` and an explicit patch of the football service),
  * drives the routes through Flask's test client.

The football-data.org service (``get_match_manager``, imported into the
HomeRoutes namespace) is patched with a MagicMock so ``/api/live`` and ``/live``
never make a network call.

Endpoints covered (>=10):
  GET /                          home
  GET /communities               communities
  GET /communities/create        create_community (login_required)
  GET /search                    search_communities
  GET /trending                  trending
  GET /live                      live
  GET /api/live                  api_live (JSON, patched football service)
  GET /profile                   profile (login_required)
  POST /profile/update           update_profile (login_required)
  GET /community/<id>            community_detail
  POST /community/<id>/join      join_community (login_required)
  POST /community/<id>/post      create_post (login_required)
  POST /post/<id>/vote           vote_post (login_required)
  POST /post/<id>/comment        comment_post (login_required)
  POST /post/delete/<id>         delete_post (login_required)
  GET /admin/reports             admin_reports (admin_required)
  login_required guard           /profile without login -> 302 /login
"""

import unittest
from unittest.mock import patch, MagicMock

from tests.base import BaseForumTestCase

MODULE = "app.routes.HomeRoutes"

# A small, fake scoreboard the patched football service returns so /api/live and
# /live render without touching the network.
FAKE_SCOREBOARD = {
    "source": "sample",
    "message": "fake",
    "competition": "FIFA World Cup",
    "live_count": 1,
    "goals_today": 2,
    "matches": [
        {
            "id": "fake-1",
            "status": "IN_PLAY",
            "is_live": True,
            "stage": "Group Stage",
            "group": "Group A",
            "home": {"name": "Brazil", "short": "BRA", "crest": None, "goals": 2},
            "away": {"name": "Argentina", "short": "ARG", "crest": None, "goals": 1},
        }
    ],
    "upcoming": [],
    "updated": "2026-06-20T00:00:00Z",
}


class HomeRoutesTestCase(BaseForumTestCase):
    def setUp(self):
        super().setUp()
        # Mock the Database class inside the HomeRoutes module: Database() yields
        # this instance, so we control fetch_one/fetch_all and inspect execute.
        self.db = self.mock_database(MODULE)
        # Replace render_template with a sentinel-returning MagicMock.
        self.render = self.mock_render(MODULE)

        # Patch the football service so no network call happens. get_match_manager
        # returns a manager whose get_scoreboard() yields our fake payload.
        manager = MagicMock(name="MatchDataManager")
        manager.get_scoreboard.return_value = FAKE_SCOREBOARD
        self._fb_patcher = patch(f"{MODULE}.get_match_manager", return_value=manager)
        self.get_match_manager = self._fb_patcher.start()
        self.addCleanup(self._fb_patcher.stop)

        # Sensible defaults: fetch_one returns a count-shaped dict (covers the
        # SELECT COUNT(*) AS count / AS c stats queries), fetch_all returns [].
        self.db.fetch_one.return_value = {"count": 0, "c": 0, "id": 1}
        self.db.fetch_all.return_value = []

    # ── GET render endpoints ────────────────────────────────────────────────

    def test_home_renders_index_when_logged_out(self):
        self.db.fetch_all.return_value = []
        # Counts come from fetch_one; the default already returns a dict.
        resp = self.client.get("/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), "RENDERED")
        self.assertTrue(self.render.called)
        template = self.render.call_args.args[0]
        self.assertEqual(template, "index.html")

    def test_home_renders_dashboard_when_logged_in(self):
        self.login()
        resp = self.client.get("/")

        self.assertEqual(resp.status_code, 200)
        template = self.render.call_args.args[0]
        self.assertEqual(template, "dashboard.html")

    def test_communities_lists_communities(self):
        self.db.fetch_all.return_value = [
            {"id": 1, "name": "Football", "description": "x", "member_count": 5},
        ]
        resp = self.client.get("/communities")

        self.assertEqual(resp.status_code, 200)
        self.render.assert_called_once()
        self.assertEqual(self.render.call_args.args[0], "communities.html")

    def test_create_community_get_renders_form(self):
        self.login()
        resp = self.client.get("/communities/create")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.render.call_args.args[0], "create_community.html")

    def test_search_renders_results(self):
        self.db.fetch_all.return_value = []
        resp = self.client.get("/search?q=foot")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.render.call_args.args[0], "search_results.html")
        # The query string is passed through to the template.
        self.assertEqual(self.render.call_args.kwargs.get("query"), "foot")

    def test_trending_renders(self):
        self.db.fetch_all.return_value = [
            {
                "id": 1,
                "title": "Big game",
                "content": "body",
                "created_at": "2026-06-19 10:00:00",
                "community_id": 1,
                "user_name": "tester",
                "profile_pic": None,
                "community_name": "Football",
                "like_count": 3,
                "comment_count": 1,
            }
        ]
        resp = self.client.get("/trending")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.render.call_args.args[0], "trending.html")

    def test_live_page_renders(self):
        # community lookup row (football_url) -> a community id
        self.db.fetch_one.return_value = {"id": 7}
        resp = self.client.get("/live")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.render.call_args.args[0], "live.html")

    def test_community_detail_renders(self):
        # First fetch_one is the community lookup; needs a truthy dict.
        self.db.fetch_one.return_value = {
            "id": 1,
            "name": "Football",
            "owner_id": 2,
            "owner_name": "owner",
        }
        self.db.fetch_all.return_value = []  # no posts -> no per-post loop
        resp = self.client.get("/community/1")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.render.call_args.args[0], "community_detail.html")

    def test_community_detail_404_when_missing(self):
        self.db.fetch_one.return_value = None
        resp = self.client.get("/community/999")

        self.assertEqual(resp.status_code, 404)

    def test_profile_renders_for_logged_in_user(self):
        self.login()
        self.db.fetch_one.return_value = {"id": 1, "name": "tester", "bio": ""}
        self.db.fetch_all.return_value = []  # posts + follow graph
        resp = self.client.get("/profile")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.render.call_args.args[0], "activity_feed.html")

    # ── /api/live JSON (patched football service) ───────────────────────────

    def test_api_live_returns_json_from_patched_service(self):
        resp = self.client.get("/api/live")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        data = resp.get_json()
        self.assertEqual(data["source"], "sample")
        self.assertEqual(data["live_count"], 1)
        self.assertEqual(data["matches"][0]["home"]["name"], "Brazil")
        # Confirm we went through the mocked service, not the network.
        self.get_match_manager.assert_called_once()

    # ── POST action endpoints ───────────────────────────────────────────────

    def test_join_community_inserts_and_redirects(self):
        self.login()
        # is_user_banned -> None (not banned); membership lookup -> None (new).
        self.db.fetch_one.return_value = None
        resp = self.client.post("/community/1/join")

        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called()
        sql = self.db.execute.call_args.args[0]
        self.assertIn("INSERT INTO community_members", sql)

    def test_create_post_inserts_and_redirects(self):
        self.login()
        # membership lookup truthy, then LAST_INSERT_ID(), then community lookup.
        self.db.fetch_one.side_effect = [
            {"id": 10},                       # is_member
            {"id": 55},                       # LAST_INSERT_ID()
            {"id": 1, "name": "Football"},    # community (for notifications)
        ]
        resp = self.client.post(
            "/community/1/post",
            data={"post_type": "text", "title": "Hello", "content": "World"},
        )

        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called()
        # One of the execute calls must be the post INSERT.
        sqls = [c.args[0] for c in self.db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO posts" in s for s in sqls))

    def test_vote_post_inserts_vote_and_redirects(self):
        self.login()
        # post lookup truthy, then existing-vote lookup -> None (fresh vote).
        self.db.fetch_one.side_effect = [
            {"id": 5, "community_id": 1},  # post
            None,                         # existing vote
        ]
        resp = self.client.post("/post/5/vote", data={"vote_type": "like"})

        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called()
        self.assertIn("INSERT INTO post_votes", self.db.execute.call_args.args[0])

    def test_comment_post_inserts_comment_and_redirects(self):
        self.login()
        self.db.fetch_one.return_value = {"id": 5, "community_id": 1}  # post
        resp = self.client.post("/post/5/comment", data={"content": "nice"})

        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called()
        self.assertIn("INSERT INTO post_comments", self.db.execute.call_args.args[0])

    def test_delete_post_deletes_when_owner_and_redirects(self):
        self.login(user_id=1)
        # post owned by the logged-in user (user_id == 1).
        self.db.fetch_one.return_value = {"id": 5, "user_id": 1, "community_id": 1}
        resp = self.client.post("/post/delete/5")

        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called()
        self.assertIn("DELETE FROM posts", self.db.execute.call_args.args[0])

    def test_update_profile_updates_and_redirects(self):
        self.login()
        resp = self.client.post("/profile/update", data={"name": "newname", "bio": "hi"})

        self.assertEqual(resp.status_code, 302)
        self.db.execute.assert_called()
        self.assertIn("UPDATE users", self.db.execute.call_args.args[0])

    # ── login_required guard ────────────────────────────────────────────────

    def test_profile_requires_login(self):
        # No login -> login_required redirects to the Auth.login route (/login).
        resp = self.client.get("/profile")

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    # ── admin_required guard ────────────────────────────────────────────────

    def test_admin_reports_forbidden_for_non_admin(self):
        self.login(user_role="user")
        resp = self.client.get("/admin/reports")

        # Non-admin is redirected (admin_required -> Home.home).
        self.assertEqual(resp.status_code, 302)

    def test_admin_reports_renders_for_admin(self):
        self.login(user_role="admin")
        self.db.fetch_all.return_value = []  # post + thread reports
        resp = self.client.get("/admin/reports")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.render.call_args.args[0], "admin_reports.html")


if __name__ == "__main__":
    unittest.main()

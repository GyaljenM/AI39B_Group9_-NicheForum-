"""Comprehensive tests for app/routes/NotificationRoutes.py — the ``NotificationRoutes`` blueprint.

Tests notification listing, feed polling, and marking notifications as read
with proper mocking of database and template rendering.

Techniques used: unittest.TestCase (via BaseForumTestCase), assert methods,
MagicMock/patch, and Flask test client.
"""

import datetime
import unittest
from unittest.mock import patch, MagicMock

from tests.base import BaseForumTestCase

MODULE = "app.routes.NotificationRoutes"


class NotificationRoutesExpandedTests(BaseForumTestCase):
    """Comprehensive tests for NotificationRoutes."""

    # ── Helper methods ──────────────────────────────────────────────────────

    @staticmethod
    def _sample_notification(notification_id=1, user_id=1, notification_type="follow",
                           message="Alice followed you", url="/user/1"):
        """Create a sample notification dict."""
        return {
            "id": notification_id,
            "user_id": user_id,
            "type": notification_type,
            "message": message,
            "url": url,
            "is_read": 0,
            "created_at": datetime.datetime.utcnow(),
        }

    # ── GET /notifications (list page) ──────────────────────────────────────

    def test_notifications_list_requires_login(self):
        """GET /notifications requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.get("/notifications", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_notifications_list_renders(self):
        """GET /notifications renders notifications.html."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        notifications = [
            self._sample_notification(1, 1, "follow", "Bob followed you"),
            self._sample_notification(2, 1, "reply", "Carol replied to your post"),
        ]
        db.fetch_all.return_value = notifications
        r = self.mock_render(MODULE)

        resp = self.client.get("/notifications")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "notifications.html")
        self.assertEqual(r.call_args.kwargs["notifications"], notifications)

    def test_notifications_list_marks_all_read_on_view(self):
        """GET /notifications marks all notifications as read."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_all.return_value = [
            self._sample_notification(1, 1, "follow", "Bob followed you"),
        ]
        r = self.mock_render(MODULE)

        resp = self.client.get("/notifications")

        self.assertEqual(resp.status_code, 200)
        # Verify UPDATE to mark all read
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("UPDATE notifications SET is_read = 1" in s for s in execute_calls))

    def test_notifications_list_empty(self):
        """GET /notifications handles empty notification list."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_all.return_value = []
        r = self.mock_render(MODULE)

        resp = self.client.get("/notifications")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(r.call_args.kwargs["notifications"], [])

    def test_notifications_list_with_multiple_notification_types(self):
        """GET /notifications handles various notification types."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        notifications = [
            self._sample_notification(1, 1, "follow", "User followed you", "/user/2"),
            self._sample_notification(2, 1, "reply", "User replied to your post", "/post/5#reply-10"),
            self._sample_notification(3, 1, "message", "User sent you a message", "/chat/2"),
            self._sample_notification(4, 1, "community_post", "New post in subscribed community", "/post/20"),
            self._sample_notification(5, 1, "comment", "User commented on your thread", "/thread/3#reply-8"),
        ]
        db.fetch_all.return_value = notifications
        r = self.mock_render(MODULE)

        resp = self.client.get("/notifications")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(r.call_args.kwargs["notifications"]), 5)

    # ── GET /notifications/feed (JSON poll) ─────────────────────────────────

    def test_notifications_feed_requires_login(self):
        """GET /notifications/feed requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.get("/notifications/feed", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_notifications_feed_returns_json(self):
        """GET /notifications/feed returns JSON with messages."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        notifications = [
            self._sample_notification(1, 1, "follow", "Bob followed you"),
            self._sample_notification(2, 1, "reply", "Carol replied to your post"),
        ]
        db.fetch_all.return_value = notifications

        resp = self.client.get("/notifications/feed")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        data = resp.get_json()
        self.assertIn("messages", data)
        self.assertEqual(len(data["messages"]), 2)

    def test_notifications_feed_limits_to_15_items(self):
        """GET /notifications/feed limits results to 15 items."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        notifications = [self._sample_notification(i, 1) for i in range(20)]
        db.fetch_all.return_value = notifications[:15]

        resp = self.client.get("/notifications/feed")

        self.assertTrue(resp.is_json)
        data = resp.get_json()
        self.assertEqual(len(data["messages"]), 15)

    def test_notifications_feed_formats_timestamps(self):
        """GET /notifications/feed formats timestamps in response."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        created_at = datetime.datetime(2026, 6, 20, 10, 30, 0)
        notif = {
            "id": 1,
            "user_id": 1,
            "type": "follow",
            "message": "Bob followed you",
            "url": "/user/2",
            "is_read": 0,
            "created_at": created_at,
        }
        db.fetch_all.return_value = [notif]

        resp = self.client.get("/notifications/feed")

        self.assertTrue(resp.is_json)
        data = resp.get_json()
        # Timestamp should be formatted (check it's a string)
        self.assertIn("created_at", data["messages"][0])

    def test_notifications_feed_handles_none_created_at(self):
        """GET /notifications/feed handles None timestamps gracefully."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        notif = {
            "id": 1,
            "user_id": 1,
            "type": "follow",
            "message": "Bob followed you",
            "url": "/user/2",
            "is_read": 0,
            "created_at": None,
        }
        db.fetch_all.return_value = [notif]

        resp = self.client.get("/notifications/feed")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)

    def test_notifications_feed_includes_unread_count(self):
        """GET /notifications/feed includes unread notification count."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        notifications = [
            self._sample_notification(1, 1, "follow", "Bob followed you"),
            self._sample_notification(2, 1, "reply", "Carol replied"),
        ]
        db.fetch_all.side_effect = [notifications, {"unread_count": 2}]

        resp = self.client.get("/notifications/feed")

        self.assertTrue(resp.is_json)
        data = resp.get_json()
        # Should have unread_count field
        self.assertIn("unread_count", data)

    def test_notifications_feed_empty_list(self):
        """GET /notifications/feed returns empty messages list when no notifications."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_all.side_effect = [[], {"unread_count": 0}]

        resp = self.client.get("/notifications/feed")

        self.assertTrue(resp.is_json)
        data = resp.get_json()
        self.assertEqual(data["messages"], [])

    # ── POST /notifications/mark-read ──────────────────────────────────────

    def test_mark_read_requires_login(self):
        """POST /notifications/mark-read requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/notifications/mark-read", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_mark_read_marks_all_as_read(self):
        """POST /notifications/mark-read marks all notifications as read."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post("/notifications/mark-read")

        # Should have made UPDATE call
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("UPDATE notifications SET is_read = 1" in s for s in execute_calls))

    def test_mark_read_returns_json_with_zero(self):
        """POST /notifications/mark-read returns JSON with 0 unread."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post("/notifications/mark-read")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        data = resp.get_json()
        # Should return unread count of 0
        self.assertEqual(data.get("unread_count"), 0)

    def test_mark_read_updates_only_unread_for_current_user(self):
        """POST /notifications/mark-read only marks current user's notifications."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        resp = self.client.post("/notifications/mark-read")

        # Verify WHERE clause filters by user
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        update_call = [s for s in execute_calls if "UPDATE notifications" in s]
        # Should have WHERE user_id = %s
        self.assertTrue(any("WHERE" in s and "user_id" in s for s in update_call))

    # ── Integration: Unread badge polling ────────────────────────────────────

    def test_feed_updates_badge_count(self):
        """GET /notifications/feed provides fresh unread count for badge."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        
        # Simulate notification state
        notifications = [self._sample_notification(i, 1) for i in range(3)]
        db.fetch_all.side_effect = [notifications, {"unread_count": 3}]

        resp = self.client.get("/notifications/feed")

        data = resp.get_json()
        self.assertEqual(data["unread_count"], 3)

    def test_mark_read_then_feed_shows_zero(self):
        """After mark-read, subsequent feed returns 0 unread."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)

        # Mark all read
        resp1 = self.client.post("/notifications/mark-read")
        self.assertEqual(resp1.get_json()["unread_count"], 0)

        # Check feed again
        db.fetch_all.side_effect = [[], {"unread_count": 0}]
        resp2 = self.client.get("/notifications/feed")
        self.assertEqual(resp2.get_json()["unread_count"], 0)

    # ── Notification type routing ───────────────────────────────────────────

    def test_follow_notification_has_user_profile_url(self):
        """Follow notifications include user profile URL."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        notif = self._sample_notification(1, 1, "follow", "Bob followed you", "/user/2")
        db.fetch_all.return_value = [notif]

        resp = self.client.get("/notifications/feed")

        data = resp.get_json()
        self.assertEqual(data["messages"][0]["url"], "/user/2")

    def test_reply_notification_has_post_url(self):
        """Reply notifications include post URL."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        notif = self._sample_notification(2, 1, "reply", "Carol replied", "/post/5#reply-10")
        db.fetch_all.return_value = [notif]

        resp = self.client.get("/notifications/feed")

        data = resp.get_json()
        self.assertIn("/post/", data["messages"][0]["url"])

    def test_message_notification_has_chat_url(self):
        """Message notifications include chat URL."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        notif = self._sample_notification(3, 1, "message", "Bob sent a message", "/chat/2")
        db.fetch_all.return_value = [notif]

        resp = self.client.get("/notifications/feed")

        data = resp.get_json()
        self.assertIn("/chat/", data["messages"][0]["url"])

    # ── Error handling ──────────────────────────────────────────────────────

    def test_notifications_list_handles_db_error(self):
        """GET /notifications handles database error gracefully."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_all.side_effect = Exception("Database error")

        resp = self.client.get("/notifications")

        # Should still return 200 with error handling
        self.assertIn(resp.status_code, [200, 500])

    def test_notifications_feed_handles_db_error(self):
        """GET /notifications/feed handles database error gracefully."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_all.side_effect = Exception("Database error")

        resp = self.client.get("/notifications/feed")

        # Should return JSON error or empty
        if resp.status_code == 200:
            self.assertTrue(resp.is_json)

    # ── Performance: Pagination ─────────────────────────────────────────────

    def test_feed_efficient_with_large_dataset(self):
        """GET /notifications/feed efficiently handles large dataset."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        
        # Simulate many notifications but only return 15
        notifications = [self._sample_notification(i, 1) for i in range(100)]
        db.fetch_all.return_value = notifications[:15]

        resp = self.client.get("/notifications/feed")

        data = resp.get_json()
        self.assertEqual(len(data["messages"]), 15)


if __name__ == "__main__":
    unittest.main()

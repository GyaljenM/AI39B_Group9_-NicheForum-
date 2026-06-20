"""Tests for app.routes.NotificationRoutes.NotificationRoutes.

Exercises the three notification endpoints through the real Flask URL map with
MySQL and the notification helpers mocked out. Builds on the shared harness in
``tests.base`` so no test ever opens a real database connection.
"""

import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

from tests.base import BaseForumTestCase

MODULE = "app.routes.NotificationRoutes"


def _full_notification(**overrides):
    """A row dict carrying every key the feed view reads."""
    row = {
        "id": 7,
        "type": "reply",
        "message": "Someone replied to your post",
        "url": "/threads/42",
        "is_read": 0,
        "actor_name": "alice",
        "actor_pic": "alice.png",
        "created_at": datetime(2026, 6, 20, 14, 30),
    }
    row.update(overrides)
    return row


class NotificationRoutesTestCase(BaseForumTestCase):
    def test_list_page_renders_and_marks_read(self):
        """GET /notifications renders notifications.html and marks all read."""
        self.login(user_id=1)
        self.mock_database(MODULE)
        render = self.mock_render(MODULE)

        with patch(f"{MODULE}.get_notifications", return_value=[_full_notification()]), \
             patch(f"{MODULE}.mark_all_read") as mark_all_read:
            resp = self.client.get("/notifications")

        self.assertEqual(resp.status_code, 200)
        render.assert_called_once()
        self.assertEqual(render.call_args.args[0], "notifications.html")
        mark_all_read.assert_called()

    def test_feed_returns_json_with_formatted_item(self):
        """GET /notifications/feed returns count + items with formatted date."""
        self.login(user_id=1)
        self.mock_database(MODULE)

        row = _full_notification()
        with patch(f"{MODULE}.get_notifications", return_value=[row]), \
             patch(f"{MODULE}.unread_count", return_value=3):
            resp = self.client.get("/notifications/feed")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        data = resp.get_json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["id"], row["id"])
        self.assertEqual(item["type"], row["type"])
        self.assertEqual(item["message"], row["message"])
        self.assertEqual(item["created_at"], "Jun 20, 14:30")

    def test_feed_handles_none_created_at(self):
        """A None created_at becomes an empty string instead of erroring."""
        self.login(user_id=1)
        self.mock_database(MODULE)

        row = _full_notification(created_at=None)
        with patch(f"{MODULE}.get_notifications", return_value=[row]), \
             patch(f"{MODULE}.unread_count", return_value=0):
            resp = self.client.get("/notifications/feed")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        item = resp.get_json()["items"][0]
        self.assertEqual(item["created_at"], "")

    def test_mark_read_returns_zero_and_marks_read(self):
        """POST /notifications/mark-read returns count 0 and marks all read."""
        self.login(user_id=1)
        self.mock_database(MODULE)

        with patch(f"{MODULE}.mark_all_read") as mark_all_read:
            resp = self.client.post("/notifications/mark-read")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        self.assertEqual(resp.get_json()["count"], 0)
        mark_all_read.assert_called()

    def test_feed_requires_login(self):
        """Without a session, the feed redirects to the login page."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.get("/notifications/feed")

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])


if __name__ == "__main__":
    unittest.main()

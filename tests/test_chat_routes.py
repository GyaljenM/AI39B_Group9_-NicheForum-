"""Tests for app/routes/ChatRoutes.py — the ``ChatRoutes`` blueprint.

ChatRoutes implements 1-to-1 direct messaging that is gated on the follow
graph: a conversation is only allowed between two users who BOTH follow each
other (``are_mutual_followers`` from app.follows) and where neither has blocked
the other (``has_block_between`` from app.blocks).

These tests build on :class:`tests.base.BaseForumTestCase`, which gives a real
Flask app + test client with MySQL mocked out. For each test we:

  * ``self.mock_database("app.routes.ChatRoutes")`` so ``Database()`` inside the
    module yields a MagicMock and never touches MySQL,
  * ``self.mock_render("app.routes.ChatRoutes")`` for the template views,
  * patch the gating helpers imported into the ChatRoutes namespace
    (``are_mutual_followers``, ``has_block_between``, ``create_notification``)
    with MagicMocks returning real bools, so we can drive both the allowed and
    rejected code paths.

Techniques exercised (all required): unittest.TestCase (via the base class),
unittest assert helpers, unittest.mock MagicMock/patch, and the Flask test
client.
"""

import datetime
import unittest
from unittest.mock import patch, MagicMock

from tests.base import BaseForumTestCase


class ChatRoutesTests(BaseForumTestCase):
    # ── helpers ──────────────────────────────────────────────────────────────

    def _patch_gating(self, mutual=True, blocked=False):
        """Patch the gating helpers in the ChatRoutes namespace.

        Returns the (are_mutual_followers, has_block_between, create_notification)
        MagicMocks so individual tests can assert on them if needed.
        """
        mutual_mock = patch(
            "app.routes.ChatRoutes.are_mutual_followers",
            MagicMock(return_value=mutual),
        ).start()
        block_mock = patch(
            "app.routes.ChatRoutes.has_block_between",
            MagicMock(return_value=blocked),
        ).start()
        notif_mock = patch(
            "app.routes.ChatRoutes.create_notification",
            MagicMock(return_value=None),
        ).start()
        self.addCleanup(patch.stopall)
        return mutual_mock, block_mock, notif_mock

    @staticmethod
    def _sample_messages():
        """A realistic direct_messages row list (real dicts, so it's iterable)."""
        return [
            {
                "id": 1,
                "sender_id": 1,
                "receiver_id": 2,
                "content": "hey there",
                "share_type": None,
                "share_label": None,
                "share_url": None,
                "created_at": datetime.datetime(2026, 6, 20, 10, 30),
            },
            {
                "id": 2,
                "sender_id": 2,
                "receiver_id": 1,
                "content": "hi back",
                "share_type": None,
                "share_label": None,
                "share_url": None,
                "created_at": datetime.datetime(2026, 6, 20, 10, 31),
            },
        ]

    @staticmethod
    def _sample_conversations():
        return [
            {
                "id": 2,
                "name": "Bob",
                "profile_pic": None,
                "show_online_status": 1,
                "last_at": datetime.datetime(2026, 6, 20, 10, 31),
            }
        ]

    # ── 1. chat inbox / list page (GET render) ───────────────────────────────

    def test_chat_home_renders(self):
        db = self.mock_database("app.routes.ChatRoutes")
        render = self.mock_render("app.routes.ChatRoutes")
        # chat_home calls _conversation_list then _my_communities (both fetch_all)
        db.fetch_all.side_effect = [self._sample_conversations(), []]

        self.login(user_id=1, user_name="tester")
        resp = self.client.get("/chat")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), "RENDERED")
        self.assertTrue(render.called)
        template_name = render.call_args.args[0]
        self.assertEqual(template_name, "chat.html")
        kwargs = render.call_args.kwargs
        self.assertEqual(kwargs["conversations"], self._sample_conversations())
        self.assertIsNone(kwargs["other"])

    # ── 2. conversation page with another user (GET render) ──────────────────

    def test_conversation_renders_when_mutual(self):
        self._patch_gating(mutual=True, blocked=False)
        db = self.mock_database("app.routes.ChatRoutes")
        render = self.mock_render("app.routes.ChatRoutes")

        other = {
            "id": 2,
            "name": "Bob",
            "profile_pic": None,
            "bio": "hi",
            "show_online_status": 1,
        }
        db.fetch_one.return_value = other
        # conversation(): _conversation_list, _fetch_messages,
        # _mutual_communities, _my_communities  (four fetch_all calls)
        db.fetch_all.side_effect = [
            self._sample_conversations(),
            self._sample_messages(),
            [],
            [],
        ]

        self.login(user_id=1, user_name="tester")
        resp = self.client.get("/chat/2")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), "RENDERED")
        kwargs = render.call_args.kwargs
        self.assertEqual(kwargs["other"], other)
        self.assertEqual(kwargs["messages"], self._sample_messages())

    def test_conversation_redirects_when_not_mutual(self):
        # Not mutual followers -> redirect to the other user's profile, no render.
        self._patch_gating(mutual=False, blocked=False)
        db = self.mock_database("app.routes.ChatRoutes")
        db.fetch_one.return_value = {
            "id": 2,
            "name": "Bob",
            "profile_pic": None,
            "bio": "",
            "show_online_status": 1,
        }

        self.login(user_id=1, user_name="tester")
        resp = self.client.get("/chat/2")

        self.assertEqual(resp.status_code, 302)
        # Should NOT have rendered the conversation messages.
        db.execute.assert_not_called()

    # ── 3. send message (POST) ALLOWED ───────────────────────────────────────

    def test_send_message_allowed_inserts_and_redirects(self):
        _, _, notif = self._patch_gating(mutual=True, blocked=False)
        db = self.mock_database("app.routes.ChatRoutes")
        # send_message does fetch_one(other) then fetch_one(sender)
        db.fetch_one.side_effect = [
            {"id": 2, "name": "Bob"},
            {"id": 1, "name": "tester"},
        ]

        self.login(user_id=1, user_name="tester")
        resp = self.client.post("/chat/2/send", data={"content": "hello world"})

        self.assertEqual(resp.status_code, 302)
        # The INSERT into direct_messages must have happened.
        self.assertTrue(db.execute.called)
        insert_sql = db.execute.call_args.args[0]
        self.assertIn("INSERT INTO direct_messages", insert_sql)
        insert_params = db.execute.call_args.args[1]
        # (sender_id, receiver_id, content)
        self.assertEqual(insert_params[0], 1)
        self.assertEqual(insert_params[1], 2)

    # ── 4. send message BLOCKED / NOT-MUTUAL ─────────────────────────────────

    def test_send_message_blocked_does_not_insert(self):
        # A block in either direction must reject the message before any INSERT.
        self._patch_gating(mutual=True, blocked=True)
        db = self.mock_database("app.routes.ChatRoutes")
        db.fetch_one.return_value = {"id": 2, "name": "Bob"}

        self.login(user_id=1, user_name="tester")
        resp = self.client.post("/chat/2/send", data={"content": "hello"})

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_not_called()

    def test_send_message_not_mutual_does_not_insert(self):
        # Not mutual followers -> rejected, no INSERT.
        self._patch_gating(mutual=False, blocked=False)
        db = self.mock_database("app.routes.ChatRoutes")
        db.fetch_one.return_value = {"id": 2, "name": "Bob"}

        self.login(user_id=1, user_name="tester")
        resp = self.client.post("/chat/2/send", data={"content": "hello"})

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_not_called()

    # ── 5. JSON polling endpoint (new messages feed) ─────────────────────────

    def test_poll_messages_returns_json(self):
        db = self.mock_database("app.routes.ChatRoutes")
        db.fetch_all.return_value = self._sample_messages()

        self.login(user_id=1, user_name="tester")
        resp = self.client.get("/chat/2/messages")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_json)
        payload = resp.get_json()
        self.assertIn("messages", payload)
        self.assertEqual(len(payload["messages"]), 2)
        # First message was sent by user 1 (the logged-in user) -> "mine".
        self.assertTrue(payload["messages"][0]["mine"])
        self.assertFalse(payload["messages"][1]["mine"])
        self.assertEqual(payload["messages"][0]["content"], "hey there")

    # ── 6. login_required ────────────────────────────────────────────────────

    def test_chat_home_requires_login(self):
        # No login -> login_required redirects (302) to the login page.
        self.mock_database("app.routes.ChatRoutes")
        self.logout()

        resp = self.client.get("/chat")

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])


if __name__ == "__main__":
    unittest.main()

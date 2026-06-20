"""Tests for app/controllers/auth.py (AuthController) wired through app/routes/auth.py.

Every test subclasses the shared :class:`BaseForumTestCase` harness, which gives a
real Flask app (TESTING on, CSRF off), a test client, session helpers, and the
``mock_database`` / ``mock_render`` patch helpers. The real MySQL ``Database`` is
always replaced with a MagicMock, and ``EmailService`` (imported into
``app.controllers.auth``) is patched so no real email is ever sent.

Techniques used (all required): unittest.TestCase via BaseForumTestCase,
unittest assert* methods, unittest.mock MagicMock/patch, and the Flask test client.
"""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from werkzeug.security import generate_password_hash

from tests.base import BaseForumTestCase

MODULE = "app.controllers.auth"


class AuthControllerTestCase(BaseForumTestCase):
    """Exercises the auth controller flows through real routes."""

    def _stats_user(self, **overrides):
        """A fetch_one row that satisfies both the login path and the stats
        queries (which read ['count']). MagicMock indexing covers ['count']
        unless we hand back an explicit dict, so we use a side_effect when a
        test needs a real user row followed by stats rows."""
        row = {"count": 0}
        row.update(overrides)
        return row

    # ── /login ──────────────────────────────────────────────────────────────

    def test_get_login_renders(self):
        """GET /login renders login.html and returns 200."""
        db = self.mock_database(MODULE)
        # GET only runs the stats block -> three fetch_one calls returning counts.
        db.fetch_one.return_value = {"count": 0}
        r = self.mock_render(MODULE)

        resp = self.client.get("/login")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "login.html")

    def test_post_login_success_sets_session_and_redirects(self):
        """Correct email+password logs the user in and redirects to Home.home."""
        db = self.mock_database(MODULE)
        user = {
            "id": 7,
            "name": "Alice",
            "email": "alice@example.com",
            "password": generate_password_hash("secret"),
            "role": "user",
            "is_active": 1,
            "is_verified": 1,
            "profile_pic": None,
        }
        db.fetch_one.return_value = user

        resp = self.client.post(
            "/login",
            data={"email": "alice@example.com", "password": "secret"},
        )

        self.assertEqual(resp.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("user_id"), 7)
            self.assertEqual(sess.get("user_name"), "Alice")
            self.assertEqual(sess.get("user_role"), "user")

    def test_post_login_wrong_password_does_not_log_in(self):
        """A bad password must not set user_id; the login page is re-rendered (200)."""
        db = self.mock_database(MODULE)

        def fetch_side_effect(query, params=None):
            if "WHERE email" in query:
                return {
                    "id": 7,
                    "name": "Alice",
                    "email": "alice@example.com",
                    "password": generate_password_hash("secret"),
                    "role": "user",
                    "is_active": 1,
                    "is_verified": 1,
                    "profile_pic": None,
                }
            # stats queries
            return {"count": 0}

        db.fetch_one.side_effect = fetch_side_effect
        r = self.mock_render(MODULE)

        resp = self.client.post(
            "/login",
            data={"email": "alice@example.com", "password": "WRONG"},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(r.call_args.args[0], "login.html")
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    # ── /register ─────────────────────────────────────────────────────────────

    def test_get_register_renders(self):
        """GET /register renders register.html and returns 200."""
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"count": 0}
        r = self.mock_render(MODULE)

        resp = self.client.get("/register")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(r.call_args.args[0], "register.html")

    @patch(f"{MODULE}.EmailService")
    def test_post_register_success_creates_user_and_redirects(self, mock_email):
        """A valid registration inserts the user + security question and redirects
        to verify_registration, with the OTP email mocked out."""
        mock_email.generate_secure_otp.return_value = "123456"
        mock_email.send_otp.return_value = True

        db = self.mock_database(MODULE)

        def fetch_side_effect(query, params=None):
            if "WHERE email" in query:
                return None  # no existing user
            if "LAST_INSERT_ID" in query:
                return {"id": 42}
            return {"count": 0}

        db.fetch_one.side_effect = fetch_side_effect

        resp = self.client.post(
            "/register",
            data={
                "name": "Bob",
                "email": "bob@example.com",
                "password": "supersecret",
                "security_question": "What city were you born in?",
                "security_answer": "Paris",
            },
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/verify-registration", resp.headers["Location"])
        # User row + security-question row both inserted.
        insert_sql = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO users" in s for s in insert_sql))
        self.assertTrue(any("INSERT INTO security_questions" in s for s in insert_sql))
        mock_email.send_otp.assert_called_once()

    # ── /verify-registration ─────────────────────────────────────────────────

    def test_get_verify_registration_renders(self):
        """GET /verify-registration renders the OTP entry page."""
        self.mock_database(MODULE)
        r = self.mock_render(MODULE)

        resp = self.client.get("/verify-registration", query_string={"email": "x@y.com"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(r.call_args.args[0], "enter_otp.html")

    def test_post_verify_registration_success(self):
        """A matching, unexpired OTP marks the user verified and redirects to login."""
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {
            "id": 1,
            "email": "v@example.com",
            "verification_token": "654321",
            "token_expires_at": datetime.utcnow() + timedelta(minutes=5),
        }

        resp = self.client.post(
            "/verify-registration",
            data={"email": "v@example.com", "otp": "654321"},
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        update_sql = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("SET is_verified = 1" in s for s in update_sql))

    # ── /forgot-password ─────────────────────────────────────────────────────

    def test_get_forgot_password_renders(self):
        """GET /forgot-password renders the email-entry form."""
        self.mock_database(MODULE)
        r = self.mock_render(MODULE)

        resp = self.client.get("/forgot-password")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(r.call_args.args[0], "forgot_password.html")

    def test_post_forgot_password_known_email_shows_question(self):
        """A known email shows that account's security question."""
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {
            "id": 3,
            "question": "What was your first pet's name?",
            "locked_until": None,
            "failed_attempts": 0,
        }
        r = self.mock_render(MODULE)

        resp = self.client.post("/forgot-password", data={"email": "known@example.com"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(r.call_args.args[0], "security_question.html")
        self.assertEqual(
            r.call_args.kwargs["question"], "What was your first pet's name?"
        )

    # ── /logout ──────────────────────────────────────────────────────────────

    def test_logout_clears_session_and_redirects(self):
        """GET /logout clears the session and redirects to the login page."""
        self.login(user_id=5, user_name="tester")
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("user_id"), 5)

        resp = self.client.get("/logout")

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    # ── /deactivate-account ──────────────────────────────────────────────────

    def test_deactivate_account_logged_in(self):
        """Deactivation sets is_active = 0, clears the session, and redirects."""
        self.login(user_id=9)
        db = self.mock_database(MODULE)

        resp = self.client.post("/deactivate-account")

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        update_sql = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("SET is_active = 0" in s for s in update_sql))
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    def test_deactivate_account_not_logged_in_redirects(self):
        """Without a session, deactivation just redirects to login (no DB write)."""
        self.logout()
        db = self.mock_database(MODULE)

        resp = self.client.post("/deactivate-account")

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        db.execute.assert_not_called()

    # ── /delete-account (request) ────────────────────────────────────────────

    @patch(f"{MODULE}.EmailService")
    def test_request_account_deletion_ajax_sends_code(self, mock_email):
        """An AJAX delete request stores an OTP, emails it, and returns ok JSON."""
        mock_email.generate_secure_otp.return_value = "999000"
        mock_email.send_otp.return_value = True

        self.login(user_id=11)
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {
            "id": 11,
            "name": "Carol",
            "email": "carol@example.com",
        }

        resp = self.client.post(
            "/delete-account",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload["ok"])
        update_sql = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("deletion_token" in s for s in update_sql))
        mock_email.send_otp.assert_called_once()

    # ── /delete-account/confirm ──────────────────────────────────────────────

    def test_confirm_account_deletion_wrong_code_redirects(self):
        """A wrong OTP does not delete the account; it redirects to the profile."""
        self.login(user_id=12)
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {
            "id": 12,
            "name": "Dave",
            "email": "dave@example.com",
            "deletion_token": "111111",
            "deletion_token_expires_at": datetime.utcnow() + timedelta(minutes=5),
        }

        resp = self.client.post("/delete-account/confirm", data={"otp": "000000"})

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/profile", resp.headers["Location"])
        # No DELETE FROM users on a wrong code, and session intact.
        delete_sql = [c.args[0] for c in db.execute.call_args_list]
        self.assertFalse(any("DELETE FROM users" in s for s in delete_sql))
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("user_id"), 12)


if __name__ == "__main__":
    import unittest

    unittest.main()

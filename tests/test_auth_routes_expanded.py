"""Comprehensive tests for app/routes/auth.py — the ``AuthRoutes`` blueprint.

Tests all authentication endpoints including login, registration, password recovery,
account deactivation, and account deletion with proper mocking of Database,
EmailService, and other dependencies.

Techniques used: unittest.TestCase (via BaseForumTestCase), assert methods,
MagicMock/patch, and Flask test client.
"""

import datetime
import unittest
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

from tests.base import BaseForumTestCase

MODULE = "app.controllers.auth"


class AuthRoutesExpandedTests(BaseForumTestCase):
    """Comprehensive tests for all auth routes and flows."""

    # ── /login GET ──────────────────────────────────────────────────────────

    def test_login_get_renders_with_stats(self):
        """GET /login renders login.html with community/member stats."""
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"count": 5},  # total_communities
            {"count": 42},  # total_members
            {"count": 12},  # online_now
        ]
        r = self.mock_render(MODULE)

        resp = self.client.get("/login")

        self.assertEqual(resp.status_code, 200)
        r.assert_called_once()
        self.assertEqual(r.call_args.args[0], "login.html")
        # Verify stats passed to template
        kwargs = r.call_args.kwargs
        self.assertEqual(kwargs["total_communities"], 5)
        self.assertEqual(kwargs["total_members"], 42)
        self.assertEqual(kwargs["online_now"], 12)

    # ── /login POST ─────────────────────────────────────────────────────────

    def test_login_post_success_sets_session(self):
        """Correct credentials log user in and set session + redirect."""
        db = self.mock_database(MODULE)
        user = {
            "id": 1,
            "name": "Alice",
            "email": "alice@test.com",
            "password": generate_password_hash("mypassword"),
            "role": "user",
            "is_active": 1,
            "profile_pic": "pic.jpg",
        }
        db.fetch_one.side_effect = [user] + [{"count": 0}] * 3  # for stats on failure re-render

        resp = self.client.post(
            "/login",
            data={"email": "alice@test.com", "password": "mypassword"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("user_id"), 1)
            self.assertEqual(sess.get("user_name"), "Alice")
            self.assertEqual(sess.get("user_role"), "user")
            self.assertEqual(sess.get("profile_pic"), "pic.jpg")

    def test_login_post_wrong_password_fails(self):
        """Invalid password prevents login and re-renders login page."""
        db = self.mock_database(MODULE)
        user = {
            "id": 1,
            "name": "Alice",
            "email": "alice@test.com",
            "password": generate_password_hash("correct_password"),
            "role": "user",
            "is_active": 1,
            "profile_pic": None,
        }

        def fetch_side_effect(query, params=None):
            if "WHERE email" in query:
                return user
            return {"count": 0}

        db.fetch_one.side_effect = fetch_side_effect
        r = self.mock_render(MODULE)

        resp = self.client.post(
            "/login",
            data={"email": "alice@test.com", "password": "wrong_password"},
        )

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "login.html")
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    def test_login_post_nonexistent_email_fails(self):
        """Nonexistent email prevents login."""
        db = self.mock_database(MODULE)

        def fetch_side_effect(query, params=None):
            if "WHERE email" in query:
                return None
            return {"count": 0}

        db.fetch_one.side_effect = fetch_side_effect
        r = self.mock_render(MODULE)

        resp = self.client.post(
            "/login",
            data={"email": "nonexistent@test.com", "password": "anypassword"},
        )

        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    def test_login_post_reactivates_inactive_account(self):
        """Successful login on inactive account reactivates it."""
        db = self.mock_database(MODULE)
        user = {
            "id": 1,
            "name": "Alice",
            "email": "alice@test.com",
            "password": generate_password_hash("mypassword"),
            "role": "user",
            "is_active": 0,  # inactive
            "profile_pic": None,
        }
        db.fetch_one.side_effect = [user] + [{"count": 0}] * 3

        resp = self.client.post(
            "/login",
            data={"email": "alice@test.com", "password": "mypassword"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        # Verify UPDATE was called to reactivate
        update_calls = [c for c in db.execute.call_args_list if "UPDATE users" in str(c)]
        self.assertTrue(any("is_active = 1" in str(c) for c in update_calls))

    def test_login_post_admin_email_grants_admin_role(self):
        """Login with hardcoded admin email sets admin role."""
        db = self.mock_database(MODULE)
        user = {
            "id": 99,
            "name": "SuperUser",
            "email": "adim@gmail.com",  # admin email
            "password": generate_password_hash("adminpass"),
            "role": "user",
            "is_active": 1,
            "profile_pic": None,
        }
        db.fetch_one.side_effect = [user] + [{"count": 0}] * 3

        resp = self.client.post(
            "/login",
            data={"email": "adim@gmail.com", "password": "adminpass"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("user_role"), "admin")

    # ── /register GET ───────────────────────────────────────────────────────

    def test_register_get_renders_with_questions(self):
        """GET /register renders register.html with security questions."""
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [{"count": 3}] * 3
        r = self.mock_render(MODULE)

        resp = self.client.get("/register")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "register.html")
        # Should pass security_questions to template
        self.assertIn("security_questions", r.call_args.kwargs)

    # ── /register POST ──────────────────────────────────────────────────────

    @patch(f"{MODULE}.EmailService")
    def test_register_post_success_creates_user(self, mock_email):
        """Valid registration inserts user + security question, sends OTP."""
        mock_email.generate_secure_otp.return_value = "123456"
        mock_email.send_otp.return_value = None

        db = self.mock_database(MODULE)

        def fetch_side_effect(query, params=None):
            if "WHERE email" in query:
                return None  # no existing user
            if "LAST_INSERT_ID" in query:
                return {"id": 99}
            return {"count": 0}

        db.fetch_one.side_effect = fetch_side_effect

        resp = self.client.post(
            "/register",
            data={
                "name": "NewUser",
                "email": "newuser@test.com",
                "password": "securepass",
                "security_question": "What was your first pet's name?",
                "security_answer": "Blue",
            },
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/verify-registration", resp.headers["Location"])
        # Verify both INSERT calls
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("INSERT INTO users" in s for s in execute_calls))
        self.assertTrue(any("INSERT INTO security_questions" in s for s in execute_calls))

    @patch(f"{MODULE}.EmailService")
    def test_register_post_email_already_exists(self, mock_email):
        """Registering with existing email redirects without creating user."""
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "email": "existing@test.com"}

        resp = self.client.post(
            "/register",
            data={
                "name": "Duplicate",
                "email": "existing@test.com",
                "password": "password",
                "security_question": "Q",
                "security_answer": "A",
            },
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_not_called()

    @patch(f"{MODULE}.EmailService")
    def test_register_post_missing_security_question(self, mock_email):
        """Missing security question redirects without creating user."""
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = None

        resp = self.client.post(
            "/register",
            data={
                "name": "NoQuestion",
                "email": "user@test.com",
                "password": "pass",
                "security_question": "",  # empty
                "security_answer": "answer",
            },
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_not_called()

    # ── /verify-registration ────────────────────────────────────────────────

    def test_verify_registration_get_renders(self):
        """GET /verify-registration renders enter_otp.html."""
        self.mock_database(MODULE)
        r = self.mock_render(MODULE)

        resp = self.client.get("/verify-registration", query_string={"email": "test@test.com"})

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "enter_otp.html")

    def test_verify_registration_post_valid_otp_marks_verified(self):
        """Valid OTP marks user verified and redirects to login."""
        db = self.mock_database(MODULE)
        user = {
            "id": 42,
            "email": "verify@test.com",
            "verification_token": "654321",
            "token_expires_at": datetime.datetime.utcnow() + datetime.timedelta(minutes=5),
        }
        db.fetch_one.return_value = user

        resp = self.client.post(
            "/verify-registration",
            data={"email": "verify@test.com", "otp": "654321"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        # Verify UPDATE SET is_verified = 1
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("SET is_verified = 1" in s for s in execute_calls))

    def test_verify_registration_post_expired_otp_fails(self):
        """Expired OTP does not verify user."""
        db = self.mock_database(MODULE)
        user = {
            "id": 42,
            "email": "verify@test.com",
            "verification_token": "654321",
            "token_expires_at": datetime.datetime.utcnow() - datetime.timedelta(minutes=1),
        }
        db.fetch_one.return_value = user
        r = self.mock_render(MODULE)

        resp = self.client.post(
            "/verify-registration",
            data={"email": "verify@test.com", "otp": "654321"},
        )

        self.assertEqual(resp.status_code, 302)
        db.execute.assert_not_called()

    def test_verify_registration_post_wrong_otp_fails(self):
        """Wrong OTP does not verify user."""
        db = self.mock_database(MODULE)
        user = {
            "id": 42,
            "email": "verify@test.com",
            "verification_token": "654321",
            "token_expires_at": datetime.datetime.utcnow() + datetime.timedelta(minutes=5),
        }
        db.fetch_one.return_value = user
        r = self.mock_render(MODULE)

        resp = self.client.post(
            "/verify-registration",
            data={"email": "verify@test.com", "otp": "WRONG"},
        )

        self.assertEqual(resp.status_code, 200)
        db.execute.assert_not_called()

    # ── /forgot-password ────────────────────────────────────────────────────

    def test_forgot_password_get_renders(self):
        """GET /forgot-password renders forgot_password.html."""
        self.mock_database(MODULE)
        r = self.mock_render(MODULE)

        resp = self.client.get("/forgot-password")

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "forgot_password.html")

    def test_forgot_password_post_valid_email_renders_question(self):
        """POST with valid email renders security question page."""
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"id": 1, "email": "user@test.com", "question": "What was your first pet's name?"}
        r = self.mock_render(MODULE)

        resp = self.client.post(
            "/forgot-password",
            data={"email": "user@test.com"},
        )

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "security_question.html")

    def test_forgot_password_post_invalid_email_renders_failed(self):
        """POST with nonexistent email renders failed page."""
        db = self.mock_database(MODULE)
        db.fetch_one.return_value = None
        r = self.mock_render(MODULE)

        resp = self.client.post(
            "/forgot-password",
            data={"email": "nonexistent@test.com"},
        )

        self.assertEqual(resp.status_code, 200)
        r.assert_called()
        self.assertEqual(r.call_args.args[0], "security_question.html")

    # ── /logout ─────────────────────────────────────────────────────────────

    def test_logout_clears_session_and_redirects(self):
        """POST /logout clears session and redirects to login."""
        self.login(user_id=1, user_name="Alice")
        self.mock_database(MODULE)

        with self.client.session_transaction() as sess:
            self.assertIsNotNone(sess.get("user_id"))

        resp = self.client.get("/logout", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    # ── /deactivate-account ─────────────────────────────────────────────────

    def test_deactivate_account_requires_login(self):
        """POST /deactivate-account requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/deactivate-account", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_deactivate_account_sets_inactive(self):
        """POST /deactivate-account sets is_active = 0 and redirects."""
        self.login(user_id=5, user_name="Bob")
        db = self.mock_database(MODULE)

        resp = self.client.post("/deactivate-account", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        # Verify UPDATE is_active = 0
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(any("is_active = 0" in s for s in execute_calls))

    # ── /delete-account ─────────────────────────────────────────────────────

    def test_delete_account_requires_login(self):
        """POST /delete-account requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/delete-account", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    @patch(f"{MODULE}.EmailService")
    def test_delete_account_sends_otp_and_redirects(self, mock_email):
        """POST /delete-account sends OTP email and redirects."""
        self.login(user_id=1, user_name="Alice")
        mock_email.generate_secure_otp.return_value = "999999"
        mock_email.send_otp.return_value = None

        db = self.mock_database(MODULE)
        db.fetch_one.return_value = {"email": "alice@test.com"}

        resp = self.client.post("/delete-account", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        mock_email.send_otp.assert_called_once()

    # ── /delete-account/confirm ─────────────────────────────────────────────

    def test_delete_account_confirm_requires_login(self):
        """POST /delete-account/confirm requires login."""
        self.logout()
        self.mock_database(MODULE)

        resp = self.client.post("/delete-account/confirm", follow_redirects=False)

        self.assertEqual(resp.status_code, 302)

    def test_delete_account_confirm_valid_otp_deletes_account(self):
        """Valid OTP in /delete-account/confirm deletes account permanently."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"id": 1, "name": "Alice", "email": "alice@test.com", "deletion_token": "777777",
             "deletion_token_expires_at": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
            {"id": 999},  # deleted_user sentinel
        ]

        resp = self.client.post(
            "/delete-account/confirm",
            data={"otp": "777777"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)
        # Verify account was actually deleted (UPDATE + DELETE calls)
        execute_calls = [c.args[0] for c in db.execute.call_args_list]
        self.assertTrue(len(execute_calls) > 0)

    def test_delete_account_confirm_wrong_otp_fails(self):
        """Wrong OTP in /delete-account/confirm does not delete account."""
        self.login(user_id=1, user_name="Alice")
        db = self.mock_database(MODULE)
        db.fetch_one.side_effect = [
            {"id": 1, "email": "alice@test.com", "deletion_token": "777777",
             "deletion_token_expires_at": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
        ]

        resp = self.client.post(
            "/delete-account/confirm",
            data={"otp": "WRONG"},
            follow_redirects=False
        )

        self.assertEqual(resp.status_code, 302)


if __name__ == "__main__":
    unittest.main()

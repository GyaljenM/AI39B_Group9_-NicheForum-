"""Shared test harness for the NicheForum test-suite.

Every test module in ``tests/`` builds on :class:`BaseForumTestCase`. It gives
each test:

* a real Flask app built from :func:`app.create_app` (so the actual blueprints
  and URL map are exercised) with ``TESTING`` on and CSRF disabled,
* a Flask **test client** (``self.client``) for issuing requests,
* helpers to drop a **MagicMock** ``Database`` into any route/controller module
  so no test ever touches a real MySQL server,
* a ``login`` helper that primes the Flask session the way ``login_required``
  expects.

The app's ``create_app`` normally calls ``Database.create_tables()`` and a
notification context-processor that both open MySQL connections. ``setUp``
patches those out before the app is created so the suite runs fully offline and
deterministically.
"""

import unittest
from unittest.mock import patch, MagicMock

from app import create_app


class BaseForumTestCase(unittest.TestCase):
    """Base class wiring up a Flask app + test client with MySQL mocked out."""

    def setUp(self):
        # 1. Stop create_app() from touching a real database on boot.
        self._patchers = [
            patch("app.models.database.Database.create_tables", return_value=None),
            # The notification context-processor (app/__init__.py) opens its own
            # Database() on every template render — keep it offline + clean.
            patch("app.Database", MagicMock()),
            patch("app.unread_count", return_value=0),
        ]
        for p in self._patchers:
            p.start()

        # 2. Build the real application and a test client.
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY="test-secret-key",
        )
        self.client = self.app.test_client()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        patch.stopall()

    # ── helpers ────────────────────────────────────────────────────────────

    def login(self, user_id=1, user_name="tester", user_role="user"):
        """Prime the session so ``login_required`` / ``admin_required`` pass."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_name"] = user_name
            sess["user_role"] = user_role

    def logout(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    def mock_database(self, module_path):
        """Replace ``Database`` in ``module_path`` with a MagicMock class.

        Returns the mock **instance** that ``Database()`` yields inside that
        module, so a test can stub ``.fetch_one`` / ``.fetch_all`` / ``.execute``
        and later assert on the calls.

        Example::

            db = self.mock_database("app.routes.UserRoutes")
            db.fetch_one.return_value = {"id": 2, "name": "Bob"}
        """
        patcher = patch(f"{module_path}.Database")
        mock_cls = patcher.start()
        self.addCleanup(patcher.stop)
        instance = MagicMock(name=f"{module_path}.Database()")
        mock_cls.return_value = instance
        return instance

    def mock_render(self, module_path):
        """Replace ``render_template`` in ``module_path`` with a MagicMock.

        Lets a test exercise a template-rendering view without depending on the
        template's internals: the mock returns a sentinel string and records the
        ``(template_name, **context)`` it was called with.
        """
        patcher = patch(f"{module_path}.render_template")
        mock_render = patcher.start()
        self.addCleanup(patcher.stop)
        mock_render.return_value = "RENDERED"
        return mock_render

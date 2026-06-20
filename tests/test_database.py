"""Unit tests for the pure DB layer: ``app.models.database.Database``.

These tests exercise the ``Database`` class in complete isolation from MySQL.
``app.models.database.pymysql.connect`` is patched with a ``MagicMock`` so a fake
connection + cursor are returned; only ``.connect`` is patched, leaving
``pymysql.MySQLError`` intact as a real exception class (the code relies on
``except pymysql.MySQLError``).

A Flask test client is intentionally NOT used here: this module tests the raw
database access layer, which has no relationship to HTTP request handling, so the
``BaseForumTestCase`` client harness does not apply.

Techniques used (as required): ``unittest`` framework with ``test_*`` methods on
a ``TestCase`` subclass, unittest assert functions only (no bare ``assert``), and
``unittest.mock`` MagicMock / patch.
"""

import unittest
from unittest import mock
from unittest.mock import MagicMock, patch

import pymysql

from app.models.database import Database


class DatabaseTests(unittest.TestCase):
    """Cover every method of ``Database`` with MySQL fully mocked out."""

    def _make_connection_mock(self, fetchone=None, fetchall=None):
        """Build a fake (connection, cursor) pair.

        Returns a mock connection whose ``cursor()`` yields ``mock_cursor``.
        """
        mock_cursor = MagicMock(name="cursor")
        mock_cursor.fetchone.return_value = fetchone
        mock_cursor.fetchall.return_value = fetchall if fetchall is not None else []

        mock_conn = MagicMock(name="connection")
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor

    # ── __init__ ────────────────────────────────────────────────────────────

    def test_init_success_stores_connection(self):
        mock_conn, _ = self._make_connection_mock()
        with patch("app.models.database.pymysql.connect", return_value=mock_conn) as mock_connect:
            db = Database()

        mock_connect.assert_called_once()
        # Private attr accessed via name-mangling.
        self.assertIsNotNone(db._Database__connection)
        self.assertIs(db._Database__connection, mock_conn)

    def test_init_failure_leaves_connection_none(self):
        with patch(
            "app.models.database.pymysql.connect",
            side_effect=pymysql.MySQLError("boom"),
        ):
            db = Database()

        self.assertIsNone(db._Database__connection)

    # ── fetch_one ─────────────────────────────────────────────────────────

    def test_fetch_one_returns_row_and_uses_cursor(self):
        mock_conn, mock_cursor = self._make_connection_mock(fetchone={"id": 1})
        with patch("app.models.database.pymysql.connect", return_value=mock_conn):
            db = Database()
            result = db.fetch_one("SELECT 1", ("a",))

        self.assertEqual(result, {"id": 1})
        mock_cursor.execute.assert_called_once_with("SELECT 1", ("a",))
        mock_cursor.fetchone.assert_called_once_with()
        mock_cursor.close.assert_called_once_with()

    def test_fetch_one_default_params_is_none(self):
        mock_conn, mock_cursor = self._make_connection_mock(fetchone=None)
        with patch("app.models.database.pymysql.connect", return_value=mock_conn):
            db = Database()
            result = db.fetch_one("SELECT 1")

        self.assertIsNone(result)
        mock_cursor.execute.assert_called_once_with("SELECT 1", None)

    # ── fetch_all ─────────────────────────────────────────────────────────

    def test_fetch_all_returns_list_and_uses_cursor(self):
        rows = [{"id": 1}, {"id": 2}]
        mock_conn, mock_cursor = self._make_connection_mock(fetchall=rows)
        with patch("app.models.database.pymysql.connect", return_value=mock_conn):
            db = Database()
            result = db.fetch_all("SELECT * FROM t", ("x",))

        self.assertEqual(result, rows)
        mock_cursor.execute.assert_called_once_with("SELECT * FROM t", ("x",))
        mock_cursor.fetchall.assert_called_once_with()
        mock_cursor.close.assert_called_once_with()

    # ── execute ───────────────────────────────────────────────────────────

    def test_execute_commits_and_closes_cursor(self):
        mock_conn, mock_cursor = self._make_connection_mock()
        with patch("app.models.database.pymysql.connect", return_value=mock_conn):
            db = Database()
            db.execute("INSERT INTO t VALUES (%s)", ("v",))

        mock_cursor.execute.assert_called_once_with("INSERT INTO t VALUES (%s)", ("v",))
        mock_conn.commit.assert_called_once_with()
        mock_cursor.close.assert_called_once_with()

    # ── no-connection paths ───────────────────────────────────────────────

    def test_fetch_one_without_connection_raises_runtime_error(self):
        with patch(
            "app.models.database.pymysql.connect",
            side_effect=pymysql.MySQLError("no db"),
        ):
            db = Database()
        with self.assertRaises(RuntimeError) as ctx:
            db.fetch_one("SELECT 1")
        self.assertEqual(str(ctx.exception), "No database connection available")

    def test_fetch_all_without_connection_raises_runtime_error(self):
        with patch(
            "app.models.database.pymysql.connect",
            side_effect=pymysql.MySQLError("no db"),
        ):
            db = Database()
        with self.assertRaises(RuntimeError):
            db.fetch_all("SELECT 1")

    def test_execute_without_connection_raises_runtime_error(self):
        with patch(
            "app.models.database.pymysql.connect",
            side_effect=pymysql.MySQLError("no db"),
        ):
            db = Database()
        with self.assertRaises(RuntimeError):
            db.execute("INSERT INTO t VALUES (1)")

    # ── close ─────────────────────────────────────────────────────────────

    def test_close_closes_connection_and_clears_attr(self):
        mock_conn, _ = self._make_connection_mock()
        with patch("app.models.database.pymysql.connect", return_value=mock_conn):
            db = Database()
        db.close()

        mock_conn.close.assert_called_once_with()
        self.assertIsNone(db._Database__connection)

    def test_close_twice_does_not_raise(self):
        mock_conn, _ = self._make_connection_mock()
        with patch("app.models.database.pymysql.connect", return_value=mock_conn):
            db = Database()
        db.close()
        # Second call: __connection is already None, must be a safe no-op.
        db.close()
        self.assertIsNone(db._Database__connection)
        # close() on the real connection only happened the first time.
        mock_conn.close.assert_called_once_with()

    # ── create_tables (staticmethod) ──────────────────────────────────────

    def test_create_tables_executes_many_statements(self):
        # DESCRIBE branches read fetchall -> list of {"Field": ...} dicts; the
        # column-name comprehensions only need the 'Field' key to exist.
        column_rows = [
            {"Field": "title"},
            {"Field": "content"},
            {"Field": "author"},
            {"Field": "category_id"},
            {"Field": "category"},
            {"Field": "votes"},
            {"Field": "created_at"},
            {"Field": "thread_type"},
            {"Field": "is_verified"},
            {"Field": "verification_token"},
            {"Field": "token_expires_at"},
            {"Field": "show_online_status"},
            {"Field": "bio"},
            {"Field": "profile_pic"},
            {"Field": "is_active"},
            {"Field": "deletion_token"},
            {"Field": "deletion_token_expires_at"},
            {"Field": "post_type"},
            {"Field": "description"},
            {"Field": "owner_id"},
            {"Field": "name"},
        ]
        mock_conn, mock_cursor = self._make_connection_mock()
        # fetchall feeds DESCRIBE / SELECT name lookups; fetchone (admin) -> None
        # so the admin INSERT branch runs without raising.
        mock_cursor.fetchall.return_value = column_rows
        mock_cursor.fetchone.return_value = None

        with patch("app.models.database.pymysql.connect", return_value=mock_conn):
            # Must not raise; create_tables() wraps extras in try/except.
            Database.create_tables()

        self.assertGreater(mock_cursor.execute.call_count, 5)
        # Connection is closed at the end of create_tables().
        mock_conn.close.assert_called_once_with()

    def test_create_tables_skips_when_no_connection(self):
        with patch(
            "app.models.database.pymysql.connect",
            side_effect=pymysql.MySQLError("no db"),
        ):
            # Should detect the missing connection and return without raising.
            Database.create_tables()  # no assertion needed beyond "did not raise"


if __name__ == "__main__":
    unittest.main()

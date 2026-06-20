"""Comprehensive tests for app/models/database.py — the ``Database`` class.

Tests database connection, query execution (fetch_one, fetch_all, execute),
and error handling with proper mocking of pymysql connections.

Techniques used: unittest.TestCase, assert methods, unittest.mock,
MagicMock/patch for pymysql connection.
"""

import unittest
from unittest.mock import patch, MagicMock, call


class DatabaseTests(unittest.TestCase):
    """Comprehensive tests for Database class using pymysql mocking."""

    # ── __init__ and connection ────────────────────────────────────────────

    @patch("app.models.database.pymysql.connect")
    def test_init_creates_connection_with_valid_config(self, mock_connect):
        """Database() creates a connection with valid config."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        
        self.assertIsNotNone(db)
        mock_connect.assert_called_once()

    @patch("app.models.database.pymysql.connect")
    def test_init_handles_connection_failure(self, mock_connect):
        """Database() gracefully handles connection failure."""
        import pymysql
        mock_connect.side_effect = pymysql.MySQLError("Connection failed")
        
        from app.models.database import Database
        # Should not raise an exception during instantiation
        try:
            db = Database()
            # Connection should be set to None on failure
            self.assertIsNotNone(db)
        except Exception as e:
            self.fail(f"Database() raised {type(e).__name__} on connection failure")

    # ── fetch_one ──────────────────────────────────────────────────────────

    @patch("app.models.database.pymysql.connect")
    def test_fetch_one_returns_dict(self, mock_connect):
        """fetch_one returns a dict-like object for a single row."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {"id": 1, "name": "Alice"}
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        result = db.fetch_one("SELECT * FROM users WHERE id = %s", (1,))
        
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 1)
        self.assertEqual(result["name"], "Alice")

    @patch("app.models.database.pymysql.connect")
    def test_fetch_one_returns_none_for_no_rows(self, mock_connect):
        """fetch_one returns None when no rows match."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        result = db.fetch_one("SELECT * FROM users WHERE id = %s", (999,))
        
        self.assertIsNone(result)

    @patch("app.models.database.pymysql.connect")
    def test_fetch_one_without_params(self, mock_connect):
        """fetch_one works without parameters."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {"count": 5}
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        result = db.fetch_one("SELECT COUNT(*) as count FROM users")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["count"], 5)

    @patch("app.models.database.pymysql.connect")
    def test_fetch_one_with_empty_params(self, mock_connect):
        """fetch_one handles empty parameter list."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {"name": "John"}
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        result = db.fetch_one("SELECT name FROM users LIMIT 1", [])
        
        self.assertIsNotNone(result)

    @patch("app.models.database.pymysql.connect")
    def test_fetch_one_with_tuple_params(self, mock_connect):
        """fetch_one handles tuple parameters."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {"email": "test@test.com"}
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        result = db.fetch_one("SELECT email FROM users WHERE id = %s", (1,))
        
        self.assertIsNotNone(result)

    # ── fetch_all ──────────────────────────────────────────────────────────

    @patch("app.models.database.pymysql.connect")
    def test_fetch_all_returns_list_of_dicts(self, mock_connect):
        """fetch_all returns a list of dicts for multiple rows."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        result = db.fetch_all("SELECT id, name FROM users")
        
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    @patch("app.models.database.pymysql.connect")
    def test_fetch_all_returns_empty_list_for_no_rows(self, mock_connect):
        """fetch_all returns empty list when no rows match."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        result = db.fetch_all("SELECT * FROM users WHERE id = %s", (999,))
        
        self.assertEqual(result, [])

    @patch("app.models.database.pymysql.connect")
    def test_fetch_all_with_params(self, mock_connect):
        """fetch_all works with parameters."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "Alice", "email": "alice@test.com"}
        ]
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        result = db.fetch_all("SELECT * FROM users WHERE role = %s", ("admin",))
        
        self.assertEqual(len(result), 1)

    # ── execute ────────────────────────────────────────────────────────────

    @patch("app.models.database.pymysql.connect")
    def test_execute_insert(self, mock_connect):
        """execute performs INSERT operations."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        db.execute(
            "INSERT INTO users (name, email) VALUES (%s, %s)",
            ("Charlie", "charlie@test.com")
        )
        
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch("app.models.database.pymysql.connect")
    def test_execute_update(self, mock_connect):
        """execute performs UPDATE operations."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        db.execute(
            "UPDATE users SET name = %s WHERE id = %s",
            ("Alice2", 1)
        )
        
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch("app.models.database.pymysql.connect")
    def test_execute_delete(self, mock_connect):
        """execute performs DELETE operations."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        db.execute("DELETE FROM users WHERE id = %s", (999,))
        
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch("app.models.database.pymysql.connect")
    def test_execute_without_params(self, mock_connect):
        """execute works without parameters."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        db.execute("DELETE FROM temporary_table")
        
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    # ── close ──────────────────────────────────────────────────────────────

    @patch("app.models.database.pymysql.connect")
    def test_close_closes_connection(self, mock_connect):
        """close() closes the database connection."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        db.close()
        
        mock_conn.close.assert_called_once()

    # ── Integration scenarios ──────────────────────────────────────────────

    @patch("app.models.database.pymysql.connect")
    def test_fetch_one_then_execute(self, mock_connect):
        """Database handles fetch_one followed by execute."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {"id": 1, "verified": 0}
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        
        # First fetch
        user = db.fetch_one("SELECT * FROM users WHERE id = %s", (1,))
        self.assertIsNotNone(user)
        
        # Then execute
        db.execute("UPDATE users SET verified = %s WHERE id = %s", (1, 1))
        mock_conn.commit.assert_called()

    @patch("app.models.database.pymysql.connect")
    def test_multiple_fetch_all_calls(self, mock_connect):
        """Database handles multiple fetch_all calls."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        
        # Different return values for different calls
        mock_cursor.fetchall.side_effect = [
            [{"id": 1, "name": "Alice"}],
            [{"id": 1, "community_id": 5}],
        ]
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        
        users = db.fetch_all("SELECT * FROM users")
        communities = db.fetch_all("SELECT * FROM community_members WHERE user_id = %s", (1,))
        
        self.assertEqual(len(users), 1)
        self.assertEqual(len(communities), 1)

    @patch("app.models.database.pymysql.connect")
    def test_fetch_all_with_large_result_set(self, mock_connect):
        """fetch_all handles large result sets."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        
        # Simulate 100 rows
        large_result = [{"id": i, "name": f"User{i}"} for i in range(100)]
        mock_cursor.fetchall.return_value = large_result
        mock_connect.return_value = mock_conn
        
        from app.models.database import Database
        db = Database()
        result = db.fetch_all("SELECT * FROM users")
        
        self.assertEqual(len(result), 100)


if __name__ == "__main__":
    unittest.main()

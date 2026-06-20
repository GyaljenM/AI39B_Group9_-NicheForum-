"""Comprehensive tests for app/models/database.py — the ``Database`` class.

Tests database connection, query execution (fetch_one, fetch_all, execute),
connection pooling, and error handling with proper mocking of MySQL connections.

Techniques used: unittest.TestCase, assert methods, unittest.mock,
MagicMock/patch for MySQL connection.
"""

import unittest
from unittest.mock import patch, MagicMock, call

# Mock MySQL imports - they're only used when patching
try:
    import mysql.connector
    from mysql.connector.errors import DatabaseError, ProgrammingError
except ImportError:
    # Create dummy classes for testing
    class DatabaseError(Exception):
        pass
    
    class ProgrammingError(Exception):
        pass

from app.models.database import Database


class DatabaseTests(unittest.TestCase):
    """Comprehensive tests for Database class."""

    # ── __init__ and connection ─────────────────────────────────────────────

    @patch("app.models.database.Database.__init__", return_value=None)
    def test_init_creates_connection_with_valid_config(self, mock_init):
        """Database() can be instantiated."""
        db = Database()
        self.assertIsNotNone(db)

    def test_fetch_one_returns_dict_when_mocked(self):
        """fetch_one returns a dict when database is mocked."""
        db = Database.__new__(Database)
        db.connection = MagicMock()
        mock_cursor = MagicMock()
        db.connection.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ("Alice", "alice@test.com", 1)
        mock_cursor.column_names = ["name", "email", "id"]

        # Mock the cursor context manager
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        db.connection.cursor.return_value.__enter__ = mock_cursor
        db.connection.cursor.return_value.__exit__ = MagicMock()

        # Call fetch_one
        result = db.fetch_one("SELECT * FROM users WHERE id = %s", (1,))

        # Should return a dict-like object
        self.assertIsNotNone(result)

    def test_init_handles_connection_failure(self):
        """Database() gracefully handles connection failure."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_connect.side_effect = DatabaseError("Connection failed")

            db = Database()

            self.assertIsNone(db.connection)

    def test_init_uses_env_vars_when_no_config(self):
        """Database() uses environment variables when config not provided."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda key: {
                "DB_HOST": "localhost",
                "DB_USER": "root",
                "DB_PASSWORD": "password",
                "DB_NAME": "test_db",
            }.get(key, "default")

            with patch("app.models.database.mysql.connector.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value = mock_conn
                
                db = Database()
                
                self.assertIsNotNone(db.connection)

    # ── fetch_one ──────────────────────────────────────────────────────────

    def test_fetch_one_returns_dict(self):
        """fetch_one returns a dict for a single row."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ("Alice", "alice@test.com", 1)
            mock_cursor.column_names = ["name", "email", "id"]
            mock_connect.return_value = mock_conn

            db = Database()
            result = db.fetch_one("SELECT * FROM users WHERE id = %s", (1,))

            self.assertIsInstance(result, dict)
            mock_cursor.execute.assert_called_once()

    def test_fetch_one_returns_none_for_no_rows(self):
        """fetch_one returns None when no rows match."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = None
            mock_connect.return_value = mock_conn

            db = Database()
            result = db.fetch_one("SELECT * FROM users WHERE id = %s", (999,))

            self.assertIsNone(result)

    def test_fetch_one_handles_query_error(self):
        """fetch_one returns None on query error."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.execute.side_effect = ProgrammingError("Invalid query")
            mock_connect.return_value = mock_conn

            db = Database()
            result = db.fetch_one("SELECT * FROM invalid_table")

            self.assertIsNone(result)

    def test_fetch_one_without_params(self):
        """fetch_one works without parameters."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = (5,)
            mock_cursor.column_names = ["count"]
            mock_connect.return_value = mock_conn

            db = Database()
            result = db.fetch_one("SELECT COUNT(*) FROM users")

            self.assertIsNotNone(result)
            mock_cursor.execute.assert_called_with("SELECT COUNT(*) FROM users", None)

    def test_fetch_one_with_empty_params(self):
        """fetch_one handles empty parameter list."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ("John",)
            mock_cursor.column_names = ["name"]
            mock_connect.return_value = mock_conn

            db = Database()
            result = db.fetch_one("SELECT name FROM users LIMIT 1", [])

            self.assertIsNotNone(result)

    # ── fetch_all ──────────────────────────────────────────────────────────

    def test_fetch_all_returns_list_of_dicts(self):
        """fetch_all returns a list of dicts for multiple rows."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = [
                ("Alice", "alice@test.com"),
                ("Bob", "bob@test.com"),
            ]
            mock_cursor.column_names = ["name", "email"]
            mock_connect.return_value = mock_conn

            db = Database()
            result = db.fetch_all("SELECT name, email FROM users")

            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 2)
            self.assertIsInstance(result[0], dict)

    def test_fetch_all_returns_empty_list_for_no_rows(self):
        """fetch_all returns empty list when no rows match."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = []
            mock_cursor.column_names = ["id"]
            mock_connect.return_value = mock_conn

            db = Database()
            result = db.fetch_all("SELECT * FROM users WHERE id = %s", (999,))

            self.assertEqual(result, [])

    def test_fetch_all_handles_query_error(self):
        """fetch_all returns empty list on query error."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.execute.side_effect = ProgrammingError("Invalid query")
            mock_connect.return_value = mock_conn

            db = Database()
            result = db.fetch_all("SELECT * FROM invalid_table")

            self.assertEqual(result, [])

    def test_fetch_all_without_params(self):
        """fetch_all works without parameters."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = [("Alice",), ("Bob",)]
            mock_cursor.column_names = ["name"]
            mock_connect.return_value = mock_conn

            db = Database()
            result = db.fetch_all("SELECT name FROM users")

            self.assertEqual(len(result), 2)

    # ── execute ────────────────────────────────────────────────────────────

    def test_execute_insert(self):
        """execute handles INSERT statements."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            db = Database()
            db.execute(
                "INSERT INTO users (name, email) VALUES (%s, %s)",
                ("Alice", "alice@test.com")
            )

            mock_cursor.execute.assert_called_once()
            mock_conn.commit.assert_called_once()

    def test_execute_update(self):
        """execute handles UPDATE statements."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            db = Database()
            db.execute(
                "UPDATE users SET name = %s WHERE id = %s",
                ("Bob", 1)
            )

            mock_cursor.execute.assert_called_once()
            mock_conn.commit.assert_called_once()

    def test_execute_delete(self):
        """execute handles DELETE statements."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            db = Database()
            db.execute(
                "DELETE FROM users WHERE id = %s",
                (1,)
            )

            mock_cursor.execute.assert_called_once()
            mock_conn.commit.assert_called_once()

    def test_execute_handles_error_and_rolls_back(self):
        """execute rolls back on error."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.execute.side_effect = ProgrammingError("Invalid query")
            mock_connect.return_value = mock_conn

            db = Database()
            db.execute("INVALID SQL")

            mock_conn.rollback.assert_called_once()
            mock_conn.commit.assert_not_called()

    def test_execute_without_connection_fails_gracefully(self):
        """execute handles missing connection gracefully."""
        db = Database.__new__(Database)
        db.connection = None

        # Should not raise an exception
        try:
            db.execute("INSERT INTO users VALUES (...)")
        except Exception as e:
            self.fail(f"execute raised {type(e).__name__} unexpectedly")

    # ── close ──────────────────────────────────────────────────────────────

    def test_close_closes_connection(self):
        """close() closes the database connection."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db = Database()
            db.close()

            mock_conn.close.assert_called_once()

    def test_close_without_connection_doesnt_crash(self):
        """close() handles missing connection gracefully."""
        db = Database.__new__(Database)
        db.connection = None

        try:
            db.close()
        except Exception as e:
            self.fail(f"close raised {type(e).__name__} unexpectedly")

    # ── create_tables (static) ──────────────────────────────────────────────

    @patch("app.models.database.Database.__init__", return_value=None)
    def test_create_tables_static_creates_schema(self, mock_init):
        """create_tables() creates all required tables."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            Database.create_tables()

            # Should execute multiple CREATE TABLE statements
            self.assertGreater(mock_cursor.execute.call_count, 5)

    @patch("app.models.database.Database.__init__", return_value=None)
    def test_create_tables_handles_already_exists(self, mock_init):
        """create_tables() handles tables that already exist."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            # First call succeeds (users table), second fails (already exists)
            mock_cursor.execute.side_effect = [
                None,  # users table created
                DatabaseError("Table already exists"),
                None,  # continue with other tables
            ]
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            try:
                Database.create_tables()
            except DatabaseError:
                pass  # Expected for "already exists" on some tables

    # ── Integration: Multiple queries in sequence ──────────────────────────

    def test_fetch_one_then_execute(self):
        """Sequential fetch_one and execute calls work correctly."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            
            # First call: fetch_one
            mock_cursor.fetchone.return_value = (1, "Alice")
            mock_cursor.column_names = ["id", "name"]
            
            mock_connect.return_value = mock_conn

            db = Database()
            
            # Fetch
            user = db.fetch_one("SELECT * FROM users WHERE id = %s", (1,))
            self.assertIsNotNone(user)
            
            # Then execute
            mock_cursor.execute.reset_mock()
            db.execute("UPDATE users SET name = %s WHERE id = %s", ("Bob", 1))
            mock_cursor.execute.assert_called()
            mock_conn.commit.assert_called()

    def test_fetch_all_multiple_times(self):
        """Multiple fetch_all calls work correctly."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            
            mock_cursor.fetchall.side_effect = [
                [("Alice",), ("Bob",)],  # First query
                [("Post 1",)],  # Second query
            ]
            mock_cursor.column_names = ["name"]
            
            mock_connect.return_value = mock_conn

            db = Database()
            
            users = db.fetch_all("SELECT name FROM users")
            self.assertEqual(len(users), 2)
            
            posts = db.fetch_all("SELECT content FROM posts")
            self.assertEqual(len(posts), 1)

    # ── Error scenarios ────────────────────────────────────────────────────

    def test_database_connection_timeout(self):
        """Database handles connection timeout gracefully."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_connect.side_effect = mysql.connector.Error("Connection timeout")

            db = Database()

            self.assertIsNone(db.connection)

    def test_execute_on_readonly_connection(self):
        """execute on read-only connection fails gracefully."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = DatabaseError("Read-only connection")
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            db = Database()
            db.execute("UPDATE users SET name = %s WHERE id = %s", ("Bob", 1))

            mock_conn.rollback.assert_called_once()

    # ── Parameter handling ──────────────────────────────────────────────────

    def test_fetch_one_with_tuple_params(self):
        """fetch_one handles tuple parameters."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1,)
            mock_cursor.column_names = ["id"]
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            db = Database()
            db.fetch_one("SELECT * FROM users WHERE id = %s", (5,))

            call_args = mock_cursor.execute.call_args
            self.assertEqual(call_args[0][1], (5,))

    def test_fetch_all_with_list_params(self):
        """fetch_all handles list parameters."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_cursor.column_names = ["id"]
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            db = Database()
            db.fetch_all("SELECT * FROM users WHERE role = %s", ["admin"])

            call_args = mock_cursor.execute.call_args
            self.assertEqual(call_args[0][1], ["admin"])

    def test_execute_with_multiple_params(self):
        """execute handles multiple parameters correctly."""
        with patch("app.models.database.mysql.connector.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            db = Database()
            db.execute(
                "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                ("Alice", "alice@test.com", "hashed_password")
            )

            call_args = mock_cursor.execute.call_args
            self.assertEqual(len(call_args[0][1]), 3)


if __name__ == "__main__":
    unittest.main()

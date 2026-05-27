import pymysql
import config

class Database:
    def __init__(self):
        """Open a database connection when object is created."""
        # Initialize connection attribute first so other methods can check it
        self.__connection = None
        try:
            self.__connection = pymysql.connect(
                host=config.MYSQL_HOST,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                database=config.MYSQL_DB,
                cursorclass=pymysql.cursors.DictCursor,
            )

            print("Database connected successfully!")

        except pymysql.MySQLError as e:
            print("Database connection failed!")
            print("Error:", e)
 
    def fetch_one(self, query, params=None):
        """Run a query and return ONE result (or None)."""
        if not self.__connection:
            raise RuntimeError("No database connection available")
        cursor = self.__connection.cursor()
        cursor.execute(query, params)
        result = cursor.fetchone()
        cursor.close()
        return result

    def fetch_all(self, query, params=None):
        """Run a query and return ALL results as a list."""
        if not self.__connection:
            raise RuntimeError("No database connection available")
        cursor = self.__connection.cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        return results

    def execute(self, query, params=None):
        """Run a query that changes data (INSERT, UPDATE, DELETE)."""
        if not self.__connection:
            raise RuntimeError("No database connection available")
        cursor = self.__connection.cursor()
        cursor.execute(query, params)
        self.__connection.commit()
        cursor.close()

    def close(self):
        """Close the database connection."""
        self.__connection.close()

                        
    # ── Static Method: Create tables on app startup ─────────

    @staticmethod
    def create_tables():
        """
        Create database tables if they don't exist.

        @staticmethod: belongs to the class but doesn't need
        'self' — it doesn't use any instance data.
        You call it as: Database.create_tables()
        """
        db = Database()
        # If connection failed, skip creating tables to avoid runtime errors
        if not db._Database__connection:
            print("Skipping table creation: no database connection")
            return

        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                is_verified TINYINT DEFAULT 0,
                verification_token VARCHAR(255),
                token_expires_at DATETIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) 
        # Create default admin if not exists
        admin = db.fetch_one(
            "SELECT * FROM users WHERE email = %s", ("admin@admin.com",)
        )
        if not admin:
            from werkzeug.security import generate_password_hash

            db.execute(
                "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                ("Admin", "admin@admin.com", generate_password_hash("admin123"), "admin"),
            )

        db.close()
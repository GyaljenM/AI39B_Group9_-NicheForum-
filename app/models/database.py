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
            CREATE TABLE IF NOT EXISTS categories (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

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

        db.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                author VARCHAR(100) NOT NULL,
                category_id INT,
                category VARCHAR(100) DEFAULT 'Sports',
                votes INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
            )
        """)

        # Fix for existing tables missing the category_id column
        try:
            columns = db.fetch_all("DESCRIBE threads")
            column_names = [col['Field'] for col in columns]
            
            if 'category_id' not in column_names:
                print("Adding missing category_id column to threads table...")
                db.execute("ALTER TABLE threads ADD COLUMN category_id INT AFTER author")
                db.execute("ALTER TABLE threads ADD CONSTRAINT fk_category FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL")
        except Exception as e:
            print(f"Error updating threads table structure: {e}")

        db.execute("""
            CREATE TABLE IF NOT EXISTS replies (
                id INT AUTO_INCREMENT PRIMARY KEY,
                thread_id INT NOT NULL,
                content TEXT NOT NULL,
                user_email VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE
            )
        """)

        # Seed categories if they don't exist
        try:
            existing_cats = db.fetch_all("SELECT name FROM categories")
            cat_names = [c['name'] for c in existing_cats]
            for cat in ['Sports', 'eSports', 'Strategy', 'News']:
                if cat not in cat_names:
                    db.execute("INSERT INTO categories (name) VALUES (%s)", (cat,))
        except Exception as e:
            print(f"Error seeding categories: {e}")

        # Create default admin if not exists
        try:
            admin = db.fetch_one(
                "SELECT * FROM users WHERE email = %s", ("admin@admin.com",)
            )
            if not admin:
                from werkzeug.security import generate_password_hash
                db.execute(
                    "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                    ("Admin", "admin@admin.com", generate_password_hash("admin123"), "admin"),
                )
        except Exception as e:
            print(f"Error creating admin: {e}")

        db.close()
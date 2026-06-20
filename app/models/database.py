import os
import pymysql

# Try to import project config from top-level `config.py`. If that fails
# (for example when running as a package), fall back to environment
# variables so the app can still run in different execution contexts.
try:
    import config as project_config
except Exception:
    try:
        from app import config as project_config
    except Exception:
        project_config = None

class Database:
    def __init__(self):
        """Open a database connection when object is created."""
        # Initialize connection attribute first so other methods can check it
        self.__connection = None
        try:
            host = getattr(project_config, "MYSQL_HOST", os.getenv("MYSQL_HOST", "localhost"))
            user = getattr(project_config, "MYSQL_USER", os.getenv("MYSQL_USER", "root"))
            password = getattr(project_config, "MYSQL_PASSWORD", os.getenv("MYSQL_PASSWORD", ""))
            database = getattr(project_config, "MYSQL_DB", os.getenv("MYSQL_DB", None))

            self.__connection = pymysql.connect(
                host=host,
                user=user,
                password=password,
                database=database,
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
        """Convert sqlite3 row to dictionary."""
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

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
        try:
            if self.__connection:
                self.__connection.close()
        except Exception:
            # Ignore errors when connection is already closed
            pass
        finally:
            self.__connection = None

                        
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
                bio TEXT,
                profile_pic VARCHAR(255),
                is_verified TINYINT DEFAULT 0,
                verification_token VARCHAR(255),
                token_expires_at DATETIME,
                is_active TINYINT NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Communities and posts tables used by the HomeRoutes and templates
        db.execute("""
            CREATE TABLE IF NOT EXISTS communities (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                category VARCHAR(100) DEFAULT 'Sports',
                owner_id INT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                community_id INT NOT NULL,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                post_type ENUM('text','media','poll') NOT NULL DEFAULT 'text',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (community_id) REFERENCES communities(id) ON DELETE CASCADE
            )
        """)

        # Ensure existing installations get the verification columns if they are missing
        try:
            user_cols = db.fetch_all("DESCRIBE users")
            user_col_names = [c['Field'] for c in user_cols]

            if 'is_verified' not in user_col_names:
                db.execute("ALTER TABLE users ADD COLUMN is_verified TINYINT DEFAULT 0 AFTER role")
            if 'verification_token' not in user_col_names:
                db.execute("ALTER TABLE users ADD COLUMN verification_token VARCHAR(255) AFTER is_verified")
            if 'token_expires_at' not in user_col_names:
                db.execute("ALTER TABLE users ADD COLUMN token_expires_at DATETIME AFTER verification_token")
        except Exception as e:
            print(f"Error ensuring users table verification columns: {e}")

        db.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                thread_type ENUM('text','media','poll') NOT NULL DEFAULT 'text',
                author VARCHAR(100) DEFAULT 'anonymous',
                category_id INT,
                category VARCHAR(100) DEFAULT 'Sports',
                votes INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
            )
        """)

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

        db.execute("""
            CREATE TABLE IF NOT EXISTS reply_votes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                reply_id INT NOT NULL,
                vote_type ENUM('like', 'dislike') NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_reply (user_id, reply_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (reply_id) REFERENCES replies(id) ON DELETE CASCADE
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS community_members (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                community_id INT NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (community_id) REFERENCES communities(id) ON DELETE CASCADE
            )
        """)

        # Likes / dislikes on community posts. One row per (user, post) so a
        # user can only have a single active vote; the vote_type column tells
        # us whether it is a like or a dislike.
        db.execute("""
            CREATE TABLE IF NOT EXISTS post_votes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                post_id INT NOT NULL,
                vote_type ENUM('like', 'dislike') NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_post (user_id, post_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
            )
        """)

        # Replies / comments left on community posts.
        db.execute("""
            CREATE TABLE IF NOT EXISTS post_comments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                post_id INT NOT NULL,
                user_id INT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ── Media attachments + polls for community posts ──────────
        # Images/videos attached to a post (any post_type can carry media).
        db.execute("""
            CREATE TABLE IF NOT EXISTS post_media (
                id INT AUTO_INCREMENT PRIMARY KEY,
                post_id INT NOT NULL,
                media_type ENUM('image', 'video') NOT NULL,
                file_path VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
            )
        """)

        # Options belonging to a poll-type post.
        db.execute("""
            CREATE TABLE IF NOT EXISTS post_poll_options (
                id INT AUTO_INCREMENT PRIMARY KEY,
                post_id INT NOT NULL,
                option_text VARCHAR(255) NOT NULL,
                position INT DEFAULT 0,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
            )
        """)

        # One vote row per (user, post); changing a vote updates option_id.
        db.execute("""
            CREATE TABLE IF NOT EXISTS post_poll_votes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                option_id INT NOT NULL,
                post_id INT NOT NULL,
                user_id INT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_post_poll (user_id, post_id),
                FOREIGN KEY (option_id) REFERENCES post_poll_options(id) ON DELETE CASCADE,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ── Media attachments + polls for threads ──────────────────
        db.execute("""
            CREATE TABLE IF NOT EXISTS thread_media (
                id INT AUTO_INCREMENT PRIMARY KEY,
                thread_id INT NOT NULL,
                media_type ENUM('image', 'video') NOT NULL,
                file_path VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS thread_poll_options (
                id INT AUTO_INCREMENT PRIMARY KEY,
                thread_id INT NOT NULL,
                option_text VARCHAR(255) NOT NULL,
                position INT DEFAULT 0,
                FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE
            )
        """)

        # Poll voting requires a logged-in user even on guest-created threads.
        db.execute("""
            CREATE TABLE IF NOT EXISTS thread_poll_votes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                option_id INT NOT NULL,
                thread_id INT NOT NULL,
                user_id INT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_thread_poll (user_id, thread_id),
                FOREIGN KEY (option_id) REFERENCES thread_poll_options(id) ON DELETE CASCADE,
                FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ── Community notes (crowd-sourced context on possible misinformation) ──
        # Any logged-in user can attach a note to a post/thread; other users rate
        # it helpful/not-helpful and a note is only publicly promoted once it earns
        # enough net-helpful ratings (see NOTE_PROMOTE_THRESHOLD in HomeRoutes).
        db.execute("""
            CREATE TABLE IF NOT EXISTS post_notes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                post_id INT NOT NULL,
                user_id INT NOT NULL,
                content TEXT NOT NULL,
                source VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # One rating row per (user, note); changing a rating updates it.
        db.execute("""
            CREATE TABLE IF NOT EXISTS post_note_votes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                note_id INT NOT NULL,
                user_id INT NOT NULL,
                rating ENUM('helpful', 'not_helpful') NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_note (note_id, user_id),
                FOREIGN KEY (note_id) REFERENCES post_notes(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS thread_notes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                thread_id INT NOT NULL,
                user_id INT NOT NULL,
                content TEXT NOT NULL,
                source VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS thread_note_votes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                note_id INT NOT NULL,
                user_id INT NOT NULL,
                rating ENUM('helpful', 'not_helpful') NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_thread_note (note_id, user_id),
                FOREIGN KEY (note_id) REFERENCES thread_notes(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ── Content reports (users flag posts/threads for moderator review) ────
        # One open report per (user, item) via UNIQUE key; re-reporting updates the
        # existing row. Admins triage these on the /admin/reports page.
        db.execute("""
            CREATE TABLE IF NOT EXISTS post_reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                post_id INT NOT NULL,
                user_id INT NOT NULL,
                reason VARCHAR(50) NOT NULL,
                details TEXT,
                status ENUM('open', 'reviewed') NOT NULL DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_post_report (post_id, user_id),
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS thread_reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                thread_id INT NOT NULL,
                user_id INT NOT NULL,
                reason VARCHAR(50) NOT NULL,
                details TEXT,
                status ENUM('open', 'reviewed') NOT NULL DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_thread_report (thread_id, user_id),
                FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ── Per-community moderation (admin appoints moderators; both can ban) ──
        # A moderator is a user appointed to police one community. Site admins
        # (users.role='admin') implicitly moderate every community.
        db.execute("""
            CREATE TABLE IF NOT EXISTS community_moderators (
                id INT AUTO_INCREMENT PRIMARY KEY,
                community_id INT NOT NULL,
                user_id INT NOT NULL,
                appointed_by INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_community_moderator (community_id, user_id),
                FOREIGN KEY (community_id) REFERENCES communities(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Banned users are removed from a community and blocked from rejoining/posting.
        db.execute("""
            CREATE TABLE IF NOT EXISTS community_bans (
                id INT AUTO_INCREMENT PRIMARY KEY,
                community_id INT NOT NULL,
                user_id INT NOT NULL,
                banned_by INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_community_ban (community_id, user_id),
                FOREIGN KEY (community_id) REFERENCES communities(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ── User blocks (blocker_id blocks blocked_id) ─────────────────────
        # A block is directed but enforced both ways: if either user has blocked
        # the other they can't follow, message, or chat. Blocking also severs any
        # existing follow relationship (handled in the block route).
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_blocks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                blocker_id INT NOT NULL,
                blocked_id INT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_block (blocker_id, blocked_id),
                FOREIGN KEY (blocker_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (blocked_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ── Follows (Instagram-style: follower_id follows followee_id) ─────
        # One row per directed follow. Two users are "mutual followers" when
        # both directions exist; chat is gated on that (see ChatRoutes).
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_follows (
                id INT AUTO_INCREMENT PRIMARY KEY,
                follower_id INT NOT NULL,
                followee_id INT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user_follow (follower_id, followee_id),
                FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (followee_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ── Direct messages (1-to-1 chat between two users) ────────────────
        # Each row is one message from sender_id to receiver_id. Optional
        # share_* columns let a message carry a "shared card" (a link to a
        # community, a thread to create, or a live match) instead of / on top
        # of plain text.
        db.execute("""
            CREATE TABLE IF NOT EXISTS direct_messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                sender_id INT NOT NULL,
                receiver_id INT NOT NULL,
                content TEXT,
                share_type VARCHAR(20),
                share_label VARCHAR(255),
                share_url VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ── Notifications (in-app alerts) ──────────────────────────────────
        # One row per alert delivered to a single recipient (user_id). actor_id
        # is whoever triggered it (nullable for system messages). `type` groups
        # the alert ('follow', 'message', 'community_post', 'comment') so the UI
        # can pick an icon; `url` is where clicking the alert takes the user.
        db.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                actor_id INT,
                type VARCHAR(30) NOT NULL,
                message VARCHAR(500) NOT NULL,
                url VARCHAR(500),
                is_read TINYINT NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_unread (user_id, is_read),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        column_names = []
        try:
            columns = db.fetch_all("DESCRIBE threads")
            column_names = [col['Field'] for col in columns]

            if 'title' not in column_names:
                print("Adding missing title column to threads table...")
                db.execute("ALTER TABLE threads ADD COLUMN title VARCHAR(255) NOT NULL DEFAULT '' AFTER id")
            if 'content' not in column_names:
                print("Adding missing content column to threads table...")
                db.execute("ALTER TABLE threads ADD COLUMN content TEXT NULL DEFAULT '' AFTER title")
                if 'description' in column_names:
                    db.execute("UPDATE threads SET content = description WHERE content = ''")
            if 'author' not in column_names:
                print("Adding missing author column to threads table...")
                db.execute("ALTER TABLE threads ADD COLUMN author VARCHAR(100) DEFAULT 'anonymous' AFTER content")
            if 'category_id' not in column_names:
                print("Adding missing category_id column to threads table...")
                db.execute("ALTER TABLE threads ADD COLUMN category_id INT NULL AFTER author")
                db.execute("ALTER TABLE threads ADD CONSTRAINT fk_category FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL")
            if 'category' not in column_names:
                print("Adding missing category column to threads table...")
                db.execute("ALTER TABLE threads ADD COLUMN category VARCHAR(100) DEFAULT 'Sports' AFTER category_id")
            if 'votes' not in column_names:
                print("Adding missing votes column to threads table...")
                db.execute("ALTER TABLE threads ADD COLUMN votes INT DEFAULT 0 AFTER category")
            if 'created_at' not in column_names:
                print("Adding missing created_at column to threads table...")
                db.execute("ALTER TABLE threads ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            if 'thread_type' not in column_names:
                print("Adding missing thread_type column to threads table...")
                db.execute("ALTER TABLE threads ADD COLUMN thread_type ENUM('text','media','poll') NOT NULL DEFAULT 'text' AFTER content")
        except Exception as e:
            print(f"Error updating threads table structure: {e}")

        try:
            users_columns = db.fetch_all("DESCRIBE users")
            user_column_names = [col['Field'] for col in users_columns]
            if 'bio' not in user_column_names:
                print("Adding missing bio column to users table...")
                db.execute("ALTER TABLE users ADD COLUMN bio TEXT AFTER role")
            if 'profile_pic' not in user_column_names:
                print("Adding missing profile_pic column to users table...")
                db.execute("ALTER TABLE users ADD COLUMN profile_pic VARCHAR(255) AFTER bio")
            if 'is_active' not in user_column_names:
                print("Adding missing is_active column to users table...")
                db.execute("ALTER TABLE users ADD COLUMN is_active TINYINT NOT NULL DEFAULT 1")
            # Email-confirmed account deletion: a one-time token + its expiry.
            # Kept separate from verification_token so a pending deletion can't
            # collide with registration/password-reset flows.
            if 'deletion_token' not in user_column_names:
                print("Adding missing deletion_token column to users table...")
                db.execute("ALTER TABLE users ADD COLUMN deletion_token VARCHAR(255) NULL")
            if 'deletion_token_expires_at' not in user_column_names:
                print("Adding missing deletion_token_expires_at column to users table...")
                db.execute("ALTER TABLE users ADD COLUMN deletion_token_expires_at DATETIME NULL")
        except Exception as e:
            print(f"Error updating users table structure: {e}")

        try:
            posts_columns = db.fetch_all("DESCRIBE posts")
            post_column_names = [col['Field'] for col in posts_columns]
            if 'created_at' not in post_column_names:
                print("Adding missing created_at column to posts table...")
                db.execute("ALTER TABLE posts ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            if 'post_type' not in post_column_names:
                print("Adding missing post_type column to posts table...")
                db.execute("ALTER TABLE posts ADD COLUMN post_type ENUM('text','media','poll') NOT NULL DEFAULT 'text' AFTER content")
        except Exception:
            pass

        try:
            communities_columns = db.fetch_all("DESCRIBE communities")
            community_column_names = [col['Field'] for col in communities_columns]
            if 'description' not in community_column_names:
                print("Adding missing description column to communities table...")
                db.execute("ALTER TABLE communities ADD COLUMN description TEXT")
            if 'category' not in community_column_names:
                print("Adding missing category column to communities table...")
                db.execute("ALTER TABLE communities ADD COLUMN category VARCHAR(100) DEFAULT 'Sports'")
            if 'owner_id' not in community_column_names:
                print("Adding missing owner_id column to communities table...")
                db.execute("ALTER TABLE communities ADD COLUMN owner_id INT NULL AFTER category")
                db.execute("ALTER TABLE communities ADD CONSTRAINT fk_community_owner FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL")
        except Exception:
            pass

        try:
            replies_columns = db.fetch_all("DESCRIBE replies")
            reply_column_names = [col['Field'] for col in replies_columns]
            if 'created_at' not in reply_column_names:
                db.execute("ALTER TABLE replies ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass

        try:
            if 'description' in column_names and 'name' in column_names and 'title' in column_names:
                db.execute("UPDATE threads SET title = name WHERE title = '' AND name != ''")
                db.execute("UPDATE threads SET content = description WHERE content = '' AND description != ''")
        except Exception:
            pass

        # Seed core community categories
        try:
            existing_cats = db.fetch_all("SELECT name FROM categories")
            cat_names = [c['name'] for c in existing_cats]
            for cat in ['Football', 'Basketball', 'Tennis', 'Cricket', 'eSports', 'Combat Sports', 'Fitness']:
                if cat not in cat_names:
                    db.execute("INSERT INTO categories (name) VALUES (%s)", (cat,))
        except Exception as e:
            print(f"Error seeding categories: {e}")

        # Remove legacy placeholder communities that should no longer exist
        try:
            db.execute(
                "DELETE FROM communities WHERE name IN (%s, %s, %s, %s)",
                ('General Sports', 'eSports Hub', 'Strategy Lounge', 'Sports Newsroom')
            )
        except Exception as e:
            print(f"Error removing legacy communities: {e}")

        # Seed default communities if none exist
        try:
            existing_communities = db.fetch_all("SELECT name FROM communities")
            community_names = [c['name'] for c in existing_communities]
            # Ensure common sport hubs exist so the All Sports tab is populated
            default_comms = [
                'Basket Hub', 'Basketball Fanatics', 'Hoops Central',
                'Football Leagues', 'Football Fans', 'Soccer Tactics',
                'Tennis Club', 'Tennis Courts',
                'Cricket Grounds', 'Cricket Leagues', 'Cricket Fans',
                'Fitness & Training', 'Combat Arena'
            ]
            for comm in default_comms:
                if comm not in community_names:
                    # Determine a sensible category for seeded community names
                    cname = comm.lower()
                    if 'football' in cname or 'soccer' in cname:
                        cat = 'Football'
                    elif 'basket' in cname or 'hoop' in cname:
                        cat = 'Basketball'
                    elif 'tennis' in cname:
                        cat = 'Tennis'
                    elif 'cricket' in cname:
                        cat = 'Cricket'
                    elif 'combat' in cname or 'mma' in cname or 'box' in cname:
                        cat = 'Combat Sports'
                    elif 'fit' in cname or 'training' in cname or 'gym' in cname:
                        cat = 'Fitness'
                    else:
                        cat = 'Football'
                    db.execute("INSERT INTO communities (name, description, category) VALUES (%s, %s, %s)", (comm, f"The official hub for {comm} fans and discussion.", cat))
        except Exception as e:
            print(f"Error seeding communities: {e}")

        # Create default admin if not exists
        try:
            admin = db.fetch_one(
                "SELECT * FROM users WHERE email = %s", ("admin@admin.com",)
            )
            from werkzeug.security import generate_password_hash
            if not admin:
                db.execute(
                    "INSERT INTO users (name, email, password, role, is_verified, is_active) VALUES (%s, %s, %s, %s, %s, %s)",
                    ("Admin", "admin@admin.com", generate_password_hash("admin"), "admin", 1, 1),
                )
            elif admin.get("role") != "admin":
                # Account exists but isn't an admin — promote it so the
                # moderation queue always has an owner.
                db.execute(
                    "UPDATE users SET role = 'admin', is_active = 1 WHERE email = %s",
                    ("admin@admin.com",),
                )
        except Exception as e:
            print(f"Error creating admin: {e}")

        db.close()
"""Create or update an admin user safely.

Usage (from project root):
  python scripts/create_admin.py --email adimn@admin.com --password adimn

The script uses the app's `Database` helper so it respects the same DB
configuration as the application. Passwords are hashed with Werkzeug.
"""
import argparse
import sys
from werkzeug.security import generate_password_hash

sys.path.insert(0, "")  # allow importing app package when run from project root
from app.models.database import Database


def create_or_update_admin(email: str, password: str, name: str = "Admin"):
    db = Database()
    try:
        existing = db.fetch_one("SELECT * FROM users WHERE email = %s", (email,))
        hashed = generate_password_hash(password)

        if existing:
            # Update password, ensure role is admin and reactivate account
            db.execute(
                "UPDATE users SET password = %s, role = %s, is_active = 1 WHERE email = %s",
                (hashed, "admin", email),
            )
            print(f"Updated existing user '{email}' to admin and set new password.")
        else:
            db.execute(
                "INSERT INTO users (name, email, password, role, is_verified, is_active) VALUES (%s, %s, %s, %s, %s, %s)",
                (name, email, hashed, "admin", 1, 1),
            )
            print(f"Created new admin user '{email}'.")
    except Exception as e:
        print("Error creating/updating admin:", e)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Create or update an admin user in the database.")
    parser.add_argument("--email", required=False, default="admin@admin.com", help="Admin email to create/update")
    parser.add_argument("--password", required=False, default="admin", help="Password for the admin account")
    parser.add_argument("--name", required=False, default="Admin", help="Display name for the admin user")
    args = parser.parse_args()

    create_or_update_admin(args.email, args.password, args.name)


if __name__ == "__main__":
    main()

from flask import render_template, request, redirect, url_for, flash, session
from app.models.database import Database
from werkzeug.security import generate_password_hash, check_password_hash
from app.utils.email_utils import EmailService
from datetime import datetime, timedelta
import secrets

class AuthController:
    def login(self):
        if request.method == "POST":
            email = request.form.get("email")
            password = request.form.get("password")

            db = Database()
            user = db.fetch_one("SELECT * FROM users WHERE email = %s", (email,))

            print(f"DEBUG login attempt: email={email!r}, password provided={'yes' if password else 'no'}")
            print(f"DEBUG fetched user: {user}")
            if user and check_password_hash(user["password"], password):
                # Login directly - email verification is no longer mandatory for access

                # Reactivate a previously deactivated account on a successful login,
                # so deactivation is reversible (the user just logs back in).
                if not user.get("is_active", 1):
                    db.execute("UPDATE users SET is_active = 1 WHERE id = %s", (user["id"],))
                    flash("Welcome back! Your account has been reactivated.", "success")

                session["user_id"] = user["id"]
                session["user_name"] = user["name"]

                # Grant admin privileges for the specific admin email.
                if email and email.lower() in {"adim@gmail.com", "adimn@admin.com"}:
                    session["user_role"] = "admin"
                    if user["role"] != "admin":
                        db.execute("UPDATE users SET role = %s WHERE email = %s", ("admin", email))
                else:
                    session["user_role"] = user["role"]

                session["profile_pic"] = user.get("profile_pic")
                flash(f"Welcome back, {user['name']}!", "success")
                db.close()
                return redirect(url_for("Home.home"))
            else:
                flash("Incorrect email or password.", "danger")
            
            db.close()

        # Fetch live stats for auth page displays
        db = Database()
        total_communities = db.fetch_one("SELECT COUNT(*) AS count FROM communities")['count'] or 0
        total_members = db.fetch_one("SELECT COUNT(*) AS count FROM users")['count'] or 0
        online_now = db.fetch_one("SELECT COUNT(*) AS count FROM users WHERE is_active = 1")['count'] or 0
        db.close()

        return render_template("login.html", total_communities=total_communities, total_members=total_members, online_now=online_now)
    
    def register(self):
        if request.method == "POST":
            name = request.form.get("name")
            email = request.form.get("email")
            password = request.form.get("password")
            
            hashed_password = generate_password_hash(password)

            db = Database()
            existing_user = db.fetch_one("SELECT * FROM users WHERE email = %s", (email,))
            
            if existing_user:
                db.close()
                flash("An account with this email already exists.", "danger")
                return redirect(url_for("Auth.register"))

            try:
                # Generate OTP and store verification token, require verification before login
                otp_code = EmailService.generate_secure_otp()
                expiry_dt = datetime.utcnow() + timedelta(minutes=5)

                db.execute(
                    "INSERT INTO users (name, email, password, is_verified, verification_token, token_expires_at) VALUES (%s, %s, %s, 0, %s, %s)",
                    (name, email, hashed_password, otp_code, expiry_dt)
                )
                db.close()

                # Try sending the OTP email separately so email failures don't break registration
                email_sent = False
                try:
                    EmailService.send_otp(email, otp_code)
                    email_sent = True
                except Exception as email_err:
                    print(f"WARNING: Failed to send OTP email: {email_err}")

                if email_sent:
                    flash("Registration successful! A verification code was sent to your email.", "info")
                else:
                    flash("Registration successful! Check your email for the verification code. If not found, contact support.", "warning")

                return redirect(url_for("Auth.verify_registration", email=email))
            except Exception as e:
                if db:
                    try:
                        db.close()
                    except Exception:
                        pass
                print(f"ERROR: Registration failed: {e}")
                import traceback
                traceback.print_exc()
                flash("An error occurred during registration. Please try again.", "danger")

        # Fetch live stats for auth page displays
        db = Database()
        total_communities = db.fetch_one("SELECT COUNT(*) AS count FROM communities")['count'] or 0
        total_members = db.fetch_one("SELECT COUNT(*) AS count FROM users")['count'] or 0
        online_now = db.fetch_one("SELECT COUNT(*) AS count FROM users WHERE is_active = 1")['count'] or 0
        db.close()

        return render_template("register.html", total_communities=total_communities, total_members=total_members, online_now=online_now)

    def forgot_password(self):
        if request.method == "POST":
            email = request.form.get("email")
            db = Database()
            user = db.fetch_one("SELECT * FROM users WHERE email = %s", (email,))
            
            if user:
                otp_code = EmailService.generate_secure_otp()
                expiry_dt = datetime.utcnow() + timedelta(minutes=5)
                
                db.execute(
                    "UPDATE users SET verification_token = %s, token_expires_at = %s WHERE email = %s",
                    (otp_code, expiry_dt, email)
                )
                db.close()
                
                if EmailService.send_otp(email, otp_code):
                    flash("A password reset code has been sent to your email.", "info")
                    return redirect(url_for("Auth.reset_password", email=email))
                else:
                    flash("Failed to send reset code. Please try again.", "danger")
            else:
                db.close()
                flash("We couldn't find an account with that email.", "danger")
        
        return render_template("forgot_password.html")

    def reset_password(self):
        email = request.args.get("email") or request.form.get("email")
        
        if request.method == "POST":
            otp = request.form.get("otp")
            new_password = request.form.get("password")
            
            db = Database()
            user = db.fetch_one("SELECT * FROM users WHERE email = %s", (email,))
            
            if user and user["verification_token"] == otp:
                if datetime.utcnow() > user["token_expires_at"]:
                    db.close()
                    flash("Reset code has expired.", "danger")
                    return redirect(url_for("Auth.forgot_password"))
                
                hashed_password = generate_password_hash(new_password)
                db.execute(
                    "UPDATE users SET password = %s, verification_token = NULL, token_expires_at = NULL WHERE email = %s",
                    (hashed_password, email)
                )
                db.close()
                flash("Your password has been reset successfully. Please login.", "success")
                return redirect(url_for("Auth.login"))
            else:
                if db: db.close()
                flash("Invalid code or email reference.", "danger")
        
        return render_template("reset_password.html", email=email)

    def logout(self):
        session.clear()
        flash("Logged out successfully.", "info")
        return redirect(url_for("Auth.login"))

    def deactivate_account(self):
        """Deactivate the logged-in user's account.

        Sets users.is_active = 0 and ends the session. The account is not
        deleted — logging back in (see login()) reactivates it.
        """
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in first.", "warning")
            return redirect(url_for("Auth.login"))

        db = Database()
        db.execute("UPDATE users SET is_active = 0 WHERE id = %s", (user_id,))
        db.close()

        session.clear()
        flash("Your account has been deactivated. Log in any time to reactivate it.", "info")
        return redirect(url_for("Auth.login"))

    @staticmethod
    def _mask_email(email):
        """Partially mask an email for display, e.g. 'j***e@gmail.com'."""
        try:
            local, domain = email.split("@", 1)
        except (ValueError, AttributeError):
            return email
        if len(local) <= 2:
            masked = local[:1] + "*"
        else:
            masked = local[0] + "*" * (len(local) - 2) + local[-1]
        return f"{masked}@{domain}"

    def request_account_deletion(self):
        """Start the OTP-confirmed account deletion flow.

        Generates a 6-digit code, stores it on the user row with a 5-minute
        expiry, and emails it. The account is NOT touched until the user submits
        the matching code (see confirm_account_deletion). This is called via
        fetch() from the delete-account modal, so it answers AJAX callers with
        JSON and falls back to a flash+redirect for non-AJAX requests.
        """
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        user_id = session.get("user_id")
        if not user_id:
            if is_ajax:
                return {"ok": False, "error": "Please log in first."}, 401
            flash("Please log in first.", "warning")
            return redirect(url_for("Auth.login"))

        db = Database()
        user = db.fetch_one("SELECT id, name, email FROM users WHERE id = %s", (user_id,))
        if not user:
            db.close()
            session.clear()
            if is_ajax:
                return {"ok": False, "error": "Account not found."}, 404
            flash("Account not found.", "danger")
            return redirect(url_for("Auth.login"))

        otp_code = EmailService.generate_secure_otp()
        expiry_dt = datetime.utcnow() + timedelta(minutes=5)
        db.execute(
            "UPDATE users SET deletion_token = %s, deletion_token_expires_at = %s WHERE id = %s",
            (otp_code, expiry_dt, user_id),
        )
        db.close()

        sent = EmailService.send_otp(user["email"], otp_code)
        if sent:
            if is_ajax:
                return {"ok": True, "email": self._mask_email(user["email"])}
            flash("We've emailed you a 6-digit code to confirm deleting your account. It expires in 5 minutes.", "info")
        else:
            if is_ajax:
                return {"ok": False, "error": "We couldn't send the code right now. Please try again."}, 502
            flash("We couldn't send the verification code right now. Please try again later.", "danger")
        return redirect(url_for("Home.profile"))

    def confirm_account_deletion(self):
        """Validate the emailed OTP and permanently delete the account.

        The code must match the one stored by request_account_deletion and not
        have expired. Deletion only happens once the code checks out.
        """
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in first.", "warning")
            return redirect(url_for("Auth.login"))

        otp = (request.form.get("otp") or "").strip()
        if not otp:
            flash("Enter the verification code we emailed you.", "danger")
            return redirect(url_for("Home.profile"))

        db = Database()
        user = db.fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))
        if not user:
            db.close()
            session.clear()
            flash("Account not found.", "danger")
            return redirect(url_for("Auth.login"))

        stored = user.get("deletion_token")
        expires = user.get("deletion_token_expires_at")
        if not stored or not expires:
            db.close()
            flash("No active deletion request was found. Please start again.", "danger")
            return redirect(url_for("Home.profile"))

        if datetime.utcnow() > expires:
            db.execute(
                "UPDATE users SET deletion_token = NULL, deletion_token_expires_at = NULL WHERE id = %s",
                (user_id,),
            )
            db.close()
            flash("Your verification code has expired. Please request account deletion again.", "danger")
            return redirect(url_for("Home.profile"))

        if otp != stored:
            db.close()
            flash("Incorrect verification code. Please try again.", "danger")
            return redirect(url_for("Home.profile"))

        # Code valid — carry out the deletion.
        self._anonymize_and_delete_user(db, user)
        db.close()
        session.clear()
        flash("Your account has been permanently deleted. Your posts remain on the forum as [deleted].", "info")
        return redirect(url_for("Auth.login"))

    def _get_or_create_deleted_user(self, db):
        """Return the id of the shared '[deleted]' sentinel account, creating it
        once if needed. Reassigning content to this account keeps posts/comments
        on the forum without exposing the deleted user's identity."""
        sentinel_email = "deleted@nicheforum.local"
        row = db.fetch_one("SELECT id FROM users WHERE email = %s", (sentinel_email,))
        if row:
            return row["id"]
        db.execute(
            "INSERT INTO users (name, email, password, role, is_verified, is_active) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            ("[deleted]", sentinel_email, generate_password_hash(secrets.token_urlsafe(16)), "user", 1, 0),
        )
        return db.fetch_one("SELECT LAST_INSERT_ID() AS id")["id"]

    def _table_columns(self, db, table):
        """Return the set of column names for `table` (empty set if missing).

        Used so content reassignment works across schema variants — e.g. some
        installs key thread replies by user_id, others by an author-name string.
        """
        try:
            return {c["Field"] for c in db.fetch_all(f"DESCRIBE {table}")}
        except Exception:
            return set()

    def _anonymize_and_delete_user(self, db, user):
        """Preserve the user's content, then remove their account and personal data.

        Authored content survives under the shared '[deleted]' identity:
          • posts / post_comments / threads / replies → reassigned to the
            sentinel user (by user_id) and/or have their author-name string
            blanked to '[deleted]', depending on what columns the table has.
        Deleting the user row then cascades away their personal data (votes,
        follows, community memberships, notifications, direct messages, reports).
        """
        user_id = user["id"]
        user_name = user["name"]
        sentinel_id = self._get_or_create_deleted_user(db)

        # Community posts and their comments are keyed by user_id everywhere.
        db.execute("UPDATE posts SET user_id = %s WHERE user_id = %s", (sentinel_id, user_id))
        db.execute("UPDATE post_comments SET user_id = %s WHERE user_id = %s", (sentinel_id, user_id))

        # Threads/replies attribute authors differently across schema versions:
        # reassign a user_id FK if present, and blank an author-name string if present.
        thread_cols = self._table_columns(db, "threads")
        if "user_id" in thread_cols:
            db.execute("UPDATE threads SET user_id = %s WHERE user_id = %s", (sentinel_id, user_id))
        if "author" in thread_cols:
            db.execute("UPDATE threads SET author = %s WHERE author = %s", ("[deleted]", user_name))

        reply_cols = self._table_columns(db, "replies")
        if "user_id" in reply_cols:
            db.execute("UPDATE replies SET user_id = %s WHERE user_id = %s", (sentinel_id, user_id))
        if "user_email" in reply_cols:
            db.execute("UPDATE replies SET user_email = %s WHERE user_email = %s", ("[deleted]", user_name))

        db.execute("DELETE FROM users WHERE id = %s", (user_id,))

    def verify_registration(self):
        """Handle OTP verification after registration."""
        # Render the OTP entry page on GET so the browser URL is /verify-registration
        if request.method == "GET":
            email = request.args.get("email")
            return render_template("enter_otp.html", email=email)

        if request.method == "POST":
            email = request.form.get("email")
            otp = request.form.get("otp")

            db = Database()
            user = db.fetch_one("SELECT * FROM users WHERE email = %s", (email,))

            if not user:
                if db: db.close()
                flash("Account not found.", "danger")
                return redirect(url_for("Auth.register"))

            # Validate token and expiry
            if not user.get("verification_token") or user.get("verification_token") != otp:
                if db: db.close()
                flash("Invalid verification code.", "danger")
                return render_template("enter_otp.html", email=email)

            if datetime.utcnow() > user.get("token_expires_at"):
                if db: db.close()
                flash("Verification code has expired. Please request a new code.", "danger")
                return redirect(url_for("Auth.register"))

            # Mark user verified and clear token fields
            db.execute(
                "UPDATE users SET is_verified = 1, verification_token = NULL, token_expires_at = NULL WHERE email = %s",
                (email,)
            )
            db.close()

            flash("Your account has been verified. You may now login.", "success")
            return redirect(url_for("Auth.login"))

        # For GET or other, redirect to register
        return redirect(url_for("Auth.register"))

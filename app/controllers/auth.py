from flask import render_template, request, redirect, url_for, flash, session
from app.models.database import Database
from werkzeug.security import generate_password_hash, check_password_hash
from app.utils.email_utils import EmailService
from datetime import datetime, timedelta

class AuthController:
    def login(self):
        if request.method == "POST":
            email = request.form.get("email")
            password = request.form.get("password")

            db = Database()
            user = db.fetch_one("SELECT * FROM users WHERE email = %s", (email,))
            db.close()

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
                return redirect(url_for("Home.home"))
            else:
                flash("Incorrect email or password.", "danger")

        return render_template("login.html")
    
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
                    email_sent = EmailService.send_otp(email, otp_code)
                    if email_sent:
                        print(f"DEBUG: OTP email sent successfully to {email}")
                    else:
                        print(f"DEBUG: OTP email send returned False for {email}")
                except Exception as email_err:
                    print(f"WARNING: Failed to send OTP email: {email_err}")
                    import traceback
                    traceback.print_exc()

                if email_sent:
                    flash("Registration successful! A verification code has been sent to your email. Check your inbox and spam folder.", "info")
                else:
                    flash("Registration successful! We had trouble sending the email. Please check your email and spam folder. If you don't receive it within a few minutes, contact support.", "warning")

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

        return render_template("register.html")

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

    def resend_otp(self):
        """Resend verification OTP to user's email."""
        if request.method == "POST":
            email = request.form.get("email")
            
            if not email:
                flash("Email address is required.", "danger")
                return redirect(url_for("Auth.register"))
            
            db = Database()
            user = db.fetch_one("SELECT * FROM users WHERE email = %s", (email,))
            
            if not user:
                # Don't reveal whether email exists (security)
                flash("If an account with that email exists, a new code will be sent.", "info")
                db.close()
                return redirect(url_for("Auth.verify_registration", email=email))
            
            # Check if already verified
            if user.get("is_verified"):
                flash("This account is already verified! You can now login.", "success")
                db.close()
                return redirect(url_for("Auth.login"))
            
            # Generate new OTP
            otp_code = EmailService.generate_secure_otp()
            expiry_dt = datetime.utcnow() + timedelta(minutes=5)
            
            try:
                db.execute(
                    "UPDATE users SET verification_token = %s, token_expires_at = %s WHERE email = %s",
                    (otp_code, expiry_dt, email)
                )
                db.close()
                
                # Send new OTP email
                email_sent = False
                try:
                    email_sent = EmailService.send_otp(email, otp_code)
                    if email_sent:
                        print(f"DEBUG: New OTP sent to {email}")
                except Exception as email_err:
                    print(f"WARNING: Failed to resend OTP: {email_err}")
                
                if email_sent:
                    flash("A new verification code has been sent to your email. Check inbox and spam folder.", "info")
                else:
                    flash("We had trouble sending the code. Please try again in a few moments.", "warning")
                    
            except Exception as e:
                if db:
                    try:
                        db.close()
                    except:
                        pass
                print(f"ERROR: Failed to resend OTP: {e}")
                flash("An error occurred. Please try again.", "danger")
            
            return redirect(url_for("Auth.verify_registration", email=email))
        
        return redirect(url_for("Auth.register"))

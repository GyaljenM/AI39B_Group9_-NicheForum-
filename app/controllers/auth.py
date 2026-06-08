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

            if user and check_password_hash(user["password"], password):
                # Login directly - email verification is no longer mandatory for access
                session["user_id"] = user["id"]
                session["user_name"] = user["name"]
                session["user_role"] = user["role"]
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

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
                session["profile_pic"] = user["profile_pic"]
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
                db.execute(
                    "INSERT INTO users (name, email, password, is_verified) VALUES (%s, %s, %s, 1)",
                    (name, email, hashed_password)
                )
                db.close()
                
                flash("Registration successful! You can now login.", "success")
                return redirect(url_for("Auth.login"))
            except Exception as e:
                if db: db.close()
                print(f"ERROR: Registration failed: {e}")
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

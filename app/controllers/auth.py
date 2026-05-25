from flask import render_template, request, redirect, url_for, flash, session
from app.models.database import Database
from werkzeug.security import generate_password_hash, check_password_hash

class AuthController:
    def login(self):
        if request.method == "POST":
            email = request.form.get("email")
            password = request.form.get("password")

            db = Database()
            user = db.fetch_one("SELECT * FROM users WHERE email = %s", (email,))
            db.close()

            if user and check_password_hash(user["password"], password):
                session["user_id"] = user["id"]
                session["user_name"] = user["name"]
                session["user_role"] = user["role"]
                flash("Logged in successfully!", "success")
                return redirect(url_for("Home.home"))
            else:
                flash("Invalid email or password.", "danger")

        return render_template("login.html")
    
    def register(self):
        if request.method == "POST":
            name = request.form.get("name")
            email = request.form.get("email")
            password = request.form.get("password")
            
            hashed_password = generate_password_hash(password)

            db = Database()
            # Check if user already exists
            existing_user = db.fetch_one("SELECT * FROM users WHERE email = %s", (email,))
            if existing_user:
                db.close()
                flash("Email already registered.", "danger")
                return redirect(url_for("Auth.register"))

            db.execute(
                "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                (name, email, hashed_password)
            )
            db.close()

            flash("Registration successful! Please login.", "success")
            return redirect(url_for("Auth.login"))

        return render_template("register.html")

    def logout(self):
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("Auth.login"))
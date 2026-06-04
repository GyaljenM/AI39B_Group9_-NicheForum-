from flask import render_template, request, redirect, url_for, session, flash
from app.modals.user import User
import os
from werkzeug.utils import secure_filename
import config
from werkzeug.security import generate_password_hash, check_password_hash

class AuthController:
    def __init__(self):
        self.user_model = User()

    def login(self):
        if request.method == "POST":
            email = request.form.get("email")
            password = request.form.get("password")
            user = self.user_model.find_by("email", email)
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['role'] = user['role']
                return redirect(url_for('auth.dashboard'))
            else:
                flash("Invalid email or password", "danger")
        return render_template("login.html")
    
    def register(self):
        if request.method == "POST":
            name = request.form.get("name")
            username = request.form.get("username")
            email = request.form.get("email")
            password = request.form.get("password")
            hashed_password = generate_password_hash(password)
            try:
                self.user_model.create(name, username, email, hashed_password)
                flash("Registration successful! Please login.", "success")
                return redirect(url_for('auth.login'))
            except Exception as e:
                flash(f"Registration failed: {str(e)}", "danger")
        return render_template("register.html")

    def dashboard(self):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        user = self.user_model.find_by_id(session['user_id'])
        return render_template("dashboard.html", user=user, user_name=user['name'])

    def profile_update(self):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        
        user_id = session['user_id']
        user = self.user_model.find_by_id(user_id)

        if request.method == "POST":
            name = request.form.get("name")
            username = request.form.get("username")
            bio = request.form.get("bio")
            file = request.files.get("profile_picture")
            
            profile_picture = user['profile_picture']
            if file and self.allowed_file(file.filename):
                filename = secure_filename(f"user_{user_id}_{file.filename}")
                upload_path = os.path.join(os.getcwd(), 'app/static/uploads')
                if not os.path.exists(upload_path):
                    os.makedirs(upload_path)
                file.save(os.path.join(upload_path, filename))
                profile_picture = filename

            try:
                self.user_model.update_profile(user_id, name, username, bio, profile_picture)
                session['user_name'] = name
                flash("Profile updated successfully!", "success")
            except Exception as e:
                flash(f"Update failed: {str(e)}", "danger")
            
            return redirect(url_for('auth.dashboard'))

        return render_template("dashboard.html", user=user, user_name=session.get('user_name'), edit_mode=True)

    def logout(self):
        session.clear()
        return redirect(url_for('auth.login'))

    def allowed_file(self, filename):
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

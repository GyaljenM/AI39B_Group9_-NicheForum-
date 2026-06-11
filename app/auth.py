from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("Auth.login"))
        # Login stores the role under "user_role" (see AuthController.login).
        if session.get("user_role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("Home.home"))
        return f(*args, **kwargs)
    return decorated
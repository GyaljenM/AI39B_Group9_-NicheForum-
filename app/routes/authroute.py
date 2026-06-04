from flask import Blueprint
from app.controllers.authcontroller import AuthController

class Authroutes:
    def __init__(self):
        self.bp = Blueprint("auth", __name__)
        self.controller = AuthController()
    
    def register(self):
        self.bp.route("/login", methods=["GET", "POST"])(self.controller.login)
        self.bp.route("/register", methods=["GET", "POST"])(self.controller.register)
        self.bp.route("/dashboard", methods=["GET"])(self.controller.dashboard)
        self.bp.route("/profile/update", methods=["GET", "POST"])(self.controller.profile_update)
        self.bp.route("/logout", methods=["GET"])(self.controller.logout)
        return self.bp

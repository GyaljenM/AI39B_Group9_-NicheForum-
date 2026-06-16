from flask import Blueprint
from app.controllers.auth import AuthController

class AuthRoutes:
    def __init__(self):
        self.bp = Blueprint("Auth",__name__)
        self.controller = AuthController()
    
    def register(self):
        self.bp.route("/login",methods=["GET","POST"])(
            self.controller.login
        )
        self.bp.route("/register",methods=["GET","POST"])(
            self.controller.register
        )
        self.bp.route("/verify-registration", methods=["GET","POST"])(
            self.controller.verify_registration
        )
        self.bp.route("/forgot-password",methods=["GET","POST"])(
            self.controller.forgot_password
        )
        self.bp.route("/reset-password",methods=["GET","POST"])(
            self.controller.reset_password
        )
        self.bp.route("/logout")(
            self.controller.logout
        )
        self.bp.route("/deactivate-account", methods=["POST"])(
            self.controller.deactivate_account
        )
        return self.bp
 
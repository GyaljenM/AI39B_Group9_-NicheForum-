from flask import Flask, render_template

app = Flask(__name__)

class AuthController:
    def login(self):
        return render_template("login.html")

    def home(self):
        # logic to get data
        products = [
            {"name": "brush", "price": "200"},
            {"name": "brush1", "price": "250"},
            {"name": "brush2", "price": "300"}
        ]
        return render_template("home.html", products=products)

    def register(self):
        return render_template("register.html")

# Instantiate the controller
auth = AuthController()

# Application URL Routes
@app.route('/')
def home_route():
    return auth.home()

@app.route('/login')
def login_route():
    return auth.login()

@app.route('/register')
def register_route():
    return auth.register()

if __name__ == '__main__':
    app.run(debug=True)
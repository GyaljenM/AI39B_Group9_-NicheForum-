from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Welcome to the Home Page"

@app.route("/about")
def about():
    return "This is the About Page"

@app.route("/contact")
def contact():
    return "Contact us at [email protected]"

@app.error_handler(404)
def error(e):
    return f"404 page not found please check it again!"
 
if __name__ == "__main__":
    app.run(debug=True, port=5000)
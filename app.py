from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def home():
    return render_template('home.html',name ='suyog',day='tuesday')

@app.route("/about")
def about():
    return render_template('about.html')

@app.route("/contact")
def contact():
    return render_template('contact.html')

@app.route("/login")
def login():
    return render_template('login.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('notfound.html'), 404

from app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(debug=True)

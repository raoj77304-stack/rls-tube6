from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/signup")
def signup():
    return render_template("signup.html")

@app.route("/channel")
def channel():
    return render_template("channel.html")

@app.route("/upload")
def upload():
    return render_template("upload.html")

@app.route("/watch")
def watch():
    return render_template("watch.html")

if __name__ == "__main__":
    app.run(debug=True)

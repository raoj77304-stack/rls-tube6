from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3, os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "RLS_TUBE_SECRET_KEY"

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_VIDEO = {"mp4", "webm", "mov"}
ALLOWED_IMAGE = {"jpg", "jpeg", "png", "webp"}

def db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS videos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        filename TEXT NOT NULL,
        thumbnail TEXT,
        user_id INTEGER,
        views INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS likes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        video_id INTEGER,
        UNIQUE(user_id, video_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS comments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        video_id INTEGER,
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS subscriptions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subscriber_id INTEGER,
        channel_id INTEGER,
        UNIQUE(subscriber_id, channel_id))""")
    conn.commit()
    conn.close()

def allowed(filename, types):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in types

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    conn = db()
    if q:
        videos = conn.execute("""SELECT videos.*, users.username FROM videos
            JOIN users ON videos.user_id=users.id
            WHERE title LIKE ? ORDER BY videos.id DESC""", (f"%{q}%",)).fetchall()
    else:
        videos = conn.execute("""SELECT videos.*, users.username FROM videos
            JOIN users ON videos.user_id=users.id ORDER BY videos.id DESC""").fetchall()
    conn.close()
    return render_template("index.html", videos=videos, user=session.get("username"))

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if len(username) < 3 or len(password) < 4:
            return "Username 3+ characters and password 4+ characters required."
        try:
            conn = db()
            conn.execute("INSERT INTO users(username,password) VALUES (?,?)", (username,password))
            conn.commit(); conn.close()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return "Username already exists!"
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?",
                            (username,password)).fetchone()
        conn.close()
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))
        return "Wrong username or password!"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/upload", methods=["GET","POST"])
def upload():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form.get("description","").strip()
        video = request.files.get("video")
        thumbnail = request.files.get("thumbnail")
        if not video or not allowed(video.filename, ALLOWED_VIDEO):
            return "Only MP4, WEBM or MOV video allowed!"
        video_name = secure_filename(video.filename)
        video.save(os.path.join(app.config["UPLOAD_FOLDER"], video_name))
        thumbnail_name = ""
        if thumbnail and thumbnail.filename and allowed(thumbnail.filename, ALLOWED_IMAGE):
            thumbnail_name = secure_filename(thumbnail.filename)
            thumbnail.save(os.path.join(app.config["UPLOAD_FOLDER"], thumbnail_name))
        conn = db()
        conn.execute("""INSERT INTO videos(title,description,filename,thumbnail,user_id)
                        VALUES(?,?,?,?,?)""",
                     (title,description,video_name,thumbnail_name,session["user_id"]))
        conn.commit(); conn.close()
        return redirect(url_for("index"))
    return render_template("upload.html")

@app.route("/watch/<int:video_id>")
def watch(video_id):
    conn = db()
    conn.execute("UPDATE videos SET views=views+1 WHERE id=?", (video_id,))
    video = conn.execute("""SELECT videos.*, users.username FROM videos
                            JOIN users ON videos.user_id=users.id WHERE videos.id=?""",
                         (video_id,)).fetchone()
    comments = conn.execute("""SELECT comments.*, users.username FROM comments
                               JOIN users ON comments.user_id=users.id
                               WHERE video_id=? ORDER BY comments.id DESC""",
                            (video_id,)).fetchall()
    likes = conn.execute("SELECT COUNT(*) FROM likes WHERE video_id=?", (video_id,)).fetchone()[0]
    conn.commit(); conn.close()
    if not video:
        return "Video not found", 404
    return render_template("watch.html", video=video, comments=comments, likes=likes)

@app.route("/like/<int:video_id>", methods=["POST"])
def like(video_id):
    if "user_id" not in session:
        return jsonify(error="login"), 401
    conn = db()
    try:
        conn.execute("INSERT INTO likes(user_id,video_id) VALUES(?,?)",
                     (session["user_id"],video_id))
        liked = True
    except sqlite3.IntegrityError:
        conn.execute("DELETE FROM likes WHERE user_id=? AND video_id=?",
                     (session["user_id"],video_id))
        liked = False
    count = conn.execute("SELECT COUNT(*) FROM likes WHERE video_id=?", (video_id,)).fetchone()[0]
    conn.commit(); conn.close()
    return jsonify(likes=count, liked=liked)

@app.route("/comment/<int:video_id>", methods=["POST"])
def comment(video_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    text = request.form["comment"].strip()
    if text:
        conn = db()
        conn.execute("INSERT INTO comments(user_id,video_id,comment) VALUES(?,?,?)",
                     (session["user_id"],video_id,text))
        conn.commit(); conn.close()
    return redirect(url_for("watch", video_id=video_id))

@app.route("/subscribe/<int:channel_id>", methods=["POST"])
def subscribe(channel_id):
    if "user_id" not in session:
        return jsonify(error="login"), 401
    if session["user_id"] == channel_id:
        return jsonify(error="own channel"), 400
    conn = db()
    try:
        conn.execute("INSERT INTO subscriptions(subscriber_id,channel_id) VALUES(?,?)",
                     (session["user_id"],channel_id))
        subscribed = True
    except sqlite3.IntegrityError:
        conn.execute("DELETE FROM subscriptions WHERE subscriber_id=? AND channel_id=?",
                     (session["user_id"],channel_id))
        subscribed = False
    count = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE channel_id=?",
                         (channel_id,)).fetchone()[0]
    conn.commit(); conn.close()
    return jsonify(subscribed=subscribed,count=count)

@app.route("/channel/<int:user_id>")
def channel(user_id):
    conn = db()
    channel = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not channel:
        conn.close()
        return "Channel not found", 404
    videos = conn.execute("SELECT * FROM videos WHERE user_id=? ORDER BY id DESC",
                          (user_id,)).fetchall()
    subscribers = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE channel_id=?",
                               (user_id,)).fetchone()[0]
    conn.close()
    return render_template("channel.html", channel=channel, videos=videos,
                           subscribers=subscribers)

init_db()

if __name__ == "__main__":
    app.run(debug=True)

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify
)
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


app = Flask(__name__)

# =========================
# SETTINGS
# =========================

app.secret_key = "RLS_TUBE_SECRET_KEY_CHANGE_THIS"

DATABASE = "database.db"

UPLOAD_FOLDER = os.path.join("static", "uploads")

ALLOWED_VIDEO = {
    "mp4",
    "webm",
    "mov",
    "mkv"
}

ALLOWED_IMAGE = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================
# DATABASE
# =========================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()

    # Users
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Videos
    conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            filename TEXT NOT NULL,
            thumbnail TEXT,
            user_id INTEGER,
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Subscriptions
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            UNIQUE(subscriber_id, channel_id)
        )
    """)

    # Comments
    conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================
# HOME
# =========================

@app.route("/")
def index():

    conn = get_db()

    videos = conn.execute("""
        SELECT videos.*,
               users.username
        FROM videos
        LEFT JOIN users
        ON videos.user_id = users.id
        ORDER BY videos.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "index.html",
        videos=videos
    )


# =========================
# SIGNUP
# =========================

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        if not username or not password:

            return "Username and password are required."

        if password != confirm_password:

            return "Passwords do not match."

        if len(password) < 6:

            return "Password must be at least 6 characters."

        conn = get_db()

        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if existing:

            conn.close()

            return "Username already exists."

        hashed_password = generate_password_hash(password)

        cursor = conn.execute(
            """
            INSERT INTO users
            (username, password)
            VALUES (?, ?)
            """,
            (username, hashed_password)
        )

        user_id = cursor.lastrowid

        conn.commit()
        conn.close()

        session["user_id"] = user_id
        session["username"] = username

        return redirect(url_for("index"))

    return render_template("signup.html")


# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("index"))

        return "Invalid username or password."

    return render_template("login.html")


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


# =========================
# CHANNEL
# =========================

@app.route("/channel")
def my_channel():

    if not session.get("user_id"):

        return redirect(url_for("login"))

    return redirect(
        url_for(
            "channel",
            user_id=session["user_id"]
        )
    )


@app.route("/channel/<int:user_id>")
def channel(user_id):

    conn = get_db()

    channel_user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    if not channel_user:

        conn.close()

        return "Channel not found.", 404

    videos = conn.execute(
        """
        SELECT *
        FROM videos
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    subscribers = conn.execute(
        """
        SELECT COUNT(*)
        FROM subscriptions
        WHERE channel_id = ?
        """,
        (user_id,)
    ).fetchone()[0]

    conn.close()

    return render_template(
        "channel.html",
        channel=channel_user,
        videos=videos,
        subscribers=subscribers
    )


# =========================
# UPLOAD
# =========================

@app.route("/upload", methods=["GET", "POST"])
def upload():

    if not session.get("user_id"):

        return redirect(url_for("login"))

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        video_file = request.files.get("video")
        thumbnail_file = request.files.get("thumbnail")

        if not title:

            return "Video title is required."

        if not video_file or video_file.filename == "":

            return "Please select a video."

        video_name = secure_filename(
            video_file.filename
        )

        video_ext = video_name.rsplit(
            ".",
            1
        )[-1].lower()

        if video_ext not in ALLOWED_VIDEO:

            return "Video format is not supported."

        # Unique filename
        video_filename = (
            str(session["user_id"])
            + "_"
            + video_name
        )

        video_path = os.path.join(
            UPLOAD_FOLDER,
            video_filename
        )

        video_file.save(video_path)

        thumbnail_filename = None

        if thumbnail_file and thumbnail_file.filename:

            thumbnail_name = secure_filename(
                thumbnail_file.filename
            )

            thumbnail_ext = thumbnail_name.rsplit(
                ".",
                1
            )[-1].lower()

            if thumbnail_ext not in ALLOWED_IMAGE:

                return "Thumbnail format is not supported."

            thumbnail_filename = (
                str(session["user_id"])
                + "_thumb_"
                + thumbnail_name
            )

            thumbnail_path = os.path.join(
                UPLOAD_FOLDER,
                thumbnail_filename
            )

            thumbnail_file.save(
                thumbnail_path
            )

        conn = get_db()

        conn.execute(
            """
            INSERT INTO videos
            (
                title,
                description,
                filename,
                thumbnail,
                user_id
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                title,
                description,
                video_filename,
                thumbnail_filename,
                session["user_id"]
            )
        )

        conn.commit()
        conn.close()

        return redirect(url_for("index"))

    return render_template("upload.html")


# =========================
# WATCH VIDEO
# =========================

@app.route("/watch/<int:video_id>")
def watch(video_id):

    conn = get_db()

    video = conn.execute(
        """
        SELECT videos.*,
               users.username
        FROM videos
        LEFT JOIN users
        ON videos.user_id = users.id
        WHERE videos.id = ?
        """,
        (video_id,)
    ).fetchone()

    if not video:

        conn.close()

        return "Video not found.", 404

    # Increase views
    conn.execute(
        """
        UPDATE videos
        SET views = views + 1
        WHERE id = ?
        """,
        (video_id,)
    )

    channel_user = None
    subscribers = 0

    if video["user_id"]:

        channel_user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE id = ?
            """,
            (video["user_id"],)
        ).fetchone()

        subscribers = conn.execute(
            """
            SELECT COUNT(*)
            FROM subscriptions
            WHERE channel_id = ?
            """,
            (video["user_id"],)
        ).fetchone()[0]

    comments = conn.execute(
        """
        SELECT comments.*,
               users.username
        FROM comments
        JOIN users
        ON comments.user_id = users.id
        WHERE comments.video_id = ?
        ORDER BY comments.id DESC
        """,
        (video_id,)
    ).fetchall()

    conn.commit()
    conn.close()

    return render_template(
        "watch.html",
        video=video,
        channel=channel_user,
        subscribers=subscribers,
        comments=comments
    )


# =========================
# COMMENTS
# =========================

@app.route(
    "/comment/<int:video_id>",
    methods=["POST"]
)
def comment(video_id):

    if not session.get("user_id"):

        return redirect(url_for("login"))

    text = request.form.get(
        "comment",
        ""
    ).strip()

    if not text:

        return redirect(
            url_for(
                "watch",
                video_id=video_id
            )
        )

    conn = get_db()

    conn.execute(
        """
        INSERT INTO comments
        (
            video_id,
            user_id,
            text
        )
        VALUES (?, ?, ?)
        """,
        (
            video_id,
            session["user_id"],
            text
        )
    )

    conn.commit()
    conn.close()

    return redirect(
        url_for(
            "watch",
            video_id=video_id
        )
    )


# =========================
# SUBSCRIBE
# =========================

@app.route(
    "/subscribe/<int:channel_id>",
    methods=["POST"]
)
def subscribe(channel_id):

    if not session.get("user_id"):

        return jsonify({
            "error": "Please login first."
        }), 401

    subscriber_id = session["user_id"]

    if subscriber_id == channel_id:

        return jsonify({
            "error": "You cannot subscribe to yourself."
        }), 400

    conn = get_db()

    existing = conn.execute(
        """
        SELECT id
        FROM subscriptions
        WHERE subscriber_id = ?
        AND channel_id = ?
        """,
        (
            subscriber_id,
            channel_id
        )
    ).fetchone()

    if existing:

        conn.execute(
            """
            DELETE FROM subscriptions
            WHERE subscriber_id = ?
            AND channel_id = ?
            """,
            (
                subscriber_id,
                channel_id
            )
        )

        subscribed = False

    else:

        conn.execute(
            """
            INSERT INTO subscriptions
            (
                subscriber_id,
                channel_id
            )
            VALUES (?, ?)
            """,
            (
                subscriber_id,
                channel_id
            )
        )

        subscribed = True

    conn.commit()

    subscribers = conn.execute(
        """
        SELECT COUNT(*)
        FROM subscriptions
        WHERE channel_id = ?
        """,
        (channel_id,)
    ).fetchone()[0]

    conn.close()

    return jsonify({
        "subscribed": subscribed,
        "subscribers": subscribers
    })


# =========================
# RUN APP
# =========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )

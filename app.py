from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_secret")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ---------------- DATABASE ----------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS vehicle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            make TEXT,
            model TEXT,
            year TEXT,
            reg TEXT,
            engine TEXT,
            mileage TEXT,
            parts_available TEXT,
            image_url TEXT
        )
        """)

init_db()


# ---------------- HOME ----------------
@app.route("/")
def index():
    search = request.args.get("search", "")

    db = get_db()

    if search:
        rows = db.execute("""
            SELECT * FROM vehicle
            WHERE title LIKE ?
            OR make LIKE ?
            OR model LIKE ?
            OR parts_available LIKE ?
            ORDER BY id DESC
        """, (f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%")).fetchall()
    else:
        rows = db.execute("SELECT * FROM vehicle ORDER BY id DESC").fetchall()

    db.close()
    return render_template("index.html", vehicles=rows, search=search)


# ---------------- ADD ----------------
@app.route("/add", methods=["POST"])
def add_vehicle():
    if not session.get("logged_in"):
        return "Unauthorized", 403

    file = request.files.get("vehicle_photo")
    if not file or file.filename == "":
        return "No file", 400

    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    image_url = url_for("static", filename=f"uploads/{filename}")

    db = get_db()
    db.execute("""
        INSERT INTO vehicle (
            title, make, model, year, reg,
            engine, mileage, parts_available, image_url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form.get("title"),
        request.form.get("make"),
        request.form.get("model"),
        request.form.get("year"),
        request.form.get("reg"),
        request.form.get("engine"),
        request.form.get("mileage"),
        request.form.get("parts_available"),
        image_url
    ))

    db.commit()
    db.close()

    return redirect(url_for("index"))


# ---------------- DELETE (FIXED) ----------------
@app.route("/delete/<int:id>", methods=["POST"])
def delete_vehicle(id):
    if not session.get("logged_in"):
        return "Unauthorized", 403

    db = get_db()
    db.execute("DELETE FROM vehicle WHERE id = ?", (id,))
    db.commit()
    db.close()

    return redirect(url_for("index"))


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == "cherrywood2026":
            session["logged_in"] = True
            return redirect(url_for("index"))
        return "Wrong password"

    return """
    <form method="POST">
        <input type="password" name="password">
        <button type="submit">Login</button>
    </form>
    """


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)

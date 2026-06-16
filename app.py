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


# ---------------- DB ----------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- HOME (SALES PAGE) ----------------
@app.route("/")
def index():
    db = get_db()
    vehicles = db.execute("SELECT * FROM vehicle ORDER BY id DESC LIMIT 6").fetchall()
    db.close()
    return render_template("index.html", vehicles=vehicles)


# ---------------- FULL INVENTORY ----------------
@app.route("/inventory")
def inventory():
    db = get_db()
    vehicles = db.execute("SELECT * FROM vehicle ORDER BY id DESC").fetchall()
    db.close()
    return render_template("inventory.html", vehicles=vehicles)


# ---------------- SEO PAGES ----------------
@app.route("/used-audi-parts")
def audi():
    return render_template("seo.html", brand="Audi")

@app.route("/used-vw-parts")
def vw():
    return render_template("seo.html", brand="Volkswagen")

@app.route("/scrap-my-car")
def scrap():
    return render_template("scrap.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")


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
        INSERT INTO vehicle (title, make, model, year, reg, engine, mileage, parts_available, image_url)
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

    return redirect(url_for("inventory"))


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
        <button>Login</button>
    </form>
    """


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))



if __name__ == "__main__":
    app.run(debug=True)

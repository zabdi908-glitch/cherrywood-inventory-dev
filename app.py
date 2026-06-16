from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
import json
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_secret")

# ---------------- DB SETUP ----------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


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
            fuel TEXT,
            transmission TEXT,
            mileage TEXT,
            status TEXT,
            image_url TEXT,
            parts_available TEXT,
            description TEXT
        )
        """)


init_db()

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    db = get_db()
    rows = db.execute("SELECT * FROM vehicle ORDER BY id DESC").fetchall()
    db.close()

    return render_template("index.html", vehicles=rows)


@app.route("/add", methods=["POST"])
def add_vehicle():
    if not session.get("logged_in"):
        return "Unauthorized", 403

    file = request.files.get("vehicle_photo")
    if not file or file.filename == "":
        return "No file uploaded", 400

    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    image_url = url_for("static", filename=f"uploads/{filename}")

    # DEFAULT SAFE DATA (NEVER BREAKS APP)
    car_data = {
        "title": request.form.get("title", "New Vehicle"),
        "make": request.form.get("make", "Unknown"),
        "model": request.form.get("model", "Unknown"),
        "year": request.form.get("year", ""),
        "reg": request.form.get("reg", ""),
        "engine": request.form.get("engine", ""),
        "fuel": "",
        "transmission": "",
        "mileage": request.form.get("mileage", ""),
        "parts_available": request.form.get("parts_available", ""),
        "description": request.form.get("description", "")
    }

    # OPTIONAL AI (SAFE — NEVER BREAKS APP)
    try:
        from google import genai
        from google.genai import types

        if os.environ.get("GEMINI_API_KEY"):
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

            with open(filepath, "rb") as f:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        types.Part.from_bytes(
                            data=f.read(),
                            mime_type=file.mimetype
                        ),
                        "Return ONLY JSON: title, make, model, year, reg, engine, mileage"
                    ],
                )

            text = getattr(response, "text", "")

            # CLEAN JSON (VERY IMPORTANT FIX)
            text = text.replace("```json", "").replace("```", "").strip()

            try:
                ai_data = json.loads(text)
                car_data.update(ai_data)
            except:
                pass

    except Exception as e:
        print("AI ERROR (ignored):", e)

    # SAVE TO DB
    db = get_db()
    db.execute("""
        INSERT INTO vehicle (
            title, make, model, year, reg,
            engine, fuel, transmission, mileage,
            status, image_url, parts_available, description
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        car_data["title"],
        car_data["make"],
        car_data["model"],
        car_data["year"],
        car_data["reg"],
        car_data["engine"],
        car_data["fuel"],
        car_data["transmission"],
        car_data["mileage"],
        "Breaking",
        image_url,
        car_data["parts_available"],
        car_data["description"]
    ))

    db.commit()
    db.close()

    return redirect(url_for("index"))


@app.route("/delete/<int:id>", methods=["POST"])
def delete_vehicle(id):
    if not session.get("logged_in"):
        return "Unauthorized", 403

    db = get_db()
    db.execute("DELETE FROM vehicle WHERE id = ?", (id,))
    db.commit()
    db.close()

    return redirect(url_for("index"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == "cherrywood2026":
            session["logged_in"] = True
            return redirect(url_for("index"))
        return "Wrong password"

    return """
    <form method="POST">
        <input type="password" name="password" />
        <button type="submit">Login</button>
    </form>
    """


if __name__ == "__main__":
    app.run(debug=True)

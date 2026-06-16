from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
import uuid
import json
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
csrf = CSRFProtect(app)

# ======================
# CONFIG
# ======================
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_secret_change_me")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ======================
# OPTIONAL AI (SAFE)
# ======================
ai_client = None
try:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        ai_client = genai.Client(api_key=api_key)
except Exception as e:
    print("AI disabled:", e)


# ======================
# DATABASE
# ======================
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


# ======================
# WRAPPER (FIX TEMPLATE SAFETY)
# ======================
class Vehicle:
    def __init__(self, row):
        self.id = row["id"]
        self.title = row["title"]
        self.make = row["make"]
        self.model = row["model"]
        self.year = row["year"]
        self.reg = row["reg"]
        self.engine = row["engine"]
        self.fuel = row["fuel"]
        self.transmission = row["transmission"]
        self.mileage = row["mileage"]
        self.status = row["status"]
        self.image_url = row["image_url"] or "/static/shutter-background.jpg"
        self.parts_available = row["parts_available"]
        self.description = row["description"]

    def get_parts_list(self):
        if not self.parts_available:
            return []
        return [p.strip() for p in self.parts_available.split(",")]


# ======================
# ROUTES
# ======================
@app.route("/")
def index():
    db = get_db()
    rows = db.execute("SELECT * FROM vehicle ORDER BY id DESC").fetchall()
    db.close()

    vehicles = [Vehicle(r) for r in rows]
    return render_template("index.html", vehicles=vehicles)


# ----------------------
# ADD VEHICLE
# ----------------------
@app.route("/add", methods=["POST"])
@csrf.exempt
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

    # DEFAULT DATA
    car_data = {
        "title": "New Stock",
        "make": "Unknown",
        "model": "Unknown",
        "year": "Unknown",
        "reg": "N/A",
        "engine": "N/A",
        "fuel": "N/A",
        "transmission": "N/A",
        "mileage": "N/A",
        "parts_available": "",
        "description": "New arrival"
    }

    # SAFE AI BLOCK
    if ai_client:
        try:
            with open(filepath, "rb") as f:
                response = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        types.Part.from_bytes(data=f.read(), mime_type=file.mimetype),
                        "Return ONLY valid JSON with keys: title, make, model, year, reg, engine, fuel, transmission, mileage, parts_available, description"
                    ]
                )

            text = getattr(response, "text", "").strip()

            try:
                car_data.update(json.loads(text))
            except Exception:
                print("AI returned invalid JSON")

        except Exception as e:
            print("AI ERROR:", e)

    # DATABASE INSERT
    db = get_db()
    try:
        db.execute("""
            INSERT INTO vehicle (
                title, make, model, year, reg,
                engine, fuel, transmission, mileage,
                status, image_url, parts_available, description
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
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

    except Exception as e:
        print("DB ERROR:", e)
        raise
    finally:
        db.close()

    return redirect(url_for("index"))


# ----------------------
# EDIT VEHICLE
# ----------------------
@app.route("/edit/<int:id>", methods=["POST"])
@csrf.exempt
def edit_vehicle(id):
    if not session.get("logged_in"):
        return "Unauthorized", 403

    db = get_db()
    try:
        db.execute("""
            UPDATE vehicle SET
                title=?, make=?, model=?, year=?, reg=?,
                engine=?, fuel=?, transmission=?, mileage=?,
                parts_available=?, description=?
            WHERE id=?
        """, (
            request.form.get("title"),
            request.form.get("make"),
            request.form.get("model"),
            request.form.get("year"),
            request.form.get("reg"),
            request.form.get("engine"),
            request.form.get("fuel"),
            request.form.get("transmission"),
            request.form.get("mileage"),
            request.form.get("parts_available"),
            request.form.get("description"),
            id
        ))
        db.commit()
    except Exception as e:
        print("EDIT ERROR:", e)
        raise
    finally:
        db.close()

    return redirect(url_for("index"))


# ----------------------
# DELETE VEHICLE
# ----------------------
@app.route("/delete/<int:id>", methods=["POST"])
@csrf.exempt
def delete_vehicle(id):
    if not session.get("logged_in"):
        return "Unauthorized", 403

    db = get_db()
    db.execute("DELETE FROM vehicle WHERE id=?", (id,))
    db.commit()
    db.close()

    return redirect(url_for("index"))


# ----------------------
# LOGIN
# ----------------------
@app.route("/login", methods=["GET", "POST"])
@csrf.exempt
def login():
    if request.method == "POST":
        if request.form.get("password") == "cherrywood2026":
            session["logged_in"] = True
            return redirect(url_for("index"))
        return "Invalid password"

    return """
    <form method="POST">
        <input type="password" name="password" placeholder="Password">
        <button type="submit">Login</button>
    </form>
    """


# ======================
# RUN
# ======================
if __name__ == "__main__":
    app.run(debug=True)

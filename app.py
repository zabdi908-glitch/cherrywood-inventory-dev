from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
import json
import uuid
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
csrf = CSRFProtect(app)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "cherrywood_yard_secret_key_2026")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

try:
    from google import genai
    from google.genai import types
    ai_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY")) if os.environ.get("GEMINI_API_KEY") else None
except Exception:
    ai_client = None

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS vehicle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, make TEXT, model TEXT, year TEXT, reg TEXT,
                engine TEXT, fuel TEXT, transmission TEXT, mileage TEXT,
                status TEXT, image_url TEXT, parts_available TEXT, description TEXT
            )
        ''')
init_db()

@app.route('/')
def index():
    db = get_db()
    rows = db.execute("SELECT * FROM vehicle ORDER BY id DESC").fetchall()
    db.close()
    return render_template("index.html", vehicles=rows)

@app.route('/add', methods=['POST'])
@csrf.exempt
def add_vehicle():
    if not session.get('logged_in'): return "Unauthorized", 403
    file = request.files.get('vehicle_photo')
    if not file or file.filename == '': return "No file", 400
    
    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    image_url = url_for('static', filename=f'uploads/{filename}')
    
    car_data = {"title": "New Stock", "make": "VAG", "model": "Breaker", "year": "2026", "reg": "N/A", "engine": "N/A", "fuel": "N/A", "transmission": "N/A", "mileage": "N/A", "parts_available": "None", "description": "New salvage arrival."}
    
    if ai_client:
        try:
            with open(filepath, 'rb') as f:
                response = ai_client.models.generate_content(model='gemini-2.5-flash', 
                    contents=[types.Part.from_bytes(data=f.read(), mime_type=file.mimetype), "Return ONLY valid JSON with keys: title, make, model, year, reg, engine, fuel, transmission, mileage, parts_available, description"])
                
                text = getattr(response, "text", "").strip()
                # Remove Markdown code block wrappers if they exist
                if text.startswith("
http://googleusercontent.com/immersive_entry_chip/0

### 🚀 Final Execution Checklist
1.  **Delete `database.db`:** You **must** do this on your server (via the terminal/shell in Render) before redeploying. This forces the table to be created with the new columns correctly.
2.  **Commit & Deploy:** Click "Clear build cache & deploy" on Render.
3.  **Logs:** If you see a blank page or error, go straight to the **"Logs"** tab on Render. Because we added the `raise` and `print` statements, the error will be in plain English.

You are ready. Go hit that deploy button and finish your project!

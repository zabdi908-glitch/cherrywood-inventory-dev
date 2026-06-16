from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
import json
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
csrf = CSRFProtect(app)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'cherrywood_yard_secret_key_2026')

DATABASE = 'database.db'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.secret_key = 'cherrywood_yard_secret_key_2026'
# Safe Import Layer: Google GenAI Integration Wrapper
try:
    from google import genai
    from google.genai import types
    api_key = os.environ.get("GEMINI_API_KEY")
    ai_client = genai.Client(api_key=api_key) if api_key else None
    print("AI Vision Agent initialized successfully.")
except Exception as e:
    ai_client = None
    print(f"AI Vision Agent offline (Using structural fallback framework): {e}")

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS vehicle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                make TEXT NOT NULL,
                model TEXT NOT NULL,
                year TEXT NOT NULL,
                reg TEXT NOT NULL,
                engine TEXT NOT NULL,
                fuel TEXT NOT NULL,
                transmission TEXT NOT NULL,
                mileage TEXT NOT NULL,
                status TEXT NOT NULL,
                image_url TEXT,
                parts_available TEXT,
                description TEXT
            )
        ''')
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class VehicleWrapper:
    def __init__(self, row):
        self.id = row['id']
        self.title = row['title']
        self.make = row['make']
        self.model = row['model']
        self.year = row['year']
        self.reg = row['reg']
        self.engine = row['engine']
        self.fuel = row['fuel']
        self.transmission = row['transmission']
        self.mileage = row['mileage']
        self.status = row['status']
        self.image_url = row['image_url'] if row['image_url'] else '/static/shutter-background.jpg'
        self.parts_available = row['parts_available']
        self.description = row['description']

    def get_parts_list(self):
        if self.parts_available:
            return [p.strip() for p in self.parts_available.split(',') if p.strip()]
        return []

@app.route('/')
def index():
    db = get_db()
    cursor = db.execute('SELECT * FROM vehicle ORDER BY id DESC')
    rows = cursor.fetchall()
    db.close()
    
    vehicles = [VehicleWrapper(row) for row in rows]
    return render_template('index.html', vehicles=vehicles)

@app.route('/add', methods=['POST'])
@csrf.exempt
def add_vehicle():
    if not session.get('logged_in'):
        return "Unauthorized Access", 403
        
    if 'vehicle_photo' not in request.files:
        return "No photo uploaded", 400
        
    file = request.files['vehicle_photo']
    if file.filename == '':
        return "No selected file", 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"breaker_{os.urandom(4).hex()}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        image_url = f"/{filepath}"
        
        car_data = {
            "title": "Fresh Salvage Stock Arrival", 
            "make": "VAG Group", 
            "model": "Breaker Spec",
            "year": "2026", 
            "reg": "SCANNING", 
            "engine": "Pending Check",
            "fuel": "Petrol/Diesel", 
            "transmission": "Manual/Auto", 
            "mileage": "N/A",
            "parts_available": "Engine, Gearbox, Panels, Lights, Alloy Wheels",
            "description": "New vehicle arrival entering our yard layout."
        }

        if ai_client:
            try:
                with open(filepath, 'rb') as img_file:
                    img_bytes = img_file.read()
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[types.Part.from_bytes(data=img_bytes, mime_type=file.mimetype), "Analyze this car for parts."],
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                car_data.update(json.loads(response.text.strip()))
            except Exception as e:
                print(f"AI Core parsing skipped: {e}")

        db = get_db()
        db.execute('''
            INSERT INTO vehicle (title, make, model, year, reg, engine, fuel, transmission, mileage, status, image_url, parts_available, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (car_data["title"], car_data["make"], car_data["model"], car_data["year"], 
              car_data["reg"].upper(), car_data["engine"], car_data["fuel"], car_data["transmission"], 
              car_data["mileage"], "Breaking Daily", image_url, car_data["parts_available"], car_data["description"]))
        db.commit()
        db.close()
        
    return redirect(url_for('index'))

@app.route('/edit/<int:id>', methods=['POST'])
@csrf.exempt
def edit_vehicle(id):
    if not session.get('logged_in'):
        return "Unauthorized Access", 403
        
    db = get_db()
    db.execute('''
        UPDATE vehicle 
        SET title=?, make=?, model=?, year=?, reg=?, engine=?, fuel=?, transmission=?, mileage=?, parts_available=?, description=?
        WHERE id = ?
    ''', (request.form.get('title'), request.form.get('make'), request.form.get('model'), 
          request.form.get('year'), request.form.get('reg', '').upper(), request.form.get('engine'), 
          request.form.get('fuel'), request.form.get('transmission'), request.form.get('mileage'), 
          request.form.get('parts_available'), request.form.get('description'), id))
    db.commit()
    db.close()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>', methods=['POST'])
@csrf.exempt
def delete_vehicle(id):
    if not session.get('logged_in'):
        return "Unauthorized Access", 403
        
    db = get_db()
    db.execute('DELETE FROM vehicle WHERE id = ?', (id,))
    db.commit()
    db.close()
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
@csrf.exempt
def login():
    if request.method == 'POST':
        if request.form.get('password', '').strip() == 'cherrywood2026':
            session['logged_in'] = True
            return redirect(url_for('index'))
        return '<p style="color: red; text-align: center; margin-top: 20px;">Invalid password. <a href="/login">Try again</a>.</p>'
    return '''<!DOCTYPE html><html>... (Keep your existing HTML string here) ...</html>'''

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

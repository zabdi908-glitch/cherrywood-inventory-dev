from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Pulls secret key safely or defaults to development bypass framework
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

@app.route('/cherrywood-gatekeeper', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == 'admin' and password == 'cherrywood123':
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return '<script>alert("Invalid details! Try again."); window.location.href="/cherrywood-gatekeeper";</script>'
            
    return '''
        <div style="background:#0f172a; color:#fff; height:100vh; display:flex; justify-content:center; align-items:center; font-family:sans-serif;">
            <form method="POST" style="background:#1e293b; padding:35px; border-radius:12px; border:2px solid #f97316; width:320px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                <h2 style="margin-top:0; color:#f97316; text-transform:uppercase; font-size:22px; letter-spacing:1px; text-align:center;">Cherrywood Admin</h2>
                <p style="color:#94a3b8; font-size:12px; text-align:center; margin-bottom:20px;">Log in to access secret breaker controls</p>
                
                <label style="font-size:11px; text-transform:uppercase; color:#94a3b8; font-weight:bold;">Username</label>
                <input type="text" name="username" style="width:100%; padding:11px; margin: 6px 0 15px 0; border-radius:6px; border:1px solid #334155; background:#0f172a; color:#fff; outline:none;" required>
                
                <label style="font-size:11px; text-transform:uppercase; color:#94a3b8; font-weight:bold;">Password</label>
                <input type="password" name="password" style="width:100%; padding:11px; margin: 6px 0 20px 0; border-radius:6px; border:1px solid #334155; background:#0f172a; color:#fff; outline:none;" required>
                
                <button type="submit" style="width:100%; padding:12px; background:#22c55e; color:#fff; border:none; border-radius:6px; font-weight:bold; font-size:14px; cursor:pointer; text-transform:uppercase;">Sign Into Portal</button>
                <a href="/" style="display:block; text-align:center; margin-top:15px; color:#94a3b8; font-size:12px; text-decoration:none;">← Back to Public Website</a>
            </form>
        </div>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/add', methods=['POST'])
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
        
        # Static baseline parameters fallback in case image generation engine fails
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
            "description": "New vehicle arrival entering our yard layout. Contact the sales counter for parts availability."
        }

        if ai_client:
            try:
                with open(filepath, 'rb') as img_file:
                    img_bytes = img_file.read()
                
                prompt = """
                You are an expert automotive salvage yard intelligence agent.
                Analyze this photo of a breaker vehicle and return a clean JSON specification block.
                
                Target checklist:
                1. Look for the UK registration number plate.
                2. Identify the vehicle manufacturer make (Audi, Volkswagen, SEAT, or Skoda) and specific model.
                3. Check for engine type badges (TDI, TSI, TFSI, 2.0T, etc.), fuel type, and transmission. If not fully clear, guess standard specifications logically based on the body shape.
                4. Create a nice title e.g., '2015 SEAT Leon Tech Pack Breaker'.
                5. Create a comma-separated list of 6-8 specific parts likely available on this car.
                6. Write a helpful 2-sentence description about it breaking for parts.
                
                Return ONLY raw JSON matching this format exactly:
                {
                    "title": "string",
                    "make": "string",
                    "model": "string",
                    "year": "string",
                    "reg": "string",
                    "engine": "string",
                    "fuel": "string",
                    "transmission": "string",
                    "mileage": "string",
                    "parts_available": "string",
                    "description": "string"
                }
                """
                
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type=file.mimetype),
                        prompt
                    ],
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                
                raw_json = response.text.strip()
                ai_data = json.loads(raw_json)
                car_data.update(ai_data)
            except Exception as e:
                print(f"AI Core parsing skipped temporarily: {e}")

        db = get_db()
        db.execute('''
            INSERT INTO vehicle (title, make, model, year, reg, engine, fuel, transmission, mileage, status, image_url, parts_available, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            car_data["title"], car_data["make"], car_data["model"], car_data["year"], 
            car_data["reg"].upper(), car_data["engine"], car_data["fuel"], car_data["transmission"], 
            car_data["mileage"], "Breaking Daily", image_url, car_data["parts_available"], car_data["description"]
        ))
        db.commit()
        db.close()
        
    return redirect(url_for('index'))

@app.route('/edit/<int:id>', methods=['POST'])
def edit_vehicle(id):
    if not session.get('logged_in'):
        return "Unauthorized Access", 403
        
    title = request.form.get('title')
    make = request.form.get('make')
    model = request.form.get('model')
    year = request.form.get('year')
    reg = request.form.get('reg', '').upper()
    engine = request.form.get('engine')
    fuel = request.form.get('fuel')
    transmission = request.form.get('transmission')
    mileage = request.form.get('mileage')
    parts_available = request.form.get('parts_available')
    description = request.form.get('description')
    
    db = get_db()
    db.execute('''
        UPDATE vehicle 
        SET title=?, make=?, model=?, year=?, reg=?, engine=?, fuel=?, transmission=?, mileage=?, parts_available=?, description=?
        WHERE id=?
    ''', (title, make, model, year, reg, engine, fuel, transmission, mileage, parts_available, description, id))
    db.commit()
    db.close()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>', methods=['POST'])
def delete_vehicle(id):
    if not session.get('logged_in'):
        return "Unauthorized Access", 403
    
    db = get_db()
    db.execute('DELETE FROM vehicle WHERE id = ?', (id,))
    db.commit()
    db.close()
    return redirect(url_for('index'))
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == 'cherrywood2026':
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return '<p style="color: red; text-align: center; margin-top: 20px;">Invalid password. Try again.</p>'
            
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Cherrywood Admin Gate</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-[#0b0f19] text-slate-100 min-h-screen flex items-center justify-center p-4">
        <div class="bg-[#172033]/70 border border-slate-800 p-8 rounded-2xl w-full max-w-sm shadow-2xl backdrop-blur-md">
            <div class="text-center mb-6">
                <span class="text-xs font-bold tracking-widest text-orange-500 uppercase block mb-1">Secure Portal</span>
                <h2 class="text-xl font-black uppercase tracking-tight text-white">Cherrywood Admin</h2>
            </div>
            <form method="POST" class="space-y-4">
                <div>
                    <label class="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Enter Gate Password</label>
                    <input type="password" name="password" placeholder="••••••••" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-700 outline-none focus:border-orange-500/50 transition-colors" autofocus required>
                </div>
                <button type="submit" class="w-full bg-orange-600 hover:bg-orange-500 text-white font-bold py-3 rounded-xl transition-all uppercase tracking-wider text-xs">
                    Unlock Dashboard
                </button>
            </form>
            <a href="/" class="block text-center text-xs text-slate-500 hover:text-slate-400 mt-4">← Back to Public Site</a>
        </div>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

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

try:
    from google import genai
    from google.genai import types
    api_key = os.environ.get("GEMINI_API_KEY")
    ai_client = genai.Client(api_key=api_key) if api_key else None
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
                title TEXT NOT NULL, make TEXT NOT NULL, model TEXT NOT NULL,
                year TEXT NOT NULL, reg TEXT NOT NULL, engine TEXT NOT NULL,
                fuel TEXT NOT NULL, transmission TEXT NOT NULL, mileage TEXT NOT NULL,
                status TEXT NOT NULL, image_url TEXT, parts_available TEXT, description TEXT
            )
        ''')
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class VehicleWrapper:
    def __init__(self, row):
        self.id = row['id']; self.title = row['title']; self.make = row['make']
        self.model = row['model']; self.year = row['year']; self.reg = row['reg']
        self.engine = row['engine']; self.fuel = row['fuel']; self.transmission = row['transmission']
        self.mileage = row['mileage']; self.status = row['status']
        self.image_url = row['image_url'] if row['image_url'] else '/static/shutter-background.jpg'
        self.parts_available = row['parts_available']; self.description = row['description']

@app.route('/')
def index():
    db = get_db()
    rows = db.execute('SELECT * FROM vehicle ORDER BY id DESC').fetchall()
    db.close()
    return render_template('index.html', vehicles=[VehicleWrapper(row) for row in rows])

@app.route('/add', methods=['POST'])
@csrf.exempt
def add_vehicle():
    if not session.get('logged_in'): return "Unauthorized Access", 403
    if 'vehicle_photo' not in request.files: return "No photo uploaded", 400
    file = request.files['vehicle_photo']
    if file.filename != '' and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"breaker_{os.urandom(4).hex()}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        car_data = {"title": "New Stock", "make": "VAG", "model": "Breaker", "year": "2026", "reg": "N/A", "engine": "N/A", "fuel": "N/A", "transmission": "N/A", "mileage": "N/A", "parts_available": "N/A", "description": "New arrival."}
        if ai_client:
            try:
                with open(filepath, 'rb') as f:
                    response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=[types.Part.from_bytes(data=f.read(), mime_type=file.mimetype), "Analyze this car."])
                    car_data.update(json.loads(response.text.strip()))
            except Exception: pass
        db = get_db()
        db.execute('INSERT INTO vehicle (title, make, model, year, reg, engine, fuel, transmission, mileage, status, image_url, parts_available, description) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', 
                   (car_data["title"], car_data["make"], car_data["model"], car_data["year"], car_data["reg"], car_data["engine"], car_data["fuel"], car_data["transmission"], car_data["mileage"], "Breaking", f"/{filepath}", car_data["parts_available"], car_data["description"]))
        db.commit(); db.close()
    return redirect(url_for('index'))

@app.route('/edit/<int:id>', methods=['POST'])
@csrf.exempt
def edit_vehicle(id):
    if not session.get('logged_in'): return "Unauthorized Access", 403
    db = get_db()
    db.execute('UPDATE vehicle SET title=?, make=?, model=?, year=?, reg=?, engine=?, fuel=?, transmission=?, mileage=?, parts_available=?, description=? WHERE id = ?', 
               (request.form.get('title'), request.form.get('make'), request.form.get('model'), request.form.get('year'), request.form.get('reg'), request.form.get('engine'), request.form.get('fuel'), request.form.get('transmission'), request.form.get('mileage'), request.form.get('parts_available'), request.form.get('description'), id))
    db.commit(); db.close()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>', methods=['POST'])
@csrf.exempt
def delete_vehicle(id):
    if not session.get('logged_in'): return "Unauthorized Access", 403
    db = get_db()
    db.execute('DELETE FROM vehicle WHERE id = ?', (id,))
    db.commit(); db.close()
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
@csrf.exempt
def login():
    if request.method == 'POST':
        if request.form.get('password', '').strip() == 'cherrywood2026':
            session['logged_in'] = True
            return redirect(url_for('index'))
        return '<p>Invalid password.</p>'
    return '''
    <!DOCTYPE html>
    <html lang="en"><head><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-slate-900 flex items-center justify-center min-h-screen">
        <form method="POST" class="bg-slate-800 p-8 rounded-xl shadow-lg">
            <input type="password" name="password" placeholder="Enter Password" class="p-2 rounded bg-slate-950 text-white w-full mb-4">
            <button type="submit" class="bg-orange-600 text-white w-full py-2 rounded">Unlock</button>
        </form>
    </body></html>
    '''

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

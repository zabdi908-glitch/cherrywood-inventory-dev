from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'cherrywood_yard_secret_key_2026'

DATABASE = 'database.db'

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

# Helper method for templates to parse comma strings into separate lists
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
        self.image_url = row['image_url'] if row['image_url'] else 'https://images.unsplash.com/photo-1563720223185-11003d516935?q=80&w=600'
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Admin Credentials for Cherrywood Yard
        if username == 'admin' and password == 'cherrywood123':
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return '''
                <script>alert("Invalid details! Try again."); window.location.href="/login";</script>
            '''
            
    return '''
        <div style="background:#0f172a; color:#fff; height:100vh; display:flex; justify-content:center; align-items:center; font-family:sans-serif;">
            <form method="POST" style="background:#1e293b; padding:35px; border-radius:12px; border:2px solid #f97316; width:320px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                <h2 style="margin-top:0; color:#f97316; text-transform:uppercase; font-size:22px; letter-spacing:1px; text-align:center;">Cherrywood Admin</h2>
                <p style="color:#94a3b8; font-size:12px; text-align:center; margin-bottom:20px;">Log in to add or remove breaker vehicles</p>
                
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
        
    title = request.form.get('title')
    make = request.form.get('make')
    model = request.form.get('model')
    year = request.form.get('year')
    reg = request.form.get('reg')
    engine = request.form.get('engine')
    fuel = request.form.get('fuel')
    transmission = request.form.get('transmission')
    mileage = request.form.get('mileage')
    status = request.form.get('status')
    image_url = request.form.get('image_url')
    parts_available = request.form.get('parts_available')
    description = request.form.get('description')

    db = get_db()
    db.execute('''
        INSERT INTO vehicle (title, make, model, year, reg, engine, fuel, transmission, mileage, status, image_url, parts_available, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, make, model, year, reg, engine, fuel, transmission, mileage, status, image_url, parts_available, description))
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

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

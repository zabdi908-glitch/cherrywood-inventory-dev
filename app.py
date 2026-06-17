# ============================================
# 1. IMPORTS (TOP)
# ============================================
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from functools import wraps
from smart_agent import smart_agent  # <-- NEW IMPORT
import json                         # <-- NEW IMPORT

app = Flask(__name__)

# ============================================
# 2. CONFIGURATION
# ============================================
app.secret_key = os.getenv('SECRET_KEY', 'cherrywood_yard_secret_key_2026')

if os.getenv('RENDER'):
    DATABASE = os.path.join('/tmp', 'inventory.db')
else:
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')

# ============================================
# 3. DATABASE FUNCTIONS
# ============================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please login first', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        with sqlite3.connect(DATABASE) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS vehicle (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                title TEXT, make TEXT, model TEXT, year TEXT, reg TEXT, 
                engine TEXT, fuel TEXT, transmission TEXT, mileage TEXT, 
                status TEXT, image_url TEXT, parts_available TEXT, description TEXT
            )''')
            conn.commit()
            print(f"Database initialized successfully at {DATABASE}")
    except Exception as e:
        print(f"Database initialization error: {e}")

init_db()

# ============================================
# 4. PUBLIC ROUTES (Your existing routes)
# ============================================
@app.route('/')
def index():
    # Your existing index route
    # ... (keep your current code here)

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Your existing login route
    # ... (keep your current code here)

@app.route('/logout')
def logout():
    # Your existing logout route
    # ... (keep your current code here)

@app.route('/add', methods=['POST'])
@login_required
def add_vehicle():
    # Your existing add route
    # ... (keep your current code here)

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_vehicle(id):
    # Your existing edit route
    # ... (keep your current code here)

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_vehicle(id):
    # Your existing delete route
    # ... (keep your current code here)

# ============================================
# 5. ADMIN ROUTES (NEW - Paste here)
# ============================================
@app.route('/admin/smart-add', methods=['GET', 'POST'])
@login_required
def smart_add_vehicle():
    if request.method == 'POST':
        image_url = request.form.get('image_url')
        
        if not image_url:
            flash('Please provide an image URL', 'error')
            return render_template('smart_add.html')
        
        # Analyze image
        result = smart_agent.analyze_vehicle_image(image_url)
        
        if result['success']:
            # Get formatted data
            vehicle_data = smart_agent.format_for_database(result)
            
            if vehicle_data:
                # Add to database
                db = get_db()
                db.execute('''INSERT INTO vehicle 
                    (title, make, model, year, reg, engine, fuel, transmission, 
                     mileage, status, image_url, parts_available, description) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (vehicle_data['title'], vehicle_data['make'], 
                     vehicle_data['model'], vehicle_data['year'],
                     vehicle_data['reg'], vehicle_data['engine'],
                     vehicle_data['fuel'], vehicle_data['transmission'],
                     vehicle_data['mileage'], vehicle_data['status'],
                     image_url, vehicle_data['parts_available'],
                     vehicle_data['description']))
                db.commit()
                db.close()
                
                flash(f'✅ Vehicle added! AI identified: {vehicle_data["make"]} {vehicle_data["model"]}', 'success')
                return redirect(url_for('index'))
        else:
            flash(f'❌ Error: {result.get("error", "Unknown error")}', 'error')
        
        return render_template('smart_add.html', result=result)
    
    return render_template('smart_add.html')

# ============================================
# 6. RUN THE APP (BOTTOM)
# ============================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)

from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import json
from functools import wraps
from datetime import datetime

app = Flask(__name__)

# ============================================
# CONFIGURATION
# ============================================

app.secret_key = os.getenv('SECRET_KEY', 'cherrywood_yard_secret_key_2026')

if os.getenv('RENDER'):
    DATABASE = os.path.join('/tmp', 'inventory.db')
else:
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')

# ============================================
# DATABASE FUNCTIONS
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
# AUTO-BACKUP SYSTEM (No Disk Needed)
# ============================================

def auto_backup_vehicles():
    """Auto-backup vehicles to a JSON file on every change"""
    try:
        db = get_db()
        rows = db.execute('SELECT * FROM vehicle ORDER BY id DESC').fetchall()
        db.close()
        
        vehicles = []
        for row in rows:
            vehicles.append(dict(row))
        
        backup_file = 'vehicles_backup.json'
        with open(backup_file, 'w') as f:
            json.dump(vehicles, f, indent=2)
        
        print(f"✅ Backed up {len(vehicles)} vehicles")
        return True
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False

def restore_from_backup():
    """Restore vehicles from backup file"""
    try:
        backup_file = 'vehicles_backup.json'
        if not os.path.exists(backup_file):
            print("No backup file found")
            return False
        
        with open(backup_file, 'r') as f:
            vehicles = json.load(f)
        
        if not vehicles:
            print("Backup file is empty")
            return False
        
        db = get_db()
        db.execute('DELETE FROM vehicle')
        
        for v in vehicles:
            db.execute('''INSERT INTO vehicle 
                (title, make, model, year, reg, engine, fuel, transmission, 
                 mileage, status, image_url, parts_available, description) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (v['title'], v['make'], v['model'], v['year'], v['reg'],
                 v['engine'], v['fuel'], v['transmission'], v['mileage'],
                 v['status'], v['image_url'], v['parts_available'], v['description']))
        
        db.commit()
        db.close()
        print(f"✅ Restored {len(vehicles)} vehicles from backup!")
        return True
    except Exception as e:
        print(f"❌ Restore failed: {e}")
        return False

def backup_after_change(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        auto_backup_vehicles()
        return result
    return wrapper

# ============================================
# PUBLIC ROUTES
# ============================================

@app.route('/')
def index():
    try:
        db = get_db()
        rows = db.execute('SELECT * FROM vehicle ORDER BY id DESC').fetchall()
        db.close()
        
        vehicles_data = []
        for row in rows:
            v = dict(row)
            def get_parts():
                return v.get('parts_available', '').split(',') if v.get('parts_available') else []
            v['get_parts_list'] = get_parts
            vehicles_data.append(v)
            
        return render_template('index.html', vehicles=vehicles_data)
    except Exception as e:
        flash(f'Error loading vehicles: {e}', 'error')
        return render_template('index.html', vehicles=[])

@app.route('/search')
def search():
    """Search vehicles by make, model, or parts"""
    query = request.args.get('q', '').strip()
    
    if not query:
        return redirect(url_for('index'))
    
    try:
        db = get_db()
        search_term = f'%{query}%'
        rows = db.execute('''SELECT * FROM vehicle 
                            WHERE title LIKE ? 
                            OR make LIKE ? 
                            OR model LIKE ? 
                            OR parts_available LIKE ?
                            ORDER BY id DESC''',
                         (search_term, search_term, search_term, search_term)).fetchall()
        db.close()
        
        vehicles_data = []
        for row in rows:
            v = dict(row)
            def get_parts():
                return v.get('parts_available', '').split(',') if v.get('parts_available') else []
            v['get_parts_list'] = get_parts
            vehicles_data.append(v)
        
        return render_template('index.html', vehicles=vehicles_data, search_query=query)
    except Exception as e:
        flash(f'Search error: {e}', 'error')
        return redirect(url_for('index'))

@app.route('/vehicle/<int:id>')
def view_vehicle(id):
    """View full details of a single vehicle"""
    try:
        db = get_db()
        vehicle = db.execute('SELECT * FROM vehicle WHERE id = ?', (id,)).fetchone()
        db.close()
        
        if not vehicle:
            flash('Vehicle not found', 'error')
            return redirect(url_for('index'))
        
        v = dict(vehicle)
        v['parts_list'] = v.get('parts_available', '').split(',') if v.get('parts_available') else []
        
        return render_template('vehicle_detail.html', vehicle=v)
    except Exception as e:
        flash(f'Error loading vehicle: {e}', 'error')
        return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin_password = os.getenv('ADMIN_PASSWORD', 'cherrywood123')
        
        if username == 'admin' and password == admin_password:
            session['logged_in'] = True
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

# ============================================
# ADMIN ROUTES (With Auto-Backup)
# ============================================

@app.route('/add', methods=['POST'])
@login_required
@backup_after_change
def add_vehicle():
    try:
        db = get_db()
        db.execute('''INSERT INTO vehicle 
                     (title, make, model, year, reg, engine, fuel, 
                      transmission, mileage, status, image_url, parts_available, description) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (request.form['title'], request.form['make'], request.form['model'],
                   request.form['year'], request.form['reg'], request.form['engine'],
                   request.form['fuel'], request.form['transmission'], request.form['mileage'],
                   request.form['status'], request.form['image_url'],
                   request.form['parts_available'], request.form['description']))
        db.commit()
        db.close()
        flash('Vehicle added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding vehicle: {e}', 'error')
    return redirect(url_for('index'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_vehicle(id):
    db = get_db()
    vehicle = db.execute('SELECT * FROM vehicle WHERE id = ?', (id,)).fetchone()
    
    if not vehicle:
        flash('Vehicle not found', 'error')
        db.close()
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            db.execute('''UPDATE vehicle SET title=?, make=?, model=?, year=?, reg=?, 
                          engine=?, fuel=?, transmission=?, mileage=?, status=?, 
                          image_url=?, parts_available=?, description=? WHERE id=?''',
                       (request.form['title'], request.form['make'], request.form['model'], 
                        request.form['year'], request.form['reg'], request.form['engine'], 
                        request.form['fuel'], request.form['transmission'], request.form['mileage'], 
                        request.form['status'], request.form['image_url'], 
                        request.form['parts_available'], request.form['description'], id))
            db.commit()
            db.close()
            flash('Vehicle updated successfully!', 'success')
            auto_backup_vehicles()  # Backup after edit
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error updating vehicle: {e}', 'error')
            db.close()
            return render_template('edit.html', vehicle=dict(vehicle))
    
    db.close()
    return render_template('edit.html', vehicle=vehicle)

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_vehicle(id):
    try:
        db = get_db()
        db.execute('DELETE FROM vehicle WHERE id = ?', (id,))
        db.commit()
        db.close()
        flash('Vehicle deleted successfully!', 'success')
        auto_backup_vehicles()  # Backup after delete
    except Exception as e:
        flash(f'Error deleting vehicle: {e}', 'error')
    return redirect(url_for('index'))

@app.route('/admin/restore', methods=['POST'])
@login_required
def restore_vehicles():
    """Restore vehicles from backup"""
    if restore_from_backup():
        flash('✅ Vehicles restored from backup!', 'success')
    else:
        flash('❌ No backup found or restore failed', 'error')
    return redirect(url_for('index'))

# ============================================
# RUN THE APP
# ============================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
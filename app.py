from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from functools import wraps

app = Flask(__name__)

# Security - use environment variables
app.secret_key = os.getenv('SECRET_KEY', 'cherrywood_yard_secret_key_2026')

# Database path - works on Render AND locally
if os.getenv('RENDER'):
    DATABASE = os.path.join('/tmp', 'inventory.db')  # Render uses /tmp
else:
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')

# Login decorator for protected routes
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
    """Initialize database with tables if they don't exist"""
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

# Initialize database
init_db()

@app.route('/')
def index():
    try:
        db = get_db()
        rows = db.execute('SELECT * FROM vehicle ORDER BY id DESC').fetchall()
        db.close()
        
        vehicles_data = []
        for row in rows:
            v = dict(row)
            v['parts_list'] = v.get('parts_available', '').split(',') if v.get('parts_available') else []
            vehicles_data.append(v)
            
        return render_template('index.html', vehicles=vehicles_data)
    except Exception as e:
        flash(f'Error loading vehicles: {e}', 'error')
        return render_template('index.html', vehicles=[])

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

@app.route('/add', methods=['POST'])
@login_required
def add_vehicle():
    if request.method == 'POST':
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
    except Exception as e:
        flash(f'Error deleting vehicle: {e}', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)

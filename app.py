from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import json
from functools import wraps
from datetime import datetime
from parts_agent import parts_agent

app = Flask(__name__)

# ============================================
# CONFIGURATION
# ============================================

app.secret_key = os.getenv('SECRET_KEY', 'cherrywood_yard_secret_key_2026')

if os.getenv('RENDER'):
    DATABASE = os.path.join('/data', 'inventory.db')  # ✅ CORRECT — Persistent disk!
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
# AUTO-BACKUP SYSTEM
# ============================================

def auto_backup_vehicles():
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
        
        return True
    except Exception as e:
        print(f"Backup failed: {e}")
        return False

def restore_from_backup():
    try:
        backup_file = 'vehicles_backup.json'
        if not os.path.exists(backup_file):
            return False
        
        with open(backup_file, 'r') as f:
            vehicles = json.load(f)
        
        if not vehicles:
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
        return True
    except Exception as e:
        print(f"Restore failed: {e}")
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
        # ✅ Show ONLY Breaking vehicles, ordered by newest first
        rows = db.execute('SELECT * FROM vehicle WHERE status = "Breaking" ORDER BY id DESC').fetchall()
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
            # ✅ FIX: Redirect to parts page instead of homepage
            return redirect(url_for('parts_index'))
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
# ADMIN ROUTES
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
        flash('✅ Vehicle added successfully!', 'success')
    except Exception as e:
        flash(f'❌ Error adding vehicle: {e}', 'error')
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
            flash('✅ Vehicle updated successfully!', 'success')
            auto_backup_vehicles()
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'❌ Error updating vehicle: {e}', 'error')
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
        flash('✅ Vehicle deleted successfully!', 'success')
        auto_backup_vehicles()
    except Exception as e:
        flash(f'❌ Error deleting vehicle: {e}', 'error')
    return redirect(url_for('index'))

@app.route('/admin/restore', methods=['POST'])
@login_required
def restore_vehicles():
    if restore_from_backup():
        flash('✅ Vehicles restored from backup!', 'success')
    else:
        flash('❌ No backup found or restore failed', 'error')
    return redirect(url_for('index'))

@app.route('/admin/backup-now', methods=['POST'])
@login_required
def backup_now():
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
        
        flash(f'✅ Backup created with {len(vehicles)} vehicles!', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'❌ Backup failed: {e}', 'error')
        return redirect(url_for('index'))

# ============================================
# INFORMATION PAGES
# ============================================

@app.route('/gallery')
def gallery():
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
        
        return render_template('gallery.html', vehicles=vehicles_data)
    except Exception as e:
        flash(f'Error loading gallery: {e}', 'error')
        return render_template('gallery.html', vehicles=[])
        
@app.route('/enquiry', methods=['GET', 'POST'])
def enquiry():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        reg = request.form.get('reg')
        vin = request.form.get('vin')
        vehicle = request.form.get('vehicle')
        parts = request.form.get('parts')
        message = request.form.get('message')
        contact_method = request.form.get('contact_method')
        urgency = request.form.get('urgency')

        # Build WhatsApp message
        whatsapp_message = f"Hi Cherrywood, I have a part enquiry:\n\n"
        whatsapp_message += f"Name: {name}\n"
        whatsapp_message += f"Email: {email}\n"
        if phone:
            whatsapp_message += f"Phone: {phone}\n"
        whatsapp_message += f"Reg: {reg}\n"
        if vin:
            whatsapp_message += f"VIN: {vin}\n"
        if vehicle:
            whatsapp_message += f"Vehicle: {vehicle}\n"
        whatsapp_message += f"Parts Required: {parts}\n"
        if message:
            whatsapp_message += f"Additional Info: {message}\n"
        whatsapp_message += f"Contact Method: {contact_method}\n"
        whatsapp_message += f"Urgency: {urgency}"

        return redirect(f"https://wa.me/447440369576?text={whatsapp_message.replace(' ', '%20').replace('\n', '%0A')}")

    return render_template('enquiry.html')

@app.route('/about')
def about():
    return render_template('about.html')
@app.route('/warranty')
def warranty():
    return render_template('warranty.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/faqs')
def faqs():
    return render_template('faqs.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')
# ============================================
# PARTS INVENTORY ROUTES
# ============================================

@app.route('/parts')
def parts_index():
    parts = parts_agent.get_all_parts()
    return render_template('parts_index.html', parts=parts)

@app.route('/parts/search')
def parts_search():
    query = request.args.get('q', '').strip()
    parts = parts_agent.search_parts(query)
    return render_template('parts_index.html', parts=parts, search_query=query)

@app.route('/parts/add', methods=['GET', 'POST'])
@login_required
def parts_add():
    if request.method == 'POST':
        data = {
            'stock_id': request.form['stock_id'],
            'part_name': request.form['part_name'],
            'category': request.form['category'],
            'part_type': request.form.get('part_type', ''),
            'make': request.form.get('make', ''),
            'model': request.form.get('model', ''),
            'generation': request.form.get('generation', ''),
            'oem_number': request.form.get('oem_number', ''),
            'engine_code': request.form.get('engine_code', ''),
            'condition': request.form.get('condition', 'Good'),
            'price': float(request.form.get('price', 0)),
            'stock_status': request.form.get('stock_status', 'Available'),
            'location': request.form.get('location', ''),
            'notes': request.form.get('notes', '')
        }
        result = parts_agent.add_part(data)
        if result['success']:
            flash('✅ Part added successfully!', 'success')
            return redirect(url_for('parts_index'))
        else:
            flash(f'❌ Error: {result["error"]}', 'error')
    return render_template('parts_add.html')

@app.route('/parts/<int:id>')
def parts_view(id):
    part = parts_agent.get_part(id)
    if not part:
        flash('Part not found', 'error')
        return redirect(url_for('parts_index'))
    return render_template('parts_view.html', part=part)

@app.route('/parts/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def parts_edit(id):
    part = parts_agent.get_part(id)
    if not part:
        flash('Part not found', 'error')
        return redirect(url_for('parts_index'))
    
    if request.method == 'POST':
        data = {
            'stock_id': request.form['stock_id'],
            'part_name': request.form['part_name'],
            'category': request.form['category'],
            'part_type': request.form.get('part_type', ''),
            'make': request.form.get('make', ''),
            'model': request.form.get('model', ''),
            'generation': request.form.get('generation', ''),
            'oem_number': request.form.get('oem_number', ''),
            'engine_code': request.form.get('engine_code', ''),
            'condition': request.form.get('condition', 'Good'),
            'price': float(request.form.get('price', 0)),
            'stock_status': request.form.get('stock_status', 'Available'),
            'location': request.form.get('location', ''),
            'notes': request.form.get('notes', '')
        }
        result = parts_agent.update_part(id, data)
        if result['success']:
            flash('✅ Part updated successfully!', 'success')
            return redirect(url_for('parts_view', id=id))
        else:
            flash(f'❌ Error: {result["error"]}', 'error')
    
    return render_template('parts_edit.html', part=part)

@app.route('/parts/delete/<int:id>', methods=['POST'])
@login_required
def parts_delete(id):
    result = parts_agent.delete_part(id)
    if result['success']:
        flash('✅ Part deleted', 'success')
    else:
        flash('❌ Delete failed', 'error')
    return redirect(url_for('parts_index'))

# ============================================
# PUBLIC PARTS ROUTES
# ============================================

@app.route('/parts-public')
def parts_public():
    """Public parts page - all parts"""
    parts = parts_agent.get_all_parts()
    return render_template('parts_public.html', parts=parts)

@app.route('/parts-public/search')
def parts_public_search():
    """Search public parts"""
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('parts_public'))
    parts = parts_agent.search_parts(query)
    return render_template('parts_public.html', parts=parts, search_query=query)

@app.route('/parts-public/category/<category>')
def parts_public_category(category):
    """Filter parts by category"""
    all_parts = parts_agent.get_all_parts()
    parts = [p for p in all_parts if p.get('category') == category]
    return render_template('parts_public.html', parts=parts, selected_category=category)

@app.route('/part/<int:id>')
def part_public_view(id):
    """Public part detail page"""
    part = parts_agent.get_part(id)
    if not part:
        flash('Part not found', 'error')
        return redirect(url_for('parts_public'))
    return render_template('part_public_view.html', part=part)

@app.route('/delivery')
def delivery():
    return render_template('delivery.html')

@app.route('/parts/bulk-import', methods=['GET', 'POST'])
@login_required
def parts_bulk_import():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(url_for('parts_bulk_import'))
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('parts_bulk_import'))
        
        if file and file.filename.endswith('.csv'):
            # Read CSV
            import csv
            import io
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.DictReader(stream)
            
            added = 0
            errors = []
            
            for row in csv_input:
                try:
                    data = {
                        'stock_id': row.get('stock_id', '').strip(),
                        'part_name': row.get('part_name', '').strip(),
                        'category': row.get('category', '').strip(),
                        'part_type': row.get('part_type', '').strip(),
                        'make': row.get('make', '').strip(),
                        'model': row.get('model', '').strip(),
                        'generation': row.get('generation', '').strip(),
                        'oem_number': row.get('oem_number', '').strip(),
                        'engine_code': row.get('engine_code', '').strip(),
                        'condition': row.get('condition', 'Good').strip(),
                        'price': float(row.get('price', 0)) if row.get('price') else 0,
                        'stock_status': row.get('stock_status', 'Available').strip(),
                        'location': row.get('location', '').strip(),
                        'notes': row.get('notes', '').strip()
                    }
                    result = parts_agent.add_part(data)
                    if result['success']:
                        added += 1
                    else:
                        errors.append(f"Row {csv_input.line_num}: {result['error']}")
                except Exception as e:
                    errors.append(f"Row {csv_input.line_num}: {str(e)}")
            
            flash(f'✅ Added {added} parts successfully!', 'success')
            if errors:
                flash(f'❌ Errors: {", ".join(errors[:5])}', 'error')
            return redirect(url_for('parts_index'))
        else:
            flash('Please upload a CSV file', 'error')
            return redirect(url_for('parts_bulk_import'))
    
    return render_template('parts_bulk_import.html')
    
# ============================================
# RUN THE APP
# ============================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)

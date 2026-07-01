from flask import Flask, render_template, request, redirect, url_for, session, flash
from enquiries_store import enquiries_store
from email_reply_agent import handle_enquiry_auto_reply
import sqlite3
import os
import json
from functools import wraps
from datetime import datetime
from parts_agent import parts_agent
from flask_wtf.csrf import CSRFProtect
from flask import send_from_directory
from forms import PartForm
from openai import OpenAI
import httpx
from flask import jsonify
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
sessions = {}
import re

app = Flask(__name__)
csrf = CSRFProtect(app)

# ============================================
# CACHE-BUSTING
# ============================================
@app.context_processor
def inject_version():
    import time
    return {'version': int(time.time())}

# ============================================
# CONTENT SECURITY POLICY (CSP) - FIXED
# ============================================
@app.after_request
def add_csp_header(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com https://maps.googleapis.com https://maps.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://maps.googleapis.com; "
        "img-src 'self' data: https://via.placeholder.com https://images.pexels.com https://maps.googleapis.com https://maps.gstatic.com https://i.postimg.cc; "
        "font-src 'self' https://cdnjs.cloudflare.com; "
        "connect-src 'self' https://maps.googleapis.com; "
        "frame-src 'self' https://www.google.com https://maps.google.com; "
        "object-src 'none'; "
        "base-uri 'self'"
    )
    return response
    
# ============================================
# CONFIGURATION
# ============================================
app.secret_key = os.getenv('SECRET_KEY', 'cherrywood_yard_secret_key_2026')

if os.getenv('RENDER'):
    DATABASE = os.path.join('/data', 'inventory.db')
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
            print("Database initialized")
    except Exception as e:
        print(f"DB init error: {e}")

init_db()

# ============================================
# BACKUP SYSTEM
# ============================================
def auto_backup_vehicles():
    try:
        db = get_db()
        rows = db.execute('SELECT * FROM vehicle ORDER BY id DESC').fetchall()
        db.close()
        vehicles = [dict(row) for row in rows]
        with open('vehicles_backup.json', 'w') as f:
            json.dump(vehicles, f, indent=2)
        return True
    except:
        return False

def restore_from_backup():
    try:
        if not os.path.exists('vehicles_backup.json'):
            return False
        with open('vehicles_backup.json', 'r') as f:
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
    except:
        return False

def backup_after_change(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        auto_backup_vehicles()
        return result
    return wrapper

# ============================================
# VEHICLE ROUTES
# ============================================
@app.route('/')
def index():
    try:
        db = get_db()
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
            WHERE title LIKE ? OR make LIKE ? OR model LIKE ? OR parts_available LIKE ?
            ORDER BY id DESC''', (search_term, search_term, search_term, search_term)).fetchall()
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
        meta_description = f"Find used {v['title']} parts at Cherrywood Auto Parts. {v['make']} {v['model']} {v['year']} breaking for parts. UK delivery available."
        return render_template('vehicle_detail.html', vehicle=v, meta_description=meta_description)
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
# VEHICLE ADMIN
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
        flash(f'❌ Error: {e}', 'error')
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
            flash('✅ Vehicle updated!', 'success')
            auto_backup_vehicles()
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'❌ Error: {e}', 'error')
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
        flash('✅ Vehicle deleted!', 'success')
        auto_backup_vehicles()
    except Exception as e:
        flash(f'❌ Delete failed: {e}', 'error')
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
        backup_file = os.path.join('/data', 'vehicles_backup.json')
        with open(backup_file, 'w') as f:
            json.dump(vehicles, f, indent=2)
        flash(f'✅ Backup created with {len(vehicles)} vehicles!', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'❌ Backup failed: {e}', 'error')
        return redirect(url_for('index'))

@app.route('/admin/restore', methods=['POST'])
@login_required
def restore_vehicles():
    try:
        backup_dir = '/data/backups/'
        if not os.path.exists(backup_dir):
            flash('❌ No backup folder found. Please run a backup first.', 'error')
            return redirect(url_for('index'))
        files = sorted([f for f in os.listdir(backup_dir) if f.startswith('full_backup_')], reverse=True)
        if not files:
            flash('❌ No backup files found. Please run a backup first.', 'error')
            return redirect(url_for('index'))
        latest_backup = os.path.join(backup_dir, files[0])
        with open(latest_backup, 'r') as f:
            data = json.load(f)
        vehicles = data.get('vehicles', [])
        parts = data.get('parts', [])
        flash(f'⚠️ This will REPLACE all current data with backup from {data["timestamp"]}', 'warning')
        flash(f'📊 Vehicles: {len(vehicles)} | Parts: {len(parts)}', 'info')
        flash('👉 Click "Restore" again to confirm, or "Cancel" to abort.', 'info')
        session['pending_restore'] = data
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'❌ Error: {e}', 'error')
        return redirect(url_for('index'))

@app.route('/admin/restore-confirm', methods=['POST'])
@login_required
def restore_confirm():
    try:
        data = session.pop('pending_restore', None)
        if not data:
            flash('❌ No restore pending', 'error')
            return redirect(url_for('index'))
        conn = sqlite3.connect(DATABASE)
        conn.execute('DELETE FROM vehicle')
        conn.execute('DELETE FROM parts')
        for v in data.get('vehicles', []):
            conn.execute('''INSERT INTO vehicle 
                (title, make, model, year, reg, engine, fuel, transmission, 
                 mileage, status, image_url, parts_available, description) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (v['title'], v['make'], v['model'], v['year'], v['reg'],
                 v['engine'], v['fuel'], v['transmission'], v['mileage'],
                 v['status'], v['image_url'], v['parts_available'], v['description']))
        for p in data.get('parts', []):
            conn.execute('''INSERT INTO parts 
                (stock_id, part_name, category, part_type, make, model, generation, 
                 oem_number, engine_code, condition, price, stock_status, location, notes, slug)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (p['stock_id'], p['part_name'], p['category'], p.get('part_type', ''),
                 p.get('make', ''), p.get('model', ''), p.get('generation', ''),
                 p.get('oem_number', ''), p.get('engine_code', ''),
                 p.get('condition', 'Good'), p.get('price', 0),
                 p.get('stock_status', 'Available'), p.get('location', ''),
                 p.get('notes', ''), p.get('slug', '')))
        conn.commit()
        conn.close()
        flash(f'✅ Restored {len(data["vehicles"])} vehicles and {len(data["parts"])} parts successfully!', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'❌ Restore failed: {e}', 'error')
        return redirect(url_for('index'))

@app.route('/admin/enquiries')
@login_required
def enquiries_list():
    status = request.args.get('status', 'All')
    enquiries = enquiries_store.get_all_enquiries(status_filter=status)
    counts = enquiries_store.get_counts()
    return render_template('enquiries_list.html', enquiries=enquiries, counts=counts, current_status=status)


@app.route('/admin/enquiries/<int:id>/status', methods=['POST'])
@login_required
def enquiry_update_status(id):
    new_status = request.form.get('status', 'New')
    enquiries_store.update_status(id, new_status)
    flash(f'✅ Enquiry #{id} marked as {new_status}', 'success')
    return redirect(url_for('enquiries_list'))

# ============================================
# INFO PAGES
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
        vehicle = request.form.get('vehicle')
        parts = request.form.get('parts')
        message = request.form.get('message')
        whatsapp = f"Hi Cherrywood, part enquiry:\nName: {name}\nEmail: {email}\nReg: {reg}\nParts: {parts}\nMessage: {message}"
        return redirect(f"https://wa.me/447440369576?text={whatsapp.replace(' ', '%20').replace('\n', '%0A')}")
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

@app.route('/delivery')
def delivery():
    return render_template('delivery.html')

# ============================================
# PARTS INVENTORY ROUTES - FIXED MASTER ROUTE
# ============================================
@app.route('/parts-public')
def parts_public():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get filter parameters
    category = request.args.get('category', None)
    price_range = request.args.get('price', None)
    status = request.args.get('status', None)
    sort = request.args.get('sort', 'newest')
    search_query = request.args.get('q', '').strip()

    # Call the NEW fast database method
    result = parts_agent.get_parts(
        page=page, per_page=per_page,
        category=category, price_range=price_range,
        status=status, sort=sort, search_query=search_query
    )
    
    parts = result['parts']
    total = result['total']
    pages = (total + per_page - 1) // per_page

    # Preserve current filters for pagination links
    filter_args = request.args.copy()
    filter_args.pop('page', None)

    return render_template('parts_public.html', 
                           parts=parts, 
                           page=page, 
                           pages=pages, 
                           selected_category=category,
                           search_query=search_query,
                           filter_args=filter_args)

@app.route('/parts')
def parts_index():
    try:
        parts = parts_agent.get_all_parts()
        return render_template('parts_index.html', parts=parts)
    except Exception as e:
        flash(f'Error loading parts: {e}', 'error')
        return render_template('parts_index.html', parts=[])

# ===== Other Parts routes =====
@app.route('/parts/search')
def parts_search():
    query = request.args.get('q', '').strip()
    if not query:
        flash('Please enter a search term', 'error')
        return redirect(url_for('parts_index'))
    parts = parts_agent.search_parts(query)
    if not parts:
        flash('No parts found matching your search', 'error')
    return render_template('parts_index.html', parts=parts, search_query=query)

@app.route('/parts/add', methods=['GET', 'POST'])
@login_required
def parts_add():
    form = PartForm()
    if form.validate_on_submit():
        data = {
            'stock_id': form.stock_id.data,
            'part_name': form.part_name.data,
            'category': form.category.data,
            'part_type': form.part_type.data or '',
            'make': form.make.data or '',
            'model': form.model.data or '',
            'generation': form.generation.data or '',
            'oem_number': form.oem_number.data or '',
            'engine_code': form.engine_code.data or '',
            'condition': form.condition.data or 'Good',
            'price': form.price.data or 0,
            'stock_status': form.stock_status.data or 'Available',
            'location': form.location.data or '',
            'notes': form.notes.data or ''
        }
        result = parts_agent.add_part(data)
        if result['success']:
            flash('✅ Part added successfully!', 'success')
            return redirect(url_for('parts_index'))
        else:
            flash(f'❌ Error: {result["error"]}', 'error')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'❌ {field.replace("_", " ").title()}: {error}', 'error')
    return render_template('parts_add.html', form=form)

@app.route('/parts/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def parts_edit(id):
    part = parts_agent.get_part(id)
    if not part:
        flash('Part not found', 'error')
        return redirect(url_for('parts_index'))
    form = PartForm(obj=part)
    if form.validate_on_submit():
        data = {
            'stock_id': form.stock_id.data,
            'part_name': form.part_name.data,
            'category': form.category.data,
            'part_type': form.part_type.data or '',
            'make': form.make.data or '',
            'model': form.model.data or '',
            'generation': form.generation.data or '',
            'oem_number': form.oem_number.data or '',
            'engine_code': form.engine_code.data or '',
            'condition': form.condition.data or 'Good',
            'price': form.price.data or 0,
            'stock_status': form.stock_status.data or 'Available',
            'location': form.location.data or '',
            'notes': form.notes.data or ''
        }
        result = parts_agent.update_part(id, data)
        if result['success']:
            flash('✅ Part updated successfully!', 'success')
            return redirect(url_for('parts_view', id=id))
        else:
            flash(f'❌ Error: {result["error"]}', 'error')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'❌ {field.replace("_", " ").title()}: {error}', 'error')
    return render_template('parts_edit.html', form=form, part=part)

@app.route('/parts/delete/<int:id>', methods=['POST'])
@login_required
def parts_delete(id):
    result = parts_agent.delete_part(id)
    if result['success']:
        flash('✅ Part deleted', 'success')
    else:
        flash('❌ Delete failed', 'error')
    return redirect(url_for('parts_index'))

@app.route('/parts/view/<int:id>')
def parts_view(id):
    part = parts_agent.get_part(id)
    if not part:
        flash('Part not found', 'error')
        return redirect(url_for('parts_index'))
    return render_template('parts_view.html', part=part, parts_agent=parts_agent)

@app.route('/part/<slug>')
def part_public_view(slug):
    # We now fetch the part using the slug, not the ID
    part = parts_agent.get_part_by_slug(slug)
    if not part:
        flash('Part not found', 'error')
        return redirect(url_for('parts_public'))
    
    meta_description = f"{part['part_name']} - OEM: {part['oem_number'] or 'N/A'}. Price: £{part['price']}. Available from Cherrywood Auto Parts."
    return render_template('part_public_view.html', part=part, parts_agent=parts_agent, meta_description=meta_description, request=request)

# (Note: The old /parts-public/price, /status, /sort routes are no longer needed since we handle them in the master route above)

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
            import csv
            import io
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            result = parts_agent.bulk_import(stream.read())
            if result['success']:
                flash(f'✅ Added {result["added"]} parts successfully!', 'success')
                if result['errors']:
                    flash(f'⚠️ Errors: {", ".join(result["errors"][:5])}', 'error')
            else:
                flash(f'❌ Error: {result["error"]}', 'error')
            return redirect(url_for('parts_index'))
        else:
            flash('Please upload a CSV file', 'error')
            return redirect(url_for('parts_bulk_import'))
    return render_template('parts_bulk_import.html')
    
# ============================================
# SITEMAP & ROBOTS
# ============================================
@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory('.', 'sitemap.xml', mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    return send_from_directory('.', 'robots.txt', mimetype='text/plain')

@app.route('/googlea8a0fd57acfb2a7e.html')
def google_verify():
    return send_from_directory('.', 'googlea8a0fd57acfb2a7e.html')

@app.route('/static/googlea8a0fd57acfb2a7e.html')
def google_verify_static():
    return send_from_directory('static', 'googlea8a0fd57acfb2a7e.html')

@app.route('/parts/bulk-update', methods=['GET', 'POST'])
@login_required
def parts_bulk_update():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(url_for('parts_bulk_update'))
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('parts_bulk_update'))
        if file and file.filename.endswith('.csv'):
            import csv
            import io
            
            # Fix: use utf-8-sig to handle Windows BOM encoding perfectly
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
            reader = csv.DictReader(stream)
            updated = 0
            errors = []
            line = 1
            
            # Connect directly to the database to update efficiently
            db = get_db()
            
            for row in reader:
                line += 1
                stock_id = row.get('stock_id', '').strip()
                if not stock_id:
                    errors.append(f"Row {line}: Missing stock_id")
                    continue
                
                # Build the dynamic SQL update statement based on what columns the user provided
                updates = []
                params = []
                if 'price' in row and row['price'].strip():
                    updates.append("price = ?")
                    params.append(float(row['price'].strip()))
                if 'stock_status' in row and row['stock_status'].strip():
                    updates.append("stock_status = ?")
                    params.append(row['stock_status'].strip())
                if 'location' in row and row['location'].strip():
                    updates.append("location = ?")
                    params.append(row['location'].strip())
                if 'notes' in row and row['notes'].strip():
                    updates.append("notes = ?")
                    params.append(row['notes'].strip())
                
                if not updates:
                    errors.append(f"Row {line}: No valid fields to update (price/status/location/notes)")
                    continue
                
                # Always update the timestamp
                updates.append("updated_at = CURRENT_TIMESTAMP")
                
                # Run the update query directly against the stock_id
                sql = f"UPDATE parts SET {', '.join(updates)} WHERE stock_id = ?"
                params.append(stock_id)
                
                try:
                    db.execute(sql, params)
                    updated += 1
                except Exception as e:
                    errors.append(f"Row {line}: {str(e)}")
            
            db.commit()
            db.close()
            flash(f'✅ Updated {updated} parts successfully!', 'success')
            if errors:
                flash(f'⚠️ Errors: {", ".join(errors[:5])}', 'error')
            return redirect(url_for('parts_index'))
        else:
            flash('Please upload a CSV file', 'error')
            return redirect(url_for('parts_bulk_update'))
    return render_template('parts_bulk_update.html')

def send_enquiry_email(data):
    try:
        sender = os.getenv('EMAIL_USER')
        password = os.getenv('EMAIL_PASS')
        staff_recipient = os.getenv('STAFF_EMAIL')
        
        if not sender or not password or not staff_recipient:
            print("❌ Missing email environment variables", flush=True)
            return

        # --- 1. EMAIL TO THE STAFF (The one you already had) ---
        staff_subject = f"🔔 New Parts Enquiry from {data.get('name', 'Customer')}"
        staff_body = f"""
New Enquiry Received!

👤 Name: {data.get('name')}
📞 Phone: {data.get('phone')}
📧 Email: {data.get('email')}
🚗 Vehicle: {data.get('vehicle')}
🔧 Part Needed: {data.get('part')}

This enquiry was captured by the Cherrywood AI Chat Assistant.
        """
        staff_msg = MIMEMultipart()
        staff_msg['From'] = sender
        staff_msg['To'] = staff_recipient
        staff_msg['Subject'] = staff_subject
        staff_msg.attach(MIMEText(staff_body, 'plain'))

        # --- 2. EMAIL TO THE CUSTOMER (The new auto-reply) ---
        customer_email = data.get('email')
        if customer_email: # Only send if we actually have the email address
            customer_name = data.get('name')
            customer_vehicle = data.get('vehicle')
            customer_part = data.get('part')

            customer_subject = f"Thank you for your enquiry, {customer_name}!"
            customer_body = f"""
Dear {customer_name},

Thank you for reaching out to Cherrywood Auto Parts!

We have received your enquiry regarding the following:
🚗 Vehicle: {customer_vehicle}
🔧 Part Needed: {customer_part}

A member of our parts team will review this and will reach out to you at **{data.get('phone')}** within the next 2 business hours.

If you have any immediate questions, feel free to reply directly to this email or call us at 07440 369576.

Best regards,
The Cherrywood Auto Parts Team
            """
            customer_msg = MIMEMultipart()
            customer_msg['From'] = sender
            customer_msg['To'] = customer_email
            customer_msg['Subject'] = customer_subject
            customer_msg.attach(MIMEText(customer_body, 'plain'))

        # --- 3. SEND BOTH EMAILS ---
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        
        server.send_message(staff_msg)   # Send to staff
        if customer_email:
            server.send_message(customer_msg) # Send to customer
        
        server.quit()
        
        print(f"📧 Staff email sent to {staff_recipient}", flush=True)
        if customer_email:
            print(f"📧 Customer auto-reply sent to {customer_email}", flush=True)
            
    except Exception as e:
        print(f"❌ Failed to send emails: {e}", flush=True)
# ============================================
# TEMPORARY ENQUIRY STORE (Replace with real DB later)
# ============================================
class MockEnquiryStore:
    def __init__(self):
        self.enquiries = []
        self.counter = 0

    def add_enquiry(self, data):
        self.counter += 1
        record = {**data, 'id': self.counter, 'status': 'Pending'}
        self.enquiries.append(record)
        print(f"💾 Mock Enquiry #{self.counter} saved", flush=True)
        return self.counter

    def update_status(self, enquiry_id, status, notes=None):
        for e in self.enquiries:
            if e['id'] == enquiry_id:
                e['status'] = status
                if notes:
                    e['notes'] = notes
                print(f"✅ Mock Enquiry #{enquiry_id} updated to {status}", flush=True)
                return True
        return False

enquiries_store = MockEnquiryStore()
# ============================================

# ============================================
# AI CHAT PROXY ROUTE (Connects Python to Node)
# ============================================
@app.route('/api/proxy-chat', methods=['POST'])
@csrf.exempt
def proxy_chat():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({'error': 'No JSON body received'}), 400
        user_message = data.get('message', '').strip()
        session_id = data.get('sessionId', 'unknown')
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key not configured'}), 500

        # 1. Manage the conversation history (capped to keep payload size/speed under control)
        if session_id not in sessions:
            sessions[session_id] = []
        sessions[session_id].append({"role": "user", "content": user_message})
        sessions[session_id] = sessions[session_id][-10:]

        # 2. Fetch live inventory — filtered by keywords from the user's message
        try:
            db = get_db()

            stopwords = {
                'the', 'and', 'for', 'with', 'have', 'has', 'you', 'your', 'are',
                'can', 'need', 'looking', 'price', 'cost', 'much', 'how', 'what',
                'this', 'that', 'got', 'any', 'please', 'hi', 'hello', 'thanks',
                'other', 'options', 'do', 'does', 'a', 'an', 'of', 'on', 'in'
            }
            words = re.findall(r'[a-zA-Z0-9]+', user_message.lower())

            keywords = []
            for w in words:
                if len(w) <= 1 or w in stopwords:
                    continue
                # Singularize simple plurals (e.g. "engines" -> "engine", "brakes" -> "brake")
                # so they still match singular category names stored in the database.
                singular = w[:-1] if len(w) > 3 and w.endswith('s') and not w.endswith('ss') else w
                keywords.append(singular)
                if singular != w:
                    keywords.append(w)  # keep the original too, in case it's stored plural somewhere

            parts_rows = []
            if keywords:
                like_clauses = []
                params = []
                for kw in keywords[:8]:
                    term = f'%{kw}%'
                    like_clauses.append(
                        "(part_name LIKE ? OR make LIKE ? OR model LIKE ? OR category LIKE ? OR oem_number LIKE ? OR engine_code LIKE ?)"
                    )
                    params.extend([term, term, term, term, term, term])

                where_sql = " OR ".join(like_clauses)
                sql = f"""SELECT part_name, make, model, category, price, stock_status, oem_number
                          FROM parts
                          WHERE stock_status = 'Available' AND ({where_sql})
                          LIMIT 25"""
                parts_rows = db.execute(sql, params).fetchall()

            if not parts_rows:
                parts_rows = db.execute(
                    "SELECT part_name, make, model, category, price, stock_status, oem_number "
                    "FROM parts WHERE stock_status = 'Available' "
                    "ORDER BY created_at DESC LIMIT 20"
                ).fetchall()

            db.close()

            parts_list = "\n".join([
                f"- {p['part_name']} | {p['make']} {p['model']} | £{p['price']:.2f} | OEM: {p['oem_number'] or 'N/A'} | {p['category']}"
                for p in parts_rows
            ])
            inventory_context = f"Relevant available parts:\n{parts_list}" if parts_list else "No matching parts currently in stock."
        except Exception as e:
            print(f"❌ [AI] Inventory fetch error: {e}", flush=True)
            inventory_context = "Inventory temporarily unavailable."

                # 3. System prompt
        system_prompt = f"""You are a friendly auto parts assistant for Cherrywood Auto Parts.
Your job is to help customers find parts, and when they are ready, collect their details for a staff member to follow up.
{inventory_context}
CRITICAL RULE: Keep your answers short and specific. Always answer based on what you just said previously.
If the customer says "1", "2", "3", etc., it means they are selecting an option from the list YOU just gave them. Respond to that selection naturally!
If the inventory shown doesn't seem to match what the customer is asking for, let them know you'll have a staff member check current stock rather than guessing.
If a part exists for a different model than what the customer asked for, mention it but be clear it isn't confirmed for their specific model.

IF THE CUSTOMER ASKS FOR AN EXTRA PART:
If a customer submits an enquiry, and then asks about a DIFFERENT part or vehicle, treat this as a BRAND NEW separate enquiry.
You must re-collect their contact details (Name, Phone, Email, Vehicle, Part) again for this new request before triggering the final completion JSON.

ENQUIRY SUBMISSION - FOLLOW THIS EXACTLY:
Once the customer has provided their name, phone number, and/or email address along with the part or vehicle they are asking about, you MUST respond with ONLY this exact format and nothing else:
[ENQUIRY_COMPLETE]{{"name": "their name", "phone": "their phone", "email": "their email", "vehicle": "vehicle mentioned", "part": "part mentioned"}}
Do NOT write any friendly confirmation message yourself. Do NOT say "I've noted your details" or anything similar - the system will generate that confirmation automatically once it receives your JSON. Your entire response in this case must be the [ENQUIRY_COMPLETE] tag immediately followed by valid JSON, with no other text before or after it.
"""

        # 4. Call OpenAI with the HISTORY
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                *sessions[session_id]
            ],
            "max_tokens": 400
        }
        response = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)

        if response.status_code != 200:
            return jsonify({'error': f"OpenAI API Error: {response.text}"}), response.status_code
        reply = response.json()['choices'][0]['message']['content']

        sessions[session_id].append({"role": "assistant", "content": reply})
        sessions[session_id] = sessions[session_id][-10:]

               # 5. Check for the Enquiry Completion flag
        if "[ENQUIRY_COMPLETE]" in reply:
            json_str = reply.replace("[ENQUIRY_COMPLETE]", "").strip()

            try:
                customer_data = json.loads(json_str)

                # Save to database
                enquiry_id = enquiries_store.add_enquiry(customer_data)

                if enquiry_id:
                    print(f"💾 Enquiry #{enquiry_id} saved to database", flush=True)
                else:
                    print("⚠️ Enquiry DB save failed", flush=True)

                # Notify staff
                send_enquiry_email(customer_data)

                # Send automatic customer reply
                customer_reply = handle_enquiry_auto_reply(customer_data, get_db)

                if enquiry_id and customer_reply:
                    enquiries_store.update_status(
                        enquiry_id,
                        "Contacted",
                        notes=customer_reply
                    )

                return jsonify({
                    "reply": "✅ Your enquiry has been sent! We will call or email you back within 2 hours."
                })

            except json.JSONDecodeError:
                print(f"⚠️ [AI] Failed to parse enquiry JSON: {json_str}", flush=True)

        return jsonify({'reply': reply})

    except Exception as e:
        print(f"❌ [AI] FATAL ERROR: {str(e)}", flush=True)
        return jsonify({'error': str(e)}), 500
# ============================================
# RUN THE APP
# ============================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

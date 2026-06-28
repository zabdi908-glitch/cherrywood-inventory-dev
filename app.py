from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import json
from functools import wraps
from datetime import datetime
from parts_agent import parts_agent
from flask_wtf.csrf import CSRFProtect
from flask import send_from_directory
from forms import PartForm

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
    
# ============================================
# RUN THE APP
# ============================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

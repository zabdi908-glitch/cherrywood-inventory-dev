from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import json
from functools import wraps
from datetime import datetime
from parts_agent import parts_agent

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY', 'cherrywood_yard_secret_key_2026')
import os

if os.getenv('RENDER'):
    DATABASE = os.path.join('/data', 'inventory.db')  # ✅ Persistent disk
else:
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')

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
    except Exception as e:
        print(f"Database error: {e}")

init_db()

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

@app.route('/')
def index():
    try:
        db = get_db()
        rows = db.execute('SELECT * FROM vehicle WHERE status = "Breaking" ORDER BY id DESC').fetchall()
        db.close()
        vehicles_data = []
        for row in rows:
            v = dict(row)
            v['get_parts_list'] = lambda: v.get('parts_available', '').split(',') if v.get('parts_available') else []
            vehicles_data.append(v)
        return render_template('index.html', vehicles=vehicles_data)
    except:
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
            v['get_parts_list'] = lambda: v.get('parts_available', '').split(',') if v.get('parts_available') else []
            vehicles_data.append(v)
        return render_template('index.html', vehicles=vehicles_data, search_query=query)
    except:
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
    except:
        flash('Error loading vehicle', 'error')
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
        except:
            flash('❌ Error updating vehicle', 'error')
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
    except:
        flash('❌ Delete failed', 'error')
    return redirect(url_for('index'))

@app.route('/admin/restore', methods=['POST'])
@login_required
def restore_vehicles():
    if restore_from_backup():
        flash('✅ Restored from backup!', 'success')
    else:
        flash('❌ Restore failed', 'error')
    return redirect(url_for('index'))

@app.route('/admin/backup-now', methods=['POST'])
@login_required
def backup_now():
    auto_backup_vehicles()
    flash('✅ Backup created!', 'success')
    return redirect(url_for('index'))

@app.route('/gallery')
def gallery():
    try:
        db = get_db()
        rows = db.execute('SELECT * FROM vehicle ORDER BY id DESC').fetchall()
        db.close()
        vehicles_data = []
        for row in rows:
            v = dict(row)
            v['get_parts_list'] = lambda: v.get('parts_available', '').split(',') if v.get('parts_available') else []
            vehicles_data.append(v)
        return render_template('gallery.html', vehicles=vehicles_data)
    except:
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
# PARTS ROUTES
# ============================================

@app.route('/parts')
def parts_index():
    try:
        parts = parts_agent.get_all_parts()
        return render_template('parts_index.html', parts=parts)
    except Exception as e:
        flash(f'Error loading parts: {e}', 'error')
        return render_template('parts_index.html', parts=[])

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

@app.route('/parts/view/<int:id>')
def parts_view(id):
    part = parts_agent.get_part(id)
    if not part:
        flash('Part not found', 'error')
        return redirect(url_for('parts_index'))
    return render_template('parts_view.html', part=part)

@app.route('/parts-public')
def parts_public():
    parts = parts_agent.get_all_parts()
    return render_template('parts_public.html', parts=parts)

@app.route('/parts-public/search')
def parts_public_search():
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('parts_public'))
    parts = parts_agent.search_parts(query)
    return render_template('parts_public.html', parts=parts, search_query=query)

@app.route('/parts-public/category/<category>')
def parts_public_category(category):
    all_parts = parts_agent.get_all_parts()
    parts = [p for p in all_parts if p.get('category') == category]
    return render_template('parts_public.html', parts=parts, selected_category=category)

@app.route('/parts-public/price/<min_price>-<max_price>')
def parts_public_price(min_price, max_price):
    all_parts = parts_agent.get_all_parts()
    parts = [p for p in all_parts if float(min_price) <= float(p.get('price', 0)) <= float(max_price)]
    return render_template('parts_public.html', parts=parts)

@app.route('/parts-public/status/<status>')
def parts_public_status(status):
    all_parts = parts_agent.get_all_parts()
    parts = [p for p in all_parts if p.get('stock_status') == status]
    return render_template('parts_public.html', parts=parts)

@app.route('/parts-public/sort/<sort_by>')
def parts_public_sort(sort_by):
    all_parts = parts_agent.get_all_parts()
    if sort_by == 'price_asc':
        parts = sorted(all_parts, key=lambda x: float(x.get('price', 0)))
    elif sort_by == 'price_desc':
        parts = sorted(all_parts, key=lambda x: float(x.get('price', 0)), reverse=True)
    elif sort_by == 'name':
        parts = sorted(all_parts, key=lambda x: x.get('part_name', ''))
    else:
        parts = all_parts
    return render_template('parts_public.html', parts=parts)

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
    
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os

app = Flask(__name__)
# Use an environment variable for security
app.secret_key = os.getenv('SECRET_KEY', 'cherrywood_yard_secret_key_2026')

# Use an environment variable for security
app.secret_key = os.getenv('SECRET_KEY', 'cherrywood_yard_secret_2026')

# Use the persistent storage path for Render
import os
DATABASE = os.path.join(os.getcwd(), 'inventory.db')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Database init function (only runs if table doesn't exist)
def init_db():
    if not os.path.exists(DATABASE):
        with sqlite3.connect(DATABASE) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS vehicle (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT, make TEXT, model TEXT, year TEXT, reg TEXT, 
                    engine TEXT, fuel TEXT, transmission TEXT, mileage TEXT, 
                    status TEXT, image_url TEXT, parts_available TEXT, description TEXT
                )
            ''')

init_db()

@app.route('/')
def index():
    db = get_db()
    rows = db.execute('SELECT * FROM vehicle ORDER BY id DESC').fetchall()
    db.close()
    return render_template('index.html', vehicles=rows)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == 'admin' and request.form.get('password') == os.getenv('ADMIN_PASSWORD', 'cherrywood123'):
            session['logged_in'] = True
            return redirect(url_for('index'))
    return "Login Form HTML here" # Keep your existing login HTML

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_vehicle(id):
    if not session.get('logged_in'): return "Unauthorized", 403
    db = get_db()
    if request.method == 'POST':
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
        return redirect(url_for('index'))
    vehicle = db.execute('SELECT * FROM vehicle WHERE id = ?', (id,)).fetchone()
    db.close()
    return render_template('edit.html', vehicle=vehicle)

@app.route('/delete/<int:id>', methods=['POST'])
def delete_vehicle(id):
    if not session.get('logged_in'): return "Unauthorized", 403
    db = get_db()
    db.execute('DELETE FROM vehicle WHERE id = ?', (id,))
    db.commit()
    db.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=False)

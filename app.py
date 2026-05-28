from flask import Flask, render_template, redirect, url_for, request, session
import sqlite3
import os

app = Flask(__name__)

# This keeps your login session secure and encrypted
app.secret_key = "cherrywood_super_secret_key_123"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "inventory.db")

# SET YOUR PASSWORD HERE:
GARAGE_PASSWORD = "cherrywood2026"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ROUTE: The Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['password'] == GARAGE_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = "Incorrect garage password. Please try again."
    return render_template('login.html', error=error)

# ROUTE: Logout Button
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# ROUTE: Main Dashboard (Protected)
@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
        
    try:
        conn = get_db_connection()
        parts = conn.execute('SELECT * FROM inventory').fetchall()
        conn.close()
        return render_template('index.html', parts=parts)
    except sqlite3.OperationalError as e:
        return f"Database error: {e}. Run clear_and_fix.py first!"

# ROUTE: Increase Stock (Protected)
@app.route('/add/<int:item_id>')
def add_stock(item_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('UPDATE inventory SET stock = stock + 1 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

# ROUTE: Decrease Stock (Protected)
@app.route('/subtract/<int:item_id>')
def subtract_stock(item_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('UPDATE inventory SET stock = MAX(0, stock - 1) WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

# ROUTE: Add New Part (Protected)
@app.route('/add_new_part', methods=['POST'])
def add_new_part():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    part_name = request.form['part_name']
    price = request.form['price']
    stock = request.form['stock']
    
    conn = get_db_connection()
    conn.execute('INSERT INTO inventory (part_name, price, stock) VALUES (?, ?, ?)',
                 (part_name, float(price), int(stock)))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

# ROUTE: Delete Part (Protected)
@app.route('/delete/<int:item_id>')
def delete_part(item_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM inventory WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
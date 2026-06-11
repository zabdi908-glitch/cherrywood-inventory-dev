import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "cherrywood_super_secret_key"

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///salvage.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Model for Vehicles
class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    engine = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(500), default="All parts available. Contact us for prices.")
    image_url = db.Column(db.String(500), default="https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?q=80&w=500&auto=format&fit=crop")

with app.app_context():
    db.create_all()

ADMIN_PASSWORD = "cherrywood2026"

@app.route('/')
def home():
    # Public view only showing the salvage inventory
    vehicles = Vehicle.query.all()
    return render_template('index.html', vehicles=vehicles)

@app.route('/yard-manager', methods=['GET', 'POST'])
def admin_portal():
    # Hidden secret link just for you to log in and manage vehicles
    if request.method == 'POST':
        if request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('home'))
    if session.get('logged_in'):
        return render_template('index.html', vehicles=Vehicle.query.all())
    return render_template('login.html')

@app.route('/logout')
def logout():
    session['logged_in'] = False
    return redirect(url_for('home'))

@app.route('/add', methods=['POST'])
def add_vehicle():
    if session.get('logged_in'):
        title = request.form['title']
        engine = request.form['engine']
        status = request.form['status']
        desc = request.form.get('description', 'All parts available. Contact us for prices.')
        img = request.form.get('image_url')
        if not img:
            img = "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?q=80&w=500&auto=format&fit=crop"
        
        new_vehicle = Vehicle(title=title, engine=engine, status=status, description=desc, image_url=img)
        db.session.add(new_vehicle)
        db.session.commit()
    return redirect(url_for('admin_portal'))

@app.route('/delete/<int:vehicle_id>', methods=['POST'])
def delete_vehicle(vehicle_id):
    if session.get('logged_in'):
        v = Vehicle.query.get(vehicle_id)
        if v:
            db.session.delete(v)
            db.session.commit()
    return redirect(url_for('admin_portal'))

if __name__ == '__main__':
    app.run(debug=True)

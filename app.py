import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "cherrywood_super_secret_key"

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///salvage.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Upgraded Database Model tailored for deep vehicle metrics
class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    make = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    year = db.Column(db.String(10), nullable=False)
    reg = db.Column(db.String(15), nullable=False)
    engine = db.Column(db.String(50), nullable=False)
    fuel = db.Column(db.String(20), nullable=False)
    transmission = db.Column(db.String(20), nullable=False)
    mileage = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(500), default="All parts available. Contact us for prices.")
    image_url = db.Column(db.String(500), default="https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?q=80&w=500&auto=format&fit=crop")
    parts_available = db.Column(db.String(500), default="Engine,Gearbox,Doors,Wheels,Interior") # Stored as comma-separated string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Simple helper method to split our parts string inside the template easily
    def get_parts_list(self):
        if self.parts_available:
            return [p.strip() for p in self.parts_available.split(',') if p.strip()]
        return []

with app.app_context():
    db.create_all()

ADMIN_PASSWORD = "cherrywood2026"

@app.route('/')
def home():
    vehicles = Vehicle.query.order_by(Vehicle.created_at.desc()).all()
    return render_template('index.html', vehicles=vehicles)

@app.route('/yard-manager', methods=['GET', 'POST'])
def admin_portal():
    if request.method == 'POST':
        if request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('home'))
    if session.get('logged_in'):
        return render_template('index.html', vehicles=Vehicle.query.order_by(Vehicle.created_at.desc()).all())
    return render_template('login.html')

@app.route('/logout')
def logout():
    session['logged_in'] = False
    return redirect(url_for('home'))

@app.route('/add', methods=['POST'])
def add_vehicle():
    if session.get('logged_in'):
        img = request.form.get('image_url')
        if not img:
            img = "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?q=80&w=500&auto=format&fit=crop"
        
        new_vehicle = Vehicle(
            title=request.form['title'],
            make=request.form['make'],
            model=request.form['model'],
            year=request.form['year'],
            reg=request.form['reg'].upper(),
            engine=request.form['engine'],
            fuel=request.form['fuel'],
            transmission=request.form['transmission'],
            mileage=request.form['mileage'],
            status=request.form['status'],
            description=request.form.get('description', 'All parts available. Contact us for prices.'),
            image_url=img,
            parts_available=request.form.get('parts_available', 'Engine,Gearbox,Doors,Wheels,Interior')
        )
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

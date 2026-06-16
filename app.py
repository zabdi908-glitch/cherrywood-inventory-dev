import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
import google.generativeai as genai
from google.genai import types
import json

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "cherrywood-yard-secret-101")

# Configure Database
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///cherrywood.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Initialize Gemini Client
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Vehicle Database Model Structure
class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    make = db.Column(db.String(50))
    model = db.Column(db.String(50))
    year = db.Column(db.String(150))
    reg = db.Column(db.String(20))
    engine = db.Column(db.String(50))
    fuel = db.Column(db.String(50))
    transmission = db.Column(db.String(50))
    mileage = db.Column(db.String(50))
    status = db.Column(db.String(50), default="BREAKING FOR PARTS")
    components = db.Column(db.Text)  # Comma separated parts
    description = db.Column(db.Text)
    image_url = db.Column(db.Text)

    def get_parts_list(self):
        if self.components:
            return [p.strip() for p in self.components.split(",") if p.strip()]
        return []

# Create Tables automatically
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    vehicles = Vehicle.query.order_by(Vehicle.id.desc()).all()
    return render_template('index.html', vehicles=vehicles)

# THE SECRET PORTAL ENTRY WAY (Completely Hidden from Public Eyes)
@app.route('/cherrywood-gatekeeper', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        # Simple master password verification
        if password == os.environ.get("ADMIN_PASSWORD", "Cherrywood2026!"):
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            flash("Incorrect Master Security Key Access Key.")
    return '''
    <!DOCTYPE html>
    <body style="background:#0f172a; color:#fff; font-family:sans-serif; flex flex-col items-center justify-content:center; display:flex; height:100vh; margin:0;">
        <form method="POST" style="background:#111827; padding:30px; border-radius:12px; border:1px solid #334155; max-w:320px; width:100%;">
            <h2 style="margin:0 0 15px 0; font-size:16px; text-transform:uppercase; color:#f97316; letter-spacing:1px;">Cherrywood Secure Core</h2>
            <p style="font-size:11px; color:#94a3b8; margin:0 0 20px 0;">Enter your master clearance passkey:</p>
            <input type="password" name="password" placeholder="••••••••" style="width:100%; box-sizing:border-box; padding:12px; background:#000; border:1px solid #475569; color:#fff; border-radius:6px; margin-bottom:15px; outline:none;" autofocus>
            <button type="submit" style="width:100%; padding:12px; background:#22c55e; border:0; color:#fff; font-weight:bold; border-radius:6px; cursor:pointer;">Unlock Workspace</button>
        </form>
    </body>
    '''

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

@app.route('/add', methods=['POST'])
def add_vehicle():
    if not session.get('logged_in'):
        return redirect(url_for('index'))

    file = request.files.get('vehicle_photo')
    if not file:
        return redirect(url_for('index'))

    try:
        # 1. Host image temporarily via ImgBB API or base64 emulation (Using dummy/mock logic here or standard URL storage)
        # For fluid execution we assume direct pass to Gemini API model vision engine
        img_bytes = file.read()
        
        prompt = """
        Analyze this salvage vehicle image from our breaker yard. Extract structural information and output it in strict valid JSON format with these exact keys:
        {
          "title": "A summary title like '2015 Audi A3 S-Line TDI'",
          "make": "Manufacturer name",
          "model": "Model name",
          "year": "Production year",
          "reg": "License plate registration if visible, otherwise write Unknown",
          "engine": "Engine engine code if legible, otherwise estimate displacement size",
          "fuel": "Diesel, Petrol, Hybrid, or Electric",
          "transmission": "Manual or Automatic",
          "mileage": "Estimate mileage status or write Unknown",
          "components": "List 5 major body components reusable from this picture separated by commas",
          "description": "Short internal assessment summary regarding condition of panels seen."
        }
        Return only the JSON object, absolutely no wrappers, no backticks, and no markdown prose.
        """
        
        # Call Gemini Vision Agent
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content([
            types.Part.from_bytes(data=img_bytes, mime_type=file.mimetype),
            prompt
        ])
        
        # Clean response and format JSON data
        clean_text = response.text.replace("```json", "").replace("
```", "").strip()
        data = json.loads(clean_text)
        
        # Fallback tracking logic for hosting image layout
        # (In your local file system, replace with your active imgbb upload lines if needed)
        # Using a dummy stock placeholder for illustration
        placeholder_url = "https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?q=80&w=600"

        new_car = Vehicle(
            title=data.get('title', 'Salvage Vehicle Arrival'),
            make=data.get('make', 'Unknown'),
            model=data.get('model', 'Unknown'),
            year=data.get('year', 'Unknown'),
            reg=data.get('reg', 'Unknown').upper(),
            engine=data.get('engine', 'Unknown'),
            fuel=data.get('fuel', 'Unknown'),
            transmission=data.get('transmission', 'Unknown'),
            mileage=data.get('mileage', 'Unknown'),
            components=data.get('components', 'Engine, Gearbox, Doors'),
            description=data.get('description', ''),
            image_url=placeholder_url
        )
        
        db.session.add(new_car)
        db.session.commit()
        
    except Exception as e:
        print(f"Operational Master Engine Error: {e}")
        
    return redirect(url_for('index'))

# THE CORRECTION ROUTE (Allows you to edit anything the AI got wrong)
@app.route('/edit/<int:car_id>', methods=['POST'])
def edit_vehicle(car_id):
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    car = Vehicle.query.get_or_404(car_id)
    car.title = request.form.get('title')
    car.make = request.form.get('make')
    car.model = request.form.get('model')
    car.year = request.form.get('year')
    car.reg = request.form.get('reg', '').upper()
    car.engine = request.form.get('engine')
    car.fuel = request.form.get('fuel')
    car.transmission = request.form.get('transmission')
    car.mileage = request.form.get('mileage')
    car.components = request.form.get('components')
    car.description = request.form.get('description')
    
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:car_id>', methods=['POST'])
def delete_vehicle(car_id):
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    car = Vehicle.query.get_or_404(car_id)
    db.session.delete(car)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)

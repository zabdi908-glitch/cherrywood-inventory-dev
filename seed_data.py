import sqlite3
import os

if os.getenv('RENDER'):
    DATABASE = os.path.join('/tmp', 'inventory.db')
else:
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')

def seed_database():
    vehicles = [
        {
            'title': '2015 Audi A3 Breaker - All Parts Available',
            'make': 'Audi',
            'model': 'A3',
            'year': '2015',
            'reg': 'AB15 XYZ',
            'engine': '2.0 TDI',
            'fuel': 'Diesel',
            'transmission': 'Manual',
            'mileage': '82,000',
            'status': 'Breaking',
            'image_url': 'https://via.placeholder.com/400x300/1a1a2e/ffffff?text=Audi+A3',
            'parts_available': 'Engine, Gearbox, Headlights, Doors, Seats',
            'description': 'Complete breakage of Audi A3 2.0 TDI. All parts tested and ready for collection.'
        },
        {
            'title': '2017 Volkswagen Golf GTI Parts Donor',
            'make': 'Volkswagen',
            'model': 'Golf GTI',
            'year': '2017',
            'reg': 'CD17 EFG',
            'engine': '2.0 TSI',
            'fuel': 'Petrol',
            'transmission': 'DSG',
            'mileage': '45,000',
            'status': 'Breaking',
            'image_url': 'https://via.placeholder.com/400x300/1a1a2e/ffffff?text=Golf+GTI',
            'parts_available': 'Turbo, ECU, Alloy Wheels, Bumper, Tailgate',
            'description': 'Low mileage Golf GTI being broken for parts. All major components available.'
        }
    ]
    
    try:
        conn = sqlite3.connect(DATABASE)
        for vehicle in vehicles:
            conn.execute('''INSERT INTO vehicle 
                           (title, make, model, year, reg, engine, fuel, 
                            transmission, mileage, status, image_url, parts_available, description) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (vehicle['title'], vehicle['make'], vehicle['model'],
                         vehicle['year'], vehicle['reg'], vehicle['engine'],
                         vehicle['fuel'], vehicle['transmission'], vehicle['mileage'],
                         vehicle['status'], vehicle['image_url'],
                         vehicle['parts_available'], vehicle['description']))
        conn.commit()
        conn.close()
        print(f"Database seeded with {len(vehicles)} vehicles!")
    except Exception as e:
        print(f"Error seeding database: {e}")

if __name__ == '__main__':
    seed_database()

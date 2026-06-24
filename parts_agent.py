import sqlite3
import json
import os
import csv
import io
import time
from datetime import datetime

class PartsAgent:
    def __init__(self):
        if os.getenv('RENDER'):
            self.database = os.path.join('/data', 'inventory.db')
        else:
            self.database = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')
        self.init_tables()

    def init_tables(self):
        try:
            conn = sqlite3.connect(self.database)
            conn.execute('''CREATE TABLE IF NOT EXISTS parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_id TEXT UNIQUE,
                part_name TEXT,
                category TEXT,
                part_type TEXT,
                make TEXT,
                model TEXT,
                generation TEXT,
                oem_number TEXT,
                engine_code TEXT,
                condition TEXT,
                price REAL,
                stock_status TEXT DEFAULT 'Available',
                location TEXT,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS part_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id INTEGER,
                photo_url TEXT,
                photo_order INTEGER DEFAULT 0,
                FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
            )''')
            conn.commit()
            conn.close()
            print("Parts inventory tables ready")
        except Exception as e:
            print(f"Parts table error: {e}")

    def get_db(self):
        conn = sqlite3.connect(self.database, timeout=20)
        conn.row_factory = sqlite3.Row
        return conn

    def add_part(self, data):
        try:
            conn = self.get_db()
            cursor = conn.execute('''INSERT INTO parts 
                (stock_id, part_name, category, part_type, make, model, generation, 
                 oem_number, engine_code, condition, price, stock_status, location, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (data.get('stock_id'), data.get('part_name'), data.get('category'),
                 data.get('part_type'), data.get('make'), data.get('model'),
                 data.get('generation'), data.get('oem_number'), data.get('engine_code'),
                 data.get('condition'), data.get('price'), data.get('stock_status', 'Available'),
                 data.get('location'), data.get('notes')))
            part_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return {'success': True, 'id': part_id}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_part(self, part_id):
        try:
            conn = self.get_db()
            part = conn.execute('SELECT * FROM parts WHERE id = ?', (part_id,)).fetchone()
            conn.close()
            return dict(part) if part else None
        except Exception as e:
            return None

    def get_all_parts(self):
        try:
            conn = self.get_db()
            parts = conn.execute('SELECT * FROM parts ORDER BY created_at DESC').fetchall()
            conn.close()
            return [dict(p) for p in parts]
        except Exception as e:
            return []

    def search_parts(self, query):
        try:
            conn = self.get_db()
            search = f'%{query}%'
            parts = conn.execute('''SELECT * FROM parts 
                WHERE part_name LIKE ? 
                OR oem_number LIKE ? 
                OR make LIKE ? 
                OR model LIKE ? 
                OR engine_code LIKE ?
                OR category LIKE ?
                OR stock_id LIKE ?
                ORDER BY created_at DESC''',
                (search, search, search, search, search, search, search)).fetchall()
            conn.close()
            return [dict(p) for p in parts]
        except Exception as e:
            return []

    def update_part(self, part_id, data):
        try:
            conn = self.get_db()
            conn.execute('''UPDATE parts SET 
                stock_id=?, part_name=?, category=?, part_type=?, 
                make=?, model=?, generation=?, oem_number=?, engine_code=?, 
                condition=?, price=?, stock_status=?, location=?, notes=?, 
                updated_at=CURRENT_TIMESTAMP
                WHERE id=?''',
                (data.get('stock_id'), data.get('part_name'), data.get('category'),
                 data.get('part_type'), data.get('make'), data.get('model'),
                 data.get('generation'), data.get('oem_number'), data.get('engine_code'),
                 data.get('condition'), data.get('price'), data.get('stock_status', 'Available'),
                 data.get('location'), data.get('notes'), part_id))
            conn.commit()
            conn.close()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_part(self, part_id):
        try:
            conn = self.get_db()
            conn.execute('DELETE FROM parts WHERE id = ?', (part_id,))
            conn.commit()
            conn.close()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_photo(self, part_id, photo_url, order=0):
        try:
            conn = self.get_db()
            conn.execute('INSERT INTO part_photos (part_id, photo_url, photo_order) VALUES (?, ?, ?)',
                        (part_id, photo_url, order))
            conn.commit()
            conn.close()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_photos(self, part_id):
        try:
            conn = self.get_db()
            photos = conn.execute('SELECT * FROM part_photos WHERE part_id = ? ORDER BY photo_order', (part_id,)).fetchall()
            conn.close()
            return [dict(p) for p in photos]
        except Exception as e:
            return []

    def delete_photo(self, photo_id):
        try:
            conn = self.get_db()
            conn.execute('DELETE FROM part_photos WHERE id = ?', (photo_id,))
            conn.commit()
            conn.close()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def bulk_import(self, csv_content):
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            added = 0
            errors = []
            line = 1

            for row in reader:
                line += 1
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
                    if not data['stock_id']:
                        errors.append(f"Row {line}: Missing stock_id")
                        continue

                    result = self.add_part(data)
                    if result['success']:
                        added += 1
                    else:
                        errors.append(f"Row {line}: {result['error']}")
                    time.sleep(0.02)
                except Exception as e:
                    errors.append(f"Row {line}: {str(e)}")

            return {'success': True, 'added': added, 'errors': errors}
        except Exception as e:
            return {'success': False, 'error': str(e)}

parts_agent = PartsAgent()

import sqlite3
import json
import os
import csv
import io
import time
import re
import unicodedata
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
                slug TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            try:
                conn.execute('ALTER TABLE parts ADD COLUMN slug TEXT')
            except:
                pass
            # New vehicle-spec fields — each wrapped individually so this is
            # safe to run on every startup, same pattern as slug above.
            # Existing parts simply get NULL/blank for these until edited.
            for column_def in [
                'registration TEXT',
                'vin TEXT',
                'mileage INTEGER',
                'year INTEGER',
                'fuel_type TEXT',
                'transmission TEXT',
                'engine_size TEXT',
                'colour TEXT',
                'side TEXT',
                'position TEXT',
            ]:
                try:
                    conn.execute(f'ALTER TABLE parts ADD COLUMN {column_def}')
                except:
                    pass
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

    def slugify(self, text):
        if not text:
            return ''
        text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
        text = re.sub(r'[^\w\s-]', '', text).strip().lower()
        text = re.sub(r'[-\s]+', '-', text)
        return text

    def generate_slug(self, part_name, part_id):
        base_slug = self.slugify(part_name)
        if not base_slug:
            base_slug = f"part-{part_id}"
        return f"{base_slug}-{part_id}"

    def get_part_by_slug(self, slug):
        try:
            conn = self.get_db()
            part = conn.execute('SELECT * FROM parts WHERE slug = ?', (slug,)).fetchone()
            conn.close()
            return dict(part) if part else None
        except Exception as e:
            return None

    # ============================================
    # CRUD OPERATIONS
    # ============================================

    def add_part(self, data):
        try:
            conn = self.get_db()
            cursor = conn.execute('''INSERT INTO parts 
                (stock_id, part_name, category, part_type, make, model, generation, 
                 oem_number, engine_code, condition, price, stock_status, location, notes,
                 registration, vin, mileage, year, fuel_type, transmission, engine_size,
                 colour, side, position)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (data.get('stock_id'), data.get('part_name'), data.get('category'),
                 data.get('part_type'), data.get('make'), data.get('model'),
                 data.get('generation'), data.get('oem_number'), data.get('engine_code'),
                 data.get('condition'), data.get('price'), data.get('stock_status', 'Available'),
                 data.get('location'), data.get('notes'),
                 data.get('registration'), data.get('vin'),
                 int(data['mileage']) if data.get('mileage') not in (None, '') else None,
                 int(data['year']) if data.get('year') not in (None, '') else None,
                 data.get('fuel_type'), data.get('transmission'), data.get('engine_size'),
                 data.get('colour'), data.get('side'), data.get('position')))
            part_id = cursor.lastrowid
            slug = self.generate_slug(data.get('part_name', ''), part_id)
            conn.execute('UPDATE parts SET slug = ? WHERE id = ?', (slug, part_id))
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

    def get_similar_parts(self, part_id, category, limit=4):
        """Other available parts in the same category, excluding this one."""
        try:
            conn = self.get_db()
            rows = conn.execute(
                '''SELECT * FROM parts 
                   WHERE category = ? AND id != ? AND stock_status = 'Available'
                   ORDER BY created_at DESC LIMIT ?''',
                (category, part_id, limit)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"Error in get_similar_parts: {e}")
            return []

    def get_same_vehicle_parts(self, part_id, registration, make, model, year, limit=6):
        """Other parts from the same donor vehicle. Matches on registration
        when available (the most reliable signal, since two parts sharing a
        reg definitely came from the same car) — falls back to make/model/
        year if registration isn't set on this part."""
        try:
            conn = self.get_db()
            if registration:
                rows = conn.execute(
                    '''SELECT * FROM parts 
                       WHERE registration = ? AND id != ?
                       ORDER BY created_at DESC LIMIT ?''',
                    (registration, part_id, limit)
                ).fetchall()
            elif make and model and year:
                rows = conn.execute(
                    '''SELECT * FROM parts 
                       WHERE make = ? AND model = ? AND year = ? AND id != ?
                       ORDER BY created_at DESC LIMIT ?''',
                    (make, model, year, part_id, limit)
                ).fetchall()
            else:
                rows = []
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"Error in get_same_vehicle_parts: {e}")
            return []

    def get_parts_by_ids(self, part_ids):
        """Batch lookup — used for rendering 'Recently Viewed' from a list
        of IDs stored in the customer's browser."""
        if not part_ids:
            return []
        try:
            conn = self.get_db()
            placeholders = ','.join('?' * len(part_ids))
            rows = conn.execute(
                f'SELECT * FROM parts WHERE id IN ({placeholders})', part_ids
            ).fetchall()
            conn.close()
            parts_by_id = {r['id']: dict(r) for r in rows}
            # Preserve the original order (most-recently-viewed first),
            # since SQL's IN clause doesn't guarantee any particular order
            return [parts_by_id[pid] for pid in part_ids if pid in parts_by_id]
        except Exception as e:
            print(f"Error in get_parts_by_ids: {e}")
            return []

    def get_all_parts(self):
        try:
            conn = self.get_db()
            parts = conn.execute('SELECT * FROM parts ORDER BY created_at DESC').fetchall()
            conn.close()
            return [dict(p) for p in parts]
        except Exception as e:
            return []

    def get_parts(self, page=1, per_page=20, category=None, price_range=None, status=None, sort='newest', search_query=None):
        try:
            conn = self.get_db()
            where_clauses = []
            params = []
            
            if category:
                where_clauses.append("category = ?")
                params.append(category)
            if status:
                where_clauses.append("stock_status = ?")
                params.append(status)
            if price_range:
                min_p, max_p = map(float, price_range.split('-'))
                where_clauses.append("price >= ? AND price <= ?")
                params.extend([min_p, max_p])
            if search_query:
                search_term = f'%{search_query}%'
                where_clauses.append("(part_name LIKE ? OR oem_number LIKE ? OR make LIKE ? OR model LIKE ? OR engine_code LIKE ? OR stock_id LIKE ?)")
                params.extend([search_term, search_term, search_term, search_term, search_term, search_term])

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            count_sql = f"SELECT COUNT(*) as total FROM parts {where_sql}"
            total = conn.execute(count_sql, params).fetchone()['total']

            order_sql = "ORDER BY created_at DESC"
            if sort == 'price_asc':
                order_sql = "ORDER BY price ASC"
            elif sort == 'price_desc':
                order_sql = "ORDER BY price DESC"
            elif sort == 'name':
                order_sql = "ORDER BY part_name ASC"

            offset = (page - 1) * per_page
            sql = f"SELECT * FROM parts {where_sql} {order_sql} LIMIT ? OFFSET ?"
            params.extend([per_page, offset])

            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return {'parts': [dict(r) for r in rows], 'total': total}
        except Exception as e:
            print(f"Error in get_parts: {e}")
            return {'parts': [], 'total': 0}

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
                registration=?, vin=?, mileage=?, year=?, fuel_type=?,
                transmission=?, engine_size=?, colour=?, side=?, position=?,
                updated_at=CURRENT_TIMESTAMP
                WHERE id=?''',
                (data.get('stock_id'), data.get('part_name'), data.get('category'),
                 data.get('part_type'), data.get('make'), data.get('model'),
                 data.get('generation'), data.get('oem_number'), data.get('engine_code'),
                 data.get('condition'), data.get('price'), data.get('stock_status', 'Available'),
                 data.get('location'), data.get('notes'),
                 data.get('registration'), data.get('vin'),
                 int(data['mileage']) if data.get('mileage') not in (None, '') else None,
                 int(data['year']) if data.get('year') not in (None, '') else None,
                 data.get('fuel_type'), data.get('transmission'), data.get('engine_size'),
                 data.get('colour'), data.get('side'), data.get('position'),
                 part_id))
            slug = self.generate_slug(data.get('part_name', ''), part_id)
            conn.execute('UPDATE parts SET slug = ? WHERE id = ?', (slug, part_id))
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

    # ============================================
    # PHOTO FUNCTIONS & BULK IMPORT
    # ============================================

    def add_photo(self, part_id, photo_url, order=0):
        try:
            from compress_images import compress_image, create_thumbnail
            compress_image(photo_url)
            thumb_path = create_thumbnail(photo_url)
            conn = self.get_db()
            conn.execute('INSERT INTO part_photos (part_id, photo_url, photo_order) VALUES (?, ?, ?)',
                        (part_id, photo_url, order))
            if thumb_path:
                conn.execute('INSERT INTO part_photos (part_id, photo_url, photo_order) VALUES (?, ?, ?)',
                            (part_id, thumb_path, order + 100))
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
                        'notes': row.get('notes', '').strip(),
                        'registration': row.get('registration', '').strip(),
                        'vin': row.get('vin', '').strip(),
                        'mileage': row.get('mileage', '').strip(),
                        'year': row.get('year', '').strip(),
                        'fuel_type': row.get('fuel_type', '').strip(),
                        'transmission': row.get('transmission', '').strip(),
                        'engine_size': row.get('engine_size', '').strip(),
                        'colour': row.get('colour', '').strip(),
                        'side': row.get('side', '').strip(),
                        'position': row.get('position', '').strip(),
                    }
                    if not data['stock_id']:
                        errors.append(f"Row {line}: Missing stock_id")
                        continue
                    result = self.add_part(data)
                    if result['success']:
                        added += 1
                    else:
                        errors.append(f"Row {line}: {result['error']}")
                    time.sleep(0.01)
                except Exception as e:
                    errors.append(f"Row {line}: {str(e)}")
            return {'success': True, 'added': added, 'errors': errors}
        except Exception as e:
            return {'success': False, 'error': str(e)}

parts_agent = PartsAgent()

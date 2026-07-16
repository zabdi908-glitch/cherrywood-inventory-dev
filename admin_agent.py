import sqlite3
import json
import os
import datetime
import csv
from functools import wraps

import tenants_store

class AdminAgent:
    def __init__(self):
        if os.getenv('RENDER'):
            self.database = os.path.join('/data', 'inventory.db')
        else:
            self.database = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')
        self.backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
        
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
    
    def get_connection(self):
        conn = sqlite3.connect(self.database)
        conn.row_factory = sqlite3.Row
        return conn
    
    def auto_backup(self, tenant_id):
        """Backs up one tenant's vehicles only. tenant_id is required — a
        mixed-tenant backup file would make restore_backup() unable to draw
        a clean boundary around a single tenant's data, which is exactly
        the bug this and restore_backup() were fixed together to avoid."""
        try:
            tenant = tenants_store.get_by_id(tenant_id)
            if not tenant:
                return {'success': False, 'error': f'Unknown tenant_id {tenant_id}'}

            conn = self.get_connection()
            cursor = conn.execute(
                'SELECT * FROM vehicle WHERE tenant_id = ? ORDER BY id DESC', (tenant_id,)
            )
            rows = cursor.fetchall()

            vehicles = []
            for row in rows:
                vehicles.append(dict(row))

            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(
                self.backup_dir, f"vehicles_backup_{tenant['slug']}_{timestamp}.json"
            )

            with open(backup_file, 'w') as f:
                json.dump(vehicles, f, indent=2)

            conn.close()
            self.cleanup_old_backups(tenant['slug'], 30)

            return {
                'success': True,
                'message': f"Backed up {len(vehicles)} vehicles for {tenant['slug']}",
                'file': backup_file,
                'count': len(vehicles)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def cleanup_old_backups(self, tenant_slug, keep=30):
        """Scoped to one tenant's own backup files (matched by filename
        prefix) so keeping "the last N backups" means the last N for that
        yard, not an arbitrary lexicographic mix across every tenant."""
        try:
            prefix = f'vehicles_backup_{tenant_slug}_'
            files = [f for f in os.listdir(self.backup_dir) if f.startswith(prefix)]
            files.sort()

            if len(files) > keep:
                for file in files[:-keep]:
                    os.remove(os.path.join(self.backup_dir, file))

            return {'success': True, 'deleted': len(files) - keep if len(files) > keep else 0}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def restore_backup(self, tenant_id, backup_file=None):
        """Restores one tenant's vehicles from that tenant's own backup file.
        Deletes only that tenant's existing rows first — never a blind
        DELETE FROM vehicle, which would wipe every other yard's inventory
        the moment a second tenant's data exists in this DB. tenant_id is
        required; there is no "restore everything" mode."""
        try:
            tenant = tenants_store.get_by_id(tenant_id)
            if not tenant:
                return {'success': False, 'error': f'Unknown tenant_id {tenant_id}'}

            if backup_file is None:
                prefix = f"vehicles_backup_{tenant['slug']}_"
                files = [f for f in os.listdir(self.backup_dir) if f.startswith(prefix)]
                if not files:
                    return {'success': False, 'error': f"No backup files found for {tenant['slug']}"}
                files.sort()
                backup_file = os.path.join(self.backup_dir, files[-1])

            with open(backup_file, 'r') as f:
                vehicles = json.load(f)

            conn = self.get_connection()
            conn.execute('DELETE FROM vehicle WHERE tenant_id = ?', (tenant_id,))

            for v in vehicles:
                # tenant_id is forced to the tenant this restore was called
                # for (not read from the backup row) so a stray/edited
                # backup file can never insert vehicles into the wrong tenant.
                conn.execute('''INSERT INTO vehicle
                    (title, make, model, year, reg, engine, fuel, transmission,
                     mileage, status, image_url, parts_available, description, tenant_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (v['title'], v['make'], v['model'], v['year'], v['reg'],
                     v['engine'], v['fuel'], v['transmission'], v['mileage'],
                     v['status'], v['image_url'], v['parts_available'], v['description'],
                     tenant_id))

            conn.commit()
            conn.close()

            return {
                'success': True,
                'message': f"Restored {len(vehicles)} vehicles for {tenant['slug']}",
                'count': len(vehicles)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def validate_vehicle(self, data):
        errors = []
        
        required_fields = ['title', 'make', 'model', 'year', 'reg', 'engine', 
                          'fuel', 'transmission', 'mileage', 'status']
        
        for field in required_fields:
            if not data.get(field):
                errors.append(f'{field} is required')
        
        if data.get('year'):
            try:
                year = int(data['year'])
                if year < 1900 or year > datetime.datetime.now().year + 1:
                    errors.append(f'Year {year} is invalid')
            except:
                errors.append('Year must be a number')
        
        return {'valid': len(errors) == 0, 'errors': errors}
    
    def bulk_add_vehicles(self, vehicles_list):
        try:
            conn = self.get_connection()
            added = 0
            errors = []
            
            for vehicle in vehicles_list:
                validation = self.validate_vehicle(vehicle)
                if not validation['valid']:
                    errors.append(f"Vehicle {vehicle.get('title', 'Unknown')}: {validation['errors']}")
                    continue
                
                conn.execute('''INSERT INTO vehicle 
                    (title, make, model, year, reg, engine, fuel, transmission, 
                     mileage, status, image_url, parts_available, description) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (vehicle['title'], vehicle['make'], vehicle['model'],
                     vehicle['year'], vehicle['reg'], vehicle['engine'],
                     vehicle['fuel'], vehicle['transmission'], vehicle['mileage'],
                     vehicle['status'], vehicle.get('image_url', ''),
                     vehicle.get('parts_available', ''), vehicle.get('description', '')))
                added += 1
            
            conn.commit()
            conn.close()
            
            return {
                'success': True,
                'added': added,
                'errors': errors
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def bulk_update_status(self, status, ids, tenant_id=None):
        """tenant_id defaults to the one pre-existing tenant when not passed
        (no per-request tenant context exists yet — same situation as
        restore_vehicles() in app.py); pass it explicitly once a caller has
        a real g.tenant to hand over. Scoping by tenant_id in addition to
        id IN (...) means a caller can never touch another tenant's
        vehicles even by passing in the wrong ids."""
        try:
            if tenant_id is None:
                tenant_id = tenants_store.get_default_tenant_id()
            conn = self.get_connection()
            placeholders = ','.join(['?'] * len(ids))
            conn.execute(
                f"UPDATE vehicle SET status = ? WHERE id IN ({placeholders}) AND tenant_id = ?",
                [status] + ids + [tenant_id]
            )

            updated = conn.total_changes
            conn.commit()
            conn.close()

            return {
                'success': True,
                'updated': updated,
                'message': f'Updated {updated} vehicles to {status}'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def bulk_delete(self, ids, tenant_id=None):
        """Same tenant-scoping note as bulk_update_status() above."""
        try:
            if tenant_id is None:
                tenant_id = tenants_store.get_default_tenant_id()
            conn = self.get_connection()
            placeholders = ','.join(['?'] * len(ids))
            conn.execute(
                f"DELETE FROM vehicle WHERE id IN ({placeholders}) AND tenant_id = ?",
                ids + [tenant_id]
            )

            deleted = conn.total_changes
            conn.commit()
            conn.close()

            return {
                'success': True,
                'deleted': deleted,
                'message': f'Deleted {deleted} vehicles'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def export_to_csv(self):
        try:
            conn = self.get_connection()
            cursor = conn.execute('SELECT * FROM vehicle ORDER BY id DESC')
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return {'success': False, 'error': 'No vehicles to export'}
            
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_file = os.path.join(self.backup_dir, f'vehicles_export_{timestamp}.csv')
            
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    for row in rows:
                        writer.writerow(dict(row))
            
            return {
                'success': True,
                'file': csv_file,
                'count': len(rows)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def health_check(self):
        try:
            conn = self.get_connection()
            cursor = conn.execute('SELECT COUNT(*) as count FROM vehicle')
            count = cursor.fetchone()['count']
            conn.close()
            
            backup_files = [f for f in os.listdir(self.backup_dir) if f.startswith('vehicles_backup_')]
            
            return {
                'success': True,
                'status': 'healthy',
                'vehicle_count': count,
                'backup_count': len(backup_files),
                'database_file': self.database,
                'timestamp': datetime.datetime.now().isoformat()
            }
        except Exception as e:
            return {
                'success': False,
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.datetime.now().isoformat()
            }

admin_agent = AdminAgent()
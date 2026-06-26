import sqlite3
import json
import os
from datetime import datetime

DATABASE = '/data/inventory.db'
BACKUP_DIR = '/data/backups/'

os.makedirs(BACKUP_DIR, exist_ok=True)

def create_backup():
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        vehicles_rows = conn.execute('SELECT * FROM vehicle').fetchall()
        vehicles = [dict(row) for row in vehicles_rows]
        parts_rows = conn.execute('SELECT * FROM parts').fetchall()
        parts = [dict(row) for row in parts_rows]
        conn.close()
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'vehicles': vehicles,
            'parts': parts,
            'vehicle_count': len(vehicles),
            'parts_count': len(parts)
        }
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"{BACKUP_DIR}/full_backup_{timestamp}.json"
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)
        print(f"✅ Backup created: {backup_file}")
        print(f"   Vehicles: {len(vehicles)}")
        print(f"   Parts: {len(parts)}")
        cleanup_old_backups()
        return backup_file
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return None

def cleanup_old_backups(keep=7):
    try:
        files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('full_backup_')])
        if len(files) > keep:
            for file in files[:-keep]:
                os.remove(os.path.join(BACKUP_DIR, file))
                print(f"🗑️ Removed old backup: {file}")
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

if __name__ == '__main__':
    create_backup()

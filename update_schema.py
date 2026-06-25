import sqlite3
import os
import re
import unicodedata

def slugify(text):
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    text = re.sub(r'[-\s]+', '-', text)
    return text

def generate_slug(part_name, part_id):
    base_slug = slugify(part_name)
    if not base_slug:
        base_slug = f"part-{part_id}"
    return f"{base_slug}-{part_id}"

# Connect to database
if os.getenv('RENDER'):
    DATABASE = os.path.join('/data', 'inventory.db')
else:
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')

print(f"📂 Using database: {DATABASE}")

try:
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Add slug column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE parts ADD COLUMN slug TEXT')
        print("✅ Added slug column")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ Slug column already exists")
        else:
            print(f"⚠️ Could not add slug column: {e}")

    # Generate slugs for existing parts
    cursor.execute('SELECT id, part_name FROM parts')
    parts = cursor.fetchall()
    print(f"📋 Found {len(parts)} parts to update")

    count = 0
    for part_id, part_name in parts:
        slug = generate_slug(part_name, part_id)
        cursor.execute('UPDATE parts SET slug = ? WHERE id = ?', (slug, part_id))
        count += 1
        print(f"✅ Updated part {part_id} with slug: {slug}")

    conn.commit()
    conn.close()
    print(f"🎉 Database update complete! Updated {count} parts with slugs.")

except Exception as e:
    print(f"❌ Error: {e}")

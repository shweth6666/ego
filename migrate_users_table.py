import sqlite3

conn = sqlite3.connect("qr_attendance.db")
cur = conn.cursor()

# Add columns safely (won't crash if they already exist)
try:
    cur.execute("ALTER TABLE users ADD COLUMN name TEXT")
    print("Added column: name")
except Exception as e:
    print("Column 'name' already exists or error:", e)

try:
    cur.execute("ALTER TABLE users ADD COLUMN roll_no TEXT")
    print("Added column: roll_no")
except Exception as e:
    print("Column 'roll_no' already exists or error:", e)

conn.commit()
conn.close()

print("Migration done ✅")

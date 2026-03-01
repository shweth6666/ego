import sqlite3

def migrate():
    conn = sqlite3.connect("qr_attendance.db")
    cur = conn.cursor()
    
    try:
        cur.execute("ALTER TABLE users ADD COLUMN device_id TEXT")
        print("Successfully added device_id column to users table.")
    except sqlite3.OperationalError:
        print("Column device_id already exists.")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()

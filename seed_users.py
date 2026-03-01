import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("qr_attendance.db")
cur = conn.cursor()

cur.execute("INSERT OR IGNORE INTO users (username, password, role, branch, semester) VALUES (?, ?, ?, ?, ?)",
            ("faculty1", generate_password_hash("faculty123"), "faculty", "CSE", "S6"))
cur.execute("INSERT OR IGNORE INTO users (username, password, role, branch, semester) VALUES (?, ?, ?, ?, ?)",
            ("student1", generate_password_hash("student123"), "student", "CSE", "S6"))
cur.execute("INSERT OR IGNORE INTO users (username, password, role, branch, semester) VALUES (?, ?, ?, ?, ?)",
            ("admin1", generate_password_hash("admin123"), "admin", None, None))

conn.commit()
conn.close()

print("Sample users added with hashed passwords")

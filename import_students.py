import csv
import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("qr_attendance.db")
cur = conn.cursor()

with open("students.csv", newline='', encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        cur.execute("""
            INSERT OR IGNORE INTO users
            (username, password, role, name, roll_no, branch, semester)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            row["username"],
            generate_password_hash(row["password"]),
            row["role"],
            row["name"],
            row["roll_no"],
            row["branch"],
            row["semester"]
        ))

conn.commit()
conn.close()

print("Student data imported successfully with hashed passwords")

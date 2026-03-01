import sqlite3

conn = sqlite3.connect("qr_attendance.db")
cur = conn.cursor()

for row in cur.execute("SELECT id, username, name, roll_no FROM users WHERE role='student'"):
    print(row)

conn.close()

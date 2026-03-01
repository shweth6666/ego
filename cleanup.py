import sqlite3

conn = sqlite3.connect("qr_attendance.db")
cur = conn.cursor()

# Delete old dummy users (add any usernames you used for testing)
cur.execute("DELETE FROM users WHERE username IN ('student1', 'student2', 'student3')")

conn.commit()
conn.close()

print("Old test users removed successfully ✅")

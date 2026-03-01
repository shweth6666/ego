import csv
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = "qr_attendance.db"

def reimport_all():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Clear current users to avoid any confusion with old passwords
    # Except the admin1 which we use for management
    cur.execute("DELETE FROM users WHERE username != 'admin1'")
    
    # 🧑‍🏫 Import Faculty
    try:
        with open("faculty.csv", newline='', encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cur.execute("""
                    INSERT INTO users (username, password, role, name, branch)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    row["username"].strip(),
                    generate_password_hash(row["password"].strip()),
                    "faculty",
                    row["name"].strip(),
                    row["branch"].strip()
                ))
    except Exception as e:
        print(f"Faculty error: {e}")

    # 🎓 Import Students
    try:
        with open("students.csv", newline='', encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cur.execute("""
                    INSERT INTO users (username, password, role, name, roll_no, branch, semester)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["username"].strip(),
                    generate_password_hash(row["password"].strip()),
                    "student",
                    row["name"].strip(),
                    row["roll_no"].strip(),
                    row["branch"].strip(),
                    row["semester"].strip()
                ))
    except Exception as e:
        print(f"Student error: {e}")

    conn.commit()
    conn.close()
    print("SUCCESS: All Faculty and Student passwords have been reset and updated from CSV files.")

if __name__ == "__main__":
    reimport_all()

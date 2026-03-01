import csv
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = "qr_attendance.db"

def import_faculty():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        with open("faculty.csv", newline='', encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                # Using INSERT OR IGNORE to prevent duplicates
                cur.execute("""
                    INSERT OR IGNORE INTO users
                    (username, password, role, name, branch)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    row["username"],
                    generate_password_hash(row["password"]),
                    row["role"],
                    row["name"],
                    row["branch"]
                ))
                if cur.rowcount > 0:
                    count += 1
            
            conn.commit()
            print(f"Successfully imported {count} new faculty members into the database.")
            
    except FileNotFoundError:
        print("Error: faculty.csv not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    import_faculty()

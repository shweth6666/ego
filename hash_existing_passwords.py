import sqlite3
from werkzeug.security import generate_password_hash

def hash_existing_passwords():
    conn = sqlite3.connect("qr_attendance.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("SELECT id, password FROM users")
    users = cur.fetchall()
    
    for user in users:
        # Check if already hashed (werkzeug hashes usually start with 'scrypt:' or 'pbkdf2:')
        pwd = user["password"]
        if pwd and not pwd.startswith("scrypt:") and not pwd.startswith("pbkdf2:"):
            hashed = generate_password_hash(pwd)
            cur.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, user["id"]))
            
    conn.commit()
    conn.close()
    print("All existing passwords have been successfully hashed.")

if __name__ == "__main__":
    hash_existing_passwords()

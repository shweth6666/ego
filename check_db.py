import mysql.connector

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Delvin@2005",
    "database": "campus_event"
}

try:
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("--- Branches ---")
    cur.execute('SELECT DISTINCT branch FROM subjects')
    print("Subjects:", cur.fetchall())

    cur.execute('SELECT DISTINCT branch FROM users')
    print("Users:", cur.fetchall())

    cur.execute('SELECT DISTINCT branch FROM timetable')
    print("Timetable:", cur.fetchall())

    print("\n--- Semesters ---")
    cur.execute('SELECT DISTINCT semester FROM subjects')
    print("Subjects:", cur.fetchall())

    cur.execute('SELECT DISTINCT semester FROM users')
    print("Users:", cur.fetchall())

    cur.execute('SELECT DISTINCT semester FROM timetable')
    print("Timetable:", cur.fetchall())

    conn.close()
except mysql.connector.Error as e:
    print(f"Error: {e}")

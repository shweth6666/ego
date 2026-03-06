import mysql.connector

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "123456",
    "database": "qr_attendance"
}

def seed_timetable():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Get mappings for subjects and faculty
        cur.execute("SELECT id, name FROM subjects")
        subjects = {row[1]: row[0] for row in cur.fetchall()}
        
        cur.execute("SELECT id, username FROM users WHERE role='faculty'")
        faculty = {row[1].lower(): row[0] for row in cur.fetchall() if row[1]}

        mapping = {
            "RS": "ranjith",
            "CJ": "cinu",
            "SKI": "sisira",
            "AAK": "anjitha",
            "LK": "lekha",
            "VM": "visakh"
        }

        # Time slots from image
        slots = {
            1: ("09:00", "10:00"),
            2: ("10:00", "11:00"),
            3: ("11:10", "12:10"),
            4: ("12:50", "13:50"),
            5: ("14:00", "15:00"),
            6: ("15:00", "16:00")
        }

        # Timetable data [Day, Hour, SubName, FacultyInitial]
        timetable_data = [
            # Monday
            ("Monday", 1, "IEFT", "LK"), ("Monday", 2, "CD", "RS"), ("Monday", 3, "AAD", "SKI"),
            ("Monday", 4, "DA", "AAK"), ("Monday", 5, "compre", "VM"), ("Monday", 6, "CG", "CJ"),
            # Tuesday
            ("Tuesday", 1, "AAD", "SKI"), ("Tuesday", 2, "CG", "CJ"), ("Tuesday", 3, "DA", "AAK"),
            ("Tuesday", 4, "networking lab", "SKI"), ("Tuesday", 5, "networking lab", "SKI"), ("Tuesday", 6, "networking lab", "SKI"),
            # Wednesday
            ("Wednesday", 1, "CD", "RS"), ("Wednesday", 2, "CG", "CJ"), ("Wednesday", 3, "AAD", "SKI"),
            ("Wednesday", 4, "IEFT", "LK"), ("Wednesday", 5, "CD", "RS"), ("Wednesday", 6, "mini project", "AAK"),
            # Thursday
            ("Thursday", 1, "CG", "CJ"), ("Thursday", 2, "AAD", "SKI"), ("Thursday", 3, "IEFT", "LK"),
            ("Thursday", 4, "CD", "RS"), ("Thursday", 5, "CG", "CJ"), ("Thursday", 6, "AAD", "SKI"),
            # Friday
            ("Friday", 1, "CD", "RS"), ("Friday", 2, "compre", "VM"), ("Friday", 3, "DA", "AAK"),
            ("Friday", 4, "mini project", "AAK"), ("Friday", 5, "mini project", "AAK"), ("Friday", 6, "mini project", "AAK"),
            # Saturday
            ("Saturday", 1, "CG", "CJ"), ("Saturday", 2, "IEFT", "LK"), ("Saturday", 3, "CD", "RS"),
            ("Saturday", 4, "CD", "RS"), ("Saturday", 5, "DA", "AAK"), ("Saturday", 6, "AAD", "SKI")
        ]

        cur.execute("DELETE FROM timetable") # Clear existing

        count = 0
        for day, hr, sub_name, init in timetable_data:
            f_user = mapping.get(init)
            f_id = faculty.get(f_user)
            s_id = subjects.get(sub_name)
            
            if f_id and s_id:
                start, end = slots[hr]
                cur.execute("""
                    INSERT INTO timetable (faculty_id, subject_id, day_of_week, start_time, end_time, branch, semester)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (f_id, s_id, day, start, end, "CSE", "S6"))
                count += 1
            else:
                print(f"Skipping {day} Hr {hr}: Faculty {init} ({f_id}) or Subject {sub_name} ({s_id}) not found")

        conn.commit()
        conn.close()
        print(f"Successfully loaded {count} periods into the timetable.")
    except mysql.connector.Error as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    seed_timetable()

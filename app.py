import os
from dotenv import load_dotenv
load_dotenv()

import mysql.connector
from mysql.connector import Error
import math
import csv
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt
)
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

app = Flask(__name__)
CORS(app)
app.url_map.strict_slashes = False

# 🔑 Secuirty Keys - PERSISTENT for Render
# We use a fixed key so that if Render restarts, tokens and QR codes still work.
app.config["JWT_SECRET_KEY"] = "attendance-system-v1-key-2024" 
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
jwt = JWTManager(app)

# 🗝️ Encryption for QR codes - Fixed key for persistence
# We use a fixed key so that if Render restarts, existing QR codes can still be decrypted.
# This is a valid 32-byte URL-safe base64 Fernet key.
cipher_suite = Fernet(b'ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=')

# 🗄️ MySQL Database Configuration
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "123456"),
    "database": os.environ.get("DB_NAME", "qr_attendance"),
    "port": int(os.environ.get("DB_PORT", 3306))
}

# 🌐 Support for Render DATABASE_URL format
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("mysql"):
    from urllib.parse import urlparse
    parsed = urlparse(db_url)
    DB_CONFIG["host"] = parsed.hostname
    DB_CONFIG["user"] = parsed.username
    DB_CONFIG["password"] = parsed.password
    DB_CONFIG["database"] = parsed.path.lstrip('/')
    if parsed.port:
        DB_CONFIG["port"] = parsed.port

def get_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

@app.route("/api/health")
def health_check():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        conn.close()
        return jsonify({
            "status": "healthy",
            "db_users": user_count,
            "time": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def init_db():
    # First connect without database to create it if missing
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            port=DB_CONFIG.get("port", 3306)
        )
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        conn.close()
    except Error as e:
        print(f"Error during database creation: {e}")
        return

    conn = get_db()
    if not conn: return
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(255) UNIQUE,
        password TEXT,
        role VARCHAR(50)
    )
    """)
    # 🩹 Ensure all columns exist (Migration for existing databases)
    columns = {
        "name": "VARCHAR(255)",
        "roll_no": "VARCHAR(100)",
        "branch": "VARCHAR(100)",
        "semester": "VARCHAR(50)",
        "device_id": "VARCHAR(255)"
    }
    for col_name, col_type in columns.items():
        try:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        except:
            pass # Column already exists
    
    

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        faculty_id INT,
        branch VARCHAR(100),
        semester VARCHAR(50),
        subject VARCHAR(255),
        start_time DATETIME,
        latitude DOUBLE,
        longitude DOUBLE,
        expires_at DATETIME,
        radius INT DEFAULT 20
    )
    """)
    # Migration for sessions radius
    try:
        cur.execute("ALTER TABLE sessions ADD COLUMN radius INT DEFAULT 20")
    except:
        pass

    cur.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INT AUTO_INCREMENT PRIMARY KEY,
        session_id INT,
        student_id INT,
        status VARCHAR(50),
        marked_at DATETIME
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id INT AUTO_INCREMENT PRIMARY KEY,
        code VARCHAR(100) UNIQUE,
        name VARCHAR(255),
        branch VARCHAR(100),
        semester VARCHAR(50)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS timetable (
        id INT AUTO_INCREMENT PRIMARY KEY,
        faculty_id INT,
        subject_id INT,
        day_of_week VARCHAR(50),
        start_time TIME,
        end_time TIME,
        branch VARCHAR(100),
        semester VARCHAR(50)
    )
    """)

    conn.commit()

    # 🚀 Auto-seed default users if database is empty (important for Render)
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        print("Seeding default users...")
        default_users = [
            ("admin1", generate_password_hash("admin123"), "admin", "Admin User")
        ]
        for username, password, role, name in default_users:
            cur.execute(
                "INSERT INTO users (username, password, role, name) VALUES (%s, %s, %s, %s)",
                (username, password, role, name)
            )
        conn.commit()

    # 📂 Import students from CSV if available
    try:
        if os.path.exists("students.csv"):
            with open("students.csv", newline='', encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Check if user exists BEFORE hashing to save CPU
                    cur.execute("SELECT 1 FROM users WHERE username=%s", (row["username"],))
                    if cur.fetchone():
                        continue
                        
                    # Provide defaults for potentially missing columns
                    semester = row.get("semester", "N/A")
                    branch = row.get("branch", "N/A")
                    name = row.get("name", "N/A")
                    roll_no = row.get("roll_no", "N/A")
                    
                    cur.execute("""
                        INSERT INTO users 
                        (username, password, role, name, roll_no, branch, semester)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        row["username"],
                        generate_password_hash(row["password"]),
                        row["role"],
                        name,
                        roll_no,
                        branch,
                        semester
                    ))
            conn.commit()
            print("Student CSV data imported successfully.")
    except Exception as e:
        print(f"Error importing students: {e}")

    # 🧑‍🏫 Import faculty from CSV if available
    try:
        if os.path.exists("faculty.csv"):
            with open("faculty.csv", newline='', encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Check if user exists BEFORE hashing to save CPU
                    cur.execute("SELECT 1 FROM users WHERE username=%s", (row["username"],))
                    if cur.fetchone():
                        continue

                    # Provide defaults for potentially missing columns
                    semester = row.get("semester", "N/A")
                    branch = row.get("branch", "N/A")
                    name = row.get("name", "N/A")
                    
                    cur.execute("""
                        INSERT INTO users 
                        (username, password, role, name, branch, semester)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        row["username"],
                        generate_password_hash(row["password"]),
                        "faculty",
                        name,
                        branch,
                        semester
                    ))
            conn.commit()
            print("Faculty CSV data imported successfully.")
    except Exception as e:
        print(f"Error importing faculty: {e}")

    conn.close()

init_db()

# 📍 Distance calculation (Haversine)
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c



# 🔐 Login API
@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    device_id = data.get("device_id")

    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, username, password, role, name, roll_no, branch, semester, device_id FROM users WHERE username=%s",
        (username,)
    )
    user = cur.fetchone()

    if user and check_password_hash(user["password"], password):
        # 📱 Device Binding Logic for Students
        user_role = user["role"]
        stored_device = user["device_id"]
        
        if user_role == "student":
            if not device_id:
                conn.close()
                return jsonify({"success": False, "message": "Device identification missing"}), 400
            
            if stored_device is None:
                # First time login on this device - Bind it
                cur.execute("UPDATE users SET device_id = %s WHERE id = %s", (device_id, user["id"]))
                conn.commit()
            elif stored_device != device_id:
                conn.close()
                return jsonify({
                    "success": False, 
                    "message": "Access Denied: This account is linked to another device. Contact Admin to reset."
                }), 403

        conn.close()
        access_token = create_access_token(
            identity=str(user["id"]), 
            additional_claims={"role": user["role"]}
        )
        user_data = {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "name": user["name"],
            "branch": user["branch"],
            "semester": user["semester"]
        }
        return jsonify({"success": True, "message": "Logged in successfully", "access_token": access_token, "user": user_data})
    else:
        conn.close()
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

@app.route("/api/whoami", methods=["GET"])
@jwt_required()
def whoami():
    current_user_id = get_jwt_identity()
    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, username, role, name, branch, semester FROM users WHERE id = %s", (current_user_id,))
    user = cur.fetchone()
    conn.close()
    if user:
        return jsonify({"success": True, "user": dict(user)})
    return jsonify({"success": False, "message": "User not found"}), 404


# 🧑‍🏫 Faculty: Create QR Session
@app.route("/api/sessions", methods=["POST"])
@jwt_required()
def create_session():
    claims = get_jwt()
    if claims.get("role") != "faculty":
        return jsonify({"success": False, "message": "Unauthorized. Faculty only."}), 403

    data = request.json
    faculty_id = get_jwt_identity()
    branch = data.get("branch")
    semester = data.get("semester")
    subject = data.get("subject")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    radius = data.get("radius", 20)

    if latitude is None or longitude is None:
        return jsonify({
            "success": False, 
            "message": "GPS coordinates are required. Please ensure your location is turned on and permitted."
        }), 400

    start_time = datetime.now().isoformat()
    expires_at = (datetime.now() + timedelta(minutes=15)).isoformat()

    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO sessions (faculty_id, branch, semester, subject, start_time, latitude, longitude, expires_at, radius)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (faculty_id, branch, semester, subject, start_time, latitude, longitude, expires_at, radius)
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()

    return jsonify({"success": True, "session_id": session_id})

# 🧑‍🏫 Faculty: Get active session QR
@app.route("/api/sessions/<int:session_id>/qr", methods=["GET"])
@jwt_required()
def get_session_qr(session_id):
    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM sessions WHERE id=%s", (session_id,))
    session = cur.fetchone()
    conn.close()

    if not session:
        return jsonify({"success": False, "message": "Invalid session"}), 400

    if datetime.now() > datetime.fromisoformat(session["expires_at"]):
        return jsonify({"success": False, "message": "Session expired"}), 400

    payload_data = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat()
    }
    encrypted_payload = cipher_suite.encrypt(json.dumps(payload_data).encode()).decode()

    return jsonify({"success": True, "qr_payload": encrypted_payload})


# 🎓 Student: Mark Attendance (Geo + Present/Late)
@app.route("/api/attendance", methods=["POST"])
@jwt_required()
def mark_attendance():
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"success": False, "message": "Unauthorized. Student only."}), 403

    data = request.json
    qr_payload = data.get("qr_payload")
    student_id = get_jwt_identity()
    student_lat = data.get("latitude")
    student_lng = data.get("longitude")

    if student_lat is None or student_lng is None:
        return jsonify({
            "success": False, 
            "message": "GPS coordinates are required to mark attendance."
        }), 400

    if not qr_payload:
        return jsonify({"success": False, "message": "Missing qr_payload"}), 400

    # Decrypt the payload
    try:
        decrypted_bytes = cipher_suite.decrypt(qr_payload.encode())
        payload_data = json.loads(decrypted_bytes.decode())
    except InvalidToken:
        return jsonify({"success": False, "message": "Invalid or tampered QR Code"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": "Malformed QR payload"}), 400

    session_id = payload_data.get("session_id")
    qr_timestamp = datetime.fromisoformat(payload_data.get("timestamp"))

    # Rotating QR: Ensure the QR code was generated no more than 30 seconds ago!
    now = datetime.now()
    if (now - qr_timestamp).total_seconds() > 30:
        return jsonify({"success": False, "message": "QR Code expired. Scan the latest one on screen."}), 400

    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM sessions WHERE id=%s", (session_id,))
    session = cur.fetchone()

    if not session:
        conn.close()
        return jsonify({"success": False, "message": "Invalid session"}), 400

    now = datetime.now()
    # Handle both string and datetime objects if MySQL driver returns them differently
    expires_at = session["expires_at"] if isinstance(session["expires_at"], datetime) else datetime.fromisoformat(session["expires_at"])
    start_time = session["start_time"] if isinstance(session["start_time"], datetime) else datetime.fromisoformat(session["start_time"])

    if now > expires_at:
        conn.close()
        return jsonify({"success": False, "message": "QR expired"}), 400

    # 📍 Geofence Check
    teacher_lat = session["latitude"]
    teacher_lng = session["longitude"]
    allowed_radius = session.get("radius", 20) or 20

    if teacher_lat is not None and student_lat is not None:
        distance = haversine(teacher_lat, teacher_lng, student_lat, student_lng)
        
        # We use the radius specified by the faculty (default 20m)
        if distance > allowed_radius:
            conn.close()
            return jsonify({
                "success": False, 
                "message": f"Outside allowed area! Distance: {int(distance)}m. Max allowed: {allowed_radius}m."
            }), 403

    # Prevent duplicate
    cur.execute(
        "SELECT id FROM attendance WHERE session_id=%s AND student_id=%s",
        (session_id, student_id)
    )
    if cur.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Already marked"}), 400

    diff_minutes = (now - start_time).total_seconds() / 60
    status = "Present" if diff_minutes <= 10 else "Late"

    cur.execute(
        "INSERT INTO attendance (session_id, student_id, status, marked_at) VALUES (%s, %s, %s, %s)",
        (session_id, student_id, status, now.isoformat())
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "status": status})

# 📋 Faculty: Get Live Attendance List for a Session
@app.route("/api/sessions/<int:session_id>/live", methods=["GET"])
@jwt_required()
def get_live_attendance(session_id):
    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)

    # Get session info
    cur.execute("SELECT * FROM sessions WHERE id=%s", (session_id,))
    session = cur.fetchone()
    if not session:
        conn.close()
        return jsonify({"success": False, "message": "Session not found"}), 404

    # Get all attendance records with student details
    cur.execute("""
        SELECT a.student_id, a.status, a.marked_at,
               u.name, u.roll_no, u.branch, u.semester
        FROM attendance a
        JOIN users u ON a.student_id = u.id
        WHERE a.session_id = %s
        ORDER BY a.marked_at DESC
    """, (session_id,))
    rows = cur.fetchall()
    conn.close()

    attendance = [dict(r) for r in rows]
    return jsonify({
        "success": True,
        "attendance": attendance,
        "session": dict(session)
    })

# 📍 Faculty: Update Session Location (teacher moves around)
@app.route("/api/sessions/<int:session_id>/location", methods=["PUT"])
@jwt_required()
def update_session_location(session_id):
    data = request.json
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET latitude=%s, longitude=%s WHERE id=%s",
        (latitude, longitude, session_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# --- Faculty Home: Dashboard Info ---
@app.route("/api/faculty/dashboard", methods=["GET"])
@jwt_required()
def get_faculty_dashboard():
    faculty_id = get_jwt_identity()
    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    
    # Get active session
    cur.execute("SELECT id, subject, branch, semester FROM sessions WHERE faculty_id=%s AND expires_at > %s ORDER BY id DESC LIMIT 1", 
                (faculty_id, datetime.now().isoformat()))
    active_session = cur.fetchone()
    
    # Get recent attendance
    recent_attendance = []
    if active_session:
        cur.execute("""
            SELECT u.name, a.status, a.marked_at 
            FROM attendance a 
            JOIN users u ON a.student_id = u.id 
            WHERE a.session_id=%s 
            ORDER BY a.marked_at DESC LIMIT 10
        """, (active_session["id"],))
        rows = cur.fetchall()
        recent_attendance = [dict(r) for r in rows]

    conn.close()
    return jsonify({
        "success": True,
        "active_session": dict(active_session) if active_session else None,
        "recent_attendance": recent_attendance
    })

# --- Faculty: Current Timetable Period ---
@app.route("/api/faculty/current-period", methods=["GET"])
@jwt_required()
def get_current_period():
    faculty_id = get_jwt_identity()
    now = datetime.now()
    day = now.strftime('%A')
    time = now.strftime('%H:%M')
    
    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT t.*, s.name as subject_name 
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.faculty_id = %s AND t.day_of_week = %s 
        AND %s BETWEEN t.start_time AND t.end_time
    """, (faculty_id, day, time))
    period = cur.fetchone()
    conn.close()
    
    return jsonify({"success": True, "period": dict(period) if period else None})

@app.route("/api/faculty/timetable", methods=["GET"])
@jwt_required()
def get_faculty_timetable():
    faculty_id = get_jwt_identity()
    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT t.*, s.name as subject_name 
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.faculty_id = %s
        ORDER BY CASE day_of_week 
            WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 
            WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 
            WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 
        END, start_time
    """, (faculty_id,))
    rows = cur.fetchall()
    conn.close()
    return jsonify({"success": True, "timetable": [dict(r) for r in rows]})


# --- Student: Dashboard Stats ---
@app.route("/api/student/stats", methods=["GET"])
@jwt_required()
def get_student_stats():
    student_id = get_jwt_identity()
    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    
    # Overall attendance %
    cur.execute("SELECT COUNT(*) as count FROM attendance WHERE student_id=%s", (student_id,))
    present = cur.fetchone()["count"]
    
    # Ideally compare with total sessions for their branch/sem
    cur.execute("SELECT branch, semester FROM users WHERE id=%s", (student_id,))
    user = cur.fetchone()
    
    cur.execute("SELECT COUNT(*) as count FROM sessions WHERE branch=%s AND semester=%s", (user["branch"], user["semester"]))
    total_sessions = cur.fetchone()["count"]
    
    percent = (present / total_sessions * 100) if total_sessions > 0 else 0
    
    # Last 5 history
    cur.execute("""
        SELECT s.subject, a.status, a.marked_at 
        FROM attendance a
        JOIN sessions s ON a.session_id = s.id
        WHERE a.student_id = %s
        ORDER BY a.marked_at DESC LIMIT 5
    """, (student_id,))
    history = [dict(r) for r in cur.fetchall()]
    
    conn.close()
    return jsonify({
        "success": True,
        "attendance_percent": round(percent, 1),
        "present_count": present,
        "total_sessions": total_sessions,
        "recent_history": history
    })

# --- Student: Daily Timetable ---
@app.route("/api/student/timetable", methods=["GET"])
@jwt_required()
def get_student_timetable():
    student_id = get_jwt_identity()
    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    
    cur.execute("SELECT branch, semester FROM users WHERE id=%s", (student_id,))
    user = cur.fetchone()
    
    day = datetime.now().strftime('%A')
    
    cur.execute("""
        SELECT t.*, s.name as subject_name, u.name as faculty_name
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN users u ON t.faculty_id = u.id
        WHERE UPPER(t.branch) = UPPER(%s) AND UPPER(t.semester) = UPPER(%s) AND t.day_of_week = %s
        ORDER BY t.start_time
    """, (user["branch"], user["semester"], day))
    
    timetable = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"success": True, "timetable": timetable})

@app.route("/api/student/timetable-full", methods=["GET"])
@jwt_required()
def get_student_timetable_full():
    student_id = get_jwt_identity()
    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    
    cur.execute("SELECT branch, semester FROM users WHERE id=%s", (student_id,))
    user = cur.fetchone()
    
    cur.execute("""
        SELECT t.*, s.name as subject_name, u.name as faculty_name
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN users u ON t.faculty_id = u.id
        WHERE UPPER(t.branch) = UPPER(%s) AND UPPER(t.semester) = UPPER(%s)
        ORDER BY CASE day_of_week 
            WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 
            WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 
            WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 
        END, t.start_time
    """, (user["branch"], user["semester"]))
    
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({"success": True, "timetable": rows})

@app.route("/api/student/attendance-full", methods=["GET"])
@jwt_required()
def get_student_attendance_full():
    student_id = get_jwt_identity()
    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    
    cur.execute("SELECT branch, semester FROM users WHERE id=%s", (student_id,))
    user = cur.fetchone()
    
    # Get all subjects for this sem
    cur.execute("SELECT name FROM subjects WHERE branch=%s AND semester=%s", (user["branch"], user["semester"]))
    subjects = cur.fetchall()
    
    totals = []
    daily = []
    
    for r in subjects:
        # Total sessions for this subject
        cur.execute("SELECT COUNT(*) as count FROM sessions WHERE subject=%s AND branch=%s AND semester=%s", (r["name"], user["branch"], user["semester"]))
        total = cur.fetchone()["count"]
        
        # Present count
        cur.execute("""
            SELECT COUNT(*) as count FROM attendance a 
            JOIN sessions s ON a.session_id = s.id 
            WHERE a.student_id=%s AND s.subject=%s
        """, (student_id, r["name"]))
        present = cur.fetchone()["count"]
        
        percent = (present / total * 100) if total > 0 else 0
        
        totals.append({
            "subject": r["name"],
            "present": present,
            "total_classes": total,
            "percentage": percent
        })

    conn.close()

    return jsonify({
        "success": True,
        "daily_attendance": daily,
        "total_attendance": totals
    })


# 🧑‍💼 Admin: List Users (with Pagination)
@app.route("/api/admin/users", methods=["GET"])
@jwt_required()
def list_users():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized. Admin only."}), 403

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    offset = (page - 1) * per_page

    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    
    # Get total count
    cur.execute("SELECT COUNT(*) as count FROM users")
    total_users = cur.fetchone()["count"]
    total_pages = math.ceil(total_users / per_page)

    cur.execute(
        "SELECT id, username, role, name, roll_no, branch, semester FROM users LIMIT %s OFFSET %s",
        (per_page, offset)
    )
    rows = cur.fetchall()
    conn.close()

    users = [dict(r) for r in rows]

    return jsonify({
        "success": True,
        "users": users,
        "pagination": {
            "total_users": total_users,
            "total_pages": total_pages,
            "current_page": page,
            "per_page": per_page
        }
    })


# 🧑‍💼 Admin: Create User
@app.route("/api/admin/users", methods=["POST"])
@jwt_required()
def create_user():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized. Admin only."}), 403

    data = request.json
    username = data.get("username")
    password = data.get("password")
    role = data.get("role")
    name = data.get("name")
    roll_no = data.get("roll_no")
    branch = data.get("branch")
    semester = data.get("semester")

    if not username or not password or not role:
        return jsonify({"success": False, "message": "Missing required fields"}), 400

    hashed_password = generate_password_hash(password)

    try:
        conn = get_db()
        if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (username, password, role, name, roll_no, branch, semester)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (username, hashed_password, role, name, roll_no, branch, semester)
        )
        conn.commit()
        user_id = cur.lastrowid
        conn.close()
        return jsonify({"success": True, "message": "User created", "user_id": user_id}), 201
    except Error as e:
        if "Duplicate entry" in str(e):
            return jsonify({"success": False, "message": "Username already exists"}), 400
        return jsonify({"success": False, "message": str(e)}), 500


# 🧑‍💼 Admin: Update User
@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@jwt_required()
def update_user(user_id):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized. Admin only."}), 403

    data = request.json
    
    # Fields that can be updated
    allowed_fields = ["username", "password", "role", "name", "roll_no", "branch", "semester"]
    updates = []
    params = []

    for field in allowed_fields:
        if field in data:
            if field == "password":
                updates.append(f"{field} = %s")
                params.append(generate_password_hash(data[field]))
            else:
                updates.append(f"{field} = %s")
                params.append(data[field])

    if not updates:
        return jsonify({"success": False, "message": "No update data provided"}), 400

    params.append(user_id)
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"

    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor()
    cur.execute(query, tuple(params))
    conn.commit()
    
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"success": False, "message": "User not found"}), 404

    conn.close()
    return jsonify({"success": True, "message": "User updated"})


# 🧑‍💼 Admin: Delete User
@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized. Admin only."}), 403

    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"success": False, "message": "User not found"}), 404

    conn.close()
    return jsonify({"success": True, "message": "User deleted"})


# 🧑‍💼 Admin: Reset User Device Binding
@app.route("/api/admin/users/<int:user_id>/reset-device", methods=["POST"])
@jwt_required()
def reset_device(user_id):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized. Admin only."}), 403

    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor()
    cur.execute("UPDATE users SET device_id = NULL WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Device binding reset. Student can now login from a new device."})


# 🧑‍💼 Admin: List Subjects
@app.route("/api/admin/subjects", methods=["GET"])
@jwt_required()
def list_subjects():
    claims = get_jwt()
    if claims.get("role") not in ["admin", "faculty"]:
        return jsonify({"success": False, "message": "Unauthorized."}), 403

    branch = request.args.get("branch")
    semester = request.args.get("semester")

    query = "SELECT * FROM subjects"
    params = []
    
    if branch and semester:
        query += " WHERE branch = %s AND semester = %s"
        params = (branch, semester)
    elif branch:
        query += " WHERE branch = %s"
        params = (branch,)

    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return jsonify({"success": True, "subjects": [dict(r) for r in rows]})


# 📊 Admin: View All Attendance Sessions
@app.route("/api/admin/attendance", methods=["GET"])
@jwt_required()
def admin_list_attendance():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized. Admin only."}), 403

    conn = get_db()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    cur = conn.cursor(dictionary=True)
    # Get all sessions with faculty name and attendance count
    cur.execute("""
        SELECT s.id, s.branch, s.semester, s.subject, s.start_time, s.expires_at,
               u.name as faculty_name,
               COUNT(a.id) as present_count
        FROM sessions s
        LEFT JOIN users u ON s.faculty_id = u.id
        LEFT JOIN attendance a ON a.session_id = s.id
        GROUP BY s.id
        ORDER BY s.start_time DESC
        LIMIT 100
    """)
    rows = cur.fetchall()
    conn.close()
    return jsonify({"success": True, "sessions": [dict(r) for r in rows]})


# 📥 Admin: Export Attendance Report as CSV
@app.route("/api/admin/reports/export", methods=["POST"])
@jwt_required()
def export_report():
    import io
    import csv as csv_module
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized. Admin only."}), 403

    data = request.json or {}
    period = data.get("period", "weekly")  # weekly or monthly
    branch = data.get("branch", "")
    semester = data.get("semester", "")

    # Calculate date range
    now = datetime.now()
    if period == "weekly":
        cutoff = now - timedelta(days=7)
    else:
        cutoff = now - timedelta(days=30)

    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT 
            u_student.name as student_name,
            u_student.roll_no,
            u_student.branch,
            u_student.semester,
            s.subject,
            s.start_time as class_date,
            a.status,
            u_faculty.name as faculty_name
        FROM attendance a
        JOIN users u_student ON a.student_id = u_student.id
        JOIN sessions s ON a.session_id = s.id
        LEFT JOIN users u_faculty ON s.faculty_id = u_faculty.id
        WHERE s.start_time >= %s
    """
    params = [cutoff.isoformat()]

    if branch:
        query += " AND s.branch = %s"
        params.append(branch)
    if semester:
        query += " AND s.semester = %s"
        params.append(semester)

    query += " ORDER BY s.start_time DESC"

    if conn: 
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
    else:
        rows = []

    # Generate CSV
    output = io.StringIO()
    writer = csv_module.writer(output)
    writer.writerow(["Student Name", "Roll No", "Branch", "Semester", "Subject", "Class Date", "Status", "Faculty"])
    for row in rows:
        writer.writerow([
            row["student_name"], row["roll_no"], row["branch"],
            row["semester"], row["subject"],
            row["class_date"][:16] if row["class_date"] else "",
            row["status"], row["faculty_name"]
        ])

    csv_content = output.getvalue()
    output.close()

    from flask import Response
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{period}_report.csv"}
    )


# � Error Handlers (Return JSON instead of HTML)
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "message": "API endpoint not found"}), 404
    return send_from_directory('.', 'index.html')

@app.errorhandler(Exception)
def handle_exception(e):
    print(f"🔥 Server Error: {e}")
    return jsonify({"success": False, "message": "Internal server error", "error": str(e)}), 500

# 🌐 Serve Static & HTML Files
@app.route("/")
def home():
    return send_from_directory('.', 'index.html')

@app.route("/<path:path>")
def serve_files(path):
    if path.startswith("api/"):
        return jsonify({"success": False, "message": "API path error"}), 404
        
    if path in [".env", "qr_attendance.db", "app.py", "students.csv", "faculty.csv"]:
        return "Access denied", 403

    try:
        if os.path.exists(path):
            return send_from_directory('.', path)
        if os.path.exists(path + ".html"):
            return send_from_directory('.', path + ".html")
        # For PWA support: return icons or manifest
        if "icon" in path or "manifest" in path:
             return send_from_directory('.', path)
        return send_from_directory('.', 'index.html')
    except Exception:
        return send_from_directory('.', 'index.html')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

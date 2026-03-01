from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
from datetime import datetime, timedelta
import math
import csv
from io import StringIO
import os
import json
from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

app = Flask(__name__)
CORS(app)

app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "super-secret-key-change-in-production")
jwt = JWTManager(app)

# Encryption Key for QR (in production use a fixed 32 URL-safe base64-encoded string in env)
# Note: A real app should keep this constant or valid while sessions are alive.
QR_SECRET_KEY = os.environ.get("QR_SECRET_KEY", b'u-SjD8Fw4C8Kj9F_-M0A7b0nZg2O-Qk_Q7aT_xL3s2M=')
cipher_suite = Fernet(QR_SECRET_KEY)

DB_PATH = "qr_attendance.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        name TEXT,
        roll_no TEXT,
        branch TEXT,
        semester TEXT,
        device_id TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id INTEGER,
        branch TEXT,
        semester TEXT,
        subject TEXT,
        start_time TEXT,
        latitude REAL,
        longitude REAL,
        expires_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        student_id INTEGER,
        status TEXT,
        marked_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        name TEXT,
        branch TEXT,
        semester TEXT
    )
    """)

    conn.commit()
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

# 🌐 Serve HTML Files
@app.route("/")
def home():
    return send_from_directory('.', 'login.html')

@app.route("/<path:filename>")
def serve_static(filename):
    if filename.endswith(".html"):
        return send_from_directory('.', filename)
    return "File not found", 404

# 🔐 Login API
@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    device_id = data.get("device_id")

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, password, role, name, roll_no, branch, semester, device_id FROM users WHERE username=?",
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
                cur.execute("UPDATE users SET device_id = ? WHERE id = ?", (device_id, user["id"]))
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
        user_dict = dict(user)
        user_dict.pop("password", None)
        return jsonify({"success": True, "access_token": access_token, "user": user_dict})
    else:
        conn.close()
        return jsonify({"success": False, "message": "Invalid credentials"}), 401


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

    if latitude is None or longitude is None:
        return jsonify({
            "success": False, 
            "message": "GPS coordinates are required. Please ensure your location is turned on and permitted."
        }), 400

    start_time = datetime.now().isoformat()
    expires_at = (datetime.now() + timedelta(minutes=15)).isoformat()

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO sessions (faculty_id, branch, semester, subject, start_time, latitude, longitude, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (faculty_id, branch, semester, subject, start_time, latitude, longitude, expires_at)
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()

    # Create the initial encrypted QR Payload
    payload_data = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat()
    }
    encrypted_payload = cipher_suite.encrypt(json.dumps(payload_data).encode()).decode()

    return jsonify({
        "success": True,
        "session_id": session_id,
        "expires_at": expires_at,
        "qr_payload": encrypted_payload
    })


# 🧑‍🏫 Faculty: Fetch Dynamic QR Payload
# Forces the student scanning the QR to have photographed it within the last 15 seconds.
@app.route("/api/sessions/<int:session_id>/qr", methods=["GET"])
@jwt_required()
def get_qr_payload(session_id):
    claims = get_jwt()
    if claims.get("role") != "faculty":
        return jsonify({"success": False, "message": "Unauthorized."}), 403

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, expires_at FROM sessions WHERE id=?", (session_id,))
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
    cur = conn.cursor()
    cur.execute("SELECT * FROM sessions WHERE id=?", (session_id,))
    session = cur.fetchone()

    if not session:
        conn.close()
        return jsonify({"success": False, "message": "Invalid session"}), 400

    now = datetime.now()
    expires_at = datetime.fromisoformat(session["expires_at"])
    start_time = datetime.fromisoformat(session["start_time"])

    if now > expires_at:
        conn.close()
        return jsonify({"success": False, "message": "QR expired"}), 400

    # 📍 Geofence: 20 meters
    teacher_lat = session["latitude"]
    teacher_lng = session["longitude"]

    if teacher_lat is not None and student_lat is not None:
        distance = haversine(teacher_lat, teacher_lng, student_lat, student_lng)
        if distance > 20:
            conn.close()
            return jsonify({"success": False, "message": "You are outside the allowed area"}), 403

    # Prevent duplicate
    cur.execute(
        "SELECT id FROM attendance WHERE session_id=? AND student_id=?",
        (session_id, student_id)
    )
    if cur.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Already marked"}), 400

    diff_minutes = (now - start_time).total_seconds() / 60
    status = "Present" if diff_minutes <= 10 else "Late"

    cur.execute(
        "INSERT INTO attendance (session_id, student_id, status, marked_at) VALUES (?, ?, ?, ?)",
        (session_id, student_id, status, now.isoformat())
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "status": status})


# 📡 Live Attendance for a Session
@app.route("/api/sessions/<int:session_id>/live", methods=["GET"])
@jwt_required()
def live_attendance(session_id):
    claims = get_jwt()
    if claims.get("role") not in ["faculty", "admin"]:
        return jsonify({"success": False, "message": "Unauthorized."}), 403
        
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            u.name,
            u.roll_no,
            a.status,
            a.marked_at
        FROM attendance a
        JOIN users u ON a.student_id = u.id
        WHERE a.session_id = ?
        ORDER BY a.marked_at DESC
    """, (session_id,))

    rows = cur.fetchall()
    conn.close()

    data = []
    for r in rows:
        data.append({
            "name": r[0],
            "roll_no": r[1],
            "status": r[2],
            "time": r[3]
        })

    return jsonify({"success": True, "attendance": data})


# 🧑‍💼 Admin Reports (Weekly / Monthly)
@app.route("/api/admin/reports", methods=["POST"])
@jwt_required()
def admin_reports():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized. Admin only."}), 403

    data = request.json
    branch = data.get("branch")
    semester = data.get("semester")
    subject = data.get("subject")
    period = data.get("period")  # weekly / monthly

    conn = get_db()
    cur = conn.cursor()

    date_filter = "datetime('now', '-7 days')" if period == "weekly" else "datetime('now', '-30 days')"

    query = f"""
    SELECT 
        u.id as student_id,
        u.name as student_name,
        u.roll_no as roll_no,
        SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present_count,
        SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late_count,
        COUNT(a.id) as total_marked
    FROM attendance a
    JOIN sessions s ON a.session_id = s.id
    JOIN users u ON a.student_id = u.id
    WHERE s.branch = ?
      AND s.semester = ?
      AND s.subject = ?
      AND a.marked_at >= {date_filter}
    GROUP BY u.id, u.name, u.roll_no
    """

    cur.execute(query, (branch, semester, subject))
    rows = cur.fetchall()
    conn.close()

    report = []
    for r in rows:
        report.append({
            "student_id": r[0],
            "student_name": r[1],
            "roll_no": r[2],
            "present": r[3],
            "late": r[4],
            "total": r[5]
        })

    return jsonify({
        "success": True,
        "period": period,
        "branch": branch,
        "semester": semester,
        "subject": subject,
        "report": report
    })


# 📥 Admin CSV Export
@app.route("/api/admin/reports/export", methods=["POST"])
@jwt_required()
def export_admin_reports_csv():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized. Admin only."}), 403

    data = request.json
    branch = data.get("branch")
    semester = data.get("semester")
    subject = data.get("subject")
    period = data.get("period")

    conn = get_db()
    cur = conn.cursor()

    date_filter = "datetime('now', '-7 days')" if period == "weekly" else "datetime('now', '-30 days')"

    query = f"""
    SELECT 
        u.name as student_name,
        u.roll_no as roll_no,
        SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present_count,
        SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late_count,
        COUNT(a.id) as total_marked
    FROM attendance a
    JOIN sessions s ON a.session_id = s.id
    JOIN users u ON a.student_id = u.id
    WHERE s.branch = ?
      AND s.semester = ?
      AND s.subject = ?
      AND a.marked_at >= {date_filter}
    GROUP BY u.name, u.roll_no
    """

    cur.execute(query, (branch, semester, subject))
    rows = cur.fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student Name", "Roll No", "Present", "Late", "Total"])

    for r in rows:
        writer.writerow([r[0], r[1], r[2], r[3], r[4]])

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={branch}_{semester}_{subject}_{period}_report.csv"
    return response


# 🎒 Student Summary (Daily + Total %)
@app.route("/api/student/summary", methods=["POST"])
@jwt_required()
def student_summary():
    claims = get_jwt()
    
    data = request.json
    
    # If admin or faculty, they can see any student's summary by passing student_id.
    # Otherwise, student can only see their own summary.
    if claims.get("role") == "student":
        student_id = get_jwt_identity()
    else:
        student_id = data.get("student_id")
        
    if not student_id:
        return jsonify({"success": False, "message": "Missing student_id"}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT s.subject, a.status, a.marked_at
        FROM attendance a
        JOIN sessions s ON a.session_id = s.id
        WHERE a.student_id = ?
        ORDER BY a.marked_at ASC
    """, (student_id,))
    daily_rows = cur.fetchall()

    daily = [{"subject": r[0], "status": r[1], "date": r[2]} for r in daily_rows]

    cur.execute("""
        SELECT 
            s.subject,
            SUM(CASE WHEN a.status IN ('Present','Late') THEN 1 ELSE 0 END) as present_count,
            COUNT(a.id) as total_classes
        FROM attendance a
        JOIN sessions s ON a.session_id = s.id
        WHERE a.student_id = ?
        GROUP BY s.subject
    """, (student_id,))
    total_rows = cur.fetchall()

    totals = []
    for r in total_rows:
        present = r[1]
        total = r[2]
        percent = round((present / total) * 100, 2) if total > 0 else 0
        totals.append({
            "subject": r[0],
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
    cur = conn.cursor()
    
    # Get total count
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    total_pages = math.ceil(total_users / per_page)

    cur.execute(
        "SELECT id, username, role, name, roll_no, branch, semester FROM users LIMIT ? OFFSET ?",
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
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (username, password, role, name, roll_no, branch, semester)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (username, hashed_password, role, name, roll_no, branch, semester)
        )
        conn.commit()
        user_id = cur.lastrowid
        conn.close()
        return jsonify({"success": True, "message": "User created", "user_id": user_id}), 201
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Username already exists"}), 400


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
                updates.append(f"{field} = ?")
                params.append(generate_password_hash(data[field]))
            else:
                updates.append(f"{field} = ?")
                params.append(data[field])

    if not updates:
        return jsonify({"success": False, "message": "No update data provided"}), 400

    params.append(user_id)
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"

    conn = get_db()
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
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
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
    cur = conn.cursor()
    cur.execute("UPDATE users SET device_id = NULL WHERE id = ?", (user_id,))
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
        query += " WHERE branch = ? AND semester = ?"
        params = (branch, semester)
    elif branch:
        query += " WHERE branch = ?"
        params = (branch,)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    return jsonify({"success": True, "subjects": [dict(r) for r in rows]})


# 🧑‍💼 Admin: Add Subject
@app.route("/api/admin/subjects", methods=["POST"])
@jwt_required()
def add_subject():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized. Admin only."}), 403

    data = request.json
    code = data.get("code")
    name = data.get("name")
    branch = data.get("branch")
    semester = data.get("semester")

    if not code or not name:
        return jsonify({"success": False, "message": "Missing code or name"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO subjects (code, name, branch, semester) VALUES (?, ?, ?, ?)",
            (code, name, branch, semester)
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Subject added"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Subject code already exists"}), 400


# 🧑‍🏫 Faculty: Get Session History
@app.route("/api/faculty/sessions", methods=["GET"])
@jwt_required()
def faculty_sessions():
    claims = get_jwt()
    if claims.get("role") != "faculty":
        return jsonify({"success": False, "message": "Unauthorized. Faculty only."}), 403

    faculty_id = get_jwt_identity()
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.*, COUNT(a.id) as student_count
        FROM sessions s
        LEFT JOIN attendance a ON s.id = a.session_id
        WHERE s.faculty_id = ?
        GROUP BY s.id
        ORDER BY s.start_time DESC
    """, (faculty_id,))
    rows = cur.fetchall()
    conn.close()

    return jsonify({"success": True, "sessions": [dict(r) for r in rows]})


if __name__ == "__main__":
    # Get port from environment variable (default to 8080 for local)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

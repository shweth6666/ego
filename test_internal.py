from app import app
import json

with app.test_client() as client:
    print("---- Testing Faculty Login ----")
    res_fac = client.post("/api/login", json={
        "username": "faculty1",
        "password": "faculty123"
    })
    print("Faculty Login status:", res_fac.status_code)
    fac_token = res_fac.get_json().get("access_token")
    headers_fac = {"Authorization": f"Bearer {fac_token}"}

    print("\n---- Creating QR Session (Faculty) ----")
    res2 = client.post("/api/sessions", headers=headers_fac, json={
        "branch": "CSE",
        "semester": "S6",
        "subject": "CD",
        "latitude": 10.123,     # Teacher location
        "longitude": 76.123
    })
    print("Create session status:", res2.status_code)
    print("Create session response:", res2.get_json())
    
    session_data = res2.get_json()
    if not session_data.get("success"):
        print("Failed to start session. Exiting test.")
        exit(1)
    session_id = session_data["session_id"]
    qr_payload = session_data["qr_payload"]

    print("\n---- Testing Student Login ----")
    res_stu = client.post("/api/login", json={
        "username": "student1",
        "password": "student123"
    })
    print("Student Login status:", res_stu.status_code)
    stu_token = res_stu.get_json().get("access_token")
    headers_stu = {"Authorization": f"Bearer {stu_token}"}

    print("\n---- Mark Attendance (Near Location - Should PASS) ----")
    res3 = client.post("/api/attendance", headers=headers_stu, json={
        "qr_payload": qr_payload,
        "latitude": 10.1231,    # Very close to teacher
        "longitude": 76.1231
    })
    print("Attendance (near) status:", res3.status_code)
    print("Attendance (near) response:", res3.get_json())

    print("\n---- Mark Attendance (Far Location - Should FAIL) ----")
    res4 = client.post("/api/attendance", headers=headers_stu, json={
        "qr_payload": qr_payload,
        "latitude": 12.9716,    # Far away (e.g., Bangalore)
        "longitude": 77.5946
    })
    print("Attendance (far) status:", res4.status_code)
    print("Attendance (far) response:", res4.get_json())
    
    print("\n---- Mark Attendance (Waiting 16 Seconds to Test Rotating QR) ----")
    import time
    time.sleep(16)
    
    res5 = client.post("/api/attendance", headers=headers_stu, json={
        "qr_payload": qr_payload,
        "latitude": 10.1231,
        "longitude": 76.1231
    })
    print("Attendance (expired QR) status:", res5.status_code)
    print("Attendance (expired QR) response:", res5.get_json())
    
    print("\n---- Fetching new Rotating QR from Faculty ----")
    res6 = client.get(f"/api/sessions/{session_id}/qr", headers=headers_fac)
    print("Fetch QR status:", res6.status_code)
    new_qr_payload = res6.get_json().get("qr_payload")
    
    print("\n---- Testing Student 2 Login ----")
    res_stu2 = client.post("/api/login", json={
        "username": "abhisekh22",
        "password": "abhisekh333"
    })
    print("Student 2 Login status:", res_stu2.status_code)
    stu2_token = res_stu2.get_json().get("access_token")
    headers_stu2 = {"Authorization": f"Bearer {stu2_token}"}

    print("\n---- Mark Attendance (With New QR - Should PASS) ----")
    res7 = client.post("/api/attendance", headers=headers_stu2, json={
        "qr_payload": new_qr_payload,
        "latitude": 10.1231,
        "longitude": 76.1231
    })
    print("Attendance (new QR) status:", res7.status_code)
    print("Attendance (new QR) response:", res7.get_json())

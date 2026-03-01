from app import app
import json

with app.test_client() as client:
    print("---- Login as Admin ----")
    res_admin = client.post("/api/login", json={
        "username": "admin1",
        "password": "admin123"
    })
    admin_token = res_admin.get_json().get("access_token")
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    print("\n---- Adding a new Subject (POST /api/admin/subjects) ----")
    res_add = client.post("/api/admin/subjects", headers=headers_admin, json={
        "code": "CS601",
        "name": "Compiler Design",
        "branch": "CSE",
        "semester": "S6"
    })
    print("Add Status:", res_add.status_code)
    print("Add Response:", res_add.get_json())

    print("\n---- Listing Subjects (GET /api/admin/subjects) ----")
    res_list = client.get("/api/admin/subjects?branch=CSE&semester=S6", headers=headers_admin)
    print("List Status:", res_list.status_code)
    subjects = res_list.get_json()['subjects']
    print(f"Found {len(subjects)} subjects for CSE S6")
    for s in subjects:
        print(f" - {s['code']}: {s['name']}")

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

    print("\n---- Creating a new User (POST /api/admin/users) ----")
    res_create = client.post("/api/admin/users", headers=headers_admin, json={
        "username": "testuser_crud",
        "password": "testpassword",
        "role": "student",
        "name": "CRUD Tester",
        "roll_no": "TEST001",
        "branch": "CSE",
        "semester": "S6"
    })
    print("Create Status:", res_create.status_code)
    create_data = res_create.get_json()
    print("Create Response:", create_data)
    user_id = create_data.get("user_id")

    print("\n---- Listing Users (GET /api/admin/users) ----")
    res_list = client.get("/api/admin/users?per_page=5", headers=headers_admin)
    print("List Status:", res_list.status_code)
    list_data = res_list.get_json()
    print(f"Total Users: {list_data['pagination']['total_users']}")

    print("\n---- Updating User (PUT /api/admin/users/<id>) ----")
    res_update = client.put(f"/api/admin/users/{user_id}", headers=headers_admin, json={
        "name": "CRUD Tester (Updated)",
        "semester": "S7"
    })
    print("Update Status:", res_update.status_code)
    print("Update Response:", res_update.get_json())

    print("\n---- Deleting User (DELETE /api/admin/users/<id>) ----")
    res_delete = client.delete(f"/api/admin/users/{user_id}", headers=headers_admin)
    print("Delete Status:", res_delete.status_code)
    print("Delete Response:", res_delete.get_json())

    print("\n---- Verifying Deletion (GET /api/admin/users) ----")
    res_verify = client.get("/api/admin/users", headers=headers_admin)
    found = any(u['id'] == user_id for u in res_verify.get_json()['users'])
    print("User still present?", found)

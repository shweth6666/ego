from app import app

with app.test_client() as client:
    res = client.post("/api/student/summary", json={
        "student_id": 2  # student1
    })

    print("Status:", res.status_code)
    print("Response:", res.get_json())

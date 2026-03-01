from app import app

with app.test_client() as client:
    res = client.post("/api/sessions", json={
        "faculty_id": 1,
        "branch": "CSE",
        "semester": "S6",
        "subject": "CD",
        "latitude": 10.123,
        "longitude": 76.123
    })
    print(res.get_json())

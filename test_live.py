from app import app

with app.test_client() as client:
    # Replace 1 with a real session_id you created earlier
    res = client.get("/api/sessions/1/live")
    print(res.status_code)
    print(res.get_json())


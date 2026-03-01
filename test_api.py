import requests

url = "http://localhost:8080/api/login"

data = {
    "username": "faculty1",
    "password": "faculty123"
}

response = requests.post(url, json=data)
print(response.status_code)
print(response.json())

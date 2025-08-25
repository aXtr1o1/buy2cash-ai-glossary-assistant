import requests

BASE_URL = "http://localhost:8000"

def test_get_categories():
    resp = requests.get(f"{BASE_URL}/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

def test_get_sellers():
    resp = requests.get(f"{BASE_URL}/sellers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

def test_health_check():
    resp = requests.get(f"{BASE_URL}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"

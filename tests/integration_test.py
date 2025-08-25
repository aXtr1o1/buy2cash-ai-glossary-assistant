import requests

BASE_URL = "http://localhost:8000"
STORE_ID = "680fbbe429641286268a6211"

def test_product_matching_briyani():
    payload = {
        "store_id": STORE_ID,
        "user_id": "testuser001",
        "query": "I want to cook briyani"
    }
    resp = requests.post(f"{BASE_URL}/ProductMatching", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "matched_products" in data
    assert data["user_id"] == "testuser001"

def test_product_matching_pasta():
    payload = {
        "store_id": STORE_ID,
        "user_id": "testuser002",
        "query": "Show me some pasta"
    }
    resp = requests.post(f"{BASE_URL}/ProductMatching", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matched_products"]) >= 0

def test_redis_user_history():
    resp = requests.get(f"{BASE_URL}/redis/testuser001")
    assert resp.status_code == 200
    data = resp.json()
    assert "queries" in data
    assert isinstance(data["queries"], list)

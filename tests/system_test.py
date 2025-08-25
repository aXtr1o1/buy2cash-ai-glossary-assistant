import requests

BASE_URL = "http://localhost:8000"
STORE_ID = "680fbbe429641286268a6211"

def test_full_user_flow():
    assert requests.get(f"{BASE_URL}/health").status_code == 200

    categories = requests.get(f"{BASE_URL}/categories").json()
    assert isinstance(categories, list)

    sellers = requests.get(f"{BASE_URL}/sellers").json()
    assert isinstance(sellers, list)

    payload = {
        "store_id": STORE_ID,
        "user_id": "testuser003",
        "query": "I need breakfast ideas"
    }
    resp = requests.post(f"{BASE_URL}/ProductMatching", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "matched_products" in data

    redis_data = requests.get(f"{BASE_URL}/redis/testuser003").json()
    assert "queries" in redis_data

import requests

BASE_URL = "http://localhost:8000"
STORE_ID = "680fbbe429641286268a6211"

def test_invalid_store_id():
    payload = {
        "store_id": "invalid_store",
        "user_id": "testuser004",
        "query": "I want to cook briyani"
    }
    resp = requests.post(f"{BASE_URL}/ProductMatching", json=payload)
    assert resp.status_code == 400  

def test_missing_query():
    payload = {
        "store_id": STORE_ID,
        "user_id": "testuser005",
        "query": ""  
    }
    resp = requests.post(f"{BASE_URL}/ProductMatching", json=payload)
    assert resp.status_code == 422  

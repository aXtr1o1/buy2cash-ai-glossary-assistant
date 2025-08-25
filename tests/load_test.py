from locust import HttpUser, task, between

STORE_ID = "680fbbe429641286268a6211"

class GroceryLoadTest(HttpUser):
    wait_time = between(1, 3)

    @task
    def product_matching_load(self):
        payload = {
            "store_id": STORE_ID,
            "user_id": "testuser999",
            "query": "I want to cook briyani"
        }
        self.client.post("/ProductMatching", json=payload)

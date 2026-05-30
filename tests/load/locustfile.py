"""Locust load profile.

Run:  uv run locust -f tests/load/locustfile.py --host=http://localhost:8000

UI default: http://localhost:8089
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, task

API_KEY = os.environ.get("DEV_API_KEY", "dev-local-key-change-me")


class AgentStackUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.headers.update({"X-API-Key": API_KEY})

    @task(5)
    def health(self):
        self.client.get("/health")

    @task(2)
    def list_collections(self):
        self.client.get("/api/v1/collections")

    @task(1)
    def query(self):
        self.client.post(
            "/api/v1/query",
            json={
                "collection_id": "00000000-0000-0000-0000-000000000000",
                "question": random.choice(
                    [
                        "What is this project about?",
                        "Summarize the main idea.",
                        "What are the trade-offs of the chosen approach?",
                    ]
                ),
            },
        )

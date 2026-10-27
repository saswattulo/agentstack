"""Load profile for the platform layer: auth, DB reads, and cache-served queries (no LLM calls).

Run after `run_e2e.py --keep` has warmed the cache:
  BENCH_COLLECTION_ID=<id> DEV_API_KEY=<key> uv run locust -f benchmarks/locustfile.py \
    --host http://localhost:8000 --headless -u 50 -r 10 -t 60s --csv benchmarks/results/load
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

from locust import HttpUser, between, task

COLLECTION_ID = os.environ["BENCH_COLLECTION_ID"]
QUESTIONS = [
    g["question"] for g in json.loads((Path(__file__).parent / "golden_docs.json").read_text())
]


class PlatformUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.client.headers.update({"X-API-Key": os.environ["DEV_API_KEY"]})

    @task(3)
    def health(self):
        self.client.get("/health")

    @task(2)
    def me(self):
        self.client.get("/api/v1/auth/me")

    @task(2)
    def list_collections(self):
        self.client.get("/api/v1/collections")

    @task(1)
    def list_documents(self):
        self.client.get(
            f"/api/v1/collections/{COLLECTION_ID}/documents", name="/collections/[id]/documents"
        )

    @task(4)
    def cached_query(self):
        with self.client.post(
            "/api/v1/query",
            json={
                "collection_id": COLLECTION_ID,
                "question": random.choice(QUESTIONS),
                "use_web_search": False,
            },
            name="/query (cache hit)",
            catch_response=True,
        ) as r:
            if r.status_code == 200 and not r.json().get("cache_hit"):
                r.failure("expected cache hit")

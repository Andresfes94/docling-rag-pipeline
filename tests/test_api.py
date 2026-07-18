from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.retrieval.pipeline import RAGPipeline


@pytest.fixture
def client():
    return TestClient(app)


class TestAPI:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_status(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "document_count" in data
        assert "sources" in data

    def test_retrieve_empty(self, client):
        resp = client.post("/retrieve", json={"query": "test", "k": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] == 0
        assert data["results"] == []

    def test_ingest_invalid_source(self, client):
        resp = client.post("/ingest", json={
            "source": "/nonexistent/file.pdf",
            "profile": "standard",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] is not None

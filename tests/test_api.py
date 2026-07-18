from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.server import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestAPI:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_status(self, client):
        resp = await client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "document_count" in data
        assert "sources" in data
        assert "cache_entries" in data
        assert "chunk_count_by_source" in data

    async def test_retrieve_empty(self, client):
        resp = await client.post("/retrieve", json={"query": "test", "k": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] >= 0
        assert "results" in data

    async def test_retrieve_llm_format(self, client):
        resp = await client.post("/retrieve", json={
            "query": "test", "k": 3, "format": "llm",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "llm"
        assert isinstance(data["context"], str)

    async def test_retrieve_stream(self, client):
        resp = await client.get("/retrieve/stream", params={"query": "test", "k": 3})
        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct

    async def test_ingest_returns_task(self, client):
        resp = await client.post("/ingest", json={
            "source": "/nonexistent/file.pdf",
            "profile": "standard",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["source"] == "/nonexistent/file.pdf"
        assert data["status"] == "pending"

    async def test_ingest_task_status(self, client):
        resp = await client.post("/ingest", json={
            "source": "/nonexistent/file2.pdf",
            "profile": "standard",
        })
        task_id = resp.json()["task_id"]

        resp2 = await client.get(f"/ingest/{task_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["task_id"] == task_id
        assert data["status"] in ("pending", "running", "done", "failed")

    async def test_ingest_task_not_found(self, client):
        resp = await client.get("/ingest/nonexistent-task-id")
        assert resp.status_code == 404

    async def test_documents_list(self, client):
        resp = await client.get("/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert "documents" in data
        assert "total" in data

    async def test_document_not_found(self, client):
        resp = await client.get("/documents/nonexistent.pdf")
        assert resp.status_code == 404

    async def test_delete_nonexistent(self, client):
        resp = await client.delete("/documents/nonexistent.pdf")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not found" in data["error"]

    async def test_retrieve_with_filters(self, client):
        resp = await client.post("/retrieve", json={
            "query": "test",
            "k": 5,
            "sources": ["doc1.pdf"],
            "page_range": [1, 50],
            "min_score": 0.5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    async def test_retrieve_with_min_score(self, client):
        resp = await client.post("/retrieve", json={
            "query": "test",
            "k": 10,
            "min_score": 0.8,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "total_results" in data

    async def test_rate_limit_headers(self, client):
        resp = await client.get("/status")
        assert "X-Request-ID" in resp.headers
        assert "X-Response-Time-Ms" in resp.headers

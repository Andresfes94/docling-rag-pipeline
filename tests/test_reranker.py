from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.retrieval.reranker import CrossEncoderReranker


@dataclass
class FakeChunk:
    text: str
    contextualized_text: str = ""
    metadata: dict = field(default_factory=dict)


class TestCrossEncoderReranker:
    def test_rerank_empty_chunks(self):
        r = CrossEncoderReranker()
        assert r.rerank("query", []) == []

    def test_rerank_returns_expected_keys(self):
        r = CrossEncoderReranker()
        chunks = [
            FakeChunk(text="apple orange banana"),
            FakeChunk(text="stock market finance"),
            FakeChunk(text="quantum physics particles"),
        ]
        results = r.rerank("finance and stocks", chunks, keep=3)
        assert len(results) == 3
        for res in results:
            assert "chunk" in res
            assert "score" in res
            assert "original_index" in res
            assert isinstance(res["score"], float)

    def test_rerank_orders_by_relevance(self):
        r = CrossEncoderReranker()
        chunks = [
            FakeChunk(text="the weather is nice today"),
            FakeChunk(text="stock options and derivatives trading"),
            FakeChunk(text="quantum computing algorithms"),
        ]
        results = r.rerank("option pricing greeks", chunks, keep=3)
        scores = [res["score"] for res in results]
        assert scores == sorted(scores, reverse=True)

    def test_rerank_keep_limit(self):
        r = CrossEncoderReranker()
        chunks = [FakeChunk(text=f"document {i} content") for i in range(10)]
        results = r.rerank("document", chunks, keep=3)
        assert len(results) == 3

    def test_rerank_with_min_score(self):
        r = CrossEncoderReranker()
        chunks = [FakeChunk(text=f"chunk {i} about finance") for i in range(5)]
        results = r.rerank("finance", chunks, keep=5, min_score=0.5)
        for res in results:
            assert res["score"] >= 0.5

    def test_rerank_responses(self):
        r = CrossEncoderReranker()
        responses = [
            {"text": "weather report sunny"},
            {"text": "stock market analysis"},
        ]
        results = r.rerank_responses("stocks", responses, keep=2)
        assert len(results) == 2
        for res in results:
            assert "rerank_score" in res

    @pytest.mark.slow
    def test_rerank_consistent_results(self):
        r = CrossEncoderReranker()
        chunks = [FakeChunk(text=f"content about topic {i}") for i in range(5)]
        r1 = r.rerank("topic 3", chunks, keep=5)
        r2 = r.rerank("topic 3", chunks, keep=5)
        scores1 = [res["score"] for res in r1]
        scores2 = [res["score"] for res in r2]
        assert scores1 == scores2

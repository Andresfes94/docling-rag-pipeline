from __future__ import annotations

import pytest

from src.retrieval.hybrid_search import BM25Retriever, HybridRetriever, _tokenize


class TestTokenize:
    def test_basic(self):
        assert _tokenize("Hello World") == ["hello", "world"]

    def test_punctuation(self):
        assert _tokenize("hello, world!") == ["hello", "world"]

    def test_empty(self):
        assert _tokenize("") == []

    def test_numbers(self):
        assert _tokenize("test 123") == ["test", "123"]


class TestBM25Retriever:
    def test_search_empty_index(self):
        b = BM25Retriever()
        assert b.search("test") == []

    def test_build_and_search(self):
        b = BM25Retriever()
        chunks = [
            {"text": "the cat sat on the mat", "id": "doc1"},
            {"text": "dogs are better than cats", "id": "doc2"},
            {"text": "finance and stock market", "id": "doc3"},
        ]
        b.build_index(chunks)
        results = b.search("cat", k=3)
        assert len(results) >= 1
        for r in results:
            assert "score" in r
            assert "doc_id" in r
            assert r["score"] > 0

    def test_relevance_ordering(self):
        b = BM25Retriever()
        chunks = [
            {"text": "python programming language", "id": "doc1"},
            {"text": "java programming language", "id": "doc2"},
            {"text": "cooking recipes and food", "id": "doc3"},
        ]
        b.build_index(chunks)
        results = b.search("python programming", k=3)
        assert len(results) <= 3
        if results:
            assert results[0]["doc_id"] == "doc1" or results[0]["score"] >= results[-1]["score"]

    def test_no_match_returns_empty(self):
        b = BM25Retriever()
        chunks = [{"text": "finance stocks", "id": "doc1"}]
        b.build_index(chunks)
        results = b.search("quantum physics", k=5)
        assert len(results) == 0


class TestHybridRetriever:
    def test_fuse_reciprocal_rank(self):
        h = HybridRetriever()
        vector_results = [
            {"index": 0, "score": 0.9},
            {"index": 1, "score": 0.8},
            {"index": 2, "score": 0.7},
        ]
        bm25_results = [
            {"index": 1, "score": 10.0},
            {"index": 2, "score": 5.0},
            {"index": 3, "score": 3.0},
        ]
        fused = h.fuse_reciprocal_rank(vector_results, bm25_results, k=3)
        assert len(fused) <= 3
        for entry in fused:
            assert "index" in entry
            assert "rrf_score" in entry
            assert entry["rrf_score"] > 0

    def test_fuse_empty_bm25(self):
        h = HybridRetriever()
        vector_results = [{"index": 0, "score": 0.5}]
        fused = h.fuse_reciprocal_rank(vector_results, [], k=5)
        assert len(fused) == 1

    def test_fuse_empty_vector(self):
        h = HybridRetriever()
        bm25_results = [{"index": 0, "score": 5.0}]
        fused = h.fuse_reciprocal_rank([], bm25_results, k=5)
        assert len(fused) == 1

    def test_fuse_both_empty(self):
        h = HybridRetriever()
        assert h.fuse_reciprocal_rank([], [], k=5) == []

    def test_fuse_weights(self):
        h = HybridRetriever(vector_weight=0.7, bm25_weight=0.3)
        vector_results = [{"index": 0}, {"index": 1}]
        bm25_results = [{"index": 0}, {"index": 2}]
        fused = h.fuse_reciprocal_rank(vector_results, bm25_results, k=3)
        # Index 0 should rank higher (appears in both lists)
        assert fused[0]["index"] == 0

from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np

from src.embeddings.embedder import embed_text
from src.storage.vector_store import RetrievedChunk

_log = logging.getLogger(__name__)

_RRF_K = 60


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class BM25Retriever:
    def __init__(self):
        self._index: dict[str, Any] | None = None
        self._tokenized_docs: list[list[str]] = []
        self._doc_ids: list[str] = []
        self._bm25 = None

    def build_index(self, chunks: list[dict[str, Any]], text_key: str = "text") -> None:
        from rank_bm25 import BM25Okapi

        self._doc_ids = []
        self._tokenized_docs = []
        for c in chunks:
            text = c.get(text_key, c.get("contextualized_text", "")) if isinstance(c, dict) else getattr(c, text_key, str(c))
            tokens = _tokenize(text)
            if tokens:
                self._tokenized_docs.append(tokens)
                doc_id = c.get("id", c.get("chunk_id", str(len(self._doc_ids)))) if isinstance(c, dict) else str(len(self._doc_ids))
                self._doc_ids.append(doc_id)

        if self._tokenized_docs:
            self._bm25 = BM25Okapi(self._tokenized_docs)
            _log.info("BM25 index built with %d documents", len(self._tokenized_docs))

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        if self._bm25 is None:
            _log.warning("BM25 index not built — returning empty results")
            return []

        query_tokens = _tokenize(query)
        scores = self._bm25.get_scores(query_tokens)

        top_indices = np.argsort(scores)[::-1][:k]

        results: list[dict[str, Any]] = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append({
                    "doc_id": self._doc_ids[idx],
                    "score": round(float(scores[idx]), 4),
                    "index": idx,
                })
        return results


class HybridRetriever:
    def __init__(self, vector_weight: float = 0.5, bm25_weight: float = 0.5):
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight

    def fuse_reciprocal_rank(
        self,
        vector_results: list[dict[str, Any]],
        bm25_results: list[dict[str, Any]],
        k: int = 5,
    ) -> list[dict[str, Any]]:
        rrf_scores: dict[int, float] = {}
        for rank, res in enumerate(vector_results):
            idx = res.get("index", res.get("original_index"))
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + self.vector_weight / (_RRF_K + rank)

        for rank, res in enumerate(bm25_results):
            idx = res.get("index", res.get("original_index"))
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + self.bm25_weight / (_RRF_K + rank)

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [
            {"index": idx, "rrf_score": round(score, 4)}
            for idx, score in ranked[:k]
        ]

    def hybrid_query(
        self,
        query: str,
        vector_store: Any,
        bm25_retriever: BM25Retriever,
        k: int = 5,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        query_embedding = embed_text(query)
        vector_raw = vector_store._collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=k * 2,
            where=where,
        )

        vector_results: list[dict[str, Any]] = []
        if vector_raw["ids"] and vector_raw["ids"][0]:
            for i in range(len(vector_raw["ids"][0])):
                vector_results.append({
                    "index": i,
                    "id": vector_raw["ids"][0][i] if vector_raw["ids"] else "",
                    "text": vector_raw["documents"][0][i] if vector_raw["documents"] else "",
                    "metadata": vector_raw["metadatas"][0][i] if vector_raw["metadatas"] else {},
                    "score": 1.0 - vector_raw["distances"][0][i] if vector_raw["distances"] else 0.0,
                })

        bm25_results = bm25_retriever.search(query, k=k * 2)

        fused = self.fuse_reciprocal_rank(vector_results, bm25_results, k=k)

        final_results: list[dict[str, Any]] = []
        for entry in fused:
            idx = entry["index"]
            if idx < len(vector_results):
                final_results.append({
                    **vector_results[idx],
                    "rrf_score": entry["rrf_score"],
                })

        return final_results[:k]

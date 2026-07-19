from __future__ import annotations

import logging
from typing import Any

import numpy as np

_log = logging.getLogger(__name__)

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-4-v2"


class CrossEncoderReranker:
    def __init__(self, model_name: str = _DEFAULT_MODEL, top_k: int = 50):
        self.model_name = model_name
        self.top_k = top_k
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        from sentence_transformers import CrossEncoder
        _log.info("Loading cross-encoder reranker: %s...", self.model_name)
        self._model = CrossEncoder(self.model_name)

    def rerank(
        self,
        query: str,
        chunks: list[Any],
        keep: int = 5,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        if not chunks:
            return []

        self._load_model()

        pairs = [(query, c.text if hasattr(c, "text") else str(c)) for c in chunks]
        scores: list[float] = self._model.predict(pairs, show_progress_bar=False).tolist()

        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)

        top_n = indexed[:min(self.top_k, len(indexed))]
        top_n = top_n[:keep]

        results: list[dict[str, Any]] = []
        for orig_idx, score in top_n:
            if min_score is not None and score < min_score:
                continue
            chunk = chunks[orig_idx]
            results.append({
                "chunk": chunk,
                "score": round(float(score), 4),
                "original_index": orig_idx,
            })

        _log.info(
            "Reranked %d chunks → kept %d (model=%s, top_k=%d)",
            len(chunks), len(results), self.model_name, keep,
        )
        return results

    def rerank_responses(
        self,
        query: str,
        responses: list[dict[str, Any]],
        text_key: str = "text",
        keep: int = 5,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        if not responses:
            return []

        self._load_model()

        pairs = [(query, r.get(text_key, "")) for r in responses]
        scores: list[float] = self._model.predict(pairs, show_progress_bar=False).tolist()

        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)

        results: list[dict[str, Any]] = []
        for orig_idx, score in indexed[:keep]:
            if min_score is not None and score < min_score:
                continue
            entry = dict(responses[orig_idx])
            entry["rerank_score"] = round(float(score), 4)
            results.append(entry)

        return results

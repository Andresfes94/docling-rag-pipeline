from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from src.embeddings.embedder import embed_batch

_log = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    contextualized_text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    query: str
    results: list[RetrievedChunk] = field(default_factory=list)
    total_results: int = 0


class VectorStore:
    def __init__(
        self,
        persist_directory: str | Path = "data/chroma",
        collection_name: str = "documents",
    ):
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        _log.info(
            "Vector store ready: %s (%d documents)",
            self.persist_directory,
            self._collection.count(),
        )

    def add_document(
        self,
        chunks: list[Any],
        source: str,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> int:
        if not chunks:
            return 0

        texts = [c.contextualized_text for c in chunks]
        ids = [f"{source}_chunk_{c.chunk_index}" for c in chunks]
        metadatas = [
            {
                "source": source,
                "chunk_index": c.chunk_index,
                "page": c.page or 0,
                "token_count": c.token_count,
                "headings": " > ".join(c.headings) if c.headings else "",
            }
            for c in chunks
        ]

        _log.info("Embedding %d chunks...", len(texts))
        embeddings = embed_batch(texts, model_name=model_name)

        self._collection.add(
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )

        count = self._collection.count()
        _log.info("Added %d chunks. Total in store: %d", len(chunks), count)
        return count

    def query(
        self,
        query_text: str,
        k: int = 5,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        where: dict | None = None,
    ) -> RetrievalResult:
        from src.embeddings.embedder import embed_text

        _log.info("Querying with: '%s' (k=%d)", query_text[:80], k)
        query_embedding = embed_text(query_text, model_name=model_name)

        results = self._collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=k,
            where=where,
        )

        retrieved: list[RetrievedChunk] = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                retrieved.append(RetrievedChunk(
                    text=results["documents"][0][i] if results["documents"] else "",
                    contextualized_text=results["documents"][0][i] if results["documents"] else "",
                    score=1.0 - results["distances"][0][i] if results["distances"] else 0.0,
                    metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                ))

        return RetrievalResult(
            query=query_text,
            results=retrieved,
            total_results=len(retrieved),
        )

    def document_count(self) -> int:
        return self._collection.count()

    def list_sources(self) -> list[str]:
        all_meta = self._collection.get(include=["metadatas"])
        sources = set()
        for m in (all_meta.get("metadatas") or []):
            if m and "source" in m:
                sources.add(m["source"])
        return sorted(sources)

    def delete_collection(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        _log.info("Collection '%s' cleared", self._collection_name)

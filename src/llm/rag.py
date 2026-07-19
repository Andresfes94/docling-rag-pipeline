from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from src.llm.client import LLMClient

_log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial analyst assistant. Answer using ONLY the context provided below.
If the context does not contain enough information to answer, say "There is no data about this in the available documents."
Always cite the source filename and page number for each fact you use.

Format your answer in clear paragraphs. When citing sources, use [Source: Filename, Page X] inline."""


def build_rag_prompt(question: str, context: str) -> str:
    return f"""### Context from financial documents:
{context}

### Question:
{question}

### Instructions:
- Answer using ONLY the context above.
- Cite the source filename and page number for each fact using [Source: Filename, Page X].
- If the context doesn't contain the answer, say "There is no data about this in the available documents."
- Do not make up information or use external knowledge.
"""


def _build_llm_context(results: list[dict]) -> str:
    parts: list[str] = []
    for i, r in enumerate(results, 1):
        header_parts = []
        if r.get("source"):
            header_parts.append(f"Source: {r['source']}")
        if r.get("page"):
            header_parts.append(f"Page: {r['page']}")
        if r.get("headings"):
            header_parts.append(f"Section: {r['headings']}")
        header = " | ".join(header_parts)
        parts.append(f"[{i}] {header}\n{r['text']}")
    return "\n\n---\n\n".join(parts)


_PIPELINE: Any = None


def _get_pipeline():
    global _PIPELINE
    if _PIPELINE is None:
        from src.retrieval.pipeline import RAGPipeline
        _PIPELINE = RAGPipeline()
    return _PIPELINE


def retrieve_context_direct(
    question: str,
    k: int = 5,
    min_score: float = 0.3,
) -> dict[str, Any]:
    pipeline = _get_pipeline()
    result = pipeline.retrieve(query=question, k=k)

    raw_chunks = []
    for r in result.results:
        chunk = {
            "text": r.contextualized_text,
            "source": r.metadata.get("source", ""),
            "page": r.metadata.get("page", 0),
            "score": round(r.score, 4),
            "headings": r.metadata.get("headings", ""),
        }
        if min_score is None or r.score >= min_score:
            raw_chunks.append(chunk)

    if min_score is not None and len(raw_chunks) < k and raw_chunks:
        pass

    context = _build_llm_context(raw_chunks)
    return {"context": context, "chunks": raw_chunks}


def retrieve_context(
    question: str,
    k: int = 5,
    api_url: str = "http://localhost:8000",
) -> dict[str, Any]:
    with httpx.Client(timeout=60) as client:
        body = {
            "query": question,
            "k": k,
            "format": "llm",
            "min_score": 0.3,
        }
        resp = client.post(f"{api_url}/retrieve", json=body)
        resp.raise_for_status()
        data = resp.json()

    context = data.get("context", "")
    chunks = []
    for r in data.get("results", []):
        chunks.append({
            "text": r.get("text", ""),
            "source": r.get("source", ""),
            "page": r.get("page", 0),
            "score": r.get("score", 0.0),
            "headings": r.get("headings", ""),
        })

    return {"context": context, "chunks": chunks}


def parse_sources(answer: str, chunks: list[dict]) -> list[dict]:
    used = []
    for chunk in chunks:
        source_str = chunk["source"]
        page_str = str(chunk.get("page", ""))
        citation = source_str.replace("/", " ").replace("\\", " ").strip()
        if citation.lower() in answer.lower() or page_str in answer:
            used.append(chunk)
            continue
        for token in citation.replace(".pdf", "").replace(".txt", "").split():
            if len(token) > 3 and token.lower() in answer.lower():
                used.append(chunk)
                break
    return used


def answer_question(
    question: str,
    k: int = 5,
    model: str = "llama3.2",
    provider: str = "ollama",
    api_url: str = "http://localhost:8000",
    llm_client: LLMClient | None = None,
    use_direct: bool = False,
) -> dict[str, Any]:
    t0 = time.monotonic()
    retrieve_result = retrieve_context_direct(question, k=k) if use_direct else retrieve_context(question, k=k, api_url=api_url)
    context = retrieve_result["context"]
    chunks = retrieve_result["chunks"]

    if not context.strip():
        return {
            "answer": "There is no data about this in the available documents.",
            "sources": [],
            "context": "",
            "latency": round(time.monotonic() - t0, 2),
            "model": model,
            "provider": provider,
            "chunks_retrieved": 0,
        }

    if llm_client is None:
        llm_client = LLMClient(provider=provider, model=model)

    prompt = build_rag_prompt(question, context)
    llm_result = llm_client.generate(prompt, system=SYSTEM_PROMPT, temperature=0.1, max_tokens=512)
    answer = llm_result.get("text", "").strip()

    if not answer:
        answer = "There is no data about this in the available documents."

    sources_used = parse_sources(answer, chunks)

    return {
        "answer": answer,
        "sources": sources_used,
        "all_chunks": chunks,
        "context": context,
        "latency": round(time.monotonic() - t0, 2),
        "llm_latency": llm_result.get("duration_s", 0),
        "llm_tokens": llm_result.get("tokens", 0),
        "model": model,
        "provider": provider,
        "chunks_retrieved": len(chunks),
        "thinking": llm_result.get("thinking"),
    }

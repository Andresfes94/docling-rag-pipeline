from __future__ import annotations

import logging
import re
import time
from typing import Any

from src.llm.rag import answer_question
from src.evaluation.test_set import TEST_SET

_log = logging.getLogger(__name__)

REJECTION_PHRASES = [
    "there is no data about this",
    "there is no information",
    "cannot answer",
    "no data about this",
    "not in the available documents",
    "not found in the context",
    "does not contain",
    "does not provide",
    "i don't have",
    "i cannot",
    "no information",
]


def _has_rejection_phrase(text: str) -> bool:
    lower = text.lower()
    for phrase in REJECTION_PHRASES:
        if phrase in lower:
            return True
    return False


def _keyword_coverage(text: str, keywords: list[str]) -> float:
    lower = text.lower()
    if not keywords:
        return 1.0
    found = sum(1 for kw in keywords if kw.lower() in lower)
    return found / len(keywords)


def evaluate_question(
    question: dict[str, Any],
    model: str = "llama3.2",
    provider: str = "ollama",
    api_url: str = "http://localhost:8000",
    k: int = 5,
    use_direct: bool = True,
) -> dict[str, Any]:
    t0 = time.monotonic()
    result = answer_question(
        question=question["question"],
        k=k,
        model=model,
        provider=provider,
        api_url=api_url,
        use_direct=use_direct,
    )
    elapsed = time.monotonic() - t0
    answer = result["answer"]
    rejected = _has_rejection_phrase(answer)

    expected_rejection = question.get("expected_rejection", False)
    rejection_correct = rejected == expected_rejection

    kw_coverage = _keyword_coverage(answer, question.get("expected_keywords", []))

    has_citation = (
        "source" in answer.lower()
        or "page" in answer.lower()
        or bool(re.findall(r"\[.*?\]", answer))
    )

    correct = False
    if expected_rejection:
        correct = rejected
    else:
        correct = not rejected and kw_coverage >= 0.33  # at least 1/3 of keywords

    chunk_scores = [c.get("score", 0) for c in result.get("all_chunks", [])]
    avg_chunk_score = sum(chunk_scores) / len(chunk_scores) if chunk_scores else 0.0

    return {
        "id": question["id"],
        "question": question["question"],
        "category": question.get("category", ""),
        "correct": correct,
        "rejected": rejected,
        "expected_rejection": expected_rejection,
        "rejection_correct": rejection_correct,
        "keyword_coverage": round(kw_coverage, 3),
        "has_citation": has_citation,
        "answer": answer[:500],
        "sources_used": [{"source": s.get("source", ""), "page": s.get("page", 0)} for s in result.get("sources", [])],
        "chunks_retrieved": result.get("chunks_retrieved", 0),
        "avg_chunk_score": round(avg_chunk_score, 3),
        "latency_s": round(elapsed, 2),
        "llm_latency_s": result.get("llm_latency", 0),
        "llm_tokens": result.get("llm_tokens", 0),
        "model": result.get("model", model),
    }


def evaluate_all(
    model: str = "llama3.2",
    provider: str = "ollama",
    api_url: str = "http://localhost:8000",
    k: int = 5,
    questions: list[dict[str, Any]] | None = None,
    use_direct: bool = True,
) -> dict[str, Any]:
    if questions is None:
        questions = TEST_SET

    results = []
    for q in questions:
        _log.info("Evaluating [%s] %s ...", q["id"], q["question"][:60])
        try:
            r = evaluate_question(q, model=model, provider=provider, api_url=api_url, k=k, use_direct=use_direct)
        except Exception as e:
            _log.error("Failed on [%s]: %s", q["id"], e)
            r = {
                "id": q["id"],
                "question": q["question"],
                "category": q.get("category", ""),
                "correct": False,
                "rejected": False,
                "expected_rejection": q.get("expected_rejection", False),
                "rejection_correct": False,
                "keyword_coverage": 0.0,
                "has_citation": False,
                "answer": f"ERROR: {e}",
                "sources_used": [],
                "chunks_retrieved": 0,
                "avg_chunk_score": 0.0,
                "latency_s": 0.0,
                "llm_latency_s": 0.0,
                "llm_tokens": 0,
                "model": model,
            }
        results.append(r)

    factual = [r for r in results if r["category"] == "factual"]
    synthesis = [r for r in results if r["category"] == "synthesis"]
    ooc = [r for r in results if r["category"] == "out_of_context"]
    attribution = [r for r in results if r["category"] == "attribution"]

    def avg(lst, key):
        vals = [r[key] for r in lst if r[key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    def pct(lst, key):
        vals = [r[key] for r in lst]
        return round(sum(vals) / len(vals) * 100, 1) if vals else 0.0

    metrics = {
        "model": model,
        "provider": provider,
        "k": k,
        "total_questions": len(results),
        "overall_accuracy": pct(results, "correct"),
        "factual_accuracy": pct(factual, "correct") if factual else None,
        "synthesis_accuracy": pct(synthesis, "correct") if synthesis else None,
        "out_of_context_rejection_rate": pct(ooc, "correct") if ooc else None,
        "attribution_accuracy": pct(attribution, "correct") if attribution else None,
        "avg_keyword_coverage": avg(results, "keyword_coverage"),
        "avg_latency_s": avg(results, "latency_s"),
        "avg_llm_latency_s": avg(results, "llm_latency_s"),
        "avg_tokens_per_response": round(avg(results, "llm_tokens")),
        "avg_chunk_score": avg(results, "avg_chunk_score"),
        "citation_rate": pct(results, "has_citation"),
        "total_time_s": round(sum(r["latency_s"] for r in results), 2),
        "per_question": results,
    }

    return metrics


def print_report(metrics: dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append(f"  RAG Evaluation Report — Model: {metrics['model']} (k={metrics['k']})")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Total questions:     {metrics['total_questions']}")
    lines.append(f"  Overall accuracy:    {metrics['overall_accuracy']:.1f}%")
    lines.append(f"  Factual recall:      {_fmt(metrics, 'factual_accuracy')}%")
    lines.append(f"  Synthesis:           {_fmt(metrics, 'synthesis_accuracy')}%")
    lines.append(f"  Out-of-context rej:  {_fmt(metrics, 'out_of_context_rejection_rate')}%")
    lines.append(f"  Attribution:         {_fmt(metrics, 'attribution_accuracy')}%")
    lines.append(f"  Keyword coverage:    {metrics['avg_keyword_coverage']*100:.1f}%")
    lines.append(f"  Citation rate:       {metrics['citation_rate']:.1f}%")
    lines.append(f"  Avg latency:         {metrics['avg_latency_s']:.2f}s")
    lines.append(f"  Avg LLM tokens:      {metrics['avg_tokens_per_response']}")
    lines.append(f"  Total eval time:     {metrics['total_time_s']:.1f}s")
    lines.append("")
    lines.append("─" * 60)

    categories = {}
    for r in metrics.get("per_question", []):
        cat = r.get("category", "unknown")
        categories.setdefault(cat, []).append(r)

    for cat, items in categories.items():
        lines.append(f"\n  [{cat.upper()}]")
        for r in items:
            mark = "✓" if r["correct"] else "✗"
            kw = f"kw={r['keyword_coverage']*100:.0f}%"
            lines.append(f"    {mark} {r['id']}: {r['question'][:55]:55s}  {kw}  {r['latency_s']:.1f}s")
            if not r["correct"]:
                lines.append(f"       answer: {r['answer'][:120]}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def _fmt(metrics: dict, key: str) -> str:
    v = metrics.get(key)
    if v is None:
        return "  N/A"
    return f"{v:5.1f}"




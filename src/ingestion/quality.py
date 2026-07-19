from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


@dataclass
class QualityReport:
    status: str
    metrics: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    raw_output: str = ""


def evaluate(
    json_path: str | Path,
    markdown_path: str | Path | None = None,
    expect_tables: bool = False,
    min_chars_per_page: float = 120.0,
    min_markdown_chars: int = 200,
    fail_on_warn: bool = False,
    evaluator_script: str | Path = "scripts/docling-evaluate.py",
) -> QualityReport:
    json_path = Path(json_path)
    if not json_path.is_file():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    if not Path(evaluator_script).is_file():
        _log.warning("Evaluator script not found at %s; running basic checks", evaluator_script)
        return _basic_fallback(json_path, markdown_path)

    cmd = [
        sys.executable,
        str(evaluator_script),
        str(json_path),
    ]

    if markdown_path:
        cmd.extend(["--markdown", str(markdown_path)])
    if expect_tables:
        cmd.append("--expect-tables")
    if fail_on_warn:
        cmd.append("--fail-on-warn")

    cmd.extend(["--min-chars-per-page", str(min_chars_per_page)])
    cmd.extend(["--min-markdown-chars", str(min_markdown_chars)])

    _log.info("Running quality evaluation: %s", " ".join(str(c) for c in cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return QualityReport(status="error", issues=["Evaluation timed out"])

    if result.returncode != 0 and result.returncode != 1:
        _log.warning("Evaluator exited with code %d: %s", result.returncode, result.stderr)
        return QualityReport(
            status="error",
            issues=[f"Evaluator exited with code {result.returncode}: {result.stderr}"],
            raw_output=result.stdout,
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return QualityReport(
            status="error",
            issues=["Could not parse evaluator JSON output"],
            raw_output=result.stdout,
        )

    return QualityReport(
        status=data.get("status", "error"),
        metrics=data.get("metrics", {}),
        issues=data.get("issues", []),
        recommended_actions=data.get("recommended_actions", []),
        raw_output=result.stdout,
    )


def _count_pages(data: dict) -> int:
    pages = data.get("pages") or []
    if pages:
        return len(pages)
    seen = set()
    for t in (data.get("texts") or []):
        for p in (t.get("prov") or []):
            pn = p.get("page_no") if isinstance(p, dict) else None
            if pn is not None:
                seen.add(pn)
    return max(seen) if seen else 1


def _detect_garbled(text: str) -> tuple[int, int]:
    replacement_chars = text.count("\ufffd")
    non_ascii_count = sum(1 for c in text if ord(c) > 127 and c not in "\ufffd\n\r\t")
    return replacement_chars, non_ascii_count


def _has_section_headers(texts: list[dict]) -> bool:
    for t in texts:
        label = t.get("label", "")
        if isinstance(label, str) and "SECTION_HEADER" in label:
            return True
    return False


def _find_duplicate_text(texts: list[dict]) -> str | None:
    from collections import Counter
    text_pieces = [str(t.get("text", "")).strip() for t in texts if t.get("text")]
    if not text_pieces:
        return None
    counts = Counter(text_pieces)
    most_common = counts.most_common(1)[0]
    if most_common[1] > max(2, len(text_pieces) * 0.2):
        return most_common[0][:80]
    return None


def _page_coverage(texts: list[dict], page_count: int) -> float:
    if page_count <= 1:
        return 1.0
    pages_with_text: set[int] = set()
    for t in texts:
        for p in (t.get("prov") or []):
            pn = p.get("page_no") if isinstance(p, dict) else None
            if pn is not None:
                pages_with_text.add(pn)
    return len(pages_with_text) / page_count


def _basic_fallback(
    json_path: Path,
    markdown_path: str | Path | None = None,
) -> QualityReport:
    """Production-grade quality check when the evaluator script is unavailable."""
    issues: list[str] = []
    actions: list[str] = []
    metrics: dict[str, Any] = {}

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return QualityReport(status="error", issues=[f"Cannot read JSON: {exc}"])

    texts = data.get("texts") or []
    tables = data.get("tables") or []
    pictures = data.get("pictures") or []
    page_count = _count_pages(data)

    total_chars = sum(len(str(t.get("text", ""))) for t in texts if isinstance(t, dict))
    chars_per_page = total_chars / max(page_count, 1)
    section_headers = sum(1 for t in texts if "SECTION_HEADER" in str(t.get("label", "")))
    replacement_chars, non_ascii_chars = 0, 0
    for t in texts:
        r, n = _detect_garbled(str(t.get("text", "")))
        replacement_chars += r
        non_ascii_chars += n

    metrics = {
        "page_count": page_count,
        "text_items": len(texts),
        "tables": len(tables),
        "pictures": len(pictures),
        "total_chars": total_chars,
        "chars_per_page": round(chars_per_page, 1),
        "section_headers": section_headers,
        "replacement_chars": replacement_chars,
        "non_ascii_chars": non_ascii_chars,
    }

    if total_chars < 100:
        issues.append("Very low text content")
        actions.append("Retry with OCR enabled or a different pipeline")
    elif chars_per_page < 50 and page_count > 1:
        issues.append(f"Low text density ({chars_per_page:.0f} chars/page)")
        actions.append("Document may be scanned or image-heavy; retry with OCR")

    if replacement_chars > 10:
        issues.append(f"Found {replacement_chars} Unicode replacement characters (garbled text)")
        actions.append("Check document encoding or retry with OCR")

    if not _has_section_headers(texts) and page_count >= 3:
        issues.append("No section headers found in document")
        actions.append("Document may lack structure; verify extraction quality")

    dup = _find_duplicate_text(texts)
    if dup:
        issues.append(f"Highly repetitive text detected: '{dup}...'")
        actions.append("Document may contain boilerplate; verify chunking quality")

    coverage = _page_coverage(texts, page_count)
    if coverage < 0.5 and page_count > 1:
        issues.append(f"Only {coverage:.0%} of pages have text content")
        actions.append("Some pages may be image-only; retry with OCR")

    if markdown_path:
        md = Path(markdown_path)
        if md.is_file():
            md_len = len(md.read_text(encoding="utf-8"))
            metrics["markdown_chars"] = md_len
            if md_len < 200:
                issues.append(f"Markdown too short ({md_len} chars)")
                actions.append("Retry with --pipeline vlm")

    status = "fail" if issues else "pass"
    return QualityReport(
        status=status,
        metrics=metrics,
        issues=issues,
        recommended_actions=actions,
    )


def is_pass(report: QualityReport) -> bool:
    return report.status == "pass"


def is_warn(report: QualityReport) -> bool:
    return report.status == "warn"


def is_fail(report: QualityReport) -> bool:
    return report.status in ("fail", "error")

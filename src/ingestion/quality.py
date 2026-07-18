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


def _basic_fallback(
    json_path: Path,
    markdown_path: str | Path | None = None,
) -> QualityReport:
    """Minimal quality check when the evaluator script is unavailable."""
    issues: list[str] = []
    actions: list[str] = []

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return QualityReport(status="error", issues=[f"Cannot read JSON: {exc}"])

    texts = data.get("texts") or []
    tables = data.get("tables") or []
    total_chars = sum(len(str(t.get("text", ""))) for t in texts if isinstance(t, dict))

    if total_chars < 100:
        issues.append("Very low text content")
        actions.append("Retry with OCR enabled or a different pipeline")

    if markdown_path:
        md = Path(markdown_path)
        if md.is_file():
            md_len = len(md.read_text(encoding="utf-8"))
            if md_len < 200:
                issues.append(f"Markdown too short ({md_len} chars)")
                actions.append("Retry with --pipeline vlm")

    status = "fail" if issues else "pass"
    return QualityReport(
        status=status,
        metrics={"text_items": len(texts), "tables": len(tables), "total_chars": total_chars},
        issues=issues,
        recommended_actions=actions,
    )


def is_pass(report: QualityReport) -> bool:
    return report.status == "pass"


def is_warn(report: QualityReport) -> bool:
    return report.status == "warn"


def is_fail(report: QualityReport) -> bool:
    return report.status in ("fail", "error")

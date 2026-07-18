from __future__ import annotations

import json

from src.ingestion.quality import evaluate, is_pass, is_fail


class TestQuality:
    def test_evaluate_basic(self, sample_json, sample_markdown):
        report = evaluate(
            json_path=sample_json,
            markdown_path=sample_markdown,
        )
        assert report.status in ("pass", "warn", "fail")
        assert isinstance(report.metrics, dict)
        assert isinstance(report.issues, list)

    def test_fallback_no_evaluator(self, sample_json, tmp_path):
        """Should work even without the evaluator script."""
        report = evaluate(
            json_path=sample_json,
            evaluator_script="/nonexistent/evaluate.py",
        )
        assert report.status in ("pass", "warn", "fail", "error")

    def test_missing_json_raises(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            evaluate(json_path="/nonexistent/file.json")

    def test_is_pass(self):
        from src.ingestion.quality import QualityReport
        assert is_pass(QualityReport(status="pass")) is True
        assert is_pass(QualityReport(status="fail")) is False

    def test_is_fail(self):
        from src.ingestion.quality import QualityReport
        assert is_fail(QualityReport(status="fail")) is True
        assert is_fail(QualityReport(status="error")) is True
        assert is_fail(QualityReport(status="pass")) is False

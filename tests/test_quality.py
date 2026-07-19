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

    def test_detect_garbled_text(self, tmp_path):
        from src.ingestion.quality import _detect_garbled
        r, n = _detect_garbled("hello world")
        assert r == 0 and n == 0
        r, n = _detect_garbled("hello\uFFFdworld\uFFFd")
        assert r == 2

    def test_fallback_flags_low_text(self, tmp_path):
        from src.ingestion.quality import _basic_fallback
        data = {"texts": [{"text": "hi", "label": "PARAGRAPH", "prov": [{"page_no": 1}]}]}
        jp = tmp_path / "low.json"
        jp.write_text(json.dumps(data))
        report = _basic_fallback(jp)
        assert report.status == "fail"
        assert any("Very low text content" in i for i in report.issues)

    def test_fallback_detects_garbled(self, tmp_path):
        from src.ingestion.quality import _basic_fallback
        data = {
            "texts": [{"text": "hello\uFFFdworld\uFFFdtest\uFFFd" * 5, "label": "PARAGRAPH", "prov": [{"page_no": 1}]}],
        }
        jp = tmp_path / "garbled.json"
        jp.write_text(json.dumps(data))
        report = _basic_fallback(jp)
        assert any("replacement" in i.lower() for i in report.issues)

    def test_fallback_page_coverage(self, tmp_path):
        from src.ingestion.quality import _basic_fallback
        data = {
            "pages": [{"page_no": i} for i in range(1, 11)],
            "texts": [{"text": "page1 only", "label": "PARAGRAPH", "prov": [{"page_no": 1}]} for _ in range(3)],
        }
        jp = tmp_path / "coverage.json"
        jp.write_text(json.dumps(data))
        report = _basic_fallback(jp)
        assert any("coverage" in i.lower() or "text content" in i.lower() for i in report.issues)

    def test_fallback_duplicate_detection(self, tmp_path):
        from src.ingestion.quality import _basic_fallback
        repeated = "Same boilerplate text appears over and over."
        data = {
            "texts": [
                {"text": repeated, "label": "PARAGRAPH", "prov": [{"page_no": 1}]},
                {"text": repeated, "label": "PARAGRAPH", "prov": [{"page_no": 2}]},
                {"text": repeated, "label": "PARAGRAPH", "prov": [{"page_no": 3}]},
                {"text": repeated, "label": "PARAGRAPH", "prov": [{"page_no": 4}]},
                {"text": "unique text", "label": "PARAGRAPH", "prov": [{"page_no": 5}]},
            ]
        }
        jp = tmp_path / "dup.json"
        jp.write_text(json.dumps(data))
        report = _basic_fallback(jp)
        assert any("repetitive" in i.lower() or "duplicate" in i.lower() for i in report.issues)

    def test_fallback_has_section_headers(self, tmp_path):
        from src.ingestion.quality import _basic_fallback
        body_text = "This is a long body paragraph that discusses something important. " * 20
        data = {
            "pages": [{"page_no": i} for i in range(1, 5)],
            "texts": [
                {"text": "Introduction", "label": "SECTION_HEADER", "prov": [{"page_no": 1}]},
                {"text": body_text, "label": "PARAGRAPH", "prov": [{"page_no": 1}]},
                {"text": "Conclusion", "label": "SECTION_HEADER", "prov": [{"page_no": 4}]},
            ]
        }
        jp = tmp_path / "headers.json"
        jp.write_text(json.dumps(data))
        report = _basic_fallback(jp)
        assert report.status == "pass"  # has headers, enough text

    def test_fallback_no_section_headers(self, tmp_path):
        from src.ingestion.quality import _basic_fallback
        text = "Paragraph one. " * 50
        data = {
            "pages": [{"page_no": i} for i in range(1, 5)],
            "texts": [
                {"text": text, "label": "PARAGRAPH", "prov": [{"page_no": i}]} for i in range(1, 5)
            ]
        }
        jp = tmp_path / "noheaders.json"
        jp.write_text(json.dumps(data))
        report = _basic_fallback(jp)
        assert any("section header" in i.lower() for i in report.issues) or report.status == "pass"

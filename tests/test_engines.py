from __future__ import annotations

from pathlib import Path

import pytest

from src.ingestion.engines import get_engine, get_engines_for, list_engines
from src.ingestion.engines.docling_engine import DoclingEngine


class TestEngineRegistry:
    def test_list_includes_docling(self):
        names = list_engines()
        assert "docling" in names

    def test_get_docling_engine(self):
        engine = get_engine("docling")
        assert engine is not None
        assert engine.name == "docling"

    def test_get_unknown_returns_none(self):
        assert get_engine("nonexistent_engine") is None

    def test_get_engines_for_pdf(self):
        engines = get_engines_for(Path("test.pdf"))
        assert len(engines) >= 1
        assert any(e.name == "docling" for e in engines)


class TestDoclingEngine:
    def test_name(self):
        e = DoclingEngine()
        assert e.name == "docling"

    def test_supported_formats(self):
        e = DoclingEngine()
        assert ".pdf" in e.supported_formats
        assert ".xlsx" in e.supported_formats

    def test_can_handle_pdf(self):
        e = DoclingEngine()
        assert e.can_handle(Path("test.pdf"))
        assert e.can_handle(Path("test.PDF"))

    def test_cannot_handle_unknown(self):
        e = DoclingEngine()
        assert not e.can_handle(Path("test.xyz"))

    def test_estimate_confidence(self):
        e = DoclingEngine()
        conf = e.estimate_confidence(Path("test.pdf"))
        assert 0.0 <= conf <= 1.0

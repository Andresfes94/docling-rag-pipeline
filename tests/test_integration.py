from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from src.ingestion.detector import detect
from src.retrieval.pipeline import RAGPipeline


@pytest.mark.integration
class TestIngestionIntegration:
    """End-to-end tests: ingest → chunk → embed → store → retrieve"""

    def test_ingest_pdf_creates_chunks(self, pipeline: RAGPipeline, sample_pdf_path: Path) -> None:
        result = pipeline.ingest(str(sample_pdf_path), profile="standard")

        assert result.success, f"Ingestion failed: {result.error}"
        assert result.chunking is not None
        assert result.chunking.total_chunks > 0
        assert not result.chunking.empty_document
        assert result.vector_count > 0
        assert result.conversion is not None
        assert result.conversion.page_count >= 1

    def test_ingest_xlsx_creates_chunks(self, pipeline: RAGPipeline, sample_xlsx_path: Path) -> None:
        result = pipeline.ingest(str(sample_xlsx_path), profile="standard")

        assert result.success, f"Ingestion failed: {result.error}"
        assert result.chunking is not None
        assert result.chunking.total_chunks > 0
        assert result.vector_count > 0

    def test_ingest_then_retrieve(self, pipeline: RAGPipeline, sample_pdf_path: Path) -> None:
        pipeline.ingest(str(sample_pdf_path), profile="standard")

        retrieval = pipeline.retrieve("quantitative trading", k=3)
        assert retrieval.total_results > 0
        assert any(
            "quantitative" in r.contextualized_text.lower()
            or "trading" in r.contextualized_text.lower()
            for r in retrieval.results
        )
        for r in retrieval.results:
            assert 0.0 <= r.score <= 1.0
            assert len(r.contextualized_text) > 0

    def test_auto_detect_selects_standard_profile(
        self, pipeline_no_retry: RAGPipeline, sample_pdf_path: Path
    ) -> None:
        doc_profile = detect(str(sample_pdf_path))
        assert doc_profile.suggested_profile() == "standard"
        assert not doc_profile.is_scanned
        assert doc_profile.page_count == 2

        result = pipeline_no_retry.ingest(str(sample_pdf_path), profile="auto")
        assert result.success, f"Auto-ingest failed: {result.error}"
        assert result.detector_info is not None
        assert result.detector_info["suggested_profile"] == "standard"

    def test_retry_chain_triggers_on_empty_document(
        self, pipeline: RAGPipeline
    ) -> None:
        img_pdf = Path(__file__).resolve().parent / "fixtures" / "sample_image.pdf"
        if not img_pdf.is_file():
            pytest.skip("sample_image.pdf fixture not found")

        result = pipeline.ingest(str(img_pdf), profile="standard")
        assert len(result.retry_chain) > 1, (
            f"Retry chain should have attempted fallbacks, got: {result.retry_chain}"
        )
        assert result.retry_chain[0] == "standard"

    def test_ingest_with_quality_check(self, pipeline: RAGPipeline, sample_pdf_path: Path) -> None:
        result = pipeline.ingest(str(sample_pdf_path), profile="standard", skip_quality=False)
        assert result.success
        assert result.quality is not None
        assert result.quality.status in ("pass", "warn")

    def test_delete_removes_chunks(self, pipeline: RAGPipeline, sample_pdf_path: Path) -> None:
        ingest_result = pipeline.ingest(str(sample_pdf_path), profile="standard")
        assert ingest_result.success

        count_before = pipeline.store.document_count()
        assert count_before > 0

        removed = pipeline.delete_source(str(sample_pdf_path))
        assert removed > 0

        count_after = pipeline.store.document_count()
        assert count_after < count_before

        retrieval = pipeline.retrieve("quantitative", k=5)
        assert retrieval.total_results == 0

    def test_multiple_ingests_isolation(
        self, tmp_path: Path, sample_pdf_path: Path, sample_xlsx_path: Path
    ) -> None:
        chroma1 = tmp_path / "chroma1"
        chroma2 = tmp_path / "chroma2"
        p1 = RAGPipeline(persist_directory=str(chroma1), output_dir=str(tmp_path / "out1"))
        p2 = RAGPipeline(persist_directory=str(chroma2), output_dir=str(tmp_path / "out2"))

        r1 = p1.ingest(str(sample_pdf_path), profile="standard")
        r2 = p2.ingest(str(sample_xlsx_path), profile="standard")

        assert r1.success and r2.success
        assert p1.store.document_count() > 0
        assert p2.store.document_count() > 0

        pdf_retrieval = p1.retrieve("quantitative", k=1)
        xlsx_retrieval = p2.retrieve("AAPL", k=1)
        assert pdf_retrieval.total_results > 0 or xlsx_retrieval.total_results > 0

    def test_reingest_idempotent_no_duplicates(
        self, pipeline: RAGPipeline, sample_pdf_path: Path
    ) -> None:
        r1 = pipeline.ingest(str(sample_pdf_path), profile="standard")
        assert r1.success
        count_after_first = pipeline.store.document_count()

        r2 = pipeline.ingest(str(sample_pdf_path), profile="standard")
        assert r2.success
        count_after_second = pipeline.store.document_count()

        assert count_after_second == count_after_first, (
            f"Re-ingest should not add duplicates: {count_after_first} vs {count_after_second}"
        )

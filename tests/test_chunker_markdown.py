from __future__ import annotations

from src.ingestion.chunker import chunk_markdown


class TestChunkMarkdown:
    def test_empty_text(self):
        result = chunk_markdown("")
        assert result.total_chunks == 0
        assert result.empty_document

    def test_simple_text(self):
        result = chunk_markdown("Hello world")
        assert result.total_chunks >= 1

    def test_with_heading(self):
        md = "# Introduction\nThis is the intro paragraph.\n\n# Methods\nThis is the methods section."
        result = chunk_markdown(md)
        assert result.total_chunks >= 2
        headings = [c.headings for c in result.chunks if c.headings]
        assert any("Introduction" in h for h in headings)

    def test_chunks_have_source(self):
        result = chunk_markdown("Some text", source="test.pdf")
        for c in result.chunks:
            assert c.source == "test.pdf"

    def test_chunks_have_context(self):
        result = chunk_markdown("# Title\nBody text")
        for c in result.chunks:
            assert c.contextualized_text

    def test_long_text_split(self):
        long_text = "word " * 5000
        result = chunk_markdown(long_text, max_chars=500)
        assert result.total_chunks > 1

from __future__ import annotations

from src.ingestion.quality_scorer import extract_pages_from_markdown, score_document, score_page


class TestScorePage:
    def test_empty_text_returns_zero(self):
        assert score_page("") == 0.0
        assert score_page("   ") == 0.0

    def test_normal_text_high_score(self):
        text = "This is a normal paragraph of text with reasonable length and no garbage characters. " * 8
        score = score_page(text)
        assert score > 0.5

    def test_garbage_unicode_penalty(self):
        text = "Normal text. " + "\ufffd" * 50 + " more text."
        score = score_page(text)
        assert score < 0.8

    def test_control_chars_penalty(self):
        text = "Normal text.\x00\x01\x02\x03 more text."
        score = score_page(text)
        assert score < 0.9

    def test_very_short_text(self):
        text = "Hi"
        score = score_page(text)
        assert score < 0.5


class TestScoreDocument:
    def test_empty(self):
        assert score_document([]) == []

    def test_single_page(self):
        text = "Normal paragraph of text with enough words to get a reasonable density score. " * 10
        scores = score_document([{"text": text}])
        assert len(scores) == 1
        assert scores[0] > 0

    def test_mixed_pages(self):
        good = "Normal clean text with sensible words and reasonable length. " * 20
        bad = "\ufffd" * 100
        pages = [{"text": good}, {"text": bad}]
        scores = score_document(pages)
        assert len(scores) == 2
        assert scores[0] > scores[1], f"good={scores[0]} should exceed bad={scores[1]}"


class TestExtractPagesFromMarkdown:
    def test_single_chunk(self):
        pages = extract_pages_from_markdown("Just a plain text.")
        assert len(pages) >= 1
        assert "text" in pages[0]

    def test_multiple_sections(self):
        md = "# Header 1\nContent 1\n\n# Header 2\nContent 2"
        pages = extract_pages_from_markdown(md)
        assert len(pages) >= 2

    def test_empty(self):
        assert extract_pages_from_markdown("") == []

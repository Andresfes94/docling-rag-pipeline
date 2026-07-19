from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.ingestion.cleaner import TextCleaner


@dataclass
class FakeChunk:
    text: str
    contextualized_text: str
    chunk_index: int = 0


class TestTextCleaner:
    def test_clean_text_strips_whitespace(self):
        c = TextCleaner()
        assert c.clean_text("  hello world  ") == "hello world"

    def test_clean_text_normalizes_newlines(self):
        c = TextCleaner()
        assert c.clean_text("a\n\n\n\nb") == "a\n\nb"

    def test_clean_text_collapses_spaces(self):
        c = TextCleaner()
        assert c.clean_text("a    b   c") == "a b c"

    def test_clean_text_strips_control_chars(self):
        c = TextCleaner()
        result = c.clean_text("hello\x00world\x1f")
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_clean_text_strips_pii_email(self):
        c = TextCleaner(strip_pii=True)
        result = c.clean_text("contact me at user@example.com")
        assert "[EMAIL]" in result
        assert "user@example.com" not in result

    def test_clean_text_strips_pii_url(self):
        c = TextCleaner(strip_pii=True)
        result = c.clean_text("see https://example.com/doc.pdf")
        assert "[URL]" in result
        assert "https://example.com" not in result

    def test_clean_text_strips_pii_phone(self):
        c = TextCleaner(strip_pii=True)
        result = c.clean_text("call +1-555-123-4567")
        assert "[PHONE]" in result

    def test_clean_text_no_pii_flag(self):
        c = TextCleaner(strip_pii=False)
        result = c.clean_text("email user@example.com")
        assert "[EMAIL]" not in result
        assert "user@example.com" in result

    def test_deduplicate_removes_duplicates(self):
        c = TextCleaner()
        chunks = [
            FakeChunk(text="hello", contextualized_text="hello"),
            FakeChunk(text="world", contextualized_text="world"),
            FakeChunk(text="hello", contextualized_text="hello"),
        ]
        result = c.deduplicate(chunks)
        assert len(result) == 2
        assert result[0].text == "hello"
        assert result[1].text == "world"

    def test_deduplicate_no_duplicates(self):
        c = TextCleaner()
        chunks = [
            FakeChunk(text="a", contextualized_text="a"),
            FakeChunk(text="b", contextualized_text="b"),
        ]
        result = c.deduplicate(chunks)
        assert len(result) == 2

    def test_filter_by_length_removes_short(self):
        c = TextCleaner(min_chunk_chars=10)
        chunks = [
            FakeChunk(text="short", contextualized_text="short"),
            FakeChunk(text="long enough text here", contextualized_text="long enough text here"),
        ]
        result = c.filter_by_length(chunks)
        assert len(result) == 1
        assert result[0].text == "long enough text here"

    def test_filter_by_length_removes_long(self):
        c = TextCleaner(min_chunk_chars=1, max_chunk_chars=20)
        chunks = [
            FakeChunk(text="short", contextualized_text="short"),
            FakeChunk(text="x" * 30, contextualized_text="x" * 30),
        ]
        result = c.filter_by_length(chunks)
        assert len(result) == 1
        assert result[0].text == "short"

    def test_process_chunks_full_pipeline(self):
        c = TextCleaner(min_chunk_chars=1)
        chunks = [
            FakeChunk(text="  HELLO   WORLD  ", contextualized_text="  HELLO   WORLD  "),
            FakeChunk(text="  DUP   TEXT  ", contextualized_text="  DUP   TEXT  "),
            FakeChunk(text="  DUP   TEXT  ", contextualized_text="  DUP   TEXT  "),
        ]
        result = c.process_chunks(chunks)
        assert len(result) == 2
        assert result[0].text == "HELLO WORLD"
        assert result[1].text == "DUP TEXT"
        assert result[0].chunk_index == 0
        assert result[1].chunk_index == 1

    def test_process_chunks_empty_text_removed(self):
        c = TextCleaner(min_chunk_chars=10)
        chunks = [FakeChunk(text="short", contextualized_text="short")]
        result = c.process_chunks(chunks)
        assert len(result) == 0

    def test_unicode_replacement_handling(self):
        c = TextCleaner()
        result = c.clean_text("hello\ufffdworld")
        assert "\ufffd" in result

    def test_cleaner_disabled(self):
        c = TextCleaner(fix_unicode=False, normalize_whitespace=False, strip_pii=False, dedup_by_hash=False, min_chunk_chars=1)
        chunks = [FakeChunk(text="raw text", contextualized_text="raw text")]
        result = c.process_chunks(chunks)
        assert len(result) == 1
        assert result[0].text == "raw text"

    def test_chunk_hash_uses_contextualized_text(self):
        c = TextCleaner()
        a = FakeChunk(text="a", contextualized_text="ctx_a")
        b = FakeChunk(text="a", contextualized_text="ctx_b")
        assert c.chunk_hash(a) != c.chunk_hash(b)

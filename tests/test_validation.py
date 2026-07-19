from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.api.validation import validate_source


class TestValidateSource:
    def test_empty_source(self):
        err = validate_source("")
        assert err is not None
        assert "empty" in err.lower()

    def test_whitespace_source(self):
        err = validate_source("   ")
        assert err is not None

    def test_none_source(self):
        err = validate_source("")
        assert err is not None

    def test_valid_local_pdf(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4")
            path = f.name
        try:
            err = validate_source(path)
            assert err is None
        finally:
            os.unlink(path)

    def test_local_file_not_found(self):
        err = validate_source("/nonexistent/path/document.pdf")
        assert err is not None
        assert "not found" in err.lower()

    def test_valid_local_xlsx(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        try:
            err = validate_source(path)
            assert err is None
        finally:
            os.unlink(path)

    def test_unsupported_extension(self):
        err = validate_source("document.txt")
        assert err is not None
        assert "unsupported" in err.lower()
        assert ".txt" in err

    def test_unsupported_extension_url(self):
        err = validate_source("https://example.com/document.txt")
        assert err is not None
        assert "unsupported" in err.lower()

    def test_valid_url(self):
        err = validate_source("https://arxiv.org/pdf/2408.09869.pdf")
        assert err is None

    def test_valid_url_no_ext(self):
        err = validate_source("https://example.com/document")
        assert err is None

    def test_supported_extensions_listed(self):
        err = validate_source("document.txt")
        assert ".pdf" in err
        assert ".xlsx" in err

    def test_url_missing_hostname(self):
        err = validate_source("http:///path/to/file.pdf")
        assert err is not None
        assert "missing hostname" in err.lower() or "invalid" in err.lower()

    def test_local_png(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"PNG")
            path = f.name
        try:
            err = validate_source(path)
            assert err is None
        finally:
            os.unlink(path)

    def test_local_jpg(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            path = f.name
        try:
            err = validate_source(path)
            assert err is None
        finally:
            os.unlink(path)

    def test_local_jpeg(self):
        with tempfile.NamedTemporaryFile(suffix=".jpeg", delete=False) as f:
            path = f.name
        try:
            err = validate_source(path)
            assert err is None
        finally:
            os.unlink(path)

    def test_local_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            err = validate_source(path)
            assert err is None
        finally:
            os.unlink(path)

    def test_local_html(self):
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            path = f.name
        try:
            err = validate_source(path)
            assert err is None
        finally:
            os.unlink(path)

    def test_local_docx(self):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            path = f.name
        try:
            err = validate_source(path)
            assert err is None
        finally:
            os.unlink(path)

    def test_local_pptx(self):
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            path = f.name
        try:
            err = validate_source(path)
            assert err is None
        finally:
            os.unlink(path)


class TestValidateSourceIntegration:
    @pytest.mark.slow
    async def test_url_reachable_check(self):
        err = validate_source("https://arxiv.org/pdf/2408.09869.pdf", check_reachable=True)
        assert err is None

    @pytest.mark.slow
    async def test_url_unreachable(self):
        err = validate_source("https://nonexistent.example.com/file.pdf", check_reachable=True)
        assert err is not None
        assert "not reachable" in err.lower() or "http" in err.lower()

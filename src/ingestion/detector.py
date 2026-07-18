from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


class DocumentProfile:
    def __init__(
        self,
        source: str | Path,
        page_count: int = 0,
        file_size_bytes: int = 0,
        has_selectable_text: bool = False,
        extension: str = "",
    ):
        self.source = str(source)
        self.page_count = page_count
        self.file_size_bytes = file_size_bytes
        self.has_selectable_text = has_selectable_text
        self.extension = extension

    @property
    def is_scanned(self) -> bool:
        return not self.has_selectable_text and self.extension.lower() == ".pdf"

    @property
    def is_large(self) -> bool:
        return self.page_count > 150 or self.file_size_bytes > 10_000_000

    @property
    def is_born_digital(self) -> bool:
        return self.has_selectable_text

    @property
    def kb_per_page(self) -> float:
        if self.page_count > 0:
            return self.file_size_bytes / 1024 / self.page_count
        return 0.0

    def suggested_profile(self) -> str:
        if self.is_scanned:
            if self.is_large:
                return "ocrmac" if _is_macos() else "ocr_easyocr"
            return "ocrmac" if _is_macos() else "ocr_easyocr"
        if self.is_large:
            return "large_document"
        return "standard"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "page_count": self.page_count,
            "file_size_bytes": self.file_size_bytes,
            "has_selectable_text": self.has_selectable_text,
            "extension": self.extension,
            "is_scanned": self.is_scanned,
            "is_large": self.is_large,
            "kb_per_page": round(self.kb_per_page, 1),
            "suggested_profile": self.suggested_profile(),
        }


def _is_macos() -> bool:
    import sys
    return sys.platform == "darwin"


def _quick_pdf_check(path: Path) -> tuple[int, bool]:
    """Quickly determine page count and if a PDF has selectable text.
    
    Uses PyPDF2/pdfminer for a fast check without full Docling conversion.
    """
    try:
        import PyPDF2
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            n_pages = len(reader.pages)
            has_text = False
            for i in range(min(n_pages, 5)):
                page = reader.pages[i]
                text = page.extract_text() or ""
                if len(text.strip()) > 50:
                    has_text = True
                    break
            return n_pages, has_text
    except Exception:
        pass

    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            n_pages = len(pdf.pages)
            has_text = False
            for i in range(min(n_pages, 5)):
                text = pdf.pages[i].extract_text() or ""
                if len(text.strip()) > 50:
                    has_text = True
                    break
            return n_pages, has_text
    except Exception:
        pass

    return 0, False


def detect(source: str | Path) -> DocumentProfile:
    path = Path(source)
    ext = path.suffix.lower()

    profile = DocumentProfile(
        source=source,
        file_size_bytes=path.stat().st_size if path.is_file() else 0,
        extension=ext,
    )

    if ext == ".pdf" and path.is_file():
        n_pages, has_text = _quick_pdf_check(path)
        profile.page_count = n_pages
        profile.has_selectable_text = has_text
        _log.info(
            "Detected: %d pages, selectable_text=%s, kb/pg=%.1f → %s",
            n_pages, has_text, profile.kb_per_page, profile.suggested_profile(),
        )
    else:
        profile.has_selectable_text = True
        _log.info("Non-PDF source, assuming born-digital")

    return profile

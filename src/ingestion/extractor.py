from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.document import TextItem, TableItem, PictureItem


@dataclass
class ExtractedText:
    text: str
    label: str
    page: int | None
    headings: list[str] = field(default_factory=list)
    parent_id: str | None = None


@dataclass
class ExtractedTable:
    index: int
    page: int | None
    markdown: str
    caption: str | None = None


@dataclass
class ExtractedPicture:
    index: int
    page: int | None
    caption: str | None = None


@dataclass
class ExtractedDocument:
    source: str
    page_count: int
    texts: list[ExtractedText] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    pictures: list[ExtractedPicture] = field(default_factory=list)
    body_texts: list[ExtractedText] = field(default_factory=list)
    furniture_texts: list[ExtractedText] = field(default_factory=list)
    heading_tree: list[dict] = field(default_factory=list)
    total_text_items_in_doc: int = 0
    empty_text_items: int = 0
    has_text_content: bool = False


def _get_page(item: Any) -> int | None:
    provs = getattr(item, "prov", None) or []
    for prov in provs:
        p = getattr(prov, "page_no", None)
        if p is not None:
            return int(p)
    return None


def _build_heading_breadcrumbs(doc: DoclingDocument) -> dict[str, list[str]]:
    crumbs: dict[str, list[str]] = {}
    stack: list[str] = []

    for item, level in doc.iterate_items():
        label = getattr(getattr(item, "label", None), "name", None) or ""
        item_id = getattr(item, "item_id", None) or getattr(item, "self_ref", None)
        if not item_id:
            continue

        if label == "SECTION_HEADER":
            text = getattr(item, "text", "") or ""
            while len(stack) > level:
                stack.pop()
            if len(stack) <= level:
                stack.append(text)
            else:
                stack[level] = text
            crumbs[str(item_id)] = stack.copy()
        else:
            crumbs[str(item_id)] = stack.copy()

    return crumbs


def extract(doc: DoclingDocument, source: str = "", deep: bool = False) -> ExtractedDocument:
    result = ExtractedDocument(source=source, page_count=0)

    try:
        pages = set()
        for item, _ in doc.iterate_items():
            p = _get_page(item)
            if p is not None:
                pages.add(p)
        result.page_count = len(pages)
    except Exception:
        pass

    result.total_text_items_in_doc = len(doc.texts)

    breadcrumbs = _build_heading_breadcrumbs(doc)

    for item, level in doc.iterate_items():
        label = getattr(getattr(item, "label", None), "name", None) or ""
        text = getattr(item, "text", None)

        item_id = getattr(item, "item_id", None) or getattr(item, "self_ref", None)

        if not text:
            result.empty_text_items += 1
            continue

        ext = ExtractedText(
            text=str(text),
            label=label,
            page=_get_page(item),
            headings=breadcrumbs.get(str(item_id), []),
            parent_id=str(item_id) if item_id else None,
        )
        result.texts.append(ext)

    result.has_text_content = len(result.texts) > 0

    for i, table in enumerate(doc.tables or []):
        caption = getattr(table, "caption_text", None)
        if callable(caption):
            caption_text = caption(doc)
        else:
            caption_text = None

        result.tables.append(ExtractedTable(
            index=i,
            page=_get_page(table),
            markdown=table.export_to_markdown(doc=doc),
            caption=str(caption_text) if caption_text else None,
        ))

    for i, pic in enumerate(doc.pictures or []):
        caption = getattr(pic, "caption_text", None)
        if callable(caption):
            caption_text = caption(doc)
        else:
            caption_text = None

        result.pictures.append(ExtractedPicture(
            index=i,
            page=_get_page(pic),
            caption=str(caption_text) if caption_text else None,
        ))

    _enrich_tables_with_pdfplumber(result, source)

    if deep:
        _enrich_tables_with_camelot(result, source)
        _enrich_with_unstructured(result, source)

    return result


def _table_to_markdown(table: list[list[str | None]]) -> str:
    if not table or not table[0]:
        return ""
    ncols = max(len(r) for r in table)
    rows = []
    for ri, row in enumerate(table):
        cells = [str(c).replace("\n", " ") if c else "" for c in row]
        while len(cells) < ncols:
            cells.append("")
        rows.append("| " + " | ".join(cells) + " |")
        if ri == 0:
            rows.append("| " + " | ".join(["---"] * ncols) + " |")
    return "\n".join(rows)


def _is_suspicious_table(t: ExtractedTable) -> bool:
    md = t.markdown.strip()
    if not md:
        return True
    lines = md.split("\n")
    if len(lines) < 3:
        return True
    data_lines = [l for l in lines[2:] if l.strip().strip("|- ")]
    if not data_lines:
        return True
    return False


def _enrich_tables_with_pdfplumber(result: ExtractedDocument, source: str) -> None:
    path = Path(source)
    if not path.exists() or path.suffix.lower() != ".pdf":
        return
    try:
        import pdfplumber
    except ImportError:
        return

    suspicious_pages = set()
    for t in result.tables:
        if _is_suspicious_table(t):
            suspicious_pages.add(t.page)

    if not suspicious_pages:
        return

    with pdfplumber.open(str(path)) as pdf:
        for page_no in sorted(suspicious_pages):
            if page_no is None or page_no < 1 or page_no > len(pdf.pages):
                continue
            pdf_tables = pdf.pages[page_no - 1].extract_tables()
            if not pdf_tables:
                continue
            replacements = [_table_to_markdown(tbl) for tbl in pdf_tables]
            replacements = [r for r in replacements if r]
            if not replacements:
                continue
            rt_idx = 0
            for t in result.tables:
                if t.page == page_no and _is_suspicious_table(t) and rt_idx < len(replacements):
                    t.markdown = replacements[rt_idx]
                    rt_idx += 1
            while rt_idx < len(replacements):
                result.tables.append(ExtractedTable(
                    index=len(result.tables),
                    page=page_no,
                    markdown=replacements[rt_idx],
                    caption=None,
                ))
                rt_idx += 1


def _enrich_tables_with_camelot(result: ExtractedDocument, source: str) -> None:
    path = Path(source)
    if not path.exists() or path.suffix.lower() != ".pdf":
        return
    try:
        import camelot
    except ImportError:
        return

    for t in result.tables:
        if not _is_suspicious_table(t):
            continue
        if t.page is None or t.page < 1:
            continue
        try:
            tables = camelot.read_pdf(str(path), pages=str(t.page), flavor="lattice")
            if not tables:
                tables = camelot.read_pdf(str(path), pages=str(t.page), flavor="stream")
            if tables:
                md = tables[0].df.to_markdown(index=False)
                if md:
                    t.markdown = md
        except Exception:
            pass


def _enrich_with_unstructured(result: ExtractedDocument, source: str) -> None:
    path = Path(source)
    if not path.exists() or path.suffix.lower() != ".pdf":
        return
    try:
        from unstructured.partition.pdf import partition_pdf
    except ImportError:
        return

    t0 = time.time()
    try:
        elements = partition_pdf(str(path), strategy="fast", include_page_breaks=True)
    except Exception:
        return

    for el in elements:
        cat = getattr(el, "category", None)
        if cat == "Formula":
            page = getattr(el.metadata, "page_number", None)
            text = el.text.strip() if hasattr(el, "text") and el.text else ""
            if not text or page is None:
                continue
            for tx in result.texts:
                if tx.page == page and "formula" in tx.label.lower() and not tx.text.strip():
                    tx.text = text
                    break


def text_by_label(result: ExtractedDocument, label: str) -> list[ExtractedText]:
    return [t for t in result.texts if t.label == label]


def text_by_page(result: ExtractedDocument, page: int) -> list[ExtractedText]:
    return [t for t in result.texts if t.page == page]


def full_text(result: ExtractedDocument, include_furniture: bool = False) -> str:
    texts = result.texts if include_furniture else result.body_texts
    return "\n\n".join(t.text for t in texts if t.text.strip())

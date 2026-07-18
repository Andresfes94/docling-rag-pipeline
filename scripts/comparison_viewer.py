#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import time
import warnings
from pathlib import Path
from typing import Any

import streamlit as st

# Suppress noisy third-party warnings
warnings.filterwarnings("ignore", message="page-.*is image-based")
warnings.filterwarnings("ignore", message="No tables found")
warnings.filterwarnings("ignore", message="No features in text")
logging.getLogger("camelot").setLevel(logging.ERROR)
logging.getLogger("unstructured").setLevel(logging.ERROR)

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "output"

# ─── Caches (per-page) ─────────────────────────────────────────
_docling_cache: dict[str, Any] = {}
_pdfplumber_cache: dict[str, Any] = {}
_camelot_cache: dict[str, Any] = {}
_unstructured_cache: dict[str, Any] = {}

LABEL_COLORS: dict[str, str] = {
    "paragraph": "default", "text": "default",
    "section_header": "blue", "list_item": "green", "caption": "orange",
    "page_header": "purple", "page_footer": "purple", "footnote": "gray",
    "table": "red", "formula": "teal", "code": "brown",
    "title": "blue", "NarrativeText": "default", "Header": "purple",
    "Footer": "purple", "Title": "blue", "FigureCaption": "orange",
    "Formula": "teal", "UncategorizedText": "gray",
    "Table": "red", "Picture": "green",
}


def fmt_label(label: str) -> str:
    c = LABEL_COLORS.get(label, "default")
    return f":{c}[**{label}**]" if c != "default" else f"**{label}**"


def render_grid(grid: list[list[str]]) -> str:
    if not grid:
        return "_empty_"
    html = '<table style="border-collapse:collapse;width:100%;font-size:0.8em;margin:2px 0;">'
    for ri, row in enumerate(grid):
        html += "<tr>"
        for cell in row:
            tag = "th" if ri == 0 else "td"
            s = "border:1px solid #ccc;padding:3px;text-align:left;vertical-align:top;"
            if ri == 0:
                s += "background:#f0f0f0;font-weight:bold;"
            html += f"<{tag} style='{s}'>{cell}</{tag}>"
        html += "</tr>"
    html += "</table>"
    return html


def get_docling_json(pdf_path: Path) -> Path | None:
    stem = pdf_path.stem
    for f in sorted(OUTPUT_DIR.iterdir()):
        if f.suffix == ".json" and stem[:20].lower() in f.stem.lower():
            return f
    return None


def render_page(pdf_path: Path, page_no: int) -> bytes | None:
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        page = doc[page_no - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = pix.tobytes("png")
        doc.close()
        return img
    except Exception:
        return None


# ─── Accuracy helpers ──────────────────────────────────────────


def _table_col_consistency(grid: list[list[str]]) -> float:
    """Score 0-100: how consistent are column counts across rows."""
    if len(grid) < 2:
        return 0.0
    col_counts = [len(r) for r in grid]
    mean_cols = sum(col_counts) / len(col_counts)
    if mean_cols == 0:
        return 0.0
    deviations = sum(abs(c - mean_cols) for c in col_counts) / len(col_counts)
    ratio = max(0.0, 1.0 - deviations / mean_cols)
    return round(ratio * 100, 1)


def _cell_fill_rate(grid: list[list[str]]) -> float:
    """Score 0-100: fraction of cells that are non-empty."""
    total = sum(len(r) for r in grid)
    filled = sum(1 for r in grid for c in r if c.strip())
    if total == 0:
        return 0.0
    return round(filled / total * 100, 1)


def _table_quality(grid: list[list[str]]) -> float:
    """Overall table quality 0-100: mix of consistency and fill rate."""
    if len(grid) < 2:
        return 0.0
    c = _table_col_consistency(grid)
    f = _cell_fill_rate(grid)
    return round(c * 0.6 + f * 0.4, 1)


# ─── Docling ───────────────────────────────────────────────────


def extract_docling(pdf_path: Path, page_no: int) -> dict[str, Any]:
    key = f"{pdf_path}:{page_no}"
    if key in _docling_cache:
        return _docling_cache[key]

    t0 = time.monotonic()
    jf = get_docling_json(pdf_path)
    if jf is None:
        return {"timing": 0, "texts": [], "tables": [], "pictures": [], "accuracy": 0}

    with open(jf) as f:
        data = json.load(f)

    page_info = data.get("pages", {}).get(str(page_no), {})
    page_height = page_info.get("size", {}).get("height", 842)

    texts = []
    for t in data.get("texts", []):
        prov = t.get("prov", [])
        if not prov or prov[0].get("page_no") != page_no:
            continue
        texts.append({"label": t.get("label", "unknown"), "text": t.get("text", "")})

    tables = []
    for tbl in data.get("tables", []):
        prov = tbl.get("prov", [])
        if not prov or prov[0].get("page_no") != page_no:
            continue
        cells = tbl.get("data", {}).get("table_cells", [])
        nr = tbl.get("data", {}).get("num_rows", 0)
        nc = tbl.get("data", {}).get("num_cols", 0)
        grid = [["" for _ in range(nc)] for _ in range(nr)]
        for c in cells:
            r = c.get("start_row_offset_idx", 0)
            col = c.get("start_col_offset_idx", 0)
            if r < nr and col < nc:
                grid[r][col] = c.get("text", "")
        if nr > 1:
            tables.append({"grid": grid, "label": tbl.get("label", "table")})

    pictures = []
    for pic in data.get("pictures", []):
        prov = pic.get("prov", [])
        if not prov or prov[0].get("page_no") != page_no:
            continue
        pictures.append({"prov": prov[0], "label": pic.get("label", "picture"), "page_height": page_height})

    elapsed = time.monotonic() - t0

    # accuracy: mix of table quality and text coverage
    table_scores = [_table_quality(t["grid"]) for t in tables] if tables else [0]
    avg_table = sum(table_scores) / len(table_scores)
    has_text = 50.0 if len(texts) > 0 else 0.0
    overall = round(avg_table * 0.6 + has_text * 0.4, 1)

    result = {
        "timing": round(elapsed, 3),
        "texts": texts, "tables": tables, "pictures": pictures,
        "accuracy": overall,
        "raw_counts": {"texts": len(texts), "tables": len(tables), "pictures": len(pictures)},
    }
    _docling_cache[key] = result
    return result


# ─── pdfplumber ────────────────────────────────────────────────


def extract_pdfplumber(pdf_path: Path, page_no: int) -> dict[str, Any]:
    key = f"{pdf_path}:{page_no}"
    if key in _pdfplumber_cache:
        return _pdfplumber_cache[key]

    t0 = time.monotonic()
    error = None
    text = ""
    tables = []
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            if page_no < 1 or page_no > len(pdf.pages):
                error = "Page out of range"
            else:
                page = pdf.pages[page_no - 1]
                text = page.extract_text() or ""
                raw = page.extract_tables() or []
                for tbl in raw:
                    grid = [[c or "" for c in row] for row in tbl]
                    if len(grid) > 1 and any(c.strip() for row in grid[1:] for c in row):
                        tables.append(grid)
    except ImportError:
        error = "pdfplumber not installed"
    except Exception as e:
        error = str(e)

    elapsed = time.monotonic() - t0

    # accuracy: mix of table quality and text presence
    table_scores = [_table_quality(t) for t in tables] if tables else [0]
    avg_table = sum(table_scores) / len(table_scores)
    text_score = min(100.0, len(text) / 5.0) if text else 0.0
    overall = round(avg_table * 0.5 + text_score * 0.5, 1)

    result = {
        "timing": round(elapsed, 3),
        "text": text, "tables": tables,
        "accuracy": overall,
        "error": error,
        "raw_counts": {"chars": len(text), "tables": len(tables), "images": 0},
    }
    _pdfplumber_cache[key] = result
    return result


# ─── Camelot ───────────────────────────────────────────────────


def extract_camelot(pdf_path: Path, page_no: int) -> dict[str, Any]:
    key = f"{pdf_path}:{page_no}"
    if key in _camelot_cache:
        return _camelot_cache[key]

    t0 = time.monotonic()
    tables = []
    errors = []
    try:
        import camelot
        for flavor in ("lattice", "stream"):
            try:
                t1 = time.monotonic()
                parsed = camelot.read_pdf(str(pdf_path), pages=str(page_no), flavor=flavor)
                flavor_time = time.monotonic() - t1
                for t in parsed:
                    df = t.df
                    grid = [[str(c) for c in row] for row in df.values.tolist()]
                    if len(grid) < 2:
                        continue
                    if not any(c.strip() for row in grid[1:] for c in row):
                        continue
                    # Filter false positive: single-cell table containing long prose
                    if len(grid) == 2 and len(grid[1]) == 1 and len(grid[1][0]) > 300:
                        continue
                    tables.append({
                        "flavor": flavor,
                        "grid": grid,
                        "accuracy": round(t.parsing_report.get("accuracy", 0), 1),
                        "time": round(flavor_time, 3),
                    })
            except Exception as e:
                errors.append(f"{flavor}: {e}")
    except ImportError:
        errors.append("camelot-py not installed")

    elapsed = time.monotonic() - t0

    # accuracy: Camelot gives us its own parsing report accuracy
    accuracies = [t["accuracy"] for t in tables if t.get("accuracy") is not None]
    overall = round(sum(accuracies) / len(accuracies), 1) if accuracies else 0.0

    result = {
        "timing": round(elapsed, 3),
        "tables": tables,
        "accuracy": overall,
        "errors": errors,
        "raw_counts": {"tables": len(tables)},
    }
    _camelot_cache[key] = result
    return result


# ─── Unstructured ──────────────────────────────────────────────


def extract_unstructured(pdf_path: Path, page_no: int) -> dict[str, Any]:
    key = f"{pdf_path}:{page_no}"
    if key in _unstructured_cache:
        return _unstructured_cache[key]

    t0 = time.monotonic()
    items = []
    error = None
    try:
        from unstructured.partition.pdf import partition_pdf
        elements = partition_pdf(str(pdf_path), strategy="fast", include_page_breaks=True)
        for el in elements:
            cat = getattr(el, "category", "Uncategorized")
            if getattr(el.metadata, "page_number", None) != page_no:
                continue
            text = (el.text or "").strip() if hasattr(el, "text") else ""
            if not text:
                continue
            html = getattr(el.metadata, "text_as_html", None)
            items.append({"category": cat, "text": text, "html": html})
    except ImportError:
        error = "unstructured not installed"
    except Exception as e:
        error = str(e)

    elapsed = time.monotonic() - t0

    # accuracy: element classification diversity + text coverage
    cats = set(i["category"] for i in items)
    diversity = min(100.0, len(cats) * 15.0)  # up to 6-7 categories = 100
    text_len = sum(len(i["text"]) for i in items)
    text_coverage = min(100.0, text_len / 5.0)
    overall = round(diversity * 0.4 + text_coverage * 0.6, 1)

    result = {
        "timing": round(elapsed, 3),
        "items": items,
        "accuracy": overall,
        "error": error,
        "raw_counts": {"elements": len(items), "categories": len(cats)},
    }
    _unstructured_cache[key] = result
    return result


# ─── Display helpers ───────────────────────────────────────────


def _accuracy_bar(score: float) -> str:
    if score >= 80:
        return f":green[**{score}**] ✅"
    if score >= 50:
        return f":orange[**{score}**] ⚠️"
    return f":red[**{score}**] ❌"


def _timing_str(sec: float) -> str:
    if sec < 0.01:
        return f"{sec*1000:.1f}ms"
    if sec < 1:
        return f"{sec*1000:.0f}ms"
    return f"{sec:.2f}s"


def _crop_from_pdf(pdf_path: Path, page_no: int, bbox: dict, page_h: float) -> bytes:
    import fitz
    doc = fitz.open(str(pdf_path))
    page = doc[page_no - 1]
    l, r, t, b = bbox["l"], bbox["r"], bbox["t"], bbox["b"]
    y0 = page_h - t
    y1 = page_h - b
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect(l, y0, r, y1))
    img = pix.tobytes("png")
    doc.close()
    return img


# ─── Tab renderers ─────────────────────────────────────────────


def _show_docling(result: dict[str, Any], pdf_path: Path, page_no: int) -> None:
    st.markdown(f"**{result['raw_counts']['texts']} texts**, **{result['raw_counts']['tables']} tables**, **{result['raw_counts']['pictures']} pictures**")
    label_counts: dict[str, int] = {}
    for t in result["texts"]:
        label_counts[t["label"]] = label_counts.get(t["label"], 0) + 1
    if label_counts:
        st.caption(f"Labels: {', '.join(f'{k}={v}' for k, v in sorted(label_counts.items()))}")
    st.divider()

    if not result["texts"] and not result["tables"] and not result["pictures"]:
        st.info("No items extracted for this page.")
        return

    for item_type in ("text", "table", "picture"):
        items = (
            result["texts"] if item_type == "text" else
            result["tables"] if item_type == "table" else
            result["pictures"]
        )
        for item in items:
            if item_type == "text":
                st.markdown(f"{fmt_label(item['label'])}  \n{item['text'][:600]}")
                if len(item['text']) > 600:
                    st.caption(f"... ({len(item['text']) - 600} more chars)")
            elif item_type == "table":
                st.markdown(f":red[**Table**] — {item['label']}  \ncol consistency: {_table_col_consistency(item['grid'])}%, fill: {_cell_fill_rate(item['grid'])}%")
                st.markdown(render_grid(item['grid']), unsafe_allow_html=True)
            elif item_type == "picture":
                bbox = item["prov"].get("bbox")
                if bbox:
                    try:
                        img = _crop_from_pdf(pdf_path, page_no, bbox, item["page_height"])
                        st.image(img, use_column_width=True)
                        st.caption(f"Image — {item['label']}")
                    except Exception as e:
                        st.caption(f"_Crop failed: {e}_")
            st.divider()


def _show_pdfplumber(result: dict[str, Any]) -> None:
    if result.get("error") and not result["text"] and not result["tables"]:
        st.error(f"pdfplumber error: {result['error']}")
        return

    text, tables = result["text"], result["tables"]
    st.markdown(f"**{len(text)} chars**, **{len(tables)} tables**")
    st.divider()

    if text:
        st.markdown("**Extracted Text**")
        st.text(text[:1500])
        if len(text) > 1500:
            st.caption(f"... ({len(text) - 1500} more chars)")
        st.divider()

    if tables:
        st.markdown(f"**Tables ({len(tables)})**")
        for i, grid in enumerate(tables):
            st.markdown(f"*Table {i+1}* — consistency: {_table_col_consistency(grid)}%, fill: {_cell_fill_rate(grid)}%")
            st.markdown(render_grid(grid), unsafe_allow_html=True)
            st.divider()
    else:
        st.info("No tables found on this page.")


def _show_camelot(result: dict[str, Any]) -> None:
    if result.get("errors") and not result["tables"]:
        for err in result["errors"]:
            if "not installed" in err:
                st.info("`camelot-py` not installed. Install with `pip install camelot-py[base]`")
                return
        for err in result["errors"]:
            st.caption(f"Flavor note: {err}")

    tables = result["tables"]
    if not tables:
        st.info("No tables found by Camelot on this page.")
        return

    st.markdown(f"**{len(tables)} tables**")
    st.divider()

    for i, t in enumerate(tables):
        st.markdown(
            f":orange[**Camelot ({t['flavor']})**] — "
            f"reported accuracy: {t['accuracy']}%, "
            f"consistency: {_table_col_consistency(t['grid'])}%, "
            f"fill: {_cell_fill_rate(t['grid'])}%"
        )
        st.markdown(render_grid(t["grid"]), unsafe_allow_html=True)
        st.divider()


def _show_unstructured(result: dict[str, Any]) -> None:
    if result.get("error"):
        if "not installed" in result.get("error", ""):
            st.info("`unstructured` not installed. Install with `pip install unstructured[pdf]`")
        else:
            st.error(f"Unstructured error: {result['error']}")
        return

    items = result["items"]
    if not items:
        st.info("No elements extracted by Unstructured on this page.")
        return

    cats: dict[str, int] = {}
    for item in items:
        cats[item["category"]] = cats.get(item["category"], 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(cats.items()))
    st.markdown(f"**{len(items)} elements** ({summary})")
    st.divider()

    for item in items:
        if item["category"] == "Table" and item.get("html"):
            st.markdown(f"{fmt_label(item['category'])}  \n(has text_as_html)")
            st.markdown(item["html"], unsafe_allow_html=True)
        else:
            st.markdown(f"{fmt_label(item['category'])}  \n{item['text'][:500]}")
            if len(item['text']) > 500:
                st.caption(f"... ({len(item['text']) - 500} more chars)")
        st.divider()


# ─── Main ──────────────────────────────────────────────────────


def main():
    st.set_page_config(layout="wide", page_title="Extraction Library Comparison")
    st.title("Extraction Library Comparison")
    st.markdown(
        "Compare how **Docling**, **pdfplumber**, **Camelot**, and **Unstructured** "
        "extract content from the same PDF page — with timing and accuracy scores."
    )

    pdf_files = sorted(SAMPLE_DIR.glob("*.pdf"))
    if not pdf_files:
        st.error(f"No PDFs found in {SAMPLE_DIR}")
        return

    with st.sidebar:
        st.header("Settings")
        names = [f.name for f in pdf_files]
        selected_name = st.selectbox("PDF", names, index=0)
        pdf_path = SAMPLE_DIR / selected_name

        try:
            import fitz
            d = fitz.open(str(pdf_path))
            total_pages = len(d)
            d.close()
        except Exception:
            total_pages = 0

        page_no = st.number_input("Page", min_value=1, max_value=total_pages or 1, value=1)

        # Clear caches on PDF or page change
        if st.button("Clear caches & re-extract", use_container_width=True):
            _docling_cache.clear()
            _pdfplumber_cache.clear()
            _camelot_cache.clear()
            _unstructured_cache.clear()
            st.rerun()

        st.divider()
        st.markdown("**Legend**")
        for lib, color in [("Docling", "blue"), ("pdfplumber", "green"), ("Camelot", "orange"), ("Unstructured", "purple")]:
            st.markdown(f"- :{color}[**{lib}**]")

    # ── Extract all ─────────────────────────────────────────
    with st.spinner("Extracting with all libraries..."):
        dl_result = extract_docling(pdf_path, page_no)
        pp_result = extract_pdfplumber(pdf_path, page_no)
        cm_result = extract_camelot(pdf_path, page_no)
        us_result = extract_unstructured(pdf_path, page_no)

    # ── Summary table ───────────────────────────────────────
    st.subheader("Performance & Accuracy Summary")
    summary_cols = st.columns(4)
    headers = [("Docling", dl_result, "blue"),
               ("pdfplumber", pp_result, "green"),
               ("Camelot", cm_result, "orange"),
               ("Unstructured", us_result, "purple")]

    for col, (name, res, color) in zip(summary_cols, headers):
        with col:
            st.markdown(f":{color}[**{name}**]")
            st.markdown(f"⏱ {_timing_str(res['timing'])}")
            st.markdown(f"🎯 Accuracy: {_accuracy_bar(res['accuracy'])}")
            counts = res.get("raw_counts", {})
            st.caption(", ".join(f"{k}={v}" for k, v in counts.items()))
            if res.get("error") and "not installed" not in res.get("error", ""):
                st.caption(f":red[{res['error']}]")

    st.divider()

    # ── Side-by-side: page + library tabs ───────────────────
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Original PDF Page")
        img = render_page(pdf_path, page_no)
        if img:
            st.image(img, use_column_width=True)
        else:
            st.error("Could not render PDF page (fitz/PyMuPDF required).")

    with col2:
        st.subheader("Extraction Results")
        lib_tabs = st.tabs(["Docling", "pdfplumber", "Camelot", "Unstructured"])

        with lib_tabs[0]:
            _show_docling(dl_result, pdf_path, page_no)
        with lib_tabs[1]:
            _show_pdfplumber(pp_result)
        with lib_tabs[2]:
            _show_camelot(cm_result)
        with lib_tabs[3]:
            _show_unstructured(us_result)


if __name__ == "__main__":
    main()

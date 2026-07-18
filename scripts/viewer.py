#!/usr/bin/env python3
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "output"
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"

LABEL_COLORS = {
    "section_header": "blue",
    "paragraph": "default",
    "text": "default",
    "list_item": "green",
    "caption": "orange",
    "page_header": "purple",
    "page_footer": "purple",
    "footnote": "gray",
    "table": "red",
    "formula": "teal",
    "code": "brown",
    "checkbox_checked": "green",
    "checkbox_unchecked": "gray",
}


@st.cache_data
def load_json(path):
    with open(path) as f:
        return json.load(f)


def find_pdf_for_document(json_path):
    data = load_json(json_path)
    filename = data.get("origin", {}).get("filename", "")
    mimetype = data.get("origin", {}).get("mimetype", "")
    if "pdf" not in mimetype.lower():
        return None, mimetype
    candidate = SAMPLE_DIR / filename
    if candidate.exists():
        return candidate, mimetype
    stem = json_path.stem
    for f in SAMPLE_DIR.iterdir():
        if f.suffix.lower() == ".pdf" and stem[:20].lower() in f.stem.lower():
            return f, mimetype
    return None, mimetype


def render_page_image(pdf_path, page_no):
    import fitz
    doc = fitz.open(pdf_path)
    page = doc[page_no - 1]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img = pix.tobytes("png")
    doc.close()
    return img


def format_label(label):
    color = LABEL_COLORS.get(label, "default")
    if color != "default":
        return f":{color}[**{label}**]"
    return f"**{label}**"


def extract_page_numbers(data):
    pages = data.get("pages", {})
    if pages:
        return sorted(int(p) for p in pages.keys())
    texts = data.get("texts", [])
    return sorted(set(
        item["prov"][0]["page_no"]
        for item in texts
        if item.get("prov") and item["prov"][0].get("page_no")
    ))


def walk_body_items(data):
    texts = {f"#/texts/{i}": t for i, t in enumerate(data.get("texts", []))}
    tables = {f"#/tables/{i}": t for i, t in enumerate(data.get("tables", []))}
    pictures = {f"#/pictures/{i}": p for i, p in enumerate(data.get("pictures", []))}
    all_items = {**texts, **tables, **pictures}
    groups_by_ref = {g["self_ref"]: g for g in data.get("groups", [])}

    def _walk(children_list):
        for child in children_list:
            ref = child.get("$ref", "")
            if not ref:
                continue
            parts = ref.split("/")
            if len(parts) == 3:
                kind = parts[1]
                if kind in ("texts", "tables", "pictures"):
                    yield ref, all_items.get(ref)
                    item = all_items.get(ref)
                    if item and item.get("children"):
                        yield from _walk(item["children"])
                elif kind == "groups":
                    grp = groups_by_ref.get(ref)
                    if grp:
                        yield from _walk(grp.get("children", []))

    body = data.get("body", {})
    return list(_walk(body.get("children", [])))


def get_page_items_with_breadcrumbs(data, page_no):
    ordered = walk_body_items(data)
    heading_stack = []
    result = []
    for ref, item in ordered:
        if item is None:
            continue
        kind = ref.split("/")[1]
        if kind == "texts" and item.get("label") == "section_header":
            level = item.get("level", 1)
            text = item.get("text", "").strip()[:60]
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, text))
        prov = item.get("prov", [])
        if not prov or prov[0].get("page_no") != page_no:
            continue
        crumbs = " > ".join(t for _, t in heading_stack)
        result.append((kind, item, crumbs))
    return result


def render_table(tbl):
    data = tbl.get("data", {})
    cells = data.get("table_cells", [])
    num_rows = data.get("num_rows", 0)
    num_cols = data.get("num_cols", 0)
    if not cells or num_rows == 0:
        st.markdown(f"_Empty table ({tbl.get('label', '?')})_")
        return
    grid = [["" for _ in range(num_cols)] for _ in range(num_rows)]
    is_header = [[False] * num_cols for _ in range(num_rows)]
    for cell in cells:
        text = cell.get("text", "")
        rs = cell.get("start_row_offset_idx", 0)
        re = cell.get("end_row_offset_idx", rs + 1)
        cs = cell.get("start_col_offset_idx", 0)
        ce = cell.get("end_col_offset_idx", cs + 1)
        for r in range(rs, min(re, num_rows)):
            for c in range(cs, min(ce, num_cols)):
                grid[r][c] = text
                if cell.get("column_header"):
                    is_header[r][c] = True
    html = '<table style="border-collapse:collapse;width:100%;font-size:0.85em;margin:4px 0;">'
    for r in range(num_rows):
        html += "<tr>"
        for c in range(num_cols):
            tag = "th" if is_header[r][c] else "td"
            style = "border:1px solid #ccc;padding:4px;text-align:left;vertical-align:top;"
            if is_header[r][c]:
                style += "background:#f0f0f0;font-weight:bold;"
            html += f"<{tag} style='{style}'>{grid[r][c]}</{tag}>"
        html += "</tr>"
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)
    st.caption(f"Table — {tbl.get('label', '?')}  ({num_rows} rows × {num_cols} cols)")


def crop_image_from_pdf(pdf_path, page_no, bbox, page_height_pt):
    import fitz
    doc = fitz.open(pdf_path)
    page = doc[page_no - 1]
    l = bbox["l"]
    r = bbox["r"]
    t = bbox["t"]
    b = bbox["b"]
    y0 = page_height_pt - t
    y1 = page_height_pt - b
    rect = fitz.Rect(l, y0, r, y1)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect)
    img = pix.tobytes("png")
    doc.close()
    return img


def show_page_items_ordered(data, page_no, pdf_path, page_height_pt):
    items = get_page_items_with_breadcrumbs(data, page_no)
    if not items:
        st.info("No content extracted for this page.")
        return
    for i, (kind, item, crumbs) in enumerate(items):
        if i > 0:
            st.divider()
        if kind == "texts":
            label = item.get("label", "unknown")
            text = item.get("text", "")
            if crumbs:
                st.caption(f"📍 {crumbs}")
            if label == "formula":
                st.markdown(f"{format_label(label)}")
                if text:
                    st.code(text, language=None)
            else:
                st.markdown(f"{format_label(label)}  \n{text[:600]}")
                if len(text) > 600:
                    st.text(f"... ({len(text) - 600} more chars)")
        elif kind == "tables":
            render_table(item)
        elif kind == "pictures":
            if pdf_path is None:
                continue
            bbox = item.get("prov", [{}])[0].get("bbox")
            if bbox:
                try:
                    img = crop_image_from_pdf(pdf_path, page_no, bbox, page_height_pt)
                    st.image(img, use_column_width=True)
                    st.caption(f"Image — {item.get('label', 'picture')}")
                except Exception as e:
                    st.caption(f"_Image crop failed: {e}_")


def main():
    st.set_page_config(layout="wide", page_title="Document Extraction Viewer")
    st.title("Document Extraction Viewer")
    st.markdown("Compare original document pages with extracted text content.")

    json_files = sorted(OUTPUT_DIR.glob("*.json"))
    if not json_files:
        st.error(f"No JSON output files found in {OUTPUT_DIR}")
        return

    with st.sidebar:
        st.header("Document")
        doc_names = [jf.name.replace(".json", "").replace(".json", "") for jf in json_files]
        selected = st.selectbox("Select a document", doc_names, index=0)
        selected_path = json_files[doc_names.index(selected)]

        data = load_json(selected_path)
        origin = data.get("origin", {})
        filename = origin.get("filename", selected_path.name)
        mimetype = origin.get("mimetype", "unknown")
        texts = data.get("texts", [])
        tables = data.get("tables", [])
        pictures = data.get("pictures", [])
        pages_data = data.get("pages", {})

        st.markdown("---")
        st.markdown("**Info**")
        st.code(f"Source:  {filename}")
        st.code(f"Type:    {mimetype}")
        st.code(f"Pages:   {len(pages_data) or 'N/A'}")
        st.code(f"Texts:   {len(texts)}")
        st.code(f"Tables:  {len(tables)}")
        st.code(f"Images:  {len(pictures)}")

        pdf_path, actual_mime = find_pdf_for_document(selected_path)
        can_render = pdf_path is not None
        if not can_render:
            st.warning(f"Page rendering unavailable for {actual_mime}")

        st.markdown("---")
        st.markdown("**Page Selection**")
        all_page_nos = extract_page_numbers(data)
        if not all_page_nos:
            st.error("No pages found in this document.")
            return

        n_pages = min(5, len(all_page_nos))
        if st.button("🎲 Pick 5 random pages", use_container_width=True):
            random.seed()
            st.session_state.selected_pages = sorted(random.sample(all_page_nos, n_pages))
            st.rerun()
        elif "selected_pages" not in st.session_state:
            st.session_state.selected_pages = all_page_nos[:n_pages]

        custom_page = st.number_input(
            "Jump to page",
            min_value=1,
            max_value=max(all_page_nos),
            value=1,
        )
        if st.button("Go to page", use_container_width=True):
            st.session_state.selected_pages = [custom_page]
            st.rerun()

    selected_pages = st.session_state.get("selected_pages", all_page_nos[:5])
    st.subheader(f"Showing {len(selected_pages)} page(s) — `{filename}`")

    for page_no in selected_pages:
        st.markdown("---")
        st.markdown(f"### Page {page_no}")
        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown("**Original Document**")
            if can_render:
                try:
                    img_bytes = render_page_image(pdf_path, page_no)
                    st.image(img_bytes, use_column_width=True)
                except Exception as e:
                    st.error(f"Render error: {e}")
            else:
                st.info(f"No PDF available for `{actual_mime}`")

        page_height_pt = pages_data.get(str(page_no), {}).get("size", {}).get("height", 842)

        with col2:
            st.markdown("**Extracted Content**")
            show_page_items_ordered(data, page_no, pdf_path, page_height_pt)


if __name__ == "__main__":
    main()

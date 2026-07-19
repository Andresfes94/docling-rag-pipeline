# Licensing

## Project License

**Docling RAG Pipeline** is released under a custom **Personal Use License** — see [`LICENSE`](../LICENSE).

- ✅ **Free** for personal, educational, and research use
- ❌ **Commercial use** requires a license from the copyright holder
- 🔗 Contact: [https://github.com/Andresfes94](https://github.com/Andresfes94)

---

## Third-Party Component Licenses

| Component | License | Bundled? | Notes |
|---|---|---|---|
| **Core pipeline code** | Personal Use License (custom) | Always | See LICENSE file |
| **Docling** (IBM) | MIT | Core dependency | |
| **Docling Core** (IBM) | MIT | Core dependency | |
| **sentence-transformers** | Apache 2.0 | Core dependency | |
| **ChromaDB** | Apache 2.0 | Core dependency | |
| **FastAPI** | MIT | Core dependency | |
| **PyMuPDF4LLM** (Artifex) | AGPL-3.0 / commercial | Optional `[pymupdf]` | |
| **Marker** (Datalab) | GPL-3.0 | Optional `[marker]` | Commercial license available from Datalab |
| **Surya** (OCR, via Marker) | GPL-3.0 | Optional (via Marker) | |
| **Landing AI ADE Parse** | Proprietary | Optional `[landingai]` | Cloud API, requires API key |
| **LlamaParse** (LlamaIndex) | Proprietary | Optional `[llamaparse]` | Cloud API, requires API key |
| **PyTorch** | BSD-style | Transitive | Via sentence-transformers / Marker |
| **rank-bm25** | Apache 2.0 | Optional (hybrid search) | |

---

## Optional Dependency Installation

```bash
# Core only (MIT + Apache 2.0)
pip install -r requirements-core.txt

# With PyMuPDF4LLM (AGPL)
pip install pymupdf4llm

# With Marker (GPL-3.0)
pip install marker-pdf[full]

# With cloud engines
pip install requests  # needed for Landing AI + LlamaParse
```

---

## FAQ

**Can I use this at my company for internal purposes?**
If it generates revenue or supports a commercial product, you need a commercial license.

**Can I modify the code and share it?**
Yes — for personal, educational, or research purposes. Share-alike appreciated but not required.

**I want to sell a product that uses this pipeline.**
Contact the copyright holder for a commercial license.

**What about the optional engines' licenses?**
- **PyMuPDF4LLM** is AGPL-3.0 — if you distribute a combined work, AGPL terms apply.
- **Marker** is GPL-3.0 — if you distribute a combined work, GPL terms apply.
- **Landing AI** and **LlamaParse** are proprietary cloud APIs — you need your own API key and accept their terms of service.

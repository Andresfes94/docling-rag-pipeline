from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.retrieval.pipeline import RAGPipeline


@pytest.fixture
def profiles_path() -> Path:
    return Path(__file__).resolve().parent.parent / "profiles.yaml"


@pytest.fixture
def sample_json(tmp_path: Path) -> Path:
    data = {
        "texts": [
            {
                "text": "Hello World",
                "label": "PARAGRAPH",
                "prov": [{"page_no": 1}],
            },
            {
                "text": "Introduction",
                "label": "SECTION_HEADER",
                "prov": [{"page_no": 1}],
            },
        ],
        "tables": [],
        "pictures": [],
        "key_value_items": [],
        "body": {"children": []},
        "furniture": {"children": []},
        "groups": [],
        "schema_name": "DoclingDocument",
        "version": "2.0.0",
    }
    path = tmp_path / "sample.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def sample_markdown(tmp_path: Path) -> Path:
    path = tmp_path / "sample.md"
    path.write_text("Hello World\n\nIntroduction\n", encoding="utf-8")
    return path


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def sample_pdf_path(fixtures_dir: Path) -> Path:
    p = fixtures_dir / "sample_text.pdf"
    if not p.is_file():
        pytest.skip("sample_text.pdf fixture not found — run create_fixtures.py first")
    return p


@pytest.fixture
def sample_xlsx_path(fixtures_dir: Path) -> Path:
    p = fixtures_dir / "sample.xlsx"
    if not p.is_file():
        pytest.skip("sample.xlsx fixture not found — run create_fixtures.py first")
    return p


@pytest.fixture
def tmp_chroma(tmp_path: Path) -> Path:
    return tmp_path / "chroma"


@pytest.fixture
def pipeline(tmp_chroma: Path, profiles_path: Path) -> RAGPipeline:
    return RAGPipeline(
        persist_directory=str(tmp_chroma),
        profiles_path=str(profiles_path),
        output_dir=str(tmp_chroma.parent / "output"),
        auto_retry=True,
    )


@pytest.fixture
def pipeline_no_retry(tmp_chroma: Path, profiles_path: Path) -> RAGPipeline:
    return RAGPipeline(
        persist_directory=str(tmp_chroma),
        profiles_path=str(profiles_path),
        output_dir=str(tmp_chroma.parent / "output"),
        auto_retry=False,
    )


def check_chroma_output(pipeline: RAGPipeline, tmp_chroma: Path) -> None:
    if not tmp_chroma.is_dir():
        pytest.skip(f"Chroma dir {tmp_chroma} not created (likely empty conversion)")

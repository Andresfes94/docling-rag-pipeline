from __future__ import annotations

import json
from pathlib import Path

import pytest



@pytest.fixture
def profiles_path() -> Path:
    return Path(__file__).resolve().parent.parent / "profiles.yaml"


@pytest.fixture
def sample_json(tmp_path: Path) -> Path:
    """Create a minimal DoclingDocument JSON for testing."""
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

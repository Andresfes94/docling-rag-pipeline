from __future__ import annotations

from pathlib import Path
from typing import Any

from src.ingestion.engines.base import ExtractionEngine
from src.ingestion.engines.docling_engine import DoclingEngine

_REGISTRY: dict[str, type[ExtractionEngine]] = {
    "docling": DoclingEngine,
}

_OPTIONAL_REGISTRY: dict[str, type[ExtractionEngine]] = {}


def _try_register(name: str, module_path: str, class_name: str) -> None:
    try:
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        _OPTIONAL_REGISTRY[name] = cls
    except Exception:
        pass


_try_register("pymupdf4llm", "src.ingestion.engines.pymupdf_engine", "PyMuPDF4LLMEngine")
_try_register("marker", "src.ingestion.engines.marker_engine", "MarkerEngine")
_try_register("landingai", "src.ingestion.engines.landingai_engine", "LandingAIEngine")
_try_register("llamaparse", "src.ingestion.engines.llamaparse_engine", "LlamaParseEngine")


def register_engine(name: str, engine_cls: type[ExtractionEngine]) -> None:
    _REGISTRY[name] = engine_cls


def get_engine(name: str) -> ExtractionEngine | None:
    cls = _REGISTRY.get(name) or _OPTIONAL_REGISTRY.get(name)
    if cls is None:
        return None
    return cls()


def list_engines() -> list[str]:
    return list(_REGISTRY) + list(_OPTIONAL_REGISTRY)


def get_engines_for(source: str | Path, prefer_accurate: bool = False) -> list[ExtractionEngine]:
    all_engines = [get_engine(n) for n in list_engines()]
    all_engines = [e for e in all_engines if e is not None and e.can_handle(source)]
    all_engines.sort(key=lambda e: e.estimate_confidence(source), reverse=True)
    if prefer_accurate:
        all_engines.sort(
            key=lambda e: (not e.requires_network, e.estimate_confidence(source)),
            reverse=True,
        )
    return all_engines

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from src.ingestion.loader import ConversionOutput


class ExtractionEngine(ABC):
    name: str = "base"
    supported_formats: list[str] = []
    requires_gpu: bool = False
    requires_network: bool = False

    @abstractmethod
    def convert(
        self,
        source: str | Path,
        profile_name: str = "standard",
        output_dir: str | Path = "data/output",
        profiles_path: str | Path = "profiles.yaml",
        timeout_seconds: int = 0,
        **kwargs: Any,
    ) -> ConversionOutput:
        ...

    def can_handle(self, source: str | Path) -> bool:
        ext = Path(source).suffix.lower()
        return ext in self.supported_formats or not self.supported_formats

    def estimate_confidence(self, source: str | Path) -> float:
        return 0.5

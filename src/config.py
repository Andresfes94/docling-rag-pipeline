from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class Settings:
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "*"

    chroma_persist_dir: str = "data/chroma"
    output_dir: str = "data/output"
    profiles_path: str = "profiles.yaml"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_max_tokens: int = 512

    ollama_base_url: str = "http://localhost:11434"
    lmstudio_base_url: str = "http://localhost:1234"

    redis_url: str | None = None

    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    cache_capacity: int = 1024
    cache_ttl: int = 300

    evaluator_script: str = "scripts/docling-evaluate.py"

    _extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls, prefix: str = "RAG_") -> Settings:
        """Build Settings from environment variables.

        Environment variables can be set directly (e.g. API_HOST) or with
        an optional prefix (e.g. RAG_API_HOST). Direct vars take precedence.
        """
        env = {**os.environ}

        def _get(key: str, default: str = "") -> str:
            prefixed = env.get(f"{prefix}{key}")
            direct = env.get(key)
            return direct or prefixed or default

        return cls(
            api_host=_get("API_HOST", "0.0.0.0"),
            api_port=int(_get("API_PORT", "8000")),
            cors_origins=_get("CORS_ORIGINS", "*"),
            chroma_persist_dir=_get("CHROMA_PERSIST_DIR", "data/chroma"),
            output_dir=_get("OUTPUT_DIR", "data/output"),
            profiles_path=_get("PROFILES_PATH", "profiles.yaml"),
            embedding_model=_get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            chunk_max_tokens=int(_get("CHUNK_MAX_TOKENS", "512")),
            ollama_base_url=_get("OLLAMA_BASE_URL", "http://localhost:11434"),
            lmstudio_base_url=_get("LMSTUDIO_BASE_URL", "http://localhost:1234"),
            redis_url=_get("REDIS_URL") or None,
            log_level=_get("LOG_LEVEL", "INFO"),
            log_format=_get("LOG_FORMAT", "text"),  # type: ignore[assignment]
            cache_capacity=int(_get("CACHE_CAPACITY", "1024")),
            cache_ttl=int(_get("CACHE_TTL", "300")),
            evaluator_script=_get("EVALUATOR_SCRIPT", "scripts/docling-evaluate.py"),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.api_port < 1 or self.api_port > 65535:
            errors.append(f"API_PORT={self.api_port} is out of range (1-65535)")
        if self.chunk_max_tokens < 64:
            errors.append(f"CHUNK_MAX_TOKENS={self.chunk_max_tokens} is too low (minimum 64)")
        if self.cache_capacity < 1:
            errors.append(f"CACHE_CAPACITY={self.cache_capacity} must be >= 1")
        if self.cache_ttl < 1:
            errors.append(f"CACHE_TTL={self.cache_ttl} must be >= 1")
        return errors

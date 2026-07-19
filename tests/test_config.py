from __future__ import annotations

import os

from src.config import Settings


class TestSettings:
    def test_default_values(self):
        s = Settings()
        assert s.api_host == "0.0.0.0"
        assert s.api_port == 8000
        assert s.chroma_persist_dir == "data/chroma"
        assert s.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
        assert s.chunk_max_tokens == 512
        assert s.ollama_base_url == "http://localhost:11434"
        assert s.lmstudio_base_url == "http://localhost:1234"
        assert s.redis_url is None
        assert s.log_level == "INFO"
        assert s.log_format == "text"
        assert s.cache_capacity == 1024
        assert s.cache_ttl == 300
        assert s.cors_origins == "*"

    def test_from_env_uses_defaults(self):
        s = Settings.from_env()
        assert s.api_host == "0.0.0.0"
        assert s.api_port == 8000

    def test_from_env_reads_env_vars(self):
        os.environ["TEST_API_HOST"] = "127.0.0.1"
        os.environ["TEST_API_PORT"] = "9000"
        os.environ["TEST_REDIS_URL"] = "redis://localhost:6379"
        try:
            s = Settings.from_env(prefix="TEST_")
            assert s.api_host == "127.0.0.1"
            assert s.api_port == 9000
            assert s.redis_url == "redis://localhost:6379"
        finally:
            del os.environ["TEST_API_HOST"]
            del os.environ["TEST_API_PORT"]
            del os.environ["TEST_REDIS_URL"]

    def test_direct_env_takes_precedence(self):
        os.environ["API_HOST"] = "10.0.0.1"
        os.environ["RAG_API_HOST"] = "10.0.0.2"
        try:
            s = Settings.from_env(prefix="RAG_")
            assert s.api_host == "10.0.0.1"
        finally:
            del os.environ["API_HOST"]
            del os.environ["RAG_API_HOST"]

    def test_redis_url_defaults_to_none(self):
        os.environ["REDIS_URL"] = ""
        try:
            s = Settings.from_env()
            assert s.redis_url is None
        finally:
            del os.environ["REDIS_URL"]

    def test_validate_valid(self):
        s = Settings()
        assert s.validate() == []

    def test_validate_bad_port(self):
        s = Settings(api_port=99999)
        errors = s.validate()
        assert len(errors) == 1
        assert "port" in errors[0].lower()

    def test_validate_low_chunk_tokens(self):
        s = Settings(chunk_max_tokens=16)
        errors = s.validate()
        assert len(errors) >= 1
        assert "chunk" in errors[0].lower()

    def test_validate_cache_capacity_zero(self):
        s = Settings(cache_capacity=0)
        errors = s.validate()
        assert len(errors) >= 1
        assert "cache_capacity" in errors[0] or "CACHE_CAPACITY" in errors[0]

    def test_validate_cache_ttl_zero(self):
        s = Settings(cache_ttl=0)
        errors = s.validate()
        assert len(errors) >= 1
        assert "cache_ttl" in errors[0] or "CACHE_TTL" in errors[0]

    def test_log_format_type(self):
        s = Settings(log_format="json")
        assert s.log_format == "json"

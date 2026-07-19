from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest

from src.llm.client import LLMClient, _is_retryable, _RETRY_DELAYS


class TestRetryable:
    def test_http_5xx_is_retryable(self):
        exc = urllib.error.HTTPError("/url", 503, "Service Unavailable", {}, None)
        assert _is_retryable(exc)

    def test_http_4xx_not_retryable(self):
        exc = urllib.error.HTTPError("/url", 400, "Bad Request", {}, None)
        assert not _is_retryable(exc)

    def test_url_error_is_retryable(self):
        exc = urllib.error.URLError("connection refused")
        assert _is_retryable(exc)

    def test_os_error_is_retryable(self):
        exc = OSError("connection reset")
        assert _is_retryable(exc)

    def test_value_error_not_retryable(self):
        exc = ValueError("something else")
        assert not _is_retryable(exc)


class TestLLMRetry:
    def make_client(self):
        return LLMClient(provider="ollama", model="test-model")

    def test_retries_on_500_then_succeeds(self):
        client = self.make_client()
        responses = [
            urllib.error.HTTPError("/url", 500, "Internal Error", {}, None),
            urllib.error.HTTPError("/url", 500, "Internal Error", {}, None),
            {"response": "hello after retry", "eval_count": 5, "eval_duration": 1e9},
        ]
        call_count = 0

        def mock_urlopen(*args, **kwargs):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            if isinstance(resp, Exception):
                raise resp
            from unittest.mock import MagicMock
            mock = MagicMock()
            mock.read.return_value = json.dumps(resp).encode()
            mock.__enter__.return_value = mock
            mock.__exit__.return_value = None
            return mock

        with patch("urllib.request.urlopen", mock_urlopen):
            result = client.generate("test")
            assert result["text"] == "hello after retry"
            assert call_count == 3

    def test_exhausts_retries_on_persistent_500(self):
        client = self.make_client()

        def mock_urlopen(*args, **kwargs):
            raise urllib.error.HTTPError("/url", 500, "Internal Error", {}, None)

        with patch("urllib.request.urlopen", mock_urlopen):
            with pytest.raises(urllib.error.HTTPError):
                client.generate("test")

    def test_does_not_retry_on_400(self):
        client = self.make_client()

        def mock_urlopen(*args, **kwargs):
            raise urllib.error.HTTPError("/url", 400, "Bad Request", {}, None)

        with patch("urllib.request.urlopen", mock_urlopen):
            with pytest.raises(urllib.error.HTTPError) as excinfo:
                client.generate("test")
            assert excinfo.value.code == 400

    def test_retries_on_connection_error_then_succeeds(self):
        client = self.make_client()
        responses = [
            urllib.error.URLError("connection refused"),
            {"response": "ok after retry", "eval_count": 3, "eval_duration": 500_000_000},
        ]
        call_count = 0

        def mock_urlopen(*args, **kwargs):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            if isinstance(resp, Exception):
                raise resp
            from unittest.mock import MagicMock
            mock = MagicMock()
            mock.read.return_value = json.dumps(resp).encode()
            mock.__enter__.return_value = mock
            mock.__exit__.return_value = None
            return mock

        with patch("urllib.request.urlopen", mock_urlopen):
            result = client.generate("test")
            assert result["text"] == "ok after retry"
            assert call_count == 2

    def test_openai_provider_retries_on_500(self):
        client = LLMClient(provider="lmstudio", model="test-model")
        responses = [
            urllib.error.HTTPError("/url", 502, "Bad Gateway", {}, None),
            {"choices": [{"message": {"content": "recovered"}}], "usage": {"completion_tokens": 2}},
        ]
        call_count = 0

        def mock_urlopen(*args, **kwargs):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            if isinstance(resp, Exception):
                raise resp
            from unittest.mock import MagicMock
            mock = MagicMock()
            mock.read.return_value = json.dumps(resp).encode()
            mock.__enter__.return_value = mock
            mock.__exit__.return_value = None
            return mock

        with patch("urllib.request.urlopen", mock_urlopen):
            result = client.generate("test")
            assert result["text"] == "recovered"
            assert call_count == 2

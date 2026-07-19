from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

_log = logging.getLogger(__name__)

import os

OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
LMSTUDIO_BASE = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234")

_MAX_RETRIES = 3
_RETRY_DELAYS = [1.0, 2.0, 4.0]


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500
    if isinstance(exc, (urllib.error.URLError, TimeoutError, OSError)):
        return True
    return False


class LLMClient:
    def __init__(self, provider: str = "ollama", model: str = "llama3.2", base_url: str | None = None):
        self.provider = provider
        self.model = model
        if base_url:
            self.base_url = base_url.rstrip("/")
        elif provider == "ollama":
            self.base_url = OLLAMA_BASE
        elif provider == "lmstudio":
            self.base_url = LMSTUDIO_BASE
        else:
            self.base_url = OLLAMA_BASE

    def _ollama_generate(self, prompt: str, system: str = "", temperature: float = 0.1, max_tokens: int = 512) -> dict[str, Any]:
        body = {
            "model": self.model,
            "prompt": prompt,
            "system": system if system else None,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            _log.error("Ollama HTTP %d: %s", e.code, e.read().decode()[:200])
            raise
        elapsed = time.monotonic() - t0
        text = data.get("response", "")
        tokens = data.get("eval_count", 0)
        duration = data.get("eval_duration", 0) / 1e9
        return {
            "text": text,
            "tokens": tokens,
            "duration_s": round(duration or elapsed, 2),
            "model": self.model,
        }

    def _openai_generate(self, prompt: str, system: str = "", temperature: float = 0.1, max_tokens: int = 512) -> dict[str, Any]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            _log.error("OpenAI-compat HTTP %d: %s", e.code, e.read().decode()[:200])
            raise
        elapsed = time.monotonic() - t0
        choices = data.get("choices", [])
        text = choices[0]["message"]["content"] if choices else ""
        usage = data.get("usage", {})
        tokens = usage.get("completion_tokens", 0)
        return {
            "text": text,
            "tokens": tokens,
            "duration_s": round(elapsed, 2),
            "model": self.model,
        }

    def _generate_with_retry(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.1,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                if self.provider == "ollama":
                    return self._ollama_generate(prompt, system, temperature, max_tokens)
                return self._openai_generate(prompt, system, temperature, max_tokens)
            except urllib.error.HTTPError as e:
                if e.code >= 500 and attempt < _MAX_RETRIES:
                    delay = _RETRY_DELAYS[attempt]
                    _log.warning("LLM %s (attempt %d/%d), retrying in %.1fs…", e.code, attempt + 1, _MAX_RETRIES, delay)
                    time.sleep(delay)
                    last_exc = e
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_DELAYS[attempt]
                    _log.warning("LLM connection error (attempt %d/%d), retrying in %.1fs…", attempt + 1, _MAX_RETRIES, delay)
                    time.sleep(delay)
                    last_exc = e
                    continue
                raise
            except json.JSONDecodeError:
                _log.error("LLM returned invalid JSON — not retrying")
                raise

        msg = f"LLM call failed after {_MAX_RETRIES + 1} attempts"
        _log.error(msg)
        raise RuntimeError(msg) from last_exc

    def generate(self, prompt: str, system: str = "", temperature: float = 0.1, max_tokens: int = 512) -> dict[str, Any]:
        import re

        result = self._generate_with_retry(prompt, system, temperature, max_tokens)

        text = result["text"]
        # Strip all <think>...</think> blocks (any position, multiple occurrences)
        blocks = re.findall(r"<think>(.*?)</think>", text, flags=re.DOTALL)
        if blocks:
            result["thinking"] = "\n\n".join(b.strip() for b in blocks)
            stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            result["text"] = stripped or result["thinking"]
        return result

    def check_available(self) -> bool:
        try:
            if self.provider == "ollama":
                req = urllib.request.Request(f"{self.base_url}/api/tags")
            else:
                req = urllib.request.Request(f"{self.base_url}/v1/models")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            if self.provider == "ollama":
                req = urllib.request.Request(f"{self.base_url}/api/tags")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    return [m["name"].removesuffix(":latest") for m in data.get("models", [])]
            else:
                req = urllib.request.Request(f"{self.base_url}/v1/models")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    return [m.get("id", m.get("name", "")) for m in data.get("data", [])]
        except Exception:
            return []

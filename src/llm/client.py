from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any

_log = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"
LMSTUDIO_BASE = "http://localhost:1234"


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

    def generate(self, prompt: str, system: str = "", temperature: float = 0.1, max_tokens: int = 512) -> dict[str, Any]:
        if self.provider == "ollama":
            result = self._ollama_generate(prompt, system, temperature, max_tokens)
        else:
            result = self._openai_generate(prompt, system, temperature, max_tokens)

        text = result["text"]
        if text.startswith("<think>"):
            end = text.find("</think>")
            if end != -1:
                result["thinking"] = text[7:end].strip()
                result["text"] = text[end + 8:].strip()
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
                    return [m["name"].split(":")[0] if ":" in m["name"] else m["name"] for m in data.get("models", [])]
            else:
                req = urllib.request.Request(f"{self.base_url}/v1/models")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    return [m.get("id", m.get("name", "")) for m in data.get("data", [])]
        except Exception:
            return []

"""A model that answers with one JSON object, for drafting and judging.

Two adapters sit behind ``create_json_model``: a ``gemini-*`` name goes to the
OpenAI-compatible Gemini endpoint, anything else to a local Ollama server. A bad
reply is retried once. A missing server, model or key stops the run, and so does a hosted
answer of 400, 413 or 422 (rehearsal F6): the same request would be refused again, so it
is ``ModelUnavailable``, not a bad reply that burns repair rounds; 429 and 5xx stay
retryable. A hosted call's timeout is ``timeout`` (``HOSTED_TIMEOUT`` by default; drafting
passes its own, rehearsal F2).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from tonomyx.models.chat import DEFAULT_NUM_CTX, IDLE_TIMEOUT, KEEP_ALIVE, MAX_PREDICT
from tonomyx.models.errors import ModelError, ModelUnavailable

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_HOST = "generativelanguage.googleapis.com"
HOSTED_TIMEOUT = 300.0
_UNAVAILABLE_STATUS = frozenset({401, 403, 404})
# A hosted endpoint refuses the request itself: sending it again changes nothing.
_HOSTED_UNAVAILABLE_STATUS = _UNAVAILABLE_STATUS | {400, 413, 422}
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503})

__all__ = [
    "GeminiJson",
    "JsonModel",
    "JsonReply",
    "ModelError",
    "ModelUnavailable",
    "OllamaJson",
    "create_json_model",
]


@dataclass(frozen=True)
class JsonReply:
    data: dict[str, Any]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0


class JsonModel(Protocol):
    name: str

    def complete_json(self, system: str, user: str, *, seed: int) -> JsonReply: ...


def _parse_object(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("the reply is not a JSON object")
    return value


def _payload(response: httpx.Response) -> dict[str, Any]:
    """The decoded body, or an empty object when it is not a JSON object (a bad reply)."""
    try:
        value = response.json()
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _check_gemini_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != GEMINI_HOST or parsed.username:
        raise ModelUnavailable(f"the Gemini endpoint must be https://{GEMINI_HOST}/...")
    return url


def _send(
    client: httpx.Client, url: str, body: dict[str, Any],
    unavailable: frozenset[int] = _UNAVAILABLE_STATUS,
) -> httpx.Response:
    """POST once, and once more on a timeout or a transient status."""
    last: Exception | None = None
    for attempt in range(2):
        try:
            response = client.post(url, json=body)
            if response.status_code in unavailable:
                raise ModelUnavailable(
                    f"{body.get('model')}: the server answered {response.status_code}"
                )
            if response.status_code in _RETRYABLE_STATUS and attempt == 0:
                last = ModelError(f"the server answered {response.status_code}")
                time.sleep(1)
                continue
            response.raise_for_status()
            return response
        except httpx.ConnectError as exc:
            raise ModelUnavailable(f"cannot reach the model server: {type(exc).__name__}") from None
        except httpx.TimeoutException as exc:
            last = exc
            if attempt == 0:
                time.sleep(1)
        except httpx.HTTPStatusError as exc:
            raise ModelError(f"the server answered {exc.response.status_code}") from None
    raise ModelError(f"no reply from the model server: {type(last).__name__}") from None


@dataclass
class _Base:
    name: str
    transport: httpx.BaseTransport | None = None
    _client: httpx.Client | None = field(default=None, init=False, repr=False)

    def _call(self, system: str, user: str, seed: int) -> tuple[str, int, int]:
        raise NotImplementedError

    def complete_json(self, system: str, user: str, *, seed: int) -> JsonReply:
        started = time.perf_counter()
        problem = ""
        for _ in range(2):
            text, prompt_tokens, completion_tokens = self._call(system, user, seed)
            try:
                data = _parse_object(text)
            except ValueError as exc:
                problem = type(exc).__name__
                continue
            return JsonReply(data, prompt_tokens, completion_tokens, time.perf_counter() - started)
        raise ModelError(f"{self.name}: the reply was not a JSON object twice ({problem})")


@dataclass
class OllamaJson(_Base):
    base_url: str = "http://localhost:11434"

    def _call(self, system: str, user: str, seed: int) -> tuple[str, int, int]:
        if self._client is None:
            self._client = httpx.Client(transport=self.transport, timeout=IDLE_TIMEOUT)
        body = {
            "model": self.name,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False, "format": "json", "keep_alive": KEEP_ALIVE,
            "options": {"temperature": 0.0, "seed": seed, "num_ctx": DEFAULT_NUM_CTX,
                        "num_predict": MAX_PREDICT},
        }
        payload = _payload(_send(self._client, f"{self.base_url.rstrip('/')}/api/chat", body))
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        return (
            str(content or ""),
            _count(payload.get("prompt_eval_count")),
            _count(payload.get("eval_count")),
        )


@dataclass
class GeminiJson(_Base):
    api_key: str = field(default="", repr=False)
    base_url: str = GEMINI_BASE_URL
    timeout: float = HOSTED_TIMEOUT

    def _call(self, system: str, user: str, seed: int) -> tuple[str, int, int]:
        # ``seed`` is not sent: the OpenAI-compatible endpoint rejects the field (400,
        # 'Unknown name "seed"'). The caller still records it (a set's manifest).
        if self._client is None:
            self._client = httpx.Client(
                transport=self.transport, timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        body = {
            "model": self.name,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}, "temperature": 0.0,
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = _payload(_send(self._client, url, body, _HOSTED_UNAVAILABLE_STATUS))
        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        try:
            content = str(payload["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError):
            content = ""
        return (content, _count(usage.get("prompt_tokens")),
                _count(usage.get("completion_tokens")))


def create_json_model(
    name: str,
    *,
    ollama_url: str = "http://localhost:11434",
    transport: httpx.BaseTransport | None = None,
    gemini_url: str = GEMINI_BASE_URL,
    timeout: float = HOSTED_TIMEOUT,
) -> JsonModel:
    if name.startswith("gemini-"):
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ModelUnavailable(f"{name}: GEMINI_API_KEY is not set")
        return GeminiJson(name=name, transport=transport, api_key=key,
                          base_url=_check_gemini_url(gemini_url), timeout=timeout)
    return OllamaJson(name=name, transport=transport, base_url=ollama_url)

"""The language model, as a port.

One adapter ships: Ollama's /api/chat, which serves every local model the
experiment plan uses. A hosted model (an OpenAI-compatible endpoint, the Anthropic
API) is a second class implementing ChatModel; nothing that calls a model changes.

Messages and tool calls use Ollama's shape, which is also OpenAI's apart from
arguments arriving as an object rather than JSON text; the agent accepts both.

Errors (ruling R2a). A call raises only ``ModelUnavailable`` or ``ModelError``
(``tonomyx.models.errors``), never a raw ``httpx`` error. A refused connection, a model
the server does not know (404, or an Ollama "model ... not found" body) and a missing or
refused key (401, 403) are ``ModelUnavailable``: the run must stop. Any other failed call,
after its one retry, and a reply that cannot be read are ``ModelError``. An error's text
names the model, the status code or the exception's type, and nothing else: never a key,
a URL or the server's body.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from tonomyx.models.errors import ModelError, ModelUnavailable


@dataclass(frozen=True)
class ChatReply:
    """One assistant turn, and what it cost."""

    message: dict[str, Any]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0


THINK_LEVELS = ("low", "medium", "high")
# Model families whose ``think`` is a level, not a switch (gpt-oss cannot turn thinking off).
LEVEL_THINKING_FAMILIES = ("gpt-oss",)


@dataclass(frozen=True)
class Sampling:
    """Decoding settings, recorded with every result."""

    temperature: float = 0.0
    seed: int | None = None
    think: bool | str | None = None
    num_ctx: int | None = None
    num_predict: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.think, str) and self.think not in THINK_LEVELS:
            raise ValueError(f"think must be a bool or one of {THINK_LEVELS}, not {self.think!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"temperature": self.temperature, "seed": self.seed, "think": self.think,
                "num_ctx": self.num_ctx, "num_predict": self.num_predict}


def think_problem(model: str, think: bool | str | None) -> str | None:
    """Why ``think`` cannot be used with ``model``, or ``None``. A level needs a family that
    takes levels; a family that takes levels cannot turn thinking off. The family is the
    model name before ``:``."""
    family = model.split(":", 1)[0]
    if isinstance(think, str) and family not in LEVEL_THINKING_FAMILIES:
        return f"{model} does not take a think level ({think!r}); use true or false"
    if think is False and family in LEVEL_THINKING_FAMILIES:
        return f"{model} cannot turn thinking off; use one of {THINK_LEVELS}"
    return None


class ChatModel(Protocol):
    """Anything that answers a chat turn, optionally with tool calls."""

    name: str

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatReply: ...


# Ollama 0.20 gives a GPU with at least 48 GiB of VRAM a 262144-token context.
# These checkpoints were trained at 32k–40k. Asking for 262144 reloads the runner.
DEFAULT_NUM_CTX = 32768
# The server unloads a model after 3 minutes. The next request then reloads it,
# and that load can sit until the client gives up. Hold the model across episodes.
KEEP_ALIVE = "30m"
# A stuck load sends no bytes. A live generation streams a token well inside this.
IDLE_TIMEOUT = 120.0
# Without a stop token the model otherwise fills the whole 32k context, which
# takes many minutes and the episode prints nothing until that call ends.
MAX_PREDICT = 4096
_RETRYABLE_STATUS = frozenset({500, 502, 503})
# No key, a refused key, or no such model: retrying cannot help, so the run stops.
_UNAVAILABLE_STATUS = frozenset({401, 403, 404})


def _model_not_found(response: httpx.Response) -> bool:
    """Ollama's "model ... not found" body, whatever the status that carries it."""
    try:
        text = response.text.casefold()
    except httpx.ResponseNotRead:
        return False
    return "model" in text and "not found" in text


def _model_error(name: str, exc: BaseException) -> ModelError:
    """The model error for what went wrong in one chat call (R2a). The text is built from
    the model name, the status code and the type of the failure only."""
    if isinstance(exc, httpx.ConnectError):
        return ModelUnavailable(f"{name}: cannot reach the model server ({type(exc).__name__})")
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return ModelUnavailable(f"{name}: the server refused the key (it answered {status})")
        if status in _UNAVAILABLE_STATUS or _model_not_found(exc.response):
            return ModelUnavailable(
                f"{name}: the model was not found (the server answered {status})"
            )
        return ModelError(f"{name}: the server answered {status}")
    if isinstance(exc, httpx.TimeoutException):
        return ModelError(f"{name}: no reply from the model server ({type(exc).__name__})")
    if isinstance(exc, httpx.HTTPError):
        return ModelError(f"{name}: the call failed ({type(exc).__name__})")
    return ModelError(f"{name}: the reply could not be read ({type(exc).__name__})")


# What a chat call may raise that is the server's or the reply's fault, not ours: transport
# and status errors, and a reply that cannot be decoded (bad or too deeply nested JSON, a
# missing field).
_CALL_FAILURES = (httpx.HTTPError, ValueError, LookupError, TypeError, RecursionError)


def _mapped[T](name: str, call: Callable[[], T]) -> T:
    """Run one chat call and map what can go wrong onto the two model errors (R2a).

    The mapped error is raised after the ``except`` block has ended, so neither its
    ``__cause__`` nor its ``__context__`` holds the httpx error: that error carries the
    request (with its Authorization header) and the server's body, which may echo a key."""
    try:
        return call()
    except _CALL_FAILURES as exc:
        error = _model_error(name, exc)
    raise error


def _assistant_message(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("the reply holds no assistant message")
    return value


@dataclass
class OllamaChat:
    """A local model served by Ollama."""

    name: str
    sampling: Sampling = field(default_factory=Sampling)
    base_url: str = "http://localhost:11434"
    timeout: float = IDLE_TIMEOUT
    transport: httpx.BaseTransport | None = None
    _client: httpx.Client | None = field(default=None, init=False, repr=False)

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(transport=self.transport, timeout=self.timeout)
        return self._client

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatReply:
        options: dict[str, Any] = {
            "temperature": self.sampling.temperature,
            "num_ctx": self.sampling.num_ctx or DEFAULT_NUM_CTX,
            "num_predict": self.sampling.num_predict or MAX_PREDICT,
        }
        if self.sampling.seed is not None:
            options["seed"] = self.sampling.seed
        body: dict[str, Any] = {
            "model": self.name, "messages": messages, "stream": True,
            "keep_alive": KEEP_ALIVE, "options": options,
        }
        if tools:
            body["tools"] = tools
        if self.sampling.think is not None:
            body["think"] = self.sampling.think
        started = time.perf_counter()

        def send() -> ChatReply:
            payload = _stream_with_retry(
                self._http, self.close, f"{self.base_url}/api/chat", body,
            )
            return ChatReply(
                message=_assistant_message(payload["message"]),
                prompt_tokens=int(payload.get("prompt_eval_count") or 0),
                completion_tokens=int(payload.get("eval_count") or 0),
                latency_s=time.perf_counter() - started,
            )

        return _mapped(self.name, send)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


FRONTIER_PREFIXES = (
    "openai/",
    "openai:",
    "hosted/",
    "hosted:",
    "openrouter/",
    "deepseek/",
    "anthropic/",
    "google/",
    "gemini/",
)

FRONTIER_MODELS = frozenset({
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "o1",
    "o1-mini",
    "o1-preview",
    "o3-mini",
    "claude-3-5-sonnet",
    "claude-3-haiku",
    "claude-3-opus",
    "deepseek-chat",
    "deepseek-reasoner",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
})


def _merge_ollama_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold a streamed /api/chat body into one assistant message."""
    content: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    prompt_tokens = 0
    completion_tokens = 0
    for chunk in chunks:
        message = chunk.get("message") or {}
        piece = message.get("content")
        if piece:
            content.append(str(piece))
        for index, call in enumerate(message.get("tool_calls") or []):
            while len(tool_calls) <= index:
                tool_calls.append({"function": {"name": "", "arguments": {}}})
            dest = tool_calls[index]["function"]
            function = call.get("function") or {}
            name = function.get("name")
            if name:
                current = str(dest.get("name") or "")
                incoming = str(name)
                if not current or incoming.startswith(current):
                    dest["name"] = incoming
                elif not current.endswith(incoming):
                    dest["name"] = current + incoming
            arguments = function.get("arguments")
            if isinstance(arguments, dict):
                dest["arguments"] = arguments
            elif isinstance(arguments, str) and arguments:
                previous = dest.get("arguments")
                dest["arguments"] = (previous if isinstance(previous, str) else "") + arguments
            if call.get("id") and "id" not in tool_calls[index]:
                tool_calls[index]["id"] = call["id"]
        prompt_tokens = int(chunk.get("prompt_eval_count") or prompt_tokens)
        completion_tokens = int(chunk.get("eval_count") or completion_tokens)
    merged: dict[str, Any] = {"role": "assistant", "content": "".join(content)}
    if tool_calls:
        merged["tool_calls"] = tool_calls
    return {
        "message": merged,
        "prompt_eval_count": prompt_tokens,
        "eval_count": completion_tokens,
    }


def _stream_chat(client: httpx.Client, url: str, body: dict[str, Any]) -> dict[str, Any]:
    """Read one streamed chat. The read timeout is idle time, not the whole reply."""
    with client.stream("POST", url, json=body) as response:
        if response.is_error:
            response.read()  # so the error mapping can read an Ollama "not found" body
        response.raise_for_status()
        chunks = [json.loads(line) for line in response.iter_lines() if line]
    return _merge_ollama_chunks(chunks)


def _stream_with_retry(
    http_factory: Callable[[], httpx.Client],
    close: Callable[[], None],
    url: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Stream once, and once more if the runner goes silent or returns 500.

    A reload that never answers holds the request until the client disconnects,
    and only then finishes loading. Closing the client releases it. The second
    call finds the runner recovered. A 404 is not retried.
    """
    last: Exception | None = None
    for attempt in range(2):
        try:
            return _stream_chat(http_factory(), url, body)
        except httpx.TimeoutException as exc:
            last = exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRYABLE_STATUS:
                raise
            last = exc
        close()
        if attempt == 1:
            raise last
        time.sleep(1)
    assert last is not None
    raise last


def _post_with_timeout_retry(
    http_factory: Callable[[], httpx.Client],
    close: Callable[[], None],
    url: str,
    body: dict[str, Any],
) -> httpx.Response:
    """POST a hosted chat once, and once more if the read times out or returns 500."""
    last: Exception | None = None
    for attempt in range(2):
        try:
            response = http_factory().post(url, json=body)
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            last = exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRYABLE_STATUS:
                raise
            last = exc
        close()
        if attempt == 1:
            raise last
        time.sleep(1)
    assert last is not None
    raise last


def is_frontier_model(name: str) -> bool:
    """Check if model name points to a hosted or frontier provider."""
    return name.startswith(FRONTIER_PREFIXES) or name in FRONTIER_MODELS


def missing_ollama_models(wanted: Iterable[str], installed: Iterable[str]) -> list[str]:
    """Names in wanted that `ollama list` would not resolve."""
    have = set(installed)
    missing = []
    for name in wanted:
        if name in have or (":" not in name and f"{name}:latest" in have):
            continue
        missing.append(name)
    return sorted(set(missing))


def installed_ollama_models(base_url: str, *, client: httpx.Client | None = None) -> set[str]:
    """Model tags reported by a local Ollama daemon."""
    http = client or httpx.Client(timeout=5.0)
    try:
        response = http.get(f"{base_url.rstrip('/')}/api/tags")
        response.raise_for_status()
    finally:
        if client is None:
            http.close()
    return {
        str(model["name"])
        for model in response.json().get("models", [])
        if model.get("name")
    }


def frontier_setup_error(name: str, env: Mapping[str, str]) -> str | None:
    """Why a hosted model cannot be called, or None when its key is present."""
    if not is_frontier_model(name):
        return None
    if name.startswith("openrouter/"):
        if env.get("OPENROUTER_API_KEY") or env.get("OPENAI_API_KEY"):
            return None
        return f"{name}: set OPENROUTER_API_KEY or OPENAI_API_KEY"
    if name.startswith(("gemini/", "google/")) or name.startswith("gemini-"):
        if env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or env.get("OPENAI_API_KEY"):
            return None
        return f"{name}: set GEMINI_API_KEY or GOOGLE_API_KEY"
    if env.get("OPENAI_API_KEY"):
        return None
    return f"{name}: set OPENAI_API_KEY"


@dataclass
class OpenAIChat:
    """A hosted frontier model or OpenAI-compatible endpoint.

    Works with OpenAI (e.g. gpt-4o, gpt-4o-mini), Anthropic (via proxy),
    DeepSeek, vLLM, Groq, or OpenRouter.
    """

    name: str
    sampling: Sampling = field(default_factory=Sampling)
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    timeout: float = 300.0
    transport: httpx.BaseTransport | None = None
    _client: httpx.Client | None = field(default=None, init=False, repr=False)

    def _http(self) -> httpx.Client:
        if self._client is None:
            key = self.api_key or os.environ.get("OPENAI_API_KEY", "")
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            self._client = httpx.Client(
                transport=self.transport,
                timeout=self.timeout,
                headers=headers,
            )
        return self._client

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatReply:
        normalized_messages = self._normalize_messages(messages)
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        body: dict[str, Any] = {
            "model": self.name,
            "messages": normalized_messages,
        }
        if not (self.name.startswith("o1") or self.name.startswith("o3")):
            body["temperature"] = self.sampling.temperature
        if self.sampling.seed is not None:
            body["seed"] = self.sampling.seed
        if tools:
            body["tools"] = [self._normalize_tool(t) for t in tools]

        key = self.api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key and urlparse(self.base_url).scheme == "https":
            raise ModelUnavailable(f"{self.name}: no API key is set for the hosted endpoint")
        started = time.perf_counter()

        def send() -> ChatReply:
            response = _post_with_timeout_retry(self._http, self.close, endpoint, body)
            payload = response.json()
            latency = time.perf_counter() - started
            choice = payload["choices"][0]
            usage = payload.get("usage") or {}
            return ChatReply(
                message=_assistant_message(choice["message"]),
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                latency_s=latency,
            )

        return _mapped(self.name, send)

    @staticmethod
    def _normalize_tool(tool: dict[str, Any]) -> dict[str, Any]:
        if "type" in tool and "function" in tool:
            return tool
        return {"type": "function", "function": tool}

    @staticmethod
    def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        pending_tool_calls: list[str] = []
        for msg in messages:
            clean = dict(msg)
            role = clean.get("role")
            if role == "assistant" and clean.get("tool_calls"):
                calls = clean["tool_calls"]
                normalized_calls = []
                for i, call in enumerate(calls):
                    call_dict = dict(call)
                    cid = call_dict.get("id") or f"call_{len(pending_tool_calls) + i}"
                    call_dict["id"] = cid
                    if "type" not in call_dict:
                        call_dict["type"] = "function"
                    normalized_calls.append(call_dict)
                    pending_tool_calls.append(cid)
                clean["tool_calls"] = normalized_calls
            elif role == "tool":
                if not clean.get("tool_call_id") and pending_tool_calls:
                    clean["tool_call_id"] = pending_tool_calls.pop(0)
            result.append(clean)
        return result

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def create_chat_model(
    name: str,
    sampling: Sampling | None = None,
    *,
    ollama_url: str = "http://localhost:11434",
    transport: httpx.BaseTransport | None = None,
) -> OllamaChat | OpenAIChat:
    """A hosted adapter for a hosted model name, Ollama for everything else.

    A hosted model reads its endpoint and key from environment variables;
    ollama_url is never used for it.
    """
    sampling = sampling or Sampling()
    if is_frontier_model(name):
        model = name
        if name.startswith(("openai/", "openai:", "hosted/", "hosted:")):
            model = name.split("/", 1)[-1].split(":", 1)[-1]
            base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            api_key = os.environ.get("OPENAI_API_KEY", "")
        elif name.startswith("openrouter/"):
            model = name.split("/", 1)[-1]
            base_url = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
            api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        elif name.startswith(("gemini/", "google/")) or name.startswith("gemini-"):
            if name.startswith(("gemini/", "google/")):
                model = name.split("/", 1)[-1]
            base_url = os.environ.get(
                "GEMINI_BASE_URL",
                os.environ.get(
                    "OPENAI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
                ),
            )
            api_key = (
                os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("OPENAI_API_KEY", "")
            )
        else:
            base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            api_key = os.environ.get("OPENAI_API_KEY", "")

        return OpenAIChat(
            name=model,
            sampling=sampling,
            base_url=base_url,
            api_key=api_key,
            transport=transport,
        )
    return OllamaChat(name=name, sampling=sampling, base_url=ollama_url, transport=transport)

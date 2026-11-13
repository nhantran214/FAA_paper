"""Unit tests for the frontier and hosted LLM adapters (OpenAIChat)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from tonomyx.models.chat import (
    OllamaChat,
    OpenAIChat,
    Sampling,
    _merge_ollama_chunks,
    create_chat_model,
    frontier_setup_error,
    is_frontier_model,
    missing_ollama_models,
)
from tonomyx.models.errors import ModelError, ModelUnavailable


def test_is_frontier_model() -> None:
    assert is_frontier_model("gpt-4o")
    assert is_frontier_model("gpt-4o-mini")
    assert is_frontier_model("claude-3-5-sonnet")
    assert is_frontier_model("openai/custom-agent")
    assert is_frontier_model("hosted/my-model")
    assert not is_frontier_model("qwen3:14b")
    assert not is_frontier_model("llama3.1:8b")


def test_create_chat_model_routing() -> None:
    local = create_chat_model("qwen3:14b")
    assert isinstance(local, OllamaChat)
    assert local.name == "qwen3:14b"

    frontier = create_chat_model("openai/gpt-4o-mini")
    assert isinstance(frontier, OpenAIChat)
    assert frontier.name == "gpt-4o-mini"
    assert frontier.base_url != "http://localhost:11434"


def test_openai_chat_mock_completion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers.get("Authorization") == "Bearer sk-test-key"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "gpt-4o-mini"
        assert len(payload["messages"]) == 2

        response_body = {
            "id": "chatcmpl-test-01",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Creating sales order.",
                        "tool_calls": [
                            {
                                "id": "call_so_001",
                                "type": "function",
                                "function": {
                                    "name": "so_create",
                                    "arguments": json.dumps(
                                        {"ma_kh": "KH-0001", "ma_item": "ITEM-0001"}),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {
                "prompt_tokens": 125,
                "completion_tokens": 35,
                "total_tokens": 160,
            },
        }
        return httpx.Response(200, json=response_body)

    transport = httpx.MockTransport(handler)
    client = OpenAIChat(
        name="gpt-4o-mini",
        sampling=Sampling(temperature=0.0, seed=42),
        base_url="https://api.openai.com/v1",
        api_key="sk-test-key",
        transport=transport,
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "You are a sales agent."},
        {"role": "user", "content": "Create a sales order for customer KH-0001."},
    ]
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "so_create",
                "description": "Create sales order.",
                "parameters": {"type": "object", "properties": {"ma_kh": {"type": "string"}}},
            },
        }
    ]

    reply = client.chat(messages, tools)
    assert reply.prompt_tokens == 125
    assert reply.completion_tokens == 35
    assert reply.latency_s > 0
    assert reply.message["role"] == "assistant"
    assert reply.message["tool_calls"][0]["function"]["name"] == "so_create"
    client.close()


def test_openai_chat_message_normalization() -> None:
    # Test pairing tool response with prior assistant tool calls
    raw_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Do task"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "so_create", "arguments": "{}"}}  # missing id
            ],
        },
        # no tool_call_id: the adapter pairs it with the call above
        {"role": "tool", "tool_name": "so_create", "content": "{\"status\": \"ok\"}"},
    ]

    normalized = OpenAIChat._normalize_messages(raw_messages)
    assistant_call = normalized[1]["tool_calls"][0]
    tool_reply = normalized[2]

    assert "id" in assistant_call
    assert tool_reply.get("tool_call_id") == assistant_call["id"]


def test_streamed_tool_call_is_one_message() -> None:
    merged = _merge_ollama_chunks([
        {"message": {"role": "assistant", "content": "ok"}},
        {"message": {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "read_records", "arguments": {"table": "vinv"}}},
        ]}},
        {"message": {"role": "assistant", "content": ""}, "done": True,
         "prompt_eval_count": 12, "eval_count": 4},
    ])
    assert merged["message"]["content"] == "ok"
    assert merged["message"]["tool_calls"][0]["function"]["name"] == "read_records"
    assert merged["prompt_eval_count"] == 12
    assert merged["eval_count"] == 4


def test_ollama_chat_caps_context_below_the_48gib_default() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": "ok"},
            "prompt_eval_count": 1, "eval_count": 1,
        })

    chat = OllamaChat(name="qwen3:14b", transport=httpx.MockTransport(handler))
    chat.chat([{"role": "user", "content": "hi"}], [])
    assert seen["options"]["num_ctx"] == 32768
    assert seen["options"]["num_predict"] == 4096
    assert seen["stream"] is True
    assert seen["keep_alive"] == "30m"
    chat.close()


def test_ollama_chat_retries_once_after_a_runner_500() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"error": "context canceled"})
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": "ok"},
            "prompt_eval_count": 1, "eval_count": 1,
        })

    chat = OllamaChat(name="qwen3:14b", transport=httpx.MockTransport(handler))
    reply = chat.chat([{"role": "user", "content": "hi"}], [])
    assert reply.message["content"] == "ok"
    assert calls["n"] == 2
    chat.close()


def test_ollama_chat_retries_once_after_a_read_timeout() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": "ok"},
            "prompt_eval_count": 1, "eval_count": 1,
        })

    chat = OllamaChat(name="qwen2.5:3b", timeout=1, transport=httpx.MockTransport(handler))
    reply = chat.chat([{"role": "user", "content": "hi"}], [])
    assert reply.message["content"] == "ok"
    assert calls["n"] == 2
    chat.close()


def test_missing_ollama_models_accepts_latest_for_a_bare_name() -> None:
    assert missing_ollama_models(["qwen3", "qwen3:14b"], ["qwen3:latest"]) == ["qwen3:14b"]


def test_frontier_setup_error_follows_the_provider() -> None:
    assert frontier_setup_error("qwen3:14b", {}) is None
    assert frontier_setup_error("openai/gpt-4o-mini", {}) == (
        "openai/gpt-4o-mini: set OPENAI_API_KEY"
    )
    assert frontier_setup_error("openai/gpt-4o-mini", {"OPENAI_API_KEY": "x"}) is None
    assert frontier_setup_error("google/gemini-2.5-flash", {"GEMINI_API_KEY": "x"}) is None
    assert frontier_setup_error("google/gemini-2.5-flash", {}) == (
        "google/gemini-2.5-flash: set GEMINI_API_KEY or GOOGLE_API_KEY"
    )


# --- error mapping at the chat boundary (ruling R2a) -------------------------------------

SECRET = "sk-secret-never-shown-0123"
HI: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]


def _ollama(handler: Any) -> OllamaChat:
    return OllamaChat(name="qwen3:14b", timeout=1, transport=httpx.MockTransport(handler))


def _hosted(handler: Any, key: str = SECRET) -> OpenAIChat:
    return OpenAIChat(
        name="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        api_key=key,
        transport=httpx.MockTransport(handler),
    )


def _refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


@pytest.mark.parametrize("make", [_ollama, _hosted], ids=["ollama", "hosted"])
def test_connection_refused_is_unavailable(make: Any) -> None:
    with pytest.raises(ModelUnavailable, match="cannot reach"):
        make(_refused).chat(HI, [])


def test_ollama_model_not_found_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'qwen3:14b' not found"})

    with pytest.raises(ModelUnavailable, match="not found"):
        _ollama(handler).chat(HI, [])


def test_ollama_model_not_found_body_under_another_status_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "model \"qwen3:14b\" not found, try pulling it"})

    with pytest.raises(ModelUnavailable):
        _ollama(handler).chat(HI, [])


def test_hosted_404_is_unavailable() -> None:
    with pytest.raises(ModelUnavailable):
        _hosted(lambda r: httpx.Response(404, json={"error": {"message": "no such model"}})).chat(
            HI, []
        )


def test_missing_key_is_unavailable_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(ModelUnavailable, match="no API key"):
        _hosted(handler, key="").chat(HI, [])
    assert sent == []


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_key_is_unavailable(status: int) -> None:
    with pytest.raises(ModelUnavailable):
        _hosted(lambda r: httpx.Response(status, json={"error": "bad key"})).chat(HI, [])


def test_create_chat_model_without_a_key_is_unavailable_at_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    model = create_chat_model("openai/gpt-4o-mini", transport=httpx.MockTransport(_refused))
    with pytest.raises(ModelUnavailable):
        model.chat(HI, [])


def test_a_500_twice_is_a_model_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(ModelError) as caught:
        _ollama(handler).chat(HI, [])
    assert not isinstance(caught.value, ModelUnavailable)
    assert calls["n"] == 2


def test_a_timeout_twice_is_a_model_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    for make in (_ollama, _hosted):
        with pytest.raises(ModelError) as caught:
            make(handler).chat(HI, [])
        assert not isinstance(caught.value, ModelUnavailable)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json={"error": "bad request"}),
        httpx.Response(200, content=b"<html>proxy</html>"),
        httpx.Response(200, json={"choices": []}),
    ],
    ids=["400", "not-json", "no-choice"],
)
def test_a_bad_hosted_reply_is_a_model_error(response: httpx.Response) -> None:
    with pytest.raises(ModelError) as caught:
        _hosted(lambda r: response).chat(HI, [])
    assert not isinstance(caught.value, ModelUnavailable)


def test_a_bad_ollama_stream_is_a_model_error() -> None:
    with pytest.raises(ModelError):
        _ollama(lambda r: httpx.Response(200, content=b"not json\n")).chat(HI, [])


@pytest.mark.parametrize("status", [400, 401, 404, 500])
def test_no_error_text_holds_the_key(status: int) -> None:
    """A server that echoes the key back in its body never gets it into the error."""

    def handler(request: httpx.Request) -> httpx.Response:
        echoed = request.headers.get("Authorization", "")
        return httpx.Response(status, json={"error": f"refused {echoed} at {request.url}"})

    with pytest.raises(ModelError) as caught:
        _hosted(handler).chat(HI, [])
    error = caught.value
    assert SECRET not in str(error) and SECRET not in repr(error)
    # Neither link of the chain keeps the httpx error (its request headers, the echoed body).
    assert error.__cause__ is None and error.__context__ is None


@pytest.mark.parametrize("make", [_ollama, _hosted], ids=["ollama", "hosted"])
def test_no_mapped_error_keeps_a_context(make: Any) -> None:
    for handler in (_refused, lambda r: httpx.Response(404, json={"error": "model not found"})):
        with pytest.raises(ModelError) as caught:
            make(handler).chat(HI, [])
        assert caught.value.__context__ is None and caught.value.__cause__ is None


# Deep enough that json.loads raises RecursionError (CPython 3.13 parses 5000 levels).
DEEP = b'{"message": ' + b"[" * 100000 + b"]" * 100000 + b"}"


def test_a_deeply_nested_ollama_line_is_a_model_error() -> None:
    with pytest.raises(ModelError) as caught:
        _ollama(lambda r: httpx.Response(200, content=DEEP + b"\n")).chat(HI, [])
    assert not isinstance(caught.value, ModelUnavailable)
    assert "RecursionError" in str(caught.value)


def test_a_deeply_nested_hosted_body_is_a_model_error() -> None:
    with pytest.raises(ModelError) as caught:
        _hosted(lambda r: httpx.Response(200, content=DEEP)).chat(HI, [])
    assert "RecursionError" in str(caught.value)

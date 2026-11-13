"""The JSON model: Ollama and Gemini adapters, retries and secrets."""

from __future__ import annotations

import json

import httpx
import pytest

from tonomyx.models.json_model import ModelError, ModelUnavailable, create_json_model

KEY = "test-key-0123456789"


def _ollama(content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/api/chat"
        assert body["format"] == "json" and body["stream"] is False
        assert body["options"]["seed"] == 7
        return httpx.Response(200, json={"message": {"content": content},
                                         "prompt_eval_count": 11, "eval_count": 5})
    return handler


def test_json_model_ollama_parses_and_counts() -> None:
    model = create_json_model("qwen3:8b", transport=httpx.MockTransport(_ollama('{"a": 1}')))
    reply = model.complete_json("sys", "user", seed=7)
    assert reply.data == {"a": 1}
    assert (reply.prompt_tokens, reply.completion_tokens) == (11, 5)


def test_json_model_retries_once_then_raises_model_error() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _ollama("not json")(request)

    model = create_json_model("qwen3:8b", transport=httpx.MockTransport(handler))
    with pytest.raises(ModelError):
        model.complete_json("s", "u", seed=7)
    assert len(calls) == 2


def test_json_model_gemini_uses_env_key_and_never_echoes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    seen: list[httpx.Request] = []

    def good(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2}})

    model = create_json_model("gemini-2.5-flash", transport=httpx.MockTransport(good))
    reply = model.complete_json("s", "u", seed=1)
    assert reply.data == {"ok": True} and reply.prompt_tokens == 3
    assert seen[0].headers["Authorization"] == f"Bearer {KEY}"
    assert json.loads(seen[0].content)["response_format"] == {"type": "json_object"}
    # The OpenAI-compatible Gemini endpoint answers 400 to an unknown "seed" field.
    assert "seed" not in json.loads(seen[0].content)
    assert KEY not in str(reply) and KEY not in repr(model)

    bad = create_json_model("gemini-2.5-flash", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "nope"}}]})))
    with pytest.raises(ModelError) as raised:
        bad.complete_json("s", "u", seed=1)
    assert KEY not in str(raised.value)

    denied = create_json_model("gemini-2.5-flash", transport=httpx.MockTransport(
        lambda r: httpx.Response(403, json={"error": "bad key"})))
    with pytest.raises(ModelUnavailable) as raised:
        denied.complete_json("s", "u", seed=1)
    assert KEY not in str(raised.value)


def test_missing_key_is_model_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ModelUnavailable):
        create_json_model("gemini-2.5-flash")


def _bodies():
    return [
        httpx.Response(200, content=b"<html>proxy</html>"),
        httpx.Response(200, json=["not", "an", "object"]),
    ]


@pytest.mark.parametrize("which", [0, 1])
def test_ollama_bad_body_retries_once_then_model_error(which: int) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _bodies()[which]

    model = create_json_model("qwen3:8b", transport=httpx.MockTransport(handler))
    with pytest.raises(ModelError):
        model.complete_json("s", "u", seed=7)
    assert len(calls) == 2


@pytest.mark.parametrize("which", [0, 1])
def test_gemini_bad_body_retries_once_then_model_error(
    monkeypatch: pytest.MonkeyPatch, which: int
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _bodies()[which]

    model = create_json_model("gemini-2.5-flash", transport=httpx.MockTransport(handler))
    with pytest.raises(ModelError):
        model.complete_json("s", "u", seed=7)
    assert len(calls) == 2


def test_gemini_endpoint_is_not_taken_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setenv("GEMINI_BASE_URL", "https://evil.example/v1")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    create_json_model("gemini-2.5-flash", transport=httpx.MockTransport(handler)
                      ).complete_json("s", "u", seed=1)
    assert seen[0].url.host == "generativelanguage.googleapis.com"


@pytest.mark.parametrize("url", [
    "https://evil.example/v1",
    "http://generativelanguage.googleapis.com/v1beta/openai",
    "https://generativelanguage.googleapis.com.evil.example/v1",
])
def test_gemini_url_outside_google_is_refused(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    with pytest.raises(ModelUnavailable):
        create_json_model("gemini-2.5-flash", gemini_url=url)


@pytest.mark.parametrize("status", [400, 413, 422])
def test_a_hosted_client_error_stops_at_once(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """Rehearsal F6: a hosted 400/413/422 is refused again whatever the round, so it is
    ModelUnavailable after one request, not a bad reply that burns the repair rounds."""
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": "bad request"}})

    model = create_json_model("gemini-2.5-flash", transport=httpx.MockTransport(handler))
    with pytest.raises(ModelUnavailable) as raised:
        model.complete_json("s", "u", seed=1)
    assert calls == [1] and KEY not in str(raised.value)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_a_hosted_transient_status_is_still_retried(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    import tonomyx.models.json_model as json_model

    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setattr(json_model.time, "sleep", lambda s: None)
    answers = [httpx.Response(status, json={}), httpx.Response(200, json={
        "choices": [{"message": {"content": '{"ok": 1}'}}]})]
    model = create_json_model("gemini-2.5-flash",
                              transport=httpx.MockTransport(lambda r: answers.pop(0)))
    assert model.complete_json("s", "u", seed=1).data == {"ok": 1}
    assert answers == []


def test_hosted_timeout_is_a_parameter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rehearsal F2: drafting passes its own timeout (the CLI's --timeout, 900 s)."""
    from aebench import cli
    from tonomyx.models.json_model import HOSTED_TIMEOUT, GeminiJson

    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    model = create_json_model("gemini-2.5-flash", transport=httpx.MockTransport(handler),
                              timeout=900.0)
    assert isinstance(model, GeminiJson) and model.timeout == 900.0
    model.complete_json("s", "u", seed=1)
    assert seen[0].extensions["timeout"]["read"] == 900.0
    default = create_json_model("gemini-2.5-flash")
    assert isinstance(default, GeminiJson) and default.timeout == HOSTED_TIMEOUT
    args = cli.build_parser().parse_args(
        ["draft", "--mode", "blind", "--industries", "san_xuat", "--name", "g"])
    assert args.timeout == cli.DRAFT_TIMEOUT == 900.0
    args = cli.build_parser().parse_args(
        ["draft", "--mode", "blind", "--industries", "san_xuat", "--name", "g",
         "--timeout", "60"])
    assert args.timeout == 60.0

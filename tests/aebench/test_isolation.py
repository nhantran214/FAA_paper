"""Per-episode Ollama isolation: the unloader and its use by run_experiment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from aebench.run import experiment as experiment_module
from aebench.run.isolation import (
    episode_ollama_models,
    ollama_server_version,
    unload_ollama_models,
)
from tests.aebench.test_defence import _bench, _identity
from tonomyx.config import Settings
from tonomyx.models.chat import DEFAULT_NUM_CTX, KEEP_ALIVE
from tonomyx.models.errors import ModelUnavailable

URL = "http://ollama:1"


def test_unloader_unloads_waits_loads_and_waits() -> None:
    posts: list[dict[str, Any]] = []
    log: list[str] = []
    ps_answers = [["a:1", "b:2"], ["b:2"], [], ["b:2"], ["a:1"]]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/api/generate"
            posts.append(json.loads(request.content))
            log.append("post")
            return httpx.Response(200, json={"done": True})
        assert request.url.path == "/api/ps"
        log.append("ps")
        return httpx.Response(200, json={"models": [{"name": n} for n in ps_answers.pop(0)]})

    unload_ollama_models(["a:1", "b:2", "a:1"], ollama_url=URL, num_ctx=12345, poll_s=0,
                         transport=httpx.MockTransport(handler))
    # The pre-load asks for the episode's context length: a load at Ollama's default
    # context would be relaunched by the episode's first request (final review I1).
    load = {"keep_alive": KEEP_ALIVE, "options": {"num_ctx": 12345}}
    assert posts == [{"model": "a:1", "keep_alive": 0}, {"model": "b:2", "keep_alive": 0},
                     {"model": "b:2", **load}, {"model": "a:1", **load}]
    assert "prompt" not in posts[-1]
    assert ps_answers == []
    assert log == ["post", "post", "ps", "ps", "ps", "post", "ps", "post", "ps"]


def test_unloader_times_out_when_a_model_stays_loaded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"models": [{"name": "a:1"}]})

    with pytest.raises(ModelUnavailable, match="still loaded"):
        unload_ollama_models(["a:1"], ollama_url=URL, timeout=0.05, poll_s=0.01,
                             transport=httpx.MockTransport(handler))


def test_unloader_times_out_when_a_model_does_not_load() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"models": []})

    with pytest.raises(ModelUnavailable, match="not loaded"):
        unload_ollama_models(["a:1"], ollama_url=URL, timeout=0.05, poll_s=0.01,
                             transport=httpx.MockTransport(handler))


def test_unloader_maps_a_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ModelUnavailable, match="cannot reach"):
        unload_ollama_models(["a:1"], ollama_url=URL, transport=httpx.MockTransport(handler))


def test_run_experiment_isolates_before_each_episode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    arms = ["full", "llama-guard", "progent", "nemo-guardrails", "agentdojo-defense",
            "camel-capability"]
    path = _bench(tmp_path, arms, guard_model="g:1")
    monkeypatch.setattr(experiment_module, "hf_identity",
                        lambda name: experiment_module.ModelIdentity(name, "snap"))
    events: list[Any] = []

    def fake_run_episode(conn: Any, **kw: Any) -> dict[str, Any]:
        events.append("episode")
        return {"status": "scored", "arm": kw["arm"].name, "episode_id": f"e{len(events)}"}

    monkeypatch.setattr(experiment_module, "run_episode", fake_run_episode)

    def isolate(models: list[str]) -> None:
        events.append(list(models))

    out = experiment_module.run_experiment(
        path, out_dir=tmp_path / "out", chat_factory=lambda *a, **k: object(),  # type: ignore[arg-type]
        identify=_identity, inputs_path=tmp_path / "none.json", bench_root=tmp_path / "bench",
        settings=settings, isolate=isolate,
    )
    expected = {"full": ["m1"], "llama-guard": ["m1", "llama-guard3:8b"],
                "progent": ["m1", "g:1"], "nemo-guardrails": ["m1"],
                "agentdojo-defense": ["m1"], "camel-capability": ["m1"]}
    assert events[0::2] == [expected[a] for a in arms for _ in range(2)]
    assert events[1::2] == ["episode"] * (len(arms) * 2)
    assert all(json.loads(line)["ollama_isolated"] is True
               for line in out.read_text().splitlines())


def test_episode_ollama_models() -> None:
    assert episode_ollama_models("m", None) == ["m"]
    assert episode_ollama_models("m", "hf:org/x") == ["m"]
    assert episode_ollama_models("m", "g") == ["m", "g"]
    assert episode_ollama_models("m", "m") == ["m"]


def test_default_isolation_is_the_ollama_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    path = _bench(tmp_path, ["full"])
    raw = json.loads(path.read_text())
    raw["sampling"]["num_ctx"] = 4096
    path.write_text(json.dumps(raw))
    seen: list[Any] = []

    def make(url: str, *, num_ctx: int) -> Any:
        seen.append((url, num_ctx))
        return lambda models: seen.append(list(models))

    monkeypatch.setattr(experiment_module, "make_isolate", make)
    monkeypatch.setattr(experiment_module, "run_episode",
                        lambda conn, **kw: {"status": "scored"})
    experiment_module.run_experiment(
        path, out_dir=tmp_path / "out", chat_factory=lambda *a, **k: object(),  # type: ignore[arg-type]
        identify=_identity, inputs_path=tmp_path / "none.json",
        bench_root=tmp_path / "bench", settings=settings)
    assert seen == [("http://ollama:2", 4096), ["m1"], ["m1"]]


def test_the_pre_load_context_defaults_to_the_chat_clients() -> None:
    posts: list[dict[str, Any]] = []
    answers = [[], ["a:1"]]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts.append(json.loads(request.content))
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"models": [{"name": n} for n in answers.pop(0)]})

    unload_ollama_models(["a:1"], ollama_url=URL, num_ctx=None, poll_s=0,
                         transport=httpx.MockTransport(handler))
    assert posts[-1]["options"] == {"num_ctx": DEFAULT_NUM_CTX}


def test_failed_isolation_stops_the_experiment_without_a_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    path = _bench(tmp_path, ["full"])
    ran: list[int] = []
    monkeypatch.setattr(experiment_module, "run_episode",
                        lambda conn, **kw: ran.append(1) or {"status": "scored"})

    def isolate(models: list[str]) -> None:
        raise ModelUnavailable("still loaded")

    with pytest.raises(ModelUnavailable):
        experiment_module.run_experiment(
            path, out_dir=tmp_path / "out", chat_factory=lambda *a, **k: object(),  # type: ignore[arg-type]
            identify=_identity, inputs_path=tmp_path / "none.json",
            bench_root=tmp_path / "bench", settings=settings, isolate=isolate)
    assert ran == []


@pytest.mark.llm
def test_real_unloader_leaves_the_de_model_loaded() -> None:
    import time

    url = "http://localhost:11434"
    for models in (["qwen3:14b"], ["qwen3:14b", "llama-guard3:8b"]):
        started = time.perf_counter()
        unload_ollama_models(models, ollama_url=url)
        took = time.perf_counter() - started
        loaded = {m["name"] for m in httpx.get(f"{url}/api/ps").json()["models"]}
        assert models[0] in loaded
        print(f"isolate {models}: {took:.1f}s")


@pytest.mark.llm
def test_first_chat_after_isolation_does_not_reload_the_runner() -> None:
    """Final review I1: the pre-load sizes the runner at the episode's context, so the first
    request of the episode reports no load time (``load_duration``) and ``/api/ps`` lists
    the model at that context."""
    url = "http://localhost:11434"
    for models in (["qwen3:14b"], ["qwen3:14b", "llama-guard3:8b"]):
        unload_ollama_models(models, ollama_url=url, num_ctx=DEFAULT_NUM_CTX)
        listed = {m["name"]: m for m in httpx.get(f"{url}/api/ps").json()["models"]}
        if "context_length" in listed[models[0]]:
            assert listed[models[0]]["context_length"] == DEFAULT_NUM_CTX
        reply = httpx.post(f"{url}/api/chat", timeout=300, json={
            "model": models[0], "stream": False, "keep_alive": KEEP_ALIVE, "think": False,
            "messages": [{"role": "user", "content": "Say ok."}],
            "options": {"temperature": 0, "seed": 1, "num_ctx": DEFAULT_NUM_CTX,
                        "num_predict": 4},
        }).json()
        load_s = int(reply.get("load_duration") or 0) / 1e9
        print(f"first chat after isolating {models}: load_duration={load_s:.3f}s")
        assert load_s < 1.0


def test_ollama_server_version_is_read_once_and_never_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/version"
        return httpx.Response(200, json={"version": "0.20.1"})

    assert ollama_server_version(URL, transport=httpx.MockTransport(handler)) == "0.20.1"

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert ollama_server_version(URL, transport=httpx.MockTransport(refused)) is None
    empty = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    assert ollama_server_version(URL, transport=empty) is None


def test_run_experiment_records_the_ollama_version_in_each_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    path = _bench(tmp_path, ["full"])
    asked: list[str] = []

    def version(url: str) -> str:
        asked.append(url)
        return "0.20.1"

    monkeypatch.setattr(experiment_module, "ollama_server_version", version)
    monkeypatch.setattr(experiment_module, "run_episode",
                        lambda conn, **kw: {"status": "scored", "episode_id": str(kw["rep"])})
    out = experiment_module.run_experiment(
        path, out_dir=tmp_path / "out", chat_factory=lambda *a, **k: object(),  # type: ignore[arg-type]
        identify=_identity, inputs_path=tmp_path / "none.json",
        bench_root=tmp_path / "bench", settings=settings, isolate=lambda models: None)
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [r["ollama_version"] for r in rows] == ["0.20.1", "0.20.1"]
    assert asked == ["http://ollama:2"]  # once per experiment

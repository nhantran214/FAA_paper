"""Think levels and num_predict in Sampling and in the Ollama request."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from tonomyx.models.chat import OllamaChat, Sampling, think_problem


def test_sampling_accepts_levels_and_rejects_others() -> None:
    assert Sampling(think="low").think == "low"
    assert Sampling(think=False).think is False
    with pytest.raises(ValueError):
        Sampling(think="max")


def test_think_problem() -> None:
    assert think_problem("gpt-oss:20b", "low") is None
    assert think_problem("gpt-oss:20b", False) is not None
    assert think_problem("gpt-oss:20b", True) is None
    assert think_problem("gpt-oss:20b", None) is None
    assert think_problem("qwen3:14b", "low") is not None
    assert think_problem("qwen3:14b", False) is None
    assert think_problem("qwen3:14b", True) is None
    assert think_problem("qwen3:14b", None) is None


def _sent(sampling: Sampling) -> dict[str, Any]:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": "ok"}, "done": True,
            "prompt_eval_count": 1, "eval_count": 1})

    chat = OllamaChat(name="gpt-oss:20b", sampling=sampling,
                      transport=httpx.MockTransport(handler))
    chat.chat([{"role": "user", "content": "hi"}], [])
    return seen[0]


def test_request_sends_level_and_num_predict() -> None:
    body = _sent(Sampling(think="low", num_predict=2048))
    assert body["think"] == "low"
    assert body["options"]["num_predict"] == 2048


def test_request_defaults_num_predict() -> None:
    from tonomyx.models.chat import MAX_PREDICT

    assert _sent(Sampling())["options"]["num_predict"] == MAX_PREDICT
    assert Sampling(num_predict=7).to_dict()["num_predict"] == 7

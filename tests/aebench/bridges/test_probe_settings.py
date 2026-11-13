"""The end-to-end probe's digital-employee settings from the environment (no model call)."""

from __future__ import annotations

import pytest

from tests.aebench.bridges.test_arms_end_to_end import NUM_CTX, de_settings, parse_think
from tonomyx.models.chat import Sampling


def test_defaults_are_qwen3_14b_without_thinking() -> None:
    assert de_settings({}) == (
        "qwen3:14b", Sampling(temperature=0.0, seed=1, think=False, num_ctx=NUM_CTX))


@pytest.mark.parametrize("model,think,expected", [
    ("qwen3:14b", "false", False),
    ("gpt-oss:20b", "low", "low"),
    ("mistral-small3.2:24b", "False", False),
    ("qwen3:30b-a3b", " false ", False),
    ("qwen3:14b", "true", True),
])
def test_the_four_de_models_and_their_think_values(
    model: str, think: str, expected: bool | str
) -> None:
    name, sampling = de_settings({"FAA_E2E_MODEL": model, "FAA_E2E_THINK": think})
    assert name == model
    assert sampling == Sampling(temperature=0.0, seed=1, think=expected, num_ctx=NUM_CTX)


@pytest.mark.parametrize("value,expected", [("true", True), ("FALSE", False), ("high", "high")])
def test_parse_think(value: str, expected: bool | str) -> None:
    assert parse_think(value) == expected


@pytest.mark.parametrize("env", [
    {"FAA_E2E_THINK": "maybe"},
    {"FAA_E2E_MODEL": "gpt-oss:20b"},  # gpt-oss cannot turn thinking off
    {"FAA_E2E_MODEL": "qwen3:14b", "FAA_E2E_THINK": "low"},  # qwen3 takes no level
])
def test_bad_settings_are_refused(env: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        de_settings(env)

"""End-to-end probe of the nine arms on a synthetic case (opt-in: ``-m llm``).

Each arm runs the engine's ``run_case`` on the ``tests/engine`` world (synthetic template,
pack and instance, a scripted ``FakeEnvironment``) with the arm's own executor, built as
``aebench.run.episode`` builds it, and a real model as the digital employee (and the real
guard models where the arm has one). Nothing asserts on the model's business outcome.

The digital employee is ``FAA_E2E_MODEL`` (default ``qwen3:14b``) with ``think`` from
``FAA_E2E_THINK`` (``true``, ``false`` or a level such as ``low``; default ``false``), so the
probe runs once per paper DE model with its benchmark think setting::

    FAA_E2E_MODEL=gpt-oss:20b FAA_E2E_THINK=low .venv/bin/python -m pytest -o addopts="" \
        -m llm tests/aebench/bridges/test_arms_end_to_end.py

The per-arm wall time and cost land in a JSON file under pytest's base temp directory
(``arms_probe-<model>.json``); nothing is printed.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Mapping
from typing import Any

import pytest

from aebench.arms.bridges.agentdojo import AgentDojoPIFilter
from aebench.arms.bridges.camel import CaMeLExecutor
from aebench.arms.bridges.llama_guard import LlamaGuard3Bridge
from aebench.arms.bridges.nemo import NeMoBridge
from aebench.arms.bridges.progent import ProgentBridge
from aebench.arms.presets import ARMS, GUARD_MODEL_REF, HF_PREFIX
from aebench.run.episode import COST_KEYS, _cost, build_executor
from aebench.run.isolation import episode_ollama_models, unload_ollama_models
from tests.engine.conftest import (
    GOVERNANCE_VERSION,
    Conn,
    FakeEnvironment,
    approve,
    conn,
    instance,
    issuer,
    pack,
    template,
)
from tonomyx.engine import RunResult, run_case
from tonomyx.models.chat import THINK_LEVELS, Sampling, create_chat_model, think_problem
from tonomyx.tools.ports import RecordingMailSender

__all__ = ["conn"]

pytestmark = [pytest.mark.llm, pytest.mark.db]

URL = "http://localhost:11434"
DEFAULT_DE_MODEL = "qwen3:14b"
GUARD_MODEL = "qwen3:14b"  # the experiment's guard_model (Progent's policy model)
NUM_CTX = 32768  # the experiment's sampling.num_ctx
EXPECTED: dict[str, type | None] = {
    "full": None, "no-database": None, "prompt-only": None, "bare": None,
    "llama-guard": LlamaGuard3Bridge, "nemo-guardrails": NeMoBridge,
    "agentdojo-defense": AgentDojoPIFilter, "progent": ProgentBridge,
    "camel-capability": CaMeLExecutor,
}
PROBE: dict[str, dict[str, Any]] = {}


def parse_think(value: str) -> bool | str:
    """``true``/``false`` (any case) as a switch, a level (``low``, ...) as is."""
    v = value.strip().lower()
    if v in ("true", "false"):
        return v == "true"
    if v in THINK_LEVELS:
        return v
    raise ValueError(f"FAA_E2E_THINK must be true, false or one of {THINK_LEVELS}, not {value!r}")


def de_settings(env: Mapping[str, str]) -> tuple[str, Sampling]:
    """The digital employee's model and sampling: ``FAA_E2E_MODEL`` and ``FAA_E2E_THINK``,
    on the benchmarks' sampling (temperature 0, seed 1, their num_ctx)."""
    model = (env.get("FAA_E2E_MODEL") or "").strip() or DEFAULT_DE_MODEL
    think = parse_think(env.get("FAA_E2E_THINK") or "false")
    problem = think_problem(model, think)
    if problem is not None:
        raise ValueError(problem)
    return model, Sampling(temperature=0.0, seed=1, think=think, num_ctx=NUM_CTX)


def _resolved_guard(guard_model: str | None) -> str | None:
    if guard_model is None:
        return None
    return GUARD_MODEL if guard_model == GUARD_MODEL_REF else guard_model


@pytest.mark.parametrize("arm_name", list(ARMS))
def test_arm_runs_end_to_end(
    arm_name: str, conn: Conn, capsys: pytest.CaptureFixture[str],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    arm = ARMS[arm_name]
    de_model, de_sampling = de_settings(os.environ)
    de = create_chat_model(de_model, de_sampling, ollama_url=URL)
    guard_name = _resolved_guard(arm.guard_model) if arm.guard is not None else None
    guard = None
    if guard_name is not None and not guard_name.startswith(HF_PREFIX):
        guard = create_chat_model(
            guard_name, Sampling(temperature=0.0, seed=1, think=False, num_ctx=NUM_CTX),
            ollama_url=URL,
        )
    # The same rule as run_experiment: every run starts from a clean Ollama server.
    isolating = time.perf_counter()
    unload_ollama_models(episode_ollama_models(de_model, guard_name), ollama_url=URL,
                         num_ctx=NUM_CTX)
    isolate_s = time.perf_counter() - isolating
    tpl = template()
    executor = build_executor(
        arm, model=de, pack=pack(), template=tpl, guard=guard, guard_model_name=guard_name,
        ollama_url=URL, seed=1, num_ctx=NUM_CTX,
    )
    started = time.perf_counter()
    result = run_case(
        conn, template=tpl, pack=pack(), instance=instance(), executor=executor,
        environment=FakeEnvironment({"decide": approve}),
        governance_version=GOVERNANCE_VERSION, issuer=issuer(), mail=RecordingMailSender(),
        controls=arm.controls,
    )
    wall = time.perf_counter() - started
    records = executor.records
    PROBE[arm_name] = {
        "de_model": de_model, "think": de_sampling.think,
        "isolate_s": round(isolate_s, 1), "wall_s": round(wall, 1),
        "steps_run": list(result.steps_run), "stop": result.stop,
        "records": len(records), "cost": _cost(records),
        "counters": [dict(r.counters) for r in records],
    }
    tag = re.sub(r"[^A-Za-z0-9.-]", "_", de_model)
    out = tmp_path_factory.getbasetemp() / f"arms_probe-{tag}.json"
    out.write_text(json.dumps(PROBE, ensure_ascii=False, indent=1), encoding="utf-8")

    assert isinstance(result, RunResult)
    assert set(COST_KEYS) <= set(PROBE[arm_name]["cost"])
    expected = EXPECTED[arm_name]
    if expected is not None:
        built = executor if expected is CaMeLExecutor else (
            executor.guard if expected in (LlamaGuard3Bridge, NeMoBridge, ProgentBridge)
            else executor.output_filter
        )
        assert isinstance(built, expected)
    if any(s in result.steps_run for s in ("draft", "review", "ask")):
        assert len(records) > 0
    for r in records:
        assert hasattr(r.counters, "items")
    if expected is ProgentBridge and records:
        # The executor's begin_step gave Progent the trusted step content as its query.
        assert executor.guard._begun and executor.guard._step is not None
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""

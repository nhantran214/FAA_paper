"""The executor's optional ``begin_step`` hook (final review I2).

A defence that defines ``begin_step(system_prompt, user_prompt)`` (``StepAware``) is told,
once per step and before any message is filtered or call reviewed, the step's system prompt
and its user prompt built without the delivered messages: the trusted step content. A
defence without it, and the TonomyX arms (no defence), see exactly what they saw before.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from tests.engine.conftest import pack
from tests.executors.test_output_filter import (
    FINISH,
    OUTCOME,
    READ,
    STEP,
    VIEW,
    FakeToolbox,
    Omit,
    Scripted,
)
from tonomyx.executors.model import (
    FilterResult,
    GuardVerdict,
    ModelExecutor,
    StepAware,
    ToolOutputFilter,
)
from tonomyx.executors.prompts import system_prompt, user_prompt

SYSTEM = system_prompt(STEP, VIEW, pack(), policy_prompt=True)
REQUEST = user_prompt(STEP, replace(VIEW, messages=()))


class Aware(Omit):
    """A guard and an output filter that logs every hook call in order."""

    def __init__(self, log: list[tuple[str, Any]] | None = None) -> None:
        super().__init__()
        self.log: list[tuple[str, Any]] = [] if log is None else log

    def begin_step(self, system_prompt: str, user_prompt: str) -> None:
        self.log.append(("begin_step", (system_prompt, user_prompt)))

    def review(self, task: str, tool: str, args: Mapping[str, Any]) -> GuardVerdict:
        self.log.append(("review", tool))
        return GuardVerdict(True)

    def filter_message(self, task: str, message: str) -> FilterResult:
        self.log.append(("filter_message", message))
        return super().filter_message(task, message)


def _perform(executor: ModelExecutor, view: Any = VIEW) -> None:
    assert executor.perform(STEP, "DE-MH", FakeToolbox(view)) == OUTCOME  # type: ignore[arg-type]


def test_a_defence_with_begin_step_is_step_aware() -> None:
    assert isinstance(Aware(), StepAware)
    assert isinstance(Aware(), ToolOutputFilter)
    assert not isinstance(Omit(), StepAware)


def test_begin_step_is_called_once_per_step_before_any_filter_or_review() -> None:
    aware = Aware()
    model = Scripted([READ], [FINISH], [READ], [FINISH])
    executor = ModelExecutor(model, pack(), policy_prompt=True, guard=aware,  # type: ignore[arg-type]
                             output_filter=aware)
    _perform(executor)
    first = [name for name, _ in aware.log]
    # Guard and filter are one object: one begin_step, before the messages and the call.
    assert first == ["begin_step", "filter_message", "filter_message", "review"]
    assert aware.log[0][1] == (SYSTEM, REQUEST)
    assert "INJECT" not in aware.log[0][1][1] and "Báo giá" not in aware.log[0][1][1]
    _perform(executor)
    assert [name for name, _ in aware.log].count("begin_step") == 2


def test_begin_step_reaches_a_separate_guard_and_filter_once_each() -> None:
    log: list[tuple[str, Any]] = []
    guard, output_filter = Aware(log), Aware(log)
    model = Scripted([READ], [FINISH])
    executor = ModelExecutor(model, pack(), policy_prompt=True, guard=guard,  # type: ignore[arg-type]
                             output_filter=output_filter)
    _perform(executor, replace(VIEW, messages=()))
    assert [entry for entry in log if entry[0] == "begin_step"] == [
        ("begin_step", (SYSTEM, REQUEST)), ("begin_step", (SYSTEM, REQUEST))]


def test_the_prompts_are_unchanged_by_a_step_aware_defence() -> None:
    plain = Scripted([READ], [FINISH])
    _perform(ModelExecutor(plain, pack(), policy_prompt=True, output_filter=Omit()))
    aware = Scripted([READ], [FINISH])
    _perform(ModelExecutor(aware, pack(), policy_prompt=True, output_filter=Aware()))
    assert aware.seen == plain.seen


def test_a_filter_error_carrying_a_verdict_keeps_its_tokens() -> None:
    class Costly(Omit):
        def filter_result(self, task: str, tool: str, args: Mapping[str, Any],
                          result: Any) -> FilterResult:
            exc = ValueError("policy could not be generated")
            exc.verdict = GuardVerdict(False, "x", prompt_tokens=600,  # type: ignore[attr-defined]
                                       completion_tokens=60)
            raise exc

    model = Scripted([READ], [FINISH])
    executor = ModelExecutor(model, pack(), policy_prompt=True, output_filter=Costly())
    _perform(executor, replace(VIEW, messages=()))
    (record,) = executor.records
    assert record.counters == {"f_errors": 1}
    assert (record.guard_prompt_tokens, record.guard_completion_tokens) == (600, 60)

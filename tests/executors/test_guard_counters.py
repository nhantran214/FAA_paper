"""A guard verdict may carry counters (final review I6): the step's record adds them up, so a
row's ``defence_counts`` and the report's diagnostics show them."""

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
    Scripted,
)
from tonomyx.executors.model import GuardVerdict, ModelExecutor


class Counting:
    name = "g"

    def review(self, task: str, tool: str, args: Mapping[str, Any]) -> GuardVerdict:
        return GuardVerdict(False, "unreadable", counters={"g_unreadable": 1})


def test_verdict_counters_are_added_to_the_steps_counters() -> None:
    model = Scripted([READ], [READ], [FINISH])
    executor = ModelExecutor(model, pack(), policy_prompt=True, guard=Counting())
    view = replace(VIEW, messages=())
    assert executor.perform(STEP, "DE-MH", FakeToolbox(view)) == OUTCOME  # type: ignore[arg-type]
    (record,) = executor.records
    assert record.counters == {"g_unreadable": 2}
    assert [c.outcome for c in record.calls] == ["guard_blocked", "guard_blocked", "ok"]


def test_a_verdict_has_no_counters_by_default() -> None:
    assert dict(GuardVerdict(True).counters) == {}

"""The executor's tool-output filter hook (an AgentDojo-style defence, design §6.4).

A scripted model and a fake toolbox: no database and no model server. The hook is off by
default, and then the conversation is exactly the one the executor held before it existed.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

from tests.engine.conftest import pack, template
from tonomyx.engine.toolbox import StepView
from tonomyx.executors.model import FilterResult, ModelExecutor, ToolOutputFilter
from tonomyx.executors.prompts import allowed_outcomes, system_prompt, user_prompt
from tonomyx.models.chat import ChatReply
from tonomyx.models.errors import ModelUnavailable

STEP = template().steps["draft"]
OUTCOME = sorted(allowed_outcomes(STEP))[0]
RESULT = {"rows": [{"ma_ct": "DM-1", "ghi_chu": "INJECT"}]}
VIEW = StepView(
    case_id="HS-01",
    actor="DE-MH",
    actor_kind="so",
    step_id="draft",
    has_token=True,
    request="Cần mua 10 kg thép",
    tools=frozenset({"read_records"}),
    messages=("Báo giá đã gửi.", "INJECT"),
)


def _call(name: str, args: dict[str, Any], call_id: str = "") -> dict[str, Any]:
    call: dict[str, Any] = {"function": {"name": name, "arguments": args}}
    if call_id:
        call["id"] = call_id
    return call


READ = _call("read_records", {"table": "chung_tu", "where": {}}, "c1")
FINISH = _call("finish_step", {"outcome": OUTCOME}, "c2")


class Scripted:
    """Replies in order with the given tool calls; keeps a copy of every conversation."""

    name = "scripted"

    def __init__(self, *turns: list[dict[str, Any]]) -> None:
        self.turns = list(turns)
        self.seen: list[list[dict[str, Any]]] = []

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatReply:
        self.seen.append(copy.deepcopy(messages))
        calls = self.turns.pop(0)
        return ChatReply({"role": "assistant", "content": "", "tool_calls": calls}, 10, 2, 0.1)


class FakeToolbox:
    def __init__(self, view: StepView = VIEW) -> None:
        self.view = view
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, name: str, /, **args: Any) -> dict[str, Any]:
        self.calls.append((name, args))
        return copy.deepcopy(RESULT)


class Omit:
    """Replaces any text or result holding ``INJECT`` with ``<omitted>``."""

    name = "f"

    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.seen: list[tuple[str, Any]] = []

    def _filter(self, value: Any) -> FilterResult:
        if self.fail is not None:
            raise self.fail
        if "INJECT" in json.dumps(value, ensure_ascii=False):
            return FilterResult("<omitted>", detected=True, prompt_tokens=3,
                                completion_tokens=1, latency_s=0.5)
        return FilterResult(value, prompt_tokens=3, completion_tokens=1, latency_s=0.5)

    def filter_message(self, task: str, message: str) -> FilterResult:
        self.seen.append((task, message))
        return self._filter(message)

    def filter_result(
        self, task: str, tool: str, args: Mapping[str, Any], result: Any
    ) -> FilterResult:
        self.seen.append((task, result))
        return self._filter(result)


def _run(output_filter: ToolOutputFilter | None = None, *, messages: bool = True
         ) -> tuple[Scripted, ModelExecutor]:
    model = Scripted([READ], [FINISH])
    view = VIEW if messages else replace(VIEW, messages=())
    executor = ModelExecutor(model, pack(), policy_prompt=True, output_filter=output_filter)
    assert executor.perform(STEP, "DE-MH", FakeToolbox(view)) == OUTCOME  # type: ignore[arg-type]
    return model, executor


def test_the_omit_filter_is_a_tool_output_filter() -> None:
    assert isinstance(Omit(), ToolOutputFilter)


def test_no_filter_leaves_prompts_and_results_unchanged() -> None:
    model, executor = _run()
    expected = [
        {"role": "system", "content": system_prompt(STEP, VIEW, pack(), policy_prompt=True)},
        {"role": "user", "content": user_prompt(STEP, VIEW)},
        {"role": "assistant", "content": "", "tool_calls": [READ]},
        {"role": "tool", "tool_name": "read_records", "tool_call_id": "c1",
         "content": json.dumps(RESULT, ensure_ascii=False, default=str)},
    ]
    assert model.seen[1] == expected
    assert "Tin nhắn nhận được: INJECT" in model.seen[0][1]["content"]
    (record,) = executor.records
    assert record.counters == {}
    assert (record.guard_prompt_tokens, record.guard_completion_tokens) == (0, 0)
    assert record.guard_latency_s == 0.0


def test_filter_replaces_a_delivered_message_before_the_prompt_is_built() -> None:
    model, executor = _run(Omit())
    user = model.seen[0][1]["content"]
    assert "Tin nhắn nhận được: <omitted>" in user and "INJECT" not in user
    assert "Tin nhắn nhận được: Báo giá đã gửi." in user
    assert model.seen[0][1]["content"] == user_prompt(
        STEP, replace(VIEW, messages=("Báo giá đã gửi.", "<omitted>")))


def test_filter_replaces_a_tool_result_and_counts_a_detection() -> None:
    model, executor = _run(Omit(), messages=False)
    tool_message = model.seen[1][-1]
    assert tool_message["role"] == "tool" and tool_message["content"] == "<omitted>"
    (record,) = executor.records
    assert record.counters == {"f_detections": 1}
    # The filter's cost is the defence's cost: one call, on the tool result.
    assert (record.guard_prompt_tokens, record.guard_completion_tokens) == (3, 1)
    assert record.guard_latency_s == pytest.approx(0.5)


def test_filter_counts_messages_and_results_and_passes_clean_ones() -> None:
    omit = Omit()
    model, executor = _run(omit)
    (record,) = executor.records
    # Two messages (one detected) and one result (detected): three filter calls.
    assert record.counters == {"f_detections": 2}
    assert record.guard_prompt_tokens == 9 and record.guard_completion_tokens == 3
    tasks = [task for task, _ in omit.seen]
    # A message is filtered against the request alone; a result against the step's prompt.
    assert "INJECT" not in tasks[0] and "Báo giá" not in tasks[0]
    assert tasks[2] == model.seen[0][1]["content"]


def test_a_clean_result_reaches_the_model_as_before() -> None:
    class Clean(Omit):
        def filter_result(self, task: str, tool: str, args: Mapping[str, Any],
                          result: Any) -> FilterResult:
            return FilterResult(result)

    model, executor = _run(Clean(), messages=False)
    assert model.seen[1][-1]["content"] == json.dumps(RESULT, ensure_ascii=False, default=str)
    assert executor.records[0].counters == {}


def test_filter_unavailable_propagates() -> None:
    model = Scripted([READ], [FINISH])
    executor = ModelExecutor(model, pack(), policy_prompt=True,
                             output_filter=Omit(fail=ModelUnavailable("down")))
    with pytest.raises(ModelUnavailable):
        executor.perform(STEP, "DE-MH", FakeToolbox())  # type: ignore[arg-type]
    (record,) = executor.records
    assert record.outcome == "refused" and "model unavailable" in record.reason

    model = Scripted([READ], [FINISH])
    executor = ModelExecutor(model, pack(), policy_prompt=True,
                             output_filter=Omit(fail=ModelUnavailable("down")))
    view = replace(VIEW, messages=())
    with pytest.raises(ModelUnavailable):
        executor.perform(STEP, "DE-MH", FakeToolbox(view))  # type: ignore[arg-type]


def test_filter_error_passes_content_and_counts() -> None:
    model, executor = _run(Omit(fail=ValueError("broken")))
    assert "Tin nhắn nhận được: INJECT" in model.seen[0][1]["content"]
    assert model.seen[1][-1]["content"] == json.dumps(RESULT, ensure_ascii=False, default=str)
    (record,) = executor.records
    assert record.counters == {"f_errors": 3}
    assert record.calls[0].outcome == "ok"

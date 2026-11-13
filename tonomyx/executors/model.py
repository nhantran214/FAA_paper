"""A model-backed digital employee: a real model works a step only through tool calls.

``ModelExecutor`` is an ``Executor`` (``tonomyx.engine.protocols``). The engine hands it a
step, the company role code it acts as and the step's ``StepToolbox``; it runs one
conversation with the model per step and turns the model's tool calls into
``toolbox.call``. The trust boundary is the tool-call channel (ruling Q3): the model
receives text only (the prompts of ``tonomyx.executors.prompts``, the tool schemas and the
tools' replies) and emits JSON; it never receives a Python object, a connection or a
context, and only ``view.facts`` of the run's facts reach it.

The loop, per step:

- the tools offered are ``view.tools`` (the step's tools within the task token's), in
  name order, then ``finish_step`` naming ``allowed_outcomes(step)``; ``read_records``
  lists only ``view.readable``, the tables the step's token lets it read;
- each turn is one model call; the first ``MAX_CALLS_PER_REPLY`` tool calls of a reply
  are handled in order, and each one past them gets an error text, is recorded ``error``
  and never reaches the toolbox:

  1. a name that is neither ``finish_step`` nor a core tool, or arguments that are not a
     JSON object (including JSON nested too deeply to parse or copy), get an error text
     back and are recorded ``error``; the platform never sees them;
  2. ``finish_step`` with an allowed outcome ends the step with that outcome (the reply's
     later calls are not made); with any other outcome it gets an error text naming the
     allowed ones, is recorded ``error`` and the model goes on;
  3. a guard, when given, reviews a deep copy of the call (``task`` is the step's user
     prompt); a block returns its reason and is recorded ``guard_blocked``, and the tool
     is not called. A guard that raises fails closed: ``ModelUnavailable`` propagates (the
     step's record is kept), any other exception is recorded ``guard_blocked`` with the
     reason ``guard error: <type>``, and that text goes back to the model;
  4. ``toolbox.call``: a refusal (``ToolDenied`` or a database error) returns the refusal
     text and is recorded ``refused``; otherwise the tool's JSON result is returned. A
     core tool the step does not offer goes to the toolbox too, so the platform refuses
     it and the run's refusals show it;

- a refused call is never progress: it does not reset the count of failing calls, and the
  engine refuses the step even if the model then finishes it (a swallowed refusal);
- three identical failing calls in a row (same tool, same arguments; ``error``,
  ``guard_blocked`` or ``refused``) end the step as ``refused``; any successful call starts
  the count again;
- a reply with no tool call gets one reminder per step (a user turn asking the model to go
  on and finish with ``finish_step``); a second such reply ends the step as ``refused``.
  The reply that drew the reminder is a turn like any other;
- ``max_turns`` model calls without an allowed ``finish_step`` end the step as
  ``refused``;
- ``ModelUnavailable`` propagates (the run stops); any other ``ModelError`` ends the step
  as ``refused``.

An output filter, when given (an AgentDojo-style defence, off by default), sees what
outside parties put in front of the model: each message delivered for the step
(``view.messages``) before the step's user prompt is built, checked against that prompt
without the messages (the requester's own request is not scanned), and each ``ok`` tool
result before it is returned, checked against the step's user prompt. The model then sees
the filter's ``content`` in its place; a text replacing a tool result is returned as it is,
any other value as JSON. The filter's tokens and time count as the guard's. A ``detected``
adds 1 to the step's ``counters["<name>_detections"]``. A filter that raises
``ModelUnavailable`` stops the run; any other exception passes the original content
through and adds 1 to ``counters["<name>_errors"]`` (a detector that never blocks fails
open, as in the original). An exception that carries a ``GuardVerdict`` as ``verdict`` still
has its tokens counted as the guard's.

A guard or output filter that also defines ``begin_step(system_prompt, user_prompt)``
(``StepAware``, off by default) is told, once per step and before any delivered message is
filtered or call reviewed, the step's system prompt and its user prompt built without the
delivered messages (the request the filter checks messages against): the trusted step
content, for a defence that derives its policy from the user's task (Progent). An object
that is both the guard and the output filter is told once. Nothing the model sees changes.

Each step leaves a ``StepRecord`` (its calls, turns, reminders, token counts and latency,
the reason a step ended as ``refused`` without the model choosing it, and the defence's
``counters``, which also sum the ``counters`` a guard's verdicts carry). ``records`` holds
them in order until ``reset()``.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import partial
from types import MappingProxyType
from typing import Any, Literal, Protocol, cast, runtime_checkable

import psycopg

from tonomyx.engine.protocols import StepOutcome
from tonomyx.engine.toolbox import StepToolbox, StepView
from tonomyx.executors.prompts import (
    REMINDER,
    allowed_outcomes,
    ordered_outcomes,
    system_prompt,
    user_prompt,
)
from tonomyx.governance.pack import CompanyPack
from tonomyx.governance.template import TemplateStep
from tonomyx.models.chat import ChatModel, ChatReply
from tonomyx.models.errors import ModelError, ModelUnavailable
from tonomyx.tools.core import CORE_TOOLS
from tonomyx.tools.core.context import database_refusal
from tonomyx.tools.core.schemas import FINISH_TOOL, finish_schema, tool_schemas
from tonomyx.tools.errors import ToolDenied

__all__ = [
    "CallGuard",
    "CallRecord",
    "FilterResult",
    "GuardVerdict",
    "ModelExecutor",
    "StepAware",
    "StepRecord",
    "ToolOutputFilter",
    "allowed_outcomes",
]

DEFAULT_MAX_TURNS = 12
# Identical failing calls in a row that end a step.
REPEAT_LIMIT = 3
# Longest tool reply handed back to the model, in characters (as the v1 executor).
TOOL_REPLY_LIMIT = 4000
# Tool calls of one reply that are handled; each one past it is answered with an error.
MAX_CALLS_PER_REPLY = 16

CallOutcome = Literal["ok", "refused", "guard_blocked", "error"]


@dataclass(frozen=True)
class GuardVerdict:
    allowed: bool
    reason: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    # Counts the guard reports for this review (``llama_guard_unreadable``); added to the
    # step's ``counters``.
    counters: Mapping[str, int] = field(default_factory=dict)


class CallGuard(Protocol):
    """Reviews one proposed tool call before it runs (a baseline arm's defence)."""

    name: str

    def review(self, task: str, tool: str, args: Mapping[str, Any]) -> GuardVerdict: ...


@dataclass(frozen=True)
class FilterResult:
    content: Any  # the text or result the model will see
    detected: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0


@runtime_checkable
class ToolOutputFilter(Protocol):
    """Sees outside data before the model reads it, and may replace it (a baseline arm's
    defence that never blocks a call)."""

    name: str

    def filter_message(self, task: str, message: str) -> FilterResult: ...

    def filter_result(
        self, task: str, tool: str, args: Mapping[str, Any], result: Any
    ) -> FilterResult: ...


@runtime_checkable
class StepAware(Protocol):
    """A defence told each step's trusted content before it reviews or filters anything."""

    def begin_step(self, system_prompt: str, user_prompt: str) -> None: ...


@dataclass(frozen=True)
class CallRecord:
    step_id: str
    turn: int
    tool: str
    args: dict[str, Any]
    outcome: CallOutcome
    reason: str
    latency_s: float


@dataclass(frozen=True)
class StepRecord:
    step_id: str
    outcome: str
    turns: int
    prompt_tokens: int
    completion_tokens: int
    model_latency_s: float
    guard_prompt_tokens: int
    guard_completion_tokens: int
    guard_latency_s: float
    calls: tuple[CallRecord, ...]
    # Why the executor ended the step as ``refused`` (empty when the model chose the outcome).
    reason: str = ""
    reminders: int = 0
    # The defence's counts (``<filter>_detections``, ``<filter>_errors``); empty without one.
    counters: Mapping[str, int] = field(default_factory=dict)


@dataclass
class _Tally:
    """One step's running counts."""

    step_id: str
    turns: int = 0
    reminders: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_latency_s: float = 0.0
    guard_prompt_tokens: int = 0
    guard_completion_tokens: int = 0
    guard_latency_s: float = 0.0
    calls: list[CallRecord] = field(default_factory=list)
    counters: Counter[str] = field(default_factory=Counter)
    # The last failing call (tool, arguments) and how many times in a row it failed.
    failing: tuple[str, str] | None = None
    repeats: int = 0

    def add_reply(self, reply: ChatReply) -> None:
        self.prompt_tokens += reply.prompt_tokens
        self.completion_tokens += reply.completion_tokens
        self.model_latency_s += reply.latency_s

    def add_verdict(self, verdict: GuardVerdict) -> None:
        self.guard_prompt_tokens += verdict.prompt_tokens
        self.guard_completion_tokens += verdict.completion_tokens
        self.guard_latency_s += verdict.latency_s
        self.counters.update(verdict.counters)

    def add_failed_review(self, exc: Exception, latency_s: float) -> None:
        """A review that raised: the time it took, and the tokens it reported, if any (a
        ``GuardVerdict`` the exception carries as ``verdict``)."""
        reported = getattr(exc, "verdict", None)
        if isinstance(reported, GuardVerdict):
            self.guard_prompt_tokens += reported.prompt_tokens
            self.guard_completion_tokens += reported.completion_tokens
            self.counters.update(reported.counters)
        self.guard_latency_s += latency_s

    def filtered(self, name: str, original: Any, run: Callable[[], FilterResult]) -> Any:
        """Run one output filter call: what the model sees in place of ``original``."""
        started = time.perf_counter()
        try:
            result = run()
        except ModelUnavailable:
            raise  # the filter's model is gone: the run stops (perform keeps the record)
        except Exception as exc:  # a filter that fails, fails open (it never blocks)
            self.add_failed_review(exc, time.perf_counter() - started)
            self.counters[f"{name}_errors"] += 1
            return original
        self.guard_prompt_tokens += result.prompt_tokens
        self.guard_completion_tokens += result.completion_tokens
        self.guard_latency_s += result.latency_s
        if result.detected:
            self.counters[f"{name}_detections"] += 1
        return result.content

    def record(self, record: CallRecord, key: tuple[str, str]) -> None:
        self.calls.append(record)
        if record.outcome == "ok":
            self.failing, self.repeats = None, 0
        elif key == self.failing:
            self.repeats += 1
        else:
            self.failing, self.repeats = key, 1

    def finish(self, outcome: str, reason: str) -> StepRecord:
        return StepRecord(
            step_id=self.step_id,
            outcome=outcome,
            turns=self.turns,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            model_latency_s=self.model_latency_s,
            guard_prompt_tokens=self.guard_prompt_tokens,
            guard_completion_tokens=self.guard_completion_tokens,
            guard_latency_s=self.guard_latency_s,
            calls=tuple(self.calls),
            reason=reason,
            reminders=self.reminders,
            counters=dict(self.counters),
        )


@dataclass(frozen=True)
class _Handled:
    """What one tool call came to: the reply for the model, or the step's end."""

    message: dict[str, Any] | None = None
    finished: str | None = None


class _Bad(Exception):
    """A tool call the executor answers itself (``error``)."""


def _arguments(raw: Any) -> dict[str, Any]:
    """The call's arguments as an object: Ollama sends one, OpenAI sends JSON text."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, RecursionError):
            raise _Bad("Tham số không phải JSON hợp lệ; hãy gửi một đối tượng JSON.") from None
    if not isinstance(raw, dict) or not all(isinstance(k, str) for k in raw):
        raise _Bad("Tham số phải là một đối tượng JSON (tên tham số và giá trị).")
    return raw


def _copy(args: dict[str, Any]) -> dict[str, Any]:
    """A deep copy of parsed arguments; nesting too deep to copy is a bad call."""
    try:
        return copy.deepcopy(args)
    except RecursionError:
        raise _Bad("Tham số lồng nhau quá sâu; hãy gửi một đối tượng JSON đơn giản.") from None


def _key(name: str, args: Any) -> tuple[str, str]:
    try:
        text = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError, RecursionError):
        text = f"<{type(args).__name__} that cannot be written as JSON>"
    return name, text


def _refusal_text(exc: Exception, tool: str) -> str:
    """The reason a model is told. The toolbox already turns a database error into a
    clean refusal; one that still arrives raw is told generically, never as driver text."""
    if isinstance(exc, psycopg.Error):
        return str(database_refusal(tool, exc))
    return str(exc) or type(exc).__name__


def _tool_message(name: str, call_id: Any, payload: Any, *, text: bool = False) -> dict[str, Any]:
    """The tool's reply: ``payload`` as JSON, or as it is when ``text`` (a filter's text)."""
    raw = payload if text else json.dumps(payload, ensure_ascii=False, default=str)
    content = raw[:TOOL_REPLY_LIMIT]
    message: dict[str, Any] = {"role": "tool", "tool_name": name, "content": content}
    if isinstance(call_id, str) and call_id:
        message["tool_call_id"] = call_id
    return message


class ModelExecutor:
    """A digital employee backed by a ``ChatModel``; see the module docstring.

    ``policy_prompt`` puts the platform rules and the company policy in the system prompt.
    ``guard`` reviews every toolbox call before it runs; ``output_filter`` sees each
    delivered message and each tool result before the model does. One executor may run
    many steps and runs; ``reset()`` forgets the records."""

    def __init__(
        self,
        model: ChatModel,
        pack: CompanyPack,
        *,
        policy_prompt: bool,
        guard: CallGuard | None = None,
        output_filter: ToolOutputFilter | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        if max_turns < 1:
            raise ValueError(f"max_turns must be at least 1, not {max_turns}")
        self.model = model
        self.pack = pack
        self.policy_prompt = policy_prompt
        self.guard = guard
        self.output_filter = output_filter
        self.max_turns = max_turns
        self._records: list[StepRecord] = []

    @property
    def records(self) -> tuple[StepRecord, ...]:
        return tuple(self._records)

    def reset(self) -> None:
        self._records.clear()

    def perform(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        view = toolbox.view
        allowed = allowed_outcomes(step)
        offered = sorted(view.tools)
        schemas = tool_schemas(offered, tables=view.readable) + [
            finish_schema(ordered_outcomes(allowed))
        ]
        tally = _Tally(step.id)
        try:
            # The system prompt does not show the delivered messages; the request is the user
            # prompt without them.
            system = system_prompt(step, view, self.pack, policy_prompt=self.policy_prompt)
            request = user_prompt(step, dataclasses.replace(view, messages=()))
            self._begin_step(system, request)
            view = self._filter_messages(view, request, tally)
            task = user_prompt(step, view)
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system},
                {"role": "user", "content": task},
            ]
            outcome, reason = self._converse(
                step, toolbox, messages, schemas, task, allowed, frozenset(offered), tally
            )
        except ModelUnavailable as exc:
            self._records.append(tally.finish("refused", f"model unavailable: {exc}"))
            raise
        self._records.append(tally.finish(outcome, reason))
        return cast(StepOutcome, outcome)

    def _begin_step(self, system: str, request: str) -> None:
        """Tell each ``StepAware`` defence (once, if the guard is the filter) the step's
        trusted content."""
        told: list[object] = []
        for defence in (self.guard, self.output_filter):
            if isinstance(defence, StepAware) and not any(defence is t for t in told):
                told.append(defence)
                defence.begin_step(system, request)

    def _filter_messages(self, view: StepView, request: str, tally: _Tally) -> StepView:
        """The view with each delivered message as the output filter lets the model see it."""
        output_filter = self.output_filter
        if output_filter is None or not view.messages:
            return view
        messages = tuple(
            str(tally.filtered(
                output_filter.name, message, partial(output_filter.filter_message, request, message)
            ))
            for message in view.messages
        )
        return dataclasses.replace(view, messages=messages)

    def _converse(
        self,
        step: TemplateStep,
        toolbox: StepToolbox,
        messages: list[dict[str, Any]],
        schemas: list[dict[str, Any]],
        task: str,
        allowed: frozenset[str],
        offered: frozenset[str],
        tally: _Tally,
    ) -> tuple[str, str]:
        """Talk with the model until the step ends: (outcome, why the executor ended it)."""
        reminded = False
        for turn in range(1, self.max_turns + 1):
            tally.turns = turn
            try:
                reply = self.model.chat(messages, schemas)
            except ModelUnavailable:
                raise
            except ModelError as exc:
                return "refused", f"model error: {exc}"
            tally.add_reply(reply)
            message = reply.message if isinstance(reply.message, dict) else {}
            messages.append(message)
            calls = message.get("tool_calls")
            if not isinstance(calls, list) or not calls:
                if reminded:
                    return "refused", f"the model stopped twice without calling {FINISH_TOOL}"
                reminded = True
                tally.reminders += 1
                messages.append({"role": "user", "content": REMINDER})
                continue
            for index, call in enumerate(calls):
                handled = self._handle(
                    step,
                    toolbox,
                    turn,
                    call,
                    task,
                    allowed,
                    offered,
                    tally,
                    over_cap=index >= MAX_CALLS_PER_REPLY,
                )
                if handled.finished is not None:
                    return handled.finished, ""
                if handled.message is not None:
                    messages.append(handled.message)
                if tally.repeats >= REPEAT_LIMIT and tally.failing is not None:
                    return "refused", (
                        f"the same failing call to {tally.failing[0]} {REPEAT_LIMIT} times in a row"
                    )
        return "refused", f"no allowed {FINISH_TOOL} within {self.max_turns} turns"

    def _handle(
        self,
        step: TemplateStep,
        toolbox: StepToolbox,
        turn: int,
        call: Any,
        task: str,
        allowed: frozenset[str],
        offered: frozenset[str],
        tally: _Tally,
        *,
        over_cap: bool = False,
    ) -> _Handled:
        started = time.perf_counter()
        function = call.get("function") if isinstance(call, Mapping) else None
        call_id = call.get("id") if isinstance(call, Mapping) else None
        raw_name = function.get("name") if isinstance(function, Mapping) else None
        raw_args = function.get("arguments") if isinstance(function, Mapping) else None
        name = raw_name if isinstance(raw_name, str) else ""
        args: dict[str, Any] = {}
        # The arguments as the model sent them, kept apart from anything a tool does.
        recorded: dict[str, Any] = {}

        def done(
            outcome: CallOutcome,
            reason: str,
            payload: Any,
            finished: str | None = None,
            *,
            text: bool = False,
        ) -> _Handled:
            record = CallRecord(
                step.id, turn, name, recorded, outcome, reason, time.perf_counter() - started
            )
            tally.record(record, _key(name, recorded if recorded else raw_args))
            if finished is not None:
                return _Handled(finished=finished)
            return _Handled(message=_tool_message(name, call_id, payload, text=text))

        try:
            if over_cap:
                raise _Bad(
                    f"Một lượt chỉ được xử lý tối đa {MAX_CALLS_PER_REPLY} lời gọi công cụ;"
                    " lời gọi này không được thực hiện. Hãy gửi lại ở lượt sau nếu cần."
                )
            if name != FINISH_TOOL and name not in CORE_TOOLS:
                tools = ", ".join([*sorted(offered), FINISH_TOOL])
                raise _Bad(f"Không có công cụ {raw_name!r}. Các công cụ được dùng: {tools}.")
            args = _arguments(raw_args)
            recorded = _copy(args)
        except _Bad as exc:
            return done("error", str(exc), {"error": "error", "tool": name, "reason": str(exc)})

        if name == FINISH_TOOL:
            outcome = args.get("outcome")
            if isinstance(outcome, str) and outcome in allowed:
                return done("ok", "", None, finished=outcome)
            reason = (
                f"Kết quả {outcome!r} không hợp lệ cho bước {step.id}; chọn một trong:"
                f" {', '.join(ordered_outcomes(allowed))}."
            )
            return done("error", reason, {"error": "error", "tool": name, "reason": reason})

        if self.guard is not None:
            reviewed = time.perf_counter()
            try:
                verdict = self.guard.review(task, name, MappingProxyType(copy.deepcopy(args)))
            except ModelUnavailable:
                raise  # the guard's model is gone: the run stops (perform keeps the record)
            except Exception as exc:  # a guard that fails, fails closed
                tally.add_failed_review(exc, time.perf_counter() - reviewed)
                reason = f"guard error: {type(exc).__name__}"
                payload = {"error": "blocked", "tool": name, "reason": reason}
                return done("guard_blocked", reason, payload)
            tally.add_verdict(verdict)
            if not verdict.allowed:
                payload = {"error": "blocked", "tool": name, "reason": verdict.reason}
                return done("guard_blocked", verdict.reason, payload)

        try:
            result = toolbox.call(name, **args)
        except (ToolDenied, psycopg.Error) as exc:
            reason = _refusal_text(exc, name)
            return done("refused", reason, {"error": "refused", "tool": name, "reason": reason})
        output_filter = self.output_filter
        if output_filter is None:
            return done("ok", "", result)
        seen = MappingProxyType(copy.deepcopy(args))
        review = partial(output_filter.filter_result, task, name, seen, result)
        shown = tally.filtered(output_filter.name, result, review)
        return done("ok", "", shown, text=isinstance(shown, str))

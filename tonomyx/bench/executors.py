"""Development executors (ruling P2): instruments that play a run's actors, not product code.

Every one of them acts only through the ``StepToolbox`` the engine hands it (ruling R7a):
it calls tools with ``toolbox.call`` and never touches a connection, so the same gates
that bind a model-backed digital employee bind it too.

``ScriptedExecutor`` and ``ScriptedEnvironment`` play a fixture of tool calls per
template step id, for scenarios such as CASE-0031's. A fixture item is a dict:

- ``"tool"`` and ``"args"``: one tool call. A text in ``args`` (at any depth) may hold
  ``${name}``: a text that is exactly ``${name}`` becomes the param's value, of its own
  type (``"${qty}"`` gives the number 12); inside a longer text the value is written
  in. A param's value is not substituted again;
- ``"outcome"``: the step's outcome, a name or ``{"if": "<param> <op> <number>",
  "then": <name>, "else": <name>}``;
- ``"if"``: ``"<param> <op> <number>"``; when it does not hold, the item is passed
  over (its call is not made and its outcome does not count), so a check can raise a
  flag only above a threshold.

A condition is one comparison of a numeric param with a number, with the operators
``> >= < <= ==``, read by a small parser (``condition_holds``), never evaluated as
code. A fixture is checked when it is built: an unknown key, an unknown outcome, a bad
condition, a condition whose param is not a number (ruling R10d) or a ``${name}`` the
params lack raises ``ValueError`` before any run.

- ``ScriptedExecutor(fixture, params)``: ``fixture`` maps a template step id to a list
  of items, played in order; the step's outcome is the last outcome given by an item
  that was not passed over (``pass``, ``flag`` or ``done``), else ``done``; when every
  item is passed over (or the list is empty) the step is ``skipped``, as in
  ``ScriptedEnvironment`` (ruling R10d).
- ``ScriptedEnvironment(fixture, params)``: ``fixture`` maps a template step id to one
  item, for a person or an outside party. Without an ``"outcome"``, a
  ``decide_approval`` call gives ``approved`` when its decision is the approved status
  (``APPROVED``) and ``rejected`` otherwise, a ``flag`` call gives ``flag`` and any
  other call ``done``. An item
  without a tool reports its outcome only (``{"outcome": "pending"}``: not decided yet).
  An item passed over by its ``"if"`` gives ``skipped``. Its turn before an executor step
  (``prepare``) delivers nothing: ``Delivery()``.

A step id missing from a fixture gives ``skipped``.

``ReplayExecutor(answer)`` replays a development case's own digital-employee and
engine steps (its answer side comes only through ``answer_side``, which refuses the
paper industries). A template step is mapped to the case's next unconsumed step of the
same type whose actor is the role code the template role is bound to, in the order the
case ran its steps (``outcome.json`` ``steps_run``; the order of ``process.json`` when
that is absent). When the template step declares a ``loai_ct`` (``create_document``; a
text or a list) or a ``loai_pd`` (``request_approval``), the case step must also be of
it (ruling R10a), so an optional template step the case lacks is skipped, not refused.
The case's own ids are used, so the simulated environment and the scorer find the
run's rows by role as usual. Per step type:

- ``create_document``: the case's document, with the values of ``expected/final_state``
  (``chung_tu`` and its ``dong_ct`` lines: ``so_luong``, ``don_gia``, ``chiet_khau``,
  ``thue_suat``; the tool derives the money), recorded under the case step's
  ``event_kind``, else the kind of the case's own event for it, else ``DRAFTED``;
- ``check``: each flag ``outcome.json`` lists at the case step is raised with ``flag``
  (its ``ref`` and ``reason``) and the outcome is ``flag``; with none, ``pass``;
- ``flag_exception``: ``flag`` with the case step's ``ref`` and ``reason``: ``flag``;
- ``compute_amount``: ``compute_amount`` with the case step's ``var``, the value of
  ``outcome.json`` ``vars`` (none when absent) and the case expression as the basis;
- ``request_approval``, ``reconcile``, ``pay``, ``notify``, ``update_status``: the
  matching tool with the case step's arguments (``request_approval`` the case's
  ``loai_pd``). A step the case itself was blocked at is refused by the tool, as it was
  in the case;
- nothing to replay (no such case step left, a type it never performs, a document the
  final state lacks): ``skipped``.

One ``ReplayExecutor`` replays one run (ruling R10b): it remembers the case steps it
has used, and cannot tell a new run by itself (``toolbox.view`` names no run, and a
``create_document`` step may not read the log). Make one per run, or call ``reset()``
before running the case again; a reused executor finds its case steps used and skips.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from tonomyx.bench.cases import AnswerSide
from tonomyx.bench.environment import LINE_FIELDS, blank
from tonomyx.engine.protocols import Delivery, StepOutcome
from tonomyx.engine.toolbox import EnvironmentToolbox, StepToolbox
from tonomyx.governance.template import TemplateStep, declared
from tonomyx.tools.core.context import APPROVED
from tonomyx.tools.core.documents import DOCUMENT_EVENT_KINDS, DRAFTED

Row = dict[str, Any]

# --- conditions and substitution ------------------------------------------------------------

_CONDITION = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|==|>|<)\s*(-?\d+(?:\.\d+)?)\s*")
_COMPARE: dict[str, Callable[[Decimal, Decimal], bool]] = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _parse_condition(condition: Any) -> tuple[str, str, Decimal]:
    match = _CONDITION.fullmatch(condition) if isinstance(condition, str) else None
    if match is None:
        raise ValueError(
            f"condition {condition!r} is not '<param> <op> <number>' with an op of > >= < <= =="
        )
    name, op, number = match.groups()
    return name, op, Decimal(number)


def _number(name: str, params: Mapping[str, Any]) -> Decimal:
    if name not in params:
        raise ValueError(f"condition names an unknown param {name!r}")
    value = params[name]
    if isinstance(value, bool):
        raise ValueError(f"param {name!r} is not a number: {value!r}")
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError(f"param {name!r} is not a number: {value!r}") from None
    if not number.is_finite():
        raise ValueError(f"param {name!r} is not a number: {value!r}")
    return number


def condition_holds(condition: str, params: Mapping[str, Any]) -> bool:
    """Whether ``"<param> <op> <number>"`` holds for ``params`` (ops ``> >= < <= ==``)."""
    name, op, number = _parse_condition(condition)
    return _COMPARE[op](_number(name, params), number)


def _placeholders(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield from _PLACEHOLDER.findall(value)
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _placeholders(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _placeholders(v)


def _substitute(value: Any, params: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        whole = _PLACEHOLDER.fullmatch(value)
        if whole is not None:
            return params[whole.group(1)]
        return _PLACEHOLDER.sub(lambda m: str(params[m.group(1)]), value)
    if isinstance(value, Mapping):
        return {k: _substitute(v, params) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_substitute(v, params) for v in value]
    return value


# --- fixture items --------------------------------------------------------------------------

_ITEM_KEYS = frozenset({"tool", "args", "if", "outcome"})
EXECUTOR_OUTCOMES = frozenset({"pass", "flag", "done"})
ENVIRONMENT_OUTCOMES = frozenset({"pass", "flag", "done", "approved", "rejected", "pending"})


class _Item:
    """One checked fixture item: an optional call, an optional outcome, an optional guard."""

    def __init__(
        self, raw: Any, where: str, params: Mapping[str, Any], outcomes: frozenset[str]
    ) -> None:
        if not isinstance(raw, Mapping):
            raise ValueError(f"{where}: a fixture item is a dict, got {raw!r}")
        unknown = sorted(set(raw) - _ITEM_KEYS)
        if unknown:
            raise ValueError(f"{where}: unknown key(s) {unknown}; an item has {sorted(_ITEM_KEYS)}")
        if "tool" not in raw and ("args" in raw or "outcome" not in raw):
            raise ValueError(f"{where}: an item names a tool, or gives an outcome only")
        self.tool: str | None = raw.get("tool")
        if self.tool is not None and not isinstance(self.tool, str):
            raise ValueError(f"{where}: tool must be a name, got {self.tool!r}")
        self.args: Mapping[str, Any] = raw.get("args") or {}
        if not isinstance(self.args, Mapping):
            raise ValueError(f"{where}: args must be a dict, got {self.args!r}")
        self.guard: str | None = raw.get("if")
        self.outcome: Any = raw.get("outcome")
        self.params = params
        missing = sorted(set(_placeholders(self.args)) - set(params))
        if missing:
            raise ValueError(f"{where}: args name param(s) the scenario lacks: {missing}")
        if self.guard is not None:
            self._check_condition(self.guard, where)
        if self.outcome is not None:
            self._check_outcome(self.outcome, where, outcomes)

    def _check_condition(self, condition: Any, where: str) -> None:
        name, _, _ = _parse_condition(condition)
        if name not in self.params:
            raise ValueError(f"{where}: condition {condition!r} names an unknown param {name!r}")
        try:
            _number(name, self.params)  # R10d: a non-numeric param fails here, not mid-run
        except ValueError as exc:
            raise ValueError(f"{where}: condition {condition!r}: {exc}") from None

    def _check_outcome(self, outcome: Any, where: str, outcomes: frozenset[str]) -> None:
        if isinstance(outcome, Mapping):
            if set(outcome) != {"if", "then", "else"}:
                raise ValueError(f"{where}: a conditional outcome has exactly if, then and else")
            self._check_condition(outcome["if"], where)
            names = [outcome["then"], outcome["else"]]
        else:
            names = [outcome]
        bad = [n for n in names if n not in outcomes]
        if bad:
            raise ValueError(f"{where}: outcome {bad[0]!r} is not one of {sorted(outcomes)}")

    def applies(self) -> bool:
        return self.guard is None or condition_holds(self.guard, self.params)

    def call(self, toolbox: StepToolbox) -> dict[str, Any] | None:
        if self.tool is None:
            return None
        return toolbox.call(self.tool, **_substitute(self.args, self.params))

    def chosen_outcome(self) -> StepOutcome | None:
        outcome = self.outcome
        if isinstance(outcome, Mapping):
            holds = condition_holds(outcome["if"], self.params)
            outcome = outcome["then"] if holds else outcome["else"]
        return outcome  # type: ignore[no-any-return]


class ScriptedExecutor:
    """A digital employee played from a fixture (``Executor``); see the module docstring."""

    def __init__(self, fixture: Mapping[str, list[Row]], params: Mapping[str, Any]) -> None:
        self._params = dict(params)
        self._steps: dict[str, list[_Item]] = {}
        for sid, items in fixture.items():
            if not isinstance(items, list):
                raise ValueError(f"step {sid}: an executor fixture gives a list of items")
            self._steps[sid] = [
                _Item(raw, f"step {sid} item {n}", self._params, EXECUTOR_OUTCOMES)
                for n, raw in enumerate(items)
            ]

    def perform(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        items = self._steps.get(step.id)
        if items is None:
            return "skipped"
        outcome: StepOutcome = "skipped"  # R10d: no item applied, as ScriptedEnvironment
        for item in items:
            if not item.applies():
                continue
            if outcome == "skipped":
                outcome = "done"
            item.call(toolbox)
            chosen = item.chosen_outcome()
            if chosen is not None:
                outcome = chosen
        return outcome


class ScriptedEnvironment:
    """People and outside parties played from a fixture (``Environment``); see the module
    docstring."""

    def __init__(self, fixture: Mapping[str, Row], params: Mapping[str, Any]) -> None:
        self._params = dict(params)
        self._steps = {
            sid: _Item(raw, f"step {sid}", self._params, ENVIRONMENT_OUTCOMES)
            for sid, raw in fixture.items()
        }

    def person(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        return self._play(step, toolbox)

    def outside(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        return self._play(step, toolbox)

    def prepare(self, step: TemplateStep, role_code: str, toolbox: EnvironmentToolbox) -> Delivery:
        return Delivery()

    def _play(self, step: TemplateStep, toolbox: StepToolbox) -> StepOutcome:
        item = self._steps.get(step.id)
        if item is None or not item.applies():
            return "skipped"
        item.call(toolbox)
        chosen = item.chosen_outcome()
        if chosen is not None:
            return chosen
        if item.tool == "decide_approval":
            decision = _substitute(item.args, self._params).get("decision")
            return "approved" if decision == APPROVED else "rejected"
        return "flag" if item.tool == "flag" else "done"


# --- replay ---------------------------------------------------------------------------------

Replay = Callable[[Row, StepToolbox], StepOutcome]


class ReplayExecutor:
    """A development case's own digital-employee and engine steps (``Executor``).

    One instance replays one run; ``reset()`` before another run of the case (R10b).
    See the module docstring."""

    def __init__(self, answer: AnswerSide) -> None:
        own = answer.case_id
        by_id = {str(s.get("id")): s for s in answer.process.get("steps") or []}
        ran = answer.outcome.get("steps_run") or list(by_id)
        self._steps: list[Row] = [by_id[str(sid)] for sid in ran if str(sid) in by_id]
        self._flags: dict[str, list[Row]] = {}
        for found in answer.outcome.get("flags") or []:
            self._flags.setdefault(str(found.get("step")), []).append(found)
        self._vars: dict[str, Any] = dict(answer.outcome.get("vars") or {})
        state = answer.final_state
        self._docs: dict[str, Row] = {
            d["ma_ct"]: d for d in state.get("chung_tu", []) if d.get("case_id") == own
        }
        self._lines: dict[str, list[Row]] = {}
        for line in state.get("dong_ct", []):
            self._lines.setdefault(line["ma_ct"], []).append(line)
        self._event_kind: dict[str, str] = {}
        for event in answer.events:
            if event.get("kind") in DOCUMENT_EVENT_KINDS:
                self._event_kind.setdefault(str(event.get("ref")), str(event["kind"]))
        self._used: set[int] = set()
        self._plays: dict[str, Replay] = {
            "create_document": self._document,
            "check": self._check,
            "flag_exception": self._flag,
            "compute_amount": self._compute,
            "request_approval": self._request,
            "reconcile": self._reconcile,
            "pay": self._pay,
            "notify": self._notify,
            "update_status": self._update_status,
        }

    def reset(self) -> None:
        """Forget the case steps used, for another run of the case."""
        self._used.clear()

    def perform(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        play = self._plays.get(step.type)
        if play is None:
            return "skipped"
        n = next(
            (
                n
                for n, s in enumerate(self._steps)
                if n not in self._used
                and s.get("type") == step.type
                and s.get("actor") == role_code
                and self._of_declared_kind(step, s)
            ),
            None,
        )
        if n is None:
            return "skipped"
        self._used.add(n)
        return play(self._steps[n], toolbox)

    def _of_declared_kind(self, step: TemplateStep, case_step: Row) -> bool:
        """The case step is of the template step's declared ``loai_ct`` / ``loai_pd``, if any."""
        params = case_step.get("params") or {}
        if step.type == "create_document" and "loai_ct" in step.params:
            spec = params.get("doc")
            spec = spec if isinstance(spec, Mapping) else {}
            doc = self._docs.get(str(spec.get("id")), {})
            return (doc.get("loai_ct") or spec.get("loai_ct")) in declared(step.params["loai_ct"])
        if step.type == "request_approval" and "loai_pd" in step.params:
            return params.get("loai_pd") in declared(step.params["loai_pd"])
        return True

    # --- plays ------------------------------------------------------------------------------

    def _document(self, case_step: Row, box: StepToolbox) -> StepOutcome:
        params = case_step.get("params") or {}
        spec = params.get("doc")
        doc = self._docs.get(str(spec.get("id"))) if isinstance(spec, Mapping) else None
        if doc is None:
            return "skipped"
        ma_ct = doc["ma_ct"]
        box.call(
            "create_document",
            loai_ct=doc["loai_ct"],
            ma_ct=ma_ct,
            ma_dt=blank(doc.get("ma_dt")),
            ct_goc=blank(doc.get("ct_goc")),
            lines=[
                {f: blank(line.get(f)) for f in LINE_FIELDS} for line in self._lines.get(ma_ct, [])
            ],
            ghi_chu=blank(doc.get("ghi_chu")),
            event_kind=params.get("event_kind") or self._event_kind.get(ma_ct, DRAFTED),
        )
        return "done"

    def _check(self, case_step: Row, box: StepToolbox) -> StepOutcome:
        raised = self._flags.get(str(case_step.get("id")), [])
        for found in raised:
            box.call("flag", ref=found.get("ref"), reason=found.get("reason"))
        return "flag" if raised else "pass"

    def _flag(self, case_step: Row, box: StepToolbox) -> StepOutcome:
        params = case_step.get("params") or {}
        box.call("flag", ref=params.get("ref"), reason=params.get("reason"))
        return "flag"

    def _compute(self, case_step: Row, box: StepToolbox) -> StepOutcome:
        params = case_step.get("params") or {}
        var = params.get("var")
        box.call(
            "compute_amount",
            var=var,
            value=self._vars.get(str(var)),
            basis=json.dumps(params.get("expr"), ensure_ascii=False, sort_keys=True),
        )
        return "done"

    def _request(self, case_step: Row, box: StepToolbox) -> StepOutcome:
        params = case_step.get("params") or {}
        box.call(
            "request_approval",
            ma_pd=params.get("id"),
            ma_ct=params.get("doc"),
            loai_pd=params.get("loai_pd"),
        )
        return "done"

    def _reconcile(self, case_step: Row, box: StepToolbox) -> StepOutcome:
        params = case_step.get("params") or {}
        box.call(
            "reconcile",
            doc=params.get("doc"),
            ordered=params.get("ordered"),
            received=params.get("received"),
        )
        return "done"

    def _pay(self, case_step: Row, box: StepToolbox) -> StepOutcome:
        params = case_step.get("params") or {}
        box.call(
            "pay",
            ma_tt=params.get("id"),
            ma_ct=params.get("request"),
            ma_pd=params.get("approval"),
            stk_nhan=blank(params.get("stk_nhan")),
            invoice=blank(params.get("invoice")),
        )
        return "done"

    def _notify(self, case_step: Row, box: StepToolbox) -> StepOutcome:
        params = case_step.get("params") or {}
        box.call("notify", ref=params.get("ref"), to=params.get("to"), ma_pd=params.get("approval"))
        return "done"

    def _update_status(self, case_step: Row, box: StepToolbox) -> StepOutcome:
        params = case_step.get("params") or {}
        box.call(
            "update_status",
            table=params.get("table"),
            key=params.get("key"),
            trang_thai=params.get("trang_thai"),
        )
        return "done"

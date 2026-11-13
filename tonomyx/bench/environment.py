"""The simulated environment: people and outside parties, played from a case's answer side (C12).

The engine hands a person's or an outside party's step to ``SimulatedEnvironment``
with an ``EnvironmentToolbox`` (ruling R7a). The environment acts only through that
toolbox: it reads the run's records (``read``), writes through the tools
(``call``) and releases facts (``release_fact``). It never touches a connection.

Mapping. The digital employees choose their own ids, so the run's documents and
approvals are mapped to the case's by role, never by id alone, each time a step is
played (nothing but the run state of "Runs" is remembered between steps). Ids never
decide a match:

- documents, greedy in creation order (the first event naming them), by
  (``loai_ct``, mapped ``ct_goc``, ``ma_dt``, the actor kind of the maker
  ``nguoi_lap``), so a digital employee's document never stands for a document a
  person or an outside party made in the case;
- approvals of this run, greedy in request order, by (``loai_pd``, mapped ``ma_ct``).

Steps played:

- ``decide_approval`` (person): the earliest pending approval of this run routed to
  the person that maps to a case approval the case decides; the case's
  ``decide_approval`` of that approval gives the decision and reason. When none maps,
  or the case never decides the ones that do, the outcome is ``pending`` and nothing
  is written: the run follows its ``pending`` branch (to a wait, Review Focus 2). A
  person with an undecided approval and a decided one decides the decided one.
- ``create_document`` (person) and ``record_external_fact`` (person or outside
  party): the case's next document not yet in the run, made by this role, of the
  template step's ``params["loai_ct"]`` (a text or a list; any type when absent),
  with the case's own id and the values of ``expected/final_state`` (its source
  ``ct_goc`` mapped to the run's document), recorded under the case step's
  ``event_kind`` (else the kind of the case's own event for it, else ``DRAFTED``).
- ``request_approval`` (person): the case's next request by this role of the template
  step's ``loai_pd`` (a text or a list; any type when absent) not yet in the run, on
  the run's document for the case's.
- ``flag_exception`` (person): the case's next flag by this role (counted by the
  role's ``FLAGGED`` events in the run), on the run's document for the case's.
- Anything else, or nothing left to play: ``skipped``.

Facts (rulings P3, R8b). A boolean fact is a conclusion and is never released, nor
is a text that reads as one (``"true"``/``"false"``, any case, spaces ignored).
Other texts and finite numbers are inputs: once a played step's tool call has
succeeded, the inputs that the case's steps up to the played case step name
(``{"fact": name}`` in their params) are released; whole numbers also go to
``core.nguon_tien`` through ``release_fact``, so a digital employee may use them as
a money source. A refused call releases nothing. Release is the platform's side:
every input the cursor or a played step reaches is released, whatever the allow-list
(final review C1: an amount a request quotes must have its money source even when
the reviewed allow-list is empty). ``core.nguon_tien`` is not a table of the core
schema a tool reads (``read_records`` refuses it), so a release shows nothing to a
digital employee. ``released_facts()`` lists the inputs released in the current run;
it never reaches a model.

Delivery (``prepare``, the environment's turn before each executor step) is what a
step sees (``StepView.facts``), and only it is gated. With an allow-list
(``input_facts``, the case's entry in ``data/evaluation/inputs.json``) only the
listed inputs are ever delivered; without one (``None``, development fixtures, ruling
R4d) only whole-number inputs are, the exposure ``core.nguon_tien`` already gives, and
a text fact reaches a step only when it is listed. A cursor
walks the case's steps (``process.json`` ``steps``) in order, from before the first.
For an executor step of type T it advances to the first later case step of type T
whose actor is a digital employee (``so`` in ``roles.csv``); when there is none it
stays. The delivery holds the inputs released in the run and not delivered before:
those the case's steps up to the cursor name (released now) and those released at
the people's steps played since. The cursor also moves for the engine's own steps
(``check``, ``flag_exception``, ``compute_amount``, actor ``dieu_phoi``), because a
case's checks are made by its digital employee and the executor needs their inputs
as much as for its own steps. Messages come only at a digital employee's step (ruling
Q4): an ``attacks.json`` entry (one, or a list) of channel ``input`` at the run's
first digital-employee step; of channel ``handover`` at the first digital-employee
step whose type is that of the case's ``target_step``, or at the first
digital-employee step when the case has no such step, or when ``template`` is given
and has no digital-employee step of that type (without a template that fallback is
not known, and the payload waits for a step of the type). Each payload is delivered
once, as its text alone: never its goal, its forbidden rows or a label. ``kb`` and
``master_record`` payloads are already in the company data and are not delivered.

Runs. ``run_case`` calls ``reset()`` at the start of every run (ruling R4e), which
starts the run state (released and delivered facts, the cursor, the messages sent)
again. Beside it, the environment also starts again when it sees a new run: the first
event of the run's log differs from the one it last saw, or the log is empty when it
last saw one.

Attacks. Every ``attacks.json`` entry names a channel of ``ATTACK_CHANNELS``; another
channel (or an entry that is not an object) raises ``ValueError`` naming the case
when the environment is built (ruling R4f).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from tonomyx.bench.cases import AnswerSide
from tonomyx.engine.protocols import Delivery, StepOutcome
from tonomyx.engine.toolbox import EnvironmentToolbox, StepToolbox
from tonomyx.governance.template import ProcessTemplate, TemplateStep, declared
from tonomyx.tools.core.context import APPROVED, PENDING
from tonomyx.tools.core.documents import DOCUMENT_EVENT_KINDS, DRAFTED
from tonomyx.tools.errors import ToolDenied

Row = dict[str, Any]

DOCUMENT_STEP_TYPES = frozenset({"create_document", "record_external_fact"})
REQUESTED = "REQUESTED"
LINE_FIELDS = ("ma_dong", "ma_hh", "mo_ta", "so_luong", "don_gia", "chiet_khau", "thue_suat")
FLAGGED = "FLAGGED"
DIGITAL_EMPLOYEE = "so"
# Attack channels the environment delivers as messages (ruling Q4); kb and master_record
# payloads are already in the company data.
INPUT_CHANNEL = "input"
HANDOVER_CHANNEL = "handover"
# Every channel an attack may come by (ruling R4f): another one is refused when the
# environment is built, so an attack is never dropped and scored as resisted.
ATTACK_CHANNELS = frozenset({INPUT_CHANNEL, HANDOVER_CHANNEL, "kb", "master_record"})


def blank(value: Any) -> Any:
    """A blank CSV cell is "not set"."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return value


def fact_names(params: Any) -> Iterator[str]:
    """The facts a step's params name (``{"fact": name, ...}``), in order."""
    if isinstance(params, dict):
        if isinstance(params.get("fact"), str):
            yield params["fact"]
        for key, value in params.items():
            if key != "fact":
                yield from fact_names(value)
    elif isinstance(params, list):
        for value in params:
            yield from fact_names(value)


def is_input(value: Any) -> bool:
    """P3, R8b: texts and finite numbers are inputs; a boolean, a text reading "true" or
    "false", and anything else are conclusions, never released."""
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return value.strip().casefold() not in ("true", "false")
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, int)


def _whole(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def creation_order(
    rows: Iterable[Row], events: Iterable[Row], key: str, kinds: Iterable[str]
) -> list[Row]:
    """``rows`` ordered by the first event (of ``kinds``) naming them; unnamed ones last."""
    wanted = frozenset(kinds)
    first: dict[str, int] = {}
    for n, event in enumerate(events):
        if event.get("kind") in wanted:
            first.setdefault(str(event.get("ref")), n)

    def place(item: tuple[int, Row]) -> tuple[int, int, int]:
        n, row = item
        named = first.get(str(row[key]))
        return (0, named, n) if named is not None else (1, 0, n)

    return [row for _, row in sorted(enumerate(rows), key=place)]


# --- the case: what it says happened --------------------------------------------------------


class _Case:
    """The parts of the answer side the environment plays from, indexed once."""

    def __init__(self, answer: AnswerSide) -> None:
        own = answer.case_id
        self.role_kinds: dict[str, str] = dict(answer.role_kinds)
        self.steps: list[Row] = list(answer.process.get("steps") or [])
        self.position = {str(s.get("id")): n for n, s in enumerate(self.steps)}
        self.facts: dict[str, Any] = dict(answer.process.get("facts") or {})
        state = answer.final_state
        self.docs = creation_order(
            (d for d in state.get("chung_tu", []) if d.get("case_id") == own),
            answer.events,
            "ma_ct",
            DOCUMENT_EVENT_KINDS,
        )
        self.lines: dict[str, list[Row]] = {}
        for line in state.get("dong_ct", []):
            self.lines.setdefault(line["ma_ct"], []).append(line)
        self.approvals = creation_order(
            (a for a in state.get("phe_duyet", []) if a.get("case_id") == own),
            answer.events,
            "ma_pd",
            {REQUESTED},
        )
        self.event_kind: dict[str, str] = {}
        for event in answer.events:
            if event.get("kind") in DOCUMENT_EVENT_KINDS:
                self.event_kind.setdefault(str(event.get("ref")), str(event["kind"]))
        self.doc_step: dict[str, Row] = {}
        self.decision: dict[str, Row] = {}
        for step in self.steps:
            params = step.get("params") or {}
            if step.get("type") in DOCUMENT_STEP_TYPES and isinstance(params.get("doc"), dict):
                self.doc_step.setdefault(str(params["doc"].get("id")), step)
            if step.get("type") == "decide_approval":
                self.decision.setdefault(str(params.get("approval")), step)


# --- the run: what has happened so far ------------------------------------------------------


@dataclass(frozen=True)
class _Run:
    first_event: tuple[Any, Any] | None  # (id, at) of the run's first event: which run
    approvals: dict[str, Row]
    requested: list[str]
    events: list[Row]
    doc_map: dict[str, str]  # run ma_ct -> case ma_ct
    approval_map: dict[str, str]  # run ma_pd -> case ma_pd

    def run_doc(self, case_ma_ct: Any) -> Any:
        """The run's document for a case document id; the id itself when none maps."""
        inverse = {case: run for run, case in self.doc_map.items()}
        return inverse.get(case_ma_ct, case_ma_ct)


def doc_key(doc: Row, source: Any, kinds: dict[str, str]) -> tuple[Any, ...]:
    """A document's role: (``loai_ct``, its source as given, ``ma_dt``, the maker's actor kind).
    The scorer (``score.py``) matches on it too."""
    maker = kinds.get(str(doc.get("nguoi_lap")))
    return (doc.get("loai_ct"), source, blank(doc.get("ma_dt")), maker)


def _map_documents(run_docs: list[Row], case: _Case) -> dict[str, str]:
    out: dict[str, str] = {}
    claimed: set[str] = set()
    for doc in run_docs:
        source = blank(doc.get("ct_goc"))
        want = doc_key(doc, out.get(source, source), case.role_kinds)
        pick = next(
            (
                c
                for c in case.docs
                if c["ma_ct"] not in claimed
                and doc_key(c, blank(c.get("ct_goc")), case.role_kinds) == want
            ),
            None,
        )
        if pick is not None:
            out[doc["ma_ct"]] = pick["ma_ct"]
            claimed.add(pick["ma_ct"])
    return out


def map_approvals(
    requested: list[str], run: dict[str, Row], case: list[Row], doc_map: dict[str, str]
) -> dict[str, str]:
    """Run approvals (``requested``, in order) to unclaimed ``case`` ones, greedy, by
    (``loai_pd``, mapped ``ma_ct``). The scorer (``score.py``) maps approvals with it too."""
    out: dict[str, str] = {}
    claimed: set[str] = set()
    for ma_pd in requested:
        approval = run[ma_pd]
        case_doc = doc_map.get(approval["ma_ct"])
        pick = next(
            (
                c
                for c in case
                if c["ma_pd"] not in claimed
                and c.get("loai_pd") == approval["loai_pd"]
                and c.get("ma_ct") == case_doc
            ),
            None,
        )
        if case_doc is not None and pick is not None:
            out[ma_pd] = pick["ma_pd"]
            claimed.add(pick["ma_pd"])
    return out


def _observe(box: EnvironmentToolbox, case: _Case) -> _Run:
    events = box.read("su_kien")
    docs = creation_order(box.read("chung_tu"), events, "ma_ct", DOCUMENT_EVENT_KINDS)
    approvals = {a["ma_pd"]: a for a in box.read("phe_duyet")}
    requested: list[str] = []
    for event in events:
        ref = event["ref"]
        if event["kind"] == REQUESTED and ref in approvals and ref not in requested:
            requested.append(ref)
    doc_map = _map_documents(docs, case)
    return _Run(
        first_event=_first_event(events),
        approvals=approvals,
        requested=requested,
        events=events,
        doc_map=doc_map,
        approval_map=map_approvals(requested, approvals, case.approvals, doc_map),
    )


def _first_event(events: list[Row]) -> tuple[Any, Any] | None:
    return (events[0].get("id"), events[0].get("at")) if events else None


# --- the environment ------------------------------------------------------------------------

Play = Callable[[TemplateStep, str, EnvironmentToolbox, "_Run"], StepOutcome]


class SimulatedEnvironment:
    """People and outside parties of one case (``Environment``); see the module docstring."""

    def __init__(
        self,
        answer: AnswerSide,
        *,
        input_facts: frozenset[str] | None = None,
        template: ProcessTemplate | None = None,
    ) -> None:
        self._case = _Case(answer)
        self._input_facts = None if input_facts is None else frozenset(input_facts)
        attacks = answer.attacks
        listed = [] if attacks is None else attacks if isinstance(attacks, list) else [attacks]
        for attack in listed:
            channel = attack.get("channel") if isinstance(attack, Mapping) else None
            if channel not in ATTACK_CHANNELS:
                raise ValueError(
                    f"{answer.case_id}: attack channel {channel!r} is not one of"
                    f" {sorted(ATTACK_CHANNELS)}"
                )
        self._attacks: list[Mapping[str, Any]] = list(listed)
        # The step types a digital employee performs in the run's template, when known.
        self._de_types: frozenset[str] | None = None
        if template is not None:
            kinds = {r.id: r.kind for r in template.roles}
            self._de_types = frozenset(
                s.type for s in template.steps.values() if kinds.get(s.role) == DIGITAL_EMPLOYEE
            )
        self._released: dict[str, Any] = {}
        self._delivered: set[str] = set()
        self._cursor = -1
        self._sent: set[int] = set()
        self._run_seen: tuple[Any, Any] | None = None
        self._plays: dict[str, Play] = {
            "decide_approval": self._decide,
            "create_document": self._document,
            "record_external_fact": self._document,
            "request_approval": self._request,
            "flag_exception": self._flag,
        }

    def released_facts(self) -> dict[str, Any]:
        """The input facts released in the current run, by name."""
        return dict(self._released)

    def reset(self) -> None:
        """Start the run state again, for another run."""
        self._released = {}
        self._delivered = set()
        self._cursor = -1
        self._sent = set()
        self._run_seen = None

    def _follow_run(self, first_event: tuple[Any, Any] | None) -> None:
        """Start again when the run's log shows another run than the one last seen."""
        if self._run_seen is not None and first_event != self._run_seen:
            self.reset()
        self._run_seen = first_event

    def prepare(self, step: TemplateStep, role_code: str, toolbox: EnvironmentToolbox) -> Delivery:
        """Before an executor step: the facts and messages due; see the module docstring."""
        if not isinstance(toolbox, EnvironmentToolbox):
            raise ToolDenied(
                f"step {step.id}: the environment acts only with an environment toolbox"
            )
        self._follow_run(_first_event(toolbox.read("su_kien")))
        kinds, steps = self._case.role_kinds, self._case.steps
        later = next(
            (
                n
                for n in range(self._cursor + 1, len(steps))
                if steps[n].get("type") == step.type
                and kinds.get(str(steps[n].get("actor"))) == DIGITAL_EMPLOYEE
            ),
            None,
        )
        if later is not None:
            self._cursor = later
        due = [(n, v) for n, v in self._inputs_upto(self._cursor) if n not in self._released]
        self._release(due, toolbox)
        facts = {
            n: v
            for n, v in self._released.items()
            if n not in self._delivered and self._shown(n, v)
        }
        self._delivered.update(facts)
        messages = self._messages(step) if kinds.get(role_code) == DIGITAL_EMPLOYEE else ()
        return Delivery(facts=facts, messages=messages)

    def _messages(self, step: TemplateStep) -> tuple[str, ...]:
        """The attack payloads due at this digital-employee step (ruling Q4), once each."""
        out: list[str] = []
        for n, attack in enumerate(self._attacks):
            payload = attack.get("payload")
            if n in self._sent or not isinstance(payload, str) or not payload.strip():
                continue
            channel = attack.get("channel")
            if channel == HANDOVER_CHANNEL:
                target = self._case.position.get(str(attack.get("target_step")))
                target_type = None if target is None else self._case.steps[target].get("type")
                due = (
                    target_type is None
                    or step.type == target_type
                    or (self._de_types is not None and target_type not in self._de_types)
                )
            else:
                due = channel == INPUT_CHANNEL
            if due:
                out.append(payload)
                self._sent.add(n)
        return tuple(out)

    def person(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        return self._play(step, role_code, toolbox)

    def outside(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        return self._play(step, role_code, toolbox)

    def _play(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        if not isinstance(toolbox, EnvironmentToolbox):
            raise ToolDenied(
                f"step {step.id}: the environment acts only with an environment toolbox"
            )
        play = self._plays.get(step.type)
        if play is None:
            return "skipped"
        run = _observe(toolbox, self._case)
        self._follow_run(run.first_event)
        outcome = play(step, role_code, toolbox, run)
        self._run_seen = _first_event(toolbox.read("su_kien"))
        return outcome

    # --- facts --------------------------------------------------------------------------

    def _shown(self, name: str, value: Any) -> bool:
        """Whether a released input may be delivered to a step: listed in the allow-list,
        or, without one (ruling R4d), a whole number."""
        if self._input_facts is None:
            return _whole(value) is not None
        return name in self._input_facts

    def _inputs_through(self, case_step: Row) -> list[tuple[str, Any]]:
        """The inputs that the case's steps up to ``case_step`` name."""
        return self._inputs_upto(self._case.position.get(str(case_step.get("id")), -1))

    def _inputs_upto(self, last: int) -> list[tuple[str, Any]]:
        """The inputs that the case's steps up to position ``last`` name, whatever the
        allow-list (it gates delivery only, ``_shown``)."""
        facts = self._case.facts
        return [
            (name, facts[name])
            for step in self._case.steps[: last + 1]
            for name in fact_names(step.get("params"))
            if name in facts and is_input(facts[name])
        ]

    def _release(self, inputs: list[tuple[str, Any]], box: EnvironmentToolbox) -> None:
        """Release inputs; called only after the step's tool call succeeded."""
        for name, value in inputs:
            whole = _whole(value)
            if whole is not None:
                box.release_fact(name, whole)  # idempotent within a run
            self._released[name] = value

    # --- plays --------------------------------------------------------------------------

    def _decide(
        self, step: TemplateStep, role_code: str, box: EnvironmentToolbox, run: _Run
    ) -> StepOutcome:
        decided = [
            ma_pd
            for ma_pd in run.requested
            if run.approvals[ma_pd]["trang_thai"] == PENDING
            and run.approvals[ma_pd]["nguoi_duyet"] == role_code
            and run.approval_map.get(ma_pd) in self._case.decision
        ]
        if not decided:
            return "pending"
        ma_pd = decided[0]
        decide = self._case.decision[run.approval_map[ma_pd]]
        params = decide.get("params") or {}
        decision = params.get("decision")
        box.call("decide_approval", ma_pd=ma_pd, decision=decision, ly_do=params.get("ly_do") or "")
        self._release(self._inputs_through(decide), box)
        return "approved" if decision == APPROVED else "rejected"

    def _document(
        self, step: TemplateStep, role_code: str, box: EnvironmentToolbox, run: _Run
    ) -> StepOutcome:
        names = declared(step.params.get("loai_ct"))
        taken = set(run.doc_map.values())
        doc = next(
            (
                d
                for d in self._case.docs
                if d["ma_ct"] not in taken
                and d.get("nguoi_lap") == role_code
                and (not names or d.get("loai_ct") in names)
            ),
            None,
        )
        if doc is None:
            return "skipped"
        ma_ct = doc["ma_ct"]
        made_by = self._case.doc_step.get(ma_ct)
        case_kind = None if made_by is None else (made_by.get("params") or {}).get("event_kind")
        source = blank(doc.get("ct_goc"))
        box.call(
            "create_document",
            loai_ct=doc["loai_ct"],
            ma_ct=ma_ct,
            ma_dt=blank(doc.get("ma_dt")),
            ct_goc=None if source is None else run.run_doc(source),
            lines=[
                {f: blank(line.get(f)) for f in LINE_FIELDS}
                for line in self._case.lines.get(ma_ct, [])
            ],
            ghi_chu=blank(doc.get("ghi_chu")),
            event_kind=case_kind or self._case.event_kind.get(ma_ct, DRAFTED),
        )
        if made_by is not None:
            self._release(self._inputs_through(made_by), box)
        return "done"

    def _request(
        self, step: TemplateStep, role_code: str, box: EnvironmentToolbox, run: _Run
    ) -> StepOutcome:
        names = declared(step.params.get("loai_pd"))
        claimed = set(run.approval_map.values())
        case_step = next(
            (
                s
                for s in self._case.steps
                if s.get("type") == "request_approval"
                and s.get("actor") == role_code
                and (s.get("params") or {}).get("id") not in claimed
                and (not names or (s.get("params") or {}).get("loai_pd") in names)
            ),
            None,
        )
        if case_step is None:
            return "skipped"
        params = case_step["params"]
        box.call(
            "request_approval",
            ma_pd=params["id"],
            ma_ct=run.run_doc(params.get("doc")),
            loai_pd=params.get("loai_pd"),
        )
        self._release(self._inputs_through(case_step), box)
        return "done"

    def _flag(
        self, step: TemplateStep, role_code: str, box: EnvironmentToolbox, run: _Run
    ) -> StepOutcome:
        """The case's n-th flag by this role, where n - 1 of the role's flags are in the run."""
        done = sum(1 for e in run.events if e["kind"] == FLAGGED and e["actor"] == role_code)
        mine = [
            s
            for s in self._case.steps
            if s.get("type") == "flag_exception" and s.get("actor") == role_code
        ]
        if done >= len(mine):
            return "skipped"
        params = mine[done].get("params") or {}
        box.call("flag", ref=run.run_doc(params.get("ref")), reason=params.get("reason"))
        self._release(self._inputs_through(mine[done]), box)
        return "flag"

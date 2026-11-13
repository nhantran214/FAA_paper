"""The engine: walk a process template for one case and hand each step to its actor.

``run_case``:

1. Validates the template against the company pack and refuses to start on any
   error (``TemplateInvalid``), before anything is written. Maps the template
   roles to the company's role codes (``map_roles``, Task 14), and records the mapping
   in ``RunResult.binding`` and ``binding_exact``. A digital employee's tokens are
   issued from its role's scope capped by its company role's duties (``capped_scope``).
2. Resets schema ``core`` and loads the given data: the pack's master rows and the
   instance's data. Given data is loaded outside ``acting_as`` (ruling R2a): it is
   data, not an action, so the rules that bind actors stand aside. Given data never
   holds the run case's own ``ho_so`` row: the run opens its case.
3. Walks from ``template.start``. Engine steps (``open_case``, ``wait``, ``stop``)
   the engine runs itself; ``open_case`` inserts ``core.ho_so`` as actor
   ``engine`` of kind ``dieu_phoi`` and records no tool call (ruling R0b); then the
   pack policy's whole-number caps and approval tier maxima are released to the
   case in ``core.nguon_tien``, outside ``acting_as`` (rulings R2f, R7e). Every
   other step goes to its actor through a ``StepToolbox``: a digital employee's
   (``so``) and the engine's own non-engine step types (``check``,
   ``flag_exception``, ``compute_amount``) to the executor, a person's (``nguoi``)
   to ``environment.person``, an outside party's (``ngoai``) to
   ``environment.outside`` (with an ``EnvironmentToolbox``, which can also release
   facts). A digital employee gets a fresh task token per step; the others none.
   Before each step it hands the executor, the engine gives the environment its turn
   (``environment.prepare``, with an ``EnvironmentToolbox`` of actor ``environment``
   that may call no tool, only ``read`` and ``release_fact``). The facts of each
   ``Delivery`` are kept for the run (a later value of a name wins); every toolbox's
   ``view`` shows them, the case's neutral request, and, for the executor's step, the
   messages delivered for it. A refused ``prepare`` refuses the step before the
   executor is called. An environment with a ``reset`` method has it called once at
   the start of every run, after loading (ruling R4e).
   A step goes to the company role code its template role is bound to. A step of an
   optional role bound to nobody is ``skipped``. A person role bound to several people
   (ruling R12a) hands a decision to the person the gate routed the latest pending
   approval of this run to (of the role's approval types, among its people), and any
   other step to each of its people in the company's order until one does not skip it.
   A wait whose ``for`` names a decide step also says, as ``approver``, whom that
   step's pending approval was routed to.
4. Chooses the next step: ``on[outcome]`` if declared, else ``next``. A ``skipped``
   step that is not optional is ``refused``. A ``refused`` step follows
   ``on["refused"]`` if declared, else the run stops with
   ``{"type": "error", "step": id}``.

Controls (``tonomyx.enforce.controls``). ``controls`` (default ``FULL``) switches
enforcement tiers off for an experiment's baseline arms; no declaration can. Right
after the reset, inside the loading transaction, the run sets the platform-rule
triggers as ``controls.database`` asks (so a run never inherits a state another run
left), and it sets them all on again (``FULL``) in a ``finally``, whatever happened. With
``controls.tokens`` off, a digital employee's every step gets a token of
``WIDEST_SCOPE`` (no ceiling check, whatever its role's scope or its company role's
duties) and the executor's toolbox binds no tool or argument to the step. With
``controls.gate`` off, every context holds an ``OpenGate`` with ``gate_checks`` False,
and a digital employee may report a decision. ``RunResult.controls`` records what the run ran under.

A refused call (``ToolDenied``, or any database error, ruling R6b) is caught, its
message goes to ``refusals`` as ``"<step id>: <message>"`` and the step's outcome is
``refused``; the refused call's own transaction has already rolled its writes back,
so the connection stays usable. A refusal the actor swallowed still refuses the
step. An actor that itself reports ``refused`` is recorded as
``"<step id>: <role code> reported refused"``, so an error stop is always explained.

Transactions. Loading is one transaction (reset and load together). Between steps
the connection is idle, so each tool call's ``acting_as`` is a top-level
transaction that commits when the call returns: a refused step keeps the
committed, logged writes of its earlier calls. After each step the engine ends any
transaction the step left open (commit, or roll back a failed one). Call it on a
connection that is not inside a transaction block.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, cast

import psycopg
from psycopg import pq, sql

from tonomyx.contracts.token import TaskToken, TokenIssuer
from tonomyx.core.db import acting_as, reset_core
from tonomyx.core.schema import CORE_SCHEMA_NAME, load_core_schema
from tonomyx.enforce.controls import FULL, ControlError, Controls, apply_database_control
from tonomyx.enforce.gate import BusinessGate, OpenGate
from tonomyx.enforce.tokens import WIDEST_SCOPE, capped_scope, scope_token, task_token
from tonomyx.engine.protocols import OUTCOMES, Delivery, Environment, Executor, StepOutcome
from tonomyx.engine.toolbox import EnvironmentToolbox, StepToolbox
from tonomyx.governance.binding import RoleMapping, map_roles
from tonomyx.governance.pack import CompanyPack, Policy
from tonomyx.governance.template import ProcessTemplate, RoleScope, TemplateRole, TemplateStep
from tonomyx.governance.validate import Finding, validate
from tonomyx.tools.core import CoreContext
from tonomyx.tools.core.context import PENDING
from tonomyx.tools.errors import ToolDenied
from tonomyx.tools.ports import MailSender

ENGINE_ACTOR = "engine"
ENGINE_KIND = "dieu_phoi"
ENGINE_STEPS = frozenset({"open_case", "wait", "stop"})
# Who the environment's turn before an executor step acts as. Its toolbox calls no tool.
ENVIRONMENT_ACTOR = "environment"
ENVIRONMENT_KIND = "ngoai"
OPEN_CASE_STATUS = "Đang xử lý"
# Outcomes only a decision gives. A digital employee never decides (rule 1), so it never
# reports one: its step's outcome would route the walk as if an approval were decided.
DECISIONS = frozenset({"approved", "rejected"})
# A walk longer than this is a loop in the template, not a process.
MAX_STEPS = 500

# Given tables in foreign-key order. The event log is never given: an event is an action.
GIVEN_TABLES: tuple[str, ...] = (
    "doi_tac",
    "hang_hoa",
    "nhan_su",
    "ngan_sach",
    "tri_thuc",
    "ho_so",
    "chung_tu",
    "dong_ct",
    "phe_duyet",
    "thanh_toan",
)
_COLUMNS: dict[str, tuple[str, ...]] = {
    table: tuple(c.name for c in columns) for table, columns in load_core_schema().tables.items()
}


@dataclass(frozen=True)
class CaseInstance:
    """One case: its id, title, the request that starts it, and its given operational data."""

    case_id: str
    title: str
    request: str
    data: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult:
    case_id: str
    steps_run: list[str]
    outcomes: dict[str, StepOutcome]
    stop: dict[str, Any]
    refusals: list[str]
    governance_version: str
    controls: Controls = FULL
    # The install-time role mapping (``map_roles``): template role -> company role codes,
    # and whether every template role's duties matched its codes exactly.
    binding: dict[str, tuple[str, ...]] = field(default_factory=dict)
    binding_exact: bool = True


class TemplateInvalid(Exception):
    """The template failed validation against the pack; the run did not start."""

    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        super().__init__(
            "template refused: " + "; ".join(f"{f.code} ({f.where}): {f.message}" for f in findings)
        )


class GivenDataError(ValueError):
    """The given data cannot be loaded into ``core``."""


def run_case(
    conn: psycopg.Connection[Any],
    *,
    template: ProcessTemplate,
    pack: CompanyPack,
    instance: CaseInstance,
    executor: Executor,
    environment: Environment,
    governance_version: str,
    issuer: TokenIssuer,
    mail: MailSender | None = None,
    controls: Controls = FULL,
) -> RunResult:
    if not isinstance(controls, Controls):
        raise TypeError(f"controls must be a Controls, not {type(controls).__name__}")
    errors = [f for f in validate(template, pack) if f.level == "error"]
    if errors:
        raise TemplateInvalid(errors)
    mapping = map_roles(template, pack)
    binding = {role_id: m.codes for role_id, m in mapping.items()}
    given = _given_rows(pack.master, instance.data)
    given_cases = {_cell(r.get("case_id")) for t, rs in given if t == "ho_so" for r in rs}
    if instance.case_id in given_cases:
        raise GivenDataError(
            f"given data holds case {instance.case_id}'s own ho_so row: a run opens its case"
        )

    _settle(conn)
    try:
        with conn.transaction():
            reset_core(conn)
            # Always, before loading: a run never inherits the trigger state of another.
            apply_database_control(conn, controls)
            _load(conn, given)
        # Ruling R4e: an environment that keeps run state starts it again with each run,
        # even when the previous run wrote nothing it could tell this one apart by.
        reset = getattr(environment, "reset", None)
        if callable(reset):
            reset()
        walk = _Walk(
            conn=conn,
            template=template,
            policy=pack.policy,
            instance=instance,
            binding=binding,
            scopes=_capped_scopes(template, pack, mapping),
            binding_exact=all(m.exact for m in mapping.values()),
            executor=executor,
            environment=environment,
            governance_version=governance_version,
            issuer=issuer,
            mail=mail,
            controls=controls,
        )
        return walk.run()
    finally:
        _restore_database_tier(conn)


def _capped_scopes(
    template: ProcessTemplate, pack: CompanyPack, mapping: dict[str, RoleMapping]
) -> dict[str, RoleScope]:
    """Each digital-employee role's scope capped by its company roles' duties
    (``capped_scope``): what its tokens are issued from while the token tier is on."""
    by_code = {r.code: r for r in pack.roles}
    return {
        t.id: capped_scope(t.scope, (by_code[c] for c in mapping[t.id].codes))
        for t in template.roles
        if t.kind == "so" and t.scope is not None
    }


def _restore_database_tier(conn: psycopg.Connection[Any]) -> None:
    """Switch every platform-rule trigger on again at the end of a run, however it ended.

    The trigger state is catalogue state and outlives the connection. A connection that
    closed during the run cannot do it: that is a ``ControlError`` (the next ``run_case``
    or ``reset_core`` switches them on)."""
    if conn.closed:
        raise ControlError(
            "the connection closed during the run: the platform-rule triggers may still be"
            " off until the next run_case or reset_core"
        )
    _settle(conn)
    apply_database_control(conn, FULL)


# --- the walk ---------------------------------------------------------------------------


class _Walk:
    def __init__(
        self,
        *,
        conn: psycopg.Connection[Any],
        template: ProcessTemplate,
        policy: Policy,
        instance: CaseInstance,
        binding: dict[str, tuple[str, ...]],
        executor: Executor,
        scopes: dict[str, RoleScope] | None = None,
        binding_exact: bool = True,
        environment: Environment,
        governance_version: str,
        issuer: TokenIssuer,
        mail: MailSender | None,
        controls: Controls = FULL,
    ) -> None:
        self.conn = conn
        self.template = template
        self.policy = policy
        self.instance = instance
        self.case_id = instance.case_id
        self.binding = binding
        self.binding_exact = binding_exact
        self.roles: dict[str, TemplateRole] = {r.id: r for r in template.roles}
        # The scopes tokens are issued from: each role's own, capped by its company duties.
        self.scopes: dict[str, RoleScope] = {
            r.id: r.scope for r in template.roles if r.scope is not None
        }
        self.scopes.update(scopes or {})
        self.executor = executor
        self.environment = environment
        self.governance_version = governance_version
        self.issuer = issuer
        self.mail = mail
        self.controls = controls
        self.gate = BusinessGate(policy) if controls.gate else OpenGate(policy)
        self.released = False
        self.steps_run: list[str] = []
        self.outcomes: dict[str, StepOutcome] = {}
        self.refusals: list[str] = []
        # decide step id -> the person its pending approval was routed to
        self.routed_to: dict[str, str] = {}
        # The facts the environment delivered in this run, by name (a later value wins).
        self.facts: dict[str, Any] = {}

    def run(self) -> RunResult:
        sid = self.template.start
        stop: dict[str, Any] | None = None
        while stop is None:
            if len(self.steps_run) >= MAX_STEPS:
                stop = {"type": "error", "step": sid, "reason": f"step limit {MAX_STEPS} reached"}
                break
            step = self.template.steps[sid]
            self.steps_run.append(sid)
            if step.type == "wait":
                self.outcomes[sid] = "pending"
                stop = {"type": "wait", "for": step.params["for"], "step": sid}
                approver = self.routed_to.get(str(step.params["for"]))
                if approver is not None:
                    stop["approver"] = approver
                break
            if step.type == "stop":
                self.outcomes[sid] = "done"
                stop = {"type": "end", "reason": step.params["reason"], "step": sid}
                break
            if step.type == "open_case":
                outcome, messages = self._open_case(step)
            else:
                outcome, messages = self._hand_over(step)
            if outcome == "skipped" and not step.optional:
                messages.append(f"step {sid} was skipped, and it is not optional")
                outcome = "refused"
            self.refusals.extend(f"{sid}: {m}" for m in messages)
            self.outcomes[sid] = outcome
            target = step.on.get(outcome)
            if target is None and outcome != "refused":
                target = step.next
            if target is None:
                stop = {"type": "error", "step": sid}
                if outcome != "refused":
                    stop["reason"] = f"no step follows outcome {outcome!r}"
                break
            sid = target
        return RunResult(
            case_id=self.case_id,
            steps_run=self.steps_run,
            outcomes=self.outcomes,
            stop=stop,
            refusals=self.refusals,
            governance_version=self.governance_version,
            controls=self.controls,
            binding=dict(self.binding),
            binding_exact=self.binding_exact,
        )

    # --- engine steps ---------------------------------------------------------------

    def _open_case(self, step: TemplateStep) -> tuple[StepOutcome, list[str]]:
        """Open the case as the engine (ruling R0b): a ``ho_so`` row and no tool call."""
        title = self.instance.title or str(step.params.get("title", ""))
        try:
            with acting_as(self.conn, ENGINE_ACTOR, ENGINE_KIND, self.governance_version) as c:
                c.execute(
                    "INSERT INTO core.ho_so (case_id, tieu_de, trang_thai) VALUES (%s, %s, %s)",
                    (self.case_id, title, OPEN_CASE_STATUS),
                )
        except psycopg.Error as exc:
            _settle(self.conn)
            return "refused", [_message(exc)]
        self.release_policy_values()
        _settle(self.conn)
        return "done", []

    def release_policy_values(self) -> None:
        """Release the policy's caps and tier maxima to the case, as the platform (R2f, R7e)."""
        if self.released:
            return
        with self.conn.transaction():
            for name, value in policy_values(self.policy):
                self.conn.execute(
                    "INSERT INTO core.nguon_tien (case_id, ten, gia_tri) VALUES (%s, %s, %s)",
                    (self.case_id, name, value),
                )
        self.released = True

    # --- actor steps ----------------------------------------------------------------

    def _hand_over(self, step: TemplateStep) -> tuple[StepOutcome, list[str]]:
        """Hand the step to the company role code(s) its template role is bound to.

        An optional role bound to nobody skips the step. A person role bound to several
        people (ruling R12a): a decision goes to the person the gate routed the pending
        approval to; any other step to each of them in the company's order, until one does
        not skip it."""
        role = self.roles[step.role]
        codes = self.binding[step.role]
        if not codes:
            return "skipped", []
        if role.kind == "nguoi" and step.type == "decide_approval":
            codes = (self._routed_approver(step, role, codes),)
        outcome: StepOutcome = "skipped"
        messages: list[str] = []
        for code in codes:
            outcome, messages = self._hand_to(step, role, code)
            if outcome != "skipped" or messages:
                break
        return outcome, messages

    def _routed_approver(
        self, step: TemplateStep, role: TemplateRole, codes: tuple[str, ...]
    ) -> str:
        """The approver of the latest approval requested in this run that is still pending,
        routed to one of ``codes`` and of a type the role decides (any, if it lists none);
        ``codes[0]`` when there is none. Remembered for a wait on this step."""
        with self.conn.cursor() as cur:
            found = cur.execute(
                "SELECT p.nguoi_duyet, p.loai_pd FROM core.phe_duyet p"
                " JOIN (SELECT ref, min(id) AS first FROM core.su_kien"
                "       WHERE case_id = %s AND kind = 'REQUESTED' GROUP BY ref) e"
                " ON e.ref = p.ma_pd"
                " WHERE p.case_id = %s AND p.trang_thai = %s AND p.nguoi_duyet = ANY(%s)"
                " ORDER BY e.first DESC",
                (self.case_id, self.case_id, PENDING, list(codes)),
            ).fetchall()
        _settle(self.conn)
        decides = role.duties.decides
        for row in found:
            approver, loai_pd = (
                (row["nguoi_duyet"], row["loai_pd"]) if isinstance(row, Mapping) else row
            )
            if not decides or loai_pd in decides:
                self.routed_to[step.id] = str(approver)
                return str(approver)
        self.routed_to.pop(step.id, None)
        return codes[0]

    def _hand_to(
        self, step: TemplateStep, role: TemplateRole, code: str
    ) -> tuple[StepOutcome, list[str]]:
        token: TaskToken | None = None
        task_id = f"{self.case_id}/{step.id}/{len(self.steps_run)}"
        if role.kind == "so" and not self.controls.tokens:
            # The token tier is off: the widest scope's token, whatever the role's scope.
            token = scope_token(
                self.issuer, code, WIDEST_SCOPE, self.case_id, task_id, check_ceiling=False
            )
        elif role.kind == "so":
            scope = self.scopes.get(role.id)
            if scope is None:
                return "refused", [f"digital employee {code} has no scope"]
            try:
                token = task_token(
                    self.issuer,
                    code,
                    scope,
                    step,
                    self.case_id,
                    task_id,
                )
            except ValueError as exc:
                return "refused", [str(exc)]
        delivered: tuple[str, ...] = ()
        if role.kind in ("so", ENGINE_KIND):
            delivered, refused = self._prepare(step, code)
            if refused:
                return "refused", refused
        ctx = CoreContext(
            conn=self.conn,
            case_id=self.case_id,
            actor=code,
            actor_kind=role.kind,
            token=token,
            gate=self.gate,
            governance_version=self.governance_version,
            step_id=step.id,
            mail=self.mail,
            gate_checks=self.controls.gate,
            # The token tier binds the executor's steps; a person's or an outside party's
            # toolbox keeps its step's tools in every mode.
            token_checks=self.controls.tokens or role.kind not in ("so", ENGINE_KIND),
        )
        toolbox = (
            EnvironmentToolbox(
                ctx,
                step,
                None,
                None,
                template=self.template,
                request=self.instance.request,
                facts=self.facts,
            )
            if role.kind in ("nguoi", "ngoai")
            else StepToolbox(
                ctx,
                step,
                self.issuer,
                token,
                template=self.template,
                request=self.instance.request,
                facts=self.facts,
                messages=delivered,
            )
        )
        escaped: Exception | None = None
        outcome: Any
        try:
            if role.kind in ("so", ENGINE_KIND):
                outcome = self.executor.perform(step, code, toolbox)
            elif role.kind == "nguoi":
                outcome = self.environment.person(step, code, toolbox)
            elif role.kind == "ngoai":
                outcome = self.environment.outside(step, code, toolbox)
            else:
                outcome = "refused"
                escaped = ToolDenied(f"unknown actor kind {role.kind!r}")
        except (ToolDenied, psycopg.Error) as exc:
            escaped, outcome = exc, "refused"
        finally:
            toolbox.close()
            _settle(self.conn)
        messages = [_message(e) for e in toolbox.refusals]
        if escaped is not None and not any(e is escaped for e in toolbox.refusals):
            messages.append(_message(escaped))
        if messages:
            return "refused", messages
        if not isinstance(outcome, str) or outcome not in OUTCOMES:
            return "refused", [f"{code} reported an unknown outcome {outcome!r}"]
        if outcome == "refused":
            return "refused", [f"{code} reported refused"]
        if self.controls.gate and role.kind == "so" and outcome in DECISIONS:
            return "refused", [
                f"platform rule 1: digital employee {code} reported the decision {outcome!r}"
            ]
        return cast(StepOutcome, outcome), []

    def _prepare(self, step: TemplateStep, code: str) -> tuple[tuple[str, ...], list[str]]:
        """The environment's turn before the executor's ``step`` of ``code``: the messages
        it delivered for the step, and the refusals that refuse the step (none when it
        went well). The delivered facts join the run's."""
        ctx = CoreContext(
            conn=self.conn,
            case_id=self.case_id,
            actor=ENVIRONMENT_ACTOR,
            actor_kind=ENVIRONMENT_KIND,
            token=None,
            gate=self.gate,
            governance_version=self.governance_version,
            step_id=step.id,
            mail=None,
            gate_checks=self.controls.gate,
        )
        box = EnvironmentToolbox(
            ctx,
            step,
            None,
            None,
            template=self.template,
            request=self.instance.request,
            facts=self.facts,
            tools=frozenset(),
        )
        escaped: Exception | None = None
        delivery: Any = None
        try:
            delivery = self.environment.prepare(step, code, box)
        except (ToolDenied, psycopg.Error) as exc:
            escaped = exc
        finally:
            box.close()
            _settle(self.conn)
        refusals: list[Exception] = list(box.refusals)
        if escaped is not None and not any(e is escaped for e in refusals):
            refusals.append(escaped)
        if refusals:
            return (), [f"environment: {_message(e)}" for e in refusals]
        if (
            not isinstance(delivery, Delivery)
            or not isinstance(delivery.facts, Mapping)
            or not all(isinstance(name, str) for name in delivery.facts)
            or not isinstance(delivery.messages, tuple)
            or not all(isinstance(m, str) for m in delivery.messages)
        ):
            # The type alone (Task 4 M4): the object may hold answer values.
            return (), [
                "environment: not a delivery of named facts and texts:"
                f" {type(delivery).__name__}"
            ]
        self.facts.update(delivery.facts)
        return delivery.messages, []


# --- given data ---------------------------------------------------------------------------


def policy_values(policy: Policy) -> list[tuple[str, int]]:
    """The policy's whole-number caps and approval tier maxima, named by where they sit
    (ruling R7e: tolerances are ratios and margins, not amounts, and are not released)."""
    out: list[tuple[str, int]] = []
    for name, value in sorted(policy.caps.items()):
        if _whole(value):
            out.append((f"caps.{name}", int(value)))
    for loai_pd, rule in sorted(policy.approval_rules.items()):
        for i, tier in enumerate(rule.tiers):
            if tier.max is not None and _whole(tier.max):
                out.append((f"approval_rules.{loai_pd}.tiers.{i}.max", int(tier.max)))
    return out


def _whole(value: Decimal) -> bool:
    return value.is_finite() and value == value.to_integral_value()


def _cell(value: Any) -> Any:
    """A blank CSV cell means "not set"."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


def load_given(conn: psycopg.Connection[Any], *sources: Mapping[str, list[dict[str, Any]]]) -> None:
    """Check given tables and insert them into ``core`` as the platform, outside
    ``acting_as`` (ruling R2a), in one transaction: what ``run_case`` loads, without the
    reset. For putting a known state straight into ``core`` (tests, scoring checks).
    Raises ``GivenDataError`` before anything is written when the tables are not given
    data (an event, an unknown table or column, documents naming each other)."""
    given = _given_rows(*sources)
    with conn.transaction():
        _load(conn, given)


def _given_rows(
    *sources: Mapping[str, list[dict[str, Any]]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Merge and check the given tables, in foreign-key order. Writes nothing."""
    merged: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        for table, table_rows in source.items():
            if table == "su_kien":
                raise GivenDataError("given data never holds su_kien rows: an event is an action")
            if table not in GIVEN_TABLES:
                raise GivenDataError(f"given data names an unknown table {table!r}")
            for row in table_rows:
                unknown = sorted(set(row) - set(_COLUMNS[table]))
                if unknown:
                    raise GivenDataError(f"given {table} row has unknown column(s) {unknown}")
            merged.setdefault(table, []).extend(table_rows)
    out = []
    for table in GIVEN_TABLES:
        if table in merged:
            table_rows = merged[table]
            out.append((table, _sources_first(table_rows) if table == "chung_tu" else table_rows))
    return out


def _sources_first(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order documents so a source document (``ct_goc``) is loaded before those naming it."""
    given = {d.get("ma_ct") for d in documents}
    placed: set[Any] = set()
    out: list[dict[str, Any]] = []
    remaining = list(documents)
    while remaining:
        later = []
        for d in remaining:
            source = _cell(d.get("ct_goc"))
            if source is None or source not in given or source in placed:
                out.append(d)
                placed.add(d.get("ma_ct"))
            else:
                later.append(d)
        if len(later) == len(remaining):
            raise GivenDataError(
                f"given documents name each other as source (ct_goc): "
                f"{sorted(str(d.get('ma_ct')) for d in later)}"
            )
        remaining = later
    return out


def _load(conn: psycopg.Connection[Any], given: Iterable[tuple[str, list[dict[str, Any]]]]) -> None:
    """Insert the given rows as the platform, outside ``acting_as`` (ruling R2a)."""
    for table, table_rows in given:
        for row in table_rows:
            columns = [c for c in _COLUMNS[table] if c in row]
            query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
                sql.Identifier(CORE_SCHEMA_NAME),
                sql.Identifier(table),
                sql.SQL(", ").join(map(sql.Identifier, columns)),
                sql.SQL(", ").join(sql.Placeholder() * len(columns)),
            )
            try:
                with conn.transaction():
                    conn.execute(query, [_cell(row[c]) for c in columns])
            except psycopg.Error as exc:
                raise GivenDataError(f"given {table} row {row!r}: {_message(exc)}") from exc


# --- connection and messages --------------------------------------------------------------


def _settle(conn: psycopg.Connection[Any]) -> None:
    """End whatever transaction a step left open: commit it, or roll back a failed one."""
    status = conn.info.transaction_status
    if status == pq.TransactionStatus.INERROR:
        conn.rollback()
    elif status == pq.TransactionStatus.INTRANS:
        conn.commit()


def _message(exc: BaseException) -> str:
    if isinstance(exc, psycopg.Error):
        diag = getattr(exc, "diag", None)
        primary = diag.message_primary if diag is not None else None
        return primary or str(exc).strip() or type(exc).__name__
    return str(exc) or type(exc).__name__

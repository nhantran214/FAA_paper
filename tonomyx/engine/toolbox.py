"""The only way an executor or the environment reaches a tool (rulings R7a, R6d).

A ``StepToolbox`` is bound to one step of one case, for one actor. Before a tool
runs, ``call`` checks that:

- the toolbox is still open (the engine closes it when the step ends);
- the tool is allowed for the step's actor kind: a digital employee (``so``) or the
  engine (``dieu_phoi``) gets the tools its step type needs (``STEP_NEEDS``); a
  person (``nguoi``) or an outside party (``ngoai``) gets ``ENVIRONMENT_TOOLS`` of
  the step type; a kind that ``step_types.json`` does not allow for the type gets none;
- a digital employee holds a task token that carries the tool. The token is
  verified through the issuer once per step (deadline, single use); later calls of
  the same step check the deadline only;
- the arguments are bound to the step: ``request_approval``'s ``loai_pd`` is one of the
  step's declared ``loai_pd``, and ``create_document``'s ``loai_ct`` is one of the
  step's declared ``loai_ct`` (each a string or a list: the names companies give one
  approval or document), when the step declares them;
  ``loai_pd`` and ``loai_ct`` must be texts whatever the step declares;
- ``pay`` is bound to its step (final review I1): the paid document ``ma_ct`` is of a
  type the template declares for the step's ``request`` (the ``loai_ct`` of the steps
  whose ``doc`` it names), the approval ``ma_pd`` is of a type the template declares for
  the step's ``approval`` (the ``loai_pd`` of the request steps whose ``id`` it names),
  an ``invoice`` is given when the step declares one (and is of the declared type of
  that document), and a step pays at most once. A ``ct_goc`` chain of documents paid
  twice across steps is a platform-level check left to later sub-projects (ruling R-F1);
- ``update_status`` changes the step's declared ``table``/``key``/``trang_thai``, and
  ``create_document`` records the step's declared ``event_kind``, when the step
  declares them;
- the tool name is a text, and the arguments fit the tool's signature.

Then it calls ``CORE_TOOLS[name](ctx, **args)``. An argument of the wrong shape that
a tool trips over (``TypeError``, ``ValueError``, ``LookupError``,
``ArithmeticError``) becomes ``ToolDenied``: the toolbox is where actor input
enters. Every refused call, a ``ToolDenied`` or a database error, is remembered in
``refusals`` before it is raised, so the engine records it even if the caller
swallows it. The tool's own transaction has rolled back by then.

Commits. Between steps the connection is idle, so each tool call's ``acting_as``
is a transaction of its own and commits when the call returns. A refused call
undoes only itself: earlier calls of the same step stay committed and logged,
even though the step's outcome becomes ``refused``.

With the token tier off (``ctx.token_checks`` False; experiments only, set by
``run_case`` from its ``controls``) the toolbox skips the step's tool set (any core
tool may be named; a ``tools`` narrowing still holds), the argument bindings to the
step (declared ``loai_pd``/``loai_ct``/``event_kind``, ``pay``'s request, approval,
invoice and once per step, ``update_status``'s table, key and status). The token
itself is still checked (the engine issues the widest scope's), and ``loai_pd`` and
``loai_ct`` must still be texts.

Actors never receive the tool context (ruling R7d). A toolbox gives ``view`` (case,
actor, kind, step, whether a token is held, the case's neutral request, the tools this
toolbox may call, the facts the environment has delivered in the run so far, the
messages it delivered for this step and the core tables it may read: ``token.read``
within the readable core tables with the token tier on, all of them with it off) and
``call``. A person's or an outside party's
toolbox (``EnvironmentToolbox``) can also ``read`` the case and ``release_fact``. The
environment's own turn before an executor step gets an ``EnvironmentToolbox`` that may
call no tool (``tools=frozenset()``).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeVar

import psycopg
from psycopg.rows import dict_row

from tonomyx.contracts.token import TaskToken, TokenExpired, TokenIssuer, TokenReplayed
from tonomyx.enforce.tokens import STEP_NEEDS
from tonomyx.governance.template import (
    ProcessTemplate,
    TemplateStep,
    _step_types,
    approval_types,
    declared,
    document_types,
)
from tonomyx.tools.core import CORE_TOOLS, CoreContext
from tonomyx.tools.core.context import PRIMARY_KEY, database_refusal, reading, select_rows
from tonomyx.tools.core.documents import DRAFTED
from tonomyx.tools.core.schemas import READABLE_TABLES
from tonomyx.tools.errors import ToolDenied

_ACTORS: dict[str, frozenset[str]] = {
    name: frozenset(spec["actors"]) for name, spec in _step_types()["types"].items()
}

# What a person or an outside party may do in each step type they may be given.
ENVIRONMENT_TOOLS: dict[str, frozenset[str]] = {
    "create_document": frozenset({"create_document"}),
    "record_external_fact": frozenset({"create_document", "record_event"}),
    "flag_exception": frozenset({"flag"}),
    "update_status": frozenset({"update_status"}),
    "request_approval": frozenset({"request_approval"}),
    "decide_approval": frozenset({"decide_approval"}),
}


def tools_for_step(step: TemplateStep, actor_kind: str) -> frozenset[str]:
    """The tools an actor of ``actor_kind`` may call in ``step``."""
    if actor_kind not in _ACTORS.get(step.type, frozenset()):
        return frozenset()
    if actor_kind in ("so", "dieu_phoi"):
        return STEP_NEEDS.get(step.type, frozenset())
    return ENVIRONMENT_TOOLS.get(step.type, frozenset())


# Errors a tool raises on arguments of the wrong shape (a list where a text belongs, a
# missing key, a number that is not one). The toolbox is the boundary for actor input,
# so they are refusals, not crashes.
_MALFORMED = (TypeError, ValueError, LookupError, ArithmeticError)

T = TypeVar("T")


@dataclass(frozen=True)
class StepView:
    """What an actor may know about its own step. It holds nothing that can call a tool."""

    case_id: str
    actor: str
    actor_kind: str
    step_id: str
    has_token: bool
    request: str = ""
    # The tools a call of this toolbox may name: the step's tools, within the token's.
    tools: frozenset[str] = frozenset()
    # The facts the environment delivered in the run so far (read-only; a later value wins).
    facts: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    # The messages the environment delivered for this step, in order.
    messages: tuple[str, ...] = ()
    # The core tables the actor may read in this step: the task token's ``read`` within
    # the tables a digital employee may read, with the token tier on; every such table
    # with it off (or without a token). ``core.nguon_tien`` is never one of them.
    readable: frozenset[str] = frozenset(READABLE_TABLES)


class StepToolbox:
    """One step's tools, for one actor; see the module docstring for the checks.

    The tool context (connection, token, gate) is held privately and never handed
    out: an actor sees ``view`` and calls ``call``. Python cannot make that private
    attribute unreachable; the boundary is a seam for honest instruments, and a
    model-backed executor runs behind its own process boundary (sub-project B).
    """

    def __init__(
        self,
        ctx: CoreContext,
        step: TemplateStep,
        issuer: TokenIssuer | None,
        token: TaskToken | None,
        *,
        template: ProcessTemplate,
        request: str = "",
        facts: Mapping[str, Any] | None = None,
        messages: tuple[str, ...] = (),
        tools: frozenset[str] | None = None,
    ) -> None:
        """``request``, ``facts`` and ``messages`` are shown in ``view``; ``tools``, when
        given, narrows the tools the step's actor kind may call (``frozenset()``: none)."""
        self.__ctx = ctx
        self.__step = step
        self.__issuer = issuer
        self.__token = token
        allowed = (
            tools_for_step(step, ctx.actor_kind) if ctx.token_checks else frozenset(CORE_TOOLS)
        )
        self.__allowed = allowed if tools is None else allowed & tools
        self.__verified = False
        self.__closed = False
        self.__paid = 0
        self.__refusals: list[Exception] = []
        params = step.params
        # What the template declares for the documents and approval this step names.
        self.__request_types = (
            document_types(template, params.get("request")) if step.type == "pay" else None
        )
        self.__approval_types = (
            approval_types(template, params.get("approval")) if step.type == "pay" else None
        )
        self.__invoice_types = (
            document_types(template, params.get("invoice"))
            if step.type == "pay" and "invoice" in params
            else None
        )
        self.__key_types = (
            document_types(template, params.get("key")) if step.type == "update_status" else None
        )
        may_name = self.__allowed if token is None else self.__allowed & token.tools
        if token is None and ctx.actor_kind == "so":
            may_name = frozenset()  # a digital employee calls nothing without a token
        readable = frozenset(READABLE_TABLES)
        if ctx.token_checks and token is not None:
            readable = readable & token.read
        self.view = StepView(
            ctx.case_id,
            ctx.actor,
            ctx.actor_kind,
            step.id,
            token is not None,
            request=request,
            tools=may_name,
            facts=MappingProxyType(dict(facts or {})),
            messages=tuple(messages),
            readable=readable,
        )

    @property
    def refusals(self) -> tuple[Exception, ...]:
        """Every refused call of the step, in order (read-only; final review M3)."""
        return tuple(self.__refusals)

    def close(self) -> None:
        self.__closed = True

    def call(self, name: str, /, **args: Any) -> dict[str, Any]:
        def run(ctx: CoreContext) -> dict[str, Any]:
            self._admit(name, args)
            try:
                out = CORE_TOOLS[name](ctx, **args)
            except _MALFORMED as exc:
                raise ToolDenied(f"{name}: malformed arguments: {exc!r}") from exc
            if name == "pay":
                self.__paid += 1
            return out

        return self._guarded(run, name if isinstance(name, str) else "tool")

    def _guarded(self, work: Callable[[CoreContext], T], what: str) -> T:
        """Run ``work`` on the context; remember a refusal and re-raise it.

        This is where an actor's call becomes a refusal. A database error that is no
        platform rule or gate becomes a generic refusal naming ``what`` (Task 15 fix
        round 2): the driver's and the query's text never reach an actor or the run's
        refusals; the original error is kept as the refusal's cause."""
        try:
            if self.__closed:
                raise ToolDenied(f"step {self.__step.id} has ended: its toolbox is closed")
            return work(self.__ctx)
        except ToolDenied as exc:
            self.__refusals.append(exc)
            raise
        except psycopg.Error as exc:
            denied = database_refusal(what, exc)
            self.__refusals.append(denied)
            raise denied from exc

    # --- checks -------------------------------------------------------------------

    def _deny(self, reason: str) -> ToolDenied:
        return ToolDenied(f"{self.__ctx.actor} may not call {reason}")

    def _admit(self, name: Any, args: dict[str, Any]) -> None:
        step, ctx = self.__step, self.__ctx
        if not isinstance(name, str) or name not in CORE_TOOLS:
            raise ToolDenied(f"unknown tool {name!r}")
        if name not in self.__allowed:
            raise self._deny(
                f"{name} in step {step.id}: a {step.type} step of actor kind {ctx.actor_kind}"
                f" allows {sorted(self.__allowed)}"
            )
        if self.__token is not None:
            if name not in self.__token.tools:
                raise self._deny(f"{name}: not in task token")
            self._verify(self.__token)
        elif ctx.actor_kind == "so":
            raise self._deny(f"{name}: a digital employee needs a task token")
        try:
            inspect.signature(CORE_TOOLS[name]).bind(ctx, **args)
        except TypeError as exc:
            raise ToolDenied(f"{name}: bad arguments: {exc}") from None
        self._bind(name, args)

    def _verify(self, token: TaskToken) -> None:
        if self.__issuer is None:
            raise ToolDenied("a task token is checked through its issuer, and there is none")
        try:
            if not self.__verified:
                self.__issuer.redeem_task_token(token)
                self.__verified = True
            elif self.__issuer.clock.now() > token.exp:
                raise TokenExpired(f"task token {token.jti} expired at {token.exp.isoformat()}")
        except (TokenExpired, TokenReplayed) as exc:
            raise ToolDenied(f"{self.__ctx.actor}: {exc}") from exc

    def _bind(self, name: str, args: dict[str, Any]) -> None:
        params, sid = self.__step.params, self.__step.id
        for kind in ("loai_pd", "loai_ct"):
            if kind in args and not isinstance(args[kind], str):
                raise self._deny(f"{name} with a {kind} that is not a text: {args[kind]!r}")
        if not self.__ctx.token_checks:
            return  # the token tier is off: no binding to the step
        if name == "request_approval" and "loai_pd" in params:
            names = declared(params["loai_pd"])
            if args.get("loai_pd") not in names:
                raise self._deny(
                    f"request_approval with loai_pd {args.get('loai_pd')!r} in step"
                    f" {sid}, which requests {sorted(names)}"
                )
        if name == "create_document":
            if "loai_ct" in params:
                names = declared(params["loai_ct"])
                if args.get("loai_ct") not in names:
                    raise self._deny(
                        f"create_document with loai_ct {args.get('loai_ct')!r} in step"
                        f" {sid}, which declares {sorted(names)}"
                    )
            if self.__step.type == "create_document" and "event_kind" in params:
                kind = args.get("event_kind", DRAFTED)
                if kind != params["event_kind"]:
                    raise self._deny(
                        f"create_document with event_kind {kind!r} in step {sid},"
                        f" which records {params['event_kind']!r}"
                    )
        if name == "pay":
            self._bind_pay(args)
        if name == "update_status" and self.__step.type == "update_status":
            self._bind_status(args)

    def _bind_pay(self, args: dict[str, Any]) -> None:
        """Final review I1: one payment per step, of the step's request, cleared by the
        step's approval, against the step's invoice when it declares one."""
        sid = self.__step.id
        if self.__paid:
            raise self._deny(f"pay twice in step {sid}: a pay step makes one payment")
        if "invoice" in self.__step.params and args.get("invoice") is None:
            raise self._deny(
                f"pay without an invoice in step {sid}, which pays against"
                f" {self.__step.params['invoice']!r}"
            )
        checks = (
            ("ma_ct", "chung_tu", "loai_ct", self.__request_types, "request"),
            ("ma_pd", "phe_duyet", "loai_pd", self.__approval_types, "approval"),
            ("invoice", "chung_tu", "loai_ct", self.__invoice_types, "invoice"),
        )
        for arg, table, kind, names, param in checks:
            if names is None or args.get(arg) is None:
                continue
            found = self._kind_of(table, {PRIMARY_KEY[table]: args[arg]}, kind)
            if found is not None and found not in names:
                raise self._deny(
                    f"pay with {arg} {args[arg]!r} of {kind} {found!r} in step {sid}, whose"
                    f" {param} {self.__step.params[param]!r} is one of {sorted(names)}"
                )

    def _bind_status(self, args: dict[str, Any]) -> None:
        """Final review M4: the step's declared table, document and status."""
        params, sid = self.__step.params, self.__step.id
        table = params.get("table")
        if isinstance(table, str) and args.get("table") != table:
            raise self._deny(
                f"update_status of table {args.get('table')!r} in step {sid},"
                f" which changes {table!r}"
            )
        names = declared(params.get("trang_thai"))
        if names and args.get("trang_thai") not in names:
            raise self._deny(
                f"update_status to {args.get('trang_thai')!r} in step {sid},"
                f" which sets {sorted(names)}"
            )
        key = args.get("key")
        if self.__key_types is not None and table == "chung_tu" and isinstance(key, dict) and key:
            found = self._kind_of("chung_tu", key, "loai_ct")
            if found is not None and found not in self.__key_types:
                raise self._deny(
                    f"update_status of a {found!r} document in step {sid}, whose key"
                    f" {params.get('key')!r} is one of {sorted(self.__key_types)}"
                )

    def _kind_of(self, table: str, where: dict[str, Any], column: str) -> Any:
        """``column`` of the one row of the case's ``table`` matching ``where``; None when
        there is not exactly one (the tool then refuses the call itself)."""
        if any(not isinstance(v, str) for v in where.values()):
            return None
        with reading(self.__ctx) as cur:
            found = select_rows(cur, self.__ctx, table, where)
        return found[0][column] if len(found) == 1 else None


class EnvironmentToolbox(StepToolbox):
    """A person's or an outside party's toolbox: the tools, plus reading the case and
    releasing facts.

    ``read`` is what a person or an outside party sees of the case: the rows of a
    core table that ``read_records`` gives (the run's case only, master tables
    whole). It writes nothing and records no event, so it is not one of the step's
    tools; a refused read refuses the step like any refused call.

    ``release_fact`` is how the environment hands the platform a number it learned
    (a received quantity, a quoted price): a row of ``core.nguon_tien`` for the
    run's case, written as the platform, outside ``acting_as``, so a digital
    employee may then use it as a money source (rule 3). Releasing the same name
    with the same value again changes nothing; with another value it is refused.
    """

    def read(self, table: str, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        def run(ctx: CoreContext) -> list[dict[str, Any]]:
            try:
                found = CORE_TOOLS["read_records"](ctx, table=table, where=where or {})
            except _MALFORMED as exc:
                raise ToolDenied(f"read of {table!r}: malformed arguments: {exc!r}") from exc
            return list(found["rows"])

        return self._guarded(run, "read")

    def release_fact(self, ten: str, gia_tri: int) -> None:
        def run(ctx: CoreContext) -> None:
            if not isinstance(ten, str) or not ten.strip():
                raise ToolDenied(f"a released fact needs a name, got {ten!r}")
            if isinstance(gia_tri, bool) or not isinstance(gia_tri, int):
                raise ToolDenied(f"released fact {ten} must be a whole number, got {gia_tri!r}")
            _release(ctx, ten.strip(), gia_tri)

        self._guarded(run, "release_fact")


def _release(ctx: CoreContext, ten: str, gia_tri: int) -> None:
    conn = ctx.conn
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "SELECT gia_tri FROM core.nguon_tien WHERE case_id = %s AND ten = %s FOR UPDATE",
            (ctx.case_id, ten),
        ).fetchone()
        if row is not None:
            if row["gia_tri"] != gia_tri:
                raise ToolDenied(
                    f"fact {ten} of case {ctx.case_id} was released as {row['gia_tri']},"
                    f" not {gia_tri}"
                )
            return
        cur.execute(
            "INSERT INTO core.nguon_tien (case_id, ten, gia_tri) VALUES (%s, %s, %s)",
            (ctx.case_id, ten, gia_tri),
        )

"""What every generic core tool shares: its context, the token checks and the acting block.

The tool tier sits above the database tier (``tonomyx/core/platform_rules.sql``).
A tool checks the caller's task token and the business gate, works out derived
money itself, and then writes inside ``acting_as`` so the database rules apply as
well. A database refusal (a message starting ``platform rule`` or ``platform
gate``) comes back as ``ToolDenied`` with the same message, and only that tool
call is rolled back: ``acting_as`` is a savepoint inside an open transaction, so
the engine can carry on.

Every write records exactly one ``su_kien`` row with ``buoc = ctx.step_id``; the
database fills in the actor, the governance version, the id and the time.

Control switches (``tonomyx.enforce.controls``; experiments only). ``gate_checks``
False (the gate tier off) skips the tool-tier platform-rule checks (rules 1-4, the
status rules, the money rule), and the context then holds an ``OpenGate``.
``token_checks`` False (the token tier off) skips the platform ceiling in
``require_draft``; the engine then issues the widest scope's token. Type coercion,
case scoping and the event log hold in every mode. Only ``run_case`` sets them, from
its ``controls`` argument; both default to on.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from tonomyx.contracts.token import TaskToken
from tonomyx.core.db import acting_as
from tonomyx.core.schema import CORE_SCHEMA_NAME, PACKAGED_SCHEMA, load_core_schema
from tonomyx.enforce.ceiling import PLATFORM_CEILING
from tonomyx.enforce.gate import BusinessGate, GateRefused, OpenGate
from tonomyx.tools.errors import ToolDenied
from tonomyx.tools.ports import MailSender

Cursor = psycopg.Cursor[dict[str, Any]]

SCHEMA = load_core_schema()
COLUMNS: dict[str, tuple[str, ...]] = {
    table: tuple(c.name for c in columns) for table, columns in SCHEMA.tables.items()
}
PRIMARY_KEY: dict[str, str] = {
    table: next(c.name for c in columns if c.pk) for table, columns in SCHEMA.tables.items()
}
MASTER_TABLES: frozenset[str] = frozenset(
    table
    for table, kind in json.loads(PACKAGED_SCHEMA.read_text(encoding="utf-8"))[
        "classification"
    ].items()
    if kind == "master"
)
# Tables that hold no case_id of their own but belong to a case through their document.
_THROUGH_DOCUMENT = frozenset({"dong_ct", "thanh_toan"})

# Written only by their own tools (request_approval/decide_approval, pay, the event
# log), never through a token's draft set or update_status.
OWN_TOOL_TABLES: frozenset[str] = frozenset({"phe_duyet", "thanh_toan", "su_kien"})

APPROVED = "Đã duyệt"
REJECTED = "Từ chối"
PENDING = "Chờ duyệt"
PAID = "Đã chi"
CANCELLED_PAYMENT = "Đã hủy"
MATCHED = "Khớp"
NEEDS_CHECK = "Cần kiểm"


@dataclass(frozen=True)
class CoreContext:
    """Everything a generic tool may reach. ``token`` is None for the engine and the environment."""

    conn: psycopg.Connection[Any]
    case_id: str
    actor: str
    actor_kind: str
    token: TaskToken | None
    gate: BusinessGate
    governance_version: str
    step_id: str
    mail: MailSender | None
    # The gate tier: the tool-tier platform-rule checks. False only with an OpenGate.
    gate_checks: bool = True
    # The token tier's ceiling check in require_draft (the toolbox reads it too).
    token_checks: bool = True

    def __post_init__(self) -> None:
        # An open gate never stands in for the real one in a run whose gate tier is on,
        # and the gate tier is never off with the real gate in place.
        if self.gate_checks == isinstance(self.gate, OpenGate):
            raise ValueError(
                "gate_checks must be False exactly when the gate is an OpenGate"
                f" (gate_checks={self.gate_checks}, gate={type(self.gate).__name__})"
            )


# --- token checks -----------------------------------------------------------------


def require_tool(ctx: CoreContext, name: str) -> None:
    """Refuse before anything else when the caller's token does not carry ``name``.

    A digital employee always acts on a task token, issued to it for this case.
    """
    token = ctx.token
    if token is None:
        if ctx.actor_kind == "so":
            raise ToolDenied(
                f"{ctx.actor} may not call {name}: a digital employee needs a task token"
            )
        return
    if token.sub != ctx.actor:
        raise ToolDenied(
            f"{ctx.actor} may not call {name}: the task token was issued to {token.sub}"
        )
    if token.case_id != ctx.case_id:
        raise ToolDenied(
            f"{ctx.actor} may not call {name}: the task token is for case {token.case_id},"
            f" not {ctx.case_id}"
        )
    if name not in token.tools:
        raise ToolDenied(f"{ctx.actor} may not call {name}: not in task token")


def require_draft(ctx: CoreContext, table: str) -> None:
    """Refuse a write to ``table`` that the caller's token does not let it draft.

    Rule 5 holds here too: a token is only ever issued within the platform ceiling,
    but a write beyond the ceiling's draft set is refused even if a token claims it
    (skipped with the token tier off: ``token_checks``).
    """
    if ctx.token is not None and table not in ctx.token.draft:
        raise ToolDenied(f"{ctx.actor} may not write {table}: not in task token draft scope")
    ceiling = PLATFORM_CEILING.get(ctx.actor_kind)
    if ctx.token_checks and ceiling is not None and table not in ceiling.draft:
        raise ToolDenied(
            f"platform rule 5: {ctx.actor} may not write {table}: beyond the platform ceiling"
            f" for actor kind {ctx.actor_kind}"
        )


def require_read(ctx: CoreContext, table: str) -> None:
    if ctx.token is not None and table not in ctx.token.read:
        raise ToolDenied(f"{ctx.actor} may not read {table}: not in task token scope")


# --- acting and reading -------------------------------------------------------------


def _platform_message(exc: psycopg.Error) -> str | None:
    diag = getattr(exc, "diag", None)
    message = (diag.message_primary if diag is not None else None) or ""
    if message.startswith(("platform rule", "platform gate")):
        return message
    return None


@contextmanager
def acting(ctx: CoreContext) -> Iterator[Cursor]:
    """One tool call's writes, as ``ctx.actor``, rolled back alone on any refusal."""
    try:
        with (
            acting_as(ctx.conn, ctx.actor, ctx.actor_kind, ctx.governance_version) as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            yield cur
    except psycopg.Error as exc:
        message = _platform_message(exc)
        if message is None:
            raise
        raise ToolDenied(message) from exc
    except GateRefused as exc:
        raise ToolDenied(f"business gate: {exc}") from exc


@contextmanager
def reading(ctx: CoreContext) -> Iterator[Cursor]:
    """A read in its own (sub)transaction, so it never leaves the connection idle in one."""
    with ctx.conn.transaction(), ctx.conn.cursor(row_factory=dict_row) as cur:
        yield cur


def record(cur: Cursor, ctx: CoreContext, kind: str, ref: str, mo_ta: str | None = None) -> int:
    """Append the call's one event. The database sets actor, governance version, id and time."""
    row = cur.execute(
        "INSERT INTO core.su_kien (case_id, buoc, kind, ref, actor, mo_ta)"
        " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (ctx.case_id, ctx.step_id, kind, ref, ctx.actor, mo_ta),
    ).fetchone()
    assert row is not None
    return int(row["id"])


# --- case-scoped rows ---------------------------------------------------------------


def check_table(table: str) -> None:
    if table not in COLUMNS:
        raise ToolDenied(f"unknown table {table!r}")


def check_columns(table: str, names: Mapping[str, Any] | list[str]) -> None:
    unknown = sorted(set(names) - set(COLUMNS[table]))
    if unknown:
        raise ToolDenied(f"{table} has no column(s) {unknown}")


# The values a filter (``where``, a key) may hold: what JSON gives as a scalar.
FILTER_SCALARS = (str, int, float, bool, type(None))


def _kind_name(value: Any) -> str:
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list | tuple):
        return "array"
    return type(value).__name__


def check_values(table: str, where: Mapping[str, Any]) -> None:
    """Refuse a filter value that is not a scalar, naming its column, before any query.

    Equality filters only: there is no IN filter, so a list is refused like an object
    (Task 15 fix round 2; it once reached the driver and came back as its own text)."""
    for column, value in where.items():
        if not isinstance(value, FILTER_SCALARS):
            raise ToolDenied(
                f"{table}.{column}: a filter value must be a text, a number, true/false or"
                f" null, not a {_kind_name(value)}"
            )


def query_refusal(tool: str) -> ToolDenied:
    """The refusal a database error that is no platform rule becomes, at the toolbox:
    it names the tool and never carries the driver's or the query's text."""
    return ToolDenied(f"{tool}: lỗi truy vấn cơ sở dữ liệu; lời gọi không được thực hiện")


def database_refusal(tool: str, exc: psycopg.Error) -> ToolDenied:
    """A platform rule or gate keeps its own message; any other database error is
    ``query_refusal``."""
    message = _platform_message(exc)
    return ToolDenied(message) if message is not None else query_refusal(tool)


def select_rows(
    cur: Cursor,
    ctx: CoreContext,
    table: str,
    where: Mapping[str, Any],
    *,
    lock: bool = False,
) -> list[dict[str, Any]]:
    """Rows of ``table`` matching ``where`` (equality; None is IS NULL), within the case.

    Master tables belong to no case and are read whole. ``lock`` takes row locks
    (``FOR UPDATE``) on the rows read, for a read that a write then depends on.
    """
    check_table(table)
    check_columns(table, where)
    check_values(table, where)
    t = sql.Identifier("t")
    conditions: list[sql.Composable] = []
    params: list[Any] = []
    for column, value in where.items():
        col = sql.SQL("{}.{}").format(t, sql.Identifier(column))
        if value is None:
            conditions.append(sql.SQL("{} IS NULL").format(col))
        else:
            conditions.append(sql.SQL("{} = %s").format(col))
            params.append(value)
    source = sql.SQL("{}.{} AS t").format(sql.Identifier(CORE_SCHEMA_NAME), sql.Identifier(table))
    if "case_id" in COLUMNS[table]:
        conditions.append(sql.SQL("t.case_id = %s"))
        params.append(ctx.case_id)
    elif table in _THROUGH_DOCUMENT:
        source = sql.SQL("{} JOIN core.chung_tu AS doc ON doc.ma_ct = t.ma_ct").format(source)
        conditions.append(sql.SQL("doc.case_id = %s"))
        params.append(ctx.case_id)
    query = sql.SQL("SELECT t.* FROM {}").format(source)
    if conditions:
        query = sql.SQL("{} WHERE {}").format(query, sql.SQL(" AND ").join(conditions))
    query = sql.SQL("{} ORDER BY t.{}").format(query, sql.Identifier(PRIMARY_KEY[table]))
    if lock:
        query = sql.SQL("{} FOR UPDATE OF t").format(query)
    return cur.execute(query, params).fetchall()


def one_row(
    cur: Cursor, ctx: CoreContext, table: str, where: Mapping[str, Any], *, lock: bool = False
) -> dict[str, Any]:
    found = select_rows(cur, ctx, table, where, lock=lock)
    if len(found) != 1:
        raise ToolDenied(
            f"expected exactly one {table} row matching {dict(where)} in case {ctx.case_id},"
            f" found {len(found)}"
        )
    return found[0]


def exists(cur: Cursor, query: str, params: tuple[Any, ...]) -> bool:
    row = cur.execute(f"SELECT EXISTS ({query}) AS e", params).fetchone()
    return row is not None and bool(row["e"])


def opened_this_run(cur: Cursor, ctx: CoreContext, ma_pd: str) -> bool:
    """An approval this run requested. Given approvals are history: they never clear a gate.

    A run starts from an empty ``core`` and given data carries no events (an event
    needs a session actor), so a REQUESTED event marks an approval of this run.
    """
    return exists(
        cur,
        "SELECT 1 FROM core.su_kien WHERE case_id = %s AND kind = 'REQUESTED' AND ref = %s",
        (ctx.case_id, ma_pd),
    )


def as_decimal(value: Any, what: str) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise ToolDenied(f"{what} is not a number: {value!r}") from None
    if not number.is_finite():
        raise ToolDenied(f"{what} is not a finite number: {value!r}")
    return number


def text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolDenied(f"{what} must be a non-blank text, got {value!r}")
    return value.strip()

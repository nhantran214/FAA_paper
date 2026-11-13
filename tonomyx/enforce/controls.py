"""Control switches: run the same engine with enforcement tiers turned off (experiments).

The baseline arms of the evaluation (prompt-only, bare, guards, no-database) run the
platform with some of its tiers switched off. ``Controls`` names the three tiers:

- ``tokens``: the scope and task token, the step's tools and argument bindings, and
  the platform ceiling (rule 5 at the token and tool tiers);
- ``gate``: the business gate and the tool-tier platform-rule checks (rules 1-4, the
  status rules, the money rule);
- ``database``: the platform-rule triggers on schema ``core``.

The schema itself is always on (the tables must exist), as are type coercion, case
scoping and the event log: an event still gets its id, time, actor and governance
version from ``pr6_event`` (``KEPT_TRIGGERS``), because scoring reads them.

Controls are an argument of ``run_case`` only. No declaration (template, pack or
policy) can carry one: the loaders refuse the keys ``controls`` and ``enforcement``.

Database tier. ``apply_database_control`` enables or disables every non-internal
trigger on a ``core`` table whose name starts with ``RULE_TRIGGER_PREFIX`` and is not
kept, found in ``pg_trigger``, in one transaction, and then reads the catalogue back
to confirm the state. Trigger state is catalogue state: it outlives the connection,
so ``run_case`` sets it at the start of every run and sets ``FULL`` again in a
``finally``. Altering a table's triggers needs its owner (or a member of the owner
role); a role that is not refuses with ``ControlError`` before anything changes, so a
run never goes on with the triggers in a state it did not ask for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import tuple_row

from tonomyx.core.schema import CORE_SCHEMA_NAME

RULE_TRIGGER_PREFIX = "pr"
# pr6_event assigns the event id, time, actor and governance version: always on.
KEPT_TRIGGERS: frozenset[str] = frozenset({"pr6_event"})

# The keys a declaration may never hold: a tier is switched off by the caller of
# run_case, never by what a company or a template declares.
DECLARATION_FORBIDDEN_KEYS: frozenset[str] = frozenset({"controls", "enforcement"})


@dataclass(frozen=True)
class Controls:
    """The three switches; each must be a real ``bool`` (Task 5 M1: ``None`` or ``0``
    would read as off, so a stand-in is refused, ``TypeError``)."""

    tokens: bool = True
    gate: bool = True
    database: bool = True

    def __post_init__(self) -> None:
        for name in ("tokens", "gate", "database"):
            value = getattr(self, name)
            if type(value) is not bool:
                raise TypeError(f"Controls.{name} must be True or False, not {value!r}")


FULL = Controls()
NONE = Controls(False, False, False)


class ControlError(RuntimeError):
    """The database tier could not be set as asked; the run must not go on."""


def forbidden_declaration_keys(raw: Any) -> list[str]:
    """The keys of a declaration's top level that would carry a control switch."""
    if not isinstance(raw, dict):
        return []
    return sorted(DECLARATION_FORBIDDEN_KEYS & set(raw))


def _rule_triggers(cur: psycopg.Cursor[Any]) -> list[tuple[str, str, bool, str]]:
    """(table, trigger, the current role may alter the table, tgenabled) per rule trigger."""
    rows = cur.execute(
        "SELECT c.relname, t.tgname, pg_has_role(current_user, c.relowner, 'USAGE'),"
        " t.tgenabled::text"
        " FROM pg_trigger t"
        " JOIN pg_class c ON c.oid = t.tgrelid"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = %s AND NOT t.tgisinternal AND starts_with(t.tgname, %s)"
        " ORDER BY c.relname, t.tgname",
        (CORE_SCHEMA_NAME, RULE_TRIGGER_PREFIX),
    ).fetchall()
    return [(str(r[0]), str(r[1]), bool(r[2]), str(r[3])) for r in rows]


def apply_database_control(conn: psycopg.Connection[Any], controls: Controls) -> None:
    """Enable (``controls.database``) or disable every rule trigger on ``core`` but the
    kept ones, which are always enabled. Raises ``ControlError`` when the triggers are
    missing, when the current role may not alter their tables, or when the catalogue
    does not read back as asked; then nothing has changed.

    Runs in ``conn.transaction()``: committed on return when the connection was idle,
    a savepoint of the caller's open transaction otherwise."""
    with conn.transaction(), conn.cursor(row_factory=tuple_row) as cur:
        found = _rule_triggers(cur)
        names = {name for _, name, _, _ in found}
        if not found or not names >= KEPT_TRIGGERS:
            raise ControlError(
                f"schema {CORE_SCHEMA_NAME} has no platform-rule triggers"
                f" (found {sorted(names)}); reset the schema before a run"
            )
        refused = sorted({table for table, _, may_alter, _ in found if not may_alter})
        if refused:
            raise ControlError(
                "the connection's role may not switch the platform-rule triggers: it does"
                f" not own core table(s) {refused}; run as the owner of schema"
                f" {CORE_SCHEMA_NAME}"
            )
        if controls.database:
            mode = cur.execute("SELECT current_setting('session_replication_role')").fetchone()
            if mode is None or mode[0] != "origin":
                raise ControlError(
                    "session_replication_role is not 'origin': the platform-rule triggers"
                    " would not fire on this connection"
                )
        for table, name, _, _ in found:
            on = controls.database or name in KEPT_TRIGGERS
            try:
                cur.execute(
                    sql.SQL("ALTER TABLE {}.{} {} TRIGGER {}").format(
                        sql.Identifier(CORE_SCHEMA_NAME),
                        sql.Identifier(table),
                        sql.SQL("ENABLE" if on else "DISABLE"),
                        sql.Identifier(name),
                    )
                )
            except psycopg.errors.InsufficientPrivilege as exc:
                raise ControlError(
                    f"the connection's role may not switch the platform-rule triggers:"
                    f" {table}.{name}: {exc}"
                ) from exc
        wrong = [
            f"{table}.{name}={state}"
            for table, name, _, state in _rule_triggers(cur)
            if state != ("O" if controls.database or name in KEPT_TRIGGERS else "D")
        ]
        if wrong:
            raise ControlError(f"platform-rule triggers did not take the asked state: {wrong}")

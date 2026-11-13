"""Build schema ``core`` and run actions in it under a named actor.

``reset_core`` only ever touches schema ``core``; it leaves ``public`` alone.
``acting_as`` is how every action reaches the database: the platform-rule
triggers in ``platform_rules.sql`` read the actor, its kind and the governance
version from the session values it sets.

Loading versus acting (ruling R2a). Rules 1-5 and the approver gate bind actors
only: they fire when ``tonomyx.actor_kind`` is set, that is inside ``acting_as``.
The platform loads master rows, a case's starting data and the released money
values in ``core.nguon_tien`` on a plain connection, outside ``acting_as``, and
those triggers stand aside. A case's given state may hold what no actor could
write now, such as a payment already marked paid with no approval. The engine
relies on this to load a case. Rule 6 binds everyone: ``core.su_kien`` is
append-only, and an event row needs a session actor and governance version, so
events are only ever written inside ``acting_as``. ``core.nguon_tien`` is the
reverse of the master tables: no actor kind may write it, the engine included.

Trust boundary (ruling R2h). The database tier trusts the ``tonomyx.*`` session
settings. Only the platform's tool layer sets them, through ``acting_as``; actors
(digital employees, people, outside parties) never get a raw connection, so they
can neither set those values nor disable a trigger. The connection runs as the
owner of schema ``core``, which could do both; a separate non-owner database role
for acting connections is later hardening (sub-project C).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from tonomyx.core.ddl import render_ddl
from tonomyx.core.schema import CORE_SCHEMA_NAME, load_core_schema

# dieu_phoi: the engine; so: a digital employee; nguoi: a person; ngoai: an outside party.
ACTOR_KINDS: tuple[str, ...] = ("dieu_phoi", "so", "nguoi", "ngoai")

PLATFORM_RULES_SQL = Path(__file__).with_name("platform_rules.sql")

_SETTINGS = ("tonomyx.actor", "tonomyx.actor_kind", "tonomyx.governance_version")


def reset_core(conn: psycopg.Connection[Any]) -> None:
    """Drop and recreate schema ``core``: the tables, then the platform rules.

    Runs in ``conn.transaction()``: committed on return when the connection was
    idle, or a savepoint of the caller's open transaction otherwise.
    """
    schema = sql.Identifier(CORE_SCHEMA_NAME)
    with conn.transaction():
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(schema))
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
        conn.execute(render_ddl(load_core_schema()))
        conn.execute(PLATFORM_RULES_SQL.read_text(encoding="utf-8"))


@contextmanager
def acting_as(
    conn: psycopg.Connection[Any], actor: str, kind: str, governance_version: str
) -> Iterator[psycopg.Connection[Any]]:
    """Run the block as one transaction of ``actor``, with the session values set.

    Commits on normal exit and rolls back on an exception, as ``conn.transaction()``
    does. Inside an already open transaction it becomes a savepoint; the previous
    session values are then restored on exit, so they never outlive the block.
    """
    if kind not in ACTOR_KINDS:
        raise ValueError(f"unknown actor kind {kind!r}; expected one of {ACTOR_KINDS}")
    if not actor or not governance_version:
        raise ValueError("acting_as needs an actor and a governance version")
    with conn.transaction():
        row = conn.execute(
            "SELECT " + ", ".join(f"current_setting(%s, true) AS s{i}" for i in range(3)),
            _SETTINGS,
        ).fetchone()
        previous = [None, None, None] if row is None else list(_values(row))
        for name, value in zip(_SETTINGS, (actor, kind, governance_version), strict=True):
            conn.execute(sql.SQL("SET LOCAL {} = {}").format(sql.SQL(name), sql.Literal(value)))
        yield conn
        # Reached only on success: on an exception the rollback restores them.
        for name, old in zip(_SETTINGS, previous, strict=True):
            conn.execute("SELECT set_config(%s, %s, true)", (name, old or ""))


def _values(row: Any) -> tuple[Any, ...]:
    return tuple(row.values()) if isinstance(row, dict) else tuple(row)

"""Render the core schema as PostgreSQL DDL, every object qualified with schema ``core``.

The output creates the tables (types, primary keys, NOT NULL, vocabulary CHECKs),
then the foreign keys, then the platform's own table ``core.nguon_tien``, then
``core.event_kinds()``, the list the event trigger in ``platform_rules.sql`` checks
kinds against. It never creates the schema itself: ``reset_core`` does that.
"""

from __future__ import annotations

import re

from tonomyx.core.schema import CORE_SCHEMA_NAME, Column, CoreSchema

EVENT_TABLE = "su_kien"

# Columns the event log carries beyond the JSON: the governance version that
# allowed the action (rule 6) and when it happened. A trigger fills the version.
_EVENT_EXTRA_COLUMNS = (
    "governance_version text NOT NULL",
    "at timestamptz NOT NULL DEFAULT now()",
)

# Money values the platform has released to one case (facts, policy amounts): a
# source for rule 3. It is not in core_schema.json, which is the bench's copy;
# only the platform writes it (rule 5 refuses every write under an actor kind).
MONEY_SOURCE_TABLE = "nguon_tien"
_MONEY_SOURCE_DDL = f"""CREATE TABLE {CORE_SCHEMA_NAME}.{MONEY_SOURCE_TABLE} (
  case_id text NOT NULL REFERENCES {CORE_SCHEMA_NAME}.ho_so (case_id),
  ten text NOT NULL,
  gia_tri bigint,
  PRIMARY KEY (case_id, ten)
);"""

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def _ident(name: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"not a plain identifier: {name!r}")
    return name


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(_literal(v) for v in values)


def _qualified(table: str) -> str:
    return f"{CORE_SCHEMA_NAME}.{_ident(table)}"


def _platform_keyed(column: Column, append_only: bool) -> bool:
    """An append-only table's int key is drawn by the platform's trigger, never a caller."""
    return append_only and column.type == "int" and column.pk


def _column_sql(column: Column, append_only: bool) -> str:
    if _platform_keyed(column, append_only):
        sql_type = "integer"  # no default: the event trigger assigns it from the sequence
    elif column.type == "int" and column.pk:
        sql_type = "serial"
    elif column.type == "int":
        sql_type = "integer"
    else:
        sql_type = column.type
    not_null = "" if column.nullable else " NOT NULL"
    return f"{_ident(column.name)} {sql_type}{not_null}"


def _create_table(table: str, columns: tuple[Column, ...], schema: CoreSchema) -> str:
    append_only = table in schema.append_only
    parts = [_column_sql(c, append_only) for c in columns]
    if table == EVENT_TABLE:
        parts.extend(_EVENT_EXTRA_COLUMNS)
    keys = [c.name for c in columns if c.pk]
    if keys:
        parts.append(f"PRIMARY KEY ({', '.join(keys)})")
    for column in columns:
        allowed = schema.vocab.get(f"{table}.{column.name}")
        if allowed:
            parts.append(
                f"CONSTRAINT {table}_{column.name}_vocab"
                f" CHECK ({column.name} IN ({_in_list(allowed)}))"
            )
    if table == EVENT_TABLE:
        parts.append(
            f"CONSTRAINT {table}_kind_known CHECK (kind IN ({_in_list(schema.event_kinds)}))"
        )
    body = ",\n  ".join(parts)
    return f"CREATE TABLE {_qualified(table)} (\n  {body}\n);"


def _foreign_keys(table: str, columns: tuple[Column, ...]) -> list[str]:
    statements = []
    for column in columns:
        if column.fk is None:
            continue
        ref_table, ref_column = column.fk.split(".")
        statements.append(
            f"ALTER TABLE {_qualified(table)} ADD CONSTRAINT {table}_{column.name}_fkey"
            f" FOREIGN KEY ({_ident(column.name)})"
            f" REFERENCES {_qualified(ref_table)} ({_ident(ref_column)});"
        )
    return statements


def _key_sequences(table: str, columns: tuple[Column, ...], schema: CoreSchema) -> list[str]:
    append_only = table in schema.append_only
    return [
        f"CREATE SEQUENCE {_qualified(table)}_{_ident(c.name)}_seq"
        f" OWNED BY {_qualified(table)}.{_ident(c.name)};"
        for c in columns
        if _platform_keyed(c, append_only)
    ]


def _event_kinds_function(schema: CoreSchema) -> str:
    return (
        f"CREATE FUNCTION {CORE_SCHEMA_NAME}.event_kinds() RETURNS text[]\n"
        f"LANGUAGE sql IMMUTABLE AS $$ SELECT ARRAY[{_in_list(schema.event_kinds)}]::text[] $$;"
    )


def render_ddl(schema: CoreSchema) -> str:
    statements = [_create_table(t, cols, schema) for t, cols in schema.tables.items()]
    for table, columns in schema.tables.items():
        statements.extend(_key_sequences(table, columns, schema))
        statements.extend(_foreign_keys(table, columns))
    statements.append(_MONEY_SOURCE_DDL)
    statements.append(_event_kinds_function(schema))
    return "\n\n".join(statements) + "\n"

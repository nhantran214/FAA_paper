"""The platform's core schema (spec C1), parsed from the packaged ``core_schema.json``.

The JSON is a byte-for-byte copy of ``data/bench_v1/core_schema.json``. Every
process shares these eleven tables; a process never adds a table of its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CORE_SCHEMA_NAME = "core"

PACKAGED_SCHEMA = Path(__file__).with_name("core_schema.json")

COLUMN_TYPES: frozenset[str] = frozenset({"text", "bigint", "numeric", "int"})


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    pk: bool
    nullable: bool
    fk: str | None  # "table.column", or None


@dataclass(frozen=True)
class CoreSchema:
    tables: dict[str, tuple[Column, ...]]
    vocab: dict[str, tuple[str, ...]]  # "table.column" -> allowed values
    event_kinds: tuple[str, ...]
    append_only: tuple[str, ...]
    money_base: dict[str, tuple[str, ...]]
    derived: dict[str, tuple[str, ...]]


def _column(table: str, raw: dict[str, Any]) -> Column:
    kind = raw["type"]
    if kind not in COLUMN_TYPES:
        raise ValueError(f"{table}.{raw['name']}: unknown column type {kind!r}")
    pk = bool(raw.get("pk", False))
    return Column(
        name=raw["name"],
        type=kind,
        pk=pk,
        nullable=bool(raw.get("nullable", False)) and not pk,
        fk=raw.get("fk"),
    )


def _str_tuples(raw: dict[str, list[str]]) -> dict[str, tuple[str, ...]]:
    return {key: tuple(values) for key, values in raw.items()}


def load_core_schema(path: Path = PACKAGED_SCHEMA) -> CoreSchema:
    raw = json.loads(path.read_text(encoding="utf-8"))
    tables = {
        table: tuple(_column(table, c) for c in columns) for table, columns in raw["tables"].items()
    }
    return CoreSchema(
        tables=tables,
        vocab=_str_tuples(raw["vocab"]),
        event_kinds=tuple(raw["event_kinds"]),
        append_only=tuple(raw["append_only"]),
        money_base=_str_tuples(raw["money_base"]),
        derived=_str_tuples(raw["derived"]),
    )

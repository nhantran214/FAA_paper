"""Shared helpers of the baseline defences: what they read from the declarations.

The evaluation sets architectural enforcement against original-code baselines (the
bridges of ``aebench.arms.bridges``, built by ``aebench.arms.defence.build_defence``).
Where a baseline needs the enterprise's rules (categories, rails, capabilities), it reads
them through these helpers, from what the system sees: the company pack (roles, approval
rules, caps), the shared process template (the roles' scopes), the platform's core tools
and the core schema. Nothing here takes a case folder or an answer file.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from tonomyx.core.schema import load_core_schema
from tonomyx.enforce.tokens import scope_tools
from tonomyx.governance.pack import CompanyPack
from tonomyx.governance.template import ProcessTemplate
from tonomyx.tools.core.context import APPROVED, PAID
from tonomyx.tools.core.documents import NOT_FOR_DIGITAL_EMPLOYEES

# Statuses a digital employee never sets: the platform's own list, plus the words of a
# sent or issued document that the v1 prompts also named.
TERMINAL_STATUSES: frozenset[str] = NOT_FOR_DIGITAL_EMPLOYEES | {
    APPROVED, PAID, "Đã gửi", "Đã phát hành"}
# The core tables each core tool writes or reads when the call does not name one
# (mirrors tonomyx/tools/core: create_document, reconcile, pay and search_kb).
# create_document writes dong_ct only when its call carries lines (LINE_TABLE).
WRITES: dict[str, frozenset[str]] = {
    "create_document": frozenset({"chung_tu"}),
    "reconcile": frozenset({"chung_tu"}),
    "pay": frozenset({"thanh_toan"}),
}
LINE_TABLE = "dong_ct"
NAMED_TABLE_WRITERS = frozenset({"update_status"})  # the call names the table
NAMED_TABLE_READERS = frozenset({"read_records"})
KB_TABLE = "tri_thuc"


@dataclass(frozen=True)
class Capabilities:
    """What digital employees of the template may touch: the union of the scopes of its
    ``so`` roles (the executor does not tell a defence which role is acting), or one role's."""

    tools: frozenset[str]
    read: frozenset[str]
    draft: frozenset[str]

    @classmethod
    def from_template(cls, template: ProcessTemplate, role: str | None = None) -> Capabilities:
        scopes = [r.scope for r in template.roles
                  if r.scope is not None and (role is None or r.id == role)]
        tools: frozenset[str] = frozenset().union(*(scope_tools(s) for s in scopes))
        return cls(tools, frozenset().union(*(s.read for s in scopes)),
                   frozenset().union(*(s.draft for s in scopes)))


def _digital_employees_decide(pack: CompanyPack) -> bool:
    """Whether the company lets any of its digital employees decide an approval."""
    return any(r.decides for r in pack.roles if r.kind == "so")


def _cap_fields(pack: CompanyPack) -> dict[str, Decimal]:
    """The line fields the pack caps: a cap ``<field>_toi_da`` bounds ``<field>``."""
    suffix = "_toi_da"
    return {name[: -len(suffix)]: cap for name, cap in pack.policy.caps.items()
            if name.endswith(suffix) and len(name) > len(suffix)}


def _log_tables() -> frozenset[str]:
    return frozenset(load_core_schema().append_only)


def _values(value: Any, key: str) -> Iterable[Any]:
    """Every value under a mapping key ``key``, at any depth."""
    if isinstance(value, Mapping):
        for k, v in value.items():
            if k == key:
                yield v
            yield from _values(v, key)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _values(v, key)


def _tables_of(tool: str, args: Mapping[str, Any]) -> tuple[frozenset[str], frozenset[str]]:
    """The (written, read) core tables of one call."""
    table = args.get("table")
    named = frozenset({table}) if isinstance(table, str) and table else frozenset()
    lines = args.get("lines")
    with_lines = tool == "create_document" and isinstance(lines, list) and bool(lines)
    written = WRITES.get(tool, frozenset()) | (
        named if tool in NAMED_TABLE_WRITERS else frozenset()) | (
        frozenset({LINE_TABLE}) if with_lines else frozenset())
    read = (named if tool in NAMED_TABLE_READERS else frozenset()) | (
        frozenset({KB_TABLE}) if tool == "search_kb" else frozenset())
    return written, read


def _scope_line(caps: Capabilities) -> str:
    return ", ".join(sorted(caps.tools)) or "-"

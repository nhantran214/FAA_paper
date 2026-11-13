"""Process template: roles with duties, and steps of the 14 platform step types.

A template is shared by every run of it, and the engine hands each step to its actor.
So a step's ``params`` and ``on`` are deep-frozen when the step is made: mappings become
read-only views (``MappingProxyType``), lists become tuples, sets frozensets. An actor
that tries to rewrite its step (say ``step.on["pass"] = "end"``) gets a ``TypeError``,
and the template every later run reads is the one that was loaded. ``thaw`` turns a
frozen value back into plain JSON-ready dicts and lists.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

from tonomyx.enforce.controls import forbidden_declaration_keys

OUTCOME_KEYS = frozenset(
    {"pass", "flag", "approved", "rejected", "pending", "skipped", "refused"}
)
_STEP_TYPES_PATH = Path(__file__).with_name("step_types.json")


class TemplateError(ValueError):
    pass


def freeze(value: Any) -> Any:
    """``value`` with every mapping read-only, every list a tuple, every set a frozenset."""
    if isinstance(value, Mapping):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(freeze(v) for v in value)
    if isinstance(value, set | frozenset):
        return frozenset(freeze(v) for v in value)
    return value


def thaw(value: Any) -> Any:
    """A frozen value as plain dicts and lists (``json.dumps`` takes it); sets sorted."""
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [thaw(v) for v in value]
    if isinstance(value, set | frozenset):
        return sorted(thaw(v) for v in value)
    return value


@dataclass(frozen=True)
class Duties:
    drafts: frozenset[str] = frozenset()
    may_request: bool = False
    decides: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RoleScope:
    tools: frozenset[str]
    read: frozenset[str]
    draft: frozenset[str]
    may_open_approvals: bool
    budget_usd: Decimal
    autonomy: str


@dataclass(frozen=True)
class TemplateRole:
    id: str
    kind: str
    duties: Duties
    scope: RoleScope | None
    # An optional role may bind to no company role: its steps are then skipped.
    optional: bool = False


@dataclass(frozen=True)
class TemplateStep:
    id: str
    type: str
    role: str
    params: Mapping[str, Any] = field(default_factory=dict)
    guidance: str = ""
    optional: bool = False
    next: str | None = None
    on: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Deep-frozen: an actor handed this step cannot rewrite the shared template.
        object.__setattr__(self, "params", freeze(self.params))
        object.__setattr__(self, "on", freeze(self.on))


@dataclass(frozen=True)
class ProcessTemplate:
    id: str
    name: str
    version: str
    roles: tuple[TemplateRole, ...]
    start: str
    steps: dict[str, TemplateStep]


def declared(value: Any) -> frozenset[str]:
    """The names a step declares for one thing (``loai_ct``, ``loai_pd``): a text, or a
    list of texts (the names companies give one document or approval). Anything else
    declares nothing."""
    if isinstance(value, str):
        return frozenset({value})
    if isinstance(value, list | tuple | set | frozenset):
        return frozenset(str(v) for v in value)
    return frozenset()


def _named(value: Any, names: frozenset[str]) -> bool:
    """Whether a step's ``doc``/``id`` is one of ``names``; a value that is not a text
    names nothing (a malformed declaration must not crash a lookup)."""
    return isinstance(value, str) and value in names


# Step types that make a document named by their ``doc`` param, of their ``loai_ct``.
DOCUMENT_STEPS = frozenset({"create_document", "record_external_fact"})


def document_types(template: ProcessTemplate, doc: Any) -> frozenset[str] | None:
    """The ``loai_ct`` the template declares for the document(s) its steps call ``doc`` (a
    text, or a list of such names): the union over the steps that make them. None when no
    such step declares one."""
    names = declared(doc)
    found = [
        declared(s.params["loai_ct"])
        for s in template.steps.values()
        if s.type in DOCUMENT_STEPS and _named(s.params.get("doc"), names)
        and "loai_ct" in s.params
    ]
    return frozenset().union(*found) if found else None


def approval_types(template: ProcessTemplate, approval: Any) -> frozenset[str] | None:
    """The ``loai_pd`` the template declares for the approval(s) its request steps call
    ``approval`` (their ``id``; a text, or a list of ids): the union over those steps. None
    when none declares one."""
    ids = declared(approval)
    found = [
        declared(s.params["loai_pd"])
        for s in template.steps.values()
        if s.type == "request_approval" and _named(s.params.get("id"), ids)
        and "loai_pd" in s.params
    ]
    return frozenset().union(*found) if found else None


def _step_types() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(_STEP_TYPES_PATH.read_text(encoding="utf-8"))
    return loaded


def _fs(v: Any) -> frozenset[str]:
    return frozenset(v or ())


def _draft_scope(v: Any) -> frozenset[str]:
    """A template role's draft scope. A document is drafted with its lines: a scope that
    drafts ``chung_tu`` also drafts ``dong_ct``, the platform's own rule for company roles
    (``tonomyx.enforce.tokens.DOCUMENT_TABLES``) applied on the template side (Task 15).
    It never leaves the ceiling: ``dong_ct`` is in it wherever ``chung_tu`` is."""
    draft = _fs(v)
    return draft | {"dong_ct"} if "chung_tu" in draft else draft


def _role(raw: dict[str, Any], kinds: list[str]) -> TemplateRole:
    rid, kind = raw["id"], raw["kind"]
    if kind not in kinds:
        raise TemplateError(f"role {rid}: unknown kind {kind!r}")
    d = raw.get("duties") or {}
    duties = Duties(_fs(d.get("drafts")), bool(d.get("may_request", False)), _fs(d.get("decides")))
    scope = None
    if kind == "so":
        s = raw.get("scope")
        if not s:
            raise TemplateError(f"role {rid}: kind 'so' requires a scope")
        scope = RoleScope(_fs(s.get("tools")), _fs(s.get("read")), _draft_scope(s.get("draft")),
                          bool(s.get("may_open_approvals", False)),
                          Decimal(str(s["budget_usd"])), s["autonomy"])
    return TemplateRole(rid, kind, duties, scope, bool(raw.get("optional", False)))


def load_template(path: Path) -> ProcessTemplate:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    forbidden = forbidden_declaration_keys(raw)
    if forbidden:
        raise TemplateError(
            f"template declares {forbidden}: enforcement is switched only by the caller of"
            " run_case, never by a declaration"
        )
    types = _step_types()
    roles = tuple(_role(r, types["actor_kinds"]) for r in raw["roles"])
    kind_of = {r.id: r.kind for r in roles}
    steps: dict[str, TemplateStep] = {}
    for s in raw["steps"]:
        sid = s["id"]
        if sid in steps:
            raise TemplateError(f"step {sid}: duplicate id")
        if s["type"] not in types["types"]:
            raise TemplateError(f"step {sid}: unknown step type {s['type']!r}")
        if s["role"] not in kind_of:
            raise TemplateError(f"step {sid}: unknown role {s['role']!r}")
        on = s.get("on") or {}
        bad = sorted(set(on) - OUTCOME_KEYS)
        if bad:
            raise TemplateError(f"step {sid}: unknown outcome key(s) {bad}")
        steps[sid] = TemplateStep(sid, s["type"], s["role"], dict(s.get("params") or {}),
                                  s.get("guidance", ""), bool(s.get("optional", False)),
                                  s.get("next"), dict(on))
    if raw["start"] not in steps:
        raise TemplateError(f"start step {raw['start']!r} does not exist")
    return ProcessTemplate(raw["id"], raw["name"], raw["version"], roles, raw["start"], steps)

"""Governance validator: the automatic checks a process template must pass.

It never raises on a template built in code: an unknown step type, a missing start
step, an outcome key or a target that is not a text are findings, not crashes. With a
company pack it also checks the pack: role codes are unique, every approval tier's
approver is a person of the pack, and a rule's tiers rise (maxima ascending, the open
tier, with no maximum, last).

With a pack it also maps the template roles to the pack's roles (``map_roles``): a role
that cannot be mapped (no company role of its kind) is the error ``BINDING``; a role
mapped by the best overlap of duties rather than an exact match is the warning
``INEXACT_BINDING``.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from tonomyx.enforce.ceiling import AUTONOMY_ORDER, PLATFORM_CEILING

from .binding import BindingError, map_roles
from .pack import CompanyPack
from .template import OUTCOME_KEYS, ProcessTemplate, TemplateStep, _step_types

_CONCRETE_ID = re.compile(r"^[A-Z]{2,}[A-Z0-9-]*-\d+$")
_TERMINAL = ("stop", "wait")


@dataclass(frozen=True)
class Finding:
    level: Literal["error", "warning"]
    code: str
    where: str
    message: str


def _err(code: str, where: str, message: str) -> Finding:
    return Finding("error", code, where, message)


def _edges(step: TemplateStep) -> list[tuple[str, Any]]:
    edges: list[tuple[str, Any]] = [("next", step.next)] if step.next else []
    return edges + [(f"on.{k}", v) for k, v in step.on.items()]


def _targets(step: TemplateStep) -> list[str]:
    return [v for _, v in _edges(step) if isinstance(v, str) and v]


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _strings(v)


def _graph(t: ProcessTemplate) -> list[Finding]:
    out: list[Finding] = []
    if not isinstance(t.start, str) or t.start not in t.steps:
        out.append(_err("UNKNOWN_START", "template",
                        f"start step {t.start!r} is not a step of the template"))
    for s in t.steps.values():
        for key in s.on:
            if key not in OUTCOME_KEYS:
                out.append(_err("UNKNOWN_OUTCOME", f"step {s.id}",
                                f"step {s.id!r} routes an unknown outcome {key!r}"))
        for label, target in _edges(s):
            if not target:
                out.append(_err("UNKNOWN_TARGET", f"step {s.id}",
                                f"step {s.id}: {label} has no target"))
            elif not isinstance(target, str) or target not in t.steps:
                out.append(_err("UNKNOWN_TARGET", f"step {s.id}",
                                f"step {s.id!r} points to {target!r}, which is not a step"))
    reached: set[str] = set()
    todo = [t.start] if isinstance(t.start, str) else []
    while todo:
        sid = todo.pop()
        if sid in reached or sid not in t.steps:
            continue
        reached.add(sid)
        todo.extend(_targets(t.steps[sid]))
    for sid in t.steps:
        if sid not in reached:
            out.append(_err("UNREACHABLE", f"step {sid}", f"no path reaches step {sid!r}"))
    # steps from which a stop/wait is reachable (backwards fixpoint)
    ends = {sid for sid, s in t.steps.items() if s.type in _TERMINAL}
    changed = True
    while changed:
        changed = False
        for sid, s in t.steps.items():
            if sid not in ends and any(x in ends for x in _targets(s)):
                ends.add(sid)
                changed = True
    for sid in sorted(reached - ends):
        out.append(_err("NO_END", f"step {sid}", f"no path from step {sid!r} reaches stop or wait"))
    return out


def _steps(t: ProcessTemplate, pack: CompanyPack | None) -> list[Finding]:
    types = _step_types()
    kind_of = {r.id: r.kind for r in t.roles}
    roles = {r.id: r for r in t.roles}
    optional_role = {r.id: r.optional for r in t.roles}
    out: list[Finding] = []
    for s in t.steps.values():
        where = f"step {s.id}"
        spec = types["types"].get(s.type) if isinstance(s.type, str) else None
        if spec is None:
            out.append(_err("UNKNOWN_STEP_TYPE", where,
                            f"step {s.id!r} has an unknown step type {s.type!r}"))
        else:
            kind = kind_of.get(s.role)
            if kind not in spec["actors"]:
                out.append(_err("ACTOR_KIND", where,
                                f"step {s.id!r} of type {s.type!r} cannot be done by role "
                                f"{s.role!r} of kind {kind!r}"))
            for p in spec["required"]:
                if p not in s.params:
                    out.append(_err("MISSING_PARAM", where,
                                    f"step {s.id!r} of type {s.type!r} lacks param {p!r}"))
        role = roles.get(s.role)
        if (s.type == "request_approval" and role is not None and role.kind == "so"
                and role.scope is not None and not role.scope.may_open_approvals):
            out.append(_err("MAY_NOT_OPEN_APPROVALS", where,
                            f"step {s.id!r} makes digital employee {s.role!r} request an "
                            f"approval, but its scope may not open approvals"))
        if s.type == "decide_approval" and kind_of.get(s.role) == "so":
            out.append(_err("DE_DECIDES", where,
                            f"step {s.id!r} makes digital employee {s.role!r} decide an approval"))
        for text in _strings(s.params):
            if _CONCRETE_ID.match(text):
                out.append(_err("CONCRETE_ID", where,
                                f"step {s.id!r} holds the case id {text!r}"))
        if pack is not None:
            for param, table in (("cap", pack.policy.caps), ("tolerance", pack.policy.tolerances)):
                if param not in s.params:
                    continue
                name = s.params[param]
                if not isinstance(name, str) or name not in table:
                    out.append(_err("UNKNOWN_POLICY_KEY", where,
                                    f"step {s.id!r} names {param} {name!r}, which the pack lacks"))
        if optional_role.get(s.role) and not s.optional:
            out.append(_err("OPTIONAL_ROLE", where,
                            f"step {s.id!r} is not optional, but its role {s.role!r} is: a run "
                            f"where the role binds to nobody would be refused at it"))
        if kind_of.get(s.role) == "so" and not s.guidance.strip():
            out.append(Finding("warning", "NO_GUIDANCE", where,
                               f"step {s.id!r} of a digital employee has no guidance"))
    return out


def _roles(t: ProcessTemplate, pack: CompanyPack | None) -> list[Finding]:
    out: list[Finding] = []
    checked = ({k for k, r in pack.policy.approval_rules.items() if r.maker_checker}
               if pack is not None else None)
    for r in t.roles:
        where = f"role {r.id}"
        if r.kind == "so" and ("decide_approval" in (r.scope.tools if r.scope else ())
                               or r.duties.decides):
            out.append(_err("DE_DECIDES", where, f"digital employee {r.id!r} may decide approvals"))
        if "chung_tu" in r.duties.drafts:
            clash = r.duties.decides if checked is None else r.duties.decides & checked
            if clash:
                out.append(_err("MAKER_CHECKER", where,
                                f"role {r.id!r} drafts documents and decides {sorted(clash)}"))
        ceiling = PLATFORM_CEILING.get(r.kind)
        if ceiling is not None and r.scope is not None:
            sc, over = r.scope, []
            for f in ("tools", "read", "draft"):
                extra = getattr(sc, f) - getattr(ceiling, f)
                if extra:
                    over.append(f"{f} {sorted(extra)}")
            if sc.budget_usd > ceiling.budget_usd:
                over.append(f"budget_usd {sc.budget_usd}")
            if sc.may_open_approvals and not ceiling.may_open_approvals:
                over.append("may_open_approvals")
            if (sc.autonomy not in AUTONOMY_ORDER or
                    AUTONOMY_ORDER.index(sc.autonomy) > AUTONOMY_ORDER.index(ceiling.autonomy)):
                over.append(f"autonomy {sc.autonomy!r}")
            if over:
                out.append(_err("SCOPE_CEILING", where,
                                f"role {r.id!r} exceeds the platform ceiling: {'; '.join(over)}"))
    return out


def _pack(pack: CompanyPack) -> list[Finding]:
    """The pack's own consistency (final review M1)."""
    out: list[Finding] = []
    counts = Counter(r.code for r in pack.roles)
    for code in sorted(c for c, n in counts.items() if n > 1):
        out.append(_err("DUPLICATE_ROLE", f"role {code}",
                        f"role code {code!r} appears {counts[code]} times in the pack"))
    persons = {r.code for r in pack.roles if r.kind == "nguoi"}
    for loai_pd, rule in sorted(pack.policy.approval_rules.items()):
        where = f"approval rule {loai_pd}"
        for tier in rule.tiers:
            if tier.approver not in persons:
                out.append(_err("TIER_APPROVER", where,
                                f"{loai_pd!r} routes to {tier.approver!r}, which is not a "
                                f"person (nguoi) of the pack"))
        maxima = [tier.max for tier in rule.tiers]
        open_tiers = [n for n, m in enumerate(maxima) if m is None]
        bounded = [m for m in maxima if m is not None]
        if (open_tiers and open_tiers != [len(maxima) - 1]) or any(
                a >= b for a, b in zip(bounded, bounded[1:], strict=False)):
            out.append(_err("TIER_ORDER", where,
                            f"the tiers of {loai_pd!r} must rise: maxima ascending and the "
                            f"open tier (no maximum) last, at most one; got "
                            f"{[None if m is None else str(m) for m in maxima]}"))
    return out


def validate(template: ProcessTemplate, pack: CompanyPack | None = None) -> list[Finding]:
    findings = _graph(template) + _steps(template, pack) + _roles(template, pack)
    if pack is not None:
        findings += _pack(pack)
        try:
            mapping = map_roles(template, pack)
        except BindingError as e:
            findings.extend(_err("BINDING", "roles", p) for p in e.problems)
        else:
            findings.extend(
                Finding("warning", "INEXACT_BINDING", f"role {m.template_role}",
                        f"template role {m.template_role!r} is mapped to "
                        f"{', '.join(m.codes)} by the best overlap of duties, not an exact"
                        f" match")
                for m in mapping.values() if not m.exact)
    return findings

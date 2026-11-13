"""Map template roles to company role codes when a process is installed (rule C13, ruling
R12a, Task 14 of the evaluation).

A shared template is drafted without knowing any one company, so its roles rarely name a
company's duties exactly. Installing the process maps each template role to the company
roles that will do its steps, the step an administrator does in production, and the
mapping is recorded (``RoleMapping``; ``RunResult.binding``). Every arm of an experiment
gets the same mapping. ``map_roles`` applies these rules, in this order:

1. A person (``nguoi``) who neither drafts nor requests, a person who only decides
   (ruling R12a), binds to every company person deciding one of its approval types, in
   the company's order (the listed types are alternative names companies give one
   approval); one that lists none binds to every person who neither drafts nor requests.
   Approval tiers route one approval type to several people, and which of them decides is
   the gate's routing at run time. If that finds nobody, it binds to every company person
   who decides any approval type. It is ``exact`` only when the first rule found someone.
2. Every other template role takes the company roles of its own actor kind as
   candidates, in two passes (final review I8):

   a. Exact first: in template order, a role with exactly one candidate whose duties
      match its own exactly (below) among the codes no earlier role of this rule took
      takes that code. So a later role's only exact match is never taken by an earlier
      role's inexact one.
   b. Best overlap for the rest, in template order. A candidate's score is the duties
      they share: ``|drafts ∩ drafts| + (1 if both may or both may not request
      approvals) + |decides ∩ decides|``. The highest score wins; ties go to the
      candidate with the fewest duties the template role lacks (``|r.drafts − t.drafts|
      + |r.decides − t.decides|``), then, for a person, to a code that no person of rule
      1 holds (a drafting person does not land on an approver's code, whose own
      decisions maker ≠ checker would then refuse, whenever another person is there),
      then to the company's order.

   A role prefers a company code that no other template role of rule 2 took: it reuses a
   taken code only when every candidate of its kind is taken. It is ``exact`` when its
   duties match the chosen code's exactly (the same drafts and request right, and the
   approval types it decides among those the company role decides; any role of the
   kind, for a kind without duties).
3. A role with no candidate of its kind (for a person who only decides: no company
   person who decides any approval type) binds to nothing when it is ``optional`` (its
   steps are then skipped; the mapping counts as exact, as strict binding gave the same);
   otherwise it is a ``BindingError``.

``exact`` is only a record of how the mapping was made: two company roles with the same
duties both match exactly, and the first in the company's order is taken.

A mapping does not widen what a company gives a role: the engine caps the scope token of
a digital employee by its company role's duties (``tonomyx.enforce.tokens.capped_scope``).
"""
from __future__ import annotations

from dataclasses import dataclass

from .pack import CompanyPack, Role
from .template import ProcessTemplate, TemplateRole


class BindingError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass(frozen=True)
class RoleMapping:
    """The company role codes one template role is mapped to, and whether its duties
    matched them exactly."""

    template_role: str
    codes: tuple[str, ...]
    exact: bool


def binds_to_every_match(t: TemplateRole) -> bool:
    """A person who only decides (R12a): no drafts, no requests."""
    return t.kind == "nguoi" and not t.duties.drafts and not t.duties.may_request


def _matches(t: TemplateRole, r: Role) -> bool:
    """The duties of ``t`` match those of ``r`` exactly (the strict rule of C13)."""
    if t.kind != r.kind:
        return False
    if t.kind in ("so", "nguoi"):
        if t.duties.drafts != r.drafts or t.duties.may_request != r.may_request:
            return False
        if binds_to_every_match(t):
            return not t.duties.decides or bool(t.duties.decides & r.decides)
        return t.duties.decides <= r.decides
    return True


def _score(t: TemplateRole, r: Role) -> int:
    d = t.duties
    return (len(d.drafts & r.drafts) + (1 if d.may_request == r.may_request else 0)
            + len(d.decides & r.decides))


def _extra(t: TemplateRole, r: Role) -> int:
    return len(r.drafts - t.duties.drafts) + len(r.decides - t.duties.decides)


def _no_candidate(t: TemplateRole, what: str = "") -> str:
    return f"template role {t.id!r}: no company role of kind {t.kind!r}{what}"


def map_roles(template: ProcessTemplate, pack: CompanyPack) -> dict[str, RoleMapping]:
    """Each template role's mapping to company role codes (see the module docstring)."""
    mapped: dict[str, RoleMapping] = {}
    problems: list[str] = []
    # Rule 1 first: the codes the people who only decide hold are known before rule 2.
    for t in template.roles:
        if not binds_to_every_match(t):
            continue
        codes = tuple(r.code for r in pack.roles if _matches(t, r))
        exact = bool(codes)
        if not codes:
            codes = tuple(r.code for r in pack.roles if r.kind == "nguoi" and r.decides)
        if not codes and not t.optional:
            problems.append(_no_candidate(t, " that decides approvals"))
            continue
        mapped[t.id] = RoleMapping(t.id, codes, exact or not codes)
    deciders = {code for m in mapped.values() for code in m.codes}
    others = [t for t in template.roles if not binds_to_every_match(t)]
    taken: set[str] = set()
    # Rule 2a: a unique exact match among the untaken codes.
    for t in others:
        matches = [r for r in pack.roles
                   if r.kind == t.kind and r.code not in taken and _matches(t, r)]
        if len(matches) == 1:
            taken.add(matches[0].code)
            mapped[t.id] = RoleMapping(t.id, (matches[0].code,), True)
    # Rule 2b and rule 3: the best overlap for the rest.
    for t in others:
        if t.id in mapped:
            continue
        candidates = [r for r in pack.roles if r.kind == t.kind]
        if not candidates:
            if t.optional:
                mapped[t.id] = RoleMapping(t.id, (), True)
            else:
                problems.append(_no_candidate(t))
            continue
        untaken = [r for r in candidates if r.code not in taken]

        def key(r: Role, t: TemplateRole = t) -> tuple[int, int, bool]:
            held = t.kind == "nguoi" and r.code in deciders
            return (-_score(t, r), _extra(t, r), held)

        # ``min`` keeps the first of equal keys: the company's order breaks the last tie.
        best = min(untaken or candidates, key=key)
        taken.add(best.code)
        mapped[t.id] = RoleMapping(t.id, (best.code,), _matches(t, best))
    if problems:
        raise BindingError(problems)
    return {t.id: mapped[t.id] for t in template.roles if t.id in mapped}


def bind_roles(template: ProcessTemplate, pack: CompanyPack) -> dict[str, tuple[str, ...]]:
    """Each template role's company role codes (``map_roles``)."""
    return {role_id: m.codes for role_id, m in map_roles(template, pack).items()}

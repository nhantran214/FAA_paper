"""Scope tokens (a role's whole scope) and task tokens (scope narrowed to one step)."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from tonomyx.contracts.token import TaskToken, TokenIssuer
from tonomyx.core.schema import load_core_schema
from tonomyx.enforce.ceiling import AUTONOMY_ORDER, PLATFORM_CEILING
from tonomyx.governance.pack import Role
from tonomyx.governance.template import RoleScope, TemplateStep
from tonomyx.tools.core import CORE_TOOLS

# Tools each step type needs. Engine-run types need none; decide_approval is for people only
# and is never inside a `so` token (the platform ceiling excludes it).
STEP_NEEDS: dict[str, frozenset[str]] = {
    "open_case": frozenset(),
    "wait": frozenset(),
    "stop": frozenset(),
    # A document's item and partner codes live in master data: the step may read them,
    # within the role's read scope (Task 15).
    "create_document": frozenset({"create_document", "read_records"}),
    "record_external_fact": frozenset({"record_event"}),
    "check": frozenset({"read_records", "flag"}),
    "flag_exception": frozenset({"flag"}),
    "compute_amount": frozenset({"compute_amount", "read_records"}),
    "update_status": frozenset({"update_status"}),
    "request_approval": frozenset({"request_approval", "read_records"}),
    "decide_approval": frozenset({"decide_approval"}),
    "reconcile": frozenset({"reconcile", "read_records"}),
    "pay": frozenset({"pay", "read_records"}),
    "notify": frozenset({"notify", "read_records"}),
}


_CORE_TABLES = frozenset(load_core_schema().tables)

# The scope of a digital employee when the token tier is switched off (``Controls.tokens``
# False; experiments only): every core tool, every core table to read and draft, and
# approvals it may open. It is above the platform ceiling, so it is issued only through
# ``scope_token(..., check_ceiling=False)``, which the engine calls only with that switch off.
WIDEST_SCOPE = RoleScope(
    tools=frozenset(CORE_TOOLS),
    read=_CORE_TABLES,
    draft=_CORE_TABLES,
    may_open_approvals=True,
    budget_usd=PLATFORM_CEILING["so"].budget_usd,
    autonomy=PLATFORM_CEILING["so"].autonomy,
)


# The document tables a company role's ``soan_bang`` governs. A document is drafted with its
# lines (bench_v1 README: ``chung_tu`` "to create documents"; a ``so`` actor needs only
# ``chung_tu`` to make a document with lines), so ``chung_tu`` also grants ``dong_ct``.
# Payments (``thanh_toan``) are not a drafting duty there: a ``pay`` step is held by the
# approval gate, so the company cap leaves them to the template's scope and the ceiling.
DOCUMENT_TABLES = frozenset({"chung_tu", "dong_ct"})


def company_document_tables(role: Role) -> frozenset[str]:
    """The document tables a company role may draft (see ``DOCUMENT_TABLES``)."""
    if "chung_tu" in role.drafts:
        return DOCUMENT_TABLES
    return role.drafts & DOCUMENT_TABLES


def capped_scope(scope: RoleScope, roles: Iterable[Role]) -> RoleScope:
    """A template role's scope, capped by the duties of the company roles it is mapped to
    (Task 14: a mapping never widens what the company gives a role).

    ``draft`` keeps only the document tables every one of ``roles`` may draft
    (``company_document_tables``), and approvals may be opened (``request_approval``) only
    when every one of them may request approvals (``yeu_cau_duyet``). A digital employee is
    mapped to one company role; with several, the cap is their intersection. Used only
    with the token tier on: with it off, the engine issues ``WIDEST_SCOPE``."""
    roles = tuple(roles)
    allowed = DOCUMENT_TABLES
    may_request = True
    for role in roles:
        allowed = allowed & company_document_tables(role)
        may_request = may_request and role.may_request
    if may_request:
        return replace(scope, draft=scope.draft - (DOCUMENT_TABLES - allowed))
    return replace(scope, draft=scope.draft - (DOCUMENT_TABLES - allowed),
                   tools=scope.tools - {"request_approval"}, may_open_approvals=False)


def _check_ceiling(scope: RoleScope, kind: str = "so") -> None:
    ceiling = PLATFORM_CEILING[kind]
    over = []
    for f in ("tools", "read", "draft"):
        extra = getattr(scope, f) - getattr(ceiling, f)
        if extra:
            over.append(f"{f} {sorted(extra)}")
    if scope.budget_usd > ceiling.budget_usd:
        over.append(f"budget {scope.budget_usd} > {ceiling.budget_usd}")
    if scope.may_open_approvals and not ceiling.may_open_approvals:
        over.append("may_open_approvals")
    if (scope.autonomy not in AUTONOMY_ORDER
            or AUTONOMY_ORDER.index(scope.autonomy) > AUTONOMY_ORDER.index(ceiling.autonomy)):
        over.append(f"autonomy {scope.autonomy}")
    if over:
        raise ValueError(f"platform rule 5: scope exceeds the platform ceiling: {'; '.join(over)}")


def _issue(issuer: TokenIssuer, role_code: str, scope: RoleScope, tools: frozenset[str],
           case_id: str, task_id: str) -> TaskToken:
    return issuer.issue_task_token(
        de=role_code, task_id=task_id, case_id=case_id, tools=tools, read=scope.read,
        draft=scope.draft, kb_domain="", autonomy=scope.autonomy, budget_usd=scope.budget_usd)


def scope_tools(scope: RoleScope) -> frozenset[str]:
    """The tools a scope really grants: its ``tools``, less ``request_approval`` when it may
    not open approvals (``may_open_approvals``; final review I4)."""
    if scope.may_open_approvals:
        return scope.tools
    return scope.tools - {"request_approval"}


def scope_token(issuer: TokenIssuer, role_code: str, scope: RoleScope, case_id: str,
                task_id: str, *, check_ceiling: bool = True) -> TaskToken:
    """A token for the whole scope. ``check_ceiling=False`` skips rule 5 at the token
    tier: only for ``WIDEST_SCOPE`` with the token tier switched off (``Controls``); any
    other scope is a ``ValueError`` (Task 5 M5)."""
    if check_ceiling:
        _check_ceiling(scope)
    elif scope != WIDEST_SCOPE:
        raise ValueError("the ceiling check is skipped only for WIDEST_SCOPE")
    return _issue(issuer, role_code, scope, scope_tools(scope), case_id, task_id)


def task_token(issuer: TokenIssuer, role_code: str, scope: RoleScope, step: TemplateStep,
               case_id: str, task_id: str) -> TaskToken:
    """A token for one step: the scope's tools that the step's type needs. A step type the
    platform does not know is a ``ValueError`` (the engine refuses the step)."""
    _check_ceiling(scope)
    needs = STEP_NEEDS.get(step.type)
    if needs is None:
        raise ValueError(f"unknown step type {step.type!r}: no task token for step {step.id}")
    return _issue(issuer, role_code, scope, scope_tools(scope) & needs, case_id, task_id)

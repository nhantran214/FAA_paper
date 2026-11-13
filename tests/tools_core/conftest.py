"""Fixtures for the generic core tools: a small world in schema ``core`` and a context maker.

Given data is loaded outside ``acting_as``, as the engine loads a case: it is data,
not an action, so the platform-rule triggers stand aside for it.

The world:
- cases ``HS-01`` (the one the tools act on) and ``HS-02`` (another case);
- partner ``NCC-01`` with account ``0011``; items ``HH-01`` (50000) and ``HH-02`` (30000);
- knowledge articles ``KB-01`` and ``KB-02``;
- in ``HS-01``: purchase order ``PO-01`` (15 of HH-01 at 50000), goods receipt
  ``GRN-01`` (12 of HH-01), supplier invoice ``INV-01`` (15 of HH-01 at 50000);
- in ``HS-02``: document ``X-01`` with one line.

Policy: ``don_mua`` up to 1000000 goes to ``TP``, above to ``GD`` (maker-checker);
``de_nghi_chi`` always to ``KTT``, ``pduyet_cuoi`` (final sign-off) always to ``GD``
(both maker-checker). Price tolerance ``gia`` is 0.05.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from tests.core_fixtures import fresh_core, seed_world
from tonomyx.config import Settings
from tonomyx.contracts.token import TaskToken
from tonomyx.enforce.ceiling import PLATFORM_CEILING
from tonomyx.enforce.gate import BusinessGate
from tonomyx.governance.pack import ApprovalRule, Policy, Tier
from tonomyx.tools.core.context import CoreContext
from tonomyx.tools.ports import MailSender

Conn = psycopg.Connection[dict[str, Any]]

GOVERNANCE_VERSION = "gv-test-1"


def policy() -> Policy:
    return Policy(
        approval_rules={
            "don_mua": ApprovalRule(
                "don_mua", True, (Tier(Decimal("1000000"), "TP"), Tier(None, "GD"))
            ),
            "de_nghi_chi": ApprovalRule("de_nghi_chi", True, (Tier(None, "KTT"),)),
            "pduyet_cuoi": ApprovalRule("pduyet_cuoi", True, (Tier(None, "GD"),)),
        },
        caps={},
        tolerances={"gia": Decimal("0.05")},
        statutory_refs=(),
    )


def token(
    actor: str = "DE-1",
    case_id: str = "HS-01",
    tools: frozenset[str] | None = None,
    read: frozenset[str] | None = None,
    draft: frozenset[str] | None = None,
) -> TaskToken:
    ceiling = PLATFORM_CEILING["so"]
    return TaskToken(
        iss="test",
        sub=actor,
        task_id="T-1",
        case_id=case_id,
        tools=ceiling.tools if tools is None else tools,
        read=ceiling.read if read is None else read,
        draft=ceiling.draft if draft is None else draft,
        kb_domain="",
        autonomy="L2",
        budget_usd=Decimal("1.00"),
        jti="jti-1",
        exp=datetime.now(UTC) + timedelta(minutes=5),
    )


MakeCtx = Callable[..., CoreContext]


@pytest.fixture
def world(settings: Settings) -> Iterator[Conn]:
    with fresh_core(settings) as c:
        seed_world(c)
        yield c


@pytest.fixture
def make_ctx(world: Conn) -> MakeCtx:
    gate = BusinessGate(policy())

    def make(
        actor: str = "DE-1",
        kind: str = "so",
        *,
        tok: TaskToken | None | str = "default",
        step_id: str = "S1",
        mail: MailSender | None = None,
        case_id: str = "HS-01",
    ) -> CoreContext:
        if tok == "default":
            tok = token(actor, case_id) if kind == "so" else None
        assert not isinstance(tok, str)
        return CoreContext(
            conn=world,
            case_id=case_id,
            actor=actor,
            actor_kind=kind,
            token=tok,
            gate=gate,
            governance_version=GOVERNANCE_VERSION,
            step_id=step_id,
            mail=mail,
        )

    return make


def rows(conn: Conn, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    out = conn.execute(query, params).fetchall()
    conn.commit()
    return out


def one(conn: Conn, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    found = rows(conn, query, params)
    assert len(found) == 1, found
    return found[0]

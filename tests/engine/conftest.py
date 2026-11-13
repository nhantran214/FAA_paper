"""Fixtures for the engine: a small company, a small process template and fake actors.

The company (pack): the coordinator ``DP-01`` (dieu_phoi), the digital employee
``DE-MH`` (drafts documents, may request approvals), the head of purchasing
``TP-MH`` and the director ``GD`` (people who decide ``don_mua``) and the supplier
``NCC-01`` (an outside party). Purchase orders (``don_mua``) up to 1000000 go to ``TP-MH``,
above to ``GD`` (maker-checker). Master rows come as CSV strings, as a pack's do.

The process template:

    open (open_case) -> draft (create_document, DE) -> review (check, DE, optional)
      -> ask (request_approval, DE) -> decide (decide_approval, TP)
      decide: next -> end (stop); on pending -> hold (wait)

The fakes play whatever a test scripts per step id, only through the toolbox.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from tests.core_fixtures import fresh_core
from tonomyx.config import Settings
from tonomyx.contracts.clock import FixedClock
from tonomyx.contracts.token import InMemoryJtiStore, TaskToken, TokenIssuer
from tonomyx.enforce.ceiling import PLATFORM_CEILING
from tonomyx.engine import CaseInstance, Delivery, EnvironmentToolbox, StepOutcome, StepToolbox
from tonomyx.governance.pack import ApprovalRule, CompanyPack, Policy, Role, Tier
from tonomyx.governance.template import (
    Duties,
    ProcessTemplate,
    RoleScope,
    TemplateRole,
    TemplateStep,
)

Conn = psycopg.Connection[dict[str, Any]]
Script = Callable[[StepToolbox], StepOutcome]

GOVERNANCE_VERSION = "gv-engine-1"
CASE_ID = "HS-01"
APPROVED = "Đã duyệt"


@pytest.fixture
def conn(settings: Settings) -> Iterator[Conn]:
    """A connection to a freshly reset, empty ``core`` schema."""
    with fresh_core(settings) as c:
        yield c


def pack() -> CompanyPack:
    policy = Policy(
        approval_rules={
            "don_mua": ApprovalRule(
                "don_mua", True, (Tier(Decimal("1000000"), "TP-MH"), Tier(None, "GD"))
            ),
        },
        caps={"han_muc_don_mua": Decimal("5000000"), "ty_le": Decimal("0.5")},
        tolerances={"gia": Decimal("0.05"), "so_luong": Decimal("2")},
        statutory_refs=(),
    )
    roles = (
        Role("DP-01", "dieu_phoi", frozenset(), False, frozenset()),
        Role("DE-MH", "so", frozenset({"chung_tu"}), True, frozenset()),
        Role("TP-MH", "nguoi", frozenset(), False, frozenset({"don_mua"})),
        Role("NCC-01", "ngoai", frozenset(), False, frozenset()),
        # Every tier's approver is a person of the pack (validator, final review M1).
        Role("GD", "nguoi", frozenset(), False, frozenset({"don_mua"})),
    )
    master = {
        "doi_tac": [
            {
                "ma_dt": "NCC-01",
                "loai": "nha_cung_cap",
                "ten": "Công ty A",
                "ma_so_thue": "",
                "hang": "",
                "han_muc_no": "",
                "ngan_hang": "VCB",
                "stk": "0011",
            }
        ],
        "hang_hoa": [
            {
                "ma_hh": "HH-01",
                "ten": "Thép",
                "don_vi": "kg",
                "loai": "hang",
                "don_gia": "50000",
                "ton_kho": "",
                "ck_toi_da": "",
            }
        ],
    }
    return CompanyPack("Công ty thử", "p-1", roles, policy, (), master)


def de_scope(**changes: Any) -> RoleScope:
    scope = RoleScope(
        tools=PLATFORM_CEILING["so"].tools,
        read=PLATFORM_CEILING["so"].read,
        draft=frozenset({"chung_tu", "dong_ct"}),
        may_open_approvals=True,
        budget_usd=Decimal("0.50"),
        autonomy="L1",
    )
    return replace(scope, **changes)


def template(
    *steps: TemplateStep, de: RoleScope | None = None, **step_changes: Any
) -> ProcessTemplate:
    """The test template. ``step_changes`` maps a step id to a dict of field changes;
    extra ``steps`` are added (or replace the step of the same id)."""
    roles = (
        TemplateRole("dp", "dieu_phoi", Duties(), None),
        TemplateRole(
            "de", "so", Duties(drafts=frozenset({"chung_tu"}), may_request=True), de or de_scope()
        ),
        TemplateRole("tp", "nguoi", Duties(decides=frozenset({"don_mua"})), None),
        TemplateRole("ncc", "ngoai", Duties(), None),
    )
    base = [
        TemplateStep("open", "open_case", "dp", {"title": "Mua vật tư"}, next="draft"),
        TemplateStep(
            "draft",
            "create_document",
            "de",
            {"doc": "don_hang", "loai_ct": "don_mua"},
            guidance="Lập đơn mua.",
            next="review",
        ),
        TemplateStep(
            "review",
            "check",
            "de",
            {"expr": "gia_hop_le"},
            guidance="Kiểm tra giá.",
            optional=True,
            next="ask",
            on={"flag": "end"},
        ),
        TemplateStep(
            "ask",
            "request_approval",
            "de",
            {"id": "pd_don_hang", "doc": "don_hang", "loai_pd": "don_mua"},
            guidance="Trình duyệt.",
            next="decide",
        ),
        TemplateStep(
            "decide",
            "decide_approval",
            "tp",
            {"approval": "pd_don_hang", "decision": "quyet_dinh"},
            next="end",
            on={"pending": "hold"},
        ),
        TemplateStep("end", "stop", "dp", {"reason": "Hoàn tất mua"}),
        TemplateStep("hold", "wait", "dp", {"for": "quyet_dinh_duyet"}),
    ]
    by_id = {s.id: s for s in base}
    for s in steps:
        by_id[s.id] = s
    for sid, changes in step_changes.items():
        by_id[sid] = replace(by_id[sid], **changes)
    return ProcessTemplate("mua_hang", "Mua hàng", "1.0", roles, "open", by_id)


def instance(data: dict[str, list[dict[str, Any]]] | None = None) -> CaseInstance:
    return CaseInstance(CASE_ID, "Mua thép cho xưởng", "Cần mua 10 kg thép", data or {})


def issuer(clock: FixedClock | None = None) -> TokenIssuer:
    return TokenIssuer(
        clock or FixedClock(datetime(2026, 11, 6, 9, 0, tzinfo=UTC)), InMemoryJtiStore()
    )


class RecordingIssuer(TokenIssuer):
    """An issuer that remembers every task token it issued and every one redeemed."""

    def __init__(self, clock: FixedClock | None = None) -> None:
        super().__init__(
            clock or FixedClock(datetime(2026, 11, 6, 9, 0, tzinfo=UTC)), InMemoryJtiStore()
        )
        self.issued: list[TaskToken] = []
        self.redeemed: list[str] = []

    def issue_task_token(self, **kwargs: Any) -> TaskToken:
        token = super().issue_task_token(**kwargs)
        self.issued.append(token)
        return token

    def redeem_task_token(self, token: TaskToken) -> TaskToken:
        out = super().redeem_task_token(token)
        self.redeemed.append(token.jti)
        return out


class FakeExecutor:
    """Plays the script of each step id; a step with no script is skipped."""

    def __init__(self, script: dict[str, Script] | None = None) -> None:
        self.script = script or {}
        self.seen: list[tuple[str, str]] = []
        self.toolboxes: list[StepToolbox] = []

    def perform(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        self.seen.append((step.id, role_code))
        self.toolboxes.append(toolbox)
        play = self.script.get(step.id)
        return "skipped" if play is None else play(toolbox)


class FakeEnvironment:
    """Plays the script of each person's or outside party's step id. Before an executor
    step it delivers ``deliveries[step id]`` (nothing when absent) and records the call
    in ``prepared``."""

    def __init__(
        self,
        script: dict[str, Script] | None = None,
        deliveries: dict[str, Delivery] | None = None,
    ) -> None:
        self.script = script or {}
        self.deliveries = deliveries or {}
        self.seen: list[tuple[str, str, str]] = []
        self.prepared: list[tuple[str, str]] = []

    def _play(
        self, who: str, step: TemplateStep, role_code: str, toolbox: StepToolbox
    ) -> StepOutcome:
        self.seen.append((who, step.id, role_code))
        play = self.script.get(step.id)
        return "skipped" if play is None else play(toolbox)

    def person(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        return self._play("person", step, role_code, toolbox)

    def outside(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        return self._play("outside", step, role_code, toolbox)

    def prepare(self, step: TemplateStep, role_code: str, toolbox: EnvironmentToolbox) -> Delivery:
        self.prepared.append((step.id, role_code))
        return self.deliveries.get(step.id, Delivery())


# --- the usual scripts ----------------------------------------------------------------


def draft_order(box: StepToolbox, quantity: int = 10) -> StepOutcome:
    box.call(
        "create_document",
        loai_ct="don_mua",
        ma_ct="PO-01",
        ma_dt="NCC-01",
        lines=[{"ma_hh": "HH-01", "so_luong": quantity, "don_gia": 50000}],
    )
    return "done"


def check_price(box: StepToolbox) -> StepOutcome:
    rows = box.call("read_records", table="dong_ct", where={"ma_ct": "PO-01"})["rows"]
    return "pass" if all(r["don_gia"] == 50000 for r in rows) else "flag"


def ask_approval(box: StepToolbox) -> StepOutcome:
    box.call("request_approval", ma_pd="PD-01", ma_ct="PO-01", loai_pd="don_mua")
    return "done"


def approve(box: StepToolbox) -> StepOutcome:
    box.call("decide_approval", ma_pd="PD-01", decision=APPROVED)
    return "approved"


def no_decision(box: StepToolbox) -> StepOutcome:
    return "pending"


def de_script(**overrides: Script) -> dict[str, Script]:
    return {"draft": draft_order, "review": check_price, "ask": ask_approval, **overrides}


def rows(conn: Conn, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    out = conn.execute(query, params).fetchall()
    conn.commit()
    return out


CORE_TABLES = (
    "doi_tac",
    "hang_hoa",
    "nhan_su",
    "ngan_sach",
    "tri_thuc",
    "ho_so",
    "chung_tu",
    "dong_ct",
    "phe_duyet",
    "thanh_toan",
    "su_kien",
    "nguon_tien",
)


def snapshot(conn: Conn) -> dict[str, list[dict[str, Any]]]:
    """Every core table's rows in a stable order; the event time is left out."""
    out = {}
    for table in CORE_TABLES:
        found = rows(conn, f"SELECT * FROM core.{table} ORDER BY 1, 2")
        out[table] = [{k: v for k, v in r.items() if k != "at"} for r in found]
    return out

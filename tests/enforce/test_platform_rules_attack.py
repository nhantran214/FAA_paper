"""Platform rules 1-6 under attack (spec 5.4; C9: enforced at every tier).

For each rule, two attempts, each refused with a message naming ``platform rule N``:

- through the tools, by a digital employee (actor kind ``so``) whose context holds an
  over-wide task token built by hand. The token carries every tool, every table to
  read and draft, a high budget and autonomy: what the token tier would never issue
  (``scope_token`` refuses that scope, rule 5). The deeper tiers must still refuse.
- through raw SQL under ``acting_as(..., "so", ...)``. Ruling R2h: the database tier
  trusts the ``tonomyx.*`` session settings, so no attack here forges them (no SET,
  no ``set_config``, no DDL).

Given data is loaded outside ``acting_as`` (ruling R2a): it is data, not an action.

Plus: a template that lets a digital employee decide is reported (``DE_DECIDES``) and
never starts, and every event of a run carries the run's governance version.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tonomyx.bench.executors import ScriptedEnvironment, ScriptedExecutor
from tonomyx.contracts.clock import FixedClock
from tonomyx.contracts.token import InMemoryJtiStore, TaskToken, TokenIssuer
from tonomyx.core.db import acting_as
from tonomyx.enforce.ceiling import PLATFORM_CEILING
from tonomyx.enforce.gate import BusinessGate
from tonomyx.enforce.tokens import scope_token
from tonomyx.engine import CaseInstance, TemplateInvalid, run_case
from tonomyx.governance.pack import ApprovalRule, Policy, Tier, load_company_pack
from tonomyx.governance.template import RoleScope, load_template
from tonomyx.governance.validate import validate
from tonomyx.tools.core import CORE_TOOLS, CoreContext
from tonomyx.tools.core.context import COLUMNS
from tonomyx.tools.errors import ToolDenied

pytestmark = pytest.mark.db

Conn = psycopg.Connection[dict[str, Any]]

REPO = Path(__file__).resolve().parents[2]
PACK_DIR = REPO / "tests" / "fixtures" / "governance" / "packs" / "sales-backorder-demo"
TEMPLATE = (
    REPO / "tests" / "fixtures" / "governance" / "templates"
    / "sales_order_with_backorder.json"
)

GV = "gv-attack-1"
DE = "DE-1"
APPROVED = "Đã duyệt"
PENDING = "Chờ duyệt"
PAID = "Đã chi"


# --- refusal helpers ---------------------------------------------------------------------


@contextmanager
def tool_refused(rule: int, *, match: str | None = None) -> Iterator[None]:
    """A tool call refused with a message starting ``platform rule N:`` (and holding
    ``match``, when given: the clause of the rule that refused it)."""
    with pytest.raises(ToolDenied) as caught:
        yield
    message = str(caught.value)
    assert message.startswith(f"platform rule {rule}:"), message
    assert match is None or match in message, message


@contextmanager
def sql_refused(
    rule: int, *, fk_tolerated: bool = False, match: str | None = None
) -> Iterator[None]:
    """A database refusal whose primary message starts ``platform rule N:`` (and holds
    ``match``, when given).

    ``fk_tolerated``: a delete of a linked record may instead be stopped by a foreign
    key (Task 2 minor, tolerated): refused all the same, without the rule's wording.
    """
    with pytest.raises(psycopg.Error) as caught:
        yield
    if fk_tolerated and isinstance(caught.value, psycopg.errors.ForeignKeyViolation):
        return
    assert isinstance(caught.value, psycopg.errors.InsufficientPrivilege), repr(caught.value)
    message = caught.value.diag.message_primary or ""
    assert message.startswith(f"platform rule {rule}:"), message
    assert match is None or match in message, message


def scalar(c: Conn, query: str, params: tuple[Any, ...] = ()) -> Any:
    row = c.execute(query, params).fetchone()
    c.commit()
    assert row is not None
    return next(iter(row.values()))


def table_rows(c: Conn, *tables: str) -> dict[str, list[dict[str, Any]]]:
    """Every row of ``tables``, in a stable order: to show an attack wrote nothing."""
    out = {}
    for table in tables:
        out[table] = c.execute(f"SELECT * FROM core.{table} ORDER BY 1").fetchall()
    c.commit()
    return out


GATES = ("chung_tu", "dong_ct", "phe_duyet", "thanh_toan")
MASTER = ("doi_tac", "hang_hoa", "nhan_su", "ngan_sach", "tri_thuc", "nguon_tien")


def events(c: Conn) -> list[dict[str, Any]]:
    out = c.execute("SELECT kind, ref, actor, governance_version FROM core.su_kien ORDER BY id")
    found = out.fetchall()
    c.commit()
    return found


# --- the attacker: a digital employee with an over-wide token, built by hand ----------------


def over_wide_token(actor: str = DE, case_id: str = "HS-01") -> TaskToken:
    """Every tool and table, budget and autonomy above the ceiling: never issued by the platform."""
    return TaskToken(
        iss="hand-built",
        sub=actor,
        task_id="T-ATTACK",
        case_id=case_id,
        tools=frozenset(CORE_TOOLS),
        read=frozenset(COLUMNS) | {"nguon_tien"},
        draft=frozenset(COLUMNS) | {"nguon_tien"},
        kb_domain="*",
        autonomy="L3",
        budget_usd=Decimal("1000"),
        jti="jti-attack",
        exp=datetime.now(UTC) + timedelta(minutes=5),
    )


def attack_policy() -> Policy:
    """The tools-core policy, plus declarations an attacker would like to exploit.

    ``tu_duyet`` routes to the digital employee itself, ``lap_duyet`` to the maker of
    ``PAY-01``; ``khong_kiem`` routes to that maker too and switches maker-checker off.
    No declaration can switch a platform rule off.
    """
    return Policy(
        approval_rules={
            "don_mua": ApprovalRule(
                "don_mua", True, (Tier(Decimal("1000000"), "TP"), Tier(None, "GD"))
            ),
            "de_nghi_chi": ApprovalRule("de_nghi_chi", True, (Tier(None, "KTT"),)),
            "tu_duyet": ApprovalRule("tu_duyet", False, (Tier(None, DE),)),
            "lap_duyet": ApprovalRule("lap_duyet", False, (Tier(None, "NV-LAP"),)),
            "khong_kiem": ApprovalRule("khong_kiem", False, (Tier(None, "NV-LAP"),)),
        },
        caps={},
        tolerances={"gia": Decimal("0.05")},
        statutory_refs=(),
    )


class FakeMail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


def ctx_for(
    c: Conn, actor: str = DE, kind: str = "so", *, mail: FakeMail | None = None
) -> CoreContext:
    return CoreContext(
        conn=c,
        case_id="HS-01",
        actor=actor,
        actor_kind=kind,
        token=over_wide_token(actor) if kind == "so" else None,
        gate=BusinessGate(attack_policy()),
        governance_version=GV,
        step_id="S-ATTACK",
        mail=mail,
    )


def call(ctx: CoreContext, tool: str, **args: Any) -> dict[str, Any]:
    return CORE_TOOLS[tool](ctx, **args)


@pytest.fixture
def arena(world: Conn) -> Conn:
    """The tools-core world (see its conftest), plus given data for the attacks.

    - ``PAY-01``: payment request for HS-01 made by person ``NV-LAP``, 10 of HH-01
      at 50000 (``tong_tien`` 500000), partner ``NCC-01`` (account ``0011``);
      approval ``APR-02`` requested by ``NV-YC``, routed to ``KTT``, pending;
      payment ``TT-01`` waiting (``Chờ chi``).
    - ``PO-DE``: purchase order drafted by the digital employee ``DE-1``, pending,
      with approval ``APR-01`` it requested, routed to ``TP``.
    - ``APR-G``: a ``khong_kiem`` approval of ``PAY-01``, routed to its maker ``NV-LAP``.
    """
    c = world
    c.execute(
        "INSERT INTO core.chung_tu (ma_ct, loai_ct, case_id, ma_dt, ct_goc, nguoi_lap,"
        " trang_thai, tien_te, tong_tien) VALUES"
        " ('PAY-01', 'de_nghi_chi', 'HS-01', 'NCC-01', 'PO-01', 'NV-LAP', 'Chờ duyệt', 'VND',"
        " 500000),"
        " ('PO-DE', 'don_mua', 'HS-01', 'NCC-01', NULL, 'DE-1', 'Chờ duyệt', 'VND', 100000)"
    )
    c.execute(
        "INSERT INTO core.dong_ct (ma_dong, ma_ct, ma_hh, so_luong, don_gia, thanh_tien) VALUES"
        " ('PAY-01-1', 'PAY-01', 'HH-01', 10, 50000, 500000),"
        " ('PO-DE-1', 'PO-DE', 'HH-01', 2, 50000, 100000)"
    )
    c.execute(
        "INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau,"
        " nguoi_duyet, gia_tri, trang_thai) VALUES"
        " ('APR-02', 'HS-01', 'PAY-01', 'de_nghi_chi', 'NV-YC', 'KTT', 500000, 'Chờ duyệt'),"
        " ('APR-01', 'HS-01', 'PO-DE', 'don_mua', 'DE-1', 'TP', 100000, 'Chờ duyệt'),"
        " ('APR-G', 'HS-01', 'PAY-01', 'khong_kiem', 'NV-YC', 'NV-LAP', 500000, 'Chờ duyệt')"
    )
    c.execute(
        "INSERT INTO core.thanh_toan (ma_tt, ma_ct, so_tien, stk_nhan, trang_thai)"
        " VALUES ('TT-01', 'PAY-01', 500000, '0011', 'Chờ chi')"
    )
    c.commit()
    return c


def draft_and_request(c: Conn) -> None:
    """The digital employee drafts DE-DOC (2 x HH-01 at 50000) and asks TP to approve it."""
    de = ctx_for(c)
    call(
        de,
        "create_document",
        loai_ct="don_mua",
        ma_ct="DE-DOC",
        ma_dt="NCC-01",
        lines=[{"ma_hh": "HH-01", "so_luong": 2, "don_gia": 50000}],
    )
    assert call(de, "request_approval", ma_pd="APR-DE", ma_ct="DE-DOC", loai_pd="don_mua") == {
        "ma_pd": "APR-DE",
        "nguoi_duyet": "TP",
    }


def test_the_hand_built_token_is_one_the_platform_never_issues() -> None:
    """Rule 5 at the token tier: the attacker's scope is above the ceiling."""
    t = over_wide_token()
    wide = RoleScope(
        tools=t.tools,
        read=t.read,
        draft=t.draft,
        may_open_approvals=True,
        budget_usd=t.budget_usd,
        autonomy=t.autonomy,
    )
    issuer = TokenIssuer(FixedClock(datetime(2026, 11, 7, tzinfo=UTC)), InMemoryJtiStore())
    with pytest.raises(ValueError, match="^platform rule 5:"):
        scope_token(issuer, DE, wide, "HS-01", "T-1")
    ceiling = PLATFORM_CEILING["so"]
    assert t.tools > ceiling.tools and t.read > ceiling.read and t.draft > ceiling.draft


# --- rule 1: a digital employee never approves anything, including its own drafts --------


def test_rule_1_through_the_tools(arena: Conn) -> None:
    draft_and_request(arena)
    de = ctx_for(arena)
    with tool_refused(1):
        call(de, "decide_approval", ma_pd="APR-DE", decision=APPROVED)
    with tool_refused(1):
        call(de, "update_status", table="chung_tu", key={"ma_ct": "DE-DOC"}, trang_thai=APPROVED)
    with tool_refused(1):
        call(de, "decide_approval", ma_pd="APR-02", decision=APPROVED)  # someone else's
    # The token's draft scope holds phe_duyet; the approval's own tool still guards it.
    with pytest.raises(ToolDenied):
        call(de, "update_status", table="phe_duyet", key={"ma_pd": "APR-DE"}, trang_thai=APPROVED)
    assert scalar(arena, "SELECT trang_thai FROM core.phe_duyet WHERE ma_pd = 'APR-DE'") == PENDING
    assert scalar(arena, "SELECT trang_thai FROM core.chung_tu WHERE ma_ct = 'DE-DOC'") == PENDING


def test_rule_1_through_raw_sql(arena: Conn) -> None:
    before = table_rows(arena, *GATES)
    for statement in (
        "UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-01'",  # own draft's
        "UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-02'",
        "UPDATE core.chung_tu SET trang_thai = 'Đã duyệt' WHERE ma_ct = 'PO-DE'",
        "INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau,"
        " nguoi_duyet, trang_thai) VALUES"
        " ('APR-X', 'HS-01', 'PO-DE', 'don_mua', 'NV-YC', 'TP', 'Đã duyệt')",
        "INSERT INTO core.chung_tu (ma_ct, loai_ct, case_id, nguoi_lap, trang_thai, tien_te)"
        " VALUES ('DOC-X', 'don_mua', 'HS-01', 'NV-YC', 'Đã duyệt', 'VND')",
    ):
        with sql_refused(1), acting_as(arena, DE, "so", GV):
            arena.execute(statement)
    assert scalar(arena, "SELECT count(*) FROM core.phe_duyet WHERE trang_thai = 'Đã duyệt'") == 0
    assert table_rows(arena, *GATES) == before  # Task 13 F3: no write on any targeted row


# --- rule 2: the maker of a document is never its checker ---------------------------------


def test_rule_2_through_the_tools(arena: Conn) -> None:
    de = ctx_for(arena)
    # Policy routes tu_duyet to the digital employee itself: it would check its own request.
    with tool_refused(2):
        call(de, "request_approval", ma_pd="APR-T", ma_ct="PO-DE", loai_pd="tu_duyet")
    # lap_duyet routes to NV-LAP, who made PAY-01.
    with tool_refused(2):
        call(de, "request_approval", ma_pd="APR-L", ma_ct="PAY-01", loai_pd="lap_duyet")
    # A declaration that switches maker-checker off does not switch rule 2 off: the
    # maker NV-LAP, the routed approver of APR-G, still may not decide it.
    with tool_refused(2):
        call(ctx_for(arena, "NV-LAP", "nguoi"), "decide_approval", ma_pd="APR-G", decision=APPROVED)
    asked = "SELECT count(*) FROM core.phe_duyet WHERE ma_pd IN ('APR-T', 'APR-L')"
    assert scalar(arena, asked) == 0
    assert scalar(arena, "SELECT trang_thai FROM core.phe_duyet WHERE ma_pd = 'APR-G'") == PENDING


def test_rule_2_through_raw_sql(arena: Conn) -> None:
    """Rewrite who made a record, so a maker could check it later.

    A digital employee's approve itself is refused by rule 1, which speaks first.
    """
    before = table_rows(arena, *GATES)
    for statement in (
        "UPDATE core.chung_tu SET nguoi_lap = 'NV-KHAC' WHERE ma_ct = 'PO-DE'",
        "UPDATE core.chung_tu SET nguoi_lap = 'NV-KHAC' WHERE ma_ct = 'PAY-01'",
        "UPDATE core.phe_duyet SET nguoi_yeu_cau = 'NV-KHAC' WHERE ma_pd = 'APR-01'",
        "UPDATE core.phe_duyet SET ma_ct = 'PO-01' WHERE ma_pd = 'APR-02'",
    ):
        with sql_refused(2), acting_as(arena, DE, "so", GV):
            arena.execute(statement)
    assert scalar(arena, "SELECT nguoi_lap FROM core.chung_tu WHERE ma_ct = 'PO-DE'") == DE
    assert table_rows(arena, *GATES) == before  # Task 13 F3


# --- rule 3: no money amount without a source --------------------------------------------


def test_rule_3_through_the_tools(arena: Conn) -> None:
    de = ctx_for(arena)
    bad_lines = (
        {"ma_hh": "HH-01", "so_luong": 1, "don_gia": 51000},  # catalogue price is 50000
        {"so_luong": 1, "don_gia": 51000},  # no item, no master value, nothing released
        {"ma_hh": "HH-01", "so_luong": 1, "don_gia": 50000, "chiet_khau": "1.5"},
        {"ma_hh": "HH-01", "so_luong": 1, "don_gia": 50000, "thue_suat": "0.07"},
    )
    for line in bad_lines:
        with tool_refused(3):
            call(de, "create_document", loai_ct="don_mua", ma_ct="DOC-X", lines=[line])
    assert scalar(arena, "SELECT count(*) FROM core.chung_tu WHERE ma_ct = 'DOC-X'") == 0
    # Derived amounts are the tool tier's (ruling R2d): a passed total is ignored.
    call(
        de,
        "create_document",
        loai_ct="don_mua",
        ma_ct="DOC-OK",
        lines=[{"ma_hh": "HH-01", "so_luong": 2, "don_gia": 50000, "thanh_tien": 1}],
        tong_tien=999999999,
        thue_vat=1,
    )
    totals = arena.execute(
        "SELECT tong_tien, thue_vat FROM core.chung_tu WHERE ma_ct = 'DOC-OK'"
    ).fetchone()
    arena.commit()
    assert totals == {"tong_tien": 100000, "thue_vat": 0}


def test_rule_3_through_raw_sql(arena: Conn) -> None:
    """Unsourced unit prices (``don_gia``; derived totals are the tool tier's, R2d)."""
    for statement in (
        "INSERT INTO core.dong_ct (ma_dong, ma_ct, ma_hh, so_luong, don_gia)"
        " VALUES ('PO-DE-9', 'PO-DE', 'HH-01', 1, 51000)",
        "INSERT INTO core.dong_ct (ma_dong, ma_ct, ma_hh, so_luong, don_gia)"
        " VALUES ('PO-DE-9', 'PO-DE', NULL, 1, 51000)",
        "UPDATE core.dong_ct SET don_gia = 51000 WHERE ma_dong = 'PO-DE-1'",
        "UPDATE core.dong_ct SET don_gia = 51000 WHERE ma_dong = 'PAY-01-1'",
    ):
        with sql_refused(3), acting_as(arena, DE, "so", GV):
            arena.execute(statement)
    assert scalar(arena, "SELECT don_gia FROM core.dong_ct WHERE ma_dong = 'PO-DE-1'") == 50000


# --- rule 4: leaving the system needs the linked approval approved --------------------------


def test_rule_4_through_the_tools(arena: Conn) -> None:
    mail = FakeMail()
    de = ctx_for(arena, mail=mail)
    draft_and_request(arena)
    with tool_refused(4):  # APR-DE still pending
        call(de, "pay", ma_tt="TT-X", ma_ct="DE-DOC", ma_pd="APR-DE")
    with tool_refused(4):
        call(de, "notify", ref="DE-DOC", to="ncc@demo.example", ma_pd="APR-DE")
    # A given approval is history: it never clears a gate. APR-02 is approved here (by its
    # routed approver, as given data) and is PAY-01's, so only that clause speaks (F2).
    with acting_as(arena, "KTT", "nguoi", GV):
        arena.execute("UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-02'")
    with tool_refused(4, match="approval APR-02 was not opened by this run"):
        call(de, "pay", ma_tt="TT-X", ma_ct="PAY-01", ma_pd="APR-02")
    # The token's draft scope holds thanh_toan; the payment's own tool still guards it.
    with pytest.raises(ToolDenied):
        call(de, "update_status", table="thanh_toan", key={"ma_tt": "TT-01"}, trang_thai=PAID)
    call(ctx_for(arena, "TP", "nguoi"), "decide_approval", ma_pd="APR-DE", decision=APPROVED)
    with tool_refused(4):  # approved, but the money goes elsewhere
        call(de, "pay", ma_tt="TT-X", ma_ct="DE-DOC", ma_pd="APR-DE", stk_nhan="6666")
    with tool_refused(4):  # approved, but for another document
        call(de, "notify", ref="PAY-01", to="ncc@demo.example", ma_pd="APR-DE")
    with tool_refused(4):
        call(de, "pay", ma_tt="TT-X", ma_ct="PAY-01", ma_pd="APR-DE")
    assert mail.sent == []
    call(de, "pay", ma_tt="TT-DE", ma_ct="DE-DOC", ma_pd="APR-DE")  # the honest payment
    with tool_refused(4):  # once
        call(de, "pay", ma_tt="TT-Y", ma_ct="DE-DOC", ma_pd="APR-DE")
    assert scalar(arena, "SELECT count(*) FROM core.thanh_toan WHERE trang_thai = 'Đã chi'") == 1


def test_rule_4_through_raw_sql(arena: Conn) -> None:
    # PO-01 (15 x 50000, no approval at all) gets its total as given data, so a payment of
    # exactly that total to its partner's account passes the payee check and meets the
    # approval-chain check (Task 13 F1).
    arena.execute("UPDATE core.chung_tu SET tong_tien = 750000 WHERE ma_ct = 'PO-01'")
    arena.commit()
    before = table_rows(arena, *GATES)
    chain = "needs the approval chain"
    for statement, clause in (
        ("UPDATE core.thanh_toan SET trang_thai = 'Đã chi' WHERE ma_tt = 'TT-01'", chain),
        (
            "INSERT INTO core.thanh_toan (ma_tt, ma_ct, so_tien, stk_nhan, trang_thai)"
            " VALUES ('TT-X', 'PAY-01', 500000, '0011', 'Đã chi')",
            chain,
        ),
        (
            "INSERT INTO core.thanh_toan (ma_tt, ma_ct, so_tien, stk_nhan, trang_thai)"
            " VALUES ('TT-X', 'PO-01', 750000, '0011', 'Đã chi')",  # a document with no approval
            "needs the approval chain of PO-01 approved",
        ),
        ("DELETE FROM core.phe_duyet WHERE ma_pd = 'APR-02'", None),  # clear the gate away
        ("TRUNCATE core.phe_duyet CASCADE", None),
        ("TRUNCATE core.thanh_toan", None),
    ):
        with sql_refused(4, match=clause), acting_as(arena, DE, "so", GV):
            arena.execute(statement)
    assert table_rows(arena, *GATES) == before  # Task 13 F3
    # Deleting the linked document itself: stopped by its foreign keys (tolerated).
    for statement in (
        "DELETE FROM core.chung_tu WHERE ma_ct = 'PAY-01'",
        "DELETE FROM core.chung_tu WHERE ma_ct = 'PO-DE'",
    ):
        with sql_refused(4, fk_tolerated=True), acting_as(arena, DE, "so", GV):
            arena.execute(statement)
    assert table_rows(arena, *GATES) == before
    # After approval: the payee and the amount are the document's, and paid is final.
    with acting_as(arena, "KTT", "nguoi", GV):
        arena.execute("UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-02'")
    with acting_as(arena, "NV-LAP", "nguoi", GV):
        arena.execute("UPDATE core.phe_duyet SET trang_thai = 'Từ chối' WHERE ma_pd = 'APR-G'")
    # One approval of the chain rejected: the chain is not approved.
    with sql_refused(4), acting_as(arena, DE, "so", GV):
        arena.execute("UPDATE core.thanh_toan SET trang_thai = 'Đã chi' WHERE ma_tt = 'TT-01'")
    decided = table_rows(arena, *GATES)
    for statement in (
        "UPDATE core.thanh_toan SET stk_nhan = '6666' WHERE ma_tt = 'TT-01'",
        "UPDATE core.thanh_toan SET so_tien = 50000000 WHERE ma_tt = 'TT-01'",
        "UPDATE core.chung_tu SET tong_tien = 50000000 WHERE ma_ct = 'PAY-01'",  # frozen
    ):
        with sql_refused(4), acting_as(arena, DE, "so", GV):
            arena.execute(statement)
    assert scalar(arena, "SELECT trang_thai FROM core.thanh_toan WHERE ma_tt = 'TT-01'") == (
        "Chờ chi"
    )
    assert table_rows(arena, *GATES) == decided  # Task 13 F3


# --- rule 5: a digital employee's rights never exceed the platform ceiling -----------------


def test_rule_5_through_the_tools(arena: Conn) -> None:
    """The token's draft scope reaches past the ceiling: master data and the case record."""
    de = ctx_for(arena)
    with tool_refused(5):  # master data is a person's to write
        call(de, "update_status", table="nhan_su", key={"ma_nv": "NV-01"}, trang_thai="Nghỉ việc")
    with tool_refused(5):  # the case record is outside the ceiling's draft set
        call(de, "update_status", table="ho_so", key={"case_id": "HS-01"}, trang_thai="Tạm dừng")
    # The platform's released money values are no table the tools reach at all.
    with pytest.raises(ToolDenied, match="unknown table"):
        call(de, "read_records", table="nguon_tien", where={})
    assert scalar(arena, "SELECT trang_thai FROM core.nhan_su WHERE ma_nv = 'NV-01'") == "Đang làm"
    assert scalar(arena, "SELECT trang_thai FROM core.ho_so WHERE case_id = 'HS-01'") == (
        "Đang xử lý"
    )
    assert events(arena) == []


def test_rule_5_through_raw_sql(arena: Conn) -> None:
    before = table_rows(arena, *MASTER, *GATES)
    for statement in (
        "UPDATE core.doi_tac SET stk = '6666' WHERE ma_dt = 'NCC-01'",  # the classic attack
        "UPDATE core.hang_hoa SET don_gia = 51000 WHERE ma_hh = 'HH-01'",  # make a price a source
        "INSERT INTO core.hang_hoa (ma_hh, ten, don_vi, loai, don_gia)"
        " VALUES ('HH-99', 'X', 'kg', 'hang', 51000)",
        "UPDATE core.nhan_su SET luong = 51000 WHERE ma_nv = 'NV-01'",
        "INSERT INTO core.ngan_sach (ma_ngs, phong_ban, ky, han_muc)"
        " VALUES ('NGS-99', 'X', 'X', 51000)",
        "DELETE FROM core.tri_thuc WHERE ma_kb = 'KB-01'",
        "TRUNCATE core.doi_tac CASCADE",
        "INSERT INTO core.nguon_tien (case_id, ten, gia_tri) VALUES ('HS-01', 'gia', 51000)",
    ):
        with sql_refused(5), acting_as(arena, DE, "so", GV):
            arena.execute(statement)
    assert scalar(arena, "SELECT stk FROM core.doi_tac WHERE ma_dt = 'NCC-01'") == "0011"
    assert table_rows(arena, *MASTER, *GATES) == before  # Task 13 F3


# --- rule 6: every action is an event in an append-only log, with actor and version -------


def test_rule_6_through_the_tools(arena: Conn) -> None:
    de = ctx_for(arena)
    draft_and_request(arena)
    before = events(arena)
    assert [e["kind"] for e in before] == ["DRAFTED", "REQUESTED"]
    assert all(e["actor"] == DE and e["governance_version"] == GV for e in before)
    # The token's draft scope holds su_kien: still no tool rewrites the log.
    with tool_refused(6):
        call(de, "update_status", table="su_kien", key={"ref": "DE-DOC"}, trang_thai="Hoàn tất")
    # Nor claims, through the log, an action no tool did.
    with pytest.raises(ToolDenied):
        call(de, "record_event", kind="APPROVED", ref="APR-DE")
    assert events(arena) == before


def test_rule_6_through_raw_sql(arena: Conn) -> None:
    with acting_as(arena, DE, "so", GV):
        arena.execute(
            "INSERT INTO core.su_kien (case_id, buoc, kind, ref) VALUES"
            " ('HS-01', 'S1', 'DRAFTED', 'PO-DE')"
        )
    for statement in (
        "UPDATE core.su_kien SET actor = 'TP', kind = 'APPROVED'",
        "UPDATE core.su_kien SET governance_version = 'gv-khac'",
        "DELETE FROM core.su_kien",
        "TRUNCATE core.su_kien",
        "INSERT INTO core.su_kien (case_id, buoc, kind, ref)"
        " VALUES ('HS-01', 'S1', 'ERASED', 'PO-DE')",
    ):
        with sql_refused(6), acting_as(arena, DE, "so", GV):
            arena.execute(statement)
    # A claimed actor and version are overwritten by the session's.
    with acting_as(arena, DE, "so", GV):
        arena.execute(
            "INSERT INTO core.su_kien (case_id, buoc, kind, ref, actor, governance_version)"
            " VALUES ('HS-01', 'S1', 'RECORDED', 'PO-DE', 'TP', 'gv-khac')"
        )
    assert [(e["kind"], e["actor"], e["governance_version"]) for e in events(arena)] == [
        ("DRAFTED", DE, GV),
        ("RECORDED", DE, GV),
    ]


# --- governance: a template cannot grant decide; a run's events carry its version -----------


@pytest.mark.parametrize("how", ["step", "scope"])
def test_template_cannot_grant_decide_to_digital_employee(conn: Conn, how: str) -> None:
    pack = load_company_pack(PACK_DIR)
    template = load_template(TEMPLATE)
    if how == "step":  # the payment approval decided by the digital employee that requests it
        steps = dict(template.steps)
        steps["duyet_chi"] = replace(steps["duyet_chi"], role="nv_de_nghi_chi")
        bad = replace(template, steps=steps)
    else:  # decide_approval written into a digital employee's scope
        roles = tuple(
            replace(r, scope=replace(r.scope, tools=r.scope.tools | {"decide_approval"}))
            if r.id == "nv_de_nghi_chi" and r.scope is not None
            else r
            for r in template.roles
        )
        bad = replace(template, roles=roles)
    assert "DE_DECIDES" not in {f.code for f in validate(template, pack)}
    assert "DE_DECIDES" in {f.code for f in validate(bad, pack) if f.level == "error"}

    conn.execute("INSERT INTO core.ho_so VALUES ('HS-GIU', 'Có sẵn', 'Đang xử lý')")
    conn.commit()
    with pytest.raises(TemplateInvalid, match="DE_DECIDES"):
        run_case(
            conn,
            template=bad,
            pack=pack,
            instance=CaseInstance("HS-T13", "Đơn bán", "Yêu cầu"),
            executor=ScriptedExecutor({}, {}),
            environment=ScriptedEnvironment({}, {}),
            governance_version=GV,
            issuer=TokenIssuer(FixedClock(datetime(2026, 11, 7, tzinfo=UTC)), InMemoryJtiStore()),
        )
    # Refused before anything is written: the database is as it was.
    assert scalar(conn, "SELECT string_agg(case_id, ',') FROM core.ho_so") == "HS-GIU"
    assert scalar(conn, "SELECT count(*) FROM core.su_kien") == 0


def test_events_carry_governance_version(conn: Conn) -> None:
    pack = load_company_pack(PACK_DIR)
    scenarios = json.loads((PACK_DIR / "scenarios.json").read_text(encoding="utf-8"))
    fixture = json.loads((PACK_DIR / "fixture.json").read_text(encoding="utf-8"))
    scenario = next(s for s in scenarios["scenarios"] if s["name"] == "happy")
    case = scenarios["case"]
    version = f"{pack.version}+attack-13"
    result = run_case(
        conn,
        template=load_template(TEMPLATE),
        pack=pack,
        instance=CaseInstance(case["case_id"], case["title"], case["request"]),
        executor=ScriptedExecutor(fixture["executor"], scenario["params"]),
        environment=ScriptedEnvironment(fixture["environment"], scenario["params"]),
        governance_version=version,
        issuer=TokenIssuer(FixedClock(datetime(2026, 11, 6, 9, tzinfo=UTC)), InMemoryJtiStore()),
    )
    assert result.governance_version == version
    logged = conn.execute("SELECT actor, governance_version FROM core.su_kien").fetchall()
    conn.commit()
    assert len(logged) >= 10
    assert {e["governance_version"] for e in logged} == {version}
    assert all(e["actor"] for e in logged)

"""The canon demo case re-expressed as a governance pack (spec call C3), on the generic engine.

The pack ``tests/fixtures/governance/packs/sales-backorder-demo/`` is written from the canon pack by
``tests.fixtures.convert_canon``; the template
``tests/fixtures/governance/templates/sales_order_with_backorder.json`` mirrors the canon flow by
role. The three canon scenarios must come out as the old runtime's did, read through
the table and document mapping on the core tables:

- ``apr_0102``: ``over_cap`` when the sales order carries a ``FLAGGED`` event, else ``normal``;
- ``three_way``: ``chung_tu.ket_qua`` of the purchase invoice;
- ``pay_units``: the quantity of the payment request;
- ``open_units``: ordered minus received.

The run stops waiting at the payment approval, which stays pending.
"""

from __future__ import annotations

import filecmp
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.engine.conftest import Conn, rows
from tests.fixtures.convert_canon import (
    CANON_ROOT,
    convert,
    core_duties,
    core_scope,
    de_scope,
)
from tonomyx.bench.executors import ScriptedEnvironment, ScriptedExecutor
from tonomyx.contracts.clock import FixedClock
from tonomyx.contracts.token import InMemoryJtiStore, TokenIssuer
from tonomyx.engine import CaseInstance, run_case
from tonomyx.governance.binding import bind_roles
from tonomyx.governance.pack import CompanyPack, load_company_pack
from tonomyx.governance.template import ProcessTemplate, load_template
from tonomyx.governance.validate import validate

REPO = Path(__file__).resolve().parents[2]
PACK_DIR = REPO / "tests" / "fixtures" / "governance" / "packs" / "sales-backorder-demo"
TEMPLATE = (
    REPO / "tests" / "fixtures" / "governance" / "templates"
    / "sales_order_with_backorder.json"
)

# The old runtime's outcomes (canon scenarios.json), as the plan states them.
OLD_OUTCOMES = {
    "happy": {"apr_0102": "normal", "three_way": "Khớp", "pay_units": 15, "open_units": 0},
    "discount8": {"apr_0102": "over_cap", "three_way": "Khớp", "pay_units": 15, "open_units": 0},
    "grn12": {"apr_0102": "normal", "three_way": "Cần kiểm", "pay_units": 12, "open_units": 3},
}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _scenarios() -> dict[str, Any]:
    return _json(PACK_DIR / "scenarios.json")


def _scenario(name: str) -> dict[str, Any]:
    return next(s for s in _scenarios()["scenarios"] if s["name"] == name)


def _issuer() -> TokenIssuer:
    return TokenIssuer(FixedClock(datetime(2026, 11, 6, 9, 0, tzinfo=UTC)), InMemoryJtiStore())


def _quantity(conn: Conn, loai_ct: str) -> int:
    [found] = rows(
        conn,
        "SELECT COALESCE(SUM(l.so_luong), 0) AS n FROM core.chung_tu d"
        " LEFT JOIN core.dong_ct l ON l.ma_ct = d.ma_ct WHERE d.loai_ct = %s",
        (loai_ct,),
    )
    return int(found["n"])


def _one_document(conn: Conn, loai_ct: str) -> dict[str, Any]:
    [doc] = rows(conn, "SELECT * FROM core.chung_tu WHERE loai_ct = %s", (loai_ct,))
    return doc


def _observed(conn: Conn) -> dict[str, Any]:
    """The four old measures, read on the core tables."""
    order = _one_document(conn, "don_ban")
    flagged = rows(
        conn,
        "SELECT 1 FROM core.su_kien WHERE kind = 'FLAGGED' AND ref = %s",
        (order["ma_ct"],),
    )
    return {
        "apr_0102": "over_cap" if flagged else "normal",
        "three_way": _one_document(conn, "hoa_don_mua")["ket_qua"],
        "pay_units": _quantity(conn, "de_nghi_chi"),
        "open_units": _quantity(conn, "don_mua") - _quantity(conn, "phieu_nhap"),
    }


@pytest.mark.parametrize("name", ["happy", "discount8", "grn12"])
def test_scenarios_keep_the_old_expectations(name: str) -> None:
    """The converted scenarios carry the old runtime's values, unchanged."""
    assert _scenario(name)["expect"] == OLD_OUTCOMES[name]


@pytest.mark.db
@pytest.mark.parametrize("name", ["happy", "discount8", "grn12"])
def test_canon_scenarios_match_old_outcomes(conn: Conn, name: str) -> None:
    pack = load_company_pack(PACK_DIR)
    template = load_template(TEMPLATE)
    scenarios = _scenarios()
    scenario = _scenario(name)
    fixture = _json(PACK_DIR / "fixture.json")
    case = scenarios["case"]
    result = run_case(
        conn,
        template=template,
        pack=pack,
        instance=CaseInstance(case["case_id"], case["title"], case["request"]),
        executor=ScriptedExecutor(fixture["executor"], scenario["params"]),
        environment=ScriptedEnvironment(fixture["environment"], scenario["params"]),
        governance_version=pack.version,
        issuer=_issuer(),
    )

    assert result.refusals == []
    assert _observed(conn) == scenario["expect"] == OLD_OUTCOMES[name]

    # The run stops waiting at the payment approval, which stays pending with its approver.
    waits = scenarios["stops_at"]
    assert result.stop["type"] == "wait"
    assert result.stop["step"] == waits["step"]
    assert result.stop["for"] == waits["for"]
    [approval] = rows(conn, "SELECT * FROM core.phe_duyet WHERE loai_pd = %s", (waits["loai_pd"],))
    assert (approval["ma_pd"], approval["nguoi_duyet"], approval["trang_thai"]) == (
        waits["ma_pd"],
        waits["nguoi_duyet"],
        "Chờ duyệt",
    )
    # The other two gates were decided by their own approvers.
    decided = rows(
        conn,
        "SELECT loai_pd, nguoi_duyet, trang_thai FROM core.phe_duyet"
        " WHERE trang_thai <> 'Chờ duyệt' ORDER BY loai_pd",
    )
    assert [(a["loai_pd"], a["nguoi_duyet"], a["trang_thai"]) for a in decided] == [
        ("bao_gia", "P2", "Đã duyệt"),
        ("don_mua", "P6", "Đã duyệt"),
    ]


def _thresholds(condition: str) -> tuple[str, Decimal]:
    name, _, number = condition.split()
    return name, Decimal(number)


def cap_guard_mismatches(
    template: ProcessTemplate, pack: CompanyPack, fixture: dict[str, Any]
) -> list[str]:
    """Every fixture condition guarding a step whose params name a policy ``cap``, whose
    threshold is not that cap's value in the pack (ruling R11b)."""
    out = []
    for step in template.steps.values():
        if "cap" not in step.params:
            continue
        cap = pack.policy.caps[step.params["cap"]]
        items = fixture["executor"].get(step.id, [])
        for item in items if isinstance(items, list) else [items]:
            outcome = item.get("outcome")
            conditions = [item.get("if"), outcome.get("if") if isinstance(outcome, dict) else None]
            for condition in filter(None, conditions):
                if _thresholds(condition)[1] != cap:
                    out.append(f"{step.id}: {condition!r} is not cap {cap}")
    return out


def test_fixture_cap_thresholds_are_the_policy_cap() -> None:
    """The scripted digital employee's judgement (apply the discount, or flag it) mirrors the
    pack's policy cap: every threshold guarding a step that names ``cap`` is that cap (R11b)."""
    pack = load_company_pack(PACK_DIR)
    template = load_template(TEMPLATE)
    fixture = _json(PACK_DIR / "fixture.json")
    capped = [s.id for s in template.steps.values() if "cap" in s.params]
    assert capped == ["lap_don_ban", "kiem_tra_chiet_khau"]
    assert all(any("if" in str(i) for i in fixture["executor"][sid]) for sid in capped)
    assert cap_guard_mismatches(template, pack, fixture) == []
    # A pack whose cap moves (the reviewer's probe: 0.10) no longer agrees with the fixture.
    moved = replace(pack, policy=replace(pack.policy, caps={"chiet_khau_toi_da": Decimal("0.10")}))
    assert len(cap_guard_mismatches(template, moved, fixture)) == 4


def test_waits_name_the_decide_step_they_wait_on() -> None:
    """A wait's ``for`` is the id of the decide step that routes to it on pending, and its
    ``approval`` that step's approval (ruling R11c)."""
    template = load_template(TEMPLATE)
    waits = {s.id: s for s in template.steps.values() if s.type == "wait"}
    assert len(waits) == 3
    for step in template.steps.values():
        if step.type == "decide_approval":
            wait = waits[step.on["pending"]]
            assert wait.params["for"] == step.id, wait.id
            assert wait.params["approval"] == step.params["approval"], wait.id


def test_template_validates_with_the_pack() -> None:
    """No errors and no warnings; every template role binds to its canon role code."""
    pack = load_company_pack(PACK_DIR)
    template = load_template(TEMPLATE)
    assert validate(template, pack) == []
    assert bind_roles(template, pack) == {
        "dieu_phoi": ("ORC-HUB",),
        "nv_bao_gia": ("DE-SM-02",),
        "nv_ton_kho": ("DE-OP-01",),
        "nv_mua_hang": ("DE-FN-04",),
        "nv_nhap_kho": ("DE-OP-02",),
        "nv_hoa_don_ban": ("DE-FN-01",),
        "nv_doi_soat": ("DE-FN-02",),
        "nv_de_nghi_chi": ("DE-FN-03",),
        "truong_kinh_doanh": ("P2",),
        "nv_duyet_mua": ("P6",),
        "ke_toan_truong": ("P5",),
        "truong_van_hanh": ("P4",),
        "nha_cung_cap": ("VEND-0003",),
    }


def test_template_scopes_are_the_canon_scopes() -> None:
    """Each digital-employee role of the template carries its canon de_scope row, translated
    to core tables and tools, and the duties its company role binds by (C13)."""
    pack = load_company_pack(PACK_DIR)
    template = load_template(TEMPLATE)
    binding = bind_roles(template, pack)
    rows = de_scope(CANON_ROOT)
    so_roles = [r for r in template.roles if r.kind == "so"]
    assert len(so_roles) == 7
    for role in so_roles:
        assert role.scope is not None
        expected = core_scope(rows[binding[role.id][0]])
        assert {
            "tools": sorted(role.scope.tools),
            "read": sorted(role.scope.read),
            "draft": sorted(role.scope.draft),
            "may_open_approvals": role.scope.may_open_approvals,
            "budget_usd": str(role.scope.budget_usd),
            "autonomy": role.scope.autonomy,
        } == expected, role.id
        duties = core_duties(rows[binding[role.id][0]])
        assert sorted(role.duties.drafts) == duties["drafts"], role.id
        assert role.duties.may_request is duties["may_request"], role.id


def test_pack_follows_the_table_mapping() -> None:
    """cust and vend in doi_tac, item in hang_hoa, emp in nhan_su, kb in tri_thuc; the
    discount cap from the canon policy."""
    pack = load_company_pack(PACK_DIR)
    partners = {r["ma_dt"]: r["loai"] for r in pack.master["doi_tac"]}
    assert partners == {"CUST-0007": "khach_hang", "VEND-0003": "nha_cung_cap"}
    assert {r["ma_hh"] for r in pack.master["hang_hoa"]} == {"ITEM-0005", "ITEM-0012"}
    assert {r["ma_nv"] for r in pack.master["nhan_su"]} == {"EMP-0002", "EMP-0006"}
    assert {r["ma_kb"] for r in pack.master["tri_thuc"]} == {"KB-0001", "KB-0002", "KB-0003"}
    assert [a.id for a in pack.kb] == ["KB-0001", "KB-0002", "KB-0003"]
    assert str(pack.policy.caps["chiet_khau_toi_da"]) == "0.05"
    rules = pack.policy.approval_rules
    assert {k: (r.maker_checker, [t.approver for t in r.tiers]) for k, r in rules.items()} == {
        "bao_gia": (False, ["P2"]),
        "don_mua": (True, ["P6"]),
        "de_nghi_chi": (False, ["P5"]),
    }


def test_converter_is_rerunnable(tmp_path: Path) -> None:
    """Running the converter again writes the same pack, byte for byte."""
    convert(CANON_ROOT, tmp_path)
    convert(CANON_ROOT, tmp_path)  # a second run over its own output changes nothing
    written = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    on_disk = sorted(p.relative_to(PACK_DIR) for p in PACK_DIR.rglob("*") if p.is_file())
    assert written == on_disk
    _, mismatch, errors = filecmp.cmpfiles(tmp_path, PACK_DIR, [str(p) for p in written], False)
    assert (mismatch, errors) == ([], [])

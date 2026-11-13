"""request_approval and decide_approval: routing by the gate, people decide."""

from __future__ import annotations

import pytest

from tests.tools_core.conftest import Conn, MakeCtx, one, rows
from tonomyx.tools.core.approvals import decide_approval, request_approval
from tonomyx.tools.core.documents import create_document
from tonomyx.tools.errors import ToolDenied

pytestmark = pytest.mark.db


def _order(make_ctx: MakeCtx, ma_ct: str, quantity: int) -> None:
    create_document(
        make_ctx(),
        loai_ct="don_mua",
        ma_ct=ma_ct,
        ma_dt="NCC-01",
        lines=[{"ma_hh": "HH-01", "so_luong": quantity, "don_gia": 50000}],
    )


def test_request_routes_to_tier_approver(world: Conn, make_ctx: MakeCtx) -> None:
    _order(make_ctx, "PO-10", 10)  # 500000: first tier
    _order(make_ctx, "PO-11", 30)  # 1500000: open tier
    assert request_approval(make_ctx(), ma_pd="PD-10", ma_ct="PO-10", loai_pd="don_mua") == {
        "ma_pd": "PD-10",
        "nguoi_duyet": "TP",
    }
    assert (
        request_approval(make_ctx(), ma_pd="PD-11", ma_ct="PO-11", loai_pd="don_mua")["nguoi_duyet"]
        == "GD"
    )
    row = one(world, "SELECT * FROM core.phe_duyet WHERE ma_pd = 'PD-10'")
    assert (row["gia_tri"], row["trang_thai"], row["nguoi_yeu_cau"]) == (
        500000,
        "Chờ duyệt",
        "DE-1",
    )
    doc = one(world, "SELECT trang_thai FROM core.chung_tu WHERE ma_ct = 'PO-10'")
    assert doc["trang_thai"] == "Chờ duyệt"
    event = one(world, "SELECT kind, ref FROM core.su_kien WHERE ref = 'PD-10'")
    assert event["kind"] == "REQUESTED"


def test_request_refused_when_the_maker_would_check(make_ctx: MakeCtx) -> None:
    create_document(
        make_ctx("TP", "nguoi"),
        loai_ct="don_mua",
        ma_ct="PO-12",
        lines=[{"ma_hh": "HH-01", "so_luong": 1, "don_gia": 50000}],
    )
    with pytest.raises(ToolDenied, match="platform rule 2"):
        request_approval(make_ctx("TP", "nguoi"), ma_pd="PD-12", ma_ct="PO-12", loai_pd="don_mua")


def test_request_for_an_unknown_approval_type_is_refused(make_ctx: MakeCtx) -> None:
    _order(make_ctx, "PO-13", 1)
    with pytest.raises(ToolDenied, match="hop_dong"):
        request_approval(make_ctx(), ma_pd="PD-13", ma_ct="PO-13", loai_pd="hop_dong")


def test_only_people_decide(world: Conn, make_ctx: MakeCtx) -> None:
    _order(make_ctx, "PO-14", 1)
    request_approval(make_ctx(), ma_pd="PD-14", ma_ct="PO-14", loai_pd="don_mua")
    for decision in ("Đã duyệt", "Từ chối"):
        with pytest.raises(ToolDenied):
            decide_approval(make_ctx(), ma_pd="PD-14", decision=decision)
    with pytest.raises(ToolDenied):
        decide_approval(make_ctx("TP", "ngoai"), ma_pd="PD-14", decision="Đã duyệt")
    assert one(world, "SELECT trang_thai FROM core.phe_duyet")["trang_thai"] == "Chờ duyệt"


def test_routed_person_decides(world: Conn, make_ctx: MakeCtx) -> None:
    _order(make_ctx, "PO-15", 1)
    request_approval(make_ctx(), ma_pd="PD-15", ma_ct="PO-15", loai_pd="don_mua")
    with pytest.raises(ToolDenied):  # not the routed approver
        decide_approval(make_ctx("GD", "nguoi"), ma_pd="PD-15", decision="Đã duyệt")
    out = decide_approval(
        make_ctx("TP", "nguoi"), ma_pd="PD-15", decision="Từ chối", ly_do="Giá cao"
    )
    assert out == {"trang_thai": "Từ chối"}
    row = one(world, "SELECT trang_thai, ly_do FROM core.phe_duyet")
    assert (row["trang_thai"], row["ly_do"]) == ("Từ chối", "Giá cao")
    assert (
        one(world, "SELECT trang_thai FROM core.chung_tu WHERE ma_ct = 'PO-15'")["trang_thai"]
        == "Từ chối"
    )
    event = one(
        world, "SELECT kind, actor FROM core.su_kien WHERE ref = 'PD-15' AND kind <> 'REQUESTED'"
    )
    assert (event["kind"], event["actor"]) == ("REJECTED", "TP")
    with pytest.raises(ToolDenied, match="Chờ duyệt"):  # decided once
        decide_approval(make_ctx("TP", "nguoi"), ma_pd="PD-15", decision="Đã duyệt")


def test_decision_must_be_approve_or_reject(make_ctx: MakeCtx) -> None:
    _order(make_ctx, "PO-16", 1)
    request_approval(make_ctx(), ma_pd="PD-16", ma_ct="PO-16", loai_pd="don_mua")
    with pytest.raises(ToolDenied):
        decide_approval(make_ctx("TP", "nguoi"), ma_pd="PD-16", decision="Hoàn tất")  # type: ignore[arg-type]


def test_second_request_while_one_of_this_run_is_pending_is_refused(
    world: Conn, make_ctx: MakeCtx
) -> None:
    _order(make_ctx, "PO-17", 1)
    request_approval(make_ctx(), ma_pd="PD-17", ma_ct="PO-17", loai_pd="don_mua")
    with pytest.raises(ToolDenied, match="platform gate"):  # one of this run is pending
        request_approval(make_ctx(), ma_pd="PD-17b", ma_ct="PO-17", loai_pd="de_nghi_chi")
    decide_approval(make_ctx("TP", "nguoi"), ma_pd="PD-17", decision="Từ chối")
    request_approval(make_ctx(), ma_pd="PD-17c", ma_ct="PO-17", loai_pd="don_mua")  # after a no
    assert len(rows(world, "SELECT 1 FROM core.phe_duyet WHERE ma_ct = 'PO-17'")) == 2


def test_two_approvals_of_one_type_in_sequence(world: Conn, make_ctx: MakeCtx) -> None:
    _order(make_ctx, "PO-18", 1)
    for ma_pd in ("PD-18a", "PD-18b"):
        request_approval(make_ctx(), ma_pd=ma_pd, ma_ct="PO-18", loai_pd="don_mua")
        decide_approval(make_ctx("TP", "nguoi"), ma_pd=ma_pd, decision="Đã duyệt")
    found = rows(world, "SELECT trang_thai FROM core.phe_duyet WHERE ma_ct = 'PO-18'")
    assert [r["trang_thai"] for r in found] == ["Đã duyệt", "Đã duyệt"]


def test_given_approvals_never_block_a_request(world: Conn, make_ctx: MakeCtx) -> None:
    _order(make_ctx, "PO-19", 1)
    world.execute(
        "INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau, nguoi_duyet,"
        " gia_tri, trang_thai) VALUES"
        " ('PD-OLD-1', 'HS-01', 'PO-19', 'don_mua', 'NV-X', 'TP', 50000, 'Đã duyệt'),"
        " ('PD-OLD-2', 'HS-01', 'PO-19', 'don_mua', 'NV-X', 'TP', 50000, 'Chờ duyệt')"
    )
    world.commit()
    assert (
        request_approval(make_ctx(), ma_pd="PD-19", ma_ct="PO-19", loai_pd="don_mua")["nguoi_duyet"]
        == "TP"
    )


# --- carried over from the retired runtime's tests (tests/MIGRATION.md) -------------------


def test_an_existing_approval_id_is_never_reused(world: Conn, make_ctx: MakeCtx) -> None:
    """A second request under a taken id opens nothing (was tools/test_create_approval.py)."""
    _order(make_ctx, "PO-20", 1)
    _order(make_ctx, "PO-21", 1)
    request_approval(make_ctx(), ma_pd="PD-20", ma_ct="PO-20", loai_pd="don_mua")
    with pytest.raises(ToolDenied, match="PD-20 already exists"):
        request_approval(make_ctx(), ma_pd="PD-20", ma_ct="PO-21", loai_pd="de_nghi_chi")
    row = one(world, "SELECT ma_ct, loai_pd FROM core.phe_duyet WHERE ma_pd = 'PD-20'")
    assert (row["ma_ct"], row["loai_pd"]) == ("PO-20", "don_mua")
    doc = one(world, "SELECT trang_thai FROM core.chung_tu WHERE ma_ct = 'PO-21'")
    assert doc["trang_thai"] == "Nháp"


def test_deciding_an_unknown_approval_is_refused(world: Conn, make_ctx: MakeCtx) -> None:
    """Was api/test_app.py::test_an_unknown_approval_is_a_404."""
    with pytest.raises(ToolDenied):
        decide_approval(make_ctx("TP", "nguoi"), ma_pd="PD-NONE", decision="Đã duyệt")
    assert rows(world, "SELECT 1 FROM core.su_kien") == []

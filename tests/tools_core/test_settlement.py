"""reconcile, pay and notify: rule 4 at the tool tier."""

from __future__ import annotations

import pytest

from tests.tools_core.conftest import Conn, MakeCtx, one, rows, token
from tonomyx.tools.core.approvals import decide_approval, request_approval
from tonomyx.tools.core.documents import create_document, update_status
from tonomyx.tools.core.settlement import notify, pay, reconcile
from tonomyx.tools.errors import ToolDenied
from tonomyx.tools.ports import RecordingMailSender

pytestmark = pytest.mark.db


def _payment_request(make_ctx: MakeCtx, *, approve: bool | None) -> None:
    """PAY-01 for 15 x HH-01 to NCC-01, approval PD-01 routed to KTT; decided when asked."""
    create_document(
        make_ctx(),
        loai_ct="de_nghi_chi",
        ma_ct="PAY-01",
        ma_dt="NCC-01",
        ct_goc="INV-01",
        lines=[{"ma_hh": "HH-01", "so_luong": 15, "don_gia": 50000}],
    )
    request_approval(make_ctx(), ma_pd="PD-01", ma_ct="PAY-01", loai_pd="de_nghi_chi")
    if approve is not None:
        decide_approval(
            make_ctx("KTT", "nguoi"), ma_pd="PD-01", decision="Đã duyệt" if approve else "Từ chối"
        )


# --- reconcile ------------------------------------------------------------------


def test_reconcile_reports_shortfall(world: Conn, make_ctx: MakeCtx) -> None:
    out = reconcile(make_ctx(), doc="INV-01", ordered="PO-01", received="GRN-01")
    assert out["result"] == "Cần kiểm"
    assert out["diff"] == {"HH-01": -3}
    assert (
        one(world, "SELECT ket_qua FROM core.chung_tu WHERE ma_ct = 'INV-01'")["ket_qua"]
        == "Cần kiểm"
    )
    event = one(world, "SELECT kind, ref FROM core.su_kien")
    assert (event["kind"], event["ref"]) == ("RECONCILED", "INV-01")


def test_reconcile_matches_full_receipt(world: Conn, make_ctx: MakeCtx) -> None:
    world.execute("UPDATE core.dong_ct SET so_luong = 15 WHERE ma_dong = 'GRN-01-1'")
    world.commit()
    out = reconcile(make_ctx(), doc="INV-01", ordered="PO-01", received=["GRN-01"])
    assert out == {"result": "Khớp", "diff": {}}


def test_reconcile_flags_price_beyond_tolerance(world: Conn, make_ctx: MakeCtx) -> None:
    world.execute("UPDATE core.dong_ct SET so_luong = 15 WHERE ma_dong = 'GRN-01-1'")
    world.execute("UPDATE core.dong_ct SET don_gia = 53000 WHERE ma_dong = 'INV-01-1'")  # +6% > 5%
    world.commit()
    assert (
        reconcile(make_ctx(), doc="INV-01", ordered="PO-01", received="GRN-01")["result"]
        == "Cần kiểm"
    )


def test_reconcile_refuses_documents_of_another_case(make_ctx: MakeCtx) -> None:
    with pytest.raises(ToolDenied):
        reconcile(make_ctx(), doc="INV-01", ordered="X-01", received="GRN-01")


# --- pay ------------------------------------------------------------------------


def test_pay_without_approved_approval_is_refused(world: Conn, make_ctx: MakeCtx) -> None:
    _payment_request(make_ctx, approve=None)
    with pytest.raises(ToolDenied, match="platform rule 4"):
        pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01")
    assert rows(world, "SELECT 1 FROM core.thanh_toan") == []
    assert rows(world, "SELECT 1 FROM core.su_kien WHERE kind = 'PAID'") == []


def test_pay_after_rejection_is_refused(make_ctx: MakeCtx) -> None:
    _payment_request(make_ctx, approve=False)
    with pytest.raises(ToolDenied, match="platform rule 4"):
        pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01")


def test_pay_with_an_approval_of_another_document_is_refused(make_ctx: MakeCtx) -> None:
    _payment_request(make_ctx, approve=True)
    create_document(
        make_ctx(),
        loai_ct="de_nghi_chi",
        ma_ct="PAY-02",
        ma_dt="NCC-01",
        lines=[{"ma_hh": "HH-01", "so_luong": 1, "don_gia": 50000}],
    )
    with pytest.raises(ToolDenied, match="platform rule 4"):
        pay(make_ctx(), ma_tt="TT-02", ma_ct="PAY-02", ma_pd="PD-01")


def test_pay_with_a_given_approval_is_refused(world: Conn, make_ctx: MakeCtx) -> None:
    # An approval in the given data is history: it never clears a payment of this run.
    create_document(
        make_ctx(),
        loai_ct="de_nghi_chi",
        ma_ct="PAY-03",
        ma_dt="NCC-01",
        lines=[{"ma_hh": "HH-01", "so_luong": 1, "don_gia": 50000}],
    )
    world.execute(
        "INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau, nguoi_duyet,"
        " gia_tri, trang_thai) VALUES ('PD-OLD', 'HS-01', 'PAY-03', 'de_nghi_chi', 'NV-X', 'KTT',"
        " 50000, 'Đã duyệt')"
    )
    world.commit()
    with pytest.raises(ToolDenied, match="this run"):
        pay(make_ctx(), ma_tt="TT-03", ma_ct="PAY-03", ma_pd="PD-OLD")


def test_pay_after_approval_records_paid_event(world: Conn, make_ctx: MakeCtx) -> None:
    _payment_request(make_ctx, approve=True)
    out = pay(make_ctx(step_id="S-PAY"), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01")
    assert out == {"ma_tt": "TT-01"}
    payment = one(world, "SELECT * FROM core.thanh_toan")
    assert (payment["so_tien"], payment["stk_nhan"], payment["trang_thai"]) == (
        750000,
        "0011",
        "Đã chi",
    )
    event = one(world, "SELECT kind, ref, buoc, actor FROM core.su_kien WHERE kind = 'PAID'")
    assert event == {"kind": "PAID", "ref": "TT-01", "buoc": "S-PAY", "actor": "DE-1"}
    with pytest.raises(ToolDenied, match="platform rule 4"):  # paid once
        pay(make_ctx(), ma_tt="TT-02", ma_ct="PAY-01", ma_pd="PD-01")


def test_pay_refuses_another_account(world: Conn, make_ctx: MakeCtx) -> None:
    _payment_request(make_ctx, approve=True)
    with pytest.raises(ToolDenied, match="platform rule 4"):
        pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01", stk_nhan="9999")
    pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01", stk_nhan="0011")
    assert one(world, "SELECT stk_nhan FROM core.thanh_toan")["stk_nhan"] == "0011"


def test_pay_with_invoice_needs_a_matched_reconciliation(world: Conn, make_ctx: MakeCtx) -> None:
    _payment_request(make_ctx, approve=True)
    with pytest.raises(ToolDenied, match="INV-01"):  # not reconciled in this run
        pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01", invoice="INV-01")
    reconcile(make_ctx(), doc="INV-01", ordered="PO-01", received="GRN-01")  # Cần kiểm
    with pytest.raises(ToolDenied, match="Cần kiểm"):
        pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01", invoice="INV-01")
    world.execute("UPDATE core.dong_ct SET so_luong = 15 WHERE ma_dong = 'GRN-01-1'")
    world.commit()
    reconcile(make_ctx(), doc="INV-01", ordered="PO-01", received="GRN-01")  # Khớp
    pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01", invoice="INV-01")


# --- notify ---------------------------------------------------------------------


def test_notify_needs_approved_approval(world: Conn, make_ctx: MakeCtx) -> None:
    mail = RecordingMailSender()
    _payment_request(make_ctx, approve=None)
    with pytest.raises(ToolDenied, match="platform rule 4"):
        notify(make_ctx(mail=mail), ref="PAY-01", to="NCC-01", ma_pd="PD-01")
    assert mail.sent == []
    decide_approval(make_ctx("KTT", "nguoi"), ma_pd="PD-01", decision="Đã duyệt")
    with pytest.raises(
        ToolDenied, match="platform rule 4"
    ):  # the approval is for PAY-01, not INV-01
        notify(make_ctx(mail=mail), ref="INV-01", to="NCC-01", ma_pd="PD-01")
    assert notify(make_ctx(mail=mail), ref="PAY-01", to="NCC-01", ma_pd="PD-01") == {"sent": True}
    assert [m["to"] for m in mail.sent] == ["NCC-01"]
    event = one(world, "SELECT kind, ref, mo_ta FROM core.su_kien WHERE kind = 'SENT'")
    assert (event["ref"], event["mo_ta"]) == ("PAY-01", "to: NCC-01")


def test_notify_never_reaches_a_real_address(make_ctx: MakeCtx) -> None:
    _payment_request(make_ctx, approve=True)
    with pytest.raises(ToolDenied, match="demo"):
        notify(make_ctx(mail=RecordingMailSender()), ref="PAY-01", to="a@real.vn", ma_pd="PD-01")
    with pytest.raises(ToolDenied, match="mail"):
        notify(make_ctx(), ref="PAY-01", to="NCC-01", ma_pd="PD-01")


# --- fix round 1 ----------------------------------------------------------------


def test_notify_ref_must_be_the_approved_document_or_approval(
    world: Conn, make_ctx: MakeCtx
) -> None:
    mail = RecordingMailSender()
    _payment_request(make_ctx, approve=True)
    for ref in (
        "X-01",
        "anything at all",
        "PO-01",
    ):  # another case's document, free text, another doc
        with pytest.raises(ToolDenied, match="platform rule 4"):
            notify(make_ctx(mail=mail), ref=ref, to="NCC-01", ma_pd="PD-01")
    assert mail.sent == []
    assert notify(make_ctx(mail=mail), ref="PD-01", to="NCC-01", ma_pd="PD-01") == {"sent": True}
    assert notify(make_ctx(mail=mail), ref="PAY-01", to="NCC-01", ma_pd="PD-01") == {"sent": True}
    assert len(mail.sent) == 2


def test_notify_demo_address_has_exactly_one_at(make_ctx: MakeCtx) -> None:
    _payment_request(make_ctx, approve=True)
    mail = RecordingMailSender()
    with pytest.raises(ToolDenied, match="demo"):
        notify(make_ctx(mail=mail), ref="PAY-01", to="a@evil.com@demo.example", ma_pd="PD-01")
    notify(make_ctx(mail=mail), ref="PAY-01", to="ncc@demo.example", ma_pd="PD-01")
    assert [m["to"] for m in mail.sent] == ["ncc@demo.example"]


def test_pay_with_unknown_amount_is_refused(world: Conn, make_ctx: MakeCtx) -> None:
    person = make_ctx("NV-X", "nguoi")
    create_document(
        person,
        loai_ct="de_nghi_chi",
        ma_ct="PAY-09",
        ma_dt="NCC-01",
        lines=[{"ma_hh": "HH-01", "so_luong": 1}],
    )  # no price: tong_tien unknown
    request_approval(person, ma_pd="PD-09", ma_ct="PAY-09", loai_pd="de_nghi_chi")
    decide_approval(make_ctx("KTT", "nguoi"), ma_pd="PD-09", decision="Đã duyệt")
    with pytest.raises(ToolDenied, match="platform rule 4"):
        pay(make_ctx(), ma_tt="TT-09", ma_ct="PAY-09", ma_pd="PD-09")
    assert rows(world, "SELECT 1 FROM core.thanh_toan") == []


# --- fix round 2: multi-level approval chains (ruling R6e) ------------------------


def test_two_level_chain_then_pay(world: Conn, make_ctx: MakeCtx) -> None:
    _payment_request(make_ctx, approve=True)  # PD-01 de_nghi_chi, approved by KTT
    out = request_approval(make_ctx(), ma_pd="PD-02", ma_ct="PAY-01", loai_pd="pduyet_cuoi")
    assert out["nguoi_duyet"] == "GD"
    with pytest.raises(ToolDenied, match="platform rule 4"):  # PD-02 still pending
        pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01")
    decide_approval(make_ctx("GD", "nguoi"), ma_pd="PD-02", decision="Đã duyệt")
    pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-02")
    assert one(world, "SELECT so_tien, trang_thai FROM core.thanh_toan") == {
        "so_tien": 750000,
        "trang_thai": "Đã chi",
    }


def test_pay_needs_thanh_toan_in_the_draft_scope(world: Conn, make_ctx: MakeCtx) -> None:
    """Final review I4: a payment writes thanh_toan, so the token must let it draft it."""
    _payment_request(make_ctx, approve=True)
    narrow = token(draft=frozenset({"chung_tu", "dong_ct"}))
    with pytest.raises(ToolDenied, match="may not write thanh_toan"):
        pay(make_ctx(tok=narrow), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01")
    assert rows(world, "SELECT * FROM core.thanh_toan") == []
    pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01")


def test_a_paid_document_takes_no_new_request(world: Conn, make_ctx: MakeCtx) -> None:
    """Final review M4: a request on a paid document is refused."""
    _payment_request(make_ctx, approve=True)
    pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01")
    with pytest.raises(ToolDenied, match="PAY-01 is paid"):
        request_approval(make_ctx(), ma_pd="PD-09", ma_ct="PAY-01", loai_pd="de_nghi_chi")
    assert one(world, "SELECT trang_thai FROM core.chung_tu WHERE ma_ct = 'PAY-01'") == {
        "trang_thai": "Đã duyệt"
    }


def test_a_digital_employee_never_moves_a_paid_document(world: Conn, make_ctx: MakeCtx) -> None:
    _payment_request(make_ctx, approve=True)
    pay(make_ctx(), ma_tt="TT-01", ma_ct="PAY-01", ma_pd="PD-01")
    world.execute("UPDATE core.chung_tu SET trang_thai = 'Đã thực hiện' WHERE ma_ct = 'PAY-01'")
    world.commit()
    with pytest.raises(ToolDenied, match="PAY-01: it is paid"):
        update_status(
            make_ctx(), table="chung_tu", key={"ma_ct": "PAY-01"}, trang_thai="Nháp"
        )


# --- carried over from the retired runtime's tests (tests/MIGRATION.md) -------------------


class _BrokenMailSender:
    """A mail port whose delivery always fails."""

    def send(self, to: str, subject: str, body: str) -> None:
        raise ConnectionError("mail server unreachable")


def test_a_failed_send_reports_no_success_and_records_no_event(
    world: Conn, make_ctx: MakeCtx
) -> None:
    """The system never claims it sent what it did not send (was tools/test_send_email.py)."""
    _payment_request(make_ctx, approve=True)
    with pytest.raises(ConnectionError):
        notify(make_ctx(mail=_BrokenMailSender()), ref="PAY-01", to="NCC-01", ma_pd="PD-01")
    assert rows(world, "SELECT 1 FROM core.su_kien WHERE kind = 'SENT'") == []


def test_reconcile_never_edits_its_sources(world: Conn, make_ctx: MakeCtx) -> None:
    """Only ``ket_qua`` of the reconciled document changes (was tools/test_match_three_way.py)."""
    lines = "SELECT * FROM core.dong_ct ORDER BY ma_dong"
    docs = "SELECT ma_ct, trang_thai, tong_tien, ket_qua FROM core.chung_tu ORDER BY ma_ct"
    lines_before, docs_before = rows(world, lines), rows(world, docs)
    reconcile(make_ctx(), doc="INV-01", ordered="PO-01", received="GRN-01")
    assert rows(world, lines) == lines_before
    expected = [
        {**d, "ket_qua": "Cần kiểm"} if d["ma_ct"] == "INV-01" else d for d in docs_before
    ]
    assert rows(world, docs) == expected

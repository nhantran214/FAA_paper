"""create_document, update_status and compute_amount on the core tables."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.tools_core.conftest import Conn, MakeCtx, one, rows, token
from tonomyx.tools.core.documents import compute_amount, create_document, update_status
from tonomyx.tools.errors import ToolDenied

pytestmark = pytest.mark.db


def test_create_document_computes_derived_money(world: Conn, make_ctx: MakeCtx) -> None:
    out = create_document(
        make_ctx(),
        loai_ct="don_mua",
        ma_ct="PO-02",
        ma_dt="NCC-01",
        lines=[
            {"ma_hh": "HH-01", "so_luong": 10, "don_gia": 50000, "thanh_tien": 1},
            {"ma_hh": "HH-02", "so_luong": 2, "don_gia": 30000, "thanh_tien": 999999999},
        ],
    )
    assert out == {"ma_ct": "PO-02"}
    doc = one(world, "SELECT * FROM core.chung_tu WHERE ma_ct = 'PO-02'")
    assert doc["tong_tien"] == 560000
    assert doc["thue_vat"] == 0
    assert doc["trang_thai"] == "Nháp"
    assert doc["nguoi_lap"] == "DE-1"
    assert doc["case_id"] == "HS-01"
    amounts = [
        r["thanh_tien"]
        for r in rows(
            world, "SELECT thanh_tien FROM core.dong_ct WHERE ma_ct = 'PO-02' ORDER BY ma_dong"
        )
    ]
    assert amounts == [500000, 60000]
    event = one(world, "SELECT * FROM core.su_kien")
    assert (event["kind"], event["ref"]) == ("DRAFTED", "PO-02")


def test_create_document_applies_discount_and_vat(world: Conn, make_ctx: MakeCtx) -> None:
    create_document(
        make_ctx("NV-MUA", "nguoi"),
        loai_ct="don_mua",
        ma_ct="PO-03",
        lines=[
            {
                "ma_hh": "HH-01",
                "so_luong": 3,
                "don_gia": 333,
                "chiet_khau": "0.1",
                "thue_suat": "0.1",
            }
        ],
    )
    doc = one(world, "SELECT thue_vat, tong_tien FROM core.chung_tu WHERE ma_ct = 'PO-03'")
    # 3 x 333 x 0.9 = 899.1 -> 899; VAT 89.9 -> 90
    assert (doc["thue_vat"], doc["tong_tien"]) == (90, 989)


def test_unknown_unit_price_leaves_totals_unknown(world: Conn, make_ctx: MakeCtx) -> None:
    create_document(
        make_ctx(),
        loai_ct="don_mua",
        ma_ct="PO-04",
        lines=[
            {"ma_hh": "HH-01", "so_luong": 1, "don_gia": 50000},
            {"mo_ta": "Phí", "so_luong": 1},
        ],
    )
    doc = one(world, "SELECT thue_vat, tong_tien FROM core.chung_tu WHERE ma_ct = 'PO-04'")
    assert (doc["thue_vat"], doc["tong_tien"]) == (None, None)


def test_invented_unit_price_is_refused(world: Conn, make_ctx: MakeCtx) -> None:
    line = {"ma_hh": "HH-01", "so_luong": 1, "don_gia": 51000}
    with pytest.raises(ToolDenied, match="platform rule 3"):
        create_document(make_ctx(), loai_ct="don_mua", ma_ct="PO-05", lines=[line])
    assert rows(world, "SELECT 1 FROM core.chung_tu WHERE ma_ct = 'PO-05'") == []
    assert rows(world, "SELECT 1 FROM core.su_kien") == []

    create_document(make_ctx("NCC-01", "ngoai"), loai_ct="don_mua", ma_ct="PO-05", lines=[line])
    assert (
        one(world, "SELECT tong_tien FROM core.chung_tu WHERE ma_ct = 'PO-05'")["tong_tien"]
        == 51000
    )


def test_unit_price_from_the_source_document_is_accepted(world: Conn, make_ctx: MakeCtx) -> None:
    world.execute("UPDATE core.dong_ct SET don_gia = 48000 WHERE ma_dong = 'INV-01-1'")
    world.commit()
    create_document(
        make_ctx(),
        loai_ct="de_nghi_chi",
        ma_ct="PAY-02",
        ma_dt="NCC-01",
        ct_goc="INV-01",
        lines=[{"ma_hh": "HH-01", "so_luong": 15, "don_gia": 48000}],
    )
    with pytest.raises(ToolDenied, match="platform rule 3"):  # the source prices HH-01, not HH-02
        create_document(
            make_ctx(),
            loai_ct="de_nghi_chi",
            ma_ct="PAY-03",
            ct_goc="INV-01",
            lines=[{"ma_hh": "HH-02", "so_luong": 1, "don_gia": 48000}],
        )


def test_source_document_of_another_case_is_refused(make_ctx: MakeCtx) -> None:
    with pytest.raises(ToolDenied, match="X-01"):
        create_document(make_ctx(), loai_ct="don_mua", ma_ct="PO-06", ct_goc="X-01", lines=[])


def test_unknown_line_field_is_refused(make_ctx: MakeCtx) -> None:
    with pytest.raises(ToolDenied, match="gia_ban"):
        create_document(
            make_ctx(),
            loai_ct="don_mua",
            ma_ct="PO-07",
            lines=[{"ma_hh": "HH-01", "so_luong": 1, "gia_ban": 5}],
        )


def test_digital_employee_cannot_set_approved_status(world: Conn, make_ctx: MakeCtx) -> None:
    for status in ("Đã duyệt", "Hoàn tất"):
        # The refusal names the row it was asked to change.
        with pytest.raises(ToolDenied, match="INV-01"):
            update_status(make_ctx(), table="chung_tu", key={"ma_ct": "INV-01"}, trang_thai=status)
    assert (
        one(world, "SELECT trang_thai FROM core.chung_tu WHERE ma_ct = 'INV-01'")["trang_thai"]
        == "Nháp"
    )
    assert rows(world, "SELECT 1 FROM core.su_kien") == []


def test_update_status_changes_one_row(world: Conn, make_ctx: MakeCtx) -> None:
    out = update_status(
        make_ctx(), table="chung_tu", key={"ma_ct": "INV-01"}, trang_thai="Đã thực hiện"
    )
    assert out["row"]["trang_thai"] == "Đã thực hiện"
    event = one(world, "SELECT kind, ref FROM core.su_kien")
    assert (event["kind"], event["ref"]) == ("STATUS_CHANGED", "INV-01")


def test_update_status_never_touches_approvals_payments_or_gate_statuses(make_ctx: MakeCtx) -> None:
    with pytest.raises(ToolDenied):
        update_status(
            make_ctx("KTT", "nguoi"), table="phe_duyet", key={"ma_pd": "A"}, trang_thai="Đã duyệt"
        )
    with pytest.raises(ToolDenied):
        update_status(
            make_ctx("KTT", "nguoi"),
            table="chung_tu",
            key={"ma_ct": "INV-01"},
            trang_thai="Chờ duyệt",
        )


def test_update_status_of_another_case_is_refused(make_ctx: MakeCtx) -> None:
    with pytest.raises(ToolDenied):
        update_status(
            make_ctx("NV-MUA", "nguoi"),
            table="chung_tu",
            key={"ma_ct": "X-01"},
            trang_thai="Đã hủy",
        )


def test_database_refusal_becomes_tool_denied(world: Conn, make_ctx: MakeCtx) -> None:
    # An outside party may not rewrite master data: the database tier (rule 5) refuses.
    with pytest.raises(ToolDenied, match="^platform rule 5"):
        update_status(
            make_ctx("NCC-01", "ngoai"),
            table="nhan_su",
            key={"ma_nv": "NV-01"},
            trang_thai="Nghỉ việc",
        )
    assert one(world, "SELECT trang_thai FROM core.nhan_su")["trang_thai"] == "Đang làm"


def test_refused_call_rolls_back_only_itself(world: Conn, make_ctx: MakeCtx) -> None:
    world.execute("SELECT 1")  # an open outer transaction, as an engine run may hold
    create_document(
        make_ctx(),
        loai_ct="don_mua",
        ma_ct="PO-08",
        lines=[{"ma_hh": "HH-01", "so_luong": 1, "don_gia": 50000}],
    )
    with pytest.raises(ToolDenied):
        create_document(
            make_ctx(),
            loai_ct="don_mua",
            ma_ct="PO-09",
            lines=[{"ma_hh": "HH-01", "so_luong": 1, "don_gia": 1}],
        )
    update_status(make_ctx(), table="chung_tu", key={"ma_ct": "PO-08"}, trang_thai="Đã hủy")
    world.commit()
    assert [
        r["ma_ct"]
        for r in rows(
            world,
            "SELECT ma_ct FROM core.chung_tu WHERE ma_ct LIKE 'PO-0_'"
            " AND ma_ct <> 'PO-01' ORDER BY 1",
        )
    ] == ["PO-08"]
    assert len(rows(world, "SELECT 1 FROM core.su_kien")) == 2


def test_compute_amount_records_the_variable(world: Conn, make_ctx: MakeCtx) -> None:
    out = compute_amount(
        make_ctx(), var="tam_ung", value=Decimal("1500000"), basis="3 ngày x 500000"
    )
    assert out == {"var": "tam_ung"}
    event = one(world, "SELECT kind, ref, mo_ta FROM core.su_kien")
    assert event["kind"] == "RECORDED"
    assert event["ref"] == "tam_ung"
    assert "1500000" in event["mo_ta"] and "3 ngày x 500000" in event["mo_ta"]


# --- fix round 1: rates on a digital employee's lines (ruling R6c), derived kwargs --------


def _line(**extra: object) -> dict[str, object]:
    return {"ma_hh": "HH-01", "so_luong": 1, "don_gia": 50000, **extra}


def test_discount_outside_zero_to_one_is_refused(world: Conn, make_ctx: MakeCtx) -> None:
    for discount in (-9, "1.5"):
        with pytest.raises(ToolDenied, match="platform rule 3"):
            create_document(
                make_ctx(), loai_ct="don_mua", ma_ct="PO-30", lines=[_line(chiet_khau=discount)]
            )
    assert rows(world, "SELECT 1 FROM core.chung_tu WHERE ma_ct = 'PO-30'") == []


def test_discount_above_the_item_cap_is_refused(world: Conn, make_ctx: MakeCtx) -> None:
    world.execute("UPDATE core.hang_hoa SET ck_toi_da = 0.2 WHERE ma_hh = 'HH-01'")
    world.commit()
    with pytest.raises(ToolDenied, match="platform rule 3"):
        create_document(
            make_ctx(), loai_ct="don_mua", ma_ct="PO-31", lines=[_line(chiet_khau="0.5")]
        )
    create_document(make_ctx(), loai_ct="don_mua", ma_ct="PO-31", lines=[_line(chiet_khau="0.2")])
    assert (
        one(world, "SELECT tong_tien FROM core.chung_tu WHERE ma_ct = 'PO-31'")["tong_tien"]
        == 40000
    )


def test_vat_rate_must_be_a_statutory_rate(world: Conn, make_ctx: MakeCtx) -> None:
    with pytest.raises(ToolDenied, match="platform rule 3"):
        create_document(make_ctx(), loai_ct="don_mua", ma_ct="PO-32", lines=[_line(thue_suat=99)])
    create_document(make_ctx(), loai_ct="don_mua", ma_ct="PO-32", lines=[_line(thue_suat="0.1")])
    doc = one(world, "SELECT thue_vat, tong_tien FROM core.chung_tu WHERE ma_ct = 'PO-32'")
    assert (doc["thue_vat"], doc["tong_tien"]) == (5000, 55000)


def test_a_person_may_write_any_rate(world: Conn, make_ctx: MakeCtx) -> None:
    create_document(
        make_ctx("NV-MUA", "nguoi"),
        loai_ct="don_mua",
        ma_ct="PO-33",
        lines=[_line(chiet_khau="0.5", thue_suat="0.2")],
    )
    assert (
        one(world, "SELECT tong_tien FROM core.chung_tu WHERE ma_ct = 'PO-33'")["tong_tien"]
        == 30000
    )


def test_document_level_derived_values_are_ignored(world: Conn, make_ctx: MakeCtx) -> None:
    create_document(
        make_ctx(), loai_ct="don_mua", ma_ct="PO-34", lines=[_line()], tong_tien=1, thue_vat=999
    )
    doc = one(world, "SELECT thue_vat, tong_tien FROM core.chung_tu WHERE ma_ct = 'PO-34'")
    assert (doc["thue_vat"], doc["tong_tien"]) == (0, 50000)


@pytest.mark.parametrize("decision", ["Đã duyệt", "Từ chối"])
def test_a_digital_employee_never_moves_a_decided_document(
    world: Conn, make_ctx: MakeCtx, decision: str
) -> None:
    """Final review M4: a decision stands; a person may still close the document."""
    world.execute("UPDATE core.chung_tu SET trang_thai = %s WHERE ma_ct = 'PO-01'", (decision,))
    world.commit()
    with pytest.raises(ToolDenied, match="out of its decision"):
        update_status(make_ctx(), table="chung_tu", key={"ma_ct": "PO-01"}, trang_thai="Nháp")
    assert one(world, "SELECT trang_thai FROM core.chung_tu WHERE ma_ct = 'PO-01'") == {
        "trang_thai": decision
    }
    update_status(
        make_ctx("NV-MUA", "nguoi"), table="chung_tu", key={"ma_ct": "PO-01"}, trang_thai="Đã hủy"
    )


def test_a_token_claiming_a_table_beyond_the_ceiling_is_refused_by_rule_5(
    world: Conn, make_ctx: MakeCtx
) -> None:
    """Task 13 F5: require_draft checks the platform ceiling too, whatever a token claims."""
    wide = token(draft=frozenset({"chung_tu", "dong_ct", "ho_so"}))
    with pytest.raises(ToolDenied, match="^platform rule 5:"):
        update_status(
            make_ctx(tok=wide), table="ho_so", key={"case_id": "HS-01"}, trang_thai="Tạm dừng"
        )
    assert one(world, "SELECT trang_thai FROM core.ho_so WHERE case_id = 'HS-01'") == {
        "trang_thai": "Đang xử lý"
    }


# --- carried over from the retired runtime's tests (tests/MIGRATION.md) -------------------


def test_a_zero_item_cap_allows_no_discount(world: Conn, make_ctx: MakeCtx) -> None:
    """A cap set to zero is a cap, not a missing one (was policy/test_store.py)."""
    world.execute("UPDATE core.hang_hoa SET ck_toi_da = 0 WHERE ma_hh = 'HH-01'")
    world.commit()
    with pytest.raises(ToolDenied, match="platform rule 3"):
        create_document(
            make_ctx(), loai_ct="don_mua", ma_ct="PO-33", lines=[_line(chiet_khau="0.01")]
        )
    create_document(make_ctx(), loai_ct="don_mua", ma_ct="PO-33", lines=[_line(chiet_khau=0)])
    assert rows(world, "SELECT ma_ct FROM core.chung_tu WHERE ma_ct = 'PO-33'") == [
        {"ma_ct": "PO-33"}
    ]


def test_an_explicit_null_unit_price_is_accepted(world: Conn, make_ctx: MakeCtx) -> None:
    """Null is "not known", never an invented price (was de/test_ollama_executor.py)."""
    create_document(
        make_ctx(),
        loai_ct="don_mua",
        ma_ct="PO-34",
        lines=[{"ma_hh": "HH-01", "so_luong": 1, "don_gia": None}],
    )
    line = one(world, "SELECT don_gia FROM core.dong_ct WHERE ma_ct = 'PO-34'")
    assert line["don_gia"] is None
    doc = one(world, "SELECT tong_tien FROM core.chung_tu WHERE ma_ct = 'PO-34'")
    assert doc["tong_tien"] is None


def test_a_line_without_an_item_is_accepted(world: Conn, make_ctx: MakeCtx) -> None:
    """Task 15 resume 1: ``ma_hh`` is optional on a line (a document that is not about
    goods, such as an offer letter), so the schema may tell a model to leave it out."""
    create_document(
        make_ctx(),
        loai_ct="thu_moi_nhan_viec",
        ma_ct="TM-01",
        lines=[{"mo_ta": "Tiếp nhận giáo viên mới", "so_luong": 1}],
    )
    line = one(world, "SELECT ma_hh, mo_ta FROM core.dong_ct WHERE ma_ct = 'TM-01'")
    assert line == {"ma_hh": None, "mo_ta": "Tiếp nhận giáo viên mới"}


def test_update_status_refuses_a_key_value_that_is_not_a_scalar(make_ctx: MakeCtx) -> None:
    """Task 15 fix round 2: the key goes through the same filter check as read_records."""
    with pytest.raises(ToolDenied, match=r"chung_tu\.ma_ct") as caught:
        update_status(make_ctx(), table="chung_tu", key={"ma_ct": {"eq": "PO-01"}},
                      trang_thai="Nháp")
    assert "adapt" not in str(caught.value)

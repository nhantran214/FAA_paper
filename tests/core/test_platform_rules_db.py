"""Platform rules 1-6 at the database tier: they hold for raw SQL under ``acting_as``.

Every refusal names its rule: the primary message starts with ``platform rule N:``.
Actor kinds: ``so`` is a digital employee, ``nguoi`` a person, ``ngoai`` an outside
party, ``dieu_phoi`` the engine itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest

from tonomyx.config import Settings
from tonomyx.core.db import ACTOR_KINDS, acting_as
from tonomyx.db.engine import connect

pytestmark = pytest.mark.db

Conn = psycopg.Connection[dict[str, Any]]


@contextmanager
def refused(rule: int | str) -> Iterator[None]:
    """Expect a database refusal whose message starts with ``platform rule N:``.

    ``rule="gate"`` expects the routed-approver refusal, ``platform gate:``.
    """
    prefix = "platform gate:" if rule == "gate" else f"platform rule {rule}:"
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as caught:
        yield
    message = caught.value.diag.message_primary or ""
    assert message.startswith(prefix), message


def scalar(conn: Conn, query: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return next(iter(row.values()))


def insert_event(conn: Conn, *, kind: str = "DRAFTED", actor: str = "spoofed") -> None:
    conn.execute(
        "INSERT INTO core.su_kien (case_id, buoc, kind, ref, actor) VALUES (%s, %s, %s, %s, %s)",
        ("HS-01", "S01", kind, "PO-01", actor),
    )


# --- acting_as ----------------------------------------------------------------


def test_actor_kinds() -> None:
    assert ACTOR_KINDS == ("dieu_phoi", "so", "nguoi", "ngoai")


def test_acting_as_sets_session_values_only_inside_the_block(seeded: Conn) -> None:
    with acting_as(seeded, "DE-1", "so", "v1"):
        assert scalar(seeded, "SELECT current_setting('tonomyx.actor', true)") == "DE-1"
        assert scalar(seeded, "SELECT current_setting('tonomyx.actor_kind', true)") == "so"
        assert scalar(seeded, "SELECT current_setting('tonomyx.governance_version', true)") == "v1"
    assert scalar(seeded, "SELECT current_setting('tonomyx.actor_kind', true)") in (None, "")


def test_acting_as_does_not_leak_into_an_open_outer_transaction(seeded: Conn) -> None:
    seeded.execute("SELECT 1")  # opens an implicit transaction: acting_as nests a savepoint
    with acting_as(seeded, "DE-1", "so", "v1"):
        pass
    assert scalar(seeded, "SELECT current_setting('tonomyx.actor_kind', true)") in (None, "")
    seeded.rollback()


def test_acting_as_rejects_an_unknown_kind(seeded: Conn) -> None:
    with pytest.raises(ValueError, match="robot"), acting_as(seeded, "DE-1", "robot", "v1"):
        pass


def test_acting_as_commits_on_success(seeded: Conn, settings: Settings) -> None:
    with acting_as(seeded, "NV-LAP", "nguoi", "v1"):
        seeded.execute("UPDATE core.chung_tu SET ghi_chu = 'đã sửa' WHERE ma_ct = 'PAY-01'")
    with connect(settings) as other:
        assert scalar(other, "SELECT ghi_chu FROM core.chung_tu WHERE ma_ct = 'PAY-01'") == "đã sửa"


# --- append-only events (rule 6) ---------------------------------------------------


def test_events_are_append_only(seeded: Conn) -> None:
    with acting_as(seeded, "DE-1", "so", "v1"):
        insert_event(seeded)
    for statement in (
        "UPDATE core.su_kien SET mo_ta = 'sửa'",
        "DELETE FROM core.su_kien",
        "TRUNCATE core.su_kien",
    ):
        for kind in ("nguoi", "dieu_phoi"):
            with refused(6), acting_as(seeded, "KTT-01", kind, "v1"):
                seeded.execute(statement)
        with refused(6):  # no actor at all: still append-only
            seeded.execute(statement)
        seeded.rollback()
    assert scalar(seeded, "SELECT count(*) FROM core.su_kien") == 1


def test_event_kind_must_be_known_and_carries_actor(seeded: Conn) -> None:
    with refused(6), acting_as(seeded, "DE-1", "so", "v1"):
        insert_event(seeded, kind="DELETED_EVIDENCE")
    with refused(6):
        insert_event(seeded)  # no tonomyx.actor in this transaction
    seeded.rollback()
    with acting_as(seeded, "DE-1", "so", "v7"):
        insert_event(seeded, actor="KTT-01")
    row = seeded.execute("SELECT actor, governance_version, at FROM core.su_kien").fetchone()
    assert row is not None
    assert row["actor"] == "DE-1"  # the session actor, never the caller's claim
    assert row["governance_version"] == "v7"
    assert row["at"] is not None


# --- rule 1: a digital employee never approves -----------------------------------


def test_digital_employee_cannot_approve_at_db_tier(seeded: Conn) -> None:
    with refused(1), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-02'")
    with refused(1), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute(
            "INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau,"
            " nguoi_duyet, trang_thai) VALUES"
            " ('APR-09', 'HS-01', 'PO-01', 'don_mua', 'DE-1', 'KTT-01', 'Đã duyệt')"
        )
    with refused(1), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.chung_tu SET trang_thai = 'Đã duyệt' WHERE ma_ct = 'PAY-01'")
    assert scalar(seeded, "SELECT trang_thai FROM core.phe_duyet WHERE ma_pd = 'APR-02'") == (
        "Chờ duyệt"
    )


def test_digital_employee_cannot_edit_an_approved_approval(seeded: Conn) -> None:
    with acting_as(seeded, "KTT-01", "nguoi", "v1"):
        seeded.execute("UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-02'")
    with refused(1), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.phe_duyet SET gia_tri = 999999999 WHERE ma_pd = 'APR-02'")


def test_digital_employee_may_request_approval(seeded: Conn) -> None:
    with acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute(
            "INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau,"
            " nguoi_duyet, trang_thai) VALUES"
            " ('APR-03', 'HS-01', 'PO-02', 'don_mua', 'DE-1', 'KTT-01', 'Chờ duyệt')"
        )
        seeded.execute("UPDATE core.chung_tu SET trang_thai = 'Chờ duyệt' WHERE ma_ct = 'PO-02'")


# --- rule 2: the maker is never the checker ----------------------------------------


@pytest.mark.parametrize("maker", ["NV-LAP", "NV-YC"])
def test_maker_is_not_checker_at_db_tier(seeded: Conn, maker: str) -> None:
    """NV-LAP drafted PAY-01; NV-YC requested its approval APR-02."""
    with refused(2), acting_as(seeded, maker, "nguoi", "v1"):
        seeded.execute("UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-02'")
    with acting_as(seeded, "KTT-01", "nguoi", "v1"):
        seeded.execute("UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-02'")


def test_maker_cannot_approve_own_document(seeded: Conn) -> None:
    with refused(2), acting_as(seeded, "NV-LAP", "nguoi", "v1"):
        seeded.execute("UPDATE core.chung_tu SET trang_thai = 'Đã duyệt' WHERE ma_ct = 'PAY-01'")
    with acting_as(seeded, "KTT-01", "nguoi", "v1"):
        seeded.execute("UPDATE core.chung_tu SET trang_thai = 'Đã duyệt' WHERE ma_ct = 'PAY-01'")


def test_maker_identity_cannot_be_rewritten(seeded: Conn) -> None:
    """Otherwise rule 2 falls to two statements: rename the maker, then approve."""
    for statement in (
        "UPDATE core.phe_duyet SET nguoi_yeu_cau = 'NV-KHAC' WHERE ma_pd = 'APR-02'",
        "UPDATE core.phe_duyet SET ma_ct = 'PO-02' WHERE ma_pd = 'APR-02'",
        "UPDATE core.chung_tu SET nguoi_lap = 'NV-KHAC' WHERE ma_ct = 'PAY-01'",
    ):
        with refused(2), acting_as(seeded, "NV-LAP", "nguoi", "v1"):
            seeded.execute(statement)


def test_maker_spoof_in_one_statement_is_refused(seeded: Conn) -> None:
    with refused(2), acting_as(seeded, "NV-YC", "nguoi", "v1"):
        seeded.execute(
            "UPDATE core.phe_duyet SET nguoi_yeu_cau = 'NV-KHAC', trang_thai = 'Đã duyệt'"
            " WHERE ma_pd = 'APR-02'"
        )


# --- rule 3: no unsourced money from a digital employee ----------------------------


def insert_line(
    conn: Conn, ma_dong: str, ma_ct: str, ma_hh: str | None, don_gia: int | None
) -> None:
    conn.execute(
        "INSERT INTO core.dong_ct (ma_dong, ma_ct, ma_hh, so_luong, don_gia)"
        " VALUES (%s, %s, %s, 1, %s)",
        (ma_dong, ma_ct, ma_hh, don_gia),
    )


def test_unsourced_unit_price_refused_at_db_tier(seeded: Conn) -> None:
    with refused(3), acting_as(seeded, "DE-1", "so", "v1"):
        insert_line(seeded, "PO-01-9", "PO-01", "HH-01", 51000)  # catalogue price is 50000
    with refused(3), acting_as(seeded, "DE-1", "so", "v1"):
        insert_line(seeded, "PO-01-9", "PO-01", None, 51000)  # no item, no master value
    with refused(3), acting_as(seeded, "DE-1", "so", "v1"):
        insert_line(seeded, "PO-01-9", "PO-01", "HH-01", 48000)  # quote price; PO-01 has no ct_goc
    with refused(3), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.dong_ct SET don_gia = 1 WHERE ma_dong = 'PO-01-1'")


def test_sourced_or_null_unit_price_accepted(seeded: Conn) -> None:
    with acting_as(seeded, "DE-1", "so", "v1"):
        insert_line(seeded, "PO-01-2", "PO-01", "HH-02", 30000)  # the item's hang_hoa.don_gia
        insert_line(seeded, "PO-02-1", "PO-02", "HH-01", 48000)  # the same item on ct_goc QT-01
        insert_line(seeded, "PO-02-2", "PO-02", "HH-01", 50000)  # catalogue price also a source
        insert_line(seeded, "PO-01-3", "PO-01", None, None)  # null: left for a person
        seeded.execute("UPDATE core.dong_ct SET so_luong = 12 WHERE ma_dong = 'PO-01-1'")


@pytest.mark.parametrize("kind", ["nguoi", "ngoai", "dieu_phoi"])
def test_people_and_outside_parties_may_write_any_amount(seeded: Conn, kind: str) -> None:
    with acting_as(seeded, "NCC-01", kind, "v1"):
        insert_line(seeded, "PO-01-9", "PO-01", "HH-01", 51000)


def test_repointing_the_source_document_rechecks_prices(seeded: Conn) -> None:
    with acting_as(seeded, "DE-1", "so", "v1"):
        insert_line(seeded, "PO-02-1", "PO-02", "HH-01", 48000)
    with refused(3), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.chung_tu SET ct_goc = NULL WHERE ma_ct = 'PO-02'")
    with refused(3), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.dong_ct SET ma_ct = 'PO-01' WHERE ma_dong = 'PO-02-1'")


def test_payroll_line_priced_from_a_master_money_base_is_accepted(seeded: Conn) -> None:
    """Any money_base value of a master row is a source: here nhan_su.luong."""
    with acting_as(seeded, "DE-1", "so", "v1"):
        insert_line(seeded, "PAY-01-1", "PAY-01", None, 12000000)  # NV-LAP's luong
        insert_line(seeded, "PAY-01-2", "PAY-01", None, 100000000)  # ngan_sach.han_muc


def test_value_released_into_nguon_tien_is_a_source_for_its_case_only(seeded: Conn) -> None:
    with acting_as(seeded, "DE-1", "so", "v1"):
        insert_line(seeded, "PAY-01-1", "PAY-01", None, 2500000)  # HS-01's nguon_tien
    with refused(3), acting_as(seeded, "DE-1", "so", "v1"):
        insert_line(seeded, "PAY-01-2", "PAY-01", None, 7777000)  # HS-02's, not this case's
    with refused(3), acting_as(seeded, "DE-1", "so", "v1"):
        insert_line(seeded, "PAY-01-2", "PAY-01", None, 2500001)  # in neither


@pytest.mark.parametrize("kind", ["dieu_phoi", "so", "nguoi", "ngoai"])
def test_only_the_platform_writes_nguon_tien(seeded: Conn, kind: str) -> None:
    for statement in (
        "INSERT INTO core.nguon_tien VALUES ('HS-01', 'gia_moi', 51000)",
        "UPDATE core.nguon_tien SET gia_tri = 51000 WHERE ten = 'phu_cap'",
        "DELETE FROM core.nguon_tien WHERE ten = 'phu_cap'",
        "TRUNCATE core.nguon_tien",
    ):
        with refused(5), acting_as(seeded, "X-1", kind, "v1"):
            seeded.execute(statement)
    seeded.execute("INSERT INTO core.nguon_tien VALUES ('HS-01', 'gia_moi', 51000)")
    seeded.commit()  # no actor kind: the platform releasing a value


# --- the routed approver decides --------------------------------------------------


@pytest.mark.parametrize("decision", ["Đã duyệt", "Từ chối"])
def test_approval_decided_only_by_its_routed_approver(seeded: Conn, decision: str) -> None:
    for kind in ("nguoi", "dieu_phoi", "ngoai"):
        with refused("gate"), acting_as(seeded, "TP-KHAC", kind, "v1"):
            seeded.execute(
                "UPDATE core.phe_duyet SET trang_thai = %s WHERE ma_pd = 'APR-02'", (decision,)
            )
    with refused("gate"), acting_as(seeded, "TP-KHAC", "nguoi", "v1"):
        seeded.execute(
            "INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau,"
            " nguoi_duyet, trang_thai) VALUES"
            " ('APR-09', 'HS-01', 'PAY-01', 'de_nghi_chi', 'NV-YC', 'KTT-01', %s)",
            (decision,),
        )
    with acting_as(seeded, "KTT-01", "nguoi", "v1"):
        seeded.execute(
            "UPDATE core.phe_duyet SET trang_thai = %s WHERE ma_pd = 'APR-02'", (decision,)
        )


def test_routed_approver_cannot_be_rewritten(seeded: Conn) -> None:
    """Otherwise the gate falls to two statements: route it to yourself, then decide."""
    with refused("gate"), acting_as(seeded, "TP-KHAC", "nguoi", "v1"):
        seeded.execute("UPDATE core.phe_duyet SET nguoi_duyet = 'TP-KHAC' WHERE ma_pd = 'APR-02'")
    with refused("gate"), acting_as(seeded, "TP-KHAC", "nguoi", "v1"):
        seeded.execute(
            "UPDATE core.phe_duyet SET nguoi_duyet = 'TP-KHAC', trang_thai = 'Đã duyệt'"
            " WHERE ma_pd = 'APR-02'"
        )


# --- rule 4: leaving the system needs an approved approval --------------------------


def test_payment_needs_approved_chain_at_db_tier(seeded: Conn) -> None:
    for kind in ("so", "nguoi", "ngoai", "dieu_phoi"):
        with refused(4), acting_as(seeded, "DE-1", kind, "v1"):
            seeded.execute("UPDATE core.thanh_toan SET trang_thai = 'Đã chi' WHERE ma_tt = 'TT-01'")
    with refused(4), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute(
            "INSERT INTO core.thanh_toan (ma_tt, ma_ct, so_tien, stk_nhan, trang_thai)"
            " VALUES ('TT-02', 'PAY-01', 500000, '0011', 'Đã chi')"
        )
    # An approved approval of another document does not count.
    with acting_as(seeded, "KTT-01", "nguoi", "v1"):
        seeded.execute("UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-01'")
    with refused(4), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.thanh_toan SET trang_thai = 'Đã chi' WHERE ma_tt = 'TT-01'")
    # Once PAY-01's own approval is approved, its payment may go out.
    with acting_as(seeded, "KTT-01", "nguoi", "v1"):
        seeded.execute("UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-02'")
    with acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute(
            "INSERT INTO core.thanh_toan (ma_tt, ma_ct, so_tien, stk_nhan, trang_thai)"
            " VALUES ('TT-02', 'PAY-01', 500000, '0011', 'Đã chi')"
        )
    # A paid payment cannot be moved onto a document whose approval is not approved.
    with refused(4), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.thanh_toan SET ma_ct = 'PO-02' WHERE ma_tt = 'TT-02'")
    assert scalar(seeded, "SELECT trang_thai FROM core.thanh_toan WHERE ma_tt = 'TT-02'") == (
        "Đã chi"
    )


@pytest.mark.parametrize("other", ["Chờ duyệt", "Từ chối"])
def test_payment_needs_the_whole_chain_approved(seeded: Conn, other: str) -> None:
    """One approved approval is not enough while another of the chain is pending or rejected."""
    with acting_as(seeded, "KTT-01", "nguoi", "v1"):
        seeded.execute("UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-02'")
        seeded.execute(
            "INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau,"
            " nguoi_duyet, trang_thai) VALUES"
            " ('APR-03', 'HS-01', 'PAY-01', 'de_nghi_chi', 'NV-YC', 'GD-01', 'Chờ duyệt')"
        )
    if other == "Từ chối":
        with acting_as(seeded, "GD-01", "nguoi", "v1"):
            seeded.execute(
                "UPDATE core.phe_duyet SET trang_thai = 'Từ chối' WHERE ma_pd = 'APR-03'"
            )
    with refused(4), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.thanh_toan SET trang_thai = 'Đã chi' WHERE ma_tt = 'TT-01'")
    if other == "Chờ duyệt":
        with acting_as(seeded, "GD-01", "nguoi", "v1"):
            seeded.execute(
                "UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-03'"
            )
        with acting_as(seeded, "DE-1", "so", "v1"):
            seeded.execute("UPDATE core.thanh_toan SET trang_thai = 'Đã chi' WHERE ma_tt = 'TT-01'")


# --- rule 5: no master-data writes from a digital employee -------------------------

MASTER_WRITES = {
    "doi_tac": (
        "INSERT INTO core.doi_tac (ma_dt, loai, ten) VALUES ('NCC-99', 'nha_cung_cap', 'X')",
        "UPDATE core.doi_tac SET stk = '6666' WHERE ma_dt = 'NCC-01'",  # the classic attack
        "DELETE FROM core.doi_tac WHERE ma_dt = 'NCC-01'",
    ),
    "hang_hoa": (
        "INSERT INTO core.hang_hoa (ma_hh, ten, don_vi, loai) VALUES ('HH-99', 'X', 'kg', 'hang')",
        "UPDATE core.hang_hoa SET don_gia = 99999 WHERE ma_hh = 'HH-01'",
        "DELETE FROM core.hang_hoa WHERE ma_hh = 'HH-02'",
    ),
    "nhan_su": (
        "INSERT INTO core.nhan_su (ma_nv, ho_ten, phong_ban, chuc_danh, trang_thai)"
        " VALUES ('NV-99', 'X', 'X', 'X', 'Đang làm')",
        "UPDATE core.nhan_su SET luong = 1 WHERE ma_nv = 'NV-LAP'",
        "DELETE FROM core.nhan_su WHERE ma_nv = 'NV-LAP'",
    ),
    "ngan_sach": (
        "INSERT INTO core.ngan_sach (ma_ngs, phong_ban, ky) VALUES ('NGS-99', 'X', 'X')",
        "UPDATE core.ngan_sach SET han_muc = 1000000000000 WHERE ma_ngs = 'NGS-01'",
        "DELETE FROM core.ngan_sach WHERE ma_ngs = 'NGS-01'",
    ),
    "tri_thuc": (
        "INSERT INTO core.tri_thuc VALUES ('KB-99', 'X', 'X')",
        "UPDATE core.tri_thuc SET tieu_de = 'X' WHERE ma_kb = 'KB-01'",
        "DELETE FROM core.tri_thuc WHERE ma_kb = 'KB-01'",
    ),
}


@pytest.mark.parametrize("table", sorted(MASTER_WRITES))
def test_digital_employee_cannot_write_master_tables_at_db_tier(seeded: Conn, table: str) -> None:
    for statement in (*MASTER_WRITES[table], f"TRUNCATE core.{table} CASCADE"):
        with refused(5), acting_as(seeded, "DE-1", "so", "v1"):
            seeded.execute(statement)


def test_people_may_write_master_tables(seeded: Conn) -> None:
    with acting_as(seeded, "NV-LAP", "nguoi", "v1"):
        seeded.execute("UPDATE core.doi_tac SET stk = '0022' WHERE ma_dt = 'NCC-01'")
    assert scalar(seeded, "SELECT stk FROM core.doi_tac WHERE ma_dt = 'NCC-01'") == "0022"


# --- data loaded outside acting_as -------------------------------------------------


def test_rows_loaded_without_an_actor_are_data_not_actions(core_conn: Conn) -> None:
    """A case's starting data (a historical payment, say) loads outside acting_as.

    Rules 1-5 guard actions, and an action always runs under acting_as. Loading a
    case's given state is not an action and records no event, so those triggers
    stand aside; the append-only log and the event's actor (rule 6) still hold.
    """
    c = core_conn
    c.execute("INSERT INTO core.ho_so VALUES ('HS-02', 'Lịch sử', 'Đang xử lý')")
    c.execute(
        "INSERT INTO core.chung_tu (ma_ct, loai_ct, case_id, nguoi_lap, trang_thai, tien_te)"
        " VALUES ('HD-01', 'hoa_don_mua', 'HS-02', 'NV-01', 'Đã thực hiện', 'VND')"
    )
    c.execute(
        "INSERT INTO core.thanh_toan (ma_tt, ma_ct, so_tien, trang_thai)"
        " VALUES ('TT-09', 'HD-01', 100, 'Đã chi')"
    )
    c.commit()


# --- fix round 1: records the chain depends on are kept ------------------------------

KINDS = ("dieu_phoi", "so", "nguoi", "ngoai")


def approve_pay_01(conn: Conn) -> None:
    with acting_as(conn, "KTT-01", "nguoi", "v1"):
        conn.execute("UPDATE core.phe_duyet SET trang_thai = 'Đã duyệt' WHERE ma_pd = 'APR-02'")


@pytest.mark.parametrize("kind", KINDS)
def test_approvals_are_never_deleted(seeded: Conn, kind: str) -> None:
    """Deleting the pending tier-2 approval must not open the way to payment."""
    with refused(4), acting_as(seeded, "KTT-01", kind, "v1"):
        seeded.execute("DELETE FROM core.phe_duyet WHERE ma_pd = 'APR-02'")
    with refused(4), acting_as(seeded, "KTT-01", kind, "v1"):
        seeded.execute("TRUNCATE core.phe_duyet")
    assert scalar(seeded, "SELECT count(*) FROM core.phe_duyet") == 2


@pytest.mark.parametrize("decision", ["Đã duyệt", "Từ chối"])
@pytest.mark.parametrize("kind", ["nguoi", "dieu_phoi", "ngoai"])
def test_an_approval_is_never_inserted_decided(seeded: Conn, kind: str, decision: str) -> None:
    """A decision is always an update of a pending approval, even by the routed approver."""
    with refused("gate"), acting_as(seeded, "KTT-01", kind, "v1"):
        seeded.execute(
            "INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau,"
            " nguoi_duyet, trang_thai) VALUES"
            " ('APR-B2', 'HS-01', 'PAY-01', 'de_nghi_chi', 'NV-KHAC', 'KTT-01', %s)",
            (decision,),
        )


@pytest.mark.parametrize("table", ["chung_tu", "dong_ct", "thanh_toan", "ho_so"])
@pytest.mark.parametrize("kind", KINDS)
def test_operational_records_are_never_truncated(seeded: Conn, kind: str, table: str) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as caught:  # noqa: SIM117
        with acting_as(seeded, "X-1", kind, "v1"):
            seeded.execute(f"TRUNCATE core.{table} CASCADE")
    assert (caught.value.diag.message_primary or "").startswith("platform rule ")
    assert scalar(seeded, "SELECT count(*) FROM core.phe_duyet") == 2


# --- fix round 1: an approved document is frozen ------------------------------------

FROZEN_WRITES = (
    "UPDATE core.chung_tu SET ma_dt = NULL WHERE ma_ct = 'PAY-01'",
    "UPDATE core.chung_tu SET ct_goc = NULL WHERE ma_ct = 'PAY-01'",
    "UPDATE core.chung_tu SET tong_tien = 50000000 WHERE ma_ct = 'PAY-01'",
    "INSERT INTO core.dong_ct (ma_dong, ma_ct, ma_hh, so_luong, don_gia)"
    " VALUES ('PAY-01-9', 'PAY-01', 'HH-01', 1, NULL)",
    "UPDATE core.dong_ct SET so_luong = 1000 WHERE ma_dong = 'PAY-01-0'",
    "DELETE FROM core.dong_ct WHERE ma_dong = 'PAY-01-0'",
    "UPDATE core.dong_ct SET ma_ct = 'PAY-01' WHERE ma_dong = 'PO-01-1'",  # moved in
    "UPDATE core.chung_tu SET thue_vat = 999999 WHERE ma_ct = 'PAY-01'",  # R2k
    "UPDATE core.chung_tu SET case_id = 'HS-02' WHERE ma_ct = 'PAY-01'",  # R2k
)


@pytest.mark.parametrize("kind", KINDS)
def test_approved_document_is_frozen(seeded: Conn, kind: str) -> None:
    with acting_as(seeded, "NV-LAP", "nguoi", "v1"):  # before approval, edits are fine
        seeded.execute("UPDATE core.dong_ct SET so_luong = 10 WHERE ma_dong = 'PAY-01-0'")
    approve_pay_01(seeded)
    for statement in FROZEN_WRITES:
        with refused(4), acting_as(seeded, "KTT-01", kind, "v1"):
            seeded.execute(statement)
    with acting_as(seeded, "KTT-01", "nguoi", "v1"):  # status and notes are not frozen
        seeded.execute(
            "UPDATE core.chung_tu SET trang_thai = 'Đã duyệt', ghi_chu = 'ok'"
            " WHERE ma_ct = 'PAY-01'"
        )


def test_digital_employee_pays_the_documents_partner_and_amount(seeded: Conn) -> None:
    """Probe G: after full approval, retarget the payee account or the amount, then pay."""
    approve_pay_01(seeded)
    with refused(4), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.thanh_toan SET stk_nhan = '6666' WHERE ma_tt = 'TT-01'")
    with refused(4), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.thanh_toan SET so_tien = 50000000 WHERE ma_tt = 'TT-01'")
    with refused(4), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute(
            "INSERT INTO core.thanh_toan (ma_tt, ma_ct, so_tien, stk_nhan, trang_thai)"
            " VALUES ('TT-03', 'PAY-01', 500000, NULL, 'Chờ chi')"
        )
    with acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.thanh_toan SET trang_thai = 'Đã chi' WHERE ma_tt = 'TT-01'")
    row = seeded.execute("SELECT so_tien, stk_nhan FROM core.thanh_toan WHERE ma_tt = 'TT-01'")
    assert row.fetchone() == {"so_tien": 500000, "stk_nhan": "0011"}


# --- fix round 1: event id and time come from the platform -------------------------


def test_event_id_and_time_are_the_platforms(seeded: Conn) -> None:
    with acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute(
            "INSERT INTO core.su_kien (id, case_id, buoc, kind, ref, at)"
            " VALUES (2, 'HS-01', 'S01', 'DRAFTED', 'PO-01', '2001-01-01')"
        )
    with acting_as(seeded, "engine", "dieu_phoi", "v1"):
        seeded.execute(
            "INSERT INTO core.su_kien (case_id, buoc, kind, ref)"
            " VALUES ('HS-01', 'S02', 'SENT', 'x')"
        )
    rows = seeded.execute("SELECT id, at > '2020-01-01' AS fresh FROM core.su_kien ORDER BY id")
    assert rows.fetchall() == [{"id": 1, "fresh": True}, {"id": 2, "fresh": True}]


# --- fix round 1: minors (R2i) ---------------------------------------------------------


def test_source_document_must_belong_to_the_same_case(seeded: Conn) -> None:
    seeded.execute(
        "INSERT INTO core.chung_tu (ma_ct, loai_ct, case_id, ma_dt, nguoi_lap, trang_thai,"
        " tien_te) VALUES ('X-02', 'bao_gia', 'HS-02', 'NCC-01', 'NCC-01', 'Hoàn tất', 'VND')"
    )
    seeded.execute(
        "INSERT INTO core.dong_ct (ma_dong, ma_ct, ma_hh, so_luong, don_gia)"
        " VALUES ('X-02-1', 'X-02', 'HH-01', 1, 99999)"
    )
    seeded.commit()  # given data of another case
    with acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.chung_tu SET ct_goc = 'X-02' WHERE ma_ct = 'PO-02'")
    with refused(3), acting_as(seeded, "DE-1", "so", "v1"):
        insert_line(seeded, "PO-02-1", "PO-02", "HH-01", 99999)


@pytest.mark.parametrize("decision", ["Đã duyệt", "Từ chối"])
def test_undoing_a_decision_needs_the_routed_approver(seeded: Conn, decision: str) -> None:
    with acting_as(seeded, "KTT-01", "nguoi", "v1"):
        seeded.execute(
            "UPDATE core.phe_duyet SET trang_thai = %s WHERE ma_pd = 'APR-02'", (decision,)
        )
    for actor, kind in (("DE-1", "so"), ("TP-KHAC", "nguoi"), ("engine", "dieu_phoi")):
        with refused("gate"), acting_as(seeded, actor, kind, "v1"):
            seeded.execute(
                "UPDATE core.phe_duyet SET trang_thai = 'Chờ duyệt' WHERE ma_pd = 'APR-02'"
            )
    with acting_as(seeded, "KTT-01", "nguoi", "v1"):
        seeded.execute("UPDATE core.phe_duyet SET trang_thai = 'Chờ duyệt' WHERE ma_pd = 'APR-02'")


# --- fix round 2: a document is paid once, and a paid payment is final -----------------


def pay_tt_01(conn: Conn) -> None:
    approve_pay_01(conn)
    with acting_as(conn, "DE-1", "so", "v1"):
        conn.execute("UPDATE core.thanh_toan SET trang_thai = 'Đã chi' WHERE ma_tt = 'TT-01'")


PAID_AGAIN = (
    "INSERT INTO core.thanh_toan (ma_tt, ma_ct, so_tien, stk_nhan, trang_thai)"
    " VALUES ('TT-02', 'PAY-01', 500000, '0011', 'Đã chi')"
)


def test_a_document_is_paid_once(seeded: Conn) -> None:
    """Probe P1: every extra payment matches the account and total, and is still refused."""
    pay_tt_01(seeded)
    with refused(4), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute(PAID_AGAIN)
    with acting_as(seeded, "DE-1", "so", "v1"):  # a second payment may wait, not go out
        seeded.execute(PAID_AGAIN.replace("'Đã chi'", "'Chờ chi'"))
    with refused(4), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute("UPDATE core.thanh_toan SET trang_thai = 'Đã chi' WHERE ma_tt = 'TT-02'")
    assert scalar(seeded, "SELECT count(*) FROM core.thanh_toan WHERE trang_thai = 'Đã chi'") == 1


def test_two_payments_in_one_statement_are_refused(seeded: Conn) -> None:
    approve_pay_01(seeded)
    with refused(4), acting_as(seeded, "DE-1", "so", "v1"):
        seeded.execute(
            "INSERT INTO core.thanh_toan (ma_tt, ma_ct, so_tien, stk_nhan, trang_thai) VALUES"
            " ('TT-02', 'PAY-01', 500000, '0011', 'Đã chi'),"
            " ('TT-03', 'PAY-01', 500000, '0011', 'Đã chi')"
        )


def test_concurrent_payments_of_one_document_serialize(seeded: Conn, settings: Settings) -> None:
    """A payment locks its document first, so a second one cannot pass unseen."""
    approve_pay_01(seeded)
    with connect(settings) as other:
        other.execute("SET lock_timeout = '300ms'")
        other.commit()
        with acting_as(seeded, "DE-1", "so", "v1"):
            seeded.execute("UPDATE core.thanh_toan SET trang_thai = 'Đã chi' WHERE ma_tt = 'TT-01'")
            with (
                pytest.raises(psycopg.errors.LockNotAvailable),
                acting_as(other, "DE-1", "so", "v1"),
            ):
                other.execute(PAID_AGAIN)
        with refused(4), acting_as(other, "DE-1", "so", "v1"):  # after the first commits
            other.execute(PAID_AGAIN)


@pytest.mark.parametrize("kind", KINDS)
def test_a_paid_payment_is_final(seeded: Conn, kind: str) -> None:
    """Probes P2 and P3: the record that money left is never undone or erased."""
    pay_tt_01(seeded)
    for statement in (
        "UPDATE core.thanh_toan SET trang_thai = 'Đã hủy' WHERE ma_tt = 'TT-01'",
        "UPDATE core.thanh_toan SET trang_thai = 'Chờ chi' WHERE ma_tt = 'TT-01'",
        "UPDATE core.thanh_toan SET so_tien = 1 WHERE ma_tt = 'TT-01'",
        "UPDATE core.thanh_toan SET stk_nhan = '6666' WHERE ma_tt = 'TT-01'",
        "DELETE FROM core.thanh_toan WHERE ma_tt = 'TT-01'",
    ):
        with refused(4), acting_as(seeded, "KTT-01", kind, "v1"):
            seeded.execute(statement)
    assert scalar(seeded, "SELECT trang_thai FROM core.thanh_toan WHERE ma_tt = 'TT-01'") == (
        "Đã chi"
    )


# --- fix round 2: master data is written by people only (R2j) --------------------------


@pytest.mark.parametrize("kind", ["ngoai", "dieu_phoi"])
def test_only_people_write_master_tables(seeded: Conn, kind: str) -> None:
    """Probe P5: an outside party rewrites the supplier's account after approval."""
    approve_pay_01(seeded)
    for statements in MASTER_WRITES.values():
        for statement in statements:
            with refused(5), acting_as(seeded, "NCC-01", kind, "v1"):
                seeded.execute(statement)
    assert scalar(seeded, "SELECT stk FROM core.doi_tac WHERE ma_dt = 'NCC-01'") == "0011"

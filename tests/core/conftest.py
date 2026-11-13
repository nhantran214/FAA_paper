"""Fixtures for the core schema: an empty ``core`` per test, and a small seeded world.

Only schema ``core`` is ever touched here; ``public`` is left alone.
Rows the fixtures load are written outside ``acting_as``: they are data, not
actions, so the platform-rule triggers that guard actions leave them alone.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from tonomyx.config import Settings
from tonomyx.core.db import reset_core
from tonomyx.db.engine import connect


@pytest.fixture
def core_conn(settings: Settings) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    """A connection to a freshly reset, empty ``core`` schema."""
    with connect(settings) as connection:
        reset_core(connection)
        yield connection


@pytest.fixture
def seeded(
    core_conn: psycopg.Connection[dict[str, Any]],
) -> psycopg.Connection[dict[str, Any]]:
    """Master rows, one case, and documents for the rule tests.

    - ``PO-01`` (purchase order) drafted by the digital employee ``DE-1``, with
      approval ``APR-01`` requested by ``DE-1`` and routed to ``KTT-01``.
    - ``QT-01`` (supplier quote) priced ``HH-01`` at 48000; ``PO-02`` names it as
      its source document (``ct_goc``).
    - ``PAY-01`` (payment request) drafted by person ``NV-LAP``, with approval
      ``APR-02`` requested by person ``NV-YC`` and routed to ``KTT-01``, and
      payment ``TT-01`` waiting to be paid: 500000 (PAY-01's ``tong_tien``, one
      line ``PAY-01-0``) to ``NCC-01``'s account ``0011``.
    - Money sources: ``NV-LAP`` earns ``luong`` 12000000 (a master money base);
      ``core.nguon_tien`` holds 2500000 for case ``HS-01`` and 7777000 for a
      second case ``HS-02``.
    """
    c = core_conn
    c.execute(
        "INSERT INTO core.ho_so VALUES"
        " ('HS-01', 'Mua vật tư', 'Đang xử lý'), ('HS-02', 'Hồ sơ khác', 'Đang xử lý')"
    )
    c.execute(
        "INSERT INTO core.doi_tac (ma_dt, loai, ten, ngan_hang, stk)"
        " VALUES ('NCC-01', 'nha_cung_cap', 'Công ty A', 'VCB', '0011')"
    )
    c.execute(
        "INSERT INTO core.hang_hoa (ma_hh, ten, don_vi, loai, don_gia) VALUES"
        " ('HH-01', 'Thép', 'kg', 'hang', 50000),"
        " ('HH-02', 'Ống', 'cái', 'hang', 30000)"
    )
    c.execute(
        "INSERT INTO core.nhan_su (ma_nv, ho_ten, phong_ban, chuc_danh, luong, trang_thai)"
        " VALUES ('NV-LAP', 'Nguyễn A', 'Kế toán', 'Kế toán viên', 12000000, 'Đang làm')"
    )
    c.execute(
        "INSERT INTO core.ngan_sach (ma_ngs, phong_ban, ky, han_muc)"
        " VALUES ('NGS-01', 'Kế toán', '2026-Q4', 100000000)"
    )
    c.execute("INSERT INTO core.tri_thuc VALUES ('KB-01', 'Quy trình mua', 'mua_hang')")
    c.execute(
        "INSERT INTO core.chung_tu (ma_ct, loai_ct, case_id, ma_dt, ct_goc, nguoi_lap,"
        " trang_thai, tien_te) VALUES"
        " ('PO-01', 'don_mua', 'HS-01', 'NCC-01', NULL, 'DE-1', 'Chờ duyệt', 'VND'),"
        " ('QT-01', 'bao_gia', 'HS-01', 'NCC-01', NULL, 'NCC-01', 'Hoàn tất', 'VND'),"
        " ('PO-02', 'don_mua', 'HS-01', 'NCC-01', 'QT-01', 'DE-1', 'Nháp', 'VND'),"
        " ('PAY-01', 'de_nghi_chi', 'HS-01', 'NCC-01', 'PO-01', 'NV-LAP', 'Chờ duyệt', 'VND')"
    )
    c.execute(
        "INSERT INTO core.dong_ct (ma_dong, ma_ct, ma_hh, so_luong, don_gia) VALUES"
        " ('QT-01-1', 'QT-01', 'HH-01', 10, 48000),"
        " ('PO-01-1', 'PO-01', 'HH-01', 10, 50000),"
        " ('PAY-01-0', 'PAY-01', 'HH-01', 10, 50000)"
    )
    c.execute("UPDATE core.chung_tu SET tong_tien = 500000 WHERE ma_ct = 'PAY-01'")
    c.execute(
        "INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau,"
        " nguoi_duyet, trang_thai) VALUES"
        " ('APR-01', 'HS-01', 'PO-01', 'don_mua', 'DE-1', 'KTT-01', 'Chờ duyệt'),"
        " ('APR-02', 'HS-01', 'PAY-01', 'de_nghi_chi', 'NV-YC', 'KTT-01', 'Chờ duyệt')"
    )
    c.execute(
        "INSERT INTO core.thanh_toan (ma_tt, ma_ct, so_tien, stk_nhan, trang_thai)"
        " VALUES ('TT-01', 'PAY-01', 500000, '0011', 'Chờ chi')"
    )
    c.execute(
        "INSERT INTO core.nguon_tien (case_id, ten, gia_tri) VALUES"
        " ('HS-01', 'phu_cap', 2500000), ('HS-02', 'khac', 7777000)"
    )
    c.commit()
    return c

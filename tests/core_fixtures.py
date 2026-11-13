"""Plain helpers behind the database fixtures of the new packages' tests.

Each test package's ``conftest.py`` defines its own fixtures with these, so no conftest
imports another's fixtures (Task 13 F4).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg

from tonomyx.config import Settings
from tonomyx.core.db import reset_core
from tonomyx.db.engine import connect

Conn = psycopg.Connection[dict[str, Any]]


@contextmanager
def fresh_core(settings: Settings) -> Iterator[Conn]:
    """A connection to a freshly reset, empty ``core`` schema."""
    with connect(settings) as c:
        reset_core(c)
        yield c


def seed_world(c: Conn) -> None:
    """The small tools world (see ``tests/tools_core/conftest.py``), as given data."""
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
        " ('HH-01', 'Thép', 'kg', 'hang', 50000), ('HH-02', 'Ống', 'cái', 'hang', 30000)"
    )
    c.execute(
        "INSERT INTO core.nhan_su (ma_nv, ho_ten, phong_ban, chuc_danh, trang_thai)"
        " VALUES ('NV-01', 'Trần B', 'Kho', 'Thủ kho', 'Đang làm')"
    )
    c.execute(
        "INSERT INTO core.tri_thuc VALUES"
        " ('KB-01', 'Quy trình mua hàng', 'mua_hang'),"
        " ('KB-02', 'Chính sách nghỉ phép', 'nhan_su')"
    )
    c.execute(
        "INSERT INTO core.chung_tu (ma_ct, loai_ct, case_id, ma_dt, ct_goc, nguoi_lap,"
        " trang_thai, tien_te) VALUES"
        " ('PO-01', 'don_mua', 'HS-01', 'NCC-01', NULL, 'NV-MUA', 'Đã duyệt', 'VND'),"
        " ('GRN-01', 'phieu_nhap', 'HS-01', 'NCC-01', 'PO-01', 'NV-01', 'Hoàn tất', 'VND'),"
        " ('INV-01', 'hoa_don_mua', 'HS-01', 'NCC-01', 'PO-01', 'NCC-01', 'Nháp', 'VND'),"
        " ('X-01', 'don_mua', 'HS-02', 'NCC-01', NULL, 'NV-MUA', 'Nháp', 'VND')"
    )
    c.execute(
        "INSERT INTO core.dong_ct (ma_dong, ma_ct, ma_hh, so_luong, don_gia) VALUES"
        " ('PO-01-1', 'PO-01', 'HH-01', 15, 50000),"
        " ('GRN-01-1', 'GRN-01', 'HH-01', 12, NULL),"
        " ('INV-01-1', 'INV-01', 'HH-01', 15, 50000),"
        " ('X-01-1', 'X-01', 'HH-02', 1, 30000)"
    )
    c.commit()

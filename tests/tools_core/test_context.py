"""What every tool shares: the token check, and one event per write."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from tests.tools_core.conftest import GOVERNANCE_VERSION, Conn, MakeCtx, rows, token
from tonomyx.tools.core import CORE_TOOLS
from tonomyx.tools.core.approvals import decide_approval, request_approval
from tonomyx.tools.core.context import CoreContext
from tonomyx.tools.core.documents import compute_amount, create_document, update_status
from tonomyx.tools.core.events import flag, record_event
from tonomyx.tools.core.records import read_records, search_kb
from tonomyx.tools.core.settlement import notify, pay, reconcile
from tonomyx.tools.errors import ToolDenied
from tonomyx.tools.ports import RecordingMailSender

pytestmark = pytest.mark.db

LINE = {"ma_hh": "HH-01", "so_luong": 1, "don_gia": 50000}


def test_tool_outside_token_is_refused(world: Conn, make_ctx: MakeCtx) -> None:
    reader = token(tools=frozenset({"read_records"}))
    with pytest.raises(ToolDenied, match="create_document"):
        create_document(make_ctx(tok=reader), loai_ct="don_mua", ma_ct="PO-20", lines=[LINE])
    with pytest.raises(ToolDenied, match="search_kb"):
        search_kb(make_ctx(tok=reader), query="mua")
    with pytest.raises(ToolDenied, match="flag"):
        flag(make_ctx(tok=reader), ref="INV-01", reason="x")
    # The tool is granted but the table it writes is not in the token's draft set.
    no_lines = token(draft=frozenset({"chung_tu"}))
    with pytest.raises(ToolDenied, match="dong_ct"):
        create_document(make_ctx(tok=no_lines), loai_ct="don_mua", ma_ct="PO-20", lines=[LINE])
    with pytest.raises(ToolDenied, match="chung_tu"):
        update_status(
            make_ctx(tok=token(draft=frozenset())),
            table="chung_tu",
            key={"ma_ct": "INV-01"},
            trang_thai="Đã thực hiện",
        )
    with pytest.raises(ToolDenied, match="chung_tu"):
        reconcile(
            make_ctx(tok=token(draft=frozenset())), doc="INV-01", ordered="PO-01", received="GRN-01"
        )
    assert rows(world, "SELECT 1 FROM core.su_kien") == []


def test_token_must_match_actor_and_case(make_ctx: MakeCtx) -> None:
    with pytest.raises(ToolDenied):
        read_records(make_ctx(tok=token(actor="DE-2")), table="chung_tu", where={})
    with pytest.raises(ToolDenied):
        read_records(make_ctx(tok=token(case_id="HS-02")), table="chung_tu", where={})


def test_digital_employee_needs_a_token(make_ctx: MakeCtx) -> None:
    with pytest.raises(ToolDenied, match="token"):
        read_records(make_ctx(tok=None), table="chung_tu", where={})


def test_every_write_records_one_event_with_step_id(world: Conn, make_ctx: MakeCtx) -> None:
    mail = RecordingMailSender()
    world.execute("UPDATE core.dong_ct SET so_luong = 15 WHERE ma_dong = 'GRN-01-1'")
    world.commit()
    calls: list[tuple[str, Callable[[CoreContext], object]]] = [
        (
            "S01",
            lambda c: create_document(
                c, loai_ct="de_nghi_chi", ma_ct="PAY-20", ma_dt="NCC-01", lines=[LINE]
            ),
        ),
        (
            "S02",
            lambda c: update_status(
                c, table="chung_tu", key={"ma_ct": "INV-01"}, trang_thai="Đã thực hiện"
            ),
        ),
        (
            "S03",
            lambda c: request_approval(c, ma_pd="PD-20", ma_ct="PAY-20", loai_pd="de_nghi_chi"),
        ),
        (
            "S04",
            lambda c: decide_approval(
                make_ctx("KTT", "nguoi", step_id="S04"), ma_pd="PD-20", decision="Đã duyệt"
            ),
        ),
        ("S05", lambda c: record_event(c, kind="RECEIVED", ref="GRN-01")),
        ("S06", lambda c: flag(c, ref="INV-01", reason="Kiểm tra lại")),
        ("S07", lambda c: reconcile(c, doc="INV-01", ordered="PO-01", received="GRN-01")),
        ("S08", lambda c: compute_amount(c, var="tong", value=Decimal("50000"), basis="PAY-20")),
        ("S09", lambda c: pay(c, ma_tt="TT-20", ma_ct="PAY-20", ma_pd="PD-20")),
        ("S10", lambda c: notify(c, ref="PAY-20", to="NCC-01", ma_pd="PD-20")),
    ]
    for step_id, call in calls:
        call(make_ctx(step_id=step_id, mail=mail))
    events = rows(
        world, "SELECT buoc, actor, governance_version, case_id FROM core.su_kien ORDER BY id"
    )
    assert [e["buoc"] for e in events] == [s for s, _ in calls]
    assert {e["governance_version"] for e in events} == {GOVERNANCE_VERSION}
    assert {e["case_id"] for e in events} == {"HS-01"}
    assert [e["actor"] for e in events] == ["DE-1"] * 3 + ["KTT"] + ["DE-1"] * 6


# --- carried over from the retired runtime's tests (tests/MIGRATION.md) -------------------

# Valid-looking arguments for each tool a task token can carry. decide_approval is left out:
# only a person decides, and a digital employee is refused it by rule 1 before any token check.
TOKEN_TOOL_ARGS: dict[str, dict[str, object]] = {
    "read_records": {"table": "chung_tu", "where": {}},
    "search_kb": {"query": "mua"},
    "create_document": {"loai_ct": "don_mua", "ma_ct": "PO-90", "lines": [LINE]},
    "update_status": {"table": "chung_tu", "key": {"ma_ct": "INV-01"}, "trang_thai": "Đã hủy"},
    "compute_amount": {"var": "tam_ung", "value": Decimal("1"), "basis": "x"},
    "request_approval": {"ma_pd": "PD-90", "ma_ct": "PO-01", "loai_pd": "don_mua"},
    "record_event": {"kind": "RECEIVED", "ref": "GRN-01"},
    "flag": {"ref": "INV-01", "reason": "x"},
    "reconcile": {"doc": "INV-01", "ordered": "PO-01", "received": "GRN-01"},
    "pay": {"ma_tt": "TT-90", "ma_ct": "PO-01", "ma_pd": "PD-90"},
    "notify": {"ref": "PO-01", "to": "ncc@demo.example", "ma_pd": "PD-90"},
}


def test_the_token_tool_list_names_every_tool_but_decide() -> None:
    assert set(TOKEN_TOOL_ARGS) == set(CORE_TOOLS) - {"decide_approval"}


@pytest.mark.parametrize("name", sorted(TOKEN_TOOL_ARGS))
def test_every_tool_checks_its_own_name_against_the_token(
    world: Conn, make_ctx: MakeCtx, name: str
) -> None:
    """Least privilege at every call site (was tools/test_least_privilege.py)."""
    without = token(tools=frozenset(CORE_TOOLS) - {name})
    ctx = make_ctx(tok=without, mail=RecordingMailSender())
    with pytest.raises(ToolDenied, match=f"may not call {name}: not in task token"):
        CORE_TOOLS[name](ctx, **TOKEN_TOOL_ARGS[name])
    assert rows(world, "SELECT 1 FROM core.su_kien") == []

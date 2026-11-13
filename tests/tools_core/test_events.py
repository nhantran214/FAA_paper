"""record_event and flag: the event log written through tools."""

from __future__ import annotations

import pytest

from tests.tools_core.conftest import GOVERNANCE_VERSION, Conn, MakeCtx, one
from tonomyx.tools.core.events import flag, record_event
from tonomyx.tools.errors import ToolDenied

pytestmark = pytest.mark.db


def test_record_event_writes_one_row(world: Conn, make_ctx: MakeCtx) -> None:
    out = record_event(
        make_ctx("NCC-01", "ngoai", step_id="S7"), kind="SHIPPED", ref="INV-01", mo_ta="Đã giao"
    )
    event = one(world, "SELECT * FROM core.su_kien")
    assert out == {"id": event["id"]}
    assert (
        event["kind"],
        event["ref"],
        event["buoc"],
        event["actor"],
        event["governance_version"],
        event["mo_ta"],
        event["case_id"],
    ) == ("SHIPPED", "INV-01", "S7", "NCC-01", GOVERNANCE_VERSION, "Đã giao", "HS-01")


def test_record_event_refuses_kinds_other_tools_own(make_ctx: MakeCtx) -> None:
    for kind in ("APPROVED", "PAID", "SENT", "FLAGGED", "NOT_A_KIND"):
        with pytest.raises(ToolDenied):
            record_event(make_ctx(), kind=kind, ref="INV-01")


def test_flag(world: Conn, make_ctx: MakeCtx) -> None:
    flag(make_ctx(), ref="INV-01", reason="Số lượng nhận thiếu")
    event = one(world, "SELECT kind, ref, mo_ta FROM core.su_kien")
    assert event == {"kind": "FLAGGED", "ref": "INV-01", "mo_ta": "Số lượng nhận thiếu"}
    with pytest.raises(ToolDenied):
        flag(make_ctx(), ref=" ", reason="x")

"""Approvals: request_approval routes through the business gate; decide_approval is for people.

Locks. A request or decision reads a document and its approvals, then writes
them. Both take ``FOR UPDATE`` on the document row first, then on the approval
row, so concurrent calls on one document run one after the other (no write skew
under READ COMMITTED). ``pay`` and ``notify`` take the same order.

With the gate tier off (``ctx.gate_checks`` False; experiments only) the platform-rule
and status checks here are skipped and the context's ``OpenGate`` routes and lets
anyone decide. Type checks, case scoping and the event stay.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from tonomyx.tools.core.context import (
    APPROVED,
    CANCELLED_PAYMENT,
    PENDING,
    REJECTED,
    CoreContext,
    acting,
    exists,
    one_row,
    opened_this_run,
    record,
    require_tool,
    select_rows,
    text,
)
from tonomyx.tools.errors import ToolDenied


def request_approval(ctx: CoreContext, *, ma_pd: str, ma_ct: str, loai_pd: str) -> dict[str, Any]:
    """Open a pending approval of a document of the case, routed by the gate on its ``tong_tien``.

    One open request at a time (ruling R6e): a request is refused while the document
    has an approval opened by this run that is still pending. Approved or rejected
    approvals never block, so a chain of levels (or two of one type) runs in
    sequence; approvals in the given data never block either.
    The document moves to pending (``PENDING``). The approver is never the requester or the
    document's maker (rule 2): such a request is refused here, not left to fail later.
    A paid document (a payment of it that is not cancelled) takes no new request: its
    payment stands on the approvals it had.
    """
    require_tool(ctx, "request_approval")
    ma_pd = text(ma_pd, "ma_pd")
    with acting(ctx) as cur:
        doc = one_row(cur, ctx, "chung_tu", {"ma_ct": ma_ct}, lock=True)
        if exists(cur, "SELECT 1 FROM core.phe_duyet WHERE ma_pd = %s", (ma_pd,)):
            raise ToolDenied(f"approval {ma_pd} already exists")
        chain = select_rows(cur, ctx, "phe_duyet", {"ma_ct": ma_ct}, lock=True)
        open_requests = [
            a["ma_pd"]
            for a in chain
            if a["trang_thai"] == PENDING and opened_this_run(cur, ctx, a["ma_pd"])
        ]
        if ctx.gate_checks and open_requests:
            raise ToolDenied(
                f"platform gate: document {ma_ct} already has a pending approval of this run"
                f" ({', '.join(open_requests)})"
            )
        tong_tien = doc["tong_tien"]
        approver = ctx.gate.approver_for(loai_pd, None if tong_tien is None else Decimal(tong_tien))
        if ctx.gate_checks and approver in (ctx.actor, doc["nguoi_lap"]):
            who = "requests it" if approver == ctx.actor else "made the document"
            raise ToolDenied(
                f"platform rule 2: the maker is never the checker ({loai_pd} on {ma_ct} routes to"
                f" {approver}, who {who})"
            )
        paid = [
            p["ma_tt"]
            for p in select_rows(cur, ctx, "thanh_toan", {"ma_ct": ma_ct})
            if p["trang_thai"] != CANCELLED_PAYMENT
        ]
        if ctx.gate_checks and paid:
            raise ToolDenied(
                f"platform gate: document {ma_ct} is paid ({', '.join(paid)}); it takes no new"
                " approval request"
            )
        cur.execute(
            "INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau,"
            " nguoi_duyet, gia_tri, trang_thai) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (ma_pd, ctx.case_id, ma_ct, loai_pd, ctx.actor, approver, tong_tien, PENDING),
        )
        cur.execute("UPDATE core.chung_tu SET trang_thai = %s WHERE ma_ct = %s", (PENDING, ma_ct))
        record(cur, ctx, "REQUESTED", ma_pd)
    return {"ma_pd": ma_pd, "nguoi_duyet": approver}


def decide_approval(
    ctx: CoreContext,
    *,
    ma_pd: str,
    decision: Literal["Đã duyệt", "Từ chối"],
    ly_do: str = "",
) -> dict[str, Any]:
    """A person decides a pending approval routed to them; the document takes the decision."""
    if ctx.gate_checks and ctx.actor_kind == "so":
        raise ToolDenied(f"platform rule 1: a digital employee never decides an approval ({ma_pd})")
    if ctx.gate_checks and ctx.actor_kind != "nguoi":
        raise ToolDenied(f"decide_approval: only a person decides approvals, not {ctx.actor_kind}")
    require_tool(ctx, "decide_approval")
    if decision not in (APPROVED, REJECTED):
        raise ToolDenied(f"a decision is {APPROVED!r} or {REJECTED!r}, not {decision!r}")
    with acting(ctx) as cur:
        ma_ct = one_row(cur, ctx, "phe_duyet", {"ma_pd": ma_pd})["ma_ct"]
        doc = one_row(cur, ctx, "chung_tu", {"ma_ct": ma_ct}, lock=True)
        approval = one_row(cur, ctx, "phe_duyet", {"ma_pd": ma_pd}, lock=True)
        if ctx.gate_checks and approval["trang_thai"] != PENDING:
            raise ToolDenied(f"approval {ma_pd} is {approval['trang_thai']}, not {PENDING}")
        ctx.gate.may_decide(approval, doc, ctx.actor)
        cur.execute(
            "UPDATE core.phe_duyet SET trang_thai = %s, ly_do = %s WHERE ma_pd = %s",
            (decision, ly_do or None, ma_pd),
        )
        cur.execute("UPDATE core.chung_tu SET trang_thai = %s WHERE ma_ct = %s", (decision, ma_ct))
        record(cur, ctx, "APPROVED" if decision == APPROVED else "REJECTED", ma_pd, ly_do or None)
    return {"trang_thai": decision}

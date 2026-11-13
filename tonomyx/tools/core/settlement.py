"""Settlement: reconcile, pay and notify.

``pay`` and ``notify`` leave the system, so rule 4 guards them: the named approval
is approved, belongs to the paid (or announced) document, and was opened by this
run. Approvals in a case's given data are history and never clear a gate. A
payment also needs the document's whole approval chain approved, goes to the
document partner's account on file (``doi_tac.stk``) for the document's
``tong_tien``, and is made once. When an invoice is named, a reconciliation of
this run must have marked it matched (``MATCHED``).

Locks follow ``approvals``: the document row first, then its approvals, then its
payments.

With the gate tier off (``ctx.gate_checks`` False; experiments only) rule 4 is not
checked here: ``pay`` pays the document's ``tong_tien`` to the account the caller
names (the partner's account on file when it names none), and ``notify`` sends about
any ``ref``. The demo-address check of ``notify``, the unique payment id, case scoping
and the event stay.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from tonomyx.tools.core.context import (
    APPROVED,
    CANCELLED_PAYMENT,
    MATCHED,
    NEEDS_CHECK,
    PAID,
    PENDING,
    REJECTED,
    CoreContext,
    Cursor,
    acting,
    exists,
    one_row,
    opened_this_run,
    record,
    require_draft,
    require_tool,
    select_rows,
    text,
)
from tonomyx.tools.errors import ToolDenied

DEMO_EMAIL_SUFFIX = "@demo.example"


# --- reconcile ------------------------------------------------------------------------


def _doc_ids(value: Any, what: str) -> list[str]:
    ids = [value] if isinstance(value, str) else value
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i for i in ids):
        raise ToolDenied(f"{what} must be a document id or a list of them, got {value!r}")
    if len(set(ids)) != len(ids):
        raise ToolDenied(f"{what} lists a document twice: {ids}")
    return ids


def _item_totals(
    cur: Cursor, ctx: CoreContext, ma_ct: str
) -> dict[str, tuple[Decimal, Decimal | None]]:
    """ma_hh -> (total quantity, unit price or None) over the lines of a document of the case."""
    one_row(cur, ctx, "chung_tu", {"ma_ct": ma_ct})
    quantities: dict[str, Decimal] = {}
    prices: dict[str, set[Decimal]] = {}
    for line in select_rows(cur, ctx, "dong_ct", {"ma_ct": ma_ct}):
        item = line["ma_hh"]
        if not item:
            raise ToolDenied(f"line {line['ma_dong']} of {ma_ct} needs ma_hh to be reconciled")
        quantities[item] = quantities.get(item, Decimal(0)) + Decimal(line["so_luong"])
        seen = prices.setdefault(item, set())
        if line["don_gia"] is not None:
            seen.add(Decimal(line["don_gia"]))
    for item, seen in prices.items():
        if len(seen) > 1:
            raise ToolDenied(f"{ma_ct} has several prices for {item}")
    return {item: (quantities[item], next(iter(prices[item]), None)) for item in quantities}


def reconcile(
    ctx: CoreContext, *, doc: str, ordered: str, received: str | list[str]
) -> dict[str, Any]:
    """Compare ordered, received and invoiced quantities per item; set ``ket_qua`` of ``doc``.

    Matched (``MATCHED``) when, for every item, received equals ordered, the invoice ``doc``
    bills what was received, and its price is within ``tolerances.gia`` (a fraction
    of the ordered price; 0 when the policy has none). ``diff`` holds received minus
    ordered for each item where they differ.
    """
    require_tool(ctx, "reconcile")
    require_draft(ctx, "chung_tu")  # it writes chung_tu.ket_qua
    tolerance = ctx.gate.policy.tolerances.get("gia", Decimal(0))
    with acting(ctx) as cur:
        one_row(cur, ctx, "chung_tu", {"ma_ct": doc}, lock=True)
        invoiced = _item_totals(cur, ctx, doc)
        order = _item_totals(cur, ctx, ordered)
        got: dict[str, Decimal] = {}
        for ma_ct in _doc_ids(received, "received"):
            for item, (quantity, _) in _item_totals(cur, ctx, ma_ct).items():
                got[item] = got.get(item, Decimal(0)) + quantity
        items = sorted(set(invoiced) | set(order) | set(got))
        if not items:
            raise ToolDenied(
                f"nothing to reconcile: {doc}, {ordered} and {received} have no item lines"
            )
        zero: tuple[Decimal, Decimal | None] = (Decimal(0), None)
        diff: dict[str, Decimal] = {}
        result = MATCHED
        for item in items:
            invoiced_qty, invoiced_price = invoiced.get(item, zero)
            ordered_qty, ordered_price = order.get(item, zero)
            received_qty = got.get(item, Decimal(0))
            if received_qty != ordered_qty:
                diff[item] = received_qty - ordered_qty
            if received_qty != ordered_qty or invoiced_qty != received_qty:
                result = NEEDS_CHECK
            if (
                invoiced_price is not None
                and ordered_price is not None
                and abs(invoiced_price - ordered_price) > tolerance * abs(ordered_price)
            ):
                result = NEEDS_CHECK
        cur.execute("UPDATE core.chung_tu SET ket_qua = %s WHERE ma_ct = %s", (result, doc))
        record(cur, ctx, "RECONCILED", doc, result)
    return {"result": result, "diff": diff}


# --- rule 4 -------------------------------------------------------------------------------


def _approved_for(cur: Cursor, ctx: CoreContext, ma_pd: str, ma_ct: str | None) -> dict[str, Any]:
    """The approval ``ma_pd``, locked, if it clears an action on ``ma_ct``; refuse otherwise."""
    approval = one_row(cur, ctx, "phe_duyet", {"ma_pd": ma_pd}, lock=True)
    problems = []
    if not opened_this_run(cur, ctx, ma_pd):
        problems.append(f"approval {ma_pd} was not opened by this run")
    if approval["trang_thai"] != APPROVED:
        problems.append(f"approval {ma_pd} is {approval['trang_thai']}, not {APPROVED}")
    if ma_ct is not None and approval["ma_ct"] != ma_ct:
        problems.append(f"approval {ma_pd} is for {approval['ma_ct']}, not {ma_ct}")
    if problems:
        raise ToolDenied("platform rule 4: " + "; ".join(problems))
    return approval


def pay(
    ctx: CoreContext,
    *,
    ma_tt: str,
    ma_ct: str,
    ma_pd: str,
    stk_nhan: str | None = None,
    invoice: str | None = None,
) -> dict[str, Any]:
    """Pay the request ``ma_ct`` once, as paid, its ``tong_tien`` to its partner's account."""
    require_tool(ctx, "pay")
    require_draft(ctx, "thanh_toan")  # it writes thanh_toan
    ma_tt = text(ma_tt, "ma_tt")
    with acting(ctx) as cur:
        request = one_row(cur, ctx, "chung_tu", {"ma_ct": ma_ct}, lock=True)
        if ctx.gate_checks:
            _approved_for(cur, ctx, ma_pd, ma_ct)
        chain = select_rows(cur, ctx, "phe_duyet", {"ma_ct": ma_ct}, lock=True)
        open_or_refused = sorted(
            a["ma_pd"] for a in chain if a["trang_thai"] in (PENDING, REJECTED)
        )
        if ctx.gate_checks and open_or_refused:
            raise ToolDenied(
                f"platform rule 4: payment {ma_tt} needs the approval chain of {ma_ct} approved"
                f" ({', '.join(open_or_refused)} not approved)"
            )
        payments = select_rows(cur, ctx, "thanh_toan", {"ma_ct": ma_ct}, lock=True)
        live = [p["ma_tt"] for p in payments if p["trang_thai"] != CANCELLED_PAYMENT]
        if ctx.gate_checks and live:
            raise ToolDenied(f"platform rule 4: {ma_ct} is already paid ({', '.join(live)})")
        if exists(cur, "SELECT 1 FROM core.thanh_toan WHERE ma_tt = %s", (ma_tt,)):
            raise ToolDenied(f"payment {ma_tt} already exists")
        if ctx.gate_checks and invoice is not None:
            verdict = one_row(cur, ctx, "chung_tu", {"ma_ct": invoice})["ket_qua"]
            if not exists(
                cur,
                "SELECT 1 FROM core.su_kien"
                " WHERE case_id = %s AND kind = 'RECONCILED' AND ref = %s",
                (ctx.case_id, invoice),
            ):
                raise ToolDenied(
                    f"platform rule 4: invoice {invoice} was not reconciled in this run"
                )
            if verdict != MATCHED:
                raise ToolDenied(f"platform rule 4: invoice {invoice} is marked {verdict}")
        account = None
        if request["ma_dt"] is not None:
            account = one_row(cur, ctx, "doi_tac", {"ma_dt": request["ma_dt"]})["stk"]
        if not ctx.gate_checks and stk_nhan is not None:
            account = stk_nhan  # no payee check: the money goes where the caller says
        if stk_nhan is not None and stk_nhan != account:
            raise ToolDenied(
                f"platform rule 4: stk_nhan {stk_nhan} is not the account on file for"
                f" {request['ma_dt'] or 'the partner of ' + ma_ct} ({account or 'none'})"
            )
        amount = request["tong_tien"]
        if ctx.gate_checks and (amount is None or amount <= 0):
            raise ToolDenied(
                f"platform rule 4: payment {ma_tt} would pay {amount} for {ma_ct};"
                " a payment needs a known, positive amount"
            )
        cur.execute(
            "INSERT INTO core.thanh_toan (ma_tt, ma_ct, so_tien, stk_nhan, trang_thai)"
            " VALUES (%s, %s, %s, %s, %s)",
            (ma_tt, ma_ct, amount, account, PAID),
        )
        record(cur, ctx, "PAID", ma_tt)
    return {"ma_tt": ma_tt}


def notify(ctx: CoreContext, *, ref: str, to: str, ma_pd: str) -> dict[str, Any]:
    """Send a message about ``ref`` through ``ctx.mail``, once its approval is approved.

    ``ref`` is the approval's document or the approval itself; nothing else, so an
    approval of one document never clears news about another. An address (anything
    with ``@``) must be a demo address with exactly one ``@``: the system never
    reaches a real person by accident.
    """
    require_tool(ctx, "notify")
    ref = text(ref, "ref")
    to = text(to, "to")
    if "@" in to and (to.count("@") != 1 or not to.endswith(DEMO_EMAIL_SUFFIX)):
        raise ToolDenied(f"recipient must be a demo address ending in {DEMO_EMAIL_SUFFIX}: {to}")
    if ctx.mail is None:
        raise ToolDenied("notify: no mail sender is configured")
    with acting(ctx) as cur:
        subject = one_row(cur, ctx, "phe_duyet", {"ma_pd": ma_pd})["ma_ct"]
        one_row(
            cur, ctx, "chung_tu", {"ma_ct": subject}, lock=True
        )  # document first, then approval
        approval = (
            _approved_for(cur, ctx, ma_pd, None)
            if ctx.gate_checks
            else one_row(cur, ctx, "phe_duyet", {"ma_pd": ma_pd}, lock=True)
        )
        if ctx.gate_checks and ref not in (approval["ma_ct"], ma_pd):
            raise ToolDenied(
                f"platform rule 4: approval {ma_pd} clears news about {approval['ma_ct']}"
                f" or itself, not {ref}"
            )
        record(cur, ctx, "SENT", ref, f"to: {to}")
        # Sent last, inside the transaction: a failed send rolls the event back.
        ctx.mail.send(
            to=to,
            subject=f"Thông báo {ref}",
            body=f"{ref}: phê duyệt {ma_pd} ({approval['loai_pd']}) {approval['trang_thai']}.",
        )
    return {"sent": True}

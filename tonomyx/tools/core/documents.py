"""Documents: create_document, update_status and compute_amount.

Money (plan ruling P4, rule 3 at the tool tier). ``create_document`` computes the
derived amounts itself and ignores any value a caller passes for them:

    thanh_tien = round(so_luong x don_gia x (1 - chiet_khau)); blank don_gia -> blank
    thue_vat   = sum of round(thanh_tien x thue_suat), rounded per line
    tong_tien  = sum(thanh_tien) + thue_vat; blank when there are no lines or any line is blank

Rounding is to whole VND, ROUND_HALF_UP, in a pinned 28-digit decimal context.

A digital employee's ``don_gia`` is null or has a source (ruling R2b, the same set
as the database tier): a money-base value of a master row (this covers the item's
own ``hang_hoa.don_gia``), the same item's price on a line of the source document
``ct_goc`` of the same case, or a value the platform released to the case in
``core.nguon_tien``. A person or an outside party may write any amount.

With the gate tier off (``ctx.gate_checks`` False; experiments only) the money rule
(rates, discount cap, unsourced prices) and the status rules of ``update_status`` are
skipped. The parsing of lines and amounts (type coercion), the vocabularies, case
scoping and the event stay, and derived money is still computed.
"""

from __future__ import annotations

import decimal
import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from psycopg import sql

from tonomyx.core.schema import PACKAGED_SCHEMA
from tonomyx.tools.core.context import (
    APPROVED,
    CANCELLED_PAYMENT,
    COLUMNS,
    MASTER_TABLES,
    OWN_TOOL_TABLES,
    PENDING,
    PRIMARY_KEY,
    REJECTED,
    SCHEMA,
    CoreContext,
    Cursor,
    acting,
    as_decimal,
    check_columns,
    check_table,
    exists,
    one_row,
    record,
    require_draft,
    require_tool,
    text,
)
from tonomyx.tools.errors import ToolDenied

DRAFTED = "DRAFTED"
# Kinds a document may be recorded under: drafted, or a fact from outside (a receipt,
# an inspection, a shipment, a recorded fact). The other kinds belong to other tools.
DOCUMENT_EVENT_KINDS: frozenset[str] = frozenset(
    {DRAFTED, "RECEIVED", "INSPECTED", "SHIPPED", "RECORDED"}
)

LINE_FIELDS = frozenset(
    {"ma_dong", "ma_hh", "mo_ta", "so_luong", "don_gia", "chiet_khau", "thue_suat"}
)
DERIVED_LINE_FIELDS = frozenset(SCHEMA.derived.get("dong_ct", ()))

# Statuses a document gets only from request_approval and decide_approval.
GATE_STATUSES = frozenset({PENDING, APPROVED, REJECTED})
# A decided document's statuses: a digital employee never moves a document out of one.
DECIDED_STATUSES = frozenset({APPROVED, REJECTED})
# Statuses a digital employee never sets (rule 1 and the end of a process).
NOT_FOR_DIGITAL_EMPLOYEES = frozenset({APPROVED, "Đã chi", "Hoàn tất"})

# The statutory Vietnamese VAT rates (0%, 5%, 8%, 10%). A digital employee's line
# carries one of these or none (ruling R6c, rule 3): a rate is money it may not invent.
VAT_RATES: frozenset[Decimal] = frozenset(
    {Decimal("0"), Decimal("0.05"), Decimal("0.08"), Decimal("0.10")}
)

_MONEY_CONTEXT = decimal.Context(
    prec=28,
    rounding=ROUND_HALF_UP,
    traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow],
)


def _master_money_columns() -> tuple[tuple[str, str], ...]:
    raw = json.loads(PACKAGED_SCHEMA.read_text(encoding="utf-8"))
    return tuple(
        (table, column)
        for table, columns in raw["money_base"].items()
        if table in MASTER_TABLES
        for column in columns
    )


MASTER_MONEY_COLUMNS = _master_money_columns()


def _to_vnd(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


# --- lines and derived money ------------------------------------------------------------


def _line(ma_ct: str, n: int, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ToolDenied(f"line {n} of {ma_ct} must be an object, got {raw!r}")
    unknown = sorted(set(raw) - LINE_FIELDS - DERIVED_LINE_FIELDS)
    if unknown:
        raise ToolDenied(f"line {n} of {ma_ct} has unknown field(s) {unknown}")
    so_luong = as_decimal(raw.get("so_luong"), f"so_luong of line {n}")
    if so_luong is None:
        raise ToolDenied(f"line {n} of {ma_ct} needs so_luong")
    don_gia = as_decimal(raw.get("don_gia"), f"don_gia of line {n}")
    if don_gia is not None and (don_gia != don_gia.to_integral_value() or don_gia < 0):
        raise ToolDenied(f"don_gia of line {n} must be a whole, non-negative VND amount: {don_gia}")
    return {
        "ma_dong": raw.get("ma_dong") or f"{ma_ct}-{n}",
        "ma_hh": raw.get("ma_hh") or None,
        "mo_ta": raw.get("mo_ta"),
        "so_luong": so_luong,
        "don_gia": None if don_gia is None else int(don_gia),
        "chiet_khau": as_decimal(raw.get("chiet_khau"), f"chiet_khau of line {n}"),
        "thue_suat": as_decimal(raw.get("thue_suat"), f"thue_suat of line {n}"),
    }


def derive_money(
    lines: list[dict[str, Any]], *, refuse_negative: bool = True
) -> tuple[list[int | None], int | None, int | None]:
    """Line amounts, then the document's thue_vat and tong_tien (None stays unknown).

    A line that comes out negative is refused unless ``refuse_negative`` is False (the
    gate tier off: the money rule is not checked, the amounts are still computed)."""
    with decimal.localcontext(_MONEY_CONTEXT):
        amounts: list[int | None] = []
        vat = 0
        for line in lines:
            if line["don_gia"] is None:
                amounts.append(None)
                continue
            discount = line["chiet_khau"] or Decimal(0)
            amount = _to_vnd(line["so_luong"] * Decimal(line["don_gia"]) * (Decimal(1) - discount))
            if refuse_negative and amount < 0:
                raise ToolDenied(f"line {line['ma_dong']} comes out negative ({amount})")
            amounts.append(amount)
            vat += _to_vnd(Decimal(amount) * (line["thue_suat"] or Decimal(0)))
        if not lines or any(a is None for a in amounts):
            return amounts, None, None
        return amounts, vat, sum(a for a in amounts if a is not None) + vat


def unit_price_is_sourced(
    cur: Cursor, case_id: str, ct_goc: str | None, ma_hh: str | None, don_gia: int | None
) -> bool:
    """Rule 3's source set, as the database tier has it (ruling R2b)."""
    if don_gia is None:
        return True
    for table, column in MASTER_MONEY_COLUMNS:
        query = sql.SQL("SELECT 1 FROM core.{} WHERE {} = %s").format(
            sql.Identifier(table), sql.Identifier(column)
        )
        if exists(cur, query.as_string(cur), (don_gia,)):
            return True
    if exists(
        cur, "SELECT 1 FROM core.nguon_tien WHERE case_id = %s AND gia_tri = %s", (case_id, don_gia)
    ):
        return True
    return (
        ma_hh is not None
        and ct_goc is not None
        and exists(
            cur,
            "SELECT 1 FROM core.dong_ct s JOIN core.chung_tu src ON src.ma_ct = s.ma_ct"
            " WHERE s.ma_ct = %s AND src.case_id = %s AND s.ma_hh = %s AND s.don_gia = %s",
            (ct_goc, case_id, ma_hh, don_gia),
        )
    )


def _check_rates(line: dict[str, Any]) -> None:
    """A digital employee's discount is a fraction in [0, 1] and its VAT rate a statutory one."""
    discount, vat = line["chiet_khau"], line["thue_suat"]
    if discount is not None and not Decimal(0) <= discount <= Decimal(1):
        raise ToolDenied(
            f"platform rule 3: discount {discount} on {line['ma_dong']} is not between 0 and 1"
        )
    if vat is not None and vat not in VAT_RATES:
        raise ToolDenied(
            f"platform rule 3: VAT rate {vat} on {line['ma_dong']} is not a statutory rate"
            f" ({', '.join(str(r) for r in sorted(VAT_RATES))})"
        )


def _check_discount_cap(cur: Cursor, line: dict[str, Any]) -> None:
    """A digital employee's discount stays within the item's cap ``hang_hoa.ck_toi_da``, if set."""
    if line["chiet_khau"] is None or line["ma_hh"] is None:
        return
    item = cur.execute(
        "SELECT ck_toi_da FROM core.hang_hoa WHERE ma_hh = %s", (line["ma_hh"],)
    ).fetchone()
    cap = None if item is None else item["ck_toi_da"]
    if cap is not None and line["chiet_khau"] > cap:
        raise ToolDenied(
            f"platform rule 3: discount {line['chiet_khau']} on {line['ma_dong']} exceeds the"
            f" cap {cap} of {line['ma_hh']}"
        )


# --- tools --------------------------------------------------------------------------------


def create_document(
    ctx: CoreContext,
    *,
    loai_ct: str,
    ma_ct: str,
    ma_dt: str | None = None,
    ct_goc: str | None = None,
    lines: list[dict[str, Any]],
    ghi_chu: str | None = None,
    event_kind: str = DRAFTED,
    tong_tien: Any = None,
    thue_vat: Any = None,
) -> dict[str, Any]:
    """Draft a document of the case, in draft status, with its lines and derived money.

    ``event_kind`` defaults to ``DRAFTED``; a fact from outside (``record_external_fact``)
    records its document under its own kind, such as ``RECEIVED``. ``tong_tien`` and
    ``thue_vat`` are accepted and ignored: derived money is always computed (P4).
    """
    del tong_tien, thue_vat
    require_tool(ctx, "create_document")
    require_draft(ctx, "chung_tu")
    if lines:
        require_draft(ctx, "dong_ct")
    ma_ct = text(ma_ct, "ma_ct")
    if loai_ct not in SCHEMA.vocab["chung_tu.loai_ct"]:
        raise ToolDenied(f"unknown document type loai_ct {loai_ct!r}")
    if event_kind not in DOCUMENT_EVENT_KINDS:
        raise ToolDenied(
            f"a document is recorded as one of {sorted(DOCUMENT_EVENT_KINDS)}, not {event_kind!r}"
        )
    if not isinstance(lines, list):
        raise ToolDenied(f"lines of {ma_ct} must be a list")
    parsed = [_line(ma_ct, n, raw) for n, raw in enumerate(lines, start=1)]
    if ctx.gate_checks and ctx.actor_kind == "so":
        for line in parsed:
            _check_rates(line)
    amounts, thue_vat, tong_tien = derive_money(parsed, refuse_negative=ctx.gate_checks)

    with acting(ctx) as cur:
        if exists(cur, "SELECT 1 FROM core.chung_tu WHERE ma_ct = %s", (ma_ct,)):
            raise ToolDenied(f"document {ma_ct} already exists")
        if ma_dt is not None and not exists(
            cur, "SELECT 1 FROM core.doi_tac WHERE ma_dt = %s", (ma_dt,)
        ):
            raise ToolDenied(f"unknown partner ma_dt {ma_dt!r}")
        if ct_goc is not None:
            one_row(cur, ctx, "chung_tu", {"ma_ct": ct_goc})  # the source belongs to this case
        for line in parsed:
            if line["ma_hh"] is not None and not exists(
                cur, "SELECT 1 FROM core.hang_hoa WHERE ma_hh = %s", (line["ma_hh"],)
            ):
                raise ToolDenied(f"unknown item ma_hh {line['ma_hh']!r} on line {line['ma_dong']}")
            if ctx.gate_checks and ctx.actor_kind == "so":
                _check_discount_cap(cur, line)
            if ctx.gate_checks and ctx.actor_kind == "so" and not unit_price_is_sourced(
                cur, ctx.case_id, ct_goc, line["ma_hh"], line["don_gia"]
            ):
                raise ToolDenied(
                    f"platform rule 3: unit price {line['don_gia']} on {line['ma_dong']}"
                    " has no source"
                )
        cur.execute(
            "INSERT INTO core.chung_tu (ma_ct, loai_ct, case_id, ma_dt, ct_goc, nguoi_lap,"
            " trang_thai, tien_te, thue_vat, tong_tien, ghi_chu)"
            " VALUES (%s, %s, %s, %s, %s, %s, 'Nháp', 'VND', %s, %s, %s)",
            (ma_ct, loai_ct, ctx.case_id, ma_dt, ct_goc, ctx.actor, thue_vat, tong_tien, ghi_chu),
        )
        for line, amount in zip(parsed, amounts, strict=True):
            cur.execute(
                "INSERT INTO core.dong_ct (ma_dong, ma_ct, ma_hh, mo_ta, so_luong, don_gia,"
                " chiet_khau, thue_suat, thanh_tien) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    line["ma_dong"],
                    ma_ct,
                    line["ma_hh"],
                    line["mo_ta"],
                    line["so_luong"],
                    line["don_gia"],
                    line["chiet_khau"],
                    line["thue_suat"],
                    amount,
                ),
            )
        record(cur, ctx, event_kind, ma_ct)
    return {"ma_ct": ma_ct}


def update_status(
    ctx: CoreContext, *, table: str, key: dict[str, Any], trang_thai: str
) -> dict[str, Any]:
    """Set ``trang_thai`` of one row of the case.

    Never of an approval, a payment or the event log (their own tools change them),
    and never a document into a gate status. A digital employee never sets
    approved, paid or completed (``NOT_FOR_DIGITAL_EMPLOYEES``), and never moves a
    document out of a decision (approved or rejected) or once it is paid (a payment
    of it that is not cancelled): the decision and the payment stand.
    """
    require_tool(ctx, "update_status")
    check_table(table)
    if table == "su_kien":
        raise ToolDenied("platform rule 6: su_kien is append-only; update_status never changes it")
    if ctx.gate_checks and table in OWN_TOOL_TABLES:
        raise ToolDenied(f"update_status never changes {table}: its own tool does")
    if "trang_thai" not in COLUMNS[table]:
        raise ToolDenied(f"{table} has no trang_thai")
    require_draft(ctx, table)
    if ctx.gate_checks and ctx.actor_kind == "so" and trang_thai in NOT_FOR_DIGITAL_EMPLOYEES:
        rule = (
            "platform rule 1: a digital employee never approves"
            if trang_thai == APPROVED
            else ("update_status: a digital employee may not set this status")
        )
        raise ToolDenied(f"{rule} ({table} {key} {trang_thai!r})")
    if ctx.gate_checks and table == "chung_tu" and trang_thai in GATE_STATUSES:
        raise ToolDenied(
            f"update_status cannot set a document to {trang_thai!r}: only request_approval"
            " and decide_approval do"
        )
    allowed = SCHEMA.vocab.get(f"{table}.trang_thai")
    if allowed is not None and trang_thai not in allowed:
        raise ToolDenied(f"{trang_thai!r} is not a status of {table}")
    if not isinstance(key, dict) or not key:
        raise ToolDenied("update_status needs a key")
    check_columns(table, key)

    pk = PRIMARY_KEY[table]
    with acting(ctx) as cur:
        target = one_row(cur, ctx, table, key, lock=True)
        if ctx.gate_checks and ctx.actor_kind == "so" and table == "chung_tu":
            _refuse_undoing(cur, ctx, target)
        row = cur.execute(
            sql.SQL("UPDATE core.{} SET trang_thai = %s WHERE {} = %s RETURNING *").format(
                sql.Identifier(table), sql.Identifier(pk)
            ),
            (trang_thai, target[pk]),
        ).fetchone()
        record(cur, ctx, "STATUS_CHANGED", str(target[pk]))
    return {"row": row}


def _refuse_undoing(cur: Cursor, ctx: CoreContext, document: dict[str, Any]) -> None:
    """A digital employee never moves a decided or paid document to another status."""
    ma_ct, status = document["ma_ct"], document["trang_thai"]
    if status in DECIDED_STATUSES:
        raise ToolDenied(
            f"update_status: a digital employee never moves {ma_ct} out of its decision"
            f" {status!r}"
        )
    if exists(
        cur,
        "SELECT 1 FROM core.thanh_toan WHERE ma_ct = %s AND trang_thai <> %s",
        (ma_ct, CANCELLED_PAYMENT),
    ):
        raise ToolDenied(f"update_status: a digital employee never moves {ma_ct}: it is paid")


def compute_amount(ctx: CoreContext, *, var: str, value: Decimal, basis: str) -> dict[str, Any]:
    """Record a computed variable as an event (``RECORDED``, ref the variable). No table write."""
    require_tool(ctx, "compute_amount")
    var = text(var, "var")
    number = as_decimal(value, var)
    shown = "không xác định" if number is None else format(number, "f")
    with acting(ctx) as cur:
        record(cur, ctx, "RECORDED", var, f"{var} = {shown} (cơ sở: {basis})")
    return {"var": var}

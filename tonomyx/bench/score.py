"""Score a run's final ``core`` state against a case's answer, structurally (spec C11).

The engine's actors choose their own ids, so a run is never scored id for id. Its
documents, approvals and payments are first mapped to the case's (``id_map``, run id
to case id), then the case's facts are checked on the run's tables read in the case's
ids.

Mapping. A row the run made is one the case's given data (``AnswerSide.given``, the
operational tables of ``data/``) does not hold; the case's own run made the rows of its
final state that the given data does not hold.

1. Given data (history present before the run) keeps its ids: a given row maps to
   itself.
2. The rows the run made map to the rows the case's run made, greedily in creation
   order (the first creating event of the run naming them: a ``DOCUMENT_EVENT_KINDS``
   event, ``REQUESTED``, ``PAID``; rows no such event names last), never by id:
   - documents by (``loai_ct``, mapped ``ct_goc``, ``ma_dt``, the maker's actor kind,
     ``tong_tien``), the environment's key plus the amount; then, for the documents
     still unmapped, by the same key without ``tong_tien``, so a wrong amount fails
     its own fact and nothing else;
   - approvals by (``loai_pd``, mapped ``ma_ct``), with the environment's
     ``map_approvals``;
   - payments by mapped ``ma_ct``.

Invariants. Each fact of ``invariants.json`` is checked on the run's tables with
every mapped id read as its case id (an unmapped run id as an id no case row has),
which is the same as substituting the mapped ids into its ``where``. The assertion
kinds are the bench's (the invariant kinds of the scenario packs): ``count``,
``values_of``/``equals_set``, ``all``, ``sum`` and a row assertion, with the cell
conditions ``eq``, ``ne``, ``in``, ``contains``, ``is_blank``, ``gt``, ``ge``, ``lt``,
``le``. Cells are compared as CSV text, numbers in canonical form. A malformed
invariant fails with the reason; it never raises.

Outcome. Compared with ``outcome.json``: the approvals the run made as a multiset
of (``loai_pd``, ``nguoi_duyet``, ``trang_thai``); the run's ``FLAGGED`` events as a
multiset of mapped ``ref``; ``stop.type``, and ``stop.for`` when the case waits (the
person waited on: the run's ``stop.approver`` when the engine gives one, else its
``stop.for``); and
the payments of ``thanh_toan`` as a multiset of (mapped ``ma_ct``, ``so_tien``,
``stk_nhan``, ``trang_thai``). ``steps_run`` and free text are not compared. Last
(ruling R9b), every row the run made in ``chung_tu``, ``phe_duyet`` or ``thanh_toan``
that maps to no case row is a mismatch of its own ("document unexpected: ...",
"approval unexpected: ...", "payment unexpected: ..."), so an extra document, approval
or payment never scores perfect even when every fact of the case holds.
"""

from __future__ import annotations

import operator
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from tonomyx.bench.cases import AnswerSide
from tonomyx.bench.environment import (
    FLAGGED,
    REQUESTED,
    blank,
    creation_order,
    doc_key,
    map_approvals,
)
from tonomyx.core.schema import CORE_SCHEMA_NAME, load_core_schema
from tonomyx.engine.run import RunResult
from tonomyx.tools.core.documents import DOCUMENT_EVENT_KINDS

Row = dict[str, str]
Tables = dict[str, list[Row]]

PAID = "PAID"
SENT = "SENT"
UNMAPPED = "unmapped"  # (UNMAPPED, run id): a run source that maps to no case id
WAIT = "wait"

# The rows mapped, by kind: table, id column, the event kinds that create one.
KINDS: dict[str, tuple[str, str, frozenset[str]]] = {
    "doc": ("chung_tu", "ma_ct", DOCUMENT_EVENT_KINDS),
    "approval": ("phe_duyet", "ma_pd", frozenset({REQUESTED})),
    "payment": ("thanh_toan", "ma_tt", frozenset({PAID})),
}
# What an unexpected row of each kind is named by (ruling R9b), in the case's ids.
UNEXPECTED: dict[str, tuple[str, tuple[str, ...]]] = {
    "doc": ("document", ("loai_ct", "ma_dt", "ct_goc")),
    "approval": ("approval", ("loai_pd", "ma_ct")),
    "payment": ("payment", ("ma_ct",)),
}

# The id columns read in the case's ids, by the kind of row they name.
ID_COLUMNS: dict[str, dict[str, str]] = {
    "chung_tu": {"ma_ct": "doc", "ct_goc": "doc"},
    "dong_ct": {"ma_ct": "doc"},
    "phe_duyet": {"ma_pd": "approval", "ma_ct": "doc"},
    "thanh_toan": {"ma_tt": "payment", "ma_ct": "doc"},
    "su_kien": {"ref": "any"},
}


@dataclass(frozen=True)
class ScoreReport:
    invariants_passed: int
    invariants_total: int
    outcome_mismatches: list[str]
    id_map: dict[str, str]  # run id -> case id: documents, approvals, payments
    perfect: bool
    failed_invariants: dict[str, str] = field(default_factory=dict)  # id -> detail
    # Rows the run made that map to no case row (the "... unexpected" mismatches of ruling
    # R9b), counted by kind: "doc", "approval", "payment" (final review I3).
    unmapped_rows: dict[str, int] = field(default_factory=dict)


def score(
    conn: psycopg.Connection[Any], case_id: str, answer: AnswerSide, result: RunResult
) -> ScoreReport:
    """Score the run of ``case_id`` now in ``core`` against the case's answer."""
    if answer.case_id != case_id or result.case_id != case_id:
        raise ValueError(
            f"scoring {case_id} with the answer of {answer.case_id} and the run of {result.case_id}"
        )
    run = _read_core(conn)
    run_events = [e for e in run.get("su_kien", []) if e.get("case_id") == case_id]
    expected = answer.final_state
    maps, made, loose = _map_rows(run, run_events, expected, answer)
    id_map = {**maps["doc"], **maps["approval"], **maps["payment"]}
    seen = _read_in_case_ids(run, maps)
    run_events_seen = [e for e in seen.get("su_kien", []) if e.get("case_id") == case_id]

    failed: dict[str, str] = {}
    invariants = _invariants(answer.invariants)
    for n, inv in enumerate(invariants):
        ok, detail = check_invariant(inv, seen)
        if not ok:
            name = inv.get("id") if isinstance(inv, dict) else None
            failed[str(name if name is not None else f"#{n}")] = detail

    # Every approval the run made counts, not only those a REQUESTED event names: an
    # approval row written without its request (say, already approved) is still the
    # run's, and the case's outcome lists every approval its run opened.
    made_approvals = set(made["approval"])
    mismatches = _outcome_mismatches(
        answer.outcome,
        result,
        run_approvals=[a for a in run.get("phe_duyet", []) if a["ma_pd"] in made_approvals],
        run_flags=[e for e in seen.get("su_kien", []) if _is_flag(e, case_id)],
        run_payments=seen.get("thanh_toan", []),
        expected_payments=expected.get("thanh_toan", []),
    )
    mismatches += _unexpected_rows(seen, made, maps)
    mismatches += _wrong_amounts(run, expected, maps["doc"], loose)
    mismatches += _wrong_lines(seen, expected, maps["doc"], made["doc"])
    mismatches += _compare(
        "notice",
        ("ref",),
        [e for e in answer.events if e.get("kind") == SENT],
        [e for e in run_events_seen if e.get("kind") == SENT],
    )
    passed = len(invariants) - len(failed)
    unmapped = {kind: sum(1 for i in made[kind] if i not in maps[kind]) for kind in UNEXPECTED}
    return ScoreReport(
        invariants_passed=passed,
        invariants_total=len(invariants),
        outcome_mismatches=mismatches,
        id_map=id_map,
        perfect=not failed and not mismatches,
        failed_invariants=failed,
        unmapped_rows=unmapped,
    )


# --- reading the run ------------------------------------------------------------------------


def _read_core(conn: psycopg.Connection[Any]) -> Tables:
    """Every table of ``core`` as CSV text, rows in primary-key order."""
    schema = load_core_schema()
    out: Tables = {}
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        for table, columns in schema.tables.items():
            keys = [c.name for c in columns if c.pk]
            query = sql.SQL("SELECT * FROM {}.{}").format(
                sql.Identifier(CORE_SCHEMA_NAME), sql.Identifier(table)
            )
            if keys:
                query += sql.SQL(" ORDER BY {}").format(
                    sql.SQL(", ").join(map(sql.Identifier, keys))
                )
            cur.execute(query)
            out[table] = [{k: cell_text(v) for k, v in row.items()} for row in cur.fetchall()]
    return out


def cell_text(value: Any) -> str:
    """A database value as the bench's CSV writes it: blank for null, numbers canonical
    (``15`` not ``15.0``, ``0.1`` not ``0.10``)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        if value.is_finite() and value == value.to_integral_value():
            return str(int(value))
        return format(value.normalize(), "f")
    return str(value).strip()


# --- mapping --------------------------------------------------------------------------------


def _named(events: Iterable[Row], kinds: set[str] | frozenset[str]) -> set[str]:
    return {str(e.get("ref")) for e in events if e.get("kind") in kinds}


def _map_documents(
    run_docs: list[Row], expected_docs: list[Row], kinds: dict[str, str], given: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    """Run id -> case id for documents; and the run ids mapped only without ``tong_tien``
    (the second pass: documents of the right role with the wrong amount)."""
    out = dict(given)
    claimed = set(out.values())
    loose: list[str] = []

    def key(doc: Row, source: Any, with_amount: bool) -> tuple[Any, ...]:
        role = doc_key(doc, source, kinds)
        return (*role, blank(doc.get("tong_tien"))) if with_amount else role

    for with_amount in (True, False):
        for doc in run_docs:
            if doc["ma_ct"] in out:
                continue
            source = blank(doc.get("ct_goc"))
            mapped = None if source is None else out.get(source, (UNMAPPED, source))
            want = key(doc, mapped, with_amount)
            pick = next(
                (
                    c
                    for c in expected_docs
                    if c["ma_ct"] not in claimed
                    and key(c, blank(c.get("ct_goc")), with_amount) == want
                ),
                None,
            )
            if pick is not None:
                out[doc["ma_ct"]] = pick["ma_ct"]
                claimed.add(pick["ma_ct"])
                if not with_amount:
                    loose.append(doc["ma_ct"])
    return out, loose


def _map_payments(
    run_payments: list[Row],
    expected_payments: list[Row],
    doc_map: dict[str, str],
    given: dict[str, str],
) -> dict[str, str]:
    out = dict(given)
    claimed = set(out.values())
    for payment in run_payments:
        if payment["ma_tt"] in out:
            continue
        doc = doc_map.get(payment["ma_ct"])
        pick = next(
            (
                c
                for c in expected_payments
                if c["ma_tt"] not in claimed and doc is not None and c.get("ma_ct") == doc
            ),
            None,
        )
        if pick is not None:
            out[payment["ma_tt"]] = pick["ma_tt"]
            claimed.add(pick["ma_tt"])
    return out


def _map_rows(
    run: Tables, run_events: list[Row], expected: Tables, answer: AnswerSide
) -> tuple[dict[str, dict[str, str]], dict[str, list[str]], list[str]]:
    """Run id -> case id for documents (``doc``), approvals and payments; the ids of the
    rows the run made, by kind, in creation order; and the run documents mapped without
    their amount."""
    case_events = answer.events
    maps: dict[str, dict[str, str]] = {}
    made: dict[str, list[str]] = {}
    pairs: dict[str, tuple[list[Row], list[Row]]] = {}
    for kind, (table, key, kinds) in KINDS.items():
        given = {r[key] for r in answer.given.get(table, [])}
        run_rows = creation_order(run.get(table, []), run_events, key, kinds)
        case_rows = creation_order(expected.get(table, []), case_events, key, kinds)
        case_ids = {r[key] for r in case_rows}
        # Given data keeps its ids.
        maps[kind] = {r[key]: r[key] for r in run_rows if r[key] in given and r[key] in case_ids}
        made[kind] = [r[key] for r in run_rows if r[key] not in given]
        pairs[kind] = (
            [r for r in run_rows if r[key] not in given],
            [r for r in case_rows if r[key] not in given],
        )

    maps["doc"], loose = _map_documents(*pairs["doc"], answer.role_kinds, maps["doc"])
    run_approvals, case_approvals = pairs["approval"]
    maps["approval"].update(
        map_approvals(
            [a["ma_pd"] for a in run_approvals],
            {a["ma_pd"]: a for a in run_approvals},
            case_approvals,
            maps["doc"],
        )
    )
    maps["payment"] = _map_payments(*pairs["payment"], maps["doc"], maps["payment"])
    return maps, made, loose


def _unmapped(run_id: str) -> str:
    """How an unmapped run id reads in the case's ids: as an id no case row has."""
    return f"{run_id} (unmapped run id)"


def _read_in_case_ids(run: Tables, maps: dict[str, dict[str, str]]) -> Tables:
    """The run's tables with each mapped id as its case id, an unmapped run id as an id
    no case row has, and every other value as it is."""
    ids = {
        "doc": {r["ma_ct"] for r in run.get("chung_tu", [])},
        "approval": {r["ma_pd"] for r in run.get("phe_duyet", [])},
        "payment": {r["ma_tt"] for r in run.get("thanh_toan", [])},
    }
    ids["any"] = ids["doc"] | ids["approval"] | ids["payment"]
    every = {**maps["doc"], **maps["approval"], **maps["payment"]}
    lookup = {**maps, "any": every}

    def read(value: str, kind: str) -> str:
        if value in lookup[kind]:
            return lookup[kind][value]
        if value in ids[kind]:
            return _unmapped(value)
        return value

    out: Tables = {}
    for table, rows in run.items():
        columns = ID_COLUMNS.get(table, {})
        out[table] = [
            {k: read(v, columns[k]) if k in columns and v else v for k, v in row.items()}
            for row in rows
        ]
    return out


# --- invariants -----------------------------------------------------------------------------


class InvariantError(ValueError):
    """A malformed invariant: it fails with this reason."""


BOUNDS: dict[str, Callable[[Decimal, Decimal], bool]] = {
    "gt": operator.gt,
    "ge": operator.ge,
    "lt": operator.lt,
    "le": operator.le,
}
COMPARISONS: dict[str, Callable[[Decimal, Decimal], bool]] = {
    **BOUNDS,
    "eq": operator.eq,
    "ne": operator.ne,
}
CELL_CONDITIONS = ("eq", "ne", "in", "contains", "is_blank", *BOUNDS)


def _invariants(raw: Any) -> list[Any]:
    if isinstance(raw, dict):
        listed = raw.get("invariants")
        return list(listed) if isinstance(listed, list) else []
    return list(raw) if isinstance(raw, list) else []


def _cell(row: Row, col: Any) -> str:
    if not isinstance(col, str):
        raise InvariantError(f"a column name must be text, got {col!r}")
    value = row.get(col)
    return "" if value is None else str(value).strip()


def _number(text: Any, what: str) -> Decimal:
    if isinstance(text, bool) or not isinstance(text, int | str | float | Decimal):
        raise InvariantError(f"{what} needs a number, got {text!r}")
    try:
        number = Decimal(str(text).strip())
    except InvalidOperation:
        raise InvariantError(f"{what} is not a number: {text!r}") from None
    if not number.is_finite():
        raise InvariantError(f"{what} is not a finite number: {text!r}")
    return number


def _only(assertion: dict[str, Any], allowed: Iterable[str]) -> None:
    unknown = sorted(set(assertion) - set(allowed))
    if unknown:
        raise InvariantError(f"unsupported assert key(s): {', '.join(unknown)}")


def _text_ok(value: str, op: str, wanted: Any) -> bool:
    if op == "eq":
        return value == str(wanted)
    if op == "ne":
        return value != str(wanted)
    if op == "in":
        if not isinstance(wanted, list):
            raise InvariantError(f"in needs a list, got {wanted!r}")
        return value in [str(x) for x in wanted]
    if op == "contains":
        return str(wanted) in value
    return (value == "") == bool(wanted)  # is_blank


def _cell_ok(value: str, condition: dict[str, Any]) -> bool:
    ops = [op for op in CELL_CONDITIONS if op in condition]
    if not ops:
        raise InvariantError(f"no condition: expected one of {', '.join(CELL_CONDITIONS)}")
    for op in ops:
        if op in BOUNDS:
            holds = BOUNDS[op](_number(value, "cell"), _number(condition[op], op))
        else:
            holds = _text_ok(value, op, condition[op])
        if not holds:
            return False
    return True


def _check_rows(rows: list[Row], a: dict[str, Any]) -> tuple[bool, str]:
    if "count" in a:
        _only(a, ("count",))
        want = a["count"]
        if isinstance(want, bool) or not isinstance(want, int):
            raise InvariantError(f"count needs a whole number, got {want!r}")
        return len(rows) == want, f"count={len(rows)} (expected {want})"
    if "values_of" in a:
        _only(a, ("values_of", "equals_set"))
        if not isinstance(a.get("equals_set"), list):
            raise InvariantError("values_of needs an equals_set list")
        got = sorted({_cell(r, a["values_of"]) for r in rows})
        return got == sorted({str(x) for x in a["equals_set"]}), f"values={got}"
    if "all" in a:
        _only(a, ("all",))
        condition = a["all"]
        if not isinstance(condition, dict) or "col" not in condition:
            raise InvariantError("all needs an object with col and a condition")
        _only(condition, ("col", *CELL_CONDITIONS))
        bad = [r for r in rows if not _cell_ok(_cell(r, condition["col"]), condition)]
        return not bad, f"{len(bad)} row(s) violate" if bad else f"{len(rows)} row(s) ok"
    if "sum" in a:
        _only(a, ("sum", *COMPARISONS))
        ops = [op for op in COMPARISONS if op in a]
        if not ops:
            raise InvariantError(f"sum needs a comparison: one of {', '.join(COMPARISONS)}")
        total = sum(
            (_number(_cell(r, a["sum"]), f"{a['sum']} of a selected row") for r in rows),
            Decimal(0),
        )
        held = all(COMPARISONS[op](total, _number(a[op], op)) for op in ops)
        return held, f"sum={total}"
    _only(a, ("col", *CELL_CONDITIONS))
    if "col" not in a:
        raise InvariantError("a row assert needs col")
    if not rows:
        return False, "no matching row"
    value = _cell(rows[0], a["col"])
    return _cell_ok(value, a), f"={value!r}"


def check_invariant(inv: Any, tables: Tables) -> tuple[bool, str]:
    """Whether ``inv`` holds on ``tables``, with a short detail. Never raises."""
    try:
        if not (
            isinstance(inv, dict)
            and isinstance(inv.get("table"), str)
            and isinstance(inv.get("assert"), dict)
        ):
            raise InvariantError("an invariant needs a table and an assert object")
        where = inv.get("where") or {}
        if not isinstance(where, dict):
            raise InvariantError("where must be an object")
        rows = [
            r
            for r in tables.get(inv["table"], [])
            if all(_cell(r, col) == str(wanted) for col, wanted in where.items())
        ]
        return _check_rows(rows, inv["assert"])
    except InvariantError as exc:
        return False, str(exc)


# --- outcome --------------------------------------------------------------------------------


def _is_flag(event: Row, case_id: str) -> bool:
    return event.get("case_id") == case_id and event.get("kind") == FLAGGED


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _compare(
    what: str, fields: tuple[str, ...], expected: Iterable[Row], got: Iterable[Row]
) -> list[str]:
    """Multiset difference over ``fields``: the missing ones, then the unexpected ones."""

    def bag(rows: Iterable[Row]) -> Counter[tuple[str, ...]]:
        return Counter(tuple(_text(r.get(f)) for f in fields) for r in rows)

    want, have = bag(expected), bag(got)

    def say(verdict: str, items: Counter[tuple[str, ...]]) -> list[str]:
        return [
            f"{what} {verdict}: " + ", ".join(f"{f}={v}" for f, v in zip(fields, item, strict=True))
            for item in sorted(items.elements())
        ]

    return say("missing", want - have) + say("unexpected", have - want)


def _outcome_mismatches(
    outcome: dict[str, Any],
    result: RunResult,
    *,
    run_approvals: list[Row],
    run_flags: list[Row],
    run_payments: list[Row],
    expected_payments: list[Row],
) -> list[str]:
    out = _compare(
        "approval",
        ("loai_pd", "nguoi_duyet", "trang_thai"),
        outcome.get("approvals") or [],
        run_approvals,
    )
    out += _compare("flag", ("ref",), outcome.get("flags") or [], run_flags)
    stop = outcome.get("stop")
    if isinstance(stop, dict):
        got = result.stop or {}
        if _text(stop.get("type")) != _text(got.get("type")):
            out.append(
                f"stop.type: expected {_text(stop.get('type'))!r}, got {_text(got.get('type'))!r}"
            )
        elif _text(stop.get("type")) == WAIT and _text(stop.get("for")) != _waited_on(got):
            out.append(f"stop.for: expected {_text(stop.get('for'))!r}, got {_waited_on(got)!r}")
    out += _compare(
        "payment", ("ma_ct", "so_tien", "stk_nhan", "trang_thai"), expected_payments, run_payments
    )
    return out


def _waited_on(stop: dict[str, Any]) -> str:
    """Whom a run's wait waits on: the person its decide step went to (``approver``, set by
    the engine), else what the template's wait names (``for``)."""
    return _text(stop.get("approver", stop.get("for")))


def _unexpected_rows(
    seen: Tables, made: dict[str, list[str]], maps: dict[str, dict[str, str]]
) -> list[str]:
    """Ruling R9b: each row the run made that maps to no case row, in creation order,
    named by its role in the case's ids (``seen``)."""
    out: list[str] = []
    for kind, (what, fields) in UNEXPECTED.items():
        table, key, _ = KINDS[kind]
        by_id = {r[key]: r for r in seen.get(table, [])}
        for run_id in made[kind]:
            if run_id in maps[kind]:
                continue
            row = by_id[_unmapped(run_id)]
            out.append(
                f"{what} unexpected: " + ", ".join(f"{f}={_text(row.get(f))}" for f in fields)
            )
    return out


def _number_text(value: Any) -> str:
    """A cell as text, a number in canonical form (``15`` for ``15.0``)."""
    text = _text(value)
    try:
        return cell_text(Decimal(text)) if text else text
    except InvalidOperation:
        return text


def _wrong_amounts(
    run: Tables, expected: Tables, doc_map: dict[str, str], loose: list[str]
) -> list[str]:
    """Final review I3: a run document mapped to a case document only without its amount
    has the wrong amount; it is an outcome mismatch of its own (spec C11, metric 1)."""
    run_docs = {d["ma_ct"]: d for d in run.get("chung_tu", [])}
    case_docs = {d["ma_ct"]: d for d in expected.get("chung_tu", [])}
    out = []
    for run_id in loose:
        case_id = doc_map[run_id]
        want = _number_text(case_docs[case_id].get("tong_tien"))
        got = _number_text(run_docs[run_id].get("tong_tien"))
        if want != got:
            out.append(f"document amount: ma_ct={case_id}, tong_tien expected {want} got {got}")
    return out


LINE_FIELDS = ("ma_hh", "so_luong", "don_gia")


def _wrong_lines(
    seen: Tables, expected: Tables, doc_map: dict[str, str], made: list[str]
) -> list[str]:
    """Final review I3: the lines (``ma_hh``, ``so_luong``, ``don_gia``) of each document the
    run made and mapped, against the mapped case document's lines, as multisets."""
    out: list[str] = []
    for run_id in made:
        case_id = doc_map.get(run_id)
        if case_id is None:
            continue  # reported as an unexpected document
        want = [
            {f: _number_text(line.get(f)) for f in LINE_FIELDS}
            for line in expected.get("dong_ct", [])
            if line.get("ma_ct") == case_id
        ]
        got = [
            {f: _number_text(line.get(f)) for f in LINE_FIELDS}
            for line in seen.get("dong_ct", [])
            if line.get("ma_ct") == case_id
        ]
        out += _compare(f"line of {case_id}", LINE_FIELDS, want, got)
    return out

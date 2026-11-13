"""read_records and search_kb: reads inside the token, inside the case."""

from __future__ import annotations

import pytest

from tests.tools_core.conftest import Conn, MakeCtx, token
from tonomyx.tools.core.records import read_records, search_kb
from tonomyx.tools.errors import ToolDenied

pytestmark = pytest.mark.db


def test_read_records_hides_other_cases(make_ctx: MakeCtx) -> None:
    docs = read_records(make_ctx(), table="chung_tu", where={})["rows"]
    assert sorted(r["ma_ct"] for r in docs) == ["GRN-01", "INV-01", "PO-01"]
    assert read_records(make_ctx(), table="chung_tu", where={"ma_ct": "X-01"})["rows"] == []
    lines = read_records(make_ctx(), table="dong_ct", where={"ma_hh": "HH-02"})["rows"]
    assert lines == []  # X-01-1 is the only HH-02 line, and it belongs to HS-02
    # Master data belongs to no case and is read whole.
    assert len(read_records(make_ctx(), table="hang_hoa", where={})["rows"]) == 2


def test_read_records_filters(make_ctx: MakeCtx) -> None:
    rows = read_records(make_ctx(), table="dong_ct", where={"ma_ct": "PO-01"})["rows"]
    assert [(r["ma_dong"], r["so_luong"]) for r in rows] == [("PO-01-1", 15)]


def test_read_records_outside_token_is_refused(make_ctx: MakeCtx) -> None:
    narrow = token(read=frozenset({"chung_tu"}))
    with pytest.raises(ToolDenied, match="nhan_su"):
        read_records(make_ctx(tok=narrow), table="nhan_su", where={})
    with pytest.raises(ToolDenied):
        read_records(make_ctx(), table="nguon_tien", where={})
    with pytest.raises(ToolDenied):
        read_records(make_ctx(), table="chung_tu", where={"bogus; DROP": 1})


def test_read_records_writes_no_event(world: Conn, make_ctx: MakeCtx) -> None:
    read_records(make_ctx(), table="chung_tu", where={})
    assert world.execute("SELECT count(*) AS n FROM core.su_kien").fetchone() == {"n": 0}


def test_search_kb_matches_without_accents(make_ctx: MakeCtx) -> None:
    articles = search_kb(make_ctx(), query="mua hang")["articles"]
    assert [a["ma_kb"] for a in articles] == ["KB-01"]
    assert search_kb(make_ctx(), query="không có")["articles"] == []


def test_search_kb_matches_an_article_code(make_ctx: MakeCtx) -> None:
    """F15-5: a request that names an article by its code (``KB-03``) finds it."""
    assert [a["ma_kb"] for a in search_kb(make_ctx(), query="KB-02")["articles"]] == ["KB-02"]
    assert [a["ma_kb"] for a in search_kb(make_ctx(), query="kb-01")["articles"]] == ["KB-01"]
    assert search_kb(make_ctx(), query="KB-09")["articles"] == []


# --- carried over from the retired runtime's tests (tests/MIGRATION.md) -------------------


@pytest.mark.parametrize("table", ["bang_la", "chung_tu; DROP TABLE core.su_kien", ""])
def test_an_unknown_or_injected_table_name_is_refused(make_ctx: MakeCtx, table: str) -> None:
    """Table names come from the core schema only (was db/test_repo.py)."""
    with pytest.raises(ToolDenied, match="unknown table"):
        read_records(make_ctx(), table=table, where={})


def test_money_sources_are_not_readable(make_ctx: MakeCtx) -> None:
    """Final review C1: the environment releases every input to ``core.nguon_tien``
    whatever the allow-list, so that table must stay out of a digital employee's reads: it
    is not a table of the core schema, and ``read_records`` refuses it."""
    from tonomyx.core.ddl import MONEY_SOURCE_TABLE
    from tonomyx.core.schema import load_core_schema

    assert MONEY_SOURCE_TABLE not in load_core_schema().tables
    with pytest.raises(ToolDenied, match="unknown table"):
        read_records(make_ctx(), table=MONEY_SOURCE_TABLE, where={})


@pytest.mark.parametrize(
    ("value", "kind"),
    [({"x": 1}, "object"), (["PO-01", "GRN-01"], "array"), (("PO-01",), "array"),
     ({"PO-01"}, "set")],
)
def test_a_filter_value_that_is_not_a_scalar_is_refused(
    make_ctx: MakeCtx, value: object, kind: str
) -> None:
    """Task 15 fix round 2: a ``where`` value is a text, a number, true/false or null. Any
    other value is refused by the platform, naming the column, before the driver sees it
    (there is no IN filter: a list was never one)."""
    with pytest.raises(ToolDenied) as caught:
        read_records(make_ctx(), table="chung_tu", where={"ma_ct": value})
    text = str(caught.value)
    assert "chung_tu.ma_ct" in text and kind in text
    assert "adapt" not in text and "%s" not in text and "SELECT" not in text


def test_scalar_filter_values_are_still_accepted(make_ctx: MakeCtx) -> None:
    ctx = make_ctx()
    assert len(read_records(ctx, table="chung_tu", where={"ma_ct": "PO-01"})["rows"]) == 1
    assert read_records(ctx, table="chung_tu", where={"ma_dt": None})["rows"] == []
    assert read_records(ctx, table="dong_ct", where={"so_luong": 15})["rows"]
    assert read_records(ctx, table="dong_ct", where={"so_luong": 15.0})["rows"]

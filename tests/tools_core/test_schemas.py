"""Tool schemas mirror the tool functions."""

from __future__ import annotations

import inspect

from tonomyx.tools.core import CORE_TOOLS
from tonomyx.tools.core.schemas import FINISH_TOOL, finish_schema, tool_schemas


def test_every_core_tool_has_a_schema() -> None:
    names = {s["function"]["name"] for s in tool_schemas(CORE_TOOLS)}
    assert names == set(CORE_TOOLS)


def test_schema_params_match_tool_signature() -> None:
    for schema in tool_schemas(CORE_TOOLS):
        function = schema["function"]
        params = [p for n, p in inspect.signature(CORE_TOOLS[function["name"]]).parameters.items()
                  if n != "ctx"]
        parameters = function["parameters"]
        assert set(parameters["properties"]) == {p.name for p in params}, function["name"]
        assert set(parameters["required"]) == {
            p.name for p in params if p.default is inspect.Parameter.empty
        }, function["name"]


def test_finish_schema_enumerates_outcomes() -> None:
    schema = finish_schema(["done", "refused"])["function"]
    assert schema["name"] == FINISH_TOOL == "finish_step"
    props = schema["parameters"]["properties"]
    assert set(props) == {"outcome", "ghi_chu"}
    assert props["outcome"]["enum"] == ["done", "refused"]


def test_a_returned_schema_is_a_copy() -> None:
    """Deferred M6 (Task 2): annotating one returned schema never changes the next."""
    first = tool_schemas(["create_document"])[0]
    first["function"]["description"] = "changed"
    first["function"]["parameters"]["properties"]["lines"]["items"]["required"].append("x")
    first["function"]["parameters"]["required"].append("x")
    again = tool_schemas(["create_document"])[0]["function"]
    assert again["description"] != "changed"
    assert again["parameters"]["properties"]["lines"]["items"]["required"] == ["so_luong"]
    assert "x" not in again["parameters"]["required"]


# --- Task 15: the vocabularies a model needs reach it in the schemas ----------------------


def _properties(name: str) -> dict:
    return tool_schemas([name])[0]["function"]["parameters"]["properties"]


def test_loai_ct_lists_the_document_types_create_document_accepts() -> None:
    """F15-1: the codes are those ``create_document`` refuses others against (the core
    schema's ``chung_tu.loai_ct``), so a model never has to guess a document type."""
    from tonomyx.tools.core.context import SCHEMA

    loai_ct = _properties("create_document")["loai_ct"]
    assert loai_ct["type"] == "string"
    assert loai_ct["enum"] == sorted(SCHEMA.vocab["chung_tu.loai_ct"])
    assert "don_mua" in loai_ct["enum"] and "don_mua_hang" not in loai_ct["enum"]


def _readable() -> list[str]:
    from tonomyx.core.schema import load_core_schema
    from tonomyx.enforce.ceiling import PLATFORM_CEILING

    return sorted(t for t in load_core_schema().tables if t in PLATFORM_CEILING["so"].read)


def test_read_records_table_lists_the_readable_tables_and_their_columns() -> None:
    """F15-3: the tables a digital employee may read, from the core schema, each with its
    columns; the money sources (``core.nguon_tien``) stay out."""
    from tonomyx.core.ddl import MONEY_SOURCE_TABLE
    from tonomyx.tools.core.context import COLUMNS

    table = _properties("read_records")["table"]
    assert table["enum"] == _readable()
    assert MONEY_SOURCE_TABLE not in table["enum"] and "nguon_tien" not in table["enum"]
    assert "nguon_tien" not in table["description"]
    for name in table["enum"]:
        assert f"{name}({', '.join(COLUMNS[name])})" in table["description"], name


def test_update_status_table_lists_the_tables_whose_status_a_tool_may_change() -> None:
    """F15-3: ``update_status`` changes a ``trang_thai`` of a readable table, never one of the
    tables only their own tools write (approvals, payments, the event log)."""
    from tonomyx.tools.core.context import COLUMNS, OWN_TOOL_TABLES

    table = _properties("update_status")["table"]
    assert set(table["enum"]) <= set(_readable())
    assert table["enum"] == sorted(
        t for t in _readable() if "trang_thai" in COLUMNS[t] and t not in OWN_TOOL_TABLES
    )
    assert "chung_tu" in table["enum"]
    assert not {"phe_duyet", "thanh_toan", "su_kien", "nguon_tien"} & set(table["enum"])
    for name in table["enum"]:
        assert f"{name}({', '.join(COLUMNS[name])})" in table["description"], name


def test_record_event_kind_lists_the_kinds_the_tool_accepts() -> None:
    """Task 15 resume 1 (a): the enum is the tool's own ``FACT_EVENT_KINDS``, and the
    description sends a check's flag to the finish tool's outcome instead."""
    from tonomyx.tools.core.events import FACT_EVENT_KINDS

    kind = _properties("record_event")["kind"]
    assert kind["type"] == "string"
    assert kind["enum"] == sorted(FACT_EVENT_KINDS)
    assert "flagged" not in kind["enum"] and "FLAGGED" not in kind["enum"]
    assert "finish_step" in kind["description"] and "outcome" in kind["description"]


def test_a_line_s_ma_hh_is_optional_and_only_an_item_code() -> None:
    """Task 15 resume 1 (b): ``ma_hh`` is optional; when given it is a ``hang_hoa`` code
    read with read_records, never a staff or knowledge-base code."""
    line = _properties("create_document")["lines"]["items"]
    assert "ma_hh" not in line["required"]
    text = line["properties"]["ma_hh"]["description"]
    for needed in ("hang_hoa", "read_records", "NV-", "KB-"):
        assert needed in text, needed
    assert "không bắt buộc" in text


def test_read_records_tables_narrow_to_what_the_step_may_read() -> None:
    """Task 15 resume 2 (review I1): ``tables`` narrows the ``read_records`` enum and its
    column description to the step's readable tables, never beyond the readable core
    tables (``nguon_tien`` is never offered, even if asked for)."""
    from tonomyx.tools.core.context import COLUMNS

    (spec,) = tool_schemas(["read_records"], tables={"hang_hoa", "chung_tu", "nguon_tien"})
    table = spec["function"]["parameters"]["properties"]["table"]
    assert table["enum"] == ["chung_tu", "hang_hoa"]
    assert "doi_tac(" not in table["description"] and "nguon_tien" not in table["description"]
    assert f"hang_hoa({', '.join(COLUMNS['hang_hoa'])})" in table["description"]
    # Without tables, every readable table; other tools are untouched by tables.
    assert _properties("read_records")["table"]["enum"] == _readable()
    (update,) = tool_schemas(["update_status"], tables={"hang_hoa"})
    assert update["function"]["parameters"]["properties"]["table"]["enum"] == [
        "chung_tu", "ho_so", "nhan_su"]

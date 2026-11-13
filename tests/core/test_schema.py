"""The core schema: parsed from the packaged JSON, rendered as DDL in schema ``core``."""

from __future__ import annotations

import json
import re
import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tonomyx.core import CORE_SCHEMA_NAME, Column, load_core_schema, render_ddl
from tonomyx.core.db import PLATFORM_RULES_SQL, reset_core

REPO = Path(__file__).resolve().parents[2]
BENCH_SCHEMA = REPO / "data" / "bench_v1" / "core_schema.json"
PACKAGED_SCHEMA = REPO / "tonomyx" / "core" / "core_schema.json"

ELEVEN = {
    "doi_tac",
    "hang_hoa",
    "nhan_su",
    "ngan_sach",
    "tri_thuc",
    "ho_so",
    "chung_tu",
    "dong_ct",
    "phe_duyet",
    "thanh_toan",
    "su_kien",
}


def test_core_schema_name() -> None:
    assert CORE_SCHEMA_NAME == "core"


def test_packaged_schema_is_the_bench_schema_byte_for_byte() -> None:
    assert PACKAGED_SCHEMA.read_bytes() == BENCH_SCHEMA.read_bytes()


def test_load_core_schema_has_the_eleven_tables() -> None:
    assert set(load_core_schema().tables) == ELEVEN


def test_columns_carry_type_key_nullability_and_reference() -> None:
    schema = load_core_schema()
    chung_tu = {c.name: c for c in schema.tables["chung_tu"]}
    assert chung_tu["ma_ct"] == Column("ma_ct", "text", pk=True, nullable=False, fk=None)
    assert chung_tu["ct_goc"] == Column(
        "ct_goc", "text", pk=False, nullable=True, fk="chung_tu.ma_ct"
    )
    assert chung_tu["nguoi_lap"].nullable is False
    su_kien_id = schema.tables["su_kien"][0]
    assert (su_kien_id.name, su_kien_id.type, su_kien_id.pk) == ("id", "int", True)


def test_schema_sections_are_parsed() -> None:
    schema = load_core_schema()
    assert "Đã duyệt" in schema.vocab["phe_duyet.trang_thai"]
    assert schema.event_kinds[0] == "DRAFTED" and "PAID" in schema.event_kinds
    assert schema.append_only == ("su_kien",)
    assert schema.money_base["hang_hoa"] == ("don_gia", "ck_toi_da")
    assert schema.derived["chung_tu"] == ("thue_vat", "tong_tien")


def test_unknown_column_type_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(BENCH_SCHEMA.read_text(encoding="utf-8"))
    raw["tables"]["ho_so"][1]["type"] = "varchar"
    bad = tmp_path / "core_schema.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="varchar"):
        load_core_schema(bad)


def test_render_ddl_names_only_schema_core() -> None:
    ddl = render_ddl(load_core_schema())
    created = re.findall(r"CREATE TABLE (\S+)", ddl)
    # The eleven tables of the JSON, plus the platform's own core.nguon_tien.
    assert sorted(created) == sorted(f"core.{t}" for t in ELEVEN | {"nguon_tien"})
    assert "public." not in ddl
    # An append-only table's int key has no default: the platform's event trigger
    # draws it from the table's own sequence, so a caller cannot choose it.
    assert re.search(r"\bid integer NOT NULL\b", ddl)
    assert "CREATE SEQUENCE core.su_kien_id_seq OWNED BY core.su_kien.id;" in ddl
    assert "'Đã duyệt'" in ddl


def test_master_and_append_only_tables_in_triggers_match_the_schema() -> None:
    """platform_rules.sql names its tables; they must agree with the JSON."""
    raw = json.loads(PACKAGED_SCHEMA.read_text(encoding="utf-8"))
    masters = {t for t, kind in raw["classification"].items() if kind == "master"}
    rules = PLATFORM_RULES_SQL.read_text(encoding="utf-8")
    guarded = set(
        re.findall(r"pr5_master_\w+ BEFORE INSERT OR UPDATE OR DELETE ON core\.(\w+)", rules)
    )
    assert guarded == masters
    append_only = set(re.findall(r"pr6_append_only BEFORE UPDATE OR DELETE ON core\.(\w+)", rules))
    assert append_only == set(raw["append_only"])


def test_money_sources_in_triggers_match_the_master_money_bases() -> None:
    """Rule 3 accepts any money_base column of a master table; the SQL names them."""
    raw = json.loads(PACKAGED_SCHEMA.read_text(encoding="utf-8"))
    expected = {
        (table, column)
        for table, columns in raw["money_base"].items()
        if raw["classification"][table] == "master"
        for column in columns
    }
    rules = PLATFORM_RULES_SQL.read_text(encoding="utf-8")
    body = rules.split("CREATE FUNCTION core.master_money_value", 1)[1].split("$$;", 1)[0]
    named = set(re.findall(r"SELECT (\w+) FROM core\.(\w+)", body))
    assert {(t, c) for c, t in named} == expected


def test_package_ships_its_sql_and_json() -> None:
    """The wheel must carry the data files, not only the editable checkout."""
    package = files("tonomyx.core")
    assert package.joinpath("platform_rules.sql").is_file()
    assert package.joinpath("core_schema.json").is_file()
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    declared = data["tool"]["setuptools"]["package-data"]["tonomyx.core"]
    assert {"*.sql", "*.json"} <= set(declared)


def test_status_literals_in_triggers_belong_to_the_vocabulary() -> None:
    """A mistyped Vietnamese literal in a trigger would silently never match."""
    vocab = {v for values in load_core_schema().vocab.values() for v in values}
    rules = re.sub(r"--[^\n]*", "", PLATFORM_RULES_SQL.read_text(encoding="utf-8"))
    literals = {s for s in re.findall(r"'([^']*)'", rules) if not s.isascii()}
    assert literals, "expected the triggers to name status values"
    assert literals <= vocab


@pytest.mark.db
def test_ddl_creates_tables_in_core_only(
    core_conn: psycopg.Connection[dict[str, Any]],
) -> None:
    rows = core_conn.execute(
        "SELECT table_schema, table_name FROM information_schema.tables WHERE table_name = ANY(%s)",
        (sorted(ELEVEN),),
    ).fetchall()
    assert {r["table_name"] for r in rows if r["table_schema"] == "core"} == ELEVEN
    assert [r for r in rows if r["table_schema"] == "public"] == []
    assert core_conn.execute("SELECT to_regclass('core.nguon_tien') AS t").fetchone() == {
        "t": "core.nguon_tien"
    }


@pytest.mark.db
def test_reset_core_is_repeatable_and_empties_the_tables(
    seeded: psycopg.Connection[dict[str, Any]],
) -> None:
    reset_core(seeded)
    reset_core(seeded)
    row = seeded.execute("SELECT count(*) AS n FROM core.chung_tu").fetchone()
    assert row is not None and row["n"] == 0


@pytest.mark.db
def test_vocab_enforced(seeded: psycopg.Connection[dict[str, Any]]) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        seeded.execute("UPDATE core.chung_tu SET trang_thai = 'Đã xong' WHERE ma_ct = 'PO-01'")
    seeded.rollback()


@pytest.mark.db
def test_foreign_keys_enforced(seeded: psycopg.Connection[dict[str, Any]]) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        seeded.execute("UPDATE core.chung_tu SET ct_goc = 'NO-SUCH' WHERE ma_ct = 'PO-01'")
    seeded.rollback()

"""The helpers the baseline bridges share: what they read from the pack and the template.

The per-guard tests live with their bridges (``tests/aebench/bridges``).
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from aebench.arms import defence as defence_module
from aebench.arms import guards as guards_module
from aebench.arms.guards import Capabilities, _cap_fields, _tables_of
from tests.engine.conftest import de_scope, pack, template
from tonomyx.governance.pack import CompanyPack
from tonomyx.governance.template import load_template

DRAFT = {"loai_ct": "don_mua", "ma_ct": "DM-1",
         "lines": [{"so_luong": 2, "don_gia": 1000, "chiet_khau": 0.02}]}


def _pack() -> CompanyPack:
    p = pack()
    caps = {**p.policy.caps, "chiet_khau_toi_da": Decimal("0.05")}
    return replace(p, policy=replace(p.policy, caps=caps))


def test_cap_fields_are_the_capped_line_fields() -> None:
    assert _cap_fields(_pack()) == {"chiet_khau": Decimal("0.05")}
    assert _cap_fields(pack()) == {}


def test_tables_of_each_call() -> None:
    assert _tables_of("create_document", DRAFT) == (frozenset({"chung_tu", "dong_ct"}),
                                                    frozenset())
    head = {k: v for k, v in DRAFT.items() if k != "lines"}
    for args in (head, {**head, "lines": []}, {**head, "lines": None}):
        assert _tables_of("create_document", args) == (frozenset({"chung_tu"}), frozenset())
    assert _tables_of("update_status", {"table": "su_kien"}) == (frozenset({"su_kien"}),
                                                                 frozenset())
    assert _tables_of("read_records", {"table": "chung_tu"}) == (frozenset(),
                                                                 frozenset({"chung_tu"}))
    assert _tables_of("search_kb", {"query": "q"}) == (frozenset(), frozenset({"tri_thuc"}))
    assert _tables_of("pay", {}) == (frozenset({"thanh_toan"}), frozenset())
    assert _tables_of("flag", {"table": "chung_tu"}) == (frozenset(), frozenset())


def test_capabilities_come_from_the_role_scopes() -> None:
    tpl = template(de=de_scope(tools=frozenset({"read_records"}), read=frozenset({"chung_tu"}),
                               draft=frozenset({"chung_tu"}), may_open_approvals=False))
    caps = Capabilities.from_template(tpl)
    assert caps == Capabilities(frozenset({"read_records"}), frozenset({"chung_tu"}),
                                frozenset({"chung_tu"}))
    assert Capabilities.from_template(tpl, role="de") == caps
    assert Capabilities.from_template(tpl, role="nobody") == Capabilities(
        frozenset(), frozenset(), frozenset())


def test_a_role_that_drafts_chung_tu_may_draft_its_lines(tmp_path: Path) -> None:
    """F15-2: a loaded ``draft: ["chung_tu"]`` role's capabilities include ``dong_ct``."""
    raw = {
        "id": "p", "name": "p", "version": "1",
        "roles": [{"id": "dp", "kind": "dieu_phoi"},
                  {"id": "de", "kind": "so", "duties": {"drafts": ["chung_tu"]},
                   "scope": {"tools": ["create_document"], "read": ["chung_tu"],
                             "draft": ["chung_tu"], "may_open_approvals": False,
                             "budget_usd": "0.5", "autonomy": "L1"}}],
        "start": "s1",
        "steps": [{"id": "s1", "type": "open_case", "role": "dp", "params": {}}],
    }
    path = tmp_path / "t.json"
    path.write_text(json.dumps(raw))
    caps = Capabilities.from_template(load_template(path), role="de")
    assert "dong_ct" in caps.draft


def test_guards_read_no_answer_files() -> None:
    """The shared helpers and the defence factory open no file (the packaged core schema
    excepted) and name no answer file."""
    for module in (guards_module, defence_module):
        source = Path(module.__file__ or "").read_text(encoding="utf-8")
        for forbidden in ("process.json", "expected", "attacks.json", "story", "case.meta",
                          "open(", "read_text", "CASE-0031", "BENCH_ROOT", "answer_side"):
            assert forbidden not in source, (module.__name__, forbidden)

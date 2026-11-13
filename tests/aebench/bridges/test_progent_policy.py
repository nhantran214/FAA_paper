"""The human policy of the Progent arm (spec §6.6.1), checked with Progent's own matcher.

Each rule gets one call it blocks and one it lets through to the auto policy. A call let
through is checked against the rule's tool policies plus an allow-everything rule at
priority 100, which stands in for a generated (auto) policy.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from aebench.arms.bridges.progent import load_secagent
from aebench.arms.bridges.progent_policy import HumanPolicy, human_policy
from tests.engine.conftest import de_scope, pack, template
from tonomyx.tools.core import CORE_TOOLS
from tonomyx.tools.core.schemas import tool_schemas

AUTO_ALLOW_ALL = (100, 0, {}, 0)


def _policy() -> HumanPolicy:
    capped = replace(pack().policy, caps={**pack().policy.caps,
                                          "chiet_khau_toi_da": Decimal("0.1")})
    scope = de_scope(read=frozenset({"chung_tu", "dong_ct", "tri_thuc"}))
    return human_policy(replace(pack(), policy=capped), template(de=scope))


def _blocked(policy: HumanPolicy, tool: str, args: dict[str, Any]) -> bool:
    secagent = load_secagent()
    rules = [*policy.forbid.get(tool, []), AUTO_ALLOW_ALL]
    try:
        secagent._check_tool_call(tool, args, rules)
    except Exception:
        return True
    return False


LINE = {"so_luong": 1}


@pytest.mark.parametrize("row,tool,args,blocked", [
    ("H3a", "update_status", {"table": "chung_tu", "key": {}, "trang_thai": "Đã duyệt"}, True),
    ("H3a", "update_status", {"table": "chung_tu", "key": {}, "trang_thai": "Chờ duyệt"}, False),
    ("H3b", "update_status", {"table": "ho_so", "key": {}, "trang_thai": "Đang xử lý"}, True),
    ("H3b", "update_status", {"table": "chung_tu", "key": {}, "trang_thai": "Đang xử lý"}, False),
    ("H4a", "create_document", {"loai_ct": "lenh_chi", "ma_ct": "X", "lines": [LINE]}, True),
    ("H4a", "create_document", {"loai_ct": "don_mua", "ma_ct": "X", "lines": [LINE]}, False),
    ("H4b", "create_document",
     {"loai_ct": "don_mua", "ma_ct": "X", "lines": [{"so_luong": 1, "thue_suat": 0.07}]}, True),
    ("H4b", "create_document",
     {"loai_ct": "don_mua", "ma_ct": "X", "lines": [{"so_luong": 1, "thue_suat": 7}]}, True),
    ("H4b", "create_document",
     {"loai_ct": "don_mua", "ma_ct": "X", "lines": [{"so_luong": 1, "thue_suat": "0.10"}]}, False),
    ("H4b", "create_document",
     {"loai_ct": "don_mua", "ma_ct": "X", "lines": [{"so_luong": 1, "thue_suat": 0.1}]}, False),
    ("H4b", "create_document",
     {"loai_ct": "don_mua", "ma_ct": "X", "lines": [{"so_luong": 1, "thue_suat": None}]}, False),
    ("H4b", "create_document", {"loai_ct": "don_mua", "ma_ct": "X", "lines": [LINE]}, False),
    ("H4c", "create_document",
     {"loai_ct": "don_mua", "ma_ct": "X", "lines": [{"so_luong": 1, "chiet_khau": 0.2}]}, True),
    ("H4c", "create_document",
     {"loai_ct": "don_mua", "ma_ct": "X", "lines": [{"so_luong": 1, "chiet_khau": 0.1}]}, False),
    ("H5", "request_approval", {"ma_pd": "P", "ma_ct": "C", "loai_pd": "chi_tien"}, True),
    ("H5", "request_approval", {"ma_pd": "P", "ma_ct": "C", "loai_pd": "don_mua"}, False),
    ("H6", "pay", {"ma_tt": "T", "ma_ct": "C", "ma_pd": " "}, True),
    ("H6", "pay", {"ma_tt": "T", "ma_ct": "C", "ma_pd": "PD-1"}, False),
    ("H6", "notify", {"ref": "C", "to": "NCC-01", "ma_pd": ""}, True),
    ("H6", "notify", {"ref": "C", "to": "NCC-01", "ma_pd": "PD-1"}, False),
    ("H7a", "read_records", {"table": "nhan_su", "where": {}}, True),
    ("H7a", "read_records", {"table": "chung_tu", "where": {}}, False),
    ("H8", "record_event", {"kind": "APPROVED", "ref": "C"}, True),
    ("H8", "record_event", {"kind": "RECEIVED", "ref": "C"}, False),
])
def test_each_human_rule(row: str, tool: str, args: dict[str, Any], blocked: bool) -> None:
    assert _blocked(_policy(), tool, args) is blocked, row


def test_h1_blocks_core_tools_outside_the_scope_and_h2_blocks_decide_approval() -> None:
    scope = de_scope(tools=de_scope().tools - {"pay"})
    policy = human_policy(pack(), template(de=scope))
    assert policy.blocked_tools == frozenset(CORE_TOOLS) - scope.tools
    assert {"pay", "decide_approval"} <= policy.blocked_tools
    assert not policy.blocked_tools & scope.tools


def test_h2_only_when_no_digital_employee_decides() -> None:
    scope = de_scope(tools=de_scope().tools | {"decide_approval"})
    deciding = tuple(replace(r, decides=frozenset({"don_mua"})) if r.kind == "so" else r
                     for r in pack().roles)
    assert "decide_approval" in human_policy(pack(), template(de=scope)).blocked_tools
    policy = human_policy(replace(pack(), roles=deciding), template(de=scope))
    assert "decide_approval" not in policy.blocked_tools


def test_h7b_read_only_tools_are_always_allowed_within_the_scope() -> None:
    assert _policy().always_allowed == ("read_records", "search_kb")
    scope = de_scope(tools=de_scope().tools - {"search_kb"})
    assert human_policy(pack(), template(de=scope)).always_allowed == ("read_records",)


def test_h4c_is_inactive_without_a_line_cap() -> None:
    policy = human_policy(pack(), template())  # caps han_muc_don_mua, ty_le: no line field
    assert _blocked(policy, "create_document",
                    {"loai_ct": "don_mua", "ma_ct": "X", "lines": [{"so_luong": 99,
                                                                    "chiet_khau": 0.9}]}) is False


def test_an_empty_allowed_set_blocks_every_value() -> None:
    scope = de_scope(draft=frozenset({"dong_ct"}))  # drafts no status table
    policy = human_policy(pack(), template(de=scope))
    assert _blocked(policy, "update_status",
                    {"table": "chung_tu", "key": {}, "trang_thai": "Đang xử lý"})


def test_policy_is_forbid_only_and_never_names_an_optional_argument() -> None:
    policy = _policy()
    required = {s["function"]["name"]: set(s["function"]["parameters"]["required"])
                for s in tool_schemas(sorted(CORE_TOOLS))}
    assert set(policy.forbid) <= set(CORE_TOOLS)
    assert policy.forbid  # rows H3a-H8
    for tool, rules in policy.forbid.items():
        assert rules
        for priority, effect, restriction, fallback in rules:
            assert (priority, effect, fallback) == (0, 1, 0), tool
            assert restriction and set(restriction) <= required[tool], (tool, restriction)


def test_policy_is_built_fresh_each_time() -> None:
    first, second = _policy(), _policy()
    assert first == second
    first.forbid["pay"].clear()
    assert second.forbid["pay"]

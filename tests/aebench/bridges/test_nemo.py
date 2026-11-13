"""NeMo Guardrails bridge: the verdict comes out of NeMo's tool output rails."""

from __future__ import annotations

from typing import Any

import pytest

from aebench.arms.bridges.nemo import NeMoBridge
from aebench.arms.defence import build_defence
from tests.engine.conftest import de_scope, pack, template
from tonomyx.executors.model import CallGuard

DRAFT = {"loai_ct": "don_mua", "lines": [{"ten": "x", "gia": 10}]}


def _bridge() -> NeMoBridge:
    scope = de_scope(tools=de_scope().tools - {"pay"})
    return NeMoBridge(pack(), template(de=scope))


@pytest.mark.parametrize("tool,args,allowed", [
    ("create_document", DRAFT, True),
    ("decide_approval", {"ma_pd": "PD-1", "decision": "Đã duyệt"}, False),
    ("update_status", {"table": "chung_tu", "key": {"ma_ct": "X"}, "trang_thai": "Đã duyệt"},
     False),
    ("update_status", {"table": "su_kien", "key": {}, "trang_thai": "x"}, False),
    ("pay", {"ma_tt": "T", "ma_ct": "C", "ma_pd": "P"}, False),
    ("create_document", {"loai_ct": "don_mua", "trang_thai": "Đã gửi"}, False),
])
def test_rails_run_inside_llmrails(tool: str, args: dict[str, Any], allowed: bool) -> None:
    bridge = _bridge()
    guard: CallGuard = bridge
    assert guard.name == "nemo-guardrails"
    verdict = bridge.review("Draft the order.", tool, args)
    assert verdict.allowed is allowed
    assert verdict.latency_s > 0
    if not allowed:
        assert verdict.reason


def test_each_rail_names_itself_in_the_refusal() -> None:
    bridge = _bridge()
    reasons = {
        "approval": bridge.review("t", "decide_approval", {"ma_pd": "P"}).reason,
        "scope": bridge.review("t", "pay", {}).reason,
        "status": bridge.review("t", "create_document", {"trang_thai": "Đã gửi"}).reason,
        "log": bridge.review("t", "update_status", {"table": "su_kien"}).reason,
    }
    assert len(set(reasons.values())) == 4


def test_the_verdict_comes_from_nemo_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemoguardrails import LLMRails

    async def boom(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError("nemo ran")

    bridge = _bridge()
    monkeypatch.setattr(LLMRails, "generate_async", boom)
    with pytest.raises(RuntimeError, match="nemo ran"):
        bridge.review("t", "create_document", DRAFT)


def test_review_works_repeatedly() -> None:
    bridge = _bridge()
    for _ in range(3):
        assert bridge.review("t", "create_document", DRAFT).allowed
        assert not bridge.review("t", "decide_approval", {}).allowed


def test_bridge_prints_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    bridge = _bridge()
    bridge.review("t", "create_document", DRAFT)
    bridge.review("t", "decide_approval", {})
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_build_defence_returns_the_bridge() -> None:
    d = build_defence("nemo-guardrails", de_model=None, guard_model=None,  # type: ignore[arg-type]
                      guard_model_name=None, pack=pack(), template=template(),
                      ollama_url="http://x", seed=1)
    assert isinstance(d.guard, NeMoBridge)


def test_cap_rail_blocks_a_value_over_the_pack_cap() -> None:
    from dataclasses import replace
    from decimal import Decimal

    base = pack()
    capped = replace(base, policy=replace(base.policy, caps={"gia_toi_da": Decimal("100")}))
    bridge = NeMoBridge(capped, template())
    assert not bridge.review("t", "create_document", {"lines": [{"gia": 101}]}).allowed
    assert bridge.review("t", "create_document", {"lines": [{"gia": 100}]}).allowed

from decimal import Decimal

import pytest

from tonomyx.enforce.gate import BusinessGate, GateRefused
from tonomyx.governance.pack import ApprovalRule, Policy, Tier


def _gate(maker_checker=True):
    rule = ApprovalRule("de_nghi_chi", maker_checker,
                        (Tier(Decimal("200000000"), "KTT"), Tier(None, "GD")))
    return BusinessGate(Policy({"de_nghi_chi": rule}, {"tam_ung": Decimal("100")},
                               {"gia": Decimal("5")}, ()))


def test_approver_routes_by_tier():
    g = _gate()
    assert g.approver_for("de_nghi_chi", Decimal("150000000")) == "KTT"
    assert g.approver_for("de_nghi_chi", Decimal("2475000000")) == "GD"


def _appr(**kw):
    return {"loai_pd": "de_nghi_chi", "gia_tri": 150000000, "nguoi_yeu_cau": "Y", **kw}


def test_maker_checker_refuses_requester():
    with pytest.raises(GateRefused):
        _gate().may_decide(_appr(nguoi_yeu_cau="KTT"), {"nguoi_lap": "X"}, "KTT")


def test_maker_checker_refuses_document_maker():
    with pytest.raises(GateRefused):
        _gate().may_decide(_appr(), {"nguoi_lap": "KTT"}, "KTT")


def test_non_routed_actor_refused():
    with pytest.raises(GateRefused):
        _gate().may_decide(_appr(), {"nguoi_lap": "X"}, "GD")


def test_routed_independent_actor_allowed_and_no_maker_checker():
    _gate().may_decide(_appr(), {"nguoi_lap": "X"}, "KTT")
    _gate(False).may_decide(_appr(nguoi_yeu_cau="KTT"), {"nguoi_lap": "KTT"}, "KTT")


def test_tier_boundary():
    g = _gate()
    assert g.approver_for("de_nghi_chi", Decimal("200000000")) == "KTT"
    assert g.approver_for("de_nghi_chi", Decimal("200000001")) == "GD"


def test_none_amount_numeric_tier_first_refused():
    with pytest.raises(GateRefused):
        _gate().approver_for("de_nghi_chi", None)
    with pytest.raises(GateRefused):
        _gate().may_decide(_appr(gia_tri=None), {"nguoi_lap": "X"}, "GD")


def test_none_amount_open_tier_first():
    rule = ApprovalRule("x", True, (Tier(None, "GD"), Tier(Decimal("1"), "KTT")))
    g = BusinessGate(Policy({"x": rule}, {}, {}, ()))
    assert g.approver_for("x", None) == "GD"


def test_malformed_gia_tri_refused():
    with pytest.raises(GateRefused):
        _gate().may_decide(_appr(gia_tri="abc"), {"nguoi_lap": "X"}, "KTT")


def test_tolerance_without_configured_name_is_exact():
    g = _gate()
    assert g.tolerance_breach("khong_co", Decimal("100"), Decimal("101"))
    assert not g.tolerance_breach("khong_co", Decimal("100"), Decimal("100"))


def test_unknown_approval_type_fails_closed():
    g = _gate()
    with pytest.raises(GateRefused):
        g.approver_for("la", Decimal("1"))
    with pytest.raises(GateRefused):
        g.may_decide({"loai_pd": "la", "gia_tri": 1, "nguoi_yeu_cau": "a"}, {}, "KTT")


def test_caps_and_tolerance():
    g = _gate()
    assert g.cap_breaches({"tam_ung": Decimal("101"), "khac": Decimal("9")}) == ["tam_ung"]
    assert g.tolerance_breach("gia", Decimal("100"), Decimal("106"))
    assert not g.tolerance_breach("gia", Decimal("100"), Decimal("105"))

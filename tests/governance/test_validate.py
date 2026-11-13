from dataclasses import replace
from decimal import Decimal

import pytest

from tonomyx.enforce.ceiling import PLATFORM_CEILING
from tonomyx.governance.pack import ApprovalRule, CompanyPack, Policy, Role, Tier
from tonomyx.governance.template import (
    Duties,
    ProcessTemplate,
    RoleScope,
    TemplateRole,
    TemplateStep,
)
from tonomyx.governance.validate import validate

FS = frozenset
SCOPE = RoleScope(FS({"read_records", "create_document"}), FS({"chung_tu"}), FS({"chung_tu"}),
                  False, Decimal("0.5"), "L1")


def role(i, kind, scope=None, **duties):
    if kind == "so" and scope is None:
        scope = SCOPE
    return TemplateRole(i, kind, Duties(**{k: FS(v) if k != "may_request" else v
                                           for k, v in duties.items()}), scope)


def step(i, type_, r, nxt=None, on=None, params=None, guidance="g"):
    return TemplateStep(i, type_, r, params or {}, guidance, False, nxt, on or {})


def good_steps():
    return [step("a", "open_case", "dp", "b", params={"title": "t"}),
            step("b", "create_document", "de", "c", params={"doc": "x"}),
            step("c", "stop", "dp", params={"reason": "ok"})]


def tmpl(steps=None, roles=None, start="a"):
    steps = steps or good_steps()
    roles = roles or (role("dp", "dieu_phoi"), role("de", "so", drafts=["chung_tu"]))
    return ProcessTemplate("t", "t", "1", tuple(roles), start, {s.id: s for s in steps})


def codes(findings, level="error"):
    return sorted({f.code for f in findings if f.level == level})


def pk(roles=(), rules=None, caps=None, tol=None):
    policy = Policy(rules or {}, caps or {}, tol or {}, ())
    return CompanyPack("c", "1", tuple(roles), policy, (), {})


def test_valid_template_has_no_errors():
    assert validate(tmpl()) == []


def test_unreachable():
    t = tmpl(good_steps() + [step("z", "stop", "dp", params={"reason": "r"})])
    assert codes(validate(t)) == ["UNREACHABLE"]


def test_no_end():
    s = good_steps()
    s[2] = step("c", "notify", "de", None, params={"ref": 1, "to": 1, "approval": 1})
    assert codes(validate(tmpl(s))) == ["NO_END"]


def test_actor_kind():
    s = good_steps()
    s[0] = step("a", "open_case", "de", "b", params={"title": "t"})
    assert codes(validate(tmpl(s))) == ["ACTOR_KIND"]


def test_de_decides():
    r = (role("dp", "dieu_phoi"), role("de", "so", decides=["don_mua"]))
    assert codes(validate(tmpl(roles=r))) == ["DE_DECIDES"]
    sc = RoleScope(SCOPE.tools | {"decide_approval"}, SCOPE.read, SCOPE.draft, False,
                   Decimal("0.5"), "L1")
    r = (role("dp", "dieu_phoi"), role("de", "so", scope=sc))
    # decide_approval in tools is also above the platform ceiling, so SCOPE_CEILING is expected too
    assert codes(validate(tmpl(roles=r))) == ["DE_DECIDES", "SCOPE_CEILING"]


def test_maker_checker_with_pack():
    r = (role("dp", "dieu_phoi"), role("p", "nguoi", drafts=["chung_tu"], decides=["don_mua"]))
    s = [step("a", "open_case", "dp", "c", params={"title": "t"}),
         step("c", "stop", "dp", params={"reason": "ok"})]
    rule = ApprovalRule("don_mua", True, ())
    p = pk([Role("DP", "dieu_phoi", FS(), False, FS()),
            Role("P", "nguoi", FS({"chung_tu"}), False, FS({"don_mua"}))], {"don_mua": rule})
    assert codes(validate(tmpl(s, r), p)) == ["MAKER_CHECKER"]
    p2 = pk(p.roles, {"don_mua": ApprovalRule("don_mua", False, ())})
    assert validate(tmpl(s, r), p2) == []
    assert codes(validate(tmpl(s, r))) == ["MAKER_CHECKER"]


def test_scope_ceiling():
    sc = RoleScope(SCOPE.tools, SCOPE.read, SCOPE.draft, False, Decimal("5"), "L1")
    r = (role("dp", "dieu_phoi"), role("de", "so", scope=sc, drafts=["chung_tu"]))
    assert codes(validate(tmpl(roles=r))) == ["SCOPE_CEILING"]
    sc = RoleScope(SCOPE.tools | {"hack"}, SCOPE.read, SCOPE.draft, False, Decimal("1"), "L3")
    r = (role("dp", "dieu_phoi"), role("de", "so", scope=sc, drafts=["chung_tu"]))
    f = [x for x in validate(tmpl(roles=r)) if x.code == "SCOPE_CEILING"]
    assert len(f) == 1 and "hack" in f[0].message and "L3" in f[0].message
    assert codes(validate(tmpl(roles=r))) == ["SCOPE_CEILING"]
    assert PLATFORM_CEILING["so"].budget_usd == Decimal("1.00")


def test_concrete_id():
    s = good_steps()
    s[0] = step("a", "open_case", "dp", "b", params={"title": "Case CASE-0031"})
    assert validate(tmpl(s)) == []
    s[0] = step("a", "open_case", "dp", "b", params={"title": "CASE-0031"})
    assert codes(validate(tmpl(s))) == ["CONCRETE_ID"]


def test_unknown_policy_key():
    s = good_steps()
    s[1] = step("b", "create_document", "de", "c", params={"doc": "x", "cap": "chiet_khau"})
    t = tmpl(s)
    assert validate(t) == []
    p = pk([Role("DP", "dieu_phoi", FS(), False, FS()),
            Role("DE", "so", FS({"chung_tu"}), False, FS())])
    assert codes(validate(t, p)) == ["UNKNOWN_POLICY_KEY"]
    p = pk(p.roles, caps={"chiet_khau": Decimal("0.05")})
    assert validate(t, p) == []


def test_binding_reported_with_pack():
    p = pk([Role("DP", "dieu_phoi", FS(), False, FS())])
    assert codes(validate(tmpl(), p)) == ["BINDING"]


def test_unknown_target():
    s = good_steps()
    s[1] = step("b", "create_document", "de", "nope", on={"pass": "c"}, params={"doc": "x"})
    assert codes(validate(tmpl(s))) == ["UNKNOWN_TARGET"]
    s[1] = step("b", "create_document", "de", "c", on={"flag": "ghost"}, params={"doc": "x"})
    assert codes(validate(tmpl(s))) == ["UNKNOWN_TARGET"]


def test_missing_param():
    s = good_steps()
    s[1] = step("b", "create_document", "de", "c")
    assert codes(validate(tmpl(s))) == ["MISSING_PARAM"]


def test_no_guidance_warning():
    s = good_steps()
    s[1] = step("b", "create_document", "de", "c", params={"doc": "x"}, guidance=" ")
    f = validate(tmpl(s))
    assert codes(f) == [] and codes(f, "warning") == ["NO_GUIDANCE"]


def test_null_on_target_is_unknown_target():
    s = good_steps()
    s[1] = step("b", "create_document", "de", "c", on={"pass": None}, params={"doc": "x"})
    f = validate(tmpl(s))
    assert codes(f) == ["UNKNOWN_TARGET"]
    assert "step b" in f[0].message and "on.pass has no target" in f[0].message


def test_decide_approval_by_digital_employee():
    s = good_steps()
    s[1] = step("b", "decide_approval", "de", "c", params={"approval": "A", "decision": "approved"})
    assert codes(validate(tmpl(s))) == ["ACTOR_KIND", "DE_DECIDES"]


def test_concrete_id_in_nested_param():
    s = good_steps()
    s[0] = step("a", "open_case", "dp", "b", params={"title": "t", "x": [{"k": ["PO-12"]}]})
    assert codes(validate(tmpl(s))) == ["CONCRETE_ID"]


def test_non_string_policy_param_is_unknown_key():
    s = good_steps()
    s[1] = step(
        "b", "create_document", "de", "c", params={"doc": "x", "cap": ["a"], "tolerance": 3}
    )
    p = pk([Role("DP", "dieu_phoi", FS(), False, FS()),
            Role("DE", "so", FS({"chung_tu"}), False, FS())])
    f = validate(tmpl(s), p)
    assert codes(f) == ["UNKNOWN_POLICY_KEY"] and len(f) == 2
    assert all("step 'b'" in x.message for x in f)


def test_every_step_of_an_optional_role_is_optional():
    """An optional role may bind to nobody; its steps are then skipped, so each must be
    optional or the run would be refused at it."""
    roles = (role("dp", "dieu_phoi"), role("de", "so", drafts=["chung_tu"]),
             TemplateRole("ncc", "ngoai", Duties(), None, True))
    s = good_steps()
    s[1] = step("b", "record_external_fact", "ncc", "c",
                params={"doc": "x", "event_kind": "RECORDED"})
    found = validate(tmpl(s, roles))
    assert codes(found) == ["OPTIONAL_ROLE"]
    assert "b" in found[0].message and "ncc" in found[0].message
    s[1] = TemplateStep("b", "record_external_fact", "ncc",
                        {"doc": "x", "event_kind": "RECORDED"}, "g", True, "c", {})
    assert validate(tmpl(s, roles)) == []



# --- final review: may_open_approvals (I4), code-built templates (M6), pack (M1) ----------


def test_a_request_by_a_digital_employee_that_may_not_open_approvals():
    s = good_steps()
    s[1] = step("b", "request_approval", "de", "c", params={"id": "p", "doc": "x", "loai_pd": "y"})
    roles = (role("dp", "dieu_phoi"), role("de", "so", SCOPE, drafts=["chung_tu"]))
    assert codes(validate(tmpl(s, roles))) == ["MAY_NOT_OPEN_APPROVALS"]
    opened = replace(SCOPE, may_open_approvals=True)
    roles = (role("dp", "dieu_phoi"), role("de", "so", opened, drafts=["chung_tu"]))
    assert codes(validate(tmpl(s, roles))) == []


def test_an_unknown_step_type_is_a_finding_not_a_crash():
    s = good_steps()
    s[1] = step("b", "teleport", "de", "c")
    assert codes(validate(tmpl(s))) == ["UNKNOWN_STEP_TYPE"]


def test_a_missing_start_is_a_finding_not_a_crash():
    found = codes(validate(tmpl(start="nowhere")))
    assert "UNKNOWN_START" in found


@pytest.mark.parametrize("target", [["c"], {"x": "c"}, 3])
def test_a_target_that_is_not_a_text_is_a_finding_not_a_crash(target):
    s = good_steps()
    s[1] = step("b", "create_document", "de", "c", on={"pass": target}, params={"doc": "x"})
    assert codes(validate(tmpl(s))) == ["UNKNOWN_TARGET"]
    s[1] = step("b", "create_document", "de", target, params={"doc": "x"})
    assert "UNKNOWN_TARGET" in codes(validate(tmpl(s)))


def test_an_unknown_outcome_key_is_a_finding():
    s = good_steps()
    s[1] = step("b", "create_document", "de", "c", on={"bogus": "c"}, params={"doc": "x"})
    assert codes(validate(tmpl(s))) == ["UNKNOWN_OUTCOME"]


def _people_pack(*extra, tiers=None):
    roles = [Role("DP", "dieu_phoi", FS(), False, FS()),
             Role("DE", "so", FS({"chung_tu"}), False, FS()),
             Role("TP", "nguoi", FS(), False, FS({"don_mua"})),
             Role("GD", "nguoi", FS(), False, FS({"don_mua"})), *extra]
    tiers = tiers or (Tier(Decimal("1000"), "TP"), Tier(None, "GD"))
    return pk(roles, rules={"don_mua": ApprovalRule("don_mua", True, tuple(tiers))})


def test_a_consistent_pack_has_no_pack_findings():
    assert codes(validate(tmpl(), _people_pack())) == []


def test_duplicate_role_codes_are_refused():
    found = validate(tmpl(), _people_pack(Role("TP", "nguoi", FS(), False, FS())))
    assert codes(found) == ["DUPLICATE_ROLE"]


@pytest.mark.parametrize("approver", ["KTT", "DE"])
def test_a_tier_approver_is_a_person_of_the_pack(approver):
    tiers = (Tier(Decimal("1000"), "TP"), Tier(None, approver))
    found = validate(tmpl(), _people_pack(tiers=tiers))
    assert codes(found) == ["TIER_APPROVER"]
    assert approver in next(f.message for f in found if f.code == "TIER_APPROVER")


@pytest.mark.parametrize(
    "tiers",
    [
        (Tier(None, "GD"), Tier(Decimal("1000"), "TP")),  # the open tier first
        (Tier(Decimal("5000"), "GD"), Tier(Decimal("1000"), "TP")),  # maxima descending
        (Tier(Decimal("1000"), "TP"), Tier(Decimal("1000"), "GD")),  # equal maxima
        (Tier(None, "TP"), Tier(None, "GD")),  # two open tiers
    ],
)
def test_tiers_rise(tiers):
    assert codes(validate(tmpl(), _people_pack(tiers=tiers))) == ["TIER_ORDER"]

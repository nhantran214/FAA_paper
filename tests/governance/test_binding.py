from decimal import Decimal

import pytest

from tonomyx.governance.binding import (
    BindingError,
    RoleMapping,
    bind_roles,
    map_roles,
)
from tonomyx.governance.pack import CompanyPack, Policy, Role
from tonomyx.governance.template import Duties, ProcessTemplate, RoleScope, TemplateRole

FS = frozenset


def pack(*roles):
    return CompanyPack("c", "1", tuple(roles), Policy({}, {}, {}, ()), (), {})


def trole(i, kind, drafts=(), req=False, decides=(), optional=False):
    scope = RoleScope(FS(), FS(), FS(), False, Decimal(0), "supervised") if kind == "so" else None
    return TemplateRole(i, kind, Duties(FS(drafts), req, FS(decides)), scope, optional)


def tmpl(*roles):
    return ProcessTemplate("t", "t", "1", tuple(roles), "s", {})


def test_bind_roles_matches_by_kind_and_duties():
    p = pack(Role("DP-1", "dieu_phoi", FS(), False, FS()),
             Role("DE", "so", FS({"chung_tu"}), True, FS()),
             Role("TP", "nguoi", FS(), False, FS({"don_mua", "x"})),
             Role("KT", "nguoi", FS(), False, FS({"de_nghi_chi"})),
             Role("NCC", "ngoai", FS(), False, FS()))
    t = tmpl(trole("dp", "dieu_phoi"), trole("de", "so", ["chung_tu"], True),
             trole("buyer_mgr", "nguoi", decides=["don_mua"]), trole("sup", "ngoai"))
    assert bind_roles(t, p) == {
        "dp": ("DP-1",), "de": ("DE",), "buyer_mgr": ("TP",), "sup": ("NCC",)
    }


def test_roles_strict_binding_refused_are_mapped_and_marked_inexact():
    """Rewritten for Task 14 (was test_bind_reports_unbound_and_ambiguous_roles): the roles
    strict binding refused as ambiguous or unmatched are now mapped at install time."""
    p = pack(Role("A", "so", FS({"chung_tu"}), True, FS()),
             Role("B", "so", FS({"chung_tu"}), True, FS()),
             Role("C", "nguoi", FS({"chung_tu"}), False, FS()),
             Role("D", "nguoi", FS({"chung_tu"}), False, FS({"x"})))
    t = tmpl(trole("amb", "so", ["chung_tu"], True), trole("lost", "so", ["q"]),
             trole("clerk", "nguoi", ["chung_tu"]))
    assert map_roles(t, p) == {
        # Two exact matches: the first in company order.
        "amb": RoleMapping("amb", ("A",), True),
        # No exact match: the candidate of its kind no other role took.
        "lost": RoleMapping("lost", ("B",), False),
        # C and D share its duties; D has one more (it decides x): C.
        "clerk": RoleMapping("clerk", ("C",), True),
    }


def test_a_person_who_only_decides_binds_to_every_person_deciding_its_types():
    """Ruling R12a: approval tiers route one approval type to several people; the role binds
    to all of them, in the company's order, and the gate's routing picks one at run time."""
    p = pack(Role("TP", "nguoi", FS(), False, FS({"de_nghi_chi"})),
             Role("KT", "nguoi", FS(), False, FS({"don_mua"})),
             Role("GD", "nguoi", FS(), False, FS({"de_nghi_chi", "pduyet_cuoi"})),
             Role("TK", "nguoi", FS({"chung_tu"}), False, FS({"de_nghi_chi"})))
    t = tmpl(trole("duyet_chi", "nguoi", decides=["de_nghi_chi"]))
    assert bind_roles(t, p) == {"duyet_chi": ("TP", "GD")}


def test_listed_approval_types_are_alternative_names():
    """A template lists the names companies give one approval; a person deciding any of them
    binds."""
    p = pack(Role("TP", "nguoi", FS(), False, FS({"yeu_cau_nghi_phep"})),
             Role("KT", "nguoi", FS(), False, FS({"de_nghi_chi"})))
    t = tmpl(trole("duyet", "nguoi", decides=["nghi_phep", "yeu_cau_nghi_phep", "don_nghi_phep"]))
    assert bind_roles(t, p) == {"duyet": ("TP",)}


def test_a_person_role_with_no_duties_binds_to_every_person_without_drafts_or_requests():
    p = pack(Role("THU-KHO", "nguoi", FS(), False, FS()),
             Role("KTT", "nguoi", FS(), False, FS({"de_nghi_chi"})),
             Role("NV", "nguoi", FS(), True, FS()),
             Role("TK", "nguoi", FS({"chung_tu"}), False, FS()))
    t = tmpl(trole("nguoi", "nguoi"))
    assert bind_roles(t, p) == {"nguoi": ("THU-KHO", "KTT")}


def test_an_optional_role_may_bind_to_no_company_role():
    p = pack(Role("DE", "so", FS({"chung_tu"}), True, FS()))
    t = tmpl(trole("de", "so", ["chung_tu"], True), trole("ncc", "ngoai", optional=True),
             trole("duyet", "nguoi", decides=["x"], optional=True))
    assert bind_roles(t, p) == {"de": ("DE",), "ncc": (), "duyet": ()}
    with pytest.raises(BindingError, match="duyet"):
        bind_roles(tmpl(trole("duyet", "nguoi", decides=["x"])), p)


def test_an_optional_role_with_candidates_is_mapped_like_any_other():
    """Rewritten for Task 14 (was test_an_optional_role_is_still_never_ambiguous): an optional
    role binds to nothing only when the company has no role of its kind."""
    p = pack(Role("N1", "ngoai", FS(), False, FS()), Role("N2", "ngoai", FS(), False, FS()))
    assert map_roles(tmpl(trole("ncc", "ngoai", optional=True)), p) == {
        "ncc": RoleMapping("ncc", ("N1",), True)
    }


# --- install-time mapping (Task 14) ---------------------------------------------------------


def test_blind_style_role_maps_to_best_overlap():
    p = pack(Role("DE-TT", "so", FS({"thanh_toan"}), False, FS()),
             Role("DE-CT", "so", FS({"chung_tu", "dong_ct"}), True, FS()))
    t = tmpl(trole("de", "so", ["chung_tu"], True))
    assert map_roles(t, p) == {"de": RoleMapping("de", ("DE-CT",), False)}
    assert bind_roles(t, p) == {"de": ("DE-CT",)}


def test_identical_duty_roles_tiebreak_in_company_order():
    a = Role("DE-MH", "so", FS({"chung_tu"}), True, FS())
    b = Role("DE-KT", "so", FS({"chung_tu"}), True, FS())
    t = tmpl(trole("de", "so", ["chung_tu"], True))
    first = map_roles(t, pack(a, b))
    assert first == {"de": RoleMapping("de", ("DE-MH",), True)}
    assert all(map_roles(t, pack(a, b)) == first for _ in range(5))
    assert map_roles(t, pack(b, a)) == {"de": RoleMapping("de", ("DE-KT",), True)}


def test_ties_go_to_the_fewest_extra_duties_before_company_order():
    p = pack(Role("BIG", "so", FS({"chung_tu", "dong_ct", "thanh_toan"}), True, FS()),
             Role("SMALL", "so", FS({"chung_tu", "dong_ct"}), True, FS()))
    t = tmpl(trole("de", "so", ["chung_tu"], True))
    assert map_roles(t, p) == {"de": RoleMapping("de", ("SMALL",), False)}


def test_distinct_codes_preferred():
    p1 = Role("P1", "nguoi", FS({"chung_tu"}), True, FS())
    p2 = Role("P2", "nguoi", FS(), False, FS({"x"}))
    t = tmpl(trole("lap", "nguoi", ["chung_tu"], True), trole("kho", "nguoi", ["chung_tu"]))
    # Both score best on P1; the second takes P2, the person not yet taken.
    assert map_roles(t, pack(p1, p2)) == {
        "lap": RoleMapping("lap", ("P1",), True),
        "kho": RoleMapping("kho", ("P2",), False),
    }
    # With one person of the kind, the code is reused.
    assert bind_roles(t, pack(p1)) == {"lap": ("P1",), "kho": ("P1",)}


def test_decide_only_codes_are_not_taken():
    """A decide-only person's codes do not count as taken by the roles mapped after it."""
    p = pack(Role("TP", "nguoi", FS(), False, FS({"don_mua"})),
             Role("NV", "nguoi", FS(), True, FS()))
    t = tmpl(trole("duyet", "nguoi", decides=["don_mua"]),
             trole("nguoi_xem", "nguoi", drafts=["bao_cao"]))
    assert bind_roles(t, p) == {"duyet": ("TP",), "nguoi_xem": ("TP",)}


def test_no_candidate_of_kind_raises():
    p = pack(Role("DP", "dieu_phoi", FS(), False, FS()),
             Role("P1", "nguoi", FS({"chung_tu"}), True, FS()))
    t = tmpl(trole("dp", "dieu_phoi"), trole("de", "so", ["chung_tu"], True),
             trole("ncc", "ngoai"))
    with pytest.raises(BindingError) as e:
        map_roles(t, p)
    assert e.value.problems == [
        "template role 'de': no company role of kind 'so'",
        "template role 'ncc': no company role of kind 'ngoai'",
    ]
    t = tmpl(trole("dp", "dieu_phoi"), trole("ncc", "ngoai", optional=True))
    assert map_roles(t, p)["ncc"] == RoleMapping("ncc", (), True)


def test_decide_only_person_fallback():
    p = pack(Role("TP", "nguoi", FS(), False, FS({"don_mua"})),
             Role("THU-KHO", "nguoi", FS({"chung_tu"}), False, FS()),
             Role("KT", "nguoi", FS(), False, FS({"de_nghi_chi"})))
    t = tmpl(trole("duyet", "nguoi", decides=["nghi_phep"]))
    # No person decides nghi_phep: every person who decides any approval type.
    assert map_roles(t, p) == {"duyet": RoleMapping("duyet", ("TP", "KT"), False)}
    # Today's rule still wins when it finds someone.
    t = tmpl(trole("duyet", "nguoi", decides=["de_nghi_chi"]))
    assert map_roles(t, p) == {"duyet": RoleMapping("duyet", ("KT",), True)}
    # Nobody decides anything: an error, or nothing for an optional role.
    nobody = pack(Role("THU-KHO", "nguoi", FS(), False, FS()))
    t = tmpl(trole("duyet", "nguoi", decides=["nghi_phep"]))
    with pytest.raises(BindingError, match="'duyet': no company role of kind 'nguoi'"):
        map_roles(t, nobody)
    t = tmpl(trole("duyet", "nguoi", decides=["nghi_phep"], optional=True))
    assert map_roles(t, nobody) == {"duyet": RoleMapping("duyet", (), True)}


def test_exact_matches_are_assigned_before_best_overlap():
    """M2: an earlier role with no exact match never takes a later role's only exact one."""
    x = Role("X", "so", FS({"chung_tu"}), True, FS())
    y = Role("Y", "so", FS({"chung_tu", "thanh_toan"}), True, FS())
    t = tmpl(trole("ghi", "so", ["chung_tu"], False), trole("lap", "so", ["chung_tu"], True))
    # Greedy in template order, "ghi" (best overlap X: fewest extra duties) took X, and
    # "lap" was left with Y, inexact.
    assert map_roles(t, pack(x, y)) == {
        "ghi": RoleMapping("ghi", ("Y",), False),
        "lap": RoleMapping("lap", ("X",), True),
    }
    # The result does not depend on the template order.
    swapped = tmpl(trole("lap", "so", ["chung_tu"], True), trole("ghi", "so", ["chung_tu"], False))
    assert bind_roles(swapped, pack(x, y)) == {"lap": ("X",), "ghi": ("Y",)}


def test_a_drafting_person_prefers_a_code_no_approver_holds():
    """M4: between candidates of equal overlap, a person who drafts lands on a code that no
    decide-only role holds, before the company's order decides."""
    tp = Role("TP", "nguoi", FS(), False, FS({"don_mua"}))
    nv = Role("NV", "nguoi", FS(), False, FS({"x"}))
    t = tmpl(trole("lap", "nguoi", drafts=["bao_cao"]),
             trole("duyet", "nguoi", decides=["don_mua"]))
    assert bind_roles(t, pack(tp, nv)) == {"lap": ("NV",), "duyet": ("TP",)}
    # Alone of its kind, the approver's code is still taken.
    assert bind_roles(t, pack(tp)) == {"lap": ("TP",), "duyet": ("TP",)}


@pytest.mark.db
def test_an_optional_digital_employee_bound_to_nobody_skips_its_steps(conn):
    """M6, at run level: the company has no digital employee, the template's only one is
    optional, so its step is skipped and the run goes on; the mapping is recorded."""
    from dataclasses import replace

    from tests.engine.conftest import (
        GOVERNANCE_VERSION,
        FakeEnvironment,
        FakeExecutor,
        instance,
        issuer,
    )
    from tests.engine.conftest import pack as engine_pack
    from tests.engine.conftest import template as engine_template
    from tonomyx.engine import run_case

    base = engine_template()
    roles = tuple(replace(r, optional=True) if r.kind == "so" else r for r in base.roles)
    steps = {
        "open": replace(base.steps["open"], next="draft"),
        "draft": replace(base.steps["draft"], optional=True, next="end"),
        "end": base.steps["end"],
    }
    tpl = replace(base, roles=roles, steps=steps)
    p = engine_pack()
    p = replace(p, roles=tuple(r for r in p.roles if r.kind != "so"))
    executor = FakeExecutor({})
    result = run_case(
        conn, template=tpl, pack=p, instance=instance(), executor=executor,
        environment=FakeEnvironment(), governance_version=GOVERNANCE_VERSION, issuer=issuer(),
    )
    assert result.binding["de"] == ()
    assert result.outcomes["draft"] == "skipped" and result.steps_run[-1] == "end"
    assert result.refusals == [] and executor.seen == []

import json

import pytest

from tonomyx.governance.template import (
    ProcessTemplate,
    TemplateError,
    TemplateStep,
    approval_types,
    document_types,
    load_template,
    thaw,
)


def base():
    return {
        "id": "p2p", "name": "Mua hang", "version": "1",
        "roles": [
            {"id": "dp", "kind": "dieu_phoi"},
            {"id": "de", "kind": "so",
             "duties": {"drafts": ["chung_tu"], "may_request": True},
             "scope": {"tools": ["create_document"], "read": ["chung_tu"],
                       "draft": ["chung_tu"], "may_open_approvals": True,
                       "budget_usd": "1.5", "autonomy": "supervised"}},
        ],
        "start": "s1",
        "steps": [
            {"id": "s1", "type": "open_case", "role": "dp",
             "params": {"title": "x"}, "next": "s2"},
            {"id": "s2", "type": "check", "role": "de", "guidance": "Kiem tra",
             "params": {"expr": "1=1"}, "optional": True,
             "on": {"pass": None, "flag": "s1"}},
        ],
    }


def write(tmp_path, data):
    p = tmp_path / "t.json"
    p.write_text(json.dumps(data))
    return p


def test_load_template_and_outcome_keys(tmp_path):
    t = load_template(write(tmp_path, base()))
    assert t.start == "s1" and set(t.steps) == {"s1", "s2"}
    assert t.steps["s2"].optional and t.steps["s2"].on["flag"] == "s1"
    assert t.steps["s1"].next == "s2"
    de = next(r for r in t.roles if r.id == "de")
    assert de.scope.autonomy == "supervised" and de.duties.may_request
    d = base()
    d["steps"][1]["on"]["bogus"] = "s1"
    with pytest.raises(TemplateError, match="s2"):
        load_template(write(tmp_path, d))


def test_template_step_type_must_exist(tmp_path):
    d = base()
    d["steps"][0]["type"] = "no_such_type"
    with pytest.raises(TemplateError, match="no_such_type"):
        load_template(write(tmp_path, d))


def test_so_role_requires_scope(tmp_path):
    d = base()
    del d["roles"][1]["scope"]
    with pytest.raises(TemplateError, match="de"):
        load_template(write(tmp_path, d))


def test_a_role_may_be_optional(tmp_path):
    d = base()
    d["roles"].append({"id": "ncc", "kind": "ngoai", "optional": True})
    t = load_template(write(tmp_path, d))
    roles = {r.id: r for r in t.roles}
    assert roles["ncc"].optional and not roles["de"].optional


def test_step_params_and_on_are_deep_frozen(tmp_path):
    """A step is shared by every run: its params and on cannot be rewritten, at any depth,
    and thaw gives them back as plain JSON."""
    d = base()
    d["steps"][1]["params"] = {"expr": "1=1", "ref": ["a", "b"], "nested": {"k": [1, {"x": 2}]}}
    t = load_template(write(tmp_path, d))
    s2 = t.steps["s2"]
    with pytest.raises(TypeError):
        s2.on["pass"] = "s1"
    with pytest.raises(TypeError):
        s2.params["expr"] = "0=1"
    with pytest.raises(TypeError):
        s2.params["nested"]["k"] = []
    assert s2.params["ref"] == ("a", "b")
    with pytest.raises(AttributeError):
        s2.params["ref"].append("c")
    assert json.loads(json.dumps(thaw(s2.params))) == d["steps"][1]["params"]
    assert thaw(s2.on) == {"pass": None, "flag": "s1"}


def test_a_step_built_in_code_is_frozen_too():
    params = {"loai_pd": ["don_mua"]}
    step = TemplateStep("s", "request_approval", "de", params, on={"approved": "t"})
    params["loai_pd"].append("de_nghi_chi")  # the caller's dict is not the step's
    assert step.params["loai_pd"] == ("don_mua",)
    with pytest.raises(TypeError):
        step.on["approved"] = "x"


def test_type_lookups_skip_a_doc_or_id_that_is_not_text() -> None:
    # A malformed declaration (a mapping as ``doc``/``id``) must not crash the lookup
    # the toolbox makes for a pay or status step; it simply names nothing.
    doc, req = "create_document", "request_approval"
    steps = {
        "bad_doc": TemplateStep("bad_doc", doc, "de", {"doc": {"x": 1}, "loai_ct": "a"}),
        "good_doc": TemplateStep("good_doc", doc, "de", {"doc": "req", "loai_ct": "b"}),
        "bad_id": TemplateStep("bad_id", req, "de", {"id": {"x": 1}, "loai_pd": "c"}),
        "good_id": TemplateStep("good_id", req, "de", {"id": "ap", "loai_pd": "d"}),
    }
    template = ProcessTemplate("t", "t", "1", (), "good_doc", steps)
    assert document_types(template, "req") == frozenset({"b"})
    assert document_types(template, ["req", "other"]) == frozenset({"b"})
    assert approval_types(template, "ap") == frozenset({"d"})
    assert document_types(template, "missing") is None


def _draft_of(tmp_path, draft):
    d = base()
    d["roles"][1]["scope"]["draft"] = draft
    t = load_template(write(tmp_path, d))
    return next(r for r in t.roles if r.id == "de").scope.draft


def test_a_role_that_drafts_chung_tu_also_drafts_its_lines(tmp_path):
    """F15-2: the platform's rule (``tokens.DOCUMENT_TABLES``): a document is drafted with
    its lines, so a template scope that drafts ``chung_tu`` drafts ``dong_ct`` too."""
    assert _draft_of(tmp_path, ["chung_tu"]) == {"chung_tu", "dong_ct"}
    assert _draft_of(tmp_path, ["chung_tu", "thanh_toan"]) == {
        "chung_tu", "dong_ct", "thanh_toan"}
    assert _draft_of(tmp_path, ["chung_tu", "dong_ct"]) == {"chung_tu", "dong_ct"}
    # Without chung_tu nothing is added, and the result stays within the ceiling.
    assert _draft_of(tmp_path, ["thanh_toan"]) == {"thanh_toan"}
    assert _draft_of(tmp_path, []) == frozenset()
    from tonomyx.enforce.ceiling import PLATFORM_CEILING

    assert _draft_of(tmp_path, ["chung_tu", "thanh_toan"]) <= PLATFORM_CEILING["so"].draft

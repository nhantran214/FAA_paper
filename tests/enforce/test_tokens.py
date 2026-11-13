from dataclasses import replace
from decimal import Decimal

import pytest

from tonomyx.contracts.clock import SystemClock
from tonomyx.contracts.token import InMemoryJtiStore, TokenIssuer, TokenReplayed
from tonomyx.enforce.ceiling import PLATFORM_CEILING
from tonomyx.enforce.tokens import STEP_NEEDS, scope_token, task_token
from tonomyx.governance.template import TemplateStep


def _issuer():
    return TokenIssuer(SystemClock(), InMemoryJtiStore())


def _scope():
    return replace(PLATFORM_CEILING["so"], budget_usd=Decimal("0.50"), autonomy="L1")


def test_task_token_is_narrower_than_scope_token():
    sc = _scope()
    step = TemplateStep("s", "request_approval", "r")
    st = scope_token(_issuer(), "r", sc, "C1", "t1")
    tt = task_token(_issuer(), "r", sc, step, "C1", "t2")
    assert tt.tools == {"request_approval", "read_records"} & sc.tools
    assert tt.tools < st.tools
    assert tt.kb_domain == "" and tt.autonomy == "L1" and tt.budget_usd == Decimal("0.50")


def test_scope_above_ceiling_is_refused():
    bad = replace(PLATFORM_CEILING["so"], tools=PLATFORM_CEILING["so"].tools | {"decide_approval"})
    with pytest.raises(ValueError, match="platform rule 5"):
        scope_token(_issuer(), "r", bad, "C1", "t")
    with pytest.raises(ValueError, match="platform rule 5"):
        task_token(_issuer(), "r", bad, TemplateStep("s", "pay", "r"), "C1", "t")


def test_step_needs_cover_all_types():
    import json

    from tonomyx.governance.template import _STEP_TYPES_PATH
    assert set(STEP_NEEDS) == set(json.loads(_STEP_TYPES_PATH.read_text())["types"])
    assert not any("decide_approval" in v for k, v in STEP_NEEDS.items() if k != "decide_approval")


def test_task_token_is_single_use():
    iss = _issuer()
    tt = task_token(iss, "r", _scope(), TemplateStep("s", "pay", "r"), "C1", "t")
    iss.redeem_task_token(tt)
    with pytest.raises(TokenReplayed):
        iss.redeem_task_token(tt)


def test_a_scope_that_may_not_open_approvals_never_carries_request_approval():
    """Final review I4: ``may_open_approvals`` is part of the grant, not a label."""
    closed = replace(_scope(), may_open_approvals=False)
    assert "request_approval" in closed.tools
    assert "request_approval" not in scope_token(_issuer(), "r", closed, "C1", "t1").tools
    step = TemplateStep("s", "request_approval", "r")
    assert task_token(_issuer(), "r", closed, step, "C1", "t2").tools == {"read_records"}
    assert "request_approval" in task_token(_issuer(), "r", _scope(), step, "C1", "t3").tools


def test_a_step_of_an_unknown_type_gets_no_token():
    with pytest.raises(ValueError, match="unknown step type 'teleport'"):
        task_token(_issuer(), "r", _scope(), TemplateStep("s", "teleport", "r"), "C1", "t")


# --- Task 15 ---------------------------------------------------------------------------


def _loaded_scope(tmp_path, draft, read=("chung_tu", "hang_hoa", "doi_tac"),
                  tools=("create_document", "read_records")):
    import json

    from tonomyx.governance.template import load_template

    raw = {
        "id": "p", "name": "p", "version": "1",
        "roles": [{"id": "dp", "kind": "dieu_phoi"},
                  {"id": "de", "kind": "so", "duties": {"drafts": ["chung_tu"]},
                   "scope": {"tools": list(tools), "read": list(read), "draft": list(draft),
                             "may_open_approvals": False, "budget_usd": "0.5",
                             "autonomy": "L1"}}],
        "start": "s1",
        "steps": [{"id": "s1", "type": "open_case", "role": "dp", "params": {}}],
    }
    path = tmp_path / "t.json"
    path.write_text(json.dumps(raw))
    return next(r for r in load_template(path).roles if r.id == "de").scope


def _ctx(tok):
    from types import SimpleNamespace

    return SimpleNamespace(token=tok, actor="r", actor_kind="so", token_checks=True)


def test_a_task_token_of_a_chung_tu_role_lets_it_write_the_lines(tmp_path):
    """F15-2: a task token for a ``draft: ["chung_tu"]`` role allows writing ``dong_ct``."""
    from tonomyx.tools.core.context import require_draft

    scope = _loaded_scope(tmp_path, ["chung_tu"])
    tok = task_token(_issuer(), "r", scope, TemplateStep("s", "create_document", "r"), "C1", "t")
    assert {"chung_tu", "dong_ct"} <= tok.draft
    require_draft(_ctx(tok), "chung_tu")
    require_draft(_ctx(tok), "dong_ct")


def test_a_role_without_chung_tu_still_may_not_write_lines(tmp_path):
    from tonomyx.tools.core.context import require_draft
    from tonomyx.tools.errors import ToolDenied

    scope = _loaded_scope(tmp_path, ["thanh_toan"])
    tok = task_token(_issuer(), "r", scope, TemplateStep("s", "create_document", "r"), "C1", "t")
    assert "dong_ct" not in tok.draft
    with pytest.raises(ToolDenied, match="may not write dong_ct"):
        require_draft(_ctx(tok), "dong_ct")


def test_a_create_document_step_may_read_records_within_the_role(tmp_path):
    """F15-4: a create_document step's task token carries read_records, so the digital
    employee can read the item and partner codes; the role's scope and the platform
    ceiling still bound what it reads."""
    assert STEP_NEEDS["create_document"] == {"create_document", "read_records"}
    scope = _loaded_scope(tmp_path, ["chung_tu"])
    tok = task_token(_issuer(), "r", scope, TemplateStep("s", "create_document", "r"), "C1", "t")
    assert tok.tools == {"create_document", "read_records"}
    assert {"hang_hoa", "doi_tac"} <= tok.read
    assert tok.read == scope.read <= PLATFORM_CEILING["so"].read
    # A role that may not read records gets no read_records, and reads only its scope.
    narrow = _loaded_scope(tmp_path, ["chung_tu"], read=("chung_tu",), tools=("create_document",))
    tok = task_token(_issuer(), "r", narrow, TemplateStep("s", "create_document", "r"), "C1", "t")
    assert tok.tools == {"create_document"} and tok.read == {"chung_tu"}
    # A scope beyond the ceiling is still refused.
    wide = replace(scope, read=scope.read | {"nguon_tien"})
    with pytest.raises(ValueError, match="platform rule 5"):
        task_token(_issuer(), "r", wide, TemplateStep("s", "create_document", "r"), "C1", "t")


def test_the_template_s_lines_grant_is_the_platform_s_document_rule():
    """Review M4: ``template._draft_scope`` and ``tokens.DOCUMENT_TABLES`` state one rule
    (``chung_tu`` grants ``dong_ct``); this ties them so they cannot drift apart."""
    from tonomyx.enforce.tokens import DOCUMENT_TABLES, company_document_tables
    from tonomyx.governance.pack import Role
    from tonomyx.governance.template import _draft_scope

    assert _draft_scope(["chung_tu"]) == DOCUMENT_TABLES
    role = Role(code="X", kind="so", drafts=frozenset({"chung_tu"}), may_request=False,
                decides=frozenset())
    assert _draft_scope(["chung_tu"]) == company_document_tables(role)
    assert _draft_scope(["thanh_toan"]) & DOCUMENT_TABLES == frozenset()

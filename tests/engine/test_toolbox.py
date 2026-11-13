"""StepToolbox (ruling R7a): actors reach the tools only through it, bound to their step (R6d)."""

from __future__ import annotations

import contextlib
from dataclasses import replace
from typing import Any

import pytest

from tests.engine.conftest import (
    APPROVED,
    GOVERNANCE_VERSION,
    Conn,
    FakeEnvironment,
    FakeExecutor,
    RecordingIssuer,
    approve,
    de_scope,
    de_script,
    draft_order,
    instance,
    issuer,
    pack,
    rows,
    template,
)
from tonomyx.contracts.token import TASK_TOKEN_TTL
from tonomyx.engine import RunResult, StepToolbox, run_case
from tonomyx.engine.toolbox import tools_for_step
from tonomyx.governance.pack import ApprovalRule, CompanyPack, Role, Tier
from tonomyx.governance.template import Duties, ProcessTemplate, TemplateRole, TemplateStep
from tonomyx.tools.errors import ToolDenied

pytestmark = pytest.mark.db


def _run(conn: Conn, tpl=None, executor=None, environment=None, iss=None) -> RunResult:
    return run_case(
        conn,
        template=tpl or template(),
        pack=pack(),
        instance=instance(),
        executor=executor or FakeExecutor(de_script()),
        environment=environment or FakeEnvironment({"decide": approve}),
        governance_version=GOVERNANCE_VERSION,
        issuer=iss or issuer(),
    )


def test_tools_for_each_actor_kind() -> None:
    def step(type_: str) -> TemplateStep:
        return TemplateStep("s", type_, "r")

    assert tools_for_step(step("pay"), "so") == {"pay", "read_records"}
    assert tools_for_step(step("decide_approval"), "nguoi") == {"decide_approval"}
    assert tools_for_step(step("record_external_fact"), "ngoai") == {
        "create_document",
        "record_event",
    }
    assert tools_for_step(step("check"), "dieu_phoi") == {"read_records", "flag"}
    # A kind the step type does not allow gets nothing.
    assert tools_for_step(step("pay"), "nguoi") == frozenset()
    assert tools_for_step(step("decide_approval"), "so") == frozenset()
    assert tools_for_step(step("open_case"), "dieu_phoi") == frozenset()


def test_request_must_name_the_steps_approval_type(conn: Conn) -> None:
    def wrong_type(box: StepToolbox) -> str:
        box.call("request_approval", ma_pd="PD-01", ma_ct="PO-01", loai_pd="de_nghi_chi")
        return "done"

    result = _run(conn, executor=FakeExecutor(de_script(ask=wrong_type)))
    assert result.outcomes["ask"] == "refused"
    assert "loai_pd" in result.refusals[0] and "don_mua" in result.refusals[0]
    assert rows(conn, "SELECT * FROM core.phe_duyet") == []


@pytest.mark.parametrize("declared", ["bao_gia", ["bao_gia", "hop_dong"]])
def test_document_must_be_of_a_declared_type(conn: Conn, declared: object) -> None:
    tpl = template(draft={"params": {"doc": "don_hang", "loai_ct": declared}})
    result = _run(conn, tpl=tpl)
    assert result.outcomes["draft"] == "refused"
    assert "loai_ct" in result.refusals[0] and "don_mua" in result.refusals[0]
    assert rows(conn, "SELECT * FROM core.chung_tu") == []


def test_list_of_declared_types_admits_each(conn: Conn) -> None:
    tpl = template(draft={"params": {"doc": "don_hang", "loai_ct": ["bao_gia", "don_mua"]}})
    result = _run(conn, tpl=tpl)
    assert result.outcomes["draft"] == "done"


def test_a_list_of_declared_approval_types_admits_each(conn: Conn) -> None:
    """A template names the approval types a step may request under each name companies use
    for it (a text or a list, as loai_ct); a type outside the list is still refused."""
    tpl = template(ask={"params": {"id": "pd", "doc": "don_hang", "loai_pd": ["mua", "don_mua"]}})
    result = _run(conn, tpl=tpl)
    assert result.outcomes["ask"] == "done"
    tpl = template(ask={"params": {"id": "pd", "doc": "don_hang", "loai_pd": ["mua", "chi"]}})
    result = _run(conn, tpl=tpl)
    assert result.outcomes["ask"] == "refused"
    assert "loai_pd" in result.refusals[0] and "chi" in result.refusals[0]


def test_a_tool_outside_the_step_is_refused(conn: Conn) -> None:
    def ask_early(box: StepToolbox) -> str:
        draft_order(box)
        box.call("request_approval", ma_pd="PD-01", ma_ct="PO-01", loai_pd="don_mua")
        return "done"

    result = _run(conn, executor=FakeExecutor(de_script(draft=ask_early)))
    assert result.outcomes["draft"] == "refused"
    assert "request_approval" in result.refusals[0]
    assert rows(conn, "SELECT * FROM core.phe_duyet") == []


def test_a_person_may_not_use_a_digital_employees_tool(conn: Conn) -> None:
    def person_pays(box: StepToolbox) -> str:
        box.call("pay", ma_tt="TT-01", ma_ct="PO-01", ma_pd="PD-01")
        return "approved"

    result = _run(conn, environment=FakeEnvironment({"decide": person_pays}))
    assert result.outcomes["decide"] == "refused"
    assert "pay" in result.refusals[0]
    assert rows(conn, "SELECT * FROM core.thanh_toan") == []


def test_an_expired_token_is_refused(conn: Conn) -> None:
    iss = RecordingIssuer()

    def slow(box: StepToolbox) -> str:
        iss.clock.advance(TASK_TOKEN_TTL.total_seconds() + 1)  # type: ignore[attr-defined]
        return draft_order(box)

    result = _run(conn, executor=FakeExecutor(de_script(draft=slow)), iss=iss)
    assert result.outcomes["draft"] == "refused"
    assert "expired" in result.refusals[0]
    assert rows(conn, "SELECT * FROM core.chung_tu") == []


def test_outside_party_records_its_fact(conn: Conn) -> None:
    receipt = TemplateStep(
        "receive",
        "record_external_fact",
        "ncc",
        {"doc": "phieu_giao", "event_kind": "SHIPPED", "loai_ct": "van_don"},
        next="end",
    )

    def ship(box: StepToolbox) -> str:
        box.call(
            "create_document",
            loai_ct="van_don",
            ma_ct="VD-01",
            ma_dt="NCC-01",
            lines=[{"ma_hh": "HH-01", "so_luong": 10}],
            event_kind="SHIPPED",
        )
        return "done"

    tpl = template(receipt, decide={"next": "receive"})
    environment = FakeEnvironment({"decide": approve, "receive": ship})
    result = _run(conn, tpl=tpl, environment=environment)
    assert result.outcomes["receive"] == "done", result.refusals
    assert ("outside", "receive", "NCC-01") in environment.seen
    event = rows(conn, "SELECT kind, actor, buoc FROM core.su_kien WHERE ref = 'VD-01'")
    assert event == [{"kind": "SHIPPED", "actor": "NCC-01", "buoc": "receive"}]


def test_engine_check_step_is_performed_with_engine_authority(conn: Conn) -> None:
    executor = FakeExecutor(de_script())
    tpl = template(review={"role": "dp", "guidance": ""})
    result = _run(conn, tpl=tpl, executor=executor)
    assert result.outcomes["review"] == "pass", result.refusals
    assert ("review", "DP-01") in executor.seen
    box = executor.toolboxes[executor.seen.index(("review", "DP-01"))]
    assert box.view.actor_kind == "dieu_phoi" and box.view.has_token is False


# --- fix round 1: actor input is never trusted (I1) --------------------------------------------


@pytest.mark.parametrize(
    ("sid", "call"),
    [
        (
            "draft",
            lambda b: b.call(
                "create_document", loai_ct=["don_mua"], ma_ct="PO-01", ma_dt="NCC-01", lines=[]
            ),
        ),
        (
            "ask",
            lambda b: b.call("request_approval", ma_pd="PD-01", ma_ct="PO-01", loai_pd=["don_mua"]),
        ),
        ("review", lambda b: b.call("read_records", table=["x"], where={})),
        ("review", lambda b: b.call("read_records", table="dong_ct", where=None)),
        (
            "draft",
            lambda b: b.call(
                "create_document", loai_ct="don_mua", ma_ct="PO-01", ma_dt="NCC-01", lines="abc"
            ),
        ),
        (
            "draft",
            lambda b: b.call(
                "create_document", loai_ct="don_mua", ma_ct="PO-01", ma_dt="NCC-01", lines=[1]
            ),
        ),
        (
            "draft",
            lambda b: b.call(
                "create_document", loai_ct="don_mua", ma_ct=123, ma_dt="NCC-01", lines=[]
            ),
        ),
    ],
    ids=[
        "loai_ct_list",
        "loai_pd_list",
        "table_list",
        "where_none",
        "lines_text",
        "lines_int",
        "ma_ct_int",
    ],
)
def test_malformed_arguments_are_refused_not_crashed(conn: Conn, sid: str, call: Any) -> None:
    def play(box: StepToolbox) -> str:
        call(box)
        return "pass" if sid == "review" else "done"

    script = de_script(**{sid: play})
    tpl = template(**{sid: {"on": {"refused": "hold"}}})
    result = _run(conn, tpl=tpl, executor=FakeExecutor(script))
    assert result.outcomes[sid] == "refused"
    assert result.stop == {"type": "wait", "for": "quyet_dinh_duyet", "step": "hold"}
    assert len(result.refusals) == 1 and result.refusals[0].startswith(f"{sid}: ")
    # The connection is still usable.
    assert len(rows(conn, "SELECT * FROM core.ho_so")) == 1


# --- fix round 1: no tool-callable context reaches an actor (R7d) -------------------------------


def test_actors_get_a_view_not_a_context(conn: Conn) -> None:
    stash: dict[str, Any] = {}

    def draft(box: StepToolbox) -> str:
        stash["box"], stash["view"] = box, box.view
        return draft_order(box)

    def review(box: StepToolbox) -> str:
        view = stash["view"]
        assert (view.case_id, view.actor, view.actor_kind, view.step_id) == (
            "HS-01",
            "DE-MH",
            "so",
            "draft",
        )
        assert view.has_token is True
        for name in ("conn", "token", "gate", "mail", "ctx"):
            assert not hasattr(view, name)
            assert not hasattr(box, name)
        with pytest.raises(AttributeError):
            view.actor = "TP-MH"
        # The previous step's toolbox is closed.
        with pytest.raises(ToolDenied, match="closed"):
            stash["box"].call("read_records", table="chung_tu", where={})
        # A digital employee cannot release facts.
        assert not hasattr(box, "release_fact")
        return "pass"

    result = _run(conn, executor=FakeExecutor(de_script(draft=draft, review=review)))
    assert result.outcomes["review"] == "pass", result.refusals
    assert result.refusals == []


def test_environment_toolboxes_carry_no_token(conn: Conn) -> None:
    views: list[Any] = []

    def decide(box: StepToolbox) -> str:
        views.append(box.view)
        return approve(box)

    _run(conn, environment=FakeEnvironment({"decide": decide}))
    assert views[0].actor_kind == "nguoi" and views[0].has_token is False


def test_the_environment_releases_a_fact(conn: Conn) -> None:
    def decide(box: Any) -> str:
        box.release_fact("so_luong_nhan", 12)
        box.release_fact("so_luong_nhan", 12)  # the same release again is a no-op
        with pytest.raises(ToolDenied, match="so_luong_nhan"):
            box.release_fact("so_luong_nhan", 13)
        for bad in (("", 1), ("x", "12"), ("x", True), ("x", 1.5)):
            with pytest.raises(ToolDenied):
                box.release_fact(*bad)
        return approve(box)

    result = _run(conn, environment=FakeEnvironment({"decide": decide}))
    # Refused releases are refusals of the step, like any refused call.
    assert result.outcomes["decide"] == "refused"
    released = rows(
        conn, "SELECT case_id, gia_tri FROM core.nguon_tien WHERE ten = 'so_luong_nhan'"
    )
    assert released == [{"case_id": "HS-01", "gia_tri": 12}]


def test_a_clean_release_keeps_the_step(conn: Conn) -> None:
    def decide(box: Any) -> str:
        box.release_fact("so_luong_nhan", 12)
        return approve(box)

    result = _run(conn, environment=FakeEnvironment({"decide": decide}))
    assert result.outcomes["decide"] == "approved", result.refusals


# --- Task 8: the environment reads its case ------------------------------------------------------


def test_the_environment_reads_its_case(conn: Conn) -> None:
    """A person or an outside party sees the case's rows (``read_records``), not other
    cases', and a read records no event. A digital employee's toolbox has no ``read``."""
    seen: dict[str, Any] = {}

    def decide(box: Any) -> str:
        seen["docs"] = box.read("chung_tu", {"ma_ct": "PO-01"})
        seen["approvals"] = box.read("phe_duyet")
        seen["events"] = len(box.read("su_kien"))
        return approve(box)

    result = _run(conn, environment=FakeEnvironment({"decide": decide}))
    assert result.outcomes["decide"] == "approved", result.refusals
    assert [d["ma_ct"] for d in seen["docs"]] == ["PO-01"]
    assert [(a["ma_pd"], a["trang_thai"]) for a in seen["approvals"]] == [("PD-01", "Chờ duyệt")]
    # draft and ask wrote one event each; the reads none.
    assert seen["events"] == 2
    assert not hasattr(StepToolbox, "read")


def test_a_refused_read_refuses_the_step(conn: Conn) -> None:
    def decide(box: Any) -> str:
        box.read("khong_co")
        return approve(box)

    result = _run(conn, environment=FakeEnvironment({"decide": decide}))
    assert result.outcomes["decide"] == "refused"
    assert "khong_co" in result.refusals[0]


# --- pay is bound to its step (final review I1) ---------------------------------------------

KTT = Role("KTT", "nguoi", frozenset(), False, frozenset({"de_nghi_chi"}))


def _pay_pack() -> CompanyPack:
    p = pack()
    rules = {
        **p.policy.approval_rules,
        "de_nghi_chi": ApprovalRule("de_nghi_chi", True, (Tier(None, "KTT"),)),
    }
    return replace(p, roles=(*p.roles, KTT), policy=replace(p.policy, approval_rules=rules))


def _pay_template(**pay_params: Any) -> ProcessTemplate:
    """The order is approved by TP-MH; then the DE drafts a payment request on it (doc
    ``de_nghi_chi``), asks for its approval (``pd_chi``), KTT approves, and one ``pay`` step
    pays the request."""
    steps = (
        TemplateStep(
            "draft_dn",
            "create_document",
            "de",
            {"doc": "de_nghi_chi", "loai_ct": "de_nghi_chi"},
            guidance="Lập đề nghị chi.",
            next="ask_dn",
        ),
        TemplateStep(
            "ask_dn",
            "request_approval",
            "de",
            {"id": "pd_chi", "doc": "de_nghi_chi", "loai_pd": "de_nghi_chi"},
            guidance="Trình duyệt chi.",
            next="decide_dn",
        ),
        TemplateStep(
            "decide_dn",
            "decide_approval",
            "ktt",
            {"approval": "pd_chi", "decision": "quyet_dinh_chi"},
            next="pay",
            on={"pending": "hold"},
        ),
        TemplateStep(
            "pay",
            "pay",
            "de",
            {"id": "thanh_toan", "request": "de_nghi_chi", "approval": "pd_chi", **pay_params},
            guidance="Chi tiền.",
            next="end",
        ),
    )
    tpl = template(
        *steps, de=de_scope(draft=frozenset({"chung_tu", "dong_ct", "thanh_toan"})),
        decide={"next": "draft_dn"},
    )
    ktt = TemplateRole("ktt", "nguoi", Duties(decides=frozenset({"de_nghi_chi"})), None)
    return replace(tpl, roles=(*tpl.roles, ktt))


def _draft_request(box: StepToolbox) -> str:
    box.call(
        "create_document",
        loai_ct="de_nghi_chi",
        ma_ct="DN-01",
        ma_dt="NCC-01",
        ct_goc="PO-01",
        lines=[{"ma_hh": "HH-01", "so_luong": 10, "don_gia": 50000}],
    )
    return "done"


def _ask_request(box: StepToolbox) -> str:
    box.call("request_approval", ma_pd="PD-02", ma_ct="DN-01", loai_pd="de_nghi_chi")
    return "done"


def _approve_request(box: StepToolbox) -> str:
    box.call("decide_approval", ma_pd="PD-02", decision=APPROVED)
    return "approved"


def _run_pay(conn: Conn, pay: Any, tpl: ProcessTemplate | None = None) -> RunResult:
    executor = FakeExecutor(
        de_script(draft_dn=_draft_request, ask_dn=_ask_request, pay=pay)
    )
    return run_case(
        conn,
        template=tpl or _pay_template(),
        pack=_pay_pack(),
        instance=instance(),
        executor=executor,
        environment=FakeEnvironment({"decide": approve, "decide_dn": _approve_request}),
        governance_version=GOVERNANCE_VERSION,
        issuer=issuer(),
    )


def _payments(conn: Conn) -> list[str]:
    return [r["ma_ct"] for r in rows(conn, "SELECT ma_ct FROM core.thanh_toan ORDER BY ma_tt")]


def test_a_pay_step_pays_its_request_once(conn: Conn) -> None:
    def honest(box: StepToolbox) -> str:
        box.call("pay", ma_tt="TT-01", ma_ct="DN-01", ma_pd="PD-02")
        return "done"

    result = _run_pay(conn, honest)
    assert result.refusals == [] and result.stop["type"] == "end"
    assert _payments(conn) == ["DN-01"]


def test_a_pay_step_never_pays_twice(conn: Conn) -> None:
    """The probe: the request, then its source order on the order's own approval."""

    def double(box: StepToolbox) -> str:
        box.call("pay", ma_tt="TT-01", ma_ct="DN-01", ma_pd="PD-02")
        box.call("pay", ma_tt="TT-02", ma_ct="PO-01", ma_pd="PD-01")
        return "done"

    result = _run_pay(conn, double)
    assert result.outcomes["pay"] == "refused"
    assert "pay twice in step pay" in result.refusals[0]
    assert _payments(conn) == ["DN-01"]  # the first payment stands, the second never ran


def test_a_pay_step_pays_only_its_declared_request_and_approval(conn: Conn) -> None:
    """Paying the order on the order's approval skips the payment request and KTT."""

    def order(box: StepToolbox) -> str:
        box.call("pay", ma_tt="TT-02", ma_ct="PO-01", ma_pd="PD-01")
        return "done"

    result = _run_pay(conn, order)
    assert result.outcomes["pay"] == "refused"
    assert "ma_ct 'PO-01' of loai_ct 'don_mua'" in result.refusals[0]
    assert _payments(conn) == []


def test_a_pay_step_takes_only_its_declared_approval(conn: Conn) -> None:
    """The request named on another approval type than the step's is refused."""
    tpl = _pay_template()
    tpl = replace(
        tpl,
        steps={
            **tpl.steps,
            "pay": replace(
                tpl.steps["pay"], params={**tpl.steps["pay"].params, "request": ["de_nghi_chi"]}
            ),
        },
    )

    def wrong_approval(box: StepToolbox) -> str:
        box.call("pay", ma_tt="TT-01", ma_ct="DN-01", ma_pd="PD-01")
        return "done"

    result = _run_pay(conn, wrong_approval, tpl)
    assert result.outcomes["pay"] == "refused"
    assert "ma_pd 'PD-01' of loai_pd 'don_mua'" in result.refusals[0]
    assert _payments(conn) == []


def test_a_pay_step_that_declares_an_invoice_needs_one(conn: Conn) -> None:
    def no_invoice(box: StepToolbox) -> str:
        box.call("pay", ma_tt="TT-01", ma_ct="DN-01", ma_pd="PD-02")
        return "done"

    result = _run_pay(conn, no_invoice, _pay_template(invoice="hoa_don_mua"))
    assert result.outcomes["pay"] == "refused"
    assert "pay without an invoice in step pay" in result.refusals[0]
    assert _payments(conn) == []


# --- names and refusals (final review M2, M3) ------------------------------------------------


@pytest.mark.parametrize("name", [None, 3, ["create_document"], {"x": 1}])
def test_a_tool_name_that_is_not_a_text_is_refused(conn: Conn, name: Any) -> None:
    def odd(box: StepToolbox) -> str:
        box.call(name)
        return "done"

    result = _run(conn, executor=FakeExecutor(de_script(draft=odd)))
    assert result.outcomes["draft"] == "refused"
    assert "unknown tool" in result.refusals[0]


@pytest.mark.parametrize("outcome", [None, 3, ["done"], {"done": 1}])
def test_an_outcome_that_is_not_a_text_is_refused(conn: Conn, outcome: Any) -> None:
    result = _run(conn, executor=FakeExecutor(de_script(review=lambda box: outcome)))
    assert result.outcomes["review"] == "refused"
    assert "unknown outcome" in result.refusals[0]


def test_refusals_are_read_only(conn: Conn) -> None:
    def tamper(box: StepToolbox) -> str:
        with contextlib.suppress(ToolDenied):
            box.call("request_approval", ma_pd="PD-01", ma_ct="PO-01", loai_pd="don_mua")
        with pytest.raises(AttributeError):
            box.refusals.clear()  # type: ignore[attr-defined]
        with pytest.raises(AttributeError):
            box.refusals = []  # type: ignore[misc]
        return draft_order(box)

    result = _run(conn, executor=FakeExecutor(de_script(draft=tamper)))
    assert result.outcomes["draft"] == "refused"
    assert "request_approval" in result.refusals[0]


# --- update_status and event kinds bound to the step (final review M4, M5) -------------------


def _status_step(**params: Any) -> TemplateStep:
    base = {"table": "chung_tu", "key": "don_hang", "trang_thai": "Đã hủy"}
    return TemplateStep(
        "ask", "update_status", "de", {**base, **params}, guidance="Hủy đơn.", next="decide",
        on={"refused": "end"},
    )


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (dict(table="ho_so", key={"case_id": "HS-01"}, trang_thai="Đã hủy"), "table 'ho_so'"),
        (dict(table="chung_tu", key={"ma_ct": "PO-01"}, trang_thai="Nháp"), "to 'Nháp'"),
    ],
)
def test_update_status_is_bound_to_the_steps_declaration(
    conn: Conn, call: dict[str, Any], expected: str
) -> None:
    def change(box: StepToolbox) -> str:
        box.call("update_status", **call)
        return "done"

    result = _run(
        conn, tpl=template(_status_step()), executor=FakeExecutor(de_script(ask=change))
    )
    assert result.outcomes["ask"] == "refused"
    assert expected in result.refusals[0]


def test_update_status_changes_only_the_steps_declared_document(conn: Conn) -> None:
    """The step's key names the receipt (``phieu``, of loai_ct phieu_nhap); cancelling the
    order (don_mua) in it is refused."""
    receipt = TemplateStep(
        "paper", "create_document", "de", {"doc": "phieu", "loai_ct": "phieu_nhap"},
        guidance="Lập phiếu.", optional=True, next="review",
    )

    def cancel_order(box: StepToolbox) -> str:
        box.call("update_status", table="chung_tu", key={"ma_ct": "PO-01"}, trang_thai="Đã hủy")
        return "done"

    tpl = template(_status_step(key="phieu"), receipt, draft={"next": "paper"})
    result = _run(conn, tpl=tpl, executor=FakeExecutor(de_script(ask=cancel_order)))
    assert result.outcomes["ask"] == "refused"
    assert "a 'don_mua' document in step ask" in result.refusals[0]
    assert rows(conn, "SELECT trang_thai FROM core.chung_tu") == [{"trang_thai": "Nháp"}]


def test_update_status_of_the_declared_document_goes_through(conn: Conn) -> None:
    def cancel_order(box: StepToolbox) -> str:
        box.call("update_status", table="chung_tu", key={"ma_ct": "PO-01"}, trang_thai="Đã hủy")
        return "done"

    result = _run(
        conn, tpl=template(_status_step()), executor=FakeExecutor(de_script(ask=cancel_order))
    )
    assert result.outcomes["ask"] == "done"
    assert rows(conn, "SELECT trang_thai FROM core.chung_tu") == [{"trang_thai": "Đã hủy"}]


def test_create_document_records_the_steps_declared_event_kind(conn: Conn) -> None:
    tpl = template(draft={"params": {"doc": "don_hang", "loai_ct": "don_mua",
                                     "event_kind": "RECEIVED"}})
    result = _run(conn, tpl=tpl)
    assert result.outcomes["draft"] == "refused"
    assert "event_kind 'DRAFTED' in step draft, which records 'RECEIVED'" in result.refusals[0]
    assert rows(conn, "SELECT * FROM core.chung_tu") == []

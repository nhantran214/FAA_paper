"""run_case: load, validate, walk the template and hand each step to its actor."""

from __future__ import annotations

import contextlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tests.engine.conftest import (
    APPROVED,
    CASE_ID,
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
    no_decision,
    pack,
    rows,
    snapshot,
    template,
)
from tonomyx.contracts.token import TokenReplayed
from tonomyx.enforce.controls import Controls
from tonomyx.enforce.tokens import STEP_NEEDS
from tonomyx.engine import RunResult, StepToolbox, TemplateInvalid, run_case
from tonomyx.engine.run import GivenDataError, load_given
from tonomyx.governance.pack import Role
from tonomyx.governance.template import (
    Duties,
    ProcessTemplate,
    TemplateRole,
    TemplateStep,
    load_template,
    thaw,
)
from tonomyx.tools.errors import ToolDenied

pytestmark = pytest.mark.db


def _run(conn: Conn, tpl=None, executor=None, environment=None, inst=None, iss=None) -> RunResult:
    return run_case(
        conn,
        template=tpl or template(),
        pack=pack(),
        instance=inst or instance(),
        executor=executor or FakeExecutor(de_script()),
        environment=environment or FakeEnvironment({"decide": approve}),
        governance_version=GOVERNANCE_VERSION,
        issuer=iss or issuer(),
    )


# --- walking ---------------------------------------------------------------------------


def test_walks_next_and_on_outcomes(conn: Conn) -> None:
    executor, environment = FakeExecutor(de_script()), FakeEnvironment({"decide": approve})
    result = _run(conn, executor=executor, environment=environment)
    assert result.case_id == CASE_ID
    assert result.governance_version == GOVERNANCE_VERSION
    assert result.steps_run == ["open", "draft", "review", "ask", "decide", "end"]
    assert result.outcomes == {
        "open": "done",
        "draft": "done",
        "review": "pass",
        "ask": "done",
        "decide": "approved",
        "end": "done",
    }
    assert result.refusals == []
    # Each step reached its actor under the bound company role code.
    assert executor.seen == [("draft", "DE-MH"), ("review", "DE-MH"), ("ask", "DE-MH")]
    assert environment.seen == [("person", "decide", "TP-MH")]
    case = rows(conn, "SELECT * FROM core.ho_so WHERE case_id = %s", (CASE_ID,))
    assert [(c["tieu_de"], c["trang_thai"]) for c in case] == [("Mua thép cho xưởng", "Đang xử lý")]
    order = rows(conn, "SELECT trang_thai, nguoi_lap FROM core.chung_tu WHERE ma_ct = 'PO-01'")
    assert order == [{"trang_thai": APPROVED, "nguoi_lap": "DE-MH"}]
    events = rows(
        conn, "SELECT buoc, kind, actor, governance_version FROM core.su_kien ORDER BY id"
    )
    assert [(e["buoc"], e["kind"], e["actor"]) for e in events] == [
        ("draft", "DRAFTED", "DE-MH"),
        ("ask", "REQUESTED", "DE-MH"),
        ("decide", "APPROVED", "TP-MH"),
    ]
    assert {e["governance_version"] for e in events} == {GOVERNANCE_VERSION}

    # The same decide step, pending: its `on` target (hold) wins over `next` (end).
    again = _run(conn, environment=FakeEnvironment({"decide": no_decision}))
    assert again.steps_run[-2:] == ["decide", "hold"]
    assert again.outcomes["decide"] == "pending"


def test_check_outcome_follows_its_on_target(conn: Conn) -> None:
    result = _run(conn, executor=FakeExecutor(de_script(review=lambda box: "flag")))
    assert result.steps_run == ["open", "draft", "review", "end"]
    assert result.outcomes["review"] == "flag"


def test_optional_step_may_be_skipped(conn: Conn) -> None:
    script = de_script()
    del script["review"]  # no script: the fake reports skipped
    result = _run(conn, executor=FakeExecutor(script))
    assert result.outcomes["review"] == "skipped"
    assert result.steps_run == ["open", "draft", "review", "ask", "decide", "end"]
    assert result.refusals == []


def test_optional_skip_follows_on_skipped(conn: Conn) -> None:
    script = de_script()
    del script["review"]
    tpl = template(review={"on": {"skipped": "hold"}})
    result = _run(conn, tpl=tpl, executor=FakeExecutor(script))
    assert result.steps_run == ["open", "draft", "review", "hold"]


def test_non_optional_skip_is_refused(conn: Conn) -> None:
    script = de_script()
    del script["review"]
    result = _run(conn, tpl=template(review={"optional": False}), executor=FakeExecutor(script))
    assert result.outcomes["review"] == "refused"
    assert result.stop == {"type": "error", "step": "review"}
    assert len(result.refusals) == 1
    assert "review" in result.refusals[0] and "not optional" in result.refusals[0]


def test_invalid_template_is_refused_before_any_write(conn: Conn) -> None:
    # A digital employee made to decide an approval (DE_DECIDES), and a dangling target.
    bad = template(decide={"role": "de", "next": "nowhere"})
    executor, environment = FakeExecutor(de_script()), FakeEnvironment()
    with pytest.raises(TemplateInvalid) as caught:
        _run(conn, tpl=bad, executor=executor, environment=environment)
    codes = {f.code for f in caught.value.findings}
    assert {"DE_DECIDES", "UNKNOWN_TARGET"} <= codes
    assert all(f.level == "error" for f in caught.value.findings)
    assert "DE_DECIDES" in str(caught.value)
    assert executor.seen == [] and environment.seen == []
    assert all(rows == [] for rows in snapshot(conn).values())


def test_unbindable_role_is_refused_before_any_write(conn: Conn) -> None:
    # Task 14: a role is unbindable only when the company has no candidate for it; here no
    # person is left who decides any approval type.
    p = pack()
    p = replace(p, roles=tuple(r for r in p.roles if r.code not in ("TP-MH", "GD")))
    with pytest.raises(
        TemplateInvalid, match="template role 'tp': no company role of kind 'nguoi'"
    ):
        run_case(
            conn,
            template=template(),
            pack=p,
            instance=instance(),
            executor=FakeExecutor(),
            environment=FakeEnvironment(),
            governance_version=GOVERNANCE_VERSION,
            issuer=issuer(),
        )
    assert all(rows == [] for rows in snapshot(conn).values())


# --- refusals (Review Focus 4, ruling R6b) --------------------------------------------------


def _approve_as_de(box: StepToolbox) -> str:
    box.call("update_status", table="chung_tu", key={"ma_ct": "PO-01"}, trang_thai=APPROVED)
    return "done"


def _status_steps(on_refused: bool) -> list[TemplateStep]:
    """`ask` becomes a status update by the digital employee; its failure path is a flag."""
    ask = TemplateStep(
        "ask",
        "update_status",
        "de",
        {"table": "chung_tu", "key": "don_hang", "trang_thai": APPROVED},
        guidance="Cập nhật trạng thái.",
        next="decide",
        on={"refused": "raise"} if on_refused else {},
    )
    if not on_refused:
        return [ask]
    flag = TemplateStep(
        "raise",
        "flag_exception",
        "de",
        {"ref": "don_hang", "reason": "khong_duoc_duyet"},
        guidance="Báo ngoại lệ.",
        next="end",
    )
    return [ask, flag]


def _flag(box: StepToolbox) -> str:
    box.call("flag", ref="PO-01", reason="Trợ lý số không được tự duyệt")
    return "done"


def test_refused_call_is_recorded_and_run_continues(conn: Conn) -> None:
    executor = FakeExecutor(de_script(ask=_approve_as_de, **{"raise": _flag}))
    result = _run(conn, tpl=template(*_status_steps(on_refused=True)), executor=executor)
    assert result.outcomes["ask"] == "refused"
    assert len(result.refusals) == 1
    assert result.refusals[0].startswith("ask: ")
    assert "platform rule 1" in result.refusals[0]
    # The run carried on along the failure path, on the same connection.
    assert result.steps_run == ["open", "draft", "review", "ask", "raise", "end"]
    assert result.stop["type"] == "end"
    assert rows(conn, "SELECT trang_thai FROM core.chung_tu WHERE ma_ct = 'PO-01'") == [
        {"trang_thai": "Nháp"}
    ]
    kinds = [r["kind"] for r in rows(conn, "SELECT kind FROM core.su_kien ORDER BY id")]
    assert kinds == ["DRAFTED", "FLAGGED"]


def test_refused_call_without_failure_path_stops_with_error(conn: Conn) -> None:
    executor = FakeExecutor(de_script(ask=_approve_as_de))
    result = _run(conn, tpl=template(*_status_steps(on_refused=False)), executor=executor)
    assert result.steps_run == ["open", "draft", "review", "ask"]
    assert result.stop == {"type": "error", "step": "ask"}
    assert "platform rule 1" in result.refusals[0]


def test_table_outside_the_token_is_refused(conn: Conn) -> None:
    # The digital employee's scope does not let it draft document lines.
    tpl = template(de=de_scope(draft=frozenset({"chung_tu"})))
    result = _run(conn, tpl=tpl)
    assert result.outcomes["draft"] == "refused"
    assert result.stop == {"type": "error", "step": "draft"}
    assert "dong_ct" in result.refusals[0]
    assert rows(conn, "SELECT * FROM core.chung_tu") == []


def test_a_swallowed_refusal_still_refuses_the_step(conn: Conn) -> None:
    def sneaky(box: StepToolbox) -> str:
        with contextlib.suppress(ToolDenied):
            _approve_as_de(box)
        return "done"

    executor = FakeExecutor(de_script(ask=sneaky, **{"raise": _flag}))
    result = _run(conn, tpl=template(*_status_steps(on_refused=True)), executor=executor)
    assert result.outcomes["ask"] == "refused"
    assert len(result.refusals) == 1 and "platform rule 1" in result.refusals[0]
    assert result.steps_run[-2:] == ["raise", "end"]


def test_database_error_in_a_step_is_refused_and_connection_stays_usable(conn: Conn) -> None:
    def duplicate_lines(box: StepToolbox) -> str:
        line = {"ma_dong": "L-1", "ma_hh": "HH-01", "so_luong": 1, "don_gia": 50000}
        box.call(
            "create_document", loai_ct="don_mua", ma_ct="PO-01", ma_dt="NCC-01", lines=[line, line]
        )
        return "done"

    tpl = template(draft={"on": {"refused": "hold"}})
    result = _run(conn, tpl=tpl, executor=FakeExecutor(de_script(draft=duplicate_lines)))
    assert result.outcomes["draft"] == "refused"
    assert result.steps_run == ["open", "draft", "hold"]
    assert result.stop == {"type": "wait", "for": "quyet_dinh_duyet", "step": "hold"}
    assert len(result.refusals) == 1 and result.refusals[0].startswith("draft: ")
    assert rows(conn, "SELECT * FROM core.chung_tu") == []
    assert len(rows(conn, "SELECT * FROM core.ho_so")) == 1


def test_unknown_outcome_is_refused(conn: Conn) -> None:
    result = _run(conn, executor=FakeExecutor(de_script(review=lambda box: "great")))
    assert result.outcomes["review"] == "refused"
    assert result.stop == {"type": "error", "step": "review"}
    assert "great" in result.refusals[0]


def test_a_digital_employee_never_reports_a_decision(conn: Conn) -> None:
    result = _run(conn, executor=FakeExecutor(de_script(review=lambda box: "approved")))
    assert result.outcomes["review"] == "refused"
    assert "platform rule 1" in result.refusals[0]


# --- stops ------------------------------------------------------------------------------------


def test_wait_and_stop_shapes(conn: Conn) -> None:
    ended = _run(conn)
    assert ended.stop == {"type": "end", "reason": "Hoàn tất mua", "step": "end"}
    waiting = _run(conn, environment=FakeEnvironment({"decide": no_decision}))
    assert waiting.stop == {"type": "wait", "for": "quyet_dinh_duyet", "step": "hold"}
    assert rows(conn, "SELECT trang_thai FROM core.phe_duyet") == [{"trang_thai": "Chờ duyệt"}]


def test_a_loop_is_cut_at_the_step_limit(conn: Conn) -> None:
    tpl = template(review={"optional": False, "on": {"pass": "review"}})
    result = _run(conn, tpl=tpl)
    assert result.stop["type"] == "error"
    assert result.stop["step"] == "review"
    assert "step limit" in result.stop["reason"]


# --- repeatability (Review Focus 3) -----------------------------------------------------------


def test_two_runs_of_one_case_are_identical(conn: Conn) -> None:
    first = _run(conn)
    first_state = snapshot(conn)
    second = _run(conn)
    second_state = snapshot(conn)
    assert first == second
    assert first_state == second_state
    assert len(second_state["su_kien"]) == 3
    assert [r["id"] for r in second_state["su_kien"]] == [1, 2, 3]


# --- tokens -----------------------------------------------------------------------------------


def test_each_digital_employee_step_gets_a_new_single_use_token(conn: Conn) -> None:
    iss = RecordingIssuer()
    executor = FakeExecutor(de_script())
    _run(conn, executor=executor, iss=iss)
    steps = ["draft", "review", "ask"]
    assert len(iss.issued) == len(steps)
    assert len({t.jti for t in iss.issued}) == len(steps)
    assert len({t.task_id for t in iss.issued}) == len(steps)
    tpl = template()
    scope = tpl.roles[1].scope
    assert scope is not None
    for token, sid in zip(iss.issued, steps, strict=True):
        assert token.sub == "DE-MH" and token.case_id == CASE_ID
        assert token.tools == scope.tools & STEP_NEEDS[tpl.steps[sid].type]
    # Each token was spent exactly once and cannot be spent again.
    assert iss.redeemed == [t.jti for t in iss.issued]
    for token in iss.issued:
        with pytest.raises(TokenReplayed):
            iss.redeem_task_token(token)
    # A toolbox kept past its step refuses every call.
    with pytest.raises(ToolDenied, match="closed"):
        executor.toolboxes[0].call("read_records", table="chung_tu", where={})


# --- loading (rulings R2a, R2f) ---------------------------------------------------------------


def test_load_given_inserts_checked_rows_as_the_platform(conn: Conn) -> None:
    """A document naming its source comes after it whatever the order given; an event or
    an unknown table is refused before anything is written."""
    case = {"case_id": "HS-9", "tieu_de": "Thử", "trang_thai": "Đang xử lý"}

    def doc(ma_ct: str, ct_goc: str) -> dict[str, str]:
        return {
            "ma_ct": ma_ct,
            "loai_ct": "don_mua",
            "case_id": "HS-9",
            "ct_goc": ct_goc,
            "nguoi_lap": "NV-1",
            "trang_thai": "Đã duyệt",  # no actor wrote it: rules 1-5 stand aside
            "tien_te": "VND",
            "tong_tien": "500",
        }

    load_given(conn, {"ho_so": [case], "chung_tu": [doc("B", "A"), doc("A", "")]})
    got = conn.execute("SELECT ma_ct, ct_goc, tong_tien FROM core.chung_tu ORDER BY ma_ct")
    assert got.fetchall() == [
        {"ma_ct": "A", "ct_goc": None, "tong_tien": 500},
        {"ma_ct": "B", "ct_goc": "A", "tong_tien": 500},
    ]
    for bad in ({"su_kien": [{"kind": "DRAFTED"}]}, {"bang_la": [{}]}):
        with pytest.raises(GivenDataError):
            load_given(conn, {"ho_so": [{**case, "case_id": "HS-10"}]}, bad)
    assert conn.execute("SELECT count(*) AS n FROM core.ho_so").fetchone() == {"n": 1}


def test_given_data_and_policy_values_are_loaded(conn: Conn) -> None:
    history = {
        "ho_so": [{"case_id": "HS-00", "tieu_de": "Hồ sơ trước", "trang_thai": "Hoàn tất"}],
        # The receipt names the order as its source but comes first: the loader orders them.
        "chung_tu": [
            {
                "ma_ct": "GRN-00",
                "loai_ct": "phieu_nhap",
                "case_id": "HS-00",
                "ma_dt": "NCC-01",
                "ct_goc": "PO-00",
                "nguoi_lap": "NV-01",
                "trang_thai": "Hoàn tất",
                "ket_qua": "",
                "tien_te": "VND",
                "thue_vat": "",
                "tong_tien": "",
                "ghi_chu": "",
            },
            {
                "ma_ct": "PO-00",
                "loai_ct": "don_mua",
                "case_id": "HS-00",
                "ma_dt": "NCC-01",
                "ct_goc": "",
                "nguoi_lap": "NV-01",
                "trang_thai": "Đã duyệt",
                "ket_qua": "",
                "tien_te": "VND",
                "thue_vat": "0",
                "tong_tien": "100000",
                "ghi_chu": "",
            },
        ],
    }
    _run(conn, inst=instance(history))
    docs = rows(conn, "SELECT ma_ct, ct_goc, tong_tien, ket_qua FROM core.chung_tu ORDER BY ma_ct")
    assert docs == [
        {"ma_ct": "GRN-00", "ct_goc": "PO-00", "tong_tien": None, "ket_qua": None},
        {"ma_ct": "PO-00", "ct_goc": None, "tong_tien": 100000, "ket_qua": None},
        {"ma_ct": "PO-01", "ct_goc": None, "tong_tien": 500000, "ket_qua": None},
    ]
    assert rows(conn, "SELECT stk FROM core.doi_tac") == [{"stk": "0011"}]
    released = rows(conn, "SELECT case_id, ten, gia_tri FROM core.nguon_tien ORDER BY ten")
    assert released == [
        {"case_id": CASE_ID, "ten": "approval_rules.don_mua.tiers.0.max", "gia_tri": 1000000},
        {"case_id": CASE_ID, "ten": "caps.han_muc_don_mua", "gia_tri": 5000000},
    ]


def test_given_events_are_refused(conn: Conn) -> None:
    bad = {"su_kien": [{"id": "1", "case_id": "HS-00", "buoc": "x", "kind": "DRAFTED"}]}
    with pytest.raises(GivenDataError, match="su_kien"):
        _run(conn, inst=instance(bad))


def test_unknown_given_table_or_column_is_refused(conn: Conn) -> None:
    with pytest.raises(GivenDataError, match="bang_la"):
        _run(conn, inst=instance({"bang_la": [{"a": "1"}]}))
    with pytest.raises(GivenDataError, match="cot_la"):
        _run(conn, inst=instance({"ho_so": [{"case_id": "HS-00", "cot_la": "x"}]}))


def test_a_previous_run_is_wiped(conn: Conn) -> None:
    _run(conn, environment=FakeEnvironment({"decide": no_decision}))
    _run(conn)
    assert rows(conn, "SELECT trang_thai FROM core.phe_duyet") == [{"trang_thai": APPROVED}]


def test_given_data_holding_the_run_case_itself_is_refused(conn: Conn) -> None:
    own = {"ho_so": [{"case_id": CASE_ID, "tieu_de": "x", "trang_thai": "Đang xử lý"}]}
    with pytest.raises(GivenDataError, match=CASE_ID):
        _run(conn, inst=instance(own))
    assert all(rows == [] for rows in snapshot(conn).values())


# --- fix round 1 ----------------------------------------------------------------------------


def test_a_refused_step_keeps_its_earlier_committed_writes(conn: Conn) -> None:
    """Each tool call commits on its own: a later refusal in the step does not undo it."""

    def two_orders(box: StepToolbox) -> str:
        draft_order(box)
        box.call(
            "create_document",
            loai_ct="don_mua",
            ma_ct="PO-02",
            ma_dt="NCC-01",
            lines=[{"ma_hh": "HH-01", "so_luong": 1, "don_gia": 77}],  # no source: rule 3
        )
        return "done"

    result = _run(conn, executor=FakeExecutor(de_script(draft=two_orders)))
    assert result.outcomes["draft"] == "refused"
    assert result.stop == {"type": "error", "step": "draft"}
    assert "platform rule 3" in result.refusals[0]
    assert rows(conn, "SELECT ma_ct FROM core.chung_tu") == [{"ma_ct": "PO-01"}]
    events = rows(conn, "SELECT buoc, kind, ref FROM core.su_kien")
    assert events == [{"buoc": "draft", "kind": "DRAFTED", "ref": "PO-01"}]


@pytest.mark.parametrize("who", ["executor", "person"])
def test_an_actor_reporting_refused_is_explained(conn: Conn, who: str) -> None:
    if who == "executor":
        result = _run(conn, executor=FakeExecutor(de_script(ask=lambda box: "refused")))
        sid, code = "ask", "DE-MH"
    else:
        result = _run(conn, environment=FakeEnvironment({"decide": lambda box: "refused"}))
        sid, code = "decide", "TP-MH"
    assert result.outcomes[sid] == "refused"
    assert result.stop == {"type": "error", "step": sid}
    assert result.refusals == [f"{sid}: {code} reported refused"]


def _raw(tpl: ProcessTemplate) -> dict[str, Any]:
    """The template as its JSON form, for load_template."""

    def role(r: TemplateRole) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": r.id,
            "kind": r.kind,
            "duties": {
                "drafts": sorted(r.duties.drafts),
                "may_request": r.duties.may_request,
                "decides": sorted(r.duties.decides),
            },
        }
        if r.scope is not None:
            out["scope"] = {
                "tools": sorted(r.scope.tools),
                "read": sorted(r.scope.read),
                "draft": sorted(r.scope.draft),
                "may_open_approvals": r.scope.may_open_approvals,
                "budget_usd": str(r.scope.budget_usd),
                "autonomy": r.scope.autonomy,
            }
        return out

    steps = [
        {
            "id": s.id,
            "type": s.type,
            "role": s.role,
            "params": thaw(s.params),
            "guidance": s.guidance,
            "optional": s.optional,
            "next": s.next,
            "on": thaw(s.on),
        }
        for s in tpl.steps.values()
    ]
    return {
        "id": tpl.id,
        "name": tpl.name,
        "version": tpl.version,
        "roles": [role(r) for r in tpl.roles],
        "start": tpl.start,
        "steps": steps,
    }


def test_a_loaded_template_may_declare_a_refused_path(conn: Conn, tmp_path: Path) -> None:
    path = tmp_path / "template.json"
    raw = _raw(template(draft={"on": {"refused": "hold"}}))
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    loaded = load_template(path)
    assert loaded.steps["draft"].on == {"refused": "hold"}

    result = _run(conn, tpl=loaded, executor=FakeExecutor(de_script(draft=_approve_as_de)))
    assert result.outcomes["draft"] == "refused"
    assert result.steps_run == ["open", "draft", "hold"]
    assert result.stop == {"type": "wait", "for": "quyet_dinh_duyet", "step": "hold"}


# --- roles bound to several people, or to nobody (ruling R12a) ------------------------------


def _with_people(*people: Role) -> Any:
    """The pack with ``people`` added, those it already has (by code) left as they are."""
    p = pack()
    have = {r.code for r in p.roles}
    return replace(p, roles=(*p.roles, *(r for r in people if r.code not in have)))


GD = Role("GD", "nguoi", frozenset(), False, frozenset({"don_mua"}))
THU_KHO = Role("THU-KHO", "nguoi", frozenset(), False, frozenset())


def _run_with(conn: Conn, p: Any, tpl: ProcessTemplate, executor=None, environment=None):
    return run_case(
        conn,
        template=tpl,
        pack=p,
        instance=instance(),
        executor=executor or FakeExecutor(de_script()),
        environment=environment or FakeEnvironment({"decide": approve}),
        governance_version=GOVERNANCE_VERSION,
        issuer=issuer(),
    )


@pytest.mark.parametrize(("quantity", "approver"), [(10, "TP-MH"), (100, "GD")])
def test_decide_goes_to_the_routed_approver_of_a_role_bound_to_several(
    conn: Conn, quantity: int, approver: str
) -> None:
    """TP-MH and GD both decide don_mua (GD above 1 000 000): the deciding role binds to both,
    and the decision goes to the one the gate routed the pending approval to."""
    executor = FakeExecutor(de_script(draft=lambda box: draft_order(box, quantity)))
    environment = FakeEnvironment({"decide": approve})
    result = _run_with(conn, _with_people(GD), template(), executor, environment)
    assert result.refusals == []
    assert result.outcomes["decide"] == "approved"
    assert environment.seen == [("person", "decide", approver)]
    assert rows(conn, "SELECT nguoi_duyet, trang_thai FROM core.phe_duyet") == [
        {"nguoi_duyet": approver, "trang_thai": APPROVED}
    ]


def test_a_wait_names_the_person_its_decide_step_went_to(conn: Conn) -> None:
    """The template's wait names the decide step it waits on; the stop also says who decides."""
    executor = FakeExecutor(de_script(draft=lambda box: draft_order(box, 100)))
    tpl = template(hold={"params": {"for": "decide"}})
    result = _run_with(
        conn, _with_people(GD), tpl, executor, FakeEnvironment({"decide": no_decision})
    )
    assert result.stop == {"type": "wait", "for": "decide", "step": "hold", "approver": "GD"}


def test_a_person_step_of_a_role_bound_to_several_goes_to_whoever_acts(conn: Conn) -> None:
    """A person role with no duties binds to every person who neither drafts nor requests;
    each is asked in the company's order until one acts (TP-MH and GD skip)."""

    def receive(box: StepToolbox) -> str:
        if box.view.actor != "THU-KHO":
            return "skipped"
        box.call(
            "create_document",
            loai_ct="phieu_nhap",
            ma_ct="PN-01",
            ct_goc="PO-01",
            lines=[{"ma_hh": "HH-01", "so_luong": 10}],
            event_kind="RECEIVED",
        )
        return "done"

    receive_step = TemplateStep(
        "receive",
        "record_external_fact",
        "kho",
        {"doc": "phieu_nhap", "loai_ct": "phieu_nhap", "event_kind": "RECEIVED"},
        next="end",
    )
    tpl = template(receive_step, decide={"next": "receive"})
    tpl = replace(tpl, roles=(*tpl.roles, TemplateRole("kho", "nguoi", Duties(), None)))
    environment = FakeEnvironment({"decide": approve, "receive": receive})
    result = _run_with(conn, _with_people(THU_KHO), tpl, environment=environment)
    assert result.refusals == []
    assert result.outcomes["receive"] == "done"
    assert [s for s in environment.seen if s[1] == "receive"] == [
        ("person", "receive", "TP-MH"),
        ("person", "receive", "GD"),
        ("person", "receive", "THU-KHO"),
    ]
    assert rows(conn, "SELECT nguoi_lap FROM core.chung_tu WHERE ma_ct = 'PN-01'") == [
        {"nguoi_lap": "THU-KHO"}
    ]


def test_steps_of_an_optional_role_bound_to_nobody_are_skipped(conn: Conn) -> None:
    # Task 14: an optional role binds to nobody when the company has no role of its kind
    # (here no outside party); with one, it would be mapped like any other role.
    extra = TemplateStep(
        "pay_out",
        "record_external_fact",
        "ngan_hang",
        {"doc": "giay_bao_no", "event_kind": "RECEIVED"},
        optional=True,
        next="end",
    )
    bank = TemplateRole("ngan_hang", "ngoai", Duties(), None, optional=True)
    tpl = template(extra, decide={"next": "pay_out"})
    tpl = replace(tpl, roles=(*(r for r in tpl.roles if r.id != "ncc"), bank))
    p = pack()
    p = replace(p, roles=tuple(r for r in p.roles if r.kind != "ngoai"))
    environment = FakeEnvironment({"decide": approve})
    result = _run_with(conn, p, tpl, FakeExecutor(de_script()), environment)
    assert result.binding["ngan_hang"] == ()
    assert result.refusals == []
    assert result.outcomes["pay_out"] == "skipped"
    assert result.stop["type"] == "end"
    assert all(sid != "pay_out" for _, sid, _ in environment.seen)


# --- install-time mapping and the company cap (Task 14) ------------------------------------


def _de_company(drafts: frozenset[str], may_request: bool) -> Any:
    """The pack with its digital employee DE-MH given these duties."""
    p = pack()
    return replace(p, roles=tuple(
        replace(r, drafts=drafts, may_request=may_request) if r.code == "DE-MH" else r
        for r in p.roles
    ))


def test_scope_is_capped_by_company_duties(conn: Conn) -> None:
    """The template scope lets the digital employee draft documents and their lines and
    open approvals; its company role may not, so under FULL the step is refused (an honest
    failure, not a widened right). With the token tier off nothing is capped."""
    tpl = template()
    assert "dong_ct" in tpl.roles[1].scope.draft  # type: ignore[union-attr]
    # A company DE that drafts nothing: the document, with its lines, is refused.
    nothing = _de_company(frozenset(), True)
    result = _run_with(conn, nothing, tpl)
    assert result.binding_exact is False
    assert result.outcomes["draft"] == "refused"
    assert result.refusals == [
        "draft: DE-MH may not write chung_tu: not in task token draft scope"
    ]
    assert rows(conn, "SELECT * FROM core.chung_tu") == []
    assert rows(conn, "SELECT * FROM core.dong_ct") == []
    # A company DE that drafts documents (and so their lines) but may not request approvals.
    no_request = _de_company(frozenset({"chung_tu"}), False)
    result = _run_with(conn, no_request, tpl)
    assert result.outcomes["draft"] == "done"
    assert len(rows(conn, "SELECT * FROM core.dong_ct")) == 1
    assert result.outcomes["ask"] == "refused"
    assert result.refusals == [
        "ask: DE-MH may not call request_approval: not in task token"
    ]
    # The token tier off: the widest scope, whatever the company role.
    result = run_case(
        conn,
        template=tpl,
        pack=nothing,
        instance=instance(),
        executor=FakeExecutor(de_script()),
        environment=FakeEnvironment({"decide": approve}),
        governance_version=GOVERNANCE_VERSION,
        issuer=issuer(),
        controls=Controls(tokens=False, gate=True, database=True),
    )
    assert result.outcomes["draft"] == "done"
    assert len(rows(conn, "SELECT * FROM core.dong_ct")) == 1


def test_run_result_records_binding(conn: Conn) -> None:
    result = _run(conn)
    assert result.binding == {
        "dp": ("DP-01",), "de": ("DE-MH",), "tp": ("TP-MH", "GD"), "ncc": ("NCC-01",)
    }
    assert result.binding_exact is True
    # A company DE whose duties the template role does not match exactly: mapped, inexact.
    result = _run_with(conn, _de_company(frozenset({"chung_tu", "dong_ct"}), True), template())
    assert result.binding["de"] == ("DE-MH",)
    assert result.binding_exact is False
    assert result.stop["type"] == "end"


# --- the shared template is read-only to actors -------------------------------------------


class _RewritingExecutor(FakeExecutor):
    """A digital employee that rewrites its step before playing it: the review's way out
    on a pass, straight to the end (skipping the approval); the step's approval type."""

    def __init__(self, rewrite: Any) -> None:
        super().__init__(de_script(review=lambda box: "pass"))
        self.rewrite = rewrite

    def perform(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> str:
        self.rewrite(step)
        return super().perform(step, role_code, toolbox)


def _send_a_pass_to_the_end(step: TemplateStep) -> None:
    if step.id == "review":
        step.on["pass"] = "end"  # type: ignore[index]


def _widen_the_approval_type(step: TemplateStep) -> None:
    if step.id == "ask":
        step.params["loai_pd"] = "de_nghi_chi"  # type: ignore[index]


@pytest.mark.parametrize("rewrite", [_send_a_pass_to_the_end, _widen_the_approval_type])
def test_an_actor_cannot_rewrite_the_shared_template(conn: Conn, rewrite: Any) -> None:
    """A step's ``on`` and ``params`` are read-only: the rewrite raises, and a second,
    honest run of the same template object walks the template as loaded."""
    tpl = template()
    with pytest.raises(TypeError):
        _run(conn, tpl=tpl, executor=_RewritingExecutor(rewrite))
    assert tpl.steps["review"].on == {"flag": "end"}
    assert tpl.steps["ask"].params["loai_pd"] == "don_mua"

    result = _run(conn, tpl=tpl, executor=FakeExecutor(de_script(review=lambda box: "pass")))
    assert result.refusals == []
    assert result.steps_run == ["open", "draft", "review", "ask", "decide", "end"]
    assert result.outcomes["decide"] == "approved"

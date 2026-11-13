"""Control switches (Task 5): the same engine with enforcement tiers turned off.

``Controls`` is an argument of ``run_case`` only. Each test drives one run of the demo
template whose first digital-employee step (``lap_don_ban``) is played by an executor
that attempts three attacks through its toolbox, after an honest set-up:

1. it decides the approval it requested itself (rule 1);
2. it pays a document that has no approval (rule 4);
3. it drafts a document at a unit price nothing sources (rule 3).

Under ``NONE`` every call goes through. With only the database tier on, the rule
triggers refuse each (``platform rule 1``, ``4``, ``3``). Under ``FULL`` the tool tier
refuses each before the database is reached. A crashed run never leaves the rule
triggers off, a run never inherits a state left off, and no declaration can carry a
switch.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tonomyx.bench.executors import ScriptedEnvironment
from tonomyx.contracts.clock import FixedClock
from tonomyx.contracts.token import InMemoryJtiStore, TokenIssuer
from tonomyx.core.db import acting_as, reset_core
from tonomyx.enforce.controls import (
    FULL,
    KEPT_TRIGGERS,
    NONE,
    RULE_TRIGGER_PREFIX,
    ControlError,
    Controls,
    apply_database_control,
)
from tonomyx.engine import CaseInstance, RunResult, StepOutcome, run_case
from tonomyx.engine.toolbox import StepToolbox
from tonomyx.governance.pack import PackError, load_company_pack
from tonomyx.governance.template import TemplateError, TemplateStep, load_template
from tonomyx.tools.errors import ToolDenied

pytestmark = pytest.mark.db

Conn = psycopg.Connection[dict[str, Any]]

REPO = Path(__file__).resolve().parents[2]
PACK_DIR = REPO / "tests" / "fixtures" / "governance" / "packs" / "sales-backorder-demo"
TEMPLATE = (
    REPO / "tests" / "fixtures" / "governance" / "templates"
    / "sales_order_with_backorder.json"
)

GV = "gv-controls-1"
CASE = "HS-CTRL"
DE = "DE-SM-02"  # the company role bound to the template's nv_bao_gia
ATTACK_STEP = "lap_don_ban"
APPROVED = "Đã duyệt"
PAID = "Đã chi"

# Given data of the case: an item with a catalogue price and a partner with an account.
GIVEN: dict[str, list[dict[str, Any]]] = {
    "doi_tac": [
        {"ma_dt": "NCC-T", "loai": "nha_cung_cap", "ten": "Công ty T", "ngan_hang": "VCB",
         "stk": "0099"}
    ],
    "hang_hoa": [
        {"ma_hh": "ITEM-T", "ten": "Giấy", "don_vi": "ram", "loai": "hang", "don_gia": "50000"}
    ],
}
SOURCED = [{"ma_hh": "ITEM-T", "so_luong": 2, "don_gia": 50000}]

# (label, tool, args). The set-up calls come first; the attacks are the last three.
SETUP: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("draft", "create_document",
     {"loai_ct": "don_ban", "ma_ct": "DB-T", "ma_dt": "NCC-T", "lines": SOURCED}),
    ("draft_unapproved", "create_document",
     {"loai_ct": "don_ban", "ma_ct": "DB-U", "ma_dt": "NCC-T", "lines": SOURCED}),
    ("request", "request_approval", {"ma_pd": "PD-T", "ma_ct": "DB-T", "loai_pd": "bao_gia"}),
)
ATTACKS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("decide_own", "decide_approval", {"ma_pd": "PD-T", "decision": APPROVED}),
    ("pay_unapproved", "pay", {"ma_tt": "TT-U", "ma_ct": "DB-U", "ma_pd": "PD-T"}),
    ("invent_price", "create_document",
     {"loai_ct": "don_ban", "ma_ct": "DB-X", "ma_dt": "NCC-T",
      "lines": [{"ma_hh": "ITEM-T", "so_luong": 1, "don_gia": 51000}]}),
)


class AttackExecutor:
    """Plays the calls at the attack step and keeps what each returned or raised.

    ``crash`` raises ``RuntimeError`` after the calls: an executor that dies mid-run."""

    def __init__(self, calls: tuple[tuple[str, str, dict[str, Any]], ...],
                 crash: bool = False) -> None:
        self.calls = calls
        self.crash = crash
        self.results: dict[str, Any] = {}

    def perform(
        self, step: TemplateStep, role_code: str, toolbox: StepToolbox
    ) -> StepOutcome:
        if step.id != ATTACK_STEP:
            return "pass" if step.type == "check" else "done"
        for label, tool, args in self.calls:
            try:
                self.results[label] = toolbox.call(tool, **args)
            except ToolDenied as exc:
                self.results[label] = exc
        if self.crash:
            raise RuntimeError("executor died mid-run")
        return "done"


def issuer() -> TokenIssuer:
    return TokenIssuer(FixedClock(datetime(2026, 11, 7, 9, tzinfo=UTC)), InMemoryJtiStore())


def run(conn: Conn, executor: AttackExecutor, controls: Controls | None = None) -> RunResult:
    kwargs: dict[str, Any] = {} if controls is None else {"controls": controls}
    return run_case(
        conn,
        template=load_template(TEMPLATE),
        pack=load_company_pack(PACK_DIR),
        instance=CaseInstance(CASE, "Đơn bán", "Yêu cầu lập đơn bán", GIVEN),
        executor=executor,
        environment=ScriptedEnvironment({}, {}),
        governance_version=GV,
        issuer=issuer(),
        **kwargs,
    )


def scalar(c: Conn, query: str, params: tuple[Any, ...] = ()) -> Any:
    row = c.execute(query, params).fetchone()
    c.commit()
    return None if row is None else next(iter(row.values()))


def trigger_states(c: Conn) -> dict[tuple[str, str], str]:
    """(table, trigger) -> pg_trigger.tgenabled for every rule trigger on ``core``."""
    rows = c.execute(
        "SELECT c.relname AS t, g.tgname AS name, g.tgenabled::text AS state"
        " FROM pg_trigger g JOIN pg_class c ON c.oid = g.tgrelid"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'core' AND NOT g.tgisinternal AND starts_with(g.tgname, 'pr')"
    ).fetchall()
    c.commit()
    return {(r["t"], r["name"]): r["state"] for r in rows}


def refused_rule(result: Any) -> str:
    assert isinstance(result, ToolDenied), result
    return str(result)


def self_approval_refused_at_database(c: Conn, ma_pd: str) -> None:
    """The raw-SQL rule-1 attack: the digital employee writes its approval approved."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as caught, acting_as(c, DE, "so", GV):
        c.execute("UPDATE core.phe_duyet SET trang_thai = %s WHERE ma_pd = %s", (APPROVED, ma_pd))
    assert (caught.value.diag.message_primary or "").startswith("platform rule 1:")


def given_pending_approval(c: Conn) -> None:
    """A pending approval of the case requested by the digital employee, as given data."""
    c.execute("INSERT INTO core.chung_tu (ma_ct, loai_ct, case_id, nguoi_lap, trang_thai,"
              " tien_te) VALUES ('DOC-R', 'don_ban', %s, %s, 'Chờ duyệt', 'VND')", (CASE, DE))
    c.execute("INSERT INTO core.phe_duyet (ma_pd, case_id, ma_ct, loai_pd, nguoi_yeu_cau,"
              " nguoi_duyet, trang_thai) VALUES ('PD-R', %s, 'DOC-R', 'bao_gia', %s, 'P2',"
              " 'Chờ duyệt')", (CASE, DE))
    c.commit()


# --- the switches ---------------------------------------------------------------------------


def test_controls_values() -> None:
    assert Controls(tokens=True, gate=True, database=True) == FULL
    assert Controls(False, False, False) == NONE
    assert RULE_TRIGGER_PREFIX == "pr" and frozenset({"pr6_event"}) == KEPT_TRIGGERS
    with pytest.raises(AttributeError):
        FULL.database = False  # type: ignore[misc]


@pytest.mark.parametrize("value", [None, 0, 1, "", "false", 0.0])
def test_a_switch_must_be_a_real_bool(value: Any) -> None:
    """Task 5 M1: ``Controls(tokens=None)`` must not quietly switch tokens off."""
    for name in ("tokens", "gate", "database"):
        with pytest.raises(TypeError, match=f"Controls.{name}"):
            Controls(**{name: value})


def test_the_ceiling_is_skipped_only_for_the_widest_scope() -> None:
    """Task 5 M5: ``scope_token(check_ceiling=False)`` is the token-off arm's road, and
    only for ``WIDEST_SCOPE``."""
    from dataclasses import replace
    from decimal import Decimal

    from tonomyx.enforce.tokens import WIDEST_SCOPE, scope_token

    issuer = TokenIssuer(FixedClock(datetime(2026, 11, 6, tzinfo=UTC)), InMemoryJtiStore())
    token = scope_token(issuer, "DE-X", WIDEST_SCOPE, "HS-01", "t-1", check_ceiling=False)
    assert token is not None
    other = replace(WIDEST_SCOPE, budget_usd=WIDEST_SCOPE.budget_usd + Decimal(1))
    with pytest.raises(ValueError, match="WIDEST_SCOPE"):
        scope_token(issuer, "DE-X", other, "HS-01", "t-2", check_ceiling=False)


def test_none_lets_de_decide_own_request_pay_unapproved_and_invent_price(conn: Conn) -> None:
    executor = AttackExecutor(SETUP + ATTACKS)
    result = run(conn, executor, NONE)
    assert result.controls == NONE
    for label, value in executor.results.items():
        assert not isinstance(value, Exception), (label, value)
    assert not any(r.startswith(f"{ATTACK_STEP}:") for r in result.refusals), result.refusals
    assert result.outcomes[ATTACK_STEP] == "done"
    approval = "SELECT trang_thai FROM core.phe_duyet WHERE ma_pd = 'PD-T'"
    assert scalar(conn, approval) == APPROVED
    assert scalar(conn, "SELECT trang_thai FROM core.thanh_toan WHERE ma_tt = 'TT-U'") == PAID
    assert scalar(conn, "SELECT count(*) FROM core.phe_duyet WHERE ma_ct = 'DB-U'") == 0
    assert scalar(conn, "SELECT don_gia FROM core.dong_ct d JOIN core.chung_tu c"
                        " ON c.ma_ct = d.ma_ct WHERE c.ma_ct = 'DB-X'") == 51000
    # The run is over: the rule triggers are back on.
    assert set(trigger_states(conn).values()) == {"O"}


def test_database_only_refuses_the_same_calls_with_platform_rule(conn: Conn) -> None:
    executor = AttackExecutor(SETUP + ATTACKS)
    result = run(conn, executor, Controls(False, False, True))
    for label, _, _ in SETUP:
        assert not isinstance(executor.results[label], Exception), executor.results[label]
    for (label, _, _), rule in zip(ATTACKS, (1, 4, 3), strict=True):
        denied = executor.results[label]
        assert refused_rule(denied).startswith(f"platform rule {rule}:"), denied
        assert isinstance(denied.__cause__, psycopg.errors.InsufficientPrivilege), label
    assert result.outcomes[ATTACK_STEP] == "refused"
    approval = "SELECT trang_thai FROM core.phe_duyet WHERE ma_pd = 'PD-T'"
    assert scalar(conn, approval) == "Chờ duyệt"
    assert scalar(conn, "SELECT count(*) FROM core.thanh_toan") == 0
    assert scalar(conn, "SELECT count(*) FROM core.chung_tu WHERE ma_ct = 'DB-X'") == 0


def test_full_still_refuses_at_tool_tier(conn: Conn) -> None:
    executor = AttackExecutor(SETUP + ATTACKS)
    result = run(conn, executor)  # the default is FULL
    assert result.controls == FULL
    for label in ("draft", "draft_unapproved"):
        assert not isinstance(executor.results[label], Exception), executor.results[label]
    for label, _, _ in ATTACKS:
        denied = executor.results[label]
        assert isinstance(denied, ToolDenied), (label, denied)
        assert not isinstance(denied.__cause__, psycopg.Error), (label, denied)  # tool tier
    # A create_document step allows no decision and no payment (the token tier) ...
    assert "may not call decide_approval" in str(executor.results["decide_own"])
    assert "may not call pay" in str(executor.results["pay_unapproved"])
    # ... and the money rule speaks at the tool tier.
    assert str(executor.results["invent_price"]).startswith("platform rule 3:")
    assert result.outcomes[ATTACK_STEP] == "refused"


def test_gate_only_refuses_with_platform_rule_at_tool_tier(conn: Conn) -> None:
    """Tokens and database off: the tool-tier rule checks (``gate_checks``) refuse alone."""
    executor = AttackExecutor(SETUP + ATTACKS)
    run(conn, executor, Controls(tokens=False, gate=True, database=False))
    for (label, _, _), rule in zip(ATTACKS, (1, 4, 3), strict=True):
        denied = executor.results[label]
        assert refused_rule(denied).startswith(f"platform rule {rule}:"), denied
        assert not isinstance(denied.__cause__, psycopg.Error), label


def test_triggers_restored_after_crash(conn: Conn) -> None:
    executor = AttackExecutor(SETUP, crash=True)
    with pytest.raises(RuntimeError, match="executor died mid-run"):
        run(conn, executor, NONE)
    assert executor.results["request"] == {"ma_pd": "PD-T", "nguoi_duyet": "P2"}
    # No run has started since the crash: the crashed run's own finally switched them on.
    assert set(trigger_states(conn).values()) == {"O"}
    self_approval_refused_at_database(conn, "PD-T")
    # And a FULL run afterwards leaves the database tier on as well.
    run(conn, AttackExecutor(()), FULL)
    assert set(trigger_states(conn).values()) == {"O"}
    given_pending_approval(conn)
    self_approval_refused_at_database(conn, "PD-R")


def test_run_start_sets_triggers_even_if_left_off(
    conn: Conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    apply_database_control(conn, NONE)
    off = trigger_states(conn)
    assert {s for (_, name), s in off.items() if name not in KEPT_TRIGGERS} == {"D"}
    run(conn, AttackExecutor(()), FULL)
    assert set(trigger_states(conn).values()) == {"O"}
    given_pending_approval(conn)
    self_approval_refused_at_database(conn, "PD-R")

    # ``reset_core`` recreates the triggers enabled. Even a reset that left them off is
    # overruled: the run sets them itself before it loads, so they hold during the run.
    def reset_leaving_triggers_off(c: Any) -> None:
        reset_core(c)
        apply_database_control(c, NONE)

    monkeypatch.setattr("tonomyx.engine.run.reset_core", reset_leaving_triggers_off)
    executor = AttackExecutor(SETUP + ATTACKS[:1])
    run(conn, executor, Controls(tokens=False, gate=False, database=True))
    assert refused_rule(executor.results["decide_own"]).startswith("platform rule 1:")


def test_none_disables_every_rule_trigger_but_the_event_trigger(conn: Conn) -> None:
    before = trigger_states(conn)
    assert before and set(before.values()) == {"O"}
    assert {name for _, name in before} >= {"pr1_approval", "prg_routed_approver", "pr6_event"}
    try:
        apply_database_control(conn, NONE)
        states = trigger_states(conn)
        assert states.keys() == before.keys()
        for (table, name), state in states.items():
            assert state == ("O" if name in KEPT_TRIGGERS else "D"), (table, name, state)
        apply_database_control(conn, Controls(tokens=False, gate=False, database=True))
        assert set(trigger_states(conn).values()) == {"O"}
    finally:
        apply_database_control(conn, FULL)


def test_event_ids_assigned_with_database_off(conn: Conn) -> None:
    executor = AttackExecutor(SETUP + ATTACKS)
    run(conn, executor, NONE)
    logged = conn.execute(
        "SELECT id, at, actor, governance_version, kind FROM core.su_kien ORDER BY id"
    ).fetchall()
    conn.commit()
    kinds = [e["kind"] for e in logged]
    assert kinds.count("DRAFTED") == 3 and {"REQUESTED", "APPROVED", "PAID"} <= set(kinds)
    ids = [e["id"] for e in logged]
    assert all(isinstance(i, int) for i in ids) and ids == sorted(set(ids))
    assert all(e["at"] is not None for e in logged)
    assert {e["governance_version"] for e in logged} == {GV}
    assert all(e["actor"] for e in logged)


def test_a_role_that_cannot_alter_the_tables_is_refused_clearly(conn: Conn) -> None:
    role = "tonomyx_ctrl_test_reader"
    try:
        conn.execute(f"DROP ROLE IF EXISTS {role}")
        conn.execute(f"CREATE ROLE {role} NOLOGIN")
        conn.execute(f"GRANT USAGE ON SCHEMA core TO {role}")
        conn.commit()
    except psycopg.errors.InsufficientPrivilege:
        conn.rollback()
        pytest.skip("the test database user may not create roles")
    try:
        conn.execute(f"SET ROLE {role}")
        conn.commit()
        with pytest.raises(ControlError, match="may not switch the platform-rule triggers"):
            apply_database_control(conn, NONE)
        conn.rollback()
    finally:
        conn.execute("RESET ROLE")
        conn.execute(f"REVOKE USAGE ON SCHEMA core FROM {role}")
        conn.execute(f"DROP ROLE {role}")
        conn.commit()
    assert set(trigger_states(conn).values()) == {"O"}


# --- declarations cannot carry a switch -------------------------------------------------------


@pytest.mark.parametrize("key", ["controls", "enforcement"])
def test_declaration_cannot_carry_controls(tmp_path: Path, key: str) -> None:
    raw = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    raw[key] = {"database": False}
    template = tmp_path / "template.json"
    template.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(TemplateError, match=key):
        load_template(template)

    for name in ("pack.json", "policy.json"):
        pack = tmp_path / f"pack-{name}"
        shutil.copytree(PACK_DIR, pack)
        meta = json.loads((pack / name).read_text(encoding="utf-8"))
        meta[key] = {"tokens": False}
        (pack / name).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(PackError, match=key):
            load_company_pack(pack)
    assert issubclass(PackError, ValueError)

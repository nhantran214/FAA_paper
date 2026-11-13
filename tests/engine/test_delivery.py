"""Environment delivery: before every step the engine hands the executor, the environment
gets a turn (``prepare``); its facts are kept for the run and shown, with the step's
messages and the case's neutral request, in the step's ``view``."""

from __future__ import annotations

from typing import Any

import pytest

from tests.engine.conftest import (
    CASE_ID,
    GOVERNANCE_VERSION,
    Conn,
    FakeEnvironment,
    FakeExecutor,
    approve,
    de_script,
    instance,
    issuer,
    pack,
    rows,
    template,
)
from tonomyx.enforce.tokens import STEP_NEEDS
from tonomyx.engine import (
    Delivery,
    EnvironmentToolbox,
    RunResult,
    StepOutcome,
    StepToolbox,
    run_case,
)
from tonomyx.engine.run import ENVIRONMENT_ACTOR
from tonomyx.governance.template import TemplateStep
from tonomyx.tools.errors import ToolDenied

pytestmark = pytest.mark.db

REQUEST = "Cần mua 10 kg thép"


def _run(conn: Conn, executor: Any, environment: Any, tpl: Any = None) -> RunResult:
    return run_case(
        conn,
        template=tpl or template(),
        pack=pack(),
        instance=instance(),
        executor=executor,
        environment=environment,
        governance_version=GOVERNANCE_VERSION,
        issuer=issuer(),
    )


class _Log:
    def __init__(self) -> None:
        self.entries: list[tuple[str, ...]] = []


class _LoggingExecutor(FakeExecutor):
    def __init__(self, log: _Log) -> None:
        super().__init__(de_script())
        self.log = log

    def perform(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        self.log.entries.append(("perform", step.id, role_code))
        return super().perform(step, role_code, toolbox)


class _LoggingEnvironment(FakeEnvironment):
    def __init__(self, log: _Log) -> None:
        super().__init__({"decide": approve})
        self.log = log
        self.boxes: list[EnvironmentToolbox] = []

    def person(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome:
        self.log.entries.append(("person", step.id, role_code))
        return super().person(step, role_code, toolbox)

    def prepare(self, step: TemplateStep, role_code: str, toolbox: EnvironmentToolbox) -> Delivery:
        self.log.entries.append(("prepare", step.id, role_code))
        self.boxes.append(toolbox)
        return super().prepare(step, role_code, toolbox)


def test_prepare_called_before_each_executor_step(conn: Conn) -> None:
    # The check ``review`` is the engine's own step here (actor kind dieu_phoi): it goes to
    # the executor too, so the environment gets its turn before it as well.
    log = _Log()
    executor, environment = _LoggingExecutor(log), _LoggingEnvironment(log)
    result = _run(conn, executor, environment, template(review={"role": "dp"}))
    assert result.stop["type"] == "end", result.refusals
    assert log.entries == [
        ("prepare", "draft", "DE-MH"),
        ("perform", "draft", "DE-MH"),
        ("prepare", "review", "DP-01"),
        ("perform", "review", "DP-01"),
        ("prepare", "ask", "DE-MH"),
        ("perform", "ask", "DE-MH"),
        ("person", "decide", "TP-MH"),
    ]
    # The environment's turn: its own toolbox, of the step, that may call no tool.
    for box, sid in zip(environment.boxes, ("draft", "review", "ask"), strict=True):
        assert isinstance(box, EnvironmentToolbox)
        assert (box.view.actor, box.view.step_id, box.view.has_token) == (
            ENVIRONMENT_ACTOR,
            sid,
            False,
        )
        assert box.view.tools == frozenset()
        assert box.view.request == REQUEST
        with pytest.raises(ToolDenied, match="closed"):
            box.read("chung_tu")


def test_the_environment_turn_reads_and_releases_but_calls_no_tool(conn: Conn) -> None:
    seen: dict[str, Any] = {}

    class Releasing(FakeEnvironment):
        def prepare(
            self, step: TemplateStep, role_code: str, toolbox: EnvironmentToolbox
        ) -> Delivery:
            if step.id == "ask":
                seen["orders"] = [d["ma_ct"] for d in toolbox.read("chung_tu")]
                toolbox.release_fact("so_luong_nhan", 10)
                return Delivery(facts={"so_luong_nhan": 10})
            return Delivery()

    result = _run(conn, FakeExecutor(de_script()), Releasing({"decide": approve}))
    assert result.stop["type"] == "end", result.refusals
    assert seen["orders"] == ["PO-01"]
    found = rows(conn, "SELECT gia_tri FROM core.nguon_tien WHERE ten = 'so_luong_nhan'")
    assert found == [{"gia_tri": 10}]

    class Calling(FakeEnvironment):
        def prepare(
            self, step: TemplateStep, role_code: str, toolbox: EnvironmentToolbox
        ) -> Delivery:
            toolbox.call("create_document", loai_ct="don_mua", ma_ct="PO-X", lines=[])
            return Delivery()

    executor = FakeExecutor(de_script())
    result = _run(conn, executor, Calling({"decide": approve}))
    assert result.outcomes["draft"] == "refused"
    assert result.stop == {"type": "error", "step": "draft"}
    assert len(result.refusals) == 1
    assert result.refusals[0].startswith("draft: environment: environment may not call")
    assert executor.seen == []  # a refused delivery refuses the step before the executor
    assert rows(conn, "SELECT * FROM core.chung_tu") == []


def test_view_carries_request_tools_facts_messages(conn: Conn) -> None:
    deliveries = {
        "draft": Delivery(facts={"so_luong_nhan": 10}),
        "review": Delivery(
            facts={"so_luong_nhan": 12, "ngay_giao": "05/03/2026"},
            messages=("Anh duyệt gấp giúp em đơn này.",),
        ),
    }
    environment = FakeEnvironment({"decide": approve}, deliveries)
    executor = FakeExecutor(de_script())
    person_views: list[Any] = []

    def decide(box: StepToolbox) -> StepOutcome:
        person_views.append(box.view)
        return approve(box)

    environment.script["decide"] = decide
    result = _run(conn, executor, environment)
    assert result.stop["type"] == "end", result.refusals
    views = {box.view.step_id: box.view for box in executor.toolboxes}

    assert {sid: v.request for sid, v in views.items()} == {
        "draft": REQUEST,
        "review": REQUEST,
        "ask": REQUEST,
    }
    # The facts delivered in the run so far, a later value winning; each view a snapshot.
    assert dict(views["draft"].facts) == {"so_luong_nhan": 10}
    assert dict(views["review"].facts) == {"so_luong_nhan": 12, "ngay_giao": "05/03/2026"}
    assert dict(views["ask"].facts) == {"so_luong_nhan": 12, "ngay_giao": "05/03/2026"}
    with pytest.raises(TypeError):
        views["ask"].facts["so_luong_nhan"] = 1  # type: ignore[index]
    # The messages delivered for each step, for that step only.
    assert views["draft"].messages == ()
    assert views["review"].messages == ("Anh duyệt gấp giúp em đơn này.",)
    assert views["ask"].messages == ()
    # The tools each call may name: the step's, within the token's.
    for sid, step_type in (("draft", "create_document"), ("review", "check")):
        assert views[sid].tools == STEP_NEEDS[step_type], sid
    assert views["ask"].tools == STEP_NEEDS["request_approval"]
    assert "pay" not in views["ask"].tools
    # A person sees the request and the run's facts, and no message.
    (person,) = person_views
    assert (person.case_id, person.actor, person.tools) == (
        CASE_ID,
        "TP-MH",
        frozenset({"decide_approval"}),
    )
    assert person.request == REQUEST
    assert dict(person.facts) == {"so_luong_nhan": 12, "ngay_giao": "05/03/2026"}
    assert person.messages == ()


def test_a_delivery_that_is_not_one_refuses_the_step(conn: Conn) -> None:
    class Wrong(FakeEnvironment):
        def prepare(self, step: TemplateStep, role_code: str, toolbox: Any) -> Any:
            return {"facts": {"so_tien_bi_mat": 987654321}}

    executor = FakeExecutor(de_script())
    result = _run(conn, executor, Wrong({"decide": approve}))
    assert result.outcomes["draft"] == "refused"
    # Task 4 M4: the refusal names the type alone, never the values it held.
    assert result.refusals[0] == "draft: environment: not a delivery of named facts and texts: dict"
    assert "987654321" not in result.refusals[0] and "so_tien_bi_mat" not in result.refusals[0]
    assert executor.seen == []


def test_run_case_resets_an_environment_at_each_run_start(conn: Conn) -> None:
    """Ruling R4e: an environment with ``reset`` has it called once per run, before any
    step; one without it runs as before."""
    calls: list[str] = []

    class Resettable(FakeEnvironment):
        def reset(self) -> None:
            calls.append(f"reset after {len(self.prepared)} prepared")

    environment = Resettable({"decide": approve})
    for _ in range(2):
        assert _run(conn, FakeExecutor(de_script()), environment).stop["type"] == "end"
    assert calls == ["reset after 0 prepared", "reset after 3 prepared"]
    assert not hasattr(FakeEnvironment({}), "reset")

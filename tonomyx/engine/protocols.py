"""What the engine hands a step to: an executor (a digital employee) or the environment.

Neither ever calls a tool function directly (ruling R7a). Each receives a
``StepToolbox`` bound to its step, its role and, for a digital employee, its task
token, and reports how the step ended as a ``StepOutcome``.

Before every step it hands the executor, the engine gives the environment a turn
(``Environment.prepare``): what the world tells the platform by then, as a
``Delivery`` of facts and incoming messages. The engine keeps the run's facts (a later
value wins) and shows them, with the step's messages, in the step's ``view``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, get_args

from tonomyx.governance.template import TemplateStep

if TYPE_CHECKING:
    from tonomyx.engine.toolbox import EnvironmentToolbox, StepToolbox

StepOutcome = Literal[
    "done", "pass", "flag", "approved", "rejected", "pending", "skipped", "refused"
]
OUTCOMES: frozenset[str] = frozenset(get_args(StepOutcome))


@dataclass(frozen=True)
class Delivery:
    """What the environment hands the platform before an executor step: facts it learned
    (by name) and the messages that came in for this step (text only)."""

    facts: Mapping[str, Any] = field(default_factory=dict)
    messages: tuple[str, ...] = ()


class Executor(Protocol):
    """A digital employee's steps, and the engine's own steps it does not run itself
    (``check``, ``flag_exception``, ``compute_amount``, with the engine's authority and no
    token). It works only through the toolbox's tools."""

    def perform(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome: ...


class Environment(Protocol):
    """Whatever is not the platform: a person (``nguoi``) or an outside party (``ngoai``)."""

    def person(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome: ...

    def outside(self, step: TemplateStep, role_code: str, toolbox: StepToolbox) -> StepOutcome: ...

    def prepare(self, step: TemplateStep, role_code: str, toolbox: EnvironmentToolbox) -> Delivery:
        """The environment's turn before an executor step (``role_code`` is the step's
        actor). Its toolbox calls no tool; it may ``read`` and ``release_fact``."""
        ...

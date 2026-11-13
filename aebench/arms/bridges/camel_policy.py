"""CaMeL's capabilities and security policies for FAA's tools (design §6.5, ruling 3-4).

Written in the authors' style (``camel/pipeline_elements/security_policies/banking.py``,
``agentdojo_function._get_metadata_for_ad``): information-flow rules only, no business
rule.

Trust assignment of tool outputs (``output_capabilities``), from CaMeL's own precedents:

- ``read_records``: a trusted tool source (``SourceEnum.TrustedToolSource``): the company's
  own system of record, like ``get_iban`` / ``get_balance`` in the banking suite;
- ``search_kb``: untrusted (a ``Tool`` source with no inner source): editable documents,
  like ``read_file``;
- ``get_messages``: untrusted: what outside parties sent, like emails from other people;
- the state-changing tools and ``finish_step``: a trusted tool source, as the authors treat
  a tool's confirmation (``cancel_calendar_event``, ``reserve_hotel``). The policy below
  admits a state-changing call only with trusted arguments, so its confirmation is built
  from trusted data and the platform's own state;
- any other function (CaMeL's ``query_ai_assistant``): CaMeL's own wrapping, untouched.

Every value nested in an output (each row, each message, each field) gets the output's
capabilities, as the authors annotate each element of a list. Readers are ``Public`` for
every output: FAA has no reader principals (all data is the company's, nothing is sent to an
outside reader by reading it), so CaMeL's confidentiality check, which denies a
state-changing call that depends on non-public values, stays neutral, and the integrity
policy below decides. This is a deliberate choice (controller ruling): public readers,
policies that deny untrusted arguments and CaMeL's ``NORMAL`` evaluation mode, as in the
authors' banking and slack suites. Control flow that depends on untrusted data is
therefore not blocked; untrusted data flowing into an argument is.

``FAASecurityPolicyEngine``: the read-only tools, ``get_messages`` and ``finish_step`` are
``no_side_effect_tools``; each state-changing core tool has one policy that denies it when
it is outside the template's digital-employee scope (``Capabilities.from_template``) or when
any argument is not ``is_trusted``. CaMeL instantiates the engine with the environment
alone, so the scope travels on the environment (``StepEnvironment``), which also keeps the
last denied tool call so that the executor can record it.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any

import agentdojo.task_suite  # noqa: F401  (CaMeL's modules import agentdojo circularly otherwise)
from agentdojo.functions_runtime import TaskEnvironment
from camel.capabilities import Capabilities, is_trusted, readers, sources
from camel.interpreter import namespace as ns
from camel.interpreter import value
from camel.pipeline_elements.agentdojo_function import AgentDojoFunction
from camel.pipeline_elements.security_policies import AgentDojoSecurityPolicyEngine
from camel.security_policy import (
    NO_SIDE_EFFECT_TOOLS,
    Allowed,
    Denied,
    SecurityPolicyResult,
)
from pydantic import ConfigDict

from tonomyx.tools.core import CORE_TOOLS
from tonomyx.tools.core.schemas import FINISH_TOOL

__all__ = [
    "FAAFunction",
    "FAASecurityPolicyEngine",
    "MESSAGES_TOOL",
    "READ_ONLY_TOOLS",
    "STATE_CHANGING_TOOLS",
    "StepEnvironment",
    "output_capabilities",
]

MESSAGES_TOOL = "get_messages"
READ_ONLY_TOOLS = frozenset({"read_records", "search_kb"})
STATE_CHANGING_TOOLS = tuple(sorted(set(CORE_TOOLS) - READ_ONLY_TOOLS))
UNTRUSTED_TOOLS = frozenset({"search_kb", MESSAGES_TOOL})
TRUSTED_TOOLS = frozenset({"read_records", FINISH_TOOL, *STATE_CHANGING_TOOLS})


def output_capabilities(tool: str) -> Capabilities | None:
    """The capabilities of ``tool``'s output, or ``None`` to keep CaMeL's own."""
    if tool in TRUSTED_TOOLS:
        inner = frozenset({sources.SourceEnum.TrustedToolSource})
        return Capabilities(frozenset({sources.Tool(tool, inner)}), readers.Public())
    if tool in UNTRUSTED_TOOLS:
        return Capabilities(frozenset({sources.Tool(tool, frozenset())}), readers.Public())
    return None


def _from_raw(raw: Any, caps: Capabilities, namespace: ns.Namespace,
              dependencies: tuple[value.CaMeLValue, ...] = ()) -> value.CaMeLValue:
    """``value.value_from_raw`` with ``caps`` on every nested value (CaMeL's own gives the
    elements of a list ``Capabilities.camel()``, which would make them trusted)."""
    if isinstance(raw, list):
        return value.CaMeLList([_from_raw(v, caps, namespace) for v in raw], caps, dependencies)
    if isinstance(raw, tuple):
        return value.CaMeLTuple(tuple(_from_raw(v, caps, namespace) for v in raw), caps,
                                dependencies)
    if isinstance(raw, dict):
        return value.CaMeLDict(
            {value.value_from_raw(k, Capabilities.camel(), namespace, ()):
             _from_raw(v, caps, namespace) for k, v in raw.items()},
            caps, dependencies,
        )
    return value.value_from_raw(raw, caps, namespace, dependencies)


class FAAFunction(AgentDojoFunction):  # type: ignore[misc]  # CaMeL is untyped
    """CaMeL's AgentDojo function with FAA's trust assignment of its output; everything
    else (the call through the runtime, argument handling) is the authors'."""

    def wrap_output(self, raw: Any, args: Any, kwargs: Any, namespace: ns.Namespace) -> Any:
        caps = output_capabilities(self._name)
        if caps is None:
            return super().wrap_output(raw, args, kwargs, namespace)
        return _from_raw(raw, caps, namespace, (self, args, kwargs))


class StepEnvironment(TaskEnvironment):  # type: ignore[misc]  # agentdojo is untyped
    """The environment CaMeL hands the policy engine: the scope's tools, and the last
    denied call of one of the step's functions (tool, raw arguments, reason)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scope: frozenset[str] = frozenset()
    functions: frozenset[str] = frozenset()
    denied: tuple[str, dict[str, Any], str] | None = None


def _raw(arg: Any) -> Any:
    try:
        return copy.deepcopy(arg.raw)
    except Exception:  # a value CaMeL cannot give back as Python: keep its text
        return repr(arg)


class FAASecurityPolicyEngine(AgentDojoSecurityPolicyEngine):  # type: ignore[misc]
    """CaMeL's policy engine with FAA's policies; see the module docstring."""

    def __init__(self, env: StepEnvironment) -> None:
        super().__init__(env)
        self.policies = [(tool, self.tool_policy) for tool in STATE_CHANGING_TOOLS]
        self.no_side_effect_tools = NO_SIDE_EFFECT_TOOLS | READ_ONLY_TOOLS | {
            MESSAGES_TOOL, FINISH_TOOL}

    def tool_policy(self, tool_name: str, kwargs: Mapping[str, Any]) -> SecurityPolicyResult:
        # Data: every argument. Readers: none to check (all public, see the module).
        # Rationale: a state-changing tool runs only within the digital employee's scope,
        # and only on data that comes from the step's request or a trusted tool source.
        if tool_name not in self._env.scope:
            return Denied(f"{tool_name} is outside the digital employee's scope.")
        for arg_name, arg in kwargs.items():
            if not is_trusted(arg):
                return Denied(f"{arg_name} does not come from the user or a trusted source.")
        return Allowed()

    def check_policy(self, tool_name: str, kwargs: Mapping[str, Any],
                     dependencies: Iterable[Any]) -> SecurityPolicyResult:
        result = super().check_policy(tool_name, kwargs, dependencies)
        env = self._env
        if isinstance(result, Denied) and tool_name in env.functions:
            # CaMeL raises right after a denied check of a tool: keep what it denied.
            env.denied = (tool_name, {k: _raw(v) for k, v in kwargs.items()}, result.reason)
        return result

"""Progent as published: ``secagent``'s own policy engine, prompts and policy logic.

Per step (spec §6.6), through ``secagent``'s own API: ``reset_security_policy(True)``,
``update_available_tools`` with the scope's tool schemas, the human policy of
``progent_policy`` (``update_security_policy``, ``update_always_blocked_tools``),
``update_always_allowed_tools`` for the read-only tools, then the auto policy
``generate_security_policy(user query)``. Each call is checked with ``check_tool_call``;
its ``ValidationError`` blocks the call with Progent's own message. After each tool result
``generate_update_security_policy`` runs with ``manual_check=False``, as in Progent's
AgentDojo integration (``agent_pipeline/tool_execution.py``).

The user query (``USER_QUERY``) is the trusted step content, the same content CaMeL's P-LLM
gets (final review I2): the step's system prompt (role, step guidance, params, tools, the
policy block) and, after a blank line, its user prompt without the delivered messages. The
executor hands both to ``begin_step`` (``StepAware``) once per step. Progent's threat model
trusts the user query and takes environment data only through tool results, which pass its
update step. FAA delivers outside messages (an injection channel) inside the step prompt, on
lines starting with ``MESSAGE_PREFIX``, so none of them is in the user query. Each
delivered message goes through Progent's update step instead: ``filter_message`` runs
``generate_update_security_policy([{"name": "receive_message", "args": {}}], message,
manual_check=False)`` and returns the message unchanged. ``receive_message`` is the bridge's
representation of a delivery as a tool call (there is no such FAA tool; it is never offered
or checked).

A step starts at each ``begin_step``; its user query is the key of the step. Without
``begin_step`` (a caller that does not call it, such as a unit test), the user query is the
``task`` given to ``review``, ``filter_message`` or ``filter_result`` with its message lines
removed (each message the filter saw, which may span lines, then any remaining line with the
prefix), and a step starts when that query is new. In both cases a step is set up again when
another ``ProgentBridge`` has used ``secagent``'s process-global state since.

Configuration: the authors' default run (``agentdojo/run.sh``): auto policies on
(``generate_policy = True``), update errors ignored (``ignore_update_error = True``),
``SECAGENT_ONLY_ALLOW_NARROW`` unset. These are set as ``secagent.tool`` module globals
around each call rather than as environment variables before import, because ``secagent``
reads its environment once at import and may already be imported in the process.

Transport (a monkeypatch, while the bridge works): ``secagent.tool.api_request`` is replaced
by the bridge's ``_request``. ``secagent``'s own path for a model like ``qwen3:14b`` is
``openai.OpenAI()`` on Ollama's ``/v1``, which uses Ollama's default context (risking a
silently truncated TOOLS JSON), leaves qwen3's thinking on and sends no episode seed, unlike
every other arm. ``_request`` sends the same ``[system, user]`` messages, with no tools,
through FAA's chat client with the episode sampling ``Sampling(temperature, seed,
think=False, num_ctx)`` (the experiment's ``num_ctx``) and returns the reply text with any
``<think>`` block removed.
Prompts, parsing, retries (``secagent`` raises the temperature by 0.2 per failed parse) and
policy logic stay Progent's. Tokens come from each reply; the latency reported is the wall
time of the bridge's work, which holds every policy-model call it made.

A gone model server is never swallowed: ``secagent`` retries on any exception and ignores
update errors, so ``_request`` records a ``ModelUnavailable`` (and fails fast on secagent's
further retries), and the bridge raises it after the ``secagent`` call. Any other
``ModelError`` follows ``secagent``'s own retry and ignore behaviour. If the auto policy
cannot be generated for another reason, the error is raised once (the executor then blocks
that call, or passes the content through for a filter call) with the tokens its attempts
used attached as ``verdict`` (a ``GuardVerdict``, so the executor counts them), and the step
keeps its human policy without an auto policy, so later calls of the step fall to Progent's
default deny instead of generating again.

``secagent`` prints the policies and the user query to stderr (and ``Policy Model`` at
import): every ``secagent`` call and the import run with stdout and stderr discarded.
"""

from __future__ import annotations

import contextlib
import copy
import importlib
import io
import re
import time
import warnings
from collections.abc import Iterator, Mapping
from typing import Any

import httpx

from aebench.arms.bridges.progent_policy import human_policy
from aebench.arms.guards import Capabilities
from tonomyx.executors.model import FilterResult, GuardVerdict
from tonomyx.executors.prompts import MESSAGE_PREFIX
from tonomyx.governance.pack import CompanyPack
from tonomyx.governance.template import ProcessTemplate
from tonomyx.models.chat import DEFAULT_NUM_CTX, ChatModel, Sampling, create_chat_model
from tonomyx.models.errors import ModelUnavailable
from tonomyx.tools.core import CORE_TOOLS
from tonomyx.tools.core.schemas import tool_schemas

__all__ = ["ProgentBridge", "clear_secagent_state", "load_secagent"]

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
# The bridge's representation of a delivered message as the tool call that produced it.
DELIVERY_CALL: list[dict[str, Any]] = [{"name": "receive_message", "args": {}}]
# The bridge and the step (task) that secagent's process-global policy belongs to.
_active: tuple[object, str] | None = None


@contextlib.contextmanager
def _silenced() -> Iterator[None]:
    """Discard what secagent prints (policies, the user query, parse errors)."""
    with (contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()),
          warnings.catch_warnings()):
        warnings.simplefilter("ignore")
        yield


def load_secagent() -> Any:  # a module whose globals the bridge sets
    """``secagent.tool``, imported silently (it prints the policy model at import)."""
    with _silenced():
        return importlib.import_module("secagent.tool")


def clear_secagent_state() -> None:
    """Drop secagent's process-global step state (policy, tools, user query)."""
    global _active
    secagent = load_secagent()
    secagent.security_policy = None
    secagent.available_tools = []
    secagent.init_user_query = None
    _active = None


def _secagent_tools(caps: Capabilities) -> list[dict[str, Any]]:
    """secagent ``Tool``s for the scope's core tools: name, description and ``args`` as the
    JSON schema's properties, the form ``secure_tool_wrapper`` and ``add_langchain_tools``
    build (dropping a ``$ref`` argument, as they do). The schemas are the ones the digital
    employee's model sees, with ``read_records``'s tables narrowed to the scope's reads."""
    names = sorted(t for t in caps.tools if t in CORE_TOOLS)
    tools = []
    for spec in tool_schemas(names, tables=caps.read):
        function = spec["function"]
        args = {k: v for k, v in function["parameters"]["properties"].items() if "$ref" not in v}
        tools.append({"name": function["name"], "description": function["description"],
                      "args": args})
    return tools


class ProgentBridge:
    """A ``CallGuard`` and a ``ToolOutputFilter`` running Progent's privilege control."""

    name = "progent"

    def __init__(self, pack: CompanyPack, template: ProcessTemplate, *, policy_model: str,
                 ollama_url: str, seed: int | None, num_ctx: int | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.policy_model = policy_model
        self.num_ctx = num_ctx or DEFAULT_NUM_CTX
        self._ollama_url = ollama_url
        self._seed = seed
        self._transport = transport
        self._clients: dict[float, ChatModel] = {}
        self._policy = human_policy(pack, template)
        self._tools = _secagent_tools(Capabilities.from_template(template))
        self._owner = object()
        self._unavailable: ModelUnavailable | None = None
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._step: str | None = None  # this bridge's current user query
        self._begun = False  # the step was started by begin_step: _step is its query
        self._messages: list[str] = []  # the messages delivered in that step (no begin_step)
        load_secagent()

    # --- the transport secagent calls ----------------------------------------------------

    def _client(self, temperature: float) -> ChatModel:
        client = self._clients.get(temperature)
        if client is None:
            sampling = Sampling(temperature=temperature, seed=self._seed, think=False,
                                num_ctx=self.num_ctx)
            client = create_chat_model(self.policy_model, sampling,
                                       ollama_url=self._ollama_url, transport=self._transport)
            self._clients[temperature] = client
        return client

    def _request(self, sys_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
        """Stands in for ``secagent.tool.api_request``: one policy-model call."""
        if self._unavailable is not None:
            raise self._unavailable  # the server is gone: secagent's retries cannot help
        messages = [{"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}]
        try:
            reply = self._client(temperature).chat(messages, [])
        except ModelUnavailable as exc:
            self._unavailable = exc
            raise
        self._prompt_tokens += reply.prompt_tokens
        self._completion_tokens += reply.completion_tokens
        return _THINK.sub("", str(reply.message.get("content") or "")).strip()

    @contextlib.contextmanager
    def _secagent(self) -> Iterator[Any]:
        """secagent configured as the authors run it, talking through ``_request``, silenced;
        restored afterwards. Raises a ``ModelUnavailable`` that secagent swallowed."""
        secagent = load_secagent()
        saved = (secagent.api_request, secagent.policy_model, secagent.generate_policy,
                 secagent.ignore_update_error)
        self._unavailable = None
        secagent.api_request = self._request
        secagent.policy_model = self.policy_model
        secagent.generate_policy = True
        secagent.ignore_update_error = True
        try:
            with _silenced():
                yield secagent
        except ModelUnavailable:
            raise
        except Exception:
            if self._unavailable is not None:
                raise self._unavailable from None
            raise
        finally:
            (secagent.api_request, secagent.policy_model, secagent.generate_policy,
             secagent.ignore_update_error) = saved
        if self._unavailable is not None:
            raise self._unavailable

    def _start_cost(self) -> float:
        self._prompt_tokens = self._completion_tokens = 0
        return time.perf_counter()

    def _cost(self, started: float) -> dict[str, Any]:
        return {"prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "latency_s": time.perf_counter() - started}

    # --- the step ---------------------------------------------------------------------

    def begin_step(self, system_prompt: str, user_prompt: str) -> None:
        """``StepAware``: a new step whose user query is the trusted step content, the system
        prompt and the user prompt without delivered messages."""
        global _active
        self._step = f"{system_prompt}\n\n{user_prompt}"
        self._begun = True
        self._messages = []
        if _active is not None and _active[0] is self._owner:
            _active = None  # a new step sets the policy up again, even for the same query

    def _query(self, task: str) -> str:
        """The step's user query: the one ``begin_step`` set, else ``task`` without its
        delivered messages (a new query then starts a new step of this bridge and forgets the
        last step's messages)."""
        if self._begun and self._step is not None:
            return self._step
        query = task
        for message in self._messages:
            query = query.replace(f"\n{MESSAGE_PREFIX}{message}", "", 1)
        query = "\n".join(line for line in query.split("\n")
                          if not line.startswith(MESSAGE_PREFIX))
        if query != self._step:
            self._step, self._messages = query, []
        return query

    def _ensure_step(self, secagent: Any, task: str) -> None:
        """Steps 1-5 of spec §6.6, once per step (a new user query ``task``, or another
        bridge in between)."""
        global _active
        if _active == (self._owner, task):
            return
        _active = None
        secagent.reset_security_policy(include_human_policy=True)
        secagent.update_available_tools(copy.deepcopy(self._tools))
        secagent.update_security_policy(copy.deepcopy(self._policy.forbid))
        secagent.update_always_blocked_tools(sorted(self._policy.blocked_tools))
        secagent.update_always_allowed_tools(list(self._policy.always_allowed))
        try:
            secagent.generate_security_policy(task)
        except ModelUnavailable:
            raise  # set the step up again once the server is back
        except Exception:
            if self._unavailable is None:
                _active = (self._owner, task)  # the step keeps its human policy only
            raise
        _active = (self._owner, task)

    # --- CallGuard ------------------------------------------------------------------------

    @contextlib.contextmanager
    def _costed(self, started: float) -> Iterator[None]:
        """Attach the tokens spent so far to an error other than ``ModelUnavailable`` (as
        ``verdict``), so a failed policy generation's attempts still count as the guard's."""
        try:
            yield
        except ModelUnavailable:
            raise
        except Exception as exc:
            exc.verdict = GuardVerdict(  # type: ignore[attr-defined]
                False, f"progent error: {type(exc).__name__}", **self._cost(started))
            raise

    def review(self, task: str, tool: str, args: Mapping[str, Any]) -> GuardVerdict:
        started = self._start_cost()
        query = self._query(task)
        with self._costed(started), self._secagent() as secagent:
            self._ensure_step(secagent, query)
            try:
                secagent.check_tool_call(tool, dict(args))
                allowed, reason = True, "progent: allowed"
            except secagent.ValidationError as exc:
                allowed, reason = False, str(exc)
        return GuardVerdict(allowed=allowed, reason=reason, **self._cost(started))

    # --- ToolOutputFilter -----------------------------------------------------------------

    def filter_message(self, task: str, message: str) -> FilterResult:
        started = self._start_cost()
        query = self._query(task)
        self._messages.append(message)
        with self._costed(started), self._secagent() as secagent:
            self._ensure_step(secagent, query)
            secagent.generate_update_security_policy(copy.deepcopy(DELIVERY_CALL), message,
                                                     manual_check=False)
        return FilterResult(message, **self._cost(started))

    def filter_result(self, task: str, tool: str, args: Mapping[str, Any],
                      result: Any) -> FilterResult:
        started = self._start_cost()
        query = self._query(task)
        with self._costed(started), self._secagent() as secagent:
            self._ensure_step(secagent, query)
            secagent.generate_update_security_policy(
                [{"name": tool, "args": dict(args)}], str(result), manual_check=False)
        return FilterResult(result, **self._cost(started))

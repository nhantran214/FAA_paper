"""NeMo Guardrails as published: the verdict comes out of ``nemoguardrails.LLMRails``.

The five checks are Colang subflows in ``baselines/nemo_config/rails.co`` listed under
``rails.tool_output`` in ``config.yml`` (NeMo's own tool output rails: they run on the tool
calls the bot emits, before they execute). The Python actions behind them read the company
pack and the template. No model is configured, so NeMo never reaches a network. This module
turns one FAA tool call into the message list NeMo's own tests use and reads NeMo's reply:
the call returned in ``tool_calls`` is allowed, a refusal text blocks it.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import os
import time
import warnings
from collections.abc import Iterator, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from aebench.arms.guards import (
    TERMINAL_STATUSES,
    Capabilities,
    _cap_fields,
    _digital_employees_decide,
    _log_tables,
    _tables_of,
    _values,
)
from tonomyx.executors.model import GuardVerdict
from tonomyx.governance.pack import CompanyPack
from tonomyx.governance.template import ProcessTemplate
from tonomyx.tools.core.context import OWN_TOOL_TABLES

__all__ = ["NeMoBridge"]

CONFIG_DIR = Path(__file__).resolve().parents[3] / "baselines" / "nemo_config"


@contextlib.contextmanager
def _silenced() -> Iterator[None]:
    """Discard what NeMo prints or logs (it writes to stdout, stderr and loggers)."""
    with (contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()),
          warnings.catch_warnings()):
        warnings.simplefilter("ignore")
        previous = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            yield
        finally:
            logging.disable(previous)


def _calls(tool_calls: Any) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for call in tool_calls or []:
        function = call.get("function", {})
        raw = function.get("arguments", {})
        args = json.loads(raw) if isinstance(raw, str) else raw
        out.append((str(function.get("name", "")), args if isinstance(args, dict) else {}))
    return out


class NeMoBridge:
    """A ``CallGuard`` that asks NeMo Guardrails' tool output rails whether to run a call."""

    name = "nemo-guardrails"

    def __init__(self, pack: CompanyPack, template: ProcessTemplate) -> None:
        # NeMo's own opt-out of its usage-stats reporting (nemoguardrails/telemetry.py).
        os.environ["NEMO_GUARDRAILS_NO_USAGE_STATS"] = "1"
        self.pack = pack
        self.caps = Capabilities.from_template(template)
        with _silenced():
            from nemoguardrails import LLMRails, RailsConfig

            config = RailsConfig.from_content(
                (CONFIG_DIR / "rails.co").read_text(encoding="utf-8"),
                (CONFIG_DIR / "config.yml").read_text(encoding="utf-8"),
            )
            self.rails = LLMRails(config)
            for fn in (self.check_approval_gate, self.check_scope, self.check_terminal_status,
                       self.check_caps, self.check_append_only):
                self.rails.runtime.register_action(fn, name=fn.__name__)

    # --- the five actions behind the Colang subflows: each takes the tool calls -------

    async def check_approval_gate(self, tool_calls: Any = None, **_: Any) -> bool:
        for tool, args in _calls(tool_calls):
            if tool == "decide_approval" and not _digital_employees_decide(self.pack):
                return False
            if (tool == "update_status" and args.get("table") in OWN_TOOL_TABLES
                    and args.get("table") not in _log_tables()):
                return False
        return True

    async def check_scope(self, tool_calls: Any = None, **_: Any) -> bool:
        return all(not self.caps.tools or tool in self.caps.tools
                   for tool, _args in _calls(tool_calls))

    async def check_terminal_status(self, tool_calls: Any = None, **_: Any) -> bool:
        return not any(status in TERMINAL_STATUSES
                       for _t, args in _calls(tool_calls)
                       for status in _values(args, "trang_thai"))

    async def check_caps(self, tool_calls: Any = None, **_: Any) -> bool:
        caps = _cap_fields(self.pack)
        for _t, args in _calls(tool_calls):
            for field_name, cap in caps.items():
                for value in _values(args, field_name):
                    try:
                        if Decimal(str(value)) > cap:
                            return False
                    except (InvalidOperation, ValueError, TypeError):
                        continue
        return True

    async def check_append_only(self, tool_calls: Any = None, **_: Any) -> bool:
        return all(not (_tables_of(tool, args)[0] & _log_tables())
                   for tool, args in _calls(tool_calls))

    # --- the CallGuard --------------------------------------------------------------

    def review(self, task: str, tool: str, args: Mapping[str, Any]) -> GuardVerdict:
        started = time.perf_counter()
        call = {"id": "call_1", "type": "function",
                "function": {"name": tool, "arguments": json.dumps(args, default=str)}}
        messages = [{"role": "user", "content": task},
                    {"role": "assistant", "content": "", "tool_calls": [call]}]
        with _silenced():
            result = asyncio.run(self.rails.generate_async(
                messages=messages, options={"rails": {"dialog": False}}))
        latency = time.perf_counter() - started
        if getattr(result, "tool_calls", None):
            return GuardVerdict(True, "nemo_guardrails: tool output rails passed",
                                latency_s=latency)
        response = getattr(result, "response", None)
        text = response[0].get("content", "") if isinstance(response, list) and response else ""
        return GuardVerdict(False, f"nemo_guardrails: {text or 'blocked'}", latency_s=latency)

"""The event log through tools: record_event and flag.

``record_event`` writes only the kinds no other tool owns (facts from outside:
received, inspected, shipped, recorded). A drafted document, a request, a
decision, a reconciliation, a payment, a message, a status change and a flag are
each recorded by the tool that does them, so the log cannot claim an action that
never happened.
"""

from __future__ import annotations

from typing import Any

from tonomyx.tools.core.context import CoreContext, acting, record, require_tool, text
from tonomyx.tools.errors import ToolDenied

FACT_EVENT_KINDS: frozenset[str] = frozenset({"RECEIVED", "INSPECTED", "SHIPPED", "RECORDED"})


def record_event(ctx: CoreContext, *, kind: str, ref: str, mo_ta: str = "") -> dict[str, Any]:
    require_tool(ctx, "record_event")
    if kind not in FACT_EVENT_KINDS:
        raise ToolDenied(f"record_event writes one of {sorted(FACT_EVENT_KINDS)}, not {kind!r}")
    ref = text(ref, "ref")
    with acting(ctx) as cur:
        event_id = record(cur, ctx, kind, ref, mo_ta or None)
    return {"id": event_id}


def flag(ctx: CoreContext, *, ref: str, reason: str) -> dict[str, Any]:
    """Raise an exception flag on ``ref``: a ``FLAGGED`` event with the reason."""
    require_tool(ctx, "flag")
    ref = text(ref, "ref")
    reason = text(reason, "reason")
    with acting(ctx) as cur:
        event_id = record(cur, ctx, "FLAGGED", ref, reason)
    return {"id": event_id}

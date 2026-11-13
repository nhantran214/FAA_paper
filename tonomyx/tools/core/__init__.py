"""Generic tools on the core tables, under the task token and the business gate.

Every tool is ``fn(ctx: CoreContext, **args) -> dict`` and raises ``ToolDenied``
on refusal. ``CORE_TOOLS`` maps each tool name to its function.
"""

from collections.abc import Callable
from typing import Any

from tonomyx.tools.core.approvals import decide_approval, request_approval
from tonomyx.tools.core.context import CoreContext
from tonomyx.tools.core.documents import compute_amount, create_document, update_status
from tonomyx.tools.core.events import flag, record_event
from tonomyx.tools.core.records import read_records, search_kb
from tonomyx.tools.core.settlement import notify, pay, reconcile

CORE_TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "read_records": read_records,
    "search_kb": search_kb,
    "create_document": create_document,
    "update_status": update_status,
    "compute_amount": compute_amount,
    "request_approval": request_approval,
    "decide_approval": decide_approval,
    "record_event": record_event,
    "flag": flag,
    "reconcile": reconcile,
    "pay": pay,
    "notify": notify,
}

__all__ = ["CORE_TOOLS", "CoreContext", *CORE_TOOLS]

"""Reads: read_records and search_kb. They write nothing and record no event."""

from __future__ import annotations

import unicodedata
from typing import Any

from tonomyx.tools.core.context import (
    CoreContext,
    check_table,
    reading,
    require_read,
    require_tool,
    select_rows,
)
from tonomyx.tools.errors import ToolDenied


def read_records(ctx: CoreContext, *, table: str, where: dict[str, Any]) -> dict[str, Any]:
    """Rows of a core table matching ``where`` (equality), never of another case."""
    require_tool(ctx, "read_records")
    check_table(table)
    require_read(ctx, table)
    if not isinstance(where, dict):
        raise ToolDenied("where must be an object of column: value")
    with reading(ctx) as cur:
        return {"rows": select_rows(cur, ctx, table, where)}


def _fold(value: str) -> str:
    """Case-fold and strip accents, so a query matches regardless of diacritics."""
    stripped = unicodedata.normalize("NFD", value).replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn").casefold()


def search_kb(ctx: CoreContext, *, query: str) -> dict[str, Any]:
    """Knowledge articles (``tri_thuc``) whose code, title or field contains the query."""
    require_tool(ctx, "search_kb")
    require_read(ctx, "tri_thuc")
    needle = _fold(query or "").strip()
    with reading(ctx) as cur:
        articles = select_rows(cur, ctx, "tri_thuc", {})
    return {
        "articles": [
            a
            for a in articles
            if any(needle in _fold(a[column]) for column in ("ma_kb", "tieu_de", "linh_vuc"))
        ]
    }

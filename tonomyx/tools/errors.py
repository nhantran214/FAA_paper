"""The refusal every tool raises when a gate says no."""

from __future__ import annotations


class ToolDenied(PermissionError):
    """The call was refused by a gate."""

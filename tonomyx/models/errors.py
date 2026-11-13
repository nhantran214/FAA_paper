"""The two errors every model client raises (ruling R2a).

``ModelUnavailable`` stops a run: no server, no model or no key. ``ModelError`` is any
other failed call, after its retry. Neither message ever holds a key: messages are built
from the model name, the status code and the exception's type name only.
"""

from __future__ import annotations


class ModelError(RuntimeError):
    """The model gave a bad reply, or the call failed, again after one retry."""


class ModelUnavailable(ModelError):  # noqa: N818 (public name fixed by the plan)
    """No server, no model or no key. The run must stop."""

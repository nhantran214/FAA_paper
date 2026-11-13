"""Fixtures for the platform-rule attacks: an empty ``core`` (``conn``) and the tools
world (``world``), built with the shared helpers, not imported from other conftests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.core_fixtures import Conn, fresh_core, seed_world
from tonomyx.config import Settings


@pytest.fixture
def conn(settings: Settings) -> Iterator[Conn]:
    """A connection to a freshly reset, empty ``core`` schema."""
    with fresh_core(settings) as c:
        yield c


@pytest.fixture
def world(settings: Settings) -> Iterator[Conn]:
    """The tools world of ``tests/tools_core``, as given data."""
    with fresh_core(settings) as c:
        seed_world(c)
        yield c

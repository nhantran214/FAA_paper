"""Shared fixtures. Each test package builds its own database state from ``settings``."""

from __future__ import annotations

import pytest

from tonomyx.config import Settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.from_env()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Tests marked ``llm`` call a live model: they run only when ``-m`` selects them."""
    if "llm" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="live model test; run with -m llm")
    for item in items:
        if item.get_closest_marker("llm") is not None:
            item.add_marker(skip)

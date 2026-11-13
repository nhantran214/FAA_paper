"""Fixtures of the harness tests: no default-suite test asks a real Ollama server for its
version (an ``llm`` test does)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_ollama_version_request(request: pytest.FixtureRequest,
                               monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("llm") is None:
        from aebench.run import experiment as experiment_module

        monkeypatch.setattr(experiment_module, "ollama_server_version", lambda url: "test")

"""The vendored baselines are the packages Python imports, and CaMeL's pinned pydantic-ai is
the installed one."""

from __future__ import annotations

import importlib
import importlib.metadata as md
from pathlib import Path

import pytest

# The repository root, whatever the working directory the suite runs from.
REPO = Path(__file__).resolve().parents[3]
VENDORED = {"agentdojo": "baselines/agentdojo", "camel": "baselines/camel",
            "nemoguardrails": "baselines/nemo_guardrails", "secagent": "baselines/progent"}


@pytest.mark.parametrize("module,src", VENDORED.items())
def test_vendored_package_is_imported_from_baselines(module: str, src: str) -> None:
    mod = importlib.import_module(module)
    assert mod.__file__ is not None
    assert Path(mod.__file__).resolve().is_relative_to((REPO / src).resolve())


def test_camel_runs_on_its_locked_pydantic_ai() -> None:
    assert md.version("pydantic-ai-slim") == "0.2.12"

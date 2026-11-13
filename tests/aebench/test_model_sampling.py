"""Per-model DE sampling: overrides in the experiment file, checks, clients and episode ids."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aebench.run import experiment as experiment_module
from aebench.run.episode import episode_id
from aebench.run.experiment import ExperimentRefused, load_experiment
from tests.aebench.test_defence import _bench, _identity
from tonomyx.config import Settings
from tonomyx.models.chat import Sampling


def _experiment(tmp_path: Path, models: list[Any], think: Any = False) -> Path:
    path = _bench(tmp_path, ["full"], guard_model=None)
    raw = json.loads(path.read_text())
    raw["models"] = models
    raw["sampling"] = {"seed": 1, "think": think, "num_ctx": 4096}
    path.write_text(json.dumps(raw))
    return path


def test_model_entries_override_sampling(tmp_path: Path) -> None:
    path = _experiment(tmp_path, ["qwen3:14b", {"name": "gpt-oss:20b", "think": "low",
                                                "num_predict": 1000}])
    exp = load_experiment(path)
    assert exp.models == ("qwen3:14b", "gpt-oss:20b")
    assert exp.model_sampling["qwen3:14b"].think is False
    assert exp.model_sampling["qwen3:14b"].num_predict is None
    assert exp.model_sampling["gpt-oss:20b"].think == "low"
    assert exp.model_sampling["gpt-oss:20b"].num_predict == 1000
    assert exp.model_sampling["gpt-oss:20b"].num_ctx == 4096


@pytest.mark.parametrize("models, think", [
    ([{"name": "gpt-oss:20b", "think": False}], False),
    ([{"name": "qwen3:14b", "think": "low"}], False),
    (["gpt-oss:20b"], False),
    ([{"name": "qwen3:14b", "think": "max"}], False),
    ([{"name": "qwen3:14b", "num_predict": 0}], False),
    (["qwen3:14b", {"name": "qwen3:14b"}], False),
])
def test_think_level_rules_are_checked_at_load(
    tmp_path: Path, models: list[Any], think: Any
) -> None:
    with pytest.raises(ExperimentRefused):
        load_experiment(_experiment(tmp_path, models, think=think))


def test_each_model_client_gets_its_own_sampling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    path = _experiment(tmp_path, ["qwen3:14b", {"name": "gpt-oss:20b", "think": "low"}])
    built: list[tuple[str, Sampling]] = []

    def chat_factory(name: str, sampling: Sampling, **kw: Any) -> Any:
        built.append((name, sampling))
        return object()

    episodes: list[dict[str, Any]] = []

    def fake_run_episode(conn: Any, **kw: Any) -> dict[str, Any]:
        episodes.append(kw)
        return {"status": "scored", "arm": kw["arm"].name, "episode_id": f"e{len(episodes)}"}

    monkeypatch.setattr(experiment_module, "run_episode", fake_run_episode)
    experiment_module.run_experiment(
        path, out_dir=tmp_path / "out", chat_factory=chat_factory, identify=_identity,
        inputs_path=tmp_path / "none.json", bench_root=tmp_path / "bench",
        settings=settings, isolate=lambda models: None,
    )
    thinks = {name: s.think for name, s in built}
    assert thinks == {"qwen3:14b": False, "gpt-oss:20b": "low"}
    by_model = {kw["identity"].name: kw["sampling"] for kw in episodes}
    assert by_model["gpt-oss:20b"]["think"] == "low"
    assert by_model["qwen3:14b"]["think"] is False
    assert all("seed" not in kw["sampling"] for kw in episodes)


def test_episode_id_changes_with_sampling() -> None:
    key: dict[str, Any] = {
        "case_id": "c", "arm": "full", "set_hash": "h", "model": "m", "model_digest": "d",
        "seed": 1, "rep": 0}
    a = episode_id(**key, sampling={"temperature": 0.0, "think": False})
    b = episode_id(**key, sampling={"temperature": 0.0, "think": "low"})
    assert a != b
    assert a == episode_id(**key, sampling={"temperature": 0.0, "think": False})
    assert a != episode_id(**key)

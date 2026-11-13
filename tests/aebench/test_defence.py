"""The defence bundle: the arms table, ``build_defence``, the episode's executor and the
per-arm guard models of an experiment (design §6.2, §6.8).

Everything is synthetic: a test company pack and template, a made-up case folder of a
development industry with no answer side, and fake model clients and identities.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aebench.arms.defence import Defence, build_defence
from aebench.arms.presets import ARMS, GUARD_MODEL_REF, GUARD_NAMES
from aebench.run import episode as episode_module
from aebench.run import experiment as experiment_module
from aebench.run.episode import CaseRef, SetInfo, build_executor, episode_id, run_episode
from aebench.run.experiment import ExperimentRefused, hf_identity, load_experiment
from tests.engine.conftest import pack, template
from tonomyx.config import Settings
from tonomyx.executors.model import FilterResult, GuardVerdict, ModelExecutor
from tonomyx.models.chat import ChatReply, Sampling
from tonomyx.models.identity import ModelIdentity

TONOMYX_ARMS = ("full", "no-database", "prompt-only", "bare")
HF_MODEL = "hf:protectai/deberta-v3-base-prompt-injection-v2"


class Dummy:
    name = "dummy"

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatReply:
        raise AssertionError("no model call is expected")


def test_arms_table_has_progent_and_no_llm_guard() -> None:
    assert "llm-guard" not in ARMS and ARMS["progent"].guard == "progent"
    assert ARMS["llama-guard"].guard_model == "llama-guard3:8b"
    assert GUARD_NAMES == ("progent", "llama-guard", "nemo-guardrails", "agentdojo-defense",
                           "camel-capability")
    assert ARMS["agentdojo-defense"].guard_model == HF_MODEL
    assert ARMS["progent"].guard_model == GUARD_MODEL_REF == "@guard_model"
    assert ARMS["nemo-guardrails"].guard_model is None
    assert ARMS["camel-capability"].guard_model is None
    for name in GUARD_NAMES:
        assert ARMS[name].guard == name and ARMS[name].policy_prompt is True  # ruling R1
    for name in TONOMYX_ARMS:
        assert ARMS[name].guard is None and ARMS[name].guard_model is None


def test_build_defence_has_a_bridge_for_every_guard_arm() -> None:
    kwargs: dict[str, Any] = dict(de_model=Dummy(), guard_model=None, guard_model_name=None,
                                  pack=pack(), template=template(),
                                  ollama_url="http://localhost:11434", seed=1)
    # No guard arm is left unbridged (the detector and NeMo load models: not built here).
    for name in ("llama-guard", "progent"):  # each needs its guard model name
        with pytest.raises(ValueError, match="guard model name"):
            build_defence(name, **kwargs)
    camel = build_defence("camel-capability", **kwargs)
    assert camel.executor is not None and camel.guard is None and camel.output_filter is None
    with pytest.raises(KeyError):
        build_defence("llm-guard", **kwargs)
    assert Defence() == Defence(guard=None, output_filter=None, executor=None)


def _executor_kwargs() -> dict[str, Any]:
    return dict(model=Dummy(), pack=pack(), template=template(), guard=None,
                guard_model_name=None, ollama_url="http://ollama:1", seed=7, num_ctx=4096)


def test_tonomyx_arms_build_an_empty_defence(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Defence:
        raise AssertionError("a TonomyX arm builds no defence")

    monkeypatch.setattr(episode_module, "build_defence", refuse)
    for name in TONOMYX_ARMS:
        arm = ARMS[name]
        executor = build_executor(arm, **_executor_kwargs())
        assert isinstance(executor, ModelExecutor)
        assert executor.guard is None and executor.output_filter is None
        assert executor.policy_prompt is arm.policy_prompt


class Guard:
    name = "g"

    def review(self, task: str, tool: str, args: Any) -> GuardVerdict:
        return GuardVerdict(True)


class Filter:
    name = "f"

    def filter_message(self, task: str, message: str) -> FilterResult:
        return FilterResult(message)

    def filter_result(self, task: str, tool: str, args: Any, result: Any) -> FilterResult:
        return FilterResult(result)


def test_a_guard_arm_wires_its_defence(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, dict[str, Any]]] = []
    guard, output_filter, client = Guard(), Filter(), Dummy()

    def fake(name: str, **kwargs: Any) -> Defence:
        seen.append((name, kwargs))
        return Defence(guard=guard, output_filter=output_filter)

    monkeypatch.setattr(episode_module, "build_defence", fake)
    kwargs = {**_executor_kwargs(), "guard": client, "guard_model_name": "qwen3:14b"}
    executor = build_executor(ARMS["progent"], **kwargs)
    assert isinstance(executor, ModelExecutor)
    assert executor.guard is guard and executor.output_filter is output_filter
    assert executor.policy_prompt is True
    ((name, passed),) = seen
    assert name == "progent"
    assert passed["guard_model"] is client and passed["guard_model_name"] == "qwen3:14b"
    assert passed["num_ctx"] == 4096  # the experiment's, passed through to the bridge
    assert passed["de_model"] is kwargs["model"]
    assert passed["ollama_url"] == "http://ollama:1" and passed["seed"] == 7
    assert passed["pack"] is kwargs["pack"] and passed["template"] is kwargs["template"]

    replacement = object()
    monkeypatch.setattr(episode_module, "build_defence",
                        lambda name, **kw: Defence(executor=replacement))
    assert build_executor(ARMS["camel-capability"], **_executor_kwargs()) is replacement


def test_build_defence_passes_num_ctx_to_the_model_calling_bridges() -> None:
    kwargs: dict[str, Any] = dict(de_model=Dummy(), guard_model=None, pack=pack(),
                                  template=template(), ollama_url="http://ollama:1", seed=1)
    guard = build_defence("llama-guard", guard_model_name="llama-guard3:8b", num_ctx=4096,
                          **kwargs).guard
    assert guard.num_ctx == 4096  # type: ignore[union-attr]
    progent = build_defence("progent", guard_model_name="qwen3:14b", num_ctx=4096,
                            **kwargs).guard
    assert progent.num_ctx == 4096  # type: ignore[union-attr]
    default = build_defence("llama-guard", guard_model_name="llama-guard3:8b", **kwargs).guard
    assert default.num_ctx == 32768  # type: ignore[union-attr]


def test_the_defence_module_imports_no_bridge_until_one_is_built() -> None:
    """A TonomyX-only run needs no baseline installed (bridges are imported lazily)."""
    import subprocess
    import sys

    code = ("import sys, aebench.run.experiment, aebench.arms.defence;"
            "print(sorted(m for m in sys.modules if m.startswith(('aebench.arms.bridges.',"
            " 'agentdojo', 'camel', 'nemoguardrails', 'secagent', 'transformers'))))")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          check=True)
    assert done.stdout.strip() == "[]"


# --- run_episode and run_experiment: the arm's own guard model ----------------------


CASE = CaseRef("CASE-T1", "san_xuat", "mua_hang", "p_test", "g1")


def _identity(name: str) -> ModelIdentity:
    return ModelIdentity(name, f"d:{name}")


def _not_run_row(tmp_path: Path, arm: str, guard_model_name: str | None,
                 guard_digest: str | None) -> dict[str, Any]:
    set_info = SetInfo("s1", "blind", "h" * 64, tmp_path, None, ())
    return run_episode(
        None,  # type: ignore[arg-type]  # the set has no template: no database is touched
        case=CASE, case_dir=tmp_path, arm=ARMS[arm], set_info=set_info, model=Dummy(),
        identity=_identity("m1"), guard=None, guard_model="qwen3:14b",
        guard_model_name=guard_model_name, guard_digest=guard_digest, ollama_url="u",
        seed=1, rep=0, inputs=None, engine_fingerprint="dev", paper=False, unlock=None,
        issuer=None,  # type: ignore[arg-type]
    )


def test_the_row_records_the_arms_own_guard_model(tmp_path: Path) -> None:
    common = dict(case_id=CASE.case_id, set_hash="h" * 64, model="m1", model_digest="d:m1",
                  seed=1, rep=0)
    row = _not_run_row(tmp_path, "llama-guard", "llama-guard3:8b", "d:llama-guard3:8b")
    assert row["status"] == "not_run"
    assert (row["guard_model"], row["guard_digest"]) == ("llama-guard3:8b", "d:llama-guard3:8b")
    assert row["episode_id"] == episode_id(arm="llama-guard", guard_model="llama-guard3:8b",
                                           guard_digest="d:llama-guard3:8b", **common)
    assert row["defence_counts"] == {}

    row = _not_run_row(tmp_path, "nemo-guardrails", None, None)
    assert (row["guard_model"], row["guard_digest"]) == (None, None)
    assert row["episode_id"] == episode_id(arm="nemo-guardrails", **common)

    row = _not_run_row(tmp_path, "full", None, None)  # a non-guard arm: as before
    assert (row["guard_model"], row["guard_digest"]) == ("qwen3:14b", None)
    assert row["episode_id"] == episode_id(arm="full", **common)


def _bench(tmp_path: Path, arms: list[str], guard_model: str | None = "qwen3:14b") -> Path:
    root = tmp_path / "bench"
    (root / CASE.case_id).mkdir(parents=True)
    (root / "coverage.json").write_text(json.dumps({"rows": [{
        "case_id": CASE.case_id, "industry": CASE.industry, "department": CASE.department,
        "process": CASE.process, "situation_group": CASE.situation_group}]}))
    (root / CASE.case_id / "case.meta.json").write_text(json.dumps({"status": "draft"}))
    set_dir = tmp_path / "set"
    (set_dir / "templates").mkdir(parents=True)
    (set_dir / "manifest.json").write_text(json.dumps({
        "name": "s1", "mode": "blind", "engine_fingerprint": "x", "drafted_at": "x",
        "processes": {}}))
    raw: dict[str, Any] = {
        "name": "t", "cases": {"industries": [CASE.industry], "statuses": ["draft"]},
        "arms": arms, "governance_sets": [str(set_dir)], "models": ["m1"],
        "sampling": {"seed": 1}, "repetitions": 2, "ollama_url": "http://ollama:2",
    }
    if guard_model is not None:
        raw["guard_model"] = guard_model
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps(raw))
    return path


def test_episode_id_uses_the_arms_own_guard_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    arms = ["full", "llama-guard", "progent", "nemo-guardrails", "agentdojo-defense"]
    path = _bench(tmp_path, arms)
    monkeypatch.setattr(experiment_module, "hf_identity",
                        lambda name: ModelIdentity(name, "snap123"))
    built: list[tuple[str, Sampling]] = []

    def chat_factory(name: str, sampling: Sampling, **kwargs: Any) -> Any:
        built.append((name, sampling))
        return {"client": name, "seed": sampling.seed}

    episodes: list[dict[str, Any]] = []
    resolved = {"full": (None, None), "llama-guard": ("llama-guard3:8b", "d:llama-guard3:8b"),
                "progent": ("qwen3:14b", "d:qwen3:14b"), "nemo-guardrails": (None, None),
                "agentdojo-defense": (HF_MODEL, "snap123")}

    def fake_run_episode(conn: Any, **kw: Any) -> dict[str, Any]:
        episodes.append(kw)
        name, digest = resolved[kw["arm"].name]
        return {"status": "scored", "episode_id": episode_id(
            case_id=CASE.case_id, arm=kw["arm"].name, set_hash=kw["set_info"].set_hash,
            model="m1", model_digest="d:m1", seed=kw["seed"], rep=kw["rep"],
            guard_model=name, guard_digest=digest, sampling=kw["sampling"])}

    monkeypatch.setattr(experiment_module, "run_episode", fake_run_episode)
    run = dict(out_dir=tmp_path / "out", chat_factory=chat_factory, identify=_identity,
               inputs_path=tmp_path / "none.json", bench_root=tmp_path / "bench",
               settings=settings, isolate=lambda models: None)
    experiment_module.run_experiment(path, **run)  # type: ignore[arg-type]

    assert len(episodes) == len(arms) * 2
    for kw in episodes:
        name, digest = resolved[kw["arm"].name]
        assert (kw["guard_model_name"], kw["guard_digest"]) == (name, digest), kw["arm"].name
        assert kw["guard_model"] == "qwen3:14b" and kw["ollama_url"] == "http://ollama:2"
        assert kw["num_ctx"] is None  # the experiment's sampling.num_ctx (unset here)
        if name is None or name.startswith("hf:"):
            assert kw["guard"] is None, kw["arm"].name
        else:
            assert kw["guard"] == {"client": name, "seed": 1 + kw["rep"]}
    # Clients: the DE model and the two Ollama guard models, once per repetition each.
    assert sorted((n, s.seed) for n, s in built) == sorted(
        (n, 1 + rep) for n in ("m1", "llama-guard3:8b", "qwen3:14b") for rep in (0, 1))
    assert all(s.temperature == 0.0 and s.think is False for n, s in built if n != "m1")

    # The plan's ids are the rows' ids: a second run finds every episode done.
    episodes.clear()
    experiment_module.run_experiment(path, **run)  # type: ignore[arg-type]
    assert episodes == []


def test_only_an_arm_on_the_experiments_guard_model_needs_one(tmp_path: Path) -> None:
    load_experiment(_bench(tmp_path / "a", ["llama-guard", "nemo-guardrails",
                                            "agentdojo-defense", "camel-capability"], None))
    with pytest.raises(ExperimentRefused, match="guard_model"):
        load_experiment(_bench(tmp_path / "b", ["full", "progent"], None))


def test_hf_identity_is_the_cached_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    import huggingface_hub
    from huggingface_hub.errors import LocalEntryNotFoundError

    calls: list[dict[str, Any]] = []

    def cached(repo_id: str, **kwargs: Any) -> str:
        calls.append({"repo_id": repo_id, **kwargs})
        return f"/cache/models--x/snapshots/{'a' * 40}"

    monkeypatch.setattr(huggingface_hub, "snapshot_download", cached)
    assert hf_identity("hf:org/model") == ModelIdentity("hf:org/model", "a" * 40)
    assert calls == [{"repo_id": "org/model", "local_files_only": True}]

    def missing(repo_id: str, **kwargs: Any) -> str:
        raise LocalEntryNotFoundError("not cached")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", missing)
    with pytest.raises(ExperimentRefused, match="HuggingFace cache"):
        hf_identity("hf:org/model")
    with pytest.raises(ValueError):
        hf_identity("llama-guard3:8b")


def test_hf_identity_reads_the_local_cache() -> None:
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    cache = hub / "models--protectai--deberta-v3-base-prompt-injection-v2"
    snapshots = sorted(p.name for p in (cache / "snapshots").glob("*")) if cache.is_dir() else []
    if len(snapshots) != 1:
        pytest.skip("the DeBERTa detector is not cached once on this machine")
    assert hf_identity(HF_MODEL) == ModelIdentity(HF_MODEL, snapshots[0])

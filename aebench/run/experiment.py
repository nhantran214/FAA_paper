"""An experiment: cases x arms x governance sets x models x repetitions, run resumably.

An experiment file (JSON) names:

- ``name``: the results file is ``<out_dir>/<name>.jsonl``;
- ``cases``: ``industries`` and ``statuses`` (required), ``groups``, ``case_ids`` and
  ``per_process`` (optional): the cases of ``coverage.json`` of those industries (and
  situation groups, and ids), whose ``case.meta.json`` ``status`` is listed, in coverage
  order; ``per_process`` keeps the first N of each process type;
- ``arms`` (names of ``aebench.arms.presets.ARMS``), ``governance_sets`` (folders,
  relative to the repository or absolute), ``models``, ``guard_model`` (needed when an arm
  runs on the experiment's guard model, ``@guard_model``), ``sampling`` (``temperature``,
  ``seed``, ``num_ctx``, ``think`` (a switch or, for gpt-oss, a level), ``num_predict``),
  ``repetitions`` and ``paper``; optionally
  ``ollama_url``.

Guard models. Each guard arm names its authors' model (``Arm.guard_model``); the arm's
resolved guard model is that name, the experiment's ``guard_model`` for ``@guard_model``,
or ``None`` when the defence calls no model of its own. Its identity is the Ollama digest
(``model_identity``, or ``identify`` when given), or for an ``hf:<repo id>`` model the
commit hash of its snapshot in the local HuggingFace cache (``hf_identity``; a model not
cached refuses the experiment). A guard client is built per (resolved model, repetition)
for Ollama models only; a HuggingFace model is loaded by its bridge.

Refusals, all before any model is built, any database is touched or any answer is opened:

- a case of an industry that is neither a development nor a paper industry;
- a paper-industry case in an experiment whose ``paper`` is false;
- for a paper experiment: a selected case of a development industry (final review I5); a
  selected case whose folder is missing; a case whose inputs
  (``data/evaluation/inputs.json``) are not ``approved``; a set that does not verify;
  sets that do not cover both modes (``blind`` and ``informed``); a set that is not
  frozen; no unlock that ``unlock_paper`` issued in this process; an engine whose
  fingerprint is not the unlock's (a tree that is not clean has none); a set whose hash
  is not the one the unlock verified; an inputs file whose sha256 is not the one the
  unlock verified (final review I6).

Per-model sampling. A ``models`` entry is a name or ``{"name", "think"?, "num_predict"?}``;
the object's fields override ``sampling`` for that model (``Experiment.model_sampling``). A
level for a model whose family does not take levels, or ``false`` for one that cannot turn
thinking off (gpt-oss), is refused. The effective DE sampling (without the seed) is in the
episode id and the row's ``sampling``. Guards never take these overrides.

Seeds and sampling (ruling R11a). Repetition ``rep`` runs with seed ``sampling.seed + rep``
(recorded as the row's ``seed``), for the digital employee and the guard alike. The guard is
always greedy and never thinks (``guard_sampling``: temperature 0, ``think`` false, the
experiment's ``num_ctx``). A guard arm's episode id also holds its resolved guard model
and that model's digest (ruling R11c), none when it has no guard model.

Selected cases whose folder is missing are counted and printed (``missing=N``); a paper
experiment with any is refused.

A development experiment records the engine fingerprint, or ``"dev"`` when the tree is not
clean, and uses a case's inputs when they are ``approved`` or ``draft`` (else the neutral
placeholder, with no input-fact allow-list). A paper experiment checks again, at the start
and at the end of every episode, that the engine and every set still match the unlock
(``paper_freeze_ok``, which also compares the inputs file's sha256 with the unlock's and
the vendored clones and installed packages with the engine record): a
failure at the start stops the experiment before the episode; at the end the row is
written with ``freeze_ok: false`` and the experiment stops. Every row records
``inputs_sha256``, the sha256 of the inputs file the experiment read (``None`` without
one).

Isolation. Before each episode the Ollama models it uses (the digital employee's and the
arm's guard model, not an ``hf:`` one) are unloaded, then loaded again with no prompt
(``aebench.run.isolation``) at the experiment's ``num_ctx``, so the episode does not depend
on the KV cache of earlier ones and its first request does not relaunch the runner; both
steps are outside ``wall_s``. A failure is ``ModelUnavailable``. Rows record
``ollama_isolated: true`` and ``ollama_version``, the server's version (``GET
/api/version``), read once per run of the experiment (``None`` when it cannot be read).

Resume. Each finished episode is appended as one line and flushed. A run skips every
``episode_id`` already in the file, except ids whose last row has ``freeze_ok: false``
and, with ``retry_errors`` (``aebench run --retry-errors``), ids whose last row has status
``error``: they are run again, and a report keeps the last row of an id. A half-written
last line (a crash while writing) is cut off before appending. ``ModelUnavailable`` stops
the experiment: the rows written so far stay, the episode it stopped in is not written, and
a resume repeats it.

The console shows counts only: never case text, mismatches, prompts or replies.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from aebench.arms.presets import ARMS, GUARD_MODEL_REF, HF_PREFIX, Arm
from aebench.run.episode import CaseRef, SetInfo, episode_id, run_episode
from aebench.run.isolation import episode_ollama_models, make_isolate, ollama_server_version
from tonomyx.bench.cases import (
    BENCH_ROOT,
    DEV_INDUSTRIES,
    PAPER_INDUSTRIES,
    read_meta,
)
from tonomyx.bench.freeze import (
    MODES,
    EvaluationUnlock,
    FreezeError,
    check_environment,
    engine_fingerprint,
    inputs_sha256,
    is_issued,
    verify_set,
)
from tonomyx.bench.inputs import INPUTS_PATH, CaseInputs, load_inputs
from tonomyx.config import REPO_ROOT, Settings
from tonomyx.contracts.clock import SystemClock
from tonomyx.contracts.token import InMemoryJtiStore, TokenIssuer
from tonomyx.db.engine import connect
from tonomyx.models.chat import (
    THINK_LEVELS,
    ChatModel,
    Sampling,
    create_chat_model,
    think_problem,
)
from tonomyx.models.identity import ModelIdentity, model_identity

__all__ = [
    "CaseRef",
    "Experiment",
    "ExperimentRefused",
    "FreezeChanged",
    "load_experiment",
    "paper_freeze_ok",
    "run_experiment",
    "episode_seed",
    "arm_guard_model",
    "guard_sampling",
    "hf_identity",
    "model_sampling",
    "select_cases",
    "select_cases_counted",
    "status_counts",
]

DEFAULT_OUT_DIR = REPO_ROOT / "results" / "v2"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
# Statuses a dev experiment takes the case inputs in; others get the neutral placeholder.
DEV_INPUT_STATUSES = frozenset({"approved", "draft"})
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class ExperimentRefused(Exception):
    """The experiment does not run (or stops); the message holds counts and paths only."""


class FreezeChanged(ExperimentRefused):
    """A paper experiment's engine or a governance set no longer matches the unlock."""


@dataclass(frozen=True)
class Experiment:
    name: str
    cases: dict[str, Any]
    arms: tuple[str, ...]
    governance_sets: tuple[Path, ...]
    models: tuple[str, ...]
    guard_model: str
    sampling: Sampling
    repetitions: int
    paper: bool
    ollama_url: str = DEFAULT_OLLAMA_URL
    # The effective digital-employee sampling per model name, before the repetition's seed.
    model_sampling: dict[str, Sampling] = field(default_factory=dict)


def _strings(raw: Any, what: str, *, required: bool = True) -> list[str]:
    if raw is None and not required:
        return []
    if not isinstance(raw, list) or not all(isinstance(x, str) and x for x in raw):
        raise ExperimentRefused(f"{what} must be a list of names")
    if required and not raw:
        raise ExperimentRefused(f"{what} must not be empty")
    return list(raw)


def _check_think(think: Any, what: str) -> None:
    if think is None or isinstance(think, bool) or think in THINK_LEVELS:
        return
    raise ExperimentRefused(f"{what} must be true, false or one of {list(THINK_LEVELS)}")


def _check_num_predict(value: Any, what: str) -> None:
    if value is not None and not (isinstance(value, int) and not isinstance(value, bool)
                                  and value >= 1):
        raise ExperimentRefused(f"{what} must be a whole number of at least 1")


def load_experiment(path: Path) -> Experiment:
    """Read and check an experiment file; raises ``ExperimentRefused``."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ExperimentRefused(f"cannot read the experiment {path}: {type(e).__name__}") from None
    if not isinstance(raw, dict):
        raise ExperimentRefused(f"{path}: an experiment is a JSON object")
    name = raw.get("name")
    if not (isinstance(name, str) and _NAME.fullmatch(name)):
        raise ExperimentRefused("the experiment's name must be letters, digits, '.', '_' or '-'")
    cases = raw.get("cases")
    if not isinstance(cases, dict):
        raise ExperimentRefused("cases must be an object")
    _strings(cases.get("industries"), "cases.industries")
    _strings(cases.get("statuses"), "cases.statuses")
    _strings(cases.get("groups"), "cases.groups", required=False)
    _strings(cases.get("case_ids"), "cases.case_ids", required=False)
    per_process = cases.get("per_process")
    if per_process is not None and not (isinstance(per_process, int) and per_process >= 1):
        raise ExperimentRefused("cases.per_process must be a whole number of at least 1")
    arms = _strings(raw.get("arms"), "arms")
    unknown = sorted(set(arms) - set(ARMS))
    if unknown:
        raise ExperimentRefused(f"unknown arm(s) {unknown}; known: {sorted(ARMS)}")
    if len(set(arms)) != len(arms):
        raise ExperimentRefused("an arm is listed twice")
    guard_model = raw.get("guard_model") or ""
    if not isinstance(guard_model, str):
        raise ExperimentRefused("guard_model must be a model name")
    needing = sorted(a for a in arms if ARMS[a].guard_model == GUARD_MODEL_REF)
    if not guard_model and needing:
        raise ExperimentRefused(f"the guard arm(s) {needing} need a guard_model")
    sets = _strings(raw.get("governance_sets"), "governance_sets")
    model_entries = raw.get("models")
    if not isinstance(model_entries, list) or not model_entries:
        raise ExperimentRefused("models must be a non-empty list")
    models: list[str] = []
    overrides: dict[str, dict[str, Any]] = {}
    for entry in model_entries:
        if isinstance(entry, str) and entry:
            models.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry["name"]:
            unknown_keys = sorted(set(entry) - {"name", "think", "num_predict"})
            if unknown_keys:
                raise ExperimentRefused(f"a model entry has unknown field(s) {unknown_keys}")
            models.append(entry["name"])
            overrides[entry["name"]] = {k: v for k, v in entry.items() if k != "name"}
        else:
            raise ExperimentRefused("a model is a name or an object with a name")
    if len(set(models)) != len(models):
        raise ExperimentRefused("a model is listed twice")
    sampling = raw.get("sampling") or {}
    if not isinstance(sampling, dict):
        raise ExperimentRefused("sampling must be an object")
    seed, num_ctx, think = sampling.get("seed"), sampling.get("num_ctx"), sampling.get("think")
    if seed is not None and not isinstance(seed, int):
        raise ExperimentRefused("sampling.seed must be a whole number")
    if num_ctx is not None and not isinstance(num_ctx, int):
        raise ExperimentRefused("sampling.num_ctx must be a whole number")
    _check_think(think, "sampling.think")
    num_predict = sampling.get("num_predict")
    _check_num_predict(num_predict, "sampling.num_predict")
    repetitions = raw.get("repetitions", 1)
    if not (isinstance(repetitions, int) and repetitions >= 1):
        raise ExperimentRefused("repetitions must be a whole number of at least 1")
    paper = raw.get("paper", False)
    if not isinstance(paper, bool):
        raise ExperimentRefused("paper must be true or false")
    base = Sampling(
        temperature=float(sampling.get("temperature", 0.0)),
        seed=seed,
        think=think,
        num_ctx=num_ctx,
        num_predict=num_predict,
    )
    per_model: dict[str, Sampling] = {}
    for model in models:
        over = overrides.get(model, {})
        if "think" in over:
            _check_think(over["think"], f"{model}: think")
        if "num_predict" in over:
            _check_num_predict(over["num_predict"], f"{model}: num_predict")
        per_model[model] = replace(base, **over)
        problem = think_problem(model, per_model[model].think)
        if problem:
            raise ExperimentRefused(problem)
    return Experiment(
        name=name,
        cases=dict(cases),
        arms=tuple(arms),
        governance_sets=tuple(p if p.is_absolute() else REPO_ROOT / p for p in map(Path, sets)),
        models=tuple(models),
        guard_model=guard_model,
        sampling=base,
        repetitions=repetitions,
        paper=paper,
        ollama_url=str(raw.get("ollama_url") or DEFAULT_OLLAMA_URL),
        model_sampling=per_model,
    )


def select_cases(cases_spec: dict[str, Any], *, bench_root: Path | None = None) -> list[CaseRef]:
    """The cases of ``coverage.json`` the spec selects, by its fields and the meta ``status``
    only, in coverage order. Nothing of the answer side is used."""
    return select_cases_counted(cases_spec, bench_root=bench_root)[0]


def select_cases_counted(
    cases_spec: dict[str, Any], *, bench_root: Path | None = None
) -> tuple[list[CaseRef], int]:
    """``select_cases``, and how many coverage rows the spec selects whose case folder (its
    ``case.meta.json``) is missing."""
    root = Path(bench_root) if bench_root is not None else BENCH_ROOT
    rows = json.loads((root / "coverage.json").read_text(encoding="utf-8"))["rows"]
    industries = set(cases_spec["industries"])
    statuses = set(cases_spec["statuses"])
    groups = set(cases_spec.get("groups") or ())
    ids = set(cases_spec.get("case_ids") or ())
    per_process = cases_spec.get("per_process")
    kept: Counter[str] = Counter()
    out: list[CaseRef] = []
    missing = 0
    for row in rows:
        case_id = str(row["case_id"])
        if row["industry"] not in industries:
            continue
        if groups and row["situation_group"] not in groups:
            continue
        if ids and case_id not in ids:
            continue
        if not (root / case_id / "case.meta.json").is_file():
            missing += 1
            continue
        if read_meta(root / case_id).get("status") not in statuses:
            continue
        process = str(row["process"])
        if per_process is not None and kept[process] >= per_process:
            continue
        kept[process] += 1
        out.append(CaseRef(case_id, str(row["industry"]), str(row.get("department") or ""),
                           process, str(row["situation_group"])))
    return out, missing


def _frozen_hash(set_info: SetInfo) -> str | None:
    """The set's hash when it verifies and is frozen, else ``None``."""
    try:
        verified = verify_set(set_info.path)
    except FreezeError:
        return None
    return verified.set_hash if verified.frozen_at is not None else None


def _inputs_hash(path: Path) -> str | None:
    """The inputs file's sha256, ``None`` when there is no readable file."""
    try:
        return inputs_sha256(path)
    except FreezeError:
        return None


def paper_freeze_ok(
    unlock: EvaluationUnlock, sets: list[SetInfo], inputs_path: Path | None = None
) -> bool:
    """The engine's fingerprint is still the unlock's, the vendored clones and installed
    packages are still the engine record's (``check_environment``), the inputs file
    (``inputs_path``, default ``INPUTS_PATH``) still has the sha256 the unlock verified, and
    every set still verifies, is frozen and has the hash the unlock verified."""
    try:
        if engine_fingerprint() != unlock.engine.fingerprint:
            return False
        check_environment(unlock.engine)
    except FreezeError:
        return False
    current = _inputs_hash(Path(inputs_path) if inputs_path is not None else INPUTS_PATH)
    if current is None or current != unlock.inputs_sha256:
        return False
    hashes = unlock.set_hashes
    for s in sets:
        current = _frozen_hash(s)
        if current is None or hashes.get(s.name) != current:
            return False
    return True


def status_counts(path: Path) -> Counter[str]:
    """How many episodes of a results file have each status, by the last row of each
    ``episode_id`` (as the report counts them), so a retried error that then scored is not an
    error any more."""
    last: dict[Any, str] = {}
    if Path(path).is_file():
        for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
            if line.strip():
                row = json.loads(line)
                last[row.get("episode_id", ("row", n))] = str(row.get("status"))
    return Counter(last.values())


def _done_ids(path: Path, *, retry_errors: bool = False) -> set[str]:
    """The episode ids already in the results file (cutting off a half-written last line).

    An id is done unless its last row has ``freeze_ok`` false, or, with ``retry_errors``,
    its last row has status ``error`` (the report keeps the last row of an id)."""
    if not path.is_file():
        return set()
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        cut = data.rfind(b"\n") + 1
        with path.open("r+b") as f:
            f.truncate(cut)
        data = data[:cut]
    last: dict[str, dict[str, Any]] = {}
    for n, line in enumerate(data.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise ExperimentRefused(f"{path}: line {n} is not a JSON row") from None
        last[str(row["episode_id"])] = row
    return {
        eid for eid, row in last.items()
        if row.get("freeze_ok") is not False
        and not (retry_errors and row.get("status") == "error")
    }


def _refuse_before_running(
    experiment: Experiment,
    cases: list[CaseRef],
    inputs: dict[str, CaseInputs],
    unlock: EvaluationUnlock | None,
    missing_folders: int = 0,
    inputs_hash: str | None = None,
) -> tuple[list[SetInfo], str]:
    """Every refusal of the module docstring, in order; the sets and the engine fingerprint
    the rows record."""
    known = set(DEV_INDUSTRIES) | set(PAPER_INDUSTRIES)
    unknown = sum(1 for c in cases if c.industry not in known)
    if unknown:
        raise ExperimentRefused(f"cases of no development or paper industry={unknown}")
    paper_cases = sum(1 for c in cases if c.industry in PAPER_INDUSTRIES)
    if paper_cases and not experiment.paper:
        raise ExperimentRefused(
            f"paper-industry cases={paper_cases} in an experiment that is not a paper one"
        )
    if experiment.paper and paper_cases != len(cases):
        raise ExperimentRefused(
            f"a paper experiment selects cases of no paper industry={len(cases) - paper_cases}"
        )
    if experiment.paper and missing_folders:
        raise ExperimentRefused(f"selected case folders missing={missing_folders}")
    if experiment.paper:
        missing = sum(
            1 for c in cases if c.case_id not in inputs or inputs[c.case_id].status != "approved"
        )
        if missing:
            raise ExperimentRefused(f"cases without approved inputs={missing}")
    try:
        sets = [SetInfo.read(d) for d in experiment.governance_sets]
    except FreezeError as e:
        raise ExperimentRefused(f"a governance set does not verify: {e}") from None
    if len({s.name for s in sets}) != len(sets):
        raise ExperimentRefused("two governance sets share a name")
    if not experiment.paper:
        try:
            return sets, engine_fingerprint()
        except FreezeError:
            return sets, "dev"
    modes = {s.mode for s in sets}
    if not all(mode in modes for mode in MODES):
        raise ExperimentRefused(
            f"a paper experiment needs a blind and an informed set (modes={sorted(modes)})"
        )
    unfrozen = sum(1 for s in sets if s.frozen_at is None)
    if unfrozen:
        raise ExperimentRefused(f"governance sets not frozen={unfrozen}")
    if unlock is None or not is_issued(unlock):
        raise ExperimentRefused("a paper experiment needs an unlock that unlock_paper issued")
    try:
        fingerprint = engine_fingerprint()
    except FreezeError as e:
        raise ExperimentRefused(f"the engine is not clean: {e}") from None
    if fingerprint != unlock.engine.fingerprint:
        raise ExperimentRefused("the engine's fingerprint is not the unlock's")
    outside = sum(1 for s in sets if unlock.set_hashes.get(s.name) != s.set_hash)
    if outside:
        raise ExperimentRefused(f"governance sets not verified by the unlock={outside}")
    if inputs_hash is None or inputs_hash != unlock.inputs_sha256:
        raise ExperimentRefused("the inputs file is not the one the unlock verified")
    return sets, fingerprint


def _load_inputs(path: Path) -> dict[str, CaseInputs]:
    return load_inputs(path) if Path(path).is_file() else {}


def _episode_inputs(
    experiment: Experiment, case: CaseRef, inputs: dict[str, CaseInputs]
) -> CaseInputs | None:
    item = inputs.get(case.case_id)
    if item is None:
        return None
    if experiment.paper:
        return item  # approved: checked before running
    return item if item.status in DEV_INPUT_STATUSES else None


@dataclass(frozen=True)
class _Plan:
    model: str
    set_info: SetInfo
    case: CaseRef
    arm: str
    rep: int


def _plan(experiment: Experiment, sets: list[SetInfo], cases: list[CaseRef]) -> Iterator[_Plan]:
    # Model first: a local server keeps one model loaded across its episodes.
    for model in experiment.models:
        for set_info in sets:
            for case in cases:
                for arm in experiment.arms:
                    for rep in range(experiment.repetitions):
                        yield _Plan(model, set_info, case, arm, rep)


def episode_seed(seed: int | None, rep: int) -> int | None:
    """Ruling R11a: each repetition gets its own seed, the experiment's seed plus ``rep``."""
    return None if seed is None else seed + rep


def model_sampling(sampling: Sampling, rep: int) -> Sampling:
    """The digital employee's sampling of repetition ``rep``."""
    return replace(sampling, seed=episode_seed(sampling.seed, rep))


def guard_sampling(sampling: Sampling, rep: int) -> Sampling:
    """The guard's sampling of repetition ``rep``: greedy and never thinking (as v1's
    ``guard_sampling``), whatever the digital employee's settings; the same seed and
    context length."""
    return Sampling(temperature=0.0, seed=episode_seed(sampling.seed, rep), think=False,
                    num_ctx=sampling.num_ctx)


def arm_guard_model(arm: Arm, guard_model: str) -> str | None:
    """The arm's resolved guard model: ``None`` for an arm with no defence or a defence that
    calls no model, the experiment's ``guard_model`` for ``@guard_model``, else the arm's."""
    if arm.guard is None or arm.guard_model is None:
        return None
    return guard_model if arm.guard_model == GUARD_MODEL_REF else arm.guard_model


def hf_identity(name: str) -> ModelIdentity:
    """An ``hf:<repo id>`` model's identity: the commit hash of its snapshot in the local
    HuggingFace cache, read without the network. Raises ``ExperimentRefused`` when the model
    is not cached."""
    if not name.startswith(HF_PREFIX):
        raise ValueError(f"{name!r} is not an {HF_PREFIX}<repo id> model")
    try:
        import huggingface_hub
    except ImportError:
        raise ExperimentRefused(f"{name}: huggingface_hub is not installed") from None
    try:
        snapshot = huggingface_hub.snapshot_download(name[len(HF_PREFIX):], local_files_only=True)
    except (OSError, ValueError):  # LocalEntryNotFoundError is an OSError
        raise ExperimentRefused(
            f"{name}: not in the local HuggingFace cache; download it before the experiment"
        ) from None
    return ModelIdentity(name, Path(snapshot).name)


def _close(model: Any) -> None:
    close = getattr(model, "close", None)
    if callable(close):
        close()


def run_experiment(
    path: Path,
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    chat_factory: Callable[..., ChatModel] = create_chat_model,
    unlock: EvaluationUnlock | None = None,
    identify: Callable[[str], ModelIdentity] | None = None,
    inputs_path: Path | None = None,
    bench_root: Path | None = None,
    settings: Settings | None = None,
    isolate: Callable[[list[str]], None] | None = None,
    retry_errors: bool = False,
) -> Path:
    """Run every episode of the experiment not yet in its results file; see the module
    docstring. Before each episode ``isolate`` (default: the Ollama unloader of
    ``aebench.run.isolation`` for the experiment's server) unloads the Ollama models the episode
    uses. With ``retry_errors`` an episode whose last row has status ``error`` runs again
    (the new row is appended; the report keeps the last row of an id). Returns the results
    file. Raises ``ExperimentRefused`` (and ``FreezeChanged``)
    and ``ModelUnavailable``."""
    experiment = load_experiment(path)
    root = Path(bench_root) if bench_root is not None else BENCH_ROOT
    cases, missing = select_cases_counted(experiment.cases, bench_root=root)
    print(f"cases={len(cases)} missing={missing}", flush=True)
    if not cases:
        raise ExperimentRefused("the experiment selects no case")
    inputs_file = Path(inputs_path) if inputs_path is not None else INPUTS_PATH
    inputs_hash = _inputs_hash(inputs_file)
    inputs = _load_inputs(inputs_file)
    sets, fingerprint = _refuse_before_running(
        experiment, cases, inputs, unlock, missing, inputs_hash
    )
    paper_unlock = unlock if experiment.paper else None
    isolate_models = isolate if isolate is not None else make_isolate(
        experiment.ollama_url, num_ctx=experiment.sampling.num_ctx
    )

    def who(name: str) -> ModelIdentity:
        if name.startswith(HF_PREFIX):
            return hf_identity(name)
        if identify is not None:
            return identify(name)
        return model_identity(name, ollama_url=experiment.ollama_url)

    identities = {name: who(name) for name in experiment.models}
    arm_guards = {a: arm_guard_model(ARMS[a], experiment.guard_model) for a in experiment.arms}
    guard_identities = {name: who(name) for name in dict.fromkeys(arm_guards.values()) if name}

    def guard_digest(arm: str) -> str | None:
        name = arm_guards[arm]
        return guard_identities[name].digest if name else None

    out = Path(out_dir) / f"{experiment.name}.jsonl"
    done = _done_ids(out, retry_errors=retry_errors)
    plan = list(_plan(experiment, sets, cases))

    def de_sampling(model: str) -> dict[str, Any]:
        d = experiment.model_sampling[model].to_dict()
        d.pop("seed")
        return d

    def plan_id(p: _Plan) -> str:
        return episode_id(
            case_id=p.case.case_id, arm=p.arm, set_hash=p.set_info.set_hash,
            model=identities[p.model].name, model_digest=identities[p.model].digest,
            seed=episode_seed(experiment.sampling.seed, p.rep), rep=p.rep,
            guard_model=arm_guards[p.arm], guard_digest=guard_digest(p.arm),
            sampling=de_sampling(p.model),
        )

    todo = [p for p in plan if plan_id(p) not in done]
    print(f"episodes={len(plan)} done={len(plan) - len(todo)} todo={len(todo)}", flush=True)
    if not todo:
        return out
    server_version = ollama_server_version(experiment.ollama_url)

    # One client per (model, repetition seed) and per (Ollama guard model, repetition seed):
    # a client keeps its sampling.
    models: dict[tuple[str, int], ChatModel] = {}
    guards: dict[tuple[str, int], ChatModel] = {}
    counts: Counter[str] = Counter()
    out.parent.mkdir(parents=True, exist_ok=True)
    issuer = TokenIssuer(SystemClock(), InMemoryJtiStore())
    try:
        with connect(settings or Settings.from_env()) as conn, out.open("a", encoding="utf-8") as f:
            for n, p in enumerate(todo, start=1):
                if (p.model, p.rep) not in models:
                    models[p.model, p.rep] = chat_factory(
                        p.model, model_sampling(experiment.model_sampling[p.model], p.rep),
                        ollama_url=experiment.ollama_url,
                    )
                guard: ChatModel | None = None
                guard_name = arm_guards[p.arm]
                if guard_name is not None and not guard_name.startswith(HF_PREFIX):
                    if (guard_name, p.rep) not in guards:
                        guards[guard_name, p.rep] = chat_factory(
                            guard_name, guard_sampling(experiment.sampling, p.rep),
                            ollama_url=experiment.ollama_url,
                        )
                    guard = guards[guard_name, p.rep]
                if paper_unlock is not None and not paper_freeze_ok(
                    paper_unlock, sets, inputs_file
                ):
                    raise FreezeChanged("the engine or a governance set changed; stopped")
                isolate_models(episode_ollama_models(p.model, guard_name))
                row = run_episode(
                    conn,
                    case=p.case,
                    case_dir=root / p.case.case_id,
                    arm=ARMS[p.arm],
                    set_info=p.set_info,
                    model=models[p.model, p.rep],
                    identity=identities[p.model],
                    guard=guard,
                    guard_model=experiment.guard_model,
                    guard_model_name=guard_name,
                    guard_digest=guard_digest(p.arm),
                    ollama_url=experiment.ollama_url,
                    seed=episode_seed(experiment.sampling.seed, p.rep),
                    num_ctx=experiment.sampling.num_ctx,
                    sampling=de_sampling(p.model),
                    rep=p.rep,
                    inputs=_episode_inputs(experiment, p.case, inputs),
                    engine_fingerprint=fingerprint,
                    paper=experiment.paper,
                    unlock=paper_unlock,
                    issuer=issuer,
                    inputs_sha256=inputs_hash,
                )
                row["ollama_isolated"] = True
                row["ollama_version"] = server_version
                freeze_ok = None
                if paper_unlock is not None:
                    freeze_ok = paper_freeze_ok(paper_unlock, sets, inputs_file)
                    row["freeze_ok"] = freeze_ok
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                f.flush()
                os.fsync(f.fileno())
                counts[str(row["status"])] += 1
                print(
                    f"[{n}/{len(todo)}] scored={counts['scored']}"
                    f" not_run={counts['not_run']} error={counts['error']}",
                    flush=True,
                )
                if freeze_ok is False:
                    raise FreezeChanged(
                        "the engine or a governance set changed during an episode; stopped"
                    )
                if conn.closed:
                    raise ExperimentRefused("the database connection closed; stopped")
    finally:
        for client in [*models.values(), *guards.values()]:
            _close(client)
    return out


"""One episode: one case, under one arm, with one governance set, model and repetition.

``run_episode`` runs the engine on the case with a model-backed digital employee
(``ModelExecutor``) and the simulated people and outside parties of the case
(``SimulatedEnvironment``), scores the run and returns its row. The flow:

1. The set's template for the case's process type (``templates/<process>.json``); none,
   one the set's manifest does not mark ``valid`` (final review I1: drafting gave up on
   it), or one that does not load, is ``not_run``.
2. The company pack and the case instance (the case inputs' subject and neutral request,
   never the case title), then the answer side, opened only here
   (``answer_side(case_dir, unlock=...)``), for the environment and the scorer.
3. One environment per run (ruling R4a): ``template=`` the run's template and, when the
   case has inputs, ``input_facts=`` their allow-list.
4. The executor (``build_executor``): a ``ModelExecutor`` with the arm's ``policy_prompt``
   and, on a guard arm, the arm's defence (``build_defence``, from the pack, the template
   and the models only): its call guard and output filter, or the executor it replaces.
   A TonomyX arm builds no defence.
5. ``run_case`` with the arm's controls and ``governance_version`` of ruling Q10. The
   runner writes nothing to ``core`` itself (ruling R5a): the scorer only reads it.
6. ``score`` and ``safety``.

A scored row records the install-time role mapping the run used (Task 14): ``binding``,
template role -> company role codes, and ``binding_exact``, whether every template role's
duties matched its codes exactly (``RunResult.binding``, ``binding_exact``). It names only
the template and the company pack; a row that was not scored has ``None`` for both.

``seed`` is the episode's own seed (the experiment's seed plus the repetition, ruling
R11a): the caller builds ``model`` and ``guard`` with it, and the row records it.

A guard arm's row records the arm's own resolved guard model (``guard_model_name``, ``None``
when its defence calls no model of its own) and its digest, and its episode id holds them
(ruling R11c; no guard keys when there is no guard model). Any other arm's row records the
experiment's ``guard_model``, as before, and no digest. ``defence_counts`` sums the steps'
``counters`` (for example how many outputs a detector replaced).

Outcomes: ``TemplateInvalid`` or ``BindingError`` is ``not_run``; ``ModelUnavailable``
propagates (the experiment stops, the row is not written, a resume repeats the episode);
any other exception is ``error``. ``wall_s`` is the time of ``run_case`` alone.

Paper rows (``paper=True``) carry no text of the scorer: no outcome mismatches and no
failed invariant details, only their counts, and not the run's ``refusals`` list (its
count stays); an ``error`` row's reason is the exception's type alone (a ``not_run`` reason
is the template's or the binding's findings, which name only the template and the company
pack). They keep ``steps``, the executor's records of the system's own calls: each call's
``reason`` is the platform's own refusal text, which names only rows of the run's own case
(ruling Q11), never the scorer's view of the answer. On a guard arm a ``guard_blocked``
call's reason is the guard's own text: Progent's ``ValidationError`` repeats the step's user
query (the trusted step content: system prompt and request), and Llama Guard's unreadable
verdict holds up to 200 characters of its reply. Both are built from what the digital
employee itself was shown, neither from the answer side. The scorer's view never reaches a
model.

Every row records ``inputs_sha256``, the sha256 of the inputs file the experiment read
(final review I6), so a report can tell which reviewed inputs a run used.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg

from aebench.arms.defence import Defence, build_defence
from aebench.arms.presets import Arm
from tonomyx.bench.cases import answer_side, company_pack_from_case, instance_from_case
from tonomyx.bench.environment import SimulatedEnvironment
from tonomyx.bench.freeze import EvaluationUnlock, verify_set
from tonomyx.bench.inputs import CaseInputs, placeholder_inputs
from tonomyx.bench.safety import safety
from tonomyx.bench.score import score
from tonomyx.config import REPO_ROOT
from tonomyx.contracts.token import TokenIssuer
from tonomyx.engine.run import TemplateInvalid, run_case
from tonomyx.executors.model import ModelExecutor, StepRecord
from tonomyx.governance.binding import BindingError
from tonomyx.governance.pack import CompanyPack
from tonomyx.governance.template import ProcessTemplate, TemplateError, load_template
from tonomyx.models.chat import ChatModel
from tonomyx.models.errors import ModelUnavailable
from tonomyx.models.identity import ModelIdentity
from tonomyx.tools.ports import RecordingMailSender

# 5: rows of an experiment record ``ollama_version`` (the report reads older rows too).
SCHEMA_VERSION = 6
COST_KEYS: tuple[str, ...] = (
    "prompt_tokens",
    "completion_tokens",
    "guard_prompt_tokens",
    "guard_completion_tokens",
    "model_latency_s",
    "guard_latency_s",
)


@dataclass(frozen=True)
class CaseRef:
    case_id: str
    industry: str
    department: str
    process: str
    situation_group: str


@dataclass(frozen=True)
class SetInfo:
    """A governance set as the runner uses it: verified against its manifest."""

    name: str
    mode: str
    set_hash: str
    path: Path
    frozen_at: str | None
    # (process, status) of each manifest entry: only a "valid" template is run (I1).
    statuses: tuple[tuple[str, str], ...] = ()

    @classmethod
    def read(cls, set_dir: Path) -> SetInfo:
        """Verify the set (``verify_set``; raises ``SetChanged``) and keep what rows name."""
        verified = verify_set(Path(set_dir))
        return cls(verified.name, verified.mode, verified.set_hash, Path(set_dir),
                   verified.frozen_at, process_statuses(Path(set_dir)))

    def valid(self, process: str) -> bool:
        """Whether the set's manifest marks the process's template ``valid``."""
        return dict(self.statuses).get(process) == "valid"

    @property
    def rel(self) -> str:
        """The set's folder, relative to the repository when it lies inside it (ruling R0b)."""
        try:
            return str(self.path.resolve().relative_to(REPO_ROOT))
        except ValueError:
            return str(self.path)

    def template_path(self, process: str) -> Path:
        return self.path / "templates" / f"{process}.json"


def process_statuses(set_dir: Path) -> tuple[tuple[str, str], ...]:
    """(process, status) of each entry of a set's ``manifest.json`` (verified by the
    caller), sorted by process."""
    manifest = json.loads((Path(set_dir) / "manifest.json").read_text(encoding="utf-8"))
    processes = manifest.get("processes") if isinstance(manifest, dict) else None
    if not isinstance(processes, dict):
        return ()
    return tuple(sorted(
        (str(pid), str(entry.get("status")))
        for pid, entry in processes.items()
        if isinstance(entry, dict)
    ))


def episode_id(
    *, case_id: str, arm: str, set_hash: str, model: str, model_digest: str, seed: int | None,
    rep: int, guard_model: str | None = None, guard_digest: str | None = None,
    sampling: Mapping[str, Any] | None = None,
) -> str:
    """The first 16 hex digits of the sha1 of the key's JSON (sorted keys).

    The key is ``case_id, arm, set_hash, model, model_digest, seed, rep``; a guard arm's key
    also holds ``guard_model`` and ``guard_digest`` (ruling R11c), so an episode run with
    another guard model is not taken as done. When ``sampling`` (the digital employee's
    sampling dict without the seed) is given, the key also holds it."""
    key: dict[str, Any] = {"case_id": case_id, "arm": arm, "set_hash": set_hash,
                           "model": model, "model_digest": model_digest, "seed": seed,
                           "rep": rep}
    if guard_model is not None or guard_digest is not None:
        key.update(guard_model=guard_model, guard_digest=guard_digest)
    if sampling is not None:
        key["sampling"] = dict(sampling)
    text = json.dumps(key, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def governance_version(set_info: SetInfo, pack_name: str, pack_version: str) -> str:
    """Ruling Q10: the set and its hash, and the company pack and its version."""
    return f"{set_info.name}@{set_info.set_hash[:12]}+{pack_name}@{pack_version}"


def _cost(records: tuple[StepRecord, ...]) -> dict[str, Any]:
    return {
        key: round(sum(getattr(r, key) for r in records), 6) if key.endswith("_s")
        else sum(getattr(r, key) for r in records)
        for key in COST_KEYS
    }


def _defence_counts(records: tuple[StepRecord, ...]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for r in records:
        counts.update(getattr(r, "counters", {}))
    return dict(sorted(counts.items()))


def build_executor(
    arm: Arm,
    *,
    model: ChatModel,
    pack: CompanyPack,
    template: ProcessTemplate,
    guard: ChatModel | None,
    guard_model_name: str | None,
    ollama_url: str,
    seed: int | None,
    num_ctx: int | None = None,
) -> Any:
    """The episode's executor: the defence's own, or a ``ModelExecutor`` with the arm's
    ``policy_prompt`` and the defence's guard and output filter (none on a TonomyX arm).
    ``num_ctx`` is the experiment's context length, for a bridge that calls Ollama itself."""
    defence = Defence()
    if arm.guard is not None:
        defence = build_defence(
            arm.guard, de_model=model, guard_model=guard, guard_model_name=guard_model_name,
            pack=pack, template=template, ollama_url=ollama_url, seed=seed, num_ctx=num_ctx,
        )
    if defence.executor is not None:
        return defence.executor
    return ModelExecutor(
        model, pack, policy_prompt=arm.policy_prompt, guard=defence.guard,
        output_filter=defence.output_filter,
    )


def _not_scored(row: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
    row.update(status=status, reason=reason, perfect=False, invariants_passed=0,
               invariants_total=0, outcome_mismatch_count=0, safety=None, stop=None,
               steps_run=[], outcomes={}, refusal_count=0)
    if not row["paper"]:
        row.update(outcome_mismatches=[], failed_invariants={}, refusals=[])
    return row


def run_episode(
    conn: psycopg.Connection[Any],
    *,
    case: CaseRef,
    case_dir: Path,
    arm: Arm,
    set_info: SetInfo,
    model: ChatModel,
    identity: ModelIdentity,
    guard: ChatModel | None,
    guard_model: str,
    guard_model_name: str | None,
    ollama_url: str,
    seed: int | None,
    rep: int,
    inputs: CaseInputs | None,
    engine_fingerprint: str,
    paper: bool,
    unlock: EvaluationUnlock | None,
    issuer: TokenIssuer,
    guard_digest: str | None = None,
    inputs_sha256: str | None = None,
    num_ctx: int | None = None,
    sampling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run and score one episode; see the module docstring. Raises ``ModelUnavailable``.

    ``guard`` is the client of the arm's resolved guard model when it is an Ollama model,
    ``guard_model_name`` that model's name (``hf:...`` included), ``guard_digest`` its
    digest and ``guard_model`` the experiment's ``guard_model``."""
    own_guard = arm.guard is not None
    row: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id(
            case_id=case.case_id, arm=arm.name, set_hash=set_info.set_hash,
            model=identity.name, model_digest=identity.digest, seed=seed, rep=rep,
            guard_model=guard_model_name if own_guard else None,
            guard_digest=guard_digest if own_guard else None,
            sampling=sampling,
        ),
        **asdict(case),
        "arm": arm.name,
        "set_name": set_info.name,
        "set_mode": set_info.mode,
        "set_hash": set_info.set_hash,
        "set_dir": set_info.rel,
        "model": identity.name,
        "model_digest": identity.digest,
        "guard_model": guard_model_name if own_guard else guard_model,
        "guard_digest": guard_digest if own_guard else None,
        "seed": seed,
        "sampling": dict(sampling) if sampling is not None else None,
        "rep": rep,
        "engine_fingerprint": engine_fingerprint,
        "governance_version": None,
        "inputs_status": inputs.status if inputs is not None else "placeholder",
        "inputs_sha256": inputs_sha256,
        "paper": paper,
        "freeze_ok": None,
        "binding": None,
        "binding_exact": None,
        "steps": [],
        "cost": dict.fromkeys(COST_KEYS, 0),
        "defence_counts": {},
        "wall_s": 0.0,
    }
    template_path = set_info.template_path(case.process)
    if not template_path.is_file():
        return _not_scored(row, "not_run", f"the set has no template for {case.process}")
    if not set_info.valid(case.process):
        return _not_scored(row, "not_run", "the set marks this template invalid")
    try:
        template: ProcessTemplate = load_template(template_path)
    except (TemplateError, ValueError, KeyError, TypeError) as exc:
        return _not_scored(row, "not_run", f"template does not load: {exc}")

    try:
        pack = company_pack_from_case(case_dir)
        instance = instance_from_case(case_dir, inputs or placeholder_inputs(case.case_id))
        answer = answer_side(case_dir, unlock=unlock)
        environment = SimulatedEnvironment(
            answer,
            input_facts=None if inputs is None else frozenset(inputs.input_facts),
            template=template,
        )
        executor = build_executor(
            arm, model=model, pack=pack, template=template, guard=guard,
            guard_model_name=guard_model_name, ollama_url=ollama_url, seed=seed,
            num_ctx=num_ctx,
        )
        version = governance_version(set_info, pack.name, pack.version)
        row["governance_version"] = version
        started = time.perf_counter()
        try:
            result = run_case(
                conn,
                template=template,
                pack=pack,
                instance=instance,
                executor=executor,
                environment=environment,
                governance_version=version,
                issuer=issuer,
                mail=RecordingMailSender(),
                controls=arm.controls,
            )
        finally:
            row["wall_s"] = round(time.perf_counter() - started, 6)
            row["steps"] = [asdict(r) for r in executor.records]
            row["cost"] = _cost(executor.records)
            row["defence_counts"] = _defence_counts(executor.records)
        report = score(conn, case.case_id, answer, result)
        verdict = safety(report, result, answer, case.situation_group)
    except ModelUnavailable:
        raise
    except (TemplateInvalid, BindingError) as exc:
        return _not_scored(row, "not_run", str(exc))
    except Exception as exc:  # noqa: BLE001 (any failure of one episode is its row)
        reason = type(exc).__name__ if paper else f"{type(exc).__name__}: {exc}"
        return _not_scored(row, "error", reason)

    row.update(
        status="scored",
        reason="",
        perfect=report.perfect,
        invariants_passed=report.invariants_passed,
        invariants_total=report.invariants_total,
        outcome_mismatch_count=len(report.outcome_mismatches),
        safety=asdict(verdict),
        stop=result.stop,
        steps_run=result.steps_run,
        outcomes=dict(result.outcomes),
        refusal_count=len(result.refusals),
        binding={role: list(codes) for role, codes in result.binding.items()},
        binding_exact=result.binding_exact,
    )
    if not paper:
        row.update(
            outcome_mismatches=list(report.outcome_mismatches),
            failed_invariants=dict(report.failed_invariants),
            refusals=list(result.refusals),
        )
    return row

"""Draft the shared governance set, one template per process type (spec L8, C14).

Per process: build the prompt, parse the reply, ``load_template`` and ``validate`` it
(blind: against no pack; informed: against the pack of each source case, which also
requires every template role to bind), and repair with the findings for up to
``MAX_ROUNDS`` model calls in all (``rounds`` counts them). The result is written to
``<out_dir>/templates/<process_id>.json`` with a ``manifest.json`` of hashes, the engine
fingerprint, ``started_at`` (before the first model call) and ``drafted_at`` (the last write),
both with microseconds (Task 10 N1), and ``inputs_sha256``, the sha256 of the inputs file
the caller drafted with (final review I6; the paper unlock compares it with the file).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from tonomyx.bench.cases import company_pack_from_case
from tonomyx.drafting.prompts import repair_prompt, system_prompt, user_prompt
from tonomyx.drafting.sources import CaseView, ProcessBrief
from tonomyx.governance.pack import CompanyPack, load_policy, load_roles
from tonomyx.governance.template import TemplateError, load_template
from tonomyx.governance.validate import validate
from tonomyx.models.identity import ModelIdentity, model_identity
from tonomyx.models.json_model import JsonModel, ModelError, ModelUnavailable

MAX_ROUNDS = 4  # one draft and up to three repair rounds
# Faults of a company's own pack: the template cannot repair them.
_PACK_FAULTS = frozenset({"DUPLICATE_ROLE", "TIER_APPROVER", "TIER_ORDER"})


@dataclass(frozen=True)
class DraftResult:
    process_id: str
    status: Literal["valid", "invalid"]
    template_path: Path | None
    findings: list[str]
    rounds: int


def pack_of_view(view: CaseView) -> CompanyPack:
    """The company pack of a view: its case folder's pack, or, with no folder, the roles and
    policy the view shows (enough to bind and validate)."""
    if view.case_dir is not None:
        return company_pack_from_case(view.case_dir)
    with tempfile.TemporaryDirectory() as tmp:
        roles, policy = Path(tmp, "roles.csv"), Path(tmp, "policy.json")
        roles.write_text(view.roles_csv, encoding="utf-8")
        policy.write_text(view.policy_json, encoding="utf-8")
        return CompanyPack(view.case_id, "view", load_roles(roles), load_policy(policy), (), {})


def _check(
    path: Path, process_id: str, packs: list[CompanyPack | None]
) -> tuple[list[str], list[str]]:
    """(errors, warnings) of the template at ``path``."""
    try:
        template = load_template(path)
    except (TemplateError, KeyError, TypeError, ValueError, AttributeError, ArithmeticError) as e:
        return [f"the template does not load: {type(e).__name__}: {e}"], []
    errors: list[str] = []
    warnings: list[str] = []
    if template.id != process_id:
        errors.append(f"id is {template.id!r}, it must be {process_id!r}")
    for n, pack in enumerate(packs, start=1):
        prefix = "" if pack is None else f"company {n}: "
        for f in validate(template, pack):
            if f.code in _PACK_FAULTS:
                continue
            line = f"{prefix}{f.code} {f.where}: {f.message}"
            (errors if f.level == "error" else warnings).append(line)
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _draft_one(
    brief: ProcessBrief, mode: str, views: list[CaseView], model: JsonModel, out_dir: Path,
    seed: int, system: str,
) -> tuple[DraftResult, str]:
    packs: list[CompanyPack | None] = (
        [pack_of_view(v) for v in views] if mode == "informed" else [None]
    )
    first = user_prompt(brief, mode, views)
    user = first
    path = out_dir / "templates" / f"{brief.process_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    if mode == "informed" and not views:
        return DraftResult(brief.process_id, "invalid", None, ["no source cases"], 0), first
    written = False
    errors: list[str] = []
    warnings: list[str] = []
    rounds = 0
    while rounds < MAX_ROUNDS:
        rounds += 1
        try:
            data: dict[str, Any] = model.complete_json(system, user, seed=seed).data
        except ModelUnavailable:
            raise
        except ModelError as e:
            errors, warnings = [f"the reply was not a JSON object: {e}"], []
            user = repair_prompt(first, "(no usable reply)", errors)
            continue
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)
        path.write_text(text + "\n", encoding="utf-8")
        written = True
        errors, warnings = _check(path, brief.process_id, packs)
        if not errors:
            break
        user = repair_prompt(first, text, errors)
    status: Literal["valid", "invalid"] = "invalid" if errors else "valid"
    result = DraftResult(
        brief.process_id, status, path if written else None, errors + warnings, rounds
    )
    return result, first


def draft_set(
    name: str,
    mode: Literal["blind", "informed"],
    briefs: list[ProcessBrief],
    views: dict[str, list[CaseView]],
    model: JsonModel,
    out_dir: Path,
    *,
    seed: int,
    engine_fingerprint: str,
    identity: ModelIdentity | None = None,
    inputs_sha256: str | None = None,
) -> list[DraftResult]:
    out_dir = Path(out_dir)
    # Before the first model call: the unlock requires drafting to have begun after the
    # engine freeze, not only to have ended after it.
    started_at = datetime.now(UTC).isoformat(timespec="microseconds")
    system = system_prompt()
    ident = identity or model_identity(model.name)
    results: list[DraftResult] = []
    firsts: list[str] = []
    for brief in briefs:
        view_list = views.get(brief.process_id, []) if mode == "informed" else []
        result, first = _draft_one(brief, mode, view_list, model, out_dir, seed, system)
        results.append(result)
        firsts.append(first)
        # After each process, so an aborted run still leaves the hashes of those done.
        _write_manifest(
            out_dir, name, mode, ident, system, firsts, seed, engine_fingerprint, results,
            started_at, inputs_sha256,
        )
    if not briefs:
        _write_manifest(
            out_dir, name, mode, ident, system, [], seed, engine_fingerprint, [], started_at,
            inputs_sha256,
        )
    return results


def _write_manifest(
    out_dir: Path, name: str, mode: str, ident: ModelIdentity, system: str, firsts: list[str],
    seed: int, engine_fingerprint: str, results: list[DraftResult], started_at: str,
    inputs_sha256: str | None = None,
) -> None:
    prompt_hash = hashlib.sha256("\n\x00\n".join([system, *firsts]).encode("utf-8")).hexdigest()
    manifest = {
        "name": name,
        "mode": mode,
        "model": ident.name,
        "model_digest": ident.digest,
        "prompt_hash": prompt_hash,
        "seed": seed,
        "engine_fingerprint": engine_fingerprint,
        "started_at": started_at,
        "drafted_at": datetime.now(UTC).isoformat(timespec="microseconds"),
        "inputs_sha256": inputs_sha256,
        "processes": {
            r.process_id: {
                "status": r.status,
                "sha256": _sha(r.template_path) if r.template_path else None,
                "rounds": r.rounds,
            }
            for r in results
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

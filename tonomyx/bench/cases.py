"""A bench case folder as the engine's inputs, and its answer side for the environment and scoring.

A bench case (``data/bench_v1/<case>/``) holds three kinds of files:

- governance: ``roles.csv``, ``policy.json``, ``kb/`` and the master tables of
  ``data/`` (classified ``master`` in the core schema): ``company_pack_from_case``;
- the case instance: the other tables of ``data/`` (history documents, approvals,
  payments), with the subject and request of the case inputs: ``instance_from_case``;
- the answer side: ``process.json``, ``expected/`` and ``attacks.json``:
  ``answer_side``, for the simulated environment and the scorer only (spec C12). It
  also carries each role code's actor kind from ``roles.csv``, so the environment
  knows which side made a case document, and the instance's given tables, so the
  scorer knows which rows a run made.

Paper isolation (spec C10, L6). The first two are not answers and load for every
industry. ``answer_side`` reads ``case.meta.json`` first and refuses, before
opening any other file, a case of a paper industry (``PAPER_INDUSTRIES``), and
equally a case whose industry is not a development industry (missing, blank or
unknown), so a meta file with a typo cannot leak a paper answer. A paper industry opens
only with an ``EvaluationUnlock`` that ``tonomyx.bench.freeze.unlock_paper`` issued after
checking the engine and governance freezes (spec C10, L8); an industry of neither list never
opens.

Bench cases carry no ``pack.json``: the pack is named after the case and versioned
by the generator's prompt version (``bench`` when the meta has none).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tonomyx.bench.freeze import EvaluationUnlock, is_issued
from tonomyx.config import REPO_ROOT
from tonomyx.engine.run import CaseInstance
from tonomyx.governance.pack import CompanyPack, load_kb, load_policy, load_roles
from tonomyx.tools.core.context import MASTER_TABLES

if TYPE_CHECKING:
    from tonomyx.bench.inputs import CaseInputs

DEV_INDUSTRIES: tuple[str, ...] = (
    "san_xuat",
    "nha_hang_khach_san",
    "y_te",
    "giao_duc",
    "xay_dung",
    "cho_thue_bds",
)
PAPER_INDUSTRIES: tuple[str, ...] = ("ban_le", "phan_phoi", "van_tai", "cntt_phan_mem")

BENCH_ROOT: Path = REPO_ROOT / "data" / "bench_v1"

UNVERSIONED = "bench"


class PaperCaseRefused(Exception):
    """The answers of a paper-industry case (or of a case of no development industry) are
    not read."""


@dataclass(frozen=True)
class AnswerSide:
    """What a case says should happen. Only the simulated environment and the scorer read it."""

    case_id: str
    industry: str
    process: dict[str, Any]
    final_state: dict[str, list[dict[str, str]]]
    events: list[dict[str, str]]
    outcome: dict[str, Any]
    invariants: Any
    attacks: Any | None = None
    # The actor kind of each role code (roles.csv): who made a case document.
    role_kinds: dict[str, str] = field(default_factory=dict)
    # The operational tables of data/ (the instance's given data, not an answer): the rows
    # present before the run, which keep their ids. The scorer tells the run's rows by them.
    given: dict[str, list[dict[str, str]]] = field(default_factory=dict)


def read_meta(case_dir: Path) -> dict[str, Any]:
    meta: dict[str, Any] = json.loads(
        (Path(case_dir) / "case.meta.json").read_text(encoding="utf-8")
    )
    return meta


def _case_id(case_dir: Path, meta: dict[str, Any]) -> str:
    return str(meta.get("case_id") or Path(case_dir).name)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _tables(directory: Path) -> dict[str, list[dict[str, str]]]:
    if not directory.is_dir():
        return {}
    return {p.stem: _read_csv(p) for p in sorted(directory.glob("*.csv"))}


def _split_data(case_dir: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    """The tables of ``data/``: master ones (governance) and the rest (the instance)."""
    master: dict[str, list[dict[str, str]]] = {}
    operational: dict[str, Any] = {}
    for table, rows in _tables(Path(case_dir) / "data").items():
        (master if table in MASTER_TABLES else operational)[table] = rows
    return master, operational


# --- governance and instance: every industry ------------------------------------------------


def company_pack_from_case(case_dir: Path) -> CompanyPack:
    """The case's company: roles, policy, knowledge base and master data."""
    case_dir = Path(case_dir)
    meta = read_meta(case_dir)
    generator = meta.get("generator") or {}
    master, _ = _split_data(case_dir)
    return CompanyPack(
        name=_case_id(case_dir, meta),
        version=str(generator.get("prompt_version") or UNVERSIONED),
        roles=load_roles(case_dir / "roles.csv"),
        policy=load_policy(case_dir / "policy.json"),
        kb=load_kb(case_dir / "kb"),
        master=master,
    )


def instance_from_case(case_dir: Path, inputs: CaseInputs) -> CaseInstance:
    """The case to run: its id, the subject and neutral request of ``inputs`` (never the
    meta title) and the operational tables of ``data/``."""
    case_dir = Path(case_dir)
    meta = read_meta(case_dir)
    _, operational = _split_data(case_dir)
    return CaseInstance(
        case_id=_case_id(case_dir, meta),
        title=inputs.subject,
        request=inputs.request,
        data=operational,
    )


# --- the answer side: development industries only -------------------------------------------


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def answer_side(case_dir: Path, *, unlock: EvaluationUnlock | None = None) -> AnswerSide:
    """Load ``process.json``, ``expected/`` and ``attacks.json`` (if present).

    Raises ``PaperCaseRefused`` before any of them is opened when the case's industry
    is a paper industry and ``unlock`` is not an unlock ``unlock_paper`` issued, or when
    the industry is not a development industry at all (with or without an unlock).
    """
    case_dir = Path(case_dir)
    meta = read_meta(case_dir)
    case_id = _case_id(case_dir, meta)
    industry = meta.get("industry")
    if industry in PAPER_INDUSTRIES:
        if unlock is None:
            raise PaperCaseRefused(
                f"{case_id}: {industry} is a paper industry; its answers are not read"
            )
        if not is_issued(unlock):
            raise PaperCaseRefused(
                f"{case_id}: {industry} is a paper industry and the unlock was not issued"
                " by unlock_paper; its answers are not read"
            )
    elif industry not in DEV_INDUSTRIES:
        raise PaperCaseRefused(
            f"{case_id}: industry {industry!r} is not a development industry;"
            " its answers are not read"
        )
    expected = case_dir / "expected"
    invariants_path = expected / "invariants.json"
    if not invariants_path.is_file():
        invariants_path = case_dir / "invariants.json"
    events_path = expected / "events.csv"
    attacks_path = case_dir / "attacks.json"
    return AnswerSide(
        case_id=case_id,
        industry=str(industry),
        process=_json(case_dir / "process.json"),
        final_state=_tables(expected / "final_state"),
        events=_read_csv(events_path) if events_path.is_file() else [],
        outcome=_json(expected / "outcome.json") if (expected / "outcome.json").is_file() else {},
        invariants=_json(invariants_path) if invariants_path.is_file() else None,
        attacks=_json(attacks_path) if attacks_path.is_file() else None,
        role_kinds={r.code: r.kind for r in load_roles(case_dir / "roles.csv")},
        given=_split_data(case_dir)[1],
    )

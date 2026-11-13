"""What the drafter may read: process names (blind) and the general description of cases
(informed).

``case_view`` opens only ``roles.csv``, ``policy.json``, ``kb/*.md`` and ``data/*.csv`` of a
case, plus the bench's ``coverage.json`` for the case's industry and process. It never
opens ``case.meta.json``, ``story.md``, ``process.json``, ``expected/`` or ``attacks.json``,
and it reads only governance and opening data, which every industry may load (spec L8).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tonomyx.bench.inputs import CaseInputs


@dataclass(frozen=True)
class ProcessBrief:
    process_id: str
    name_vi: str
    name_en: str
    department_id: str
    department_vi: str
    industries: tuple[str, ...]
    # "ten (name_en)" of each industry, from axes.json, for the prompt.
    industry_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseView:
    case_id: str
    request: str
    roles_csv: str
    policy_json: str
    kb: dict[str, str] = field(default_factory=dict)
    opening_data: dict[str, str] = field(default_factory=dict)
    case_dir: Path | None = None


def _rows(coverage_path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = json.loads(coverage_path.read_text(encoding="utf-8"))["rows"]
    return rows


def briefs(axes_path: Path, industries: tuple[str, ...] | list[str]) -> list[ProcessBrief]:
    """The processes that occur in ``industries``, in the order of ``axes.json``."""
    axes_path = Path(axes_path)
    axes = json.loads(axes_path.read_text(encoding="utf-8"))
    wanted = set(industries)
    named = {i["id"]: f"{i['ten']} ({i['name_en']})" for i in axes["industries"]}
    seen: dict[str, list[str]] = {}
    for row in _rows(axes_path.with_name("coverage.json")):
        if row["industry"] in wanted:
            seen.setdefault(str(row["process"]), [])
            if row["industry"] not in seen[str(row["process"])]:
                seen[str(row["process"])].append(str(row["industry"]))
    out: list[ProcessBrief] = []
    for dept in axes["departments"]:
        for proc in dept["processes"]:
            if proc["id"] in seen:
                out.append(
                    ProcessBrief(
                        proc["id"], proc["ten"], proc["name_en"], dept["id"], dept["ten"],
                        tuple(sorted(seen[proc["id"]])),
                        tuple(named.get(i, i) for i in sorted(seen[proc["id"]])),
                    )
                )
    return out


def coverage_row(case_dir: Path) -> dict[str, object]:
    """The coverage row of a case (its industry and process; never the meta's)."""
    case_dir = Path(case_dir)
    for row in _rows(case_dir.parent / "coverage.json"):
        if row["case_id"] == case_dir.name:
            return row
    raise KeyError(f"{case_dir.name}: not in coverage.json")


def case_view(case_dir: Path, inputs: CaseInputs) -> CaseView:
    case_dir = Path(case_dir)
    kb = {
        p.stem: p.read_text(encoding="utf-8") for p in sorted((case_dir / "kb").glob("*.md"))
    }
    data = {
        p.stem: p.read_text(encoding="utf-8") for p in sorted((case_dir / "data").glob("*.csv"))
    }
    return CaseView(
        case_id=case_dir.name,
        request=inputs.request,
        roles_csv=(case_dir / "roles.csv").read_text(encoding="utf-8"),
        policy_json=(case_dir / "policy.json").read_text(encoding="utf-8"),
        kb=kb,
        opening_data=data,
        case_dir=case_dir,
    )

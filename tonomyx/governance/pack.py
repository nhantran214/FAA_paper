"""Company pack: roles, policy, knowledge base and master data of one company."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from tonomyx.enforce.controls import forbidden_declaration_keys


class PackError(ValueError):
    """A company pack that cannot be loaded as it is declared."""


def _refuse_controls(raw: Any, where: str) -> None:
    forbidden = forbidden_declaration_keys(raw)
    if forbidden:
        raise PackError(
            f"{where} declares {forbidden}: enforcement is switched only by the caller of"
            " run_case, never by a declaration"
        )


@dataclass(frozen=True)
class Role:
    code: str
    kind: str
    drafts: frozenset[str]
    may_request: bool
    decides: frozenset[str]


@dataclass(frozen=True)
class Tier:
    max: Decimal | None
    approver: str


@dataclass(frozen=True)
class ApprovalRule:
    loai_pd: str
    maker_checker: bool
    tiers: tuple[Tier, ...]


@dataclass(frozen=True)
class Policy:
    approval_rules: dict[str, ApprovalRule]
    caps: dict[str, Decimal]
    tolerances: dict[str, Decimal]
    statutory_refs: tuple[str, ...]


@dataclass(frozen=True)
class KbArticle:
    id: str
    title: str
    body: str


@dataclass(frozen=True)
class CompanyPack:
    name: str
    version: str
    roles: tuple[Role, ...]
    policy: Policy
    kb: tuple[KbArticle, ...]
    master: dict[str, list[dict[str, Any]]]


def _cell_set(value: str | None) -> frozenset[str]:
    return frozenset(x for x in (value or "").split("|") if x)


def load_roles(path: Path) -> tuple[Role, ...]:
    with path.open(newline="", encoding="utf-8") as f:
        return tuple(
            Role(code=r["ma_vai"], kind=r["loai"], drafts=_cell_set(r["soan_bang"]),
                 may_request=(r["yeu_cau_duyet"] or "").strip() == "t",
                 decides=_cell_set(r["duyet_loai"]))
            for r in csv.DictReader(f))


def load_policy(path: Path) -> Policy:
    raw = json.loads(path.read_text(encoding="utf-8"))
    _refuse_controls(raw, path.name)
    rules = {}
    for r in raw.get("approval_rules", []):
        tiers = tuple(Tier(None if t["max"] is None else Decimal(str(t["max"])),
                           t["nguoi_duyet"]) for t in r["tiers"])
        rules[r["loai_pd"]] = ApprovalRule(r["loai_pd"], bool(r["maker_checker"]), tiers)
    return Policy(
        approval_rules=rules,
        caps={k: Decimal(str(v)) for k, v in raw.get("caps", {}).items()},
        tolerances={k: Decimal(str(v)) for k, v in raw.get("tolerances", {}).items()},
        statutory_refs=tuple(raw.get("statutory_refs", [])))


def load_kb(directory: Path) -> tuple[KbArticle, ...]:
    if not directory.is_dir():
        return ()
    out = []
    for p in sorted(directory.glob("*.md")):
        body = p.read_text(encoding="utf-8")
        first = body.strip().splitlines()[0] if body.strip() else ""
        out.append(KbArticle(p.stem, first.lstrip("# ").strip() or p.stem, body))
    return tuple(out)


def _load_master(directory: Path) -> dict[str, list[dict[str, Any]]]:
    if not directory.is_dir():
        return {}
    out = {}
    for p in sorted(directory.glob("*.csv")):
        with p.open(newline="", encoding="utf-8") as f:
            out[p.stem] = [dict(r) for r in csv.DictReader(f)]
    return out


def load_company_pack(directory: Path) -> CompanyPack:
    directory = Path(directory)
    meta = json.loads((directory / "pack.json").read_text(encoding="utf-8"))
    _refuse_controls(meta, "pack.json")
    return CompanyPack(
        name=meta["name"], version=meta["version"],
        roles=load_roles(directory / "roles.csv"),
        policy=load_policy(directory / "policy.json"),
        kb=load_kb(directory / "kb"),
        master=_load_master(directory / "master"))

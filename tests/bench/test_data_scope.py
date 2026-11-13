"""The data folder holds the four e-commerce industries and nothing else."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "data" / "bench_v1"
PAPER = {"ban_le", "phan_phoi", "van_tai", "cntt_phan_mem"}


def test_data_holds_only_paper_industry_cases() -> None:
    rows = json.loads((BENCH_ROOT / "coverage.json").read_text())["rows"]
    folders = {p.name for p in BENCH_ROOT.glob("CASE-*") if p.is_dir()}
    assert {r["industry"] for r in rows} == PAPER
    assert folders == {r["case_id"] for r in rows} and len(folders) == 96


def test_no_generator_files_remain() -> None:
    assert not (BENCH_ROOT / "tools").exists() and not (BENCH_ROOT / "fixtures").exists()
    assert not list(BENCH_ROOT.glob("CASE-*/assumptions.json"))
    assert not list(BENCH_ROOT.glob("CASE-*/critic.json"))
    assert sorted(p.name for p in (REPO_ROOT / "data").iterdir()) == ["bench_v1", "evaluation"]

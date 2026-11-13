"""The paper tables and figures on synthetic rows."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from aebench.analysis.stats import holm, wilson
from aebench.arms.presets import ARMS
from aebench.cli import main
from aebench.report.evaluation import ReportRefused
from aebench.report.paper import write_paper_artefacts
from tests.aebench.test_report import recorded_guard_model

TABLES = ["tab_fidelity", "tab_safety", "tab_false_refusal", "tab_cost", "tab_defence",
          "tab_models"]
FIGURES = ["fig_benchmarks", "fig_fidelity_safety", "fig_cost"]


def _row(arm: str, case: str, *, industry: str = "ban_le", set_name: str = "g-blind",
         mode: str = "blind", model: str = "m1", perfect: bool = True, attack: bool = False,
         happened: int = 0, blocked: bool | None = None, fp: str = "dev",
         guard: str | None = None, defence: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "paper": True, "binding_exact": True, "episode_id": f"{arm}-{case}-{set_name}-{model}",
        "case_id": case, "industry": industry, "department": "d", "process": "p", "arm": arm,
        "set_name": set_name, "set_mode": mode, "set_dir": "nowhere", "model": model, "rep": 0,
        "guard_model": recorded_guard_model(arm), "guard_digest": guard,
        "engine_fingerprint": fp, "freeze_ok": True,
        "status": "scored", "perfect": perfect,
        "safety": {"attack": attack, "forbidden_ids": ["f1", "f2"] if attack else [],
                   "forbidden_happened": ["f1"] * happened, "wrongly_blocked": blocked,
                   "unmapped_writes": 0},
        "cost": {"prompt_tokens": 10, "completion_tokens": 5, "guard_prompt_tokens": 2,
                 "guard_completion_tokens": 1, "model_latency_s": 0.5, "guard_latency_s": 0.2},
        "wall_s": 2.0, "defence_counts": defence,
    }


def _rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for industry in ("ban_le", "van_tai"):
        for set_name, mode in (("g-blind", "blind"), ("g-informed", "informed")):
            for model in ("m1", "m2"):
                for arm in ("full", "bare", "progent"):
                    for i in range(4):
                        case = f"SECRETCASE-{industry}-{i}"
                        guarded = arm == "progent"
                        rows.append(_row(
                            arm, case, industry=industry, set_name=set_name, mode=mode,
                            model=model, perfect=(i < 3 if arm == "full" else i < 2),
                            attack=i == 3, happened=1 if (i == 3 and arm == "bare") else 0,
                            blocked=(i == 0) if (i < 3 and arm != "progent") else None,
                            guard="d" if guarded else None,
                            defence={"progent_detections": 2} if guarded else None,
                        ))
    return rows


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_wilson_known_value() -> None:
    lo, hi = wilson(3, 4)  # type: ignore[misc]
    assert lo == pytest.approx(0.3006, abs=1e-3)
    assert hi == pytest.approx(0.9544, abs=1e-3)
    assert wilson(0, 0) is None


def test_writes_every_artefact(tmp_path: Path) -> None:
    paths = write_paper_artefacts(_rows(), tmp_path)
    for name in TABLES:
        assert (tmp_path / f"{name}.csv").is_file() and (tmp_path / f"{name}.tex").is_file()
    for name in FIGURES:
        assert (tmp_path / f"{name}.csv").is_file()
        assert (tmp_path / f"{name}.pdf").read_bytes().startswith(b"%PDF")
    assert len(paths) == 18 and all(p.is_file() for p in paths)


def test_fidelity_csv_values_and_wilson(tmp_path: Path) -> None:
    write_paper_artefacts(_rows(), tmp_path)
    path = tmp_path / "tab_fidelity.csv"
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header == ("arm,set,set_mode,benchmark,episodes,perfect,perfect_share,"
                      "ci_low,ci_high,pairs,only_reference_perfect,only_arm_perfect,"
                      "p_value,p_holm")
    row = next(r for r in _read(path) if (r["arm"], r["set"], r["benchmark"])
               == ("full", "g-blind", "ban_le"))
    assert (row["episodes"], row["perfect"], row["perfect_share"]) == ("8", "6", "0.75")
    lo, hi = wilson(6, 8)  # type: ignore[misc]
    assert float(row["ci_low"]) == pytest.approx(lo, abs=1e-5)
    assert float(row["ci_high"]) == pytest.approx(hi, abs=1e-5)
    assert any(r["benchmark"] == "all" for r in _read(path))
    assert not any(r["benchmark"] == "phan_phoi" and r["episodes"] != "0" for r in _read(path))


def test_safety_table_has_mcnemar_vs_full(tmp_path: Path) -> None:
    write_paper_artefacts(_rows(), tmp_path)
    rows = _read(tmp_path / "tab_safety.csv")
    bare = next(r for r in rows if (r["arm"], r["set"], r["benchmark"])
                == ("bare", "g-blind", "all"))
    # bare is unsafe on 4 attack pairs where full is safe: b=4, c=0, exact p=0.125, Holm x2
    assert (bare["pairs"], bare["excluded_pairs"]) == ("4", "0")
    assert (bare["only_reference_unsafe"], bare["only_arm_unsafe"]) == ("0", "4")
    assert float(bare["p_value"]) == pytest.approx(0.125)
    assert float(bare["p_holm"]) == pytest.approx(0.25)
    progent = next(r for r in rows if (r["arm"], r["set"], r["benchmark"])
                   == ("progent", "g-blind", "all"))
    assert float(progent["p_holm"]) == pytest.approx(1.0)
    one = next(r for r in rows if (r["arm"], r["set"], r["benchmark"])
               == ("bare", "g-blind", "ban_le"))
    assert (one["pairs"], one["only_arm_unsafe"]) == ("2", "2")
    assert float(bare["safe_share"]) == pytest.approx(0.5)  # 1 of 2 forbidden effects happened
    full = next(r for r in rows if (r["arm"], r["set"], r["benchmark"])
                == ("full", "g-blind", "all"))
    assert full["p_holm"] == ""


def test_fidelity_csv_carries_perfect_mcnemar(tmp_path: Path) -> None:
    write_paper_artefacts(_rows(), tmp_path)
    path = tmp_path / "tab_fidelity.csv"
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header.endswith(",pairs,only_reference_perfect,only_arm_perfect,p_value,p_holm")
    bare = next(r for r in _read(path) if (r["arm"], r["set"], r["benchmark"])
                == ("bare", "g-blind", "all"))
    assert (bare["pairs"], bare["only_reference_perfect"], bare["only_arm_perfect"]) \
        == ("16", "4", "0")
    assert float(bare["p_holm"]) == pytest.approx(0.25)


def test_every_arm_is_tested_against_full_whatever_guard_model_it_records(
    tmp_path: Path,
) -> None:
    # Final review C1: rows carry each arm's own guard model; every arm still pairs with full.
    rows = []
    for k, arm in enumerate(ARMS):
        for i in range(8):
            attack = i >= 4
            rows.append(_row(arm, f"c{i}", perfect=arm == "full" or i < k % 4, attack=attack,
                             happened=1 if attack and arm != "full" and i - 4 < k % 4 else 0,
                             blocked=False if not attack else None))
    write_paper_artefacts(rows, tmp_path)
    others = [a for a in ARMS if a != "full"]
    for name, outcome in (("tab_fidelity", "pairs"), ("tab_safety", "pairs")):
        got = {r["arm"]: r for r in _read(tmp_path / f"{name}.csv")
               if (r["set"], r["benchmark"]) == ("g-blind", "all")}
        assert all(got[a][outcome] == ("8" if name == "tab_fidelity" else "4") for a in others), \
            (name, {a: got[a][outcome] for a in others})
        ps = [float(got[a]["p_value"]) for a in ARMS if a in others]
        assert [float(got[a]["p_holm"]) for a in others] == pytest.approx(holm(ps)), name


def test_missing_cells_render_as_dash(tmp_path: Path) -> None:
    # full has no benign episode
    rows = [_row("full", "a", attack=True), _row("bare", "b", blocked=True)]
    write_paper_artefacts(rows, tmp_path)
    tex = (tmp_path / "tab_false_refusal.tex").read_text(encoding="utf-8")
    assert "--" in tex or "\\textendash" in tex
    csv_rows = _read(tmp_path / "tab_false_refusal.csv")
    full = next(r for r in csv_rows if r["arm"] == "full" and r["benchmark"] == "ban_le")
    assert full["wrongly_blocked_share"] == "" and full["ci_low"] == ""


def test_artefacts_refuse_mixed_engines(tmp_path: Path) -> None:
    rows = [_row("full", "a"), _row("bare", "b", fp="other")]
    with pytest.raises(ReportRefused):
        write_paper_artefacts(rows, tmp_path)
    path = tmp_path / "r.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert main(["paper-artefacts", str(path), "--out", str(tmp_path / "o")]) == 2


def test_artefacts_refuse_rows_without_a_paper_row(tmp_path: Path) -> None:
    rows = [{**_row("full", "a"), "paper": False, "industry": "giao_duc"},
            {**_row("bare", "a"), "paper": False, "industry": "giao_duc"}]
    with pytest.raises(ReportRefused, match="paper row"):
        write_paper_artefacts(rows, tmp_path / "x")
    with pytest.raises(ReportRefused, match="paper row"):
        write_paper_artefacts([], tmp_path / "y")
    path = tmp_path / "r.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert main(["paper-artefacts", str(path), "--out", str(tmp_path / "o")]) == 2
    assert not (tmp_path / "o").exists()


def test_cli_reads_several_files(tmp_path: Path) -> None:
    rows = _rows()
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_text("\n".join(json.dumps(r) for r in rows if r["industry"] == "ban_le"))
    b.write_text("\n".join(json.dumps(r) for r in rows if r["industry"] == "van_tai"))
    assert main(["paper-artefacts", str(a), str(b), "--out", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "tab_fidelity.tex").is_file()


def test_tex_escapes_specials(tmp_path: Path) -> None:
    write_paper_artefacts(_rows(), tmp_path)
    for name in TABLES:
        tex = (tmp_path / f"{name}.tex").read_text(encoding="utf-8")
        for rule in ("\\toprule", "\\midrule", "\\bottomrule"):
            assert rule in tex
        assert "\\begin{table" not in tex and "\\caption" not in tex
        stripped = tex.replace("\\_", "").replace("\\%", "")
        assert "_" not in stripped and "%" not in stripped
    fidelity = (tmp_path / "tab_fidelity.tex").read_text(encoding="utf-8")
    assert "ban\\_le" in fidelity and "G-blind" in fidelity and "G-informed" in fidelity
    assert "75.0\\%" in fidelity


def test_no_case_ids_in_artefacts(tmp_path: Path) -> None:
    write_paper_artefacts(_rows(), tmp_path)
    for p in tmp_path.iterdir():
        assert b"SECRETCASE" not in p.read_bytes(), p.name


def test_output_is_deterministic(tmp_path: Path) -> None:
    write_paper_artefacts(_rows(), tmp_path / "1")
    write_paper_artefacts(_rows(), tmp_path / "2")
    for name in FIGURES:
        assert ((tmp_path / "1" / f"{name}.pdf").read_bytes()
                == (tmp_path / "2" / f"{name}.pdf").read_bytes())


def test_every_arm_has_its_own_marker_and_models_their_fill() -> None:
    from aebench.report.paper import ARMS, MODEL_FILLS, _style

    assert len({_style(a)[1] for a in ARMS}) == len(ARMS)
    assert len(set(MODEL_FILLS)) == len(MODEL_FILLS) >= 4


def test_scatter_figures_fit_one_column(tmp_path: Path) -> None:
    import re

    write_paper_artefacts(_rows(), tmp_path)
    for name in ("fig_fidelity_safety", "fig_cost"):
        data = (tmp_path / f"{name}.pdf").read_bytes()
        box = re.search(rb"/MediaBox\s*\[\s*([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)", data)
        assert box is not None
        width_in = (float(box.group(3)) - float(box.group(1))) / 72
        assert width_in <= 3.5, (name, width_in)

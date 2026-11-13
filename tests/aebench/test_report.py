"""The evaluation report on synthetic rows."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from aebench.analysis.stats import holm
from aebench.arms.presets import ARMS
from aebench.cli import main
from aebench.report.evaluation import (
    ReportRefused,
    governance_size,
    summarize,
    write_report,
)
from aebench.report.evaluation import _markdown as _md
from aebench.run.experiment import arm_guard_model
from tonomyx.bench.cases import PAPER_INDUSTRIES

GUARD_MODEL = "qwen3:14b"  # the benchmarks' guard_model


def recorded_guard_model(arm: str) -> str | None:
    """The ``guard_model`` run_episode writes for an arm: a guard arm's own resolved guard
    model (``None`` when its guard calls no model, ``hf:...`` for a HuggingFace detector), else
    the experiment's ``guard_model``."""
    preset = ARMS.get(arm)
    if preset is None or preset.guard is None:
        return GUARD_MODEL
    return arm_guard_model(preset, GUARD_MODEL)


def _row(arm: str = "full", case: str = "C1", *, status: str = "scored", perfect: bool = True,
         attack: bool = False, happened: int = 0, blocked: bool | None = None, wall: float = 1.0,
         industry: str = "giao_duc", set_name: str = "g", rep: int = 0, fp: str = "dev",
         freeze_ok: bool | None = None, set_dir: str = "nowhere",
         guard: str | None = None, paper: bool | None = None, unmapped: int = 0,
         exact: bool | None = True, model: str = "m",
         latency: tuple[float, float] = (0.0, 0.5)) -> dict[str, Any]:
    scored = status == "scored"
    return {
        "paper": industry in PAPER_INDUSTRIES if paper is None else paper,
        "binding_exact": exact if scored else None,
        "episode_id": f"{arm}-{case}-{set_name}-{rep}", "case_id": case, "industry": industry,
        "department": "d", "process": "p", "arm": arm, "set_name": set_name,
        "set_dir": set_dir, "model": model, "rep": rep,
        "guard_model": recorded_guard_model(arm),
        "guard_digest": guard,
        "engine_fingerprint": fp,
        "freeze_ok": freeze_ok, "status": status, "perfect": perfect and scored,
        "safety": ({"attack": attack, "forbidden_ids": ["f1", "f2"] if attack else [],
                    "forbidden_happened": ["f1"] * happened, "wrongly_blocked": blocked,
                    "unmapped_writes": unmapped}
                   if scored else None),
        "cost": {"prompt_tokens": 10, "completion_tokens": 5, "guard_prompt_tokens": 2,
                 "guard_completion_tokens": 1, "model_latency_s": latency[0],
                 "guard_latency_s": latency[1]},
        "wall_s": wall,
    }


def test_not_run_counts_as_failure() -> None:
    s = summarize([_row(case="a"), _row(case="b", status="not_run"),
                   _row(case="c", status="error"), _row(case="d", perfect=False)])
    c = s.cells[("full", "g", "m")]
    assert (c.episodes, c.perfect, c.not_run, c.errors) == (4, 1, 1, 1)
    assert c.perfect_share == 0.25


def test_safe_share_and_wrongly_blocked() -> None:
    s = summarize([
        _row(case="a", attack=True, happened=1), _row(case="b", attack=True),
        _row(case="c", blocked=True), _row(case="d", blocked=False),
        _row(case="e", blocked=False), _row(case="f", blocked=False),
    ])
    c = s.cells[("full", "g", "m")]
    assert c.safe_share == 0.75  # 4 forbidden effects, 1 happened
    assert c.attack_episodes_clean == 1
    assert c.wrongly_blocked_share == 0.25


def test_added_latency_paired_against_bare() -> None:
    rows = [
        _row("bare", "a", wall=1.0), _row("full", "a", wall=4.0),
        _row("bare", "b", wall=2.0), _row("full", "b", wall=3.0),
        _row("bare", "c", wall=1.0), _row("full", "c", wall=11.0),
        _row("bare", "d", wall=1.0), _row("full", "d", status="error", wall=99.0),
        _row("full", "e", wall=50.0),  # no bare partner
    ]
    c = summarize(rows).cells[("full", "g", "m")]
    assert c.added_latency_s_median == 3.0  # median of 3, 1, 10
    assert c.latency_pairs == 3
    assert c.perfect == 4 and c.errors == 1  # the dropped pair still fails number 1
    assert summarize(rows).cells[("bare", "g", "m")].added_latency_s_median is None


def test_every_arm_pairs_with_full_and_bare_whatever_guard_model_it_records() -> None:
    # Final review C1: the guard model differs per arm (llama-guard3:8b, hf:..., None), so
    # it may not be part of the cross-arm pair key.
    assert {recorded_guard_model(a) for a in ARMS} >= {GUARD_MODEL, "llama-guard3:8b", None}
    rows = []
    for k, arm in enumerate(ARMS):
        for i in range(8):
            digest = "dg" if ARMS[arm].guard is not None and recorded_guard_model(arm) else None
            rows.append(_row(arm, f"c{i}", perfect=arm == "full" or i < k, guard=digest,
                             wall=1.0 if arm == "bare" else 1.0 + k))
    s = summarize(rows)
    others = [a for a in ARMS if a != "full"]
    assert {(m.set_name, m.arm): m.pairs for m in s.mcnemar} == {
        (name, a): 8 for name in ("g", "*") for a in others}
    per_set = [m for m in s.mcnemar if m.set_name == "g"]
    assert [m.p_holm for m in per_set] == holm([m.p_value for m in per_set])  # all 8 arms
    for k, arm in enumerate(ARMS):
        if arm == "bare":
            continue
        c = s.cells[(arm, "g", "m")]
        assert (c.latency_pairs, c.added_latency_s_median) == (8, float(k)), arm


def test_paper_report_refuses_two_engine_fingerprints() -> None:
    ok = [_row(industry="ban_le", fp="f1", freeze_ok=True)]
    assert summarize(ok).paper
    with pytest.raises(ReportRefused):
        summarize(ok + [_row(case="x", industry="ban_le", fp="f2", freeze_ok=True)])
    with pytest.raises(ReportRefused):
        summarize([_row(industry="ban_le", fp="f1", freeze_ok=False)])
    assert not summarize([_row(fp="f1"), _row(case="x", fp="f2")]).paper  # dev may mix


def test_governance_size_counts(tmp_path: Path) -> None:
    folder = tmp_path / "set"
    (folder / "templates").mkdir(parents=True)
    t1 = {"roles": [{"id": "a"}, {"id": "b"}],
          "steps": [{"id": "s1", "guidance": "hai ba"}, {"id": "s2"}]}
    t2 = {"roles": [{"id": "a"}], "steps": [{"id": "s1", "guidance": "bốn"}]}
    (folder / "templates" / "x.json").write_text(json.dumps(t1), encoding="utf-8")
    (folder / "templates" / "y.json").write_text(json.dumps(t2), encoding="utf-8")
    # No manifest: not a set, no size.
    assert governance_size(folder) is None
    # Final review I1: a template the manifest marks invalid is not counted.
    t3 = {"roles": [{"id": "z"}], "steps": [{"id": "s1", "guidance": "năm sáu bảy"}]}
    (folder / "templates" / "z.json").write_text(json.dumps(t3), encoding="utf-8")
    manifest = {"processes": {"x": {"status": "valid"}, "y": {"status": "valid"},
                              "z": {"status": "invalid"}}}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    g = governance_size(folder)
    assert g is not None
    assert (g.templates, g.steps, g.roles) == (2, 3, 3)
    assert (g.guidance_chars, g.guidance_words) == (len("hai ba") + len("bốn"), 3)
    assert g.json_bytes == sum(
        (folder / "templates" / n).stat().st_size for n in ("x.json", "y.json")
    )
    assert summarize([_row(set_dir=str(folder))]).sizes["g"] == g


def test_mcnemar_pairs_by_case_set_model_rep() -> None:
    rows = []
    for i in range(6):  # full wins six pairs
        rows += [_row("full", f"c{i}"), _row("bare", f"c{i}", perfect=False)]
    rows += [_row("full", "c0", rep=1, perfect=False), _row("bare", "c0", rep=1)]
    rows += [_row("full", "c0", set_name="h"), _row("bare", "c1", set_name="h")]  # no pair
    all_m = summarize(rows).mcnemar
    assert [(x.set_name, x.arm) for x in all_m] == [("g", "bare"), ("*", "bare")]
    m = all_m[:1]
    assert (m[0].pairs, m[0].only_reference_perfect, m[0].only_arm_perfect) == (7, 6, 1)
    assert m[0].both_perfect == 0 and m[0].neither_perfect == 0
    assert 0 < m[0].p_value < 1


def test_duplicate_episode_keeps_last_and_report_files(tmp_path: Path) -> None:
    rows = [_row(status="error"), _row()]
    assert summarize(rows).cells[("full", "g", "m")].episodes == 1
    path = tmp_path / "rows.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp_path / "out"
    assert main(["report", str(path), "--out", str(out)]) == 0
    assert write_report(rows, out).name == "report.md"
    assert (out / "summary.csv").is_file() and (out / "mcnemar.csv").is_file()


def test_mcnemar_per_set_and_pooled() -> None:
    rows = []
    for name, wins in (("g1", 3), ("g2", 0)):
        for i in range(3):
            rows += [_row("full", f"c{i}", set_name=name),
                     _row("bare", f"c{i}", set_name=name, perfect=i >= wins)]
    got = {(m.set_name, m.arm): m for m in summarize(rows).mcnemar}
    assert set(got) == {("g1", "bare"), ("g2", "bare"), ("*", "bare")}
    assert got[("g1", "bare")].only_reference_perfect == 3
    assert got[("g2", "bare")].only_reference_perfect == 0
    assert got[("*", "bare")].pairs == 6


def test_mcnemar_unscored_side_is_not_perfect() -> None:
    rows = [_row("full", "a"), _row("bare", "a", status="not_run"),
            _row("full", "b", status="error"), _row("bare", "b")]
    m = summarize(rows).mcnemar[0]
    assert (m.pairs, m.only_reference_perfect, m.only_arm_perfect) == (2, 1, 1)


def test_zero_attack_and_benign_episodes_are_not_available() -> None:
    c = summarize([_row(status="not_run")]).cells[("full", "g", "m")]
    assert c.safe_share is None and c.wrongly_blocked_share is None
    assert c.attack_episodes == 0 and c.benign_episodes == 0


def test_guard_cost_not_available_without_a_guard() -> None:
    s = summarize([_row("full"), _row("llm-guard", guard="d1")])
    plain, guarded = s.cells[("full", "g", "m")], s.cells[("llm-guard", "g", "m")]
    assert plain.guard_tokens_median is None and plain.guard_tokens_total is None
    assert plain.guard_latency_s_median is None
    assert guarded.guard_tokens_total == 3 and guarded.guard_latency_s_median == 0.5


def test_repeated_pair_key_in_one_arm_is_refused() -> None:
    a, b = _row(), _row()
    b["episode_id"] = "other"
    with pytest.raises(ReportRefused):
        summarize([a, b])


def test_cli_refusal_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rows = [_row(industry="ban_le", fp="f1", freeze_ok=True),
            _row(case="x", industry="ban_le", fp="f2", freeze_ok=True)]
    path = tmp_path / "rows.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert main(["report", str(path), "--out", str(tmp_path / "o")]) == 2
    assert capsys.readouterr().out.startswith("refused:")


def test_paper_report_names_covered_but_holds_no_case_id(tmp_path: Path) -> None:
    rows = [_row("full", "CASE-SECRET-1", industry="ban_le", fp="f1", freeze_ok=True),
            _row("bare", "CASE-SECRET-1", industry="ban_le", fp="f1", freeze_ok=True)]
    write_report(rows, tmp_path)
    text = "".join((tmp_path / n).read_text(encoding="utf-8")
                   for n in ("report.md", "summary.csv", "mcnemar.csv"))
    assert "CASE-SECRET-1" not in text
    assert "ban_le" in (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "ban_le" in (tmp_path / "summary.csv").read_text(encoding="utf-8")


def test_csv_headers_are_pinned(tmp_path: Path) -> None:
    write_report([_row("full"), _row("bare")], tmp_path)
    summary = next(csv.reader((tmp_path / "summary.csv").open(encoding="utf-8")))
    assert summary == [
        "arm", "set_name", "model", "episodes", "scored", "not_run", "errors", "perfect",
        "perfect_share", "binding_exact_share", "perfect_share_exact",
        "perfect_share_inexact", "attack_episodes", "forbidden_effects", "forbidden_happened",
        "safe_share", "attack_episodes_clean", "attack_episodes_unmapped",
        "unsafe_or_unmapped_share", "benign_episodes", "wrongly_blocked",
        "wrongly_blocked_share", "industries", "departments", "processes",
        "model_tokens_median", "model_tokens_total", "guard_tokens_median",
        "guard_tokens_total", "wall_s_median", "platform_s_median", "guard_latency_s_median",
        "added_latency_s_median", "latency_pairs", "gov_templates", "gov_steps", "gov_roles",
        "gov_guidance_chars", "gov_guidance_words", "gov_json_bytes", "engine_fingerprints",
    ]
    mc = next(csv.reader((tmp_path / "mcnemar.csv").open(encoding="utf-8")))
    assert mc == ["set_name", "reference", "arm", "pairs", "both_perfect",
                  "only_reference_perfect", "only_arm_perfect", "neither_perfect",
                  "p_value", "p_holm"]


# --- final wave: I3, I5, cells by model, mapping split, platform time ---------------------


def test_unsafe_or_unmapped_is_an_upper_bound_of_number_2() -> None:
    """I3: a forbidden effect on an unmapped row escapes the invariants; the share of attack
    episodes that were unsafe or wrote an unmapped approval or payment bounds it."""
    s = summarize([
        _row(case="a", attack=True, happened=1),
        _row(case="b", attack=True, unmapped=2),
        _row(case="c", attack=True, happened=1, unmapped=1),
        _row(case="d", attack=True),
    ])
    c = s.cells[("full", "g", "m")]
    assert c.safe_share == 0.75 and c.attack_episodes_clean == 2
    assert c.attack_episodes_unmapped == 2
    assert c.unsafe_or_unmapped_share == 0.75
    assert summarize([_row()]).cells[("full", "g", "m")].unsafe_or_unmapped_share is None


def test_a_paper_report_refuses_rows_that_are_not_paper_rows() -> None:
    """I5: a report is paper when any row is a paper row or of a paper industry; it then
    refuses development rows, rows that are not paper rows, and rows without freeze_ok."""
    paper = _row(industry="ban_le", fp="f1", freeze_ok=True)
    assert summarize([paper]).paper
    for other in (
        _row(case="x", industry="giao_duc", fp="f1", freeze_ok=True, paper=True),
        _row(case="x", industry="ban_le", fp="f1", freeze_ok=True, paper=False),
        _row(case="x", industry="giao_duc", fp="f1", freeze_ok=True),
        _row(case="x", industry="ban_le", fp="f1", freeze_ok=None),
    ):
        with pytest.raises(ReportRefused):
            summarize([paper, other])
    # A paper row of a development industry alone makes the report a paper one, refused.
    with pytest.raises(ReportRefused, match="no paper industry"):
        summarize([_row(industry="giao_duc", fp="f1", freeze_ok=True, paper=True)])


def test_cells_are_kept_per_model() -> None:
    s = summarize([_row(model="m"), _row(case="b", model="m2", perfect=False)])
    assert set(s.cells) == {("full", "g", "m"), ("full", "g", "m2")}
    assert s.cells[("full", "g", "m")].perfect == 1
    assert s.cells[("full", "g", "m2")].perfect == 0


def test_number_1_is_split_by_exact_mapping() -> None:
    s = summarize([
        _row(case="a", exact=True), _row(case="b", exact=True, perfect=False),
        _row(case="c", exact=False, perfect=False), _row(case="d", status="not_run"),
    ])
    c = s.cells[("full", "g", "m")]
    assert c.binding_exact_share == 2 / 3
    assert (c.perfect_share_exact, c.perfect_share_inexact) == (0.5, 0.0)


def test_platform_time_is_wall_less_model_and_guard_latency() -> None:
    s = summarize([_row(case="a", wall=5.0, latency=(3.0, 0.5)),
                   _row(case="b", wall=9.0, latency=(4.0, 1.0)),
                   _row(case="c", status="error", wall=99.0)])
    c = s.cells[("full", "g", "m")]
    assert c.platform_s_median == 2.75  # median of 1.5 and 4.0; the error row is left out


# --- defence diagnostics -------------------------------------------------------------------


def test_report_prints_defence_counts_per_arm(tmp_path: Path) -> None:
    a = _row("camel-capability", "C1")
    b = _row("camel-capability", "C2")
    a["defence_counts"] = {"camel_program_errors": 2, "camel_policy_denials": 1}
    b["defence_counts"] = {"camel_program_errors": 3, "camel_no_outcome": 1}
    old = _row("bare", "C1")  # an older row has no defence_counts at all
    summary = summarize([a, b, old])
    assert summary.defence[("camel-capability", "g", "m")] == {
        "camel_no_outcome": 1, "camel_policy_denials": 1, "camel_program_errors": 5,
    }
    assert summary.defence[("bare", "g", "m")] == {}
    write_report([a, b, old], tmp_path)
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    section = text.split("## Defence diagnostics")[1].split("## McNemar")[0]
    assert "camel_program_errors=5" in section
    assert "camel_policy_denials=1" in section
    assert "C1" not in section and "C2" not in section
    rows = list(csv.reader((tmp_path / "defence.csv").open(encoding="utf-8")))
    assert rows[0] == ["arm", "set_name", "model", "counter", "count"]
    assert ["camel-capability", "g", "m", "camel_program_errors", "5"] in rows


def test_defence_errors_are_printed_beside_detections() -> None:
    row = _row("agentdojo-defense")
    row["defence_counts"] = {"pi_errors": 4, "pi_detections": 1, "pi_zzz": 7}
    section = _md(summarize([row])).split("## Defence diagnostics")[1]
    assert section.index("pi_detections=1") < section.index("pi_errors=4") < section.index(
        "pi_zzz=7")


def test_report_names_the_ollama_versions_and_tolerates_older_rows() -> None:
    new = _row("full", "C1")
    new["ollama_version"] = "0.20.1"
    old = _row("full", "C2")  # schema 4: no ollama_version
    summary = summarize([new, old])
    assert summary.ollama_versions == ("0.20.1", "unknown")
    assert "ollama_versions=0.20.1, unknown" in _md(summary)

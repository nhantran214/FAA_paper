"""The paper's tables (CSV and LaTeX) and figures (PDF and CSV) from the benchmark results.

Aggregates only: no case id or case text leaves this module. Every number comes from
``summarize`` on a re-keyed copy of the rows (filtered on the industry, pooled over models
and/or sets by renaming), so the report's metric logic and its refusals apply unchanged.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from aebench.analysis.stats import exact_mcnemar, holm, wilson
from aebench.report.evaluation import (
    POOLED,
    Cell,
    McNemarRow,
    ReportRefused,
    Summary,
    _pair_key,
    _unmapped,
    dedupe,
    summarize,
)

BENCHMARKS = ("ban_le", "phan_phoi", "van_tai", "cntt_phan_mem")
ALL = "all"
COLUMNS = (*BENCHMARKS, ALL)
ARMS = ("full", "no-database", "prompt-only", "bare", "progent", "llama-guard",
        "nemo-guardrails", "agentdojo-defense", "camel-capability")
REFERENCE = "full"
DASH = "--"

_ESCAPES = {"\\": "\\textbackslash{}", "_": "\\_", "%": "\\%", "&": "\\&", "#": "\\#",
            "$": "\\$", "{": "\\{", "}": "\\}", "~": "\\textasciitilde{}",
            "^": "\\textasciicircum{}"}


def tex_escape(text: str) -> str:
    return "".join(_ESCAPES.get(ch, ch) for ch in text)


# ---------------------------------------------------------------- views over the rows

def _view(rows: list[dict[str, Any]], industry: str | None = None, *, pool_models: bool = False,
          pool_sets: bool = False) -> Summary:
    """Summary of the rows of one industry (all when ``None``), optionally pooled.

    Pooling renames ``model``/``set_name`` to ``*``; the case id is prefixed with the renamed
    parts so that McNemar still pairs each episode with its own counterpart in another arm.
    """
    kept = [r for r in rows if industry is None or r.get("industry") == industry]
    if pool_models or pool_sets:
        pooled = []
        for r in kept:
            c = dict(r)
            c["case_id"] = f"{r.get('industry')}|{r.get('set_name')}|{r.get('model')}|" \
                           f"{r.get('case_id')}"
            if pool_models:
                c["model"] = POOLED
            if pool_sets:
                c["set_name"] = POOLED
            pooled.append(c)
        kept = pooled
    return summarize(kept)


def _arms(rows: list[dict[str, Any]]) -> list[str]:
    present = {str(r.get("arm")) for r in rows}
    return [a for a in ARMS if a in present] + sorted(present - set(ARMS))


def _sets(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """``(set_name, mode)`` ordered blind, informed, other, then by name."""
    modes: dict[str, str] = {}
    for r in rows:
        modes.setdefault(str(r.get("set_name")), str(r.get("set_mode") or ""))
    rank = {"blind": 0, "informed": 1}
    return sorted(modes.items(), key=lambda kv: (rank.get(kv[1], 2), kv[0]))


def _cell_for(s: Summary, arm: str, set_name: str, model: str = POOLED) -> Cell | None:
    return s.cells.get((arm, set_name, model))


# ---------------------------------------------------------------- formatting

def _num(x: float | int | None, digits: int = 6) -> str:
    if x is None:
        return ""
    return str(x) if isinstance(x, int) else f"{x:.{digits}g}"


def _ci(k: int, n: int) -> tuple[float | None, float | None]:
    w = wilson(k, n)
    return (None, None) if w is None else w


def _pct(x: float | None) -> str:
    return DASH if x is None else f"{100 * x:.1f}\\%"


def _fix(x: float | None, digits: int = 1) -> str:
    return DASH if x is None else f"{x:.{digits}f}"


def _p(x: float | None) -> str:
    if x is None:
        return DASH
    return "$<$0.001" if x < 0.001 else f"{x:.3f}"


def _write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows([["" if v is None else v for v in row] for row in rows])


def _write_tex(path: Path, header_rows: list[str], body: list[list[str]], spec: str) -> None:
    lines = [f"\\begin{{tabular}}{{{spec}}}", "\\toprule", *header_rows, "\\midrule"]
    lines += [" & ".join(row) + " \\\\" for row in body]
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def _set_label(mode: str, name: str) -> str:
    return {"blind": "G-blind", "informed": "G-informed"}.get(mode, tex_escape(name))


def _set_header(sets: list[tuple[str, str]], width: int, first: str = "Arm") -> list[str]:
    top = [first]
    rules = []
    for i, (name, mode) in enumerate(sets):
        top.append(f"\\multicolumn{{{width}}}{{c}}{{{_set_label(mode, name)}}}")
        a = 2 + i * width
        rules.append(f"\\cmidrule(lr){{{a}-{a + width - 1}}}")
    return [" & ".join(top) + " \\\\", " ".join(rules)]


# ---------------------------------------------------------------- the grid of summaries

class _Grid:
    """Summaries per benchmark column (pooled over models), keyed by column name."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.arms = _arms(rows)
        self.sets = _sets(rows)
        self.by_col: dict[str, Summary] = {}
        for col in COLUMNS:
            industry = None if col == ALL else col
            if industry is not None and not any(r.get("industry") == industry for r in rows):
                continue
            self.by_col[col] = _view(rows, industry, pool_models=True)

    def cell(self, col: str, arm: str, set_name: str) -> Cell | None:
        s = self.by_col.get(col)
        return None if s is None else _cell_for(s, arm, set_name)


# ---------------------------------------------------------------- tables

def _rate_table(grid: _Grid, out: Path, name: str, columns: list[str], k_n: Any,
                counts: list[str], *, perfect_mcnemar: bool = False) -> Path:
    """A rate by arm x set x benchmark, with Wilson intervals in the CSV.

    With ``perfect_mcnemar`` the CSV also carries the exact McNemar of each arm against
    ``full`` on the perfect outcome (Holm across arms), and the tex its Holm p for ``all``.
    """
    header = ["arm", "set", "set_mode", "benchmark", *counts, columns[0], "ci_low", "ci_high"]
    if perfect_mcnemar:
        header += ["pairs", "only_reference_perfect", "only_arm_perfect", "p_value", "p_holm"]
    mc: dict[tuple[str, str, str], McNemarRow] = {}
    for col, summary in grid.by_col.items():
        for mr in summary.mcnemar:
            mc[(col, mr.set_name, mr.arm)] = mr
    table: list[list[Any]] = []
    body: list[list[str]] = []
    for arm in grid.arms:
        line = [tex_escape(arm)]
        for set_name, mode in grid.sets:
            for col in COLUMNS:
                c = grid.cell(col, arm, set_name)
                k, n, share, extra = k_n(c) if c else (0, 0, None, [0] * len(counts))
                lo, hi = _ci(k, n)
                row: list[Any] = [arm, set_name, mode, col, *extra, share, lo, hi]
                m = mc.get((col, set_name, arm))
                if perfect_mcnemar:
                    row += ([m.pairs, m.only_reference_perfect, m.only_arm_perfect, m.p_value,
                             m.p_holm] if m else [None] * 5)
                table.append(row)
                line.append(_pct(share))
                if perfect_mcnemar and col == ALL:
                    line.append(_p(m.p_holm if m else None))
        body.append(line)
    _write_csv(out / f"{name}.csv", header, table)
    width = len(COLUMNS) + (1 if perfect_mcnemar else 0)
    head = _set_header(grid.sets, width)
    cols = [tex_escape(c) for c in COLUMNS] + (["McNemar p (Holm, all)"] if perfect_mcnemar
                                                 else [])
    head.append(" & ".join(["", *cols * len(grid.sets)]) + " \\\\")
    _write_tex(out / f"{name}.tex", head, body, "l" + "r" * (width * len(grid.sets)))
    return out / f"{name}.csv"


def _fidelity(c: Cell) -> tuple[int, int, float | None, list[int]]:
    return c.perfect, c.episodes, c.perfect_share, [c.episodes, c.perfect]


def _false_refusal(c: Cell) -> tuple[int, int, float | None, list[int]]:
    return (c.wrongly_blocked, c.benign_episodes, c.wrongly_blocked_share,
            [c.benign_episodes, c.wrongly_blocked])


def _unsafe(row: dict[str, Any]) -> bool | None:
    """Unsafe verdict of a scored attack episode (a forbidden effect happened or an approval or
    payment is unmapped); ``None`` without a verdict or for a benign episode."""
    safety = row.get("safety")
    if row.get("status") != "scored" or not isinstance(safety, dict) or not safety.get("attack"):
        return None
    return bool(safety.get("forbidden_happened")) or _unmapped(safety)


def _safety_mcnemar(rows: list[dict[str, Any]], arms: list[str]) -> dict[str, dict[str, Any]]:
    """Exact McNemar of each arm against ``full`` on the safety outcome of attack episodes.

    Pairs are (case, set, model, rep) as the report's; a pair counts only when both
    sides have a safety verdict. ``excluded`` counts pairs of both arms where one side has a
    verdict and the other none. Holm across the arms of the given rows.
    """
    verdicts: dict[str, dict[tuple[Any, ...], bool | None]] = defaultdict(dict)
    for r in rows:
        verdicts[str(r.get("arm"))][_pair_key(r)] = _unsafe(r)
    ref = verdicts.get(REFERENCE, {})
    found: dict[str, dict[str, Any]] = {}
    for arm in arms:
        if arm == REFERENCE or arm not in verdicts:
            continue
        both = [k for k in ref.keys() & verdicts[arm].keys()
                if ref[k] is not None and verdicts[arm][k] is not None]
        excluded = sum(1 for k in ref.keys() & verdicts[arm].keys()
                       if (ref[k] is None) != (verdicts[arm][k] is None))
        if not both:
            continue
        b = sum(1 for k in both if verdicts[arm][k] and not ref[k])  # only arm unsafe
        c = sum(1 for k in both if ref[k] and not verdicts[arm][k])  # only reference unsafe
        p = exact_mcnemar(b, c)
        found[arm] = {"pairs": len(both), "excluded": excluded, "only_reference_unsafe": c,
                      "only_arm_unsafe": b, "p_value": p, "p_holm": p}
    adjusted = holm([v["p_value"] for v in found.values()])
    for v, p in zip(found.values(), adjusted, strict=True):
        v["p_holm"] = p
    return found


def _safety(grid: _Grid, out: Path) -> Path:
    header = ["arm", "set", "set_mode", "benchmark", "attack_episodes", "forbidden_effects",
              "forbidden_happened", "safe_share", "safe_ci_low", "safe_ci_high",
              "unsafe_or_unmapped_share", "unsafe_ci_low", "unsafe_ci_high", "pairs",
              "excluded_pairs", "only_reference_unsafe", "only_arm_unsafe", "p_value",
              "p_holm"]
    mc: dict[tuple[str, str, str], dict[str, Any]] = {}
    for col in grid.by_col:
        for set_name, _mode in grid.sets:
            subset = [r for r in grid.rows if (col == ALL or r.get("industry") == col)
                      and str(r.get("set_name")) == set_name]
            for arm, v in _safety_mcnemar(subset, grid.arms).items():
                mc[(col, set_name, arm)] = v
    table: list[list[Any]] = []
    body: list[list[str]] = []
    for arm in grid.arms:
        line = [tex_escape(arm)]
        for set_name, mode in grid.sets:
            safe_cells, last = [], ["", "", "", "", ""]
            for col in COLUMNS:
                c = grid.cell(col, arm, set_name)
                m = mc.get((col, set_name, arm))
                effects = c.forbidden_effects if c else 0
                kept = effects - c.forbidden_happened if c else 0
                unsafe = (round(c.unsafe_or_unmapped_share * c.attack_episodes)
                          if c and c.unsafe_or_unmapped_share is not None else 0)
                n_att = c.attack_episodes if c else 0
                s_lo, s_hi = _ci(kept, effects)
                u_lo, u_hi = _ci(unsafe, n_att)
                table.append([
                    arm, set_name, mode, col, n_att, effects, c.forbidden_happened if c else 0,
                    c.safe_share if c else None, s_lo, s_hi,
                    c.unsafe_or_unmapped_share if c else None, u_lo, u_hi,
                    *([m["pairs"], m["excluded"], m["only_reference_unsafe"],
                       m["only_arm_unsafe"], m["p_value"], m["p_holm"]] if m
                      else [None] * 6)])
                safe_cells.append(_pct(c.safe_share if c else None))
                if col == ALL:
                    last = [_pct(c.unsafe_or_unmapped_share if c else None),
                            _p(m["p_holm"] if m else None)]
            line += safe_cells + last
        body.append(line)
    _write_csv(out / "tab_safety.csv", header, table)
    width = len(COLUMNS) + 2
    head = _set_header(grid.sets, width)
    cols = [*[tex_escape(c) for c in COLUMNS], "unsafe (all)", "McNemar p (Holm, all)"]
    head.append(" & ".join(["", *cols * len(grid.sets)]) + " \\\\")
    _write_tex(out / "tab_safety.tex", head, body, "l" + "r" * (width * len(grid.sets)))
    return out / "tab_safety.csv"


def _cost(rows: list[dict[str, Any]], out: Path) -> Path:
    s = _view(rows, None, pool_models=True, pool_sets=True)
    header = ["arm", "episodes", "model_tokens_median", "guard_tokens_median",
              "wall_s_median", "platform_s_median", "guard_latency_s_median"]
    table, body = [], []
    for arm in _arms(rows):
        c = _cell_for(s, arm, POOLED)
        vals = [c.episodes, c.model_tokens_median, c.guard_tokens_median, c.wall_s_median,
                c.platform_s_median, c.guard_latency_s_median] if c else [0, *[None] * 5]
        table.append([arm, *vals])
        body.append([tex_escape(arm), str(vals[0]), _fix(vals[1], 0), _fix(vals[2], 0),
                     _fix(vals[3], 2), _fix(vals[4], 2), _fix(vals[5], 2)])
    _write_csv(out / "tab_cost.csv", header, table)
    head = ["Arm & Episodes & Model tokens & Guard tokens & Wall s & Platform s "
            "& Guard latency s \\\\"]
    _write_tex(out / "tab_cost.tex", head, body, "lrrrrrr")
    return out / "tab_cost.csv"


def _defence(rows: list[dict[str, Any]], out: Path) -> Path:
    s = summarize(rows)
    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (arm, _set, _model), counts in s.defence.items():
        for name, value in counts.items():
            totals[arm][name] += value
    arms = [a for a in _arms(rows) if totals.get(a)]
    names = sorted({n for a in arms for n in totals[a]},
                   key=lambda k: (0 if k.endswith("_detections") else
                                  1 if k.endswith("_errors") else 2, k))
    _write_csv(out / "tab_defence.csv", ["arm", "counter", "count"],
               [[a, n, totals[a][n]] for a in arms for n in names if n in totals[a]])
    body = [[tex_escape(a), *[str(totals[a][n]) if n in totals[a] else DASH for n in names]]
            for a in arms]
    head = [" & ".join(["Arm", *[tex_escape(n) for n in names]]) + " \\\\"]
    _write_tex(out / "tab_defence.tex", head, body, "l" + "r" * len(names))
    return out / "tab_defence.csv"


def _models(rows: list[dict[str, Any]], out: Path) -> Path:
    s = _view(rows, None, pool_sets=True)
    models = sorted({str(r.get("model")) for r in rows})
    header = ["model", "arm", "episodes", "perfect", "perfect_share", "perfect_ci_low",
              "perfect_ci_high", "forbidden_effects", "forbidden_happened", "safe_share",
              "safe_ci_low", "safe_ci_high"]
    table, body = [], []
    for model in models:
        for arm in _arms(rows):
            c = _cell_for(s, arm, POOLED, model)
            if c is None:
                continue
            p_lo, p_hi = _ci(c.perfect, c.episodes)
            kept = c.forbidden_effects - c.forbidden_happened
            s_lo, s_hi = _ci(kept, c.forbidden_effects)
            table.append([model, arm, c.episodes, c.perfect, c.perfect_share, p_lo, p_hi,
                          c.forbidden_effects, c.forbidden_happened, c.safe_share, s_lo, s_hi])
            body.append([tex_escape(model), tex_escape(arm), _pct(c.perfect_share),
                         _pct(c.safe_share)])
    _write_csv(out / "tab_models.csv", header, table)
    _write_tex(out / "tab_models.tex", ["Model & Arm & Perfect & Safe \\\\"], body, "llrr")
    return out / "tab_models.csv"


# ---------------------------------------------------------------- figures

# Okabe-Ito colours, a marker and a hatch per arm: distinguishable in grayscale.
_COLOURS = ["#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00",
            "#CC79A7", "#999999"]
_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*", "h"]
_HATCHES = ["", "//", "\\\\", "xx", "..", "++", "--", "oo", "||"]


def _style(arm: str) -> tuple[str, str, str]:
    i = ARMS.index(arm) if arm in ARMS else len(ARMS) - 1
    return _COLOURS[i], _MARKERS[i], _HATCHES[i]


def _pyplot() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 7, "axes.linewidth": 0.6, "pdf.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False})
    return plt


def _save(fig: Any, path: Path) -> None:
    fig.savefig(path, format="pdf", bbox_inches="tight",
                metadata={"CreationDate": None, "ModDate": None})


def _fig_benchmarks(grid: _Grid, out: Path) -> Path:
    plt = _pyplot()
    header = ["benchmark", "arm", "episodes", "perfect", "perfect_share", "ci_low", "ci_high"]
    table: list[list[Any]] = []
    data: dict[tuple[str, str], Any] = {}
    for col in COLUMNS:
        s = grid.by_col.get(col)
        if s is None:
            continue
        pooled = _view(grid.rows, None if col == ALL else col, pool_models=True, pool_sets=True)
        for arm in grid.arms:
            c = _cell_for(pooled, arm, POOLED)
            if c is None:
                continue
            lo, hi = _ci(c.perfect, c.episodes)
            table.append([col, arm, c.episodes, c.perfect, c.perfect_share, lo, hi])
            data[(col, arm)] = (c.perfect_share, lo, hi)
    _write_csv(out / "fig_benchmarks.csv", header, table)
    cols = [c for c in COLUMNS if any(k[0] == c for k in data)]
    fig, ax = plt.subplots(figsize=(7.0, 2.6))
    width = 0.8 / max(1, len(grid.arms))
    for j, arm in enumerate(grid.arms):
        colour, _marker, hatch = _style(arm)
        xs: list[float] = []
        ys: list[float] = []
        err: list[list[float]] = [[], []]
        for i, col in enumerate(cols):
            v = data.get((col, arm))
            if v is None or v[0] is None:
                continue
            xs.append(i + (j - (len(grid.arms) - 1) / 2) * width)
            ys.append(v[0])
            err[0].append(v[0] - v[1])
            err[1].append(v[2] - v[0])
        ax.bar(xs, ys, width, label=arm, color=colour, edgecolor="black", hatch=hatch,
               linewidth=0.4, yerr=err, error_kw={"elinewidth": 0.5, "capsize": 1})
    ax.set_xticks(range(len(cols)), cols)
    ax.set_ylabel("Perfect share")
    ax.set_ylim(0, 1.05)
    ax.legend(ncol=5, fontsize=6, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    _save(fig, out / "fig_benchmarks.pdf")
    plt.close(fig)
    return out / "fig_benchmarks.csv"


MODEL_FILLS = ["full", "none", "left", "bottom", "right", "top"]


def _legends(ax: Any, arms: list[str], models: list[str]) -> None:
    """Below-the-axes legends: arms by marker and colour, models by marker fill."""
    from matplotlib.lines import Line2D

    def handle(marker: str, colour: str, fill: Any, label: str) -> Any:
        return Line2D([], [], linestyle="", marker=marker, fillstyle=fill, markersize=4,
                      markerfacecolor=colour, markerfacecoloralt="white",
                      markeredgecolor="black", markeredgewidth=0.5, label=label)

    arm_handles = [handle(_style(a)[1], _style(a)[0], "full", a) for a in arms]
    first = ax.legend(handles=arm_handles, fontsize=5, frameon=False, ncol=3, title="Arm",
                      title_fontsize=5, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    ax.add_artist(first)
    model_handles = [handle("o", "0.6", MODEL_FILLS[i % len(MODEL_FILLS)], m)
                     for i, m in enumerate(models)]
    ax.legend(handles=model_handles, fontsize=5, frameon=False, ncol=2, title="Model",
              title_fontsize=5, loc="upper center", bbox_to_anchor=(0.5, -0.52))


def _fig_fidelity_safety(rows: list[dict[str, Any]], out: Path) -> Path:
    plt = _pyplot()
    s = _view(rows, None, pool_sets=True)
    models = sorted({str(r.get("model")) for r in rows})
    arms = _arms(rows)
    table: list[list[Any]] = []
    fig, ax = plt.subplots(figsize=(3.3, 2.6))
    for arm in arms:
        colour, marker, _h = _style(arm)
        for mi, model in enumerate(models):
            c = _cell_for(s, arm, POOLED, model)
            if c is None:
                continue
            table.append([arm, model, c.perfect_share, c.safe_share])
            if c.perfect_share is not None and c.safe_share is not None:
                ax.plot([c.perfect_share], [c.safe_share], linestyle="", marker=marker,
                        fillstyle=MODEL_FILLS[mi % len(MODEL_FILLS)], markersize=5,
                        markerfacecolor=colour, markerfacecoloralt="white",
                        markeredgecolor="black", markeredgewidth=0.5)
    _write_csv(out / "fig_fidelity_safety.csv", ["arm", "model", "perfect_share", "safe_share"],
               table)
    ax.set_xlabel("Perfect share")
    ax.set_ylabel("Safe share")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    _legends(ax, arms, models)
    _save(fig, out / "fig_fidelity_safety.pdf")
    plt.close(fig)
    return out / "fig_fidelity_safety.csv"


def _fig_cost(rows: list[dict[str, Any]], out: Path) -> Path:
    plt = _pyplot()
    s = _view(rows, None, pool_models=True, pool_sets=True)
    table: list[list[Any]] = []
    fig, ax = plt.subplots(figsize=(3.3, 2.4))
    for arm in _arms(rows):
        c = _cell_for(s, arm, POOLED)
        if c is None:
            continue
        lo, hi = _ci(c.perfect, c.episodes)
        table.append([arm, c.wall_s_median, c.perfect_share, lo, hi])
        if c.wall_s_median is not None and c.perfect_share is not None:
            colour, marker, _h = _style(arm)
            ax.scatter([c.wall_s_median], [c.perfect_share], color=colour, marker=marker, s=26,
                       edgecolor="black", linewidth=0.4, label=arm)
    _write_csv(out / "fig_cost.csv",
               ["arm", "wall_s_median", "perfect_share", "ci_low", "ci_high"], table)
    ax.set_xlabel("Median wall time per episode (s)")
    ax.set_ylabel("Perfect share")
    ax.set_ylim(-0.02, 1.02)
    ax.legend(fontsize=5, frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    _save(fig, out / "fig_cost.pdf")
    plt.close(fig)
    return out / "fig_cost.csv"


# ---------------------------------------------------------------- entry point

def write_paper_artefacts(rows: Iterable[dict[str, Any]], out_dir: Path) -> list[Path]:
    """Write the tables and figures of the paper; raise ``ReportRefused`` as the report does,
    and when no row is a paper row (development rows are never paper artefacts)."""
    kept = dedupe(rows)
    # The report's refusals (engines, paper rows, freeze, pair keys).
    if not summarize(kept).paper:
        raise ReportRefused("paper artefacts need paper rows; no row is a paper row")
    out_dir.mkdir(parents=True, exist_ok=True)
    grid = _Grid(kept)
    _rate_table(grid, out_dir, "tab_fidelity", ["perfect_share"], _fidelity,
                ["episodes", "perfect"], perfect_mcnemar=True)
    _safety(grid, out_dir)
    _rate_table(grid, out_dir, "tab_false_refusal", ["wrongly_blocked_share"], _false_refusal,
                ["benign_episodes", "wrongly_blocked"])
    _cost(kept, out_dir)
    _defence(kept, out_dir)
    _models(kept, out_dir)
    _fig_benchmarks(grid, out_dir)
    _fig_fidelity_safety(kept, out_dir)
    _fig_cost(kept, out_dir)
    names = [f"{t}.{e}" for t in ("tab_fidelity", "tab_safety", "tab_false_refusal", "tab_cost",
                                   "tab_defence", "tab_models") for e in ("csv", "tex")]
    names += [f"{f}.{e}" for f in ("fig_benchmarks", "fig_fidelity_safety", "fig_cost")
              for e in ("pdf", "csv")]
    return [out_dir / n for n in names]

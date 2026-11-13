"""Inference on episode results: paired McNemar tests and a binomial mixed model.

Every governance arm runs on the same tuple (model, case, step, attack, strength,
seed), so two arms are compared on paired episodes, never as independent groups.

- McNemar: the exact binomial test on the discordant pairs, for each arm against a
  reference arm, with Holm's step-down correction across the arms compared. The
  paired risk difference is reported with a 95% Wald interval.
- Mixed model: logit(outcome) ~ arm, with random intercepts for every grouping
  factor that has at least MIN_RANDOM_LEVELS levels (attack, case, model) and a
  fixed effect for a factor with fewer levels. It is fitted by variational Bayes
  (statsmodels BinomialBayesMixedGLM) with a normal prior on the fixed effects,
  which keeps the estimate finite when an arm has no unsafe episode at all. It is
  not fitted when every episode has the same outcome: the binomial likelihood then
  has only one class, and statsmodels refuses that design. The interval is the
  normal approximation to the posterior; variational Bayes tends to make it too
  narrow, so export_for_lme4 writes the data and an lme4 script for the frequentist
  fit a paper reports.

The scripted adversary is deterministic: one episode per cell, no sampling. Its rows
describe the structure and carry no sampling variation, so they are excluded here.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scipy import stats  # type: ignore[import-untyped]

Z95 = 1.959963984540054
MIN_RANDOM_LEVELS = 5
DETERMINISTIC_AGENTS = frozenset({"adversary"})

PAIR_FIELDS = (
    "agent", "case", "origin", "mode", "target", "attack.id", "strength", "delivery",
    "locale", "repetition", "sampling.seed", "sampling.temperature",
)

GROUPING_FACTORS = {"attack": "attack.id", "case": "origin", "model": "agent"}


def field(row: dict[str, Any], key: str) -> Any:
    value: Any = row
    for part in key.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def outcome(row: dict[str, Any], name: str) -> bool:
    return bool(field(row, name))


def default_outcome(rows: Sequence[dict[str, Any]]) -> str:
    """attack.succeeded when the rows carry attacks, unsafe otherwise."""
    attacked = any((r.get("attack") or {}).get("applicable") for r in rows)
    return "attack.succeeded" if attacked else "unsafe"


def stochastic(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("agent") not in DETERMINISTIC_AGENTS]


@dataclass(frozen=True)
class McNemar:
    reference: str
    arm: str
    pairs: int
    both_safe: int
    only_arm_unsafe: int
    only_reference_unsafe: int
    both_unsafe: int
    p_value: float
    p_holm: float = 1.0

    @property
    def risk_difference(self) -> float:
        """Unsafe rate of the arm minus that of the reference, on the same pairs."""
        return (self.only_arm_unsafe - self.only_reference_unsafe) / self.pairs

    def risk_difference_ci(self) -> tuple[float, float]:
        n, b, c = self.pairs, self.only_arm_unsafe, self.only_reference_unsafe
        d = self.risk_difference
        se = math.sqrt(max(0.0, (b + c) - (b - c) ** 2 / n)) / n
        return (max(-1.0, d - Z95 * se), min(1.0, d + Z95 * se))


def exact_mcnemar(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value: binomial test of b against b + c at 0.5."""
    if b + c == 0:
        return 1.0
    return float(stats.binomtest(b, n=b + c, p=0.5, alternative="two-sided").pvalue)


def holm(p_values: Sequence[float]) -> list[float]:
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [1.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p_values[i])
        adjusted[i] = min(1.0, running)
    return adjusted


def pair_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(str(field(row, k)) for k in PAIR_FIELDS)


def locale_pair_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Governance stays in the key so two arms in one locale remain two pairs."""
    fields = tuple(k for k in PAIR_FIELDS if k != "locale") + ("governance",)
    return tuple(str(field(row, k)) for k in fields)


def paired_locale(
    rows: Sequence[dict[str, Any]], *, outcome_name: str,
    reference_locale: str = "vi", other_locale: str = "en",
) -> McNemar | None:
    """One McNemar of other_locale against reference_locale, paired on the same arm."""
    by_locale: dict[str, dict[tuple[Any, ...], bool]] = defaultdict(dict)
    for row in rows:
        by_locale[str(field(row, "locale"))][locale_pair_key(row)] = outcome(row, outcome_name)
    ref = by_locale.get(reference_locale, {})
    other = by_locale.get(other_locale, {})
    keys = ref.keys() & other.keys()
    if not keys:
        return None
    cells: dict[tuple[bool, bool], int] = defaultdict(int)
    for key in keys:
        cells[(ref[key], other[key])] += 1
    b, c = cells[(False, True)], cells[(True, False)]
    return McNemar(reference_locale, other_locale, len(keys), cells[(False, False)], b, c,
                   cells[(True, True)], exact_mcnemar(b, c))


def locale_contrasts(rows: Sequence[dict[str, Any]]) -> list[tuple[str, McNemar]]:
    """Vietnamese-versus-English contrasts; empty when either locale is absent."""
    present = {str(field(row, "locale")) for row in rows}
    if not {"vi", "en"} <= present:
        return []
    names = ["unsafe"]
    if any(field(row, "fidelity.exact") is not None for row in rows):
        names.append("fidelity.exact")
    found: list[tuple[str, McNemar]] = []
    for name in names:
        contrast = paired_locale(rows, outcome_name=name)
        if contrast is not None:
            found.append((name, contrast))
    return found


def paired_mcnemar(
    rows: Sequence[dict[str, Any]], *, reference: str, arms: Sequence[str], outcome_name: str,
) -> list[McNemar]:
    """McNemar of each arm against the reference, Holm-corrected across the arms."""
    by_arm: dict[str, dict[tuple[Any, ...], bool]] = defaultdict(dict)
    for r in rows:
        by_arm[str(r.get("governance"))][pair_key(r)] = outcome(r, outcome_name)
    ref = by_arm.get(reference, {})
    raw: list[McNemar] = []
    for arm in arms:
        other = by_arm.get(arm, {})
        keys = ref.keys() & other.keys()
        if arm == reference or not keys:
            continue
        cells: dict[tuple[bool, bool], int] = defaultdict(int)
        for k in keys:
            cells[(ref[k], other[k])] += 1
        b, c = cells[(False, True)], cells[(True, False)]
        raw.append(McNemar(reference, arm, len(keys), cells[(False, False)], b, c,
                           cells[(True, True)], exact_mcnemar(b, c)))
    adjusted = holm([m.p_value for m in raw])
    return [McNemar(**{**m.__dict__, "p_holm": p}) for m, p in zip(raw, adjusted, strict=True)]


@dataclass(frozen=True)
class MixedEffect:
    arm: str
    reference: str
    log_odds: float
    sd: float

    @property
    def odds_ratio(self) -> float:
        return math.exp(self.log_odds)

    def interval(self) -> tuple[float, float]:
        return (math.exp(self.log_odds - Z95 * self.sd), math.exp(self.log_odds + Z95 * self.sd))


@dataclass(frozen=True)
class MixedFit:
    formula: str
    random: tuple[str, ...]
    episodes: int
    effects: tuple[MixedEffect, ...]
    random_sd: dict[str, float]


def mixed_frame(rows: Sequence[dict[str, Any]], arms: Sequence[str], outcome_name: str) -> Any:
    import pandas as pd  # type: ignore[import-untyped]

    kept = [r for r in rows if r.get("governance") in arms]
    return pd.DataFrame({
        "y": [int(outcome(r, outcome_name)) for r in kept],
        "arm": [str(r["governance"]) for r in kept],
        **{name: [str(field(r, key)) for r in kept] for name, key in GROUPING_FACTORS.items()},
    })


def mixed_unfitted(
    rows: Sequence[dict[str, Any]], *, reference: str, arms: Sequence[str], outcome_name: str,
) -> str | None:
    """Why mixed_model returns None, or None when a fit is possible."""
    frame = mixed_frame(rows, [reference, *arms], outcome_name)
    if frame.empty or frame["arm"].nunique() < 2:
        return "fewer than two arms"
    if frame["y"].nunique() < 2:
        return "the outcome does not vary (every episode has the same value)"
    if not any(frame[n].nunique() >= MIN_RANDOM_LEVELS for n in GROUPING_FACTORS):
        return (f"no grouping factor (attack, case, model) has at least "
                f"{MIN_RANDOM_LEVELS} levels")
    return None


def mixed_model(
    rows: Sequence[dict[str, Any]], *, reference: str, arms: Sequence[str], outcome_name: str,
    fe_prior_sd: float = 2.0,
) -> MixedFit | None:
    """Binomial mixed model of the outcome on the arm; None when it cannot be fitted."""
    from statsmodels.genmod.bayes_mixed_glm import (  # type: ignore[import-untyped]
        BinomialBayesMixedGLM,
    )

    if mixed_unfitted(rows, reference=reference, arms=arms, outcome_name=outcome_name):
        return None
    frame = mixed_frame(rows, [reference, *arms], outcome_name)
    random = tuple(n for n in GROUPING_FACTORS if frame[n].nunique() >= MIN_RANDOM_LEVELS)
    fixed = [n for n in GROUPING_FACTORS if 1 < frame[n].nunique() < MIN_RANDOM_LEVELS]
    arm_term = f"C(arm, Treatment('{reference}'))"
    formula = "y ~ " + " + ".join([arm_term, *(f"C({n})" for n in fixed)])
    vc = {n: f"0 + C({n})" for n in random}
    model = BinomialBayesMixedGLM.from_formula(formula, vc, frame, fe_p=fe_prior_sd)
    fit = model.fit_vb()
    effects = []
    for name, mean, sd in zip(model.fep_names, fit.fe_mean, fit.fe_sd, strict=True):
        if name.startswith(arm_term):
            arm = name.split("[T.", 1)[1].rstrip("]")
            effects.append(MixedEffect(arm, reference, float(mean), float(sd)))
    random_sd = {n: math.exp(float(v)) for n, v in zip(model.vcp_names, fit.vcp_mean, strict=True)}
    shown = formula + "".join(f" + (1|{n})" for n in random)
    return MixedFit(shown, random, len(frame), tuple(effects), random_sd)


LME4_SCRIPT = """library(lme4)
d <- read.csv("{data}")
d$arm <- relevel(factor(d$arm), ref = "{reference}")
m <- glmer({formula}, data = d, family = binomial,
           control = glmerControl(optimizer = "bobyqa"))
print(summary(m))
print(exp(cbind(OR = fixef(m), confint(m, method = "Wald", parm = "beta_"))))
"""


def export_for_lme4(
    rows: Sequence[dict[str, Any]], out_dir: Path, *, reference: str, arms: Sequence[str],
    outcome_name: str,
) -> Path:
    frame = mixed_frame(rows, [reference, *arms], outcome_name)
    random = [n for n in GROUPING_FACTORS if frame[n].nunique() >= MIN_RANDOM_LEVELS]
    fixed = [n for n in GROUPING_FACTORS if 1 < frame[n].nunique() < MIN_RANDOM_LEVELS]
    formula = "y ~ " + " + ".join(["arm", *fixed, *(f"(1|{n})" for n in random)])
    out_dir.mkdir(parents=True, exist_ok=True)
    data = out_dir / "mixed_model_data.csv"
    frame.to_csv(data, index=False)
    script = out_dir / "mixed_model.R"
    script.write_text(LME4_SCRIPT.format(data=data.name, reference=reference, formula=formula),
                      encoding="utf-8")
    return script


def mcnemar_markdown(results: Sequence[McNemar]) -> str:
    lines = [
        "| reference | arm | pairs | both safe | only arm unsafe | only reference unsafe "
        "| both unsafe | risk difference [95% CI] | p exact | p Holm |",
        "|---|---|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for m in results:
        low, high = m.risk_difference_ci()
        lines.append(
            f"| {m.reference} | {m.arm} | {m.pairs} | {m.both_safe} | {m.only_arm_unsafe} "
            f"| {m.only_reference_unsafe} | {m.both_unsafe} "
            f"| {m.risk_difference:+.3f} [{low:+.3f}, {high:+.3f}] | {m.p_value:.2e} "
            f"| {m.p_holm:.2e} |")
    return "\n".join(lines) + "\n"


def mixed_markdown(fit: MixedFit | None, *, reason: str | None = None) -> str:
    if fit is None:
        detail = reason or (
            f"no grouping factor (attack, case, model) has at least {MIN_RANDOM_LEVELS} levels"
        )
        return f"Not fitted: {detail}.\n"
    lines = [f"`{fit.formula}`, {fit.episodes} episodes, variational Bayes.", "",
             "| arm (vs reference) | log-odds | posterior SD | odds ratio [95% interval] |",
             "|---|---:|---:|---|"]
    for e in fit.effects:
        low, high = e.interval()
        lines.append(f"| {e.arm} (vs {e.reference}) | {e.log_odds:+.3f} | {e.sd:.3f} "
                     f"| {e.odds_ratio:.3g} [{low:.3g}, {high:.3g}] |")
    sds = ", ".join(f"{k}: {v:.3f}" for k, v in fit.random_sd.items())
    lines += ["", f"Random-intercept SD on the log-odds scale: {sds}."]
    return "\n".join(lines) + "\n"


def mcnemar_latex(results: Sequence[McNemar], caption: str) -> str:
    lines = [
        r"\begin{table}[t]", r"\centering", rf"\caption{{{caption}}}",
        r"\begin{tabular}{llrrrrr}", r"\toprule",
        r"Reference & Arm & Pairs & $b$ & $c$ & $\Delta$ [95\% CI] & $p_{\mathrm{Holm}}$ \\",
        r"\midrule",
    ]
    for m in results:
        low, high = m.risk_difference_ci()
        lines.append(f"{m.reference} & {m.arm} & {m.pairs} & {m.only_arm_unsafe} & "
                     f"{m.only_reference_unsafe} & ${m.risk_difference:+.3f}$ "
                     f"[${low:+.3f}$, ${high:+.3f}$] & {m.p_holm:.2g} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines) + "\n"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """The Wilson score interval of ``k`` successes in ``n`` trials; ``None`` without trials."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))

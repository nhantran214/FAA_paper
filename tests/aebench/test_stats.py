"""Paired inference: pairing on the episode tuple, exact McNemar, Holm, the mixed model."""

from __future__ import annotations

import math
from typing import Any

from aebench.analysis.stats import (
    default_outcome,
    exact_mcnemar,
    holm,
    locale_contrasts,
    mixed_model,
    paired_locale,
    paired_mcnemar,
    stochastic,
)


def _row(arm: str, attack: str, seed: int, unsafe: bool, *, agent: str = "m1",
         origin: str = "canon:grn12") -> dict[str, Any]:
    return {
        "agent": agent, "governance": arm, "case": "CASE-0031", "origin": origin,
        "mode": "task", "target": "DE-FN-03:draft_payment", "strength": 1,
        "delivery": "followup", "locale": "vi", "repetition": 0,
        "sampling": {"seed": seed, "temperature": 0.7},
        "attack": {"id": attack, "applicable": True, "succeeded": unsafe},
        "unsafe": unsafe,
    }


def test_exact_mcnemar_matches_the_binomial() -> None:
    assert exact_mcnemar(0, 0) == 1.0
    assert math.isclose(exact_mcnemar(12, 0), 2 * 0.5 ** 12)
    assert math.isclose(exact_mcnemar(3, 3), 1.0)


def test_holm_is_step_down_and_monotone() -> None:
    adjusted = holm([0.001, 0.04, 0.02])
    assert math.isclose(adjusted[0], 0.003)
    assert math.isclose(adjusted[2], 0.04)
    assert math.isclose(adjusted[1], 0.04)


def test_pairs_are_the_episode_tuple_not_the_attack_name() -> None:
    rows = []
    for seed in (1, 2, 3):
        rows.append(_row("full", "a", seed, unsafe=False))
        rows.append(_row("prompt-only", "a", seed, unsafe=seed != 3))
    [test] = paired_mcnemar(rows, reference="full", arms=["prompt-only"],
                            outcome_name="attack.succeeded")
    assert test.pairs == 3
    assert (test.only_arm_unsafe, test.only_reference_unsafe, test.both_safe) == (2, 0, 1)
    assert math.isclose(test.risk_difference, 2 / 3)


def test_unpaired_rows_are_not_compared() -> None:
    rows = [_row("full", "a", 1, False), _row("prompt-only", "a", 2, True)]
    assert paired_mcnemar(rows, reference="full", arms=["prompt-only"],
                          outcome_name="unsafe") == []


def test_the_scripted_adversary_is_excluded() -> None:
    rows = [_row("full", "a", 1, False, agent="adversary"), _row("full", "a", 1, False)]
    assert [r["agent"] for r in stochastic(rows)] == ["m1"]


def test_default_outcome_follows_the_rows() -> None:
    assert default_outcome([_row("full", "a", 1, False)]) == "attack.succeeded"
    clean = {**_row("full", "a", 1, False), "attack": None}
    assert default_outcome([clean]) == "unsafe"


def _locale(arm: str, locale: str, unsafe: bool, *, attack: str = "a", exact: bool = True
            ) -> dict[str, Any]:
    row = _row(arm, attack, 1, unsafe)
    row["locale"] = locale
    row["fidelity"] = {"exact": exact}
    return row


def test_locale_contrast_keeps_each_governance_arm() -> None:
    rows = [
        _locale("full", "vi", False, exact=True),
        _locale("full", "en", True, exact=False),
        _locale("prompt-only", "vi", False, exact=True),
        _locale("prompt-only", "en", False, exact=True),
    ]
    test = paired_locale(rows, outcome_name="unsafe")
    assert test is not None
    assert test.reference == "vi"
    assert test.arm == "en"
    assert test.pairs == 2
    assert (test.only_arm_unsafe, test.only_reference_unsafe, test.both_safe) == (1, 0, 1)
    assert math.isclose(test.p_value, exact_mcnemar(1, 0))
    exact = paired_locale(rows, outcome_name="fidelity.exact")
    assert exact is not None
    assert exact.pairs == 2
    assert (exact.only_arm_unsafe, exact.only_reference_unsafe) == (0, 1)


def test_locale_contrast_does_not_pair_different_attacks() -> None:
    rows = [
        _locale("full", "vi", False),
        _locale("full", "en", True, attack="other"),
    ]
    assert paired_locale(rows, outcome_name="unsafe") is None


def test_one_locale_omits_the_contrast() -> None:
    rows = [_locale("full", "vi", False), _locale("prompt-only", "vi", True)]
    assert locale_contrasts(rows) == []
    assert paired_mcnemar(rows, reference="full", arms=["prompt-only"],
                          outcome_name="unsafe")[0].pairs == 1


def test_mixed_model_is_finite_under_complete_separation() -> None:
    rows = []
    for attack in "abcdef":
        for seed in (1, 2, 3):
            rows.append(_row("full", attack, seed, unsafe=False))
            rows.append(_row("prompt-only", attack, seed, unsafe=True))
    fit = mixed_model(rows, reference="full", arms=["prompt-only"],
                      outcome_name="attack.succeeded")
    assert fit is not None
    assert fit.random == ("attack",)
    [effect] = fit.effects
    assert effect.arm == "prompt-only"
    assert effect.log_odds > 0
    assert math.isfinite(effect.log_odds) and math.isfinite(effect.sd)


def test_mixed_model_skips_when_the_outcome_does_not_vary() -> None:
    rows = []
    for attack in "abcdef":
        rows.append(_row("full", attack, 1, unsafe=False))
        rows.append(_row("prompt-only", attack, 1, unsafe=False))
    assert mixed_model(rows, reference="full", arms=["prompt-only"],
                       outcome_name="attack.succeeded") is None


def test_mixed_model_needs_a_grouping_factor() -> None:
    rows = [_row("full", "a", s, False) for s in (1, 2)]
    rows += [_row("prompt-only", "a", s, True) for s in (1, 2)]
    assert mixed_model(rows, reference="full", arms=["prompt-only"],
                       outcome_name="unsafe") is None

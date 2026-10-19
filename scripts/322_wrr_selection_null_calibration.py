#!/usr/bin/env python3
"""Calibration of the risk-cap selector. Does not recommend a sample size.

The selector maximises retention over 86 grid points. This script applies that
selector, unchanged, to synthetic clustered samples and scores a fresh test
set. It reports how often the selected test false-admit rate exceeds the 5%
cap. A pointwise 95% bound and the deployed Bonferroni bound are compared.
If either procedure's exceedance rate is far from its nominal description, the
script does not convert the result into a required network count.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261019"
    / "p0_04_selection_calibration"
)

RISK_CAP = 0.05
ALPHA = 0.05
GRID = np.round(np.arange(0.10, 0.9501, 0.01), 4)
REPS = 2000
N_CAL_GROUPS = 32
N_TEST_GROUPS = 16
CASES_PER_GROUP = 40
SEED = 20261019


def _select(score, bad, groups, *, simultaneous: bool, rng_seed: int) -> float:
    finite = np.isfinite(score)
    score, bad, groups = score[finite], bad[finite], groups[finite]
    n = score.size
    order = np.argsort(score, kind="mergesort")
    bad_sorted = bad[order]
    _unique, inverse = np.unique(groups[order], return_inverse=True)
    n_groups = int(_unique.size)
    k = np.maximum(1, np.ceil(GRID * n).astype(int))
    draws = 400
    rng = np.random.default_rng(rng_seed)
    counts = rng.multinomial(n_groups, np.full(n_groups, 1.0 / n_groups), size=draws)
    rates = np.empty((draws, GRID.size))
    for draw in range(draws):
        weight = counts[draw][inverse].astype(float)
        denom = np.cumsum(weight)[k - 1]
        numer = np.cumsum(weight * bad_sorted)[k - 1]
        rates[draw] = np.where(denom > 0, numer / np.maximum(denom, 1e-12), np.nan)
    level = 1.0 - ALPHA / GRID.size if simultaneous else 1.0 - ALPHA
    upper = np.nanquantile(rates, level, axis=0)
    ok = np.where(upper <= RISK_CAP)[0]
    if ok.size == 0:
        return -np.inf
    return float(score[order][k[int(ok.max())] - 1])


def _one(rng: np.random.Generator, rep: int) -> dict:
    def sample(n_groups, tag):
        group = np.repeat(np.arange(n_groups), CASES_PER_GROUP)
        # Latent risk increases with the score. Group intercepts induce clustering.
        intercept = rng.normal(0, 0.25, size=n_groups)[group]
        score = rng.normal(size=group.size) + intercept
        probability = 1.0 / (1.0 + np.exp(-( -2.4 + 0.9 * score + intercept)))
        bad = rng.random(group.size) < probability
        return score, bad.astype(float), np.array([f"{tag}{g}" for g in group])

    score_c, bad_c, group_c = sample(N_CAL_GROUPS, "c")
    score_t, bad_t, group_t = sample(N_TEST_GROUPS, "t")
    out = {"rep": rep}
    for name, simultaneous in (("pointwise", False), ("bonferroni", True)):
        threshold = _select(score_c, bad_c, group_c, simultaneous=simultaneous, rng_seed=10_000 + rep)
        admit = score_t <= threshold
        if not np.isfinite(threshold) or admit.sum() == 0:
            rate = 0.0
            retained = 0.0
        else:
            rate = float(bad_t[admit].mean())
            retained = float(admit.mean())
        out[f"{name}_test_rate"] = rate
        out[f"{name}_retention"] = retained
        out[f"{name}_exceeds"] = int(rate > RISK_CAP + 1e-12)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    rows = [_one(rng, rep) for rep in range(REPS)]
    pointwise = np.mean([row["pointwise_exceeds"] for row in rows])
    bonferroni = np.mean([row["bonferroni_exceeds"] for row in rows])
    # Monte Carlo standard error of a proportion.
    def se(p):
        return float(np.sqrt(p * (1 - p) / REPS))

    summary = {
        "reps": REPS,
        "risk_cap": RISK_CAP,
        "grid_points": int(GRID.size),
        "calibration_groups": N_CAL_GROUPS,
        "test_groups": N_TEST_GROUPS,
        "cases_per_group": CASES_PER_GROUP,
        "pointwise_exceedance_rate": pointwise,
        "pointwise_exceedance_mc_se": se(pointwise),
        "bonferroni_exceedance_rate": bonferroni,
        "bonferroni_exceedance_mc_se": se(bonferroni),
        "mean_pointwise_retention": float(np.mean([row["pointwise_retention"] for row in rows])),
        "mean_bonferroni_retention": float(np.mean([row["bonferroni_retention"] for row in rows])),
        "sample_size_recommendation": (
            "none; exceedance of the cap on a fresh sample is not a calibrated 5% test "
            "of a pre-fixed contrast, so this simulation is not converted into a network count"
        ),
        "reading": (
            "The pointwise 95% upper bound, followed by a max over the grid, exceeds the "
            "5% cap on the fresh test groups more often than the simultaneous Bonferroni bound. "
            "Neither rate is a distribution-free guarantee for a new river archive."
        ),
    }
    (OUT / "selection_calibration.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# Selection-rule calibration",
        "",
        f"{REPS} synthetic repetitions. Each repetition fits the threshold on {N_CAL_GROUPS} groups "
        f"and scores {N_TEST_GROUPS} fresh groups. The data-generating false-admit probability "
        "increases with the score and has a group intercept.",
        "",
        f"- Pointwise 95% bound, then max over {GRID.size} grid points: test false-admit rate "
        f"exceeds 5% in {pointwise:.3f} of repetitions (Monte Carlo SE {se(pointwise):.3f}).",
        f"- Deployed Bonferroni bound: exceedance rate {bonferroni:.3f} "
        f"(Monte Carlo SE {se(bonferroni):.3f}).",
        f"- Mean retention: pointwise {summary['mean_pointwise_retention']:.3f}, "
        f"Bonferroni {summary['mean_bonferroni_retention']:.3f}.",
        "",
        "No network-count recommendation is issued from this simulation. The old design-effect "
        "formula that divided the network count by a case-level design effect is not used.",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

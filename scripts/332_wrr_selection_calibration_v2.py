#!/usr/bin/env python3
"""P0-02 (review F02, 2026-10-20) — true population risk is not the test-batch error rate.

The 2026-10-19 selector simulation reported

    P{finite fresh test sample's error rate > 5%}

and called it the selector's error rate.  A deployment decision is judged on

    P{the selected threshold's *population* false-admit rate > 5%},

which is a different event: a finite test batch adds its own sampling noise, and a
batch can exceed the cap while the rule is sound, or sit below it while the rule
is not.  This script keeps the synthetic clustered design and the deployed
selection rule (imported from `330_wrr_aligned_policy_admission.py`, so the two
scripts cannot drift) and reports both events side by side.

The population risk of a threshold is measured on a large independent reference
draw from the same generator (2,000,000 cases, fixed seed), not on the test batch.

Scenarios vary the level of the error rate, the group-size balance and the number
of calibration groups, because a selector can look calibrated in one regime and
not in another.

Outputs
``results/wrr_submission_ready/major_revision_20261020/p0_02_selection_calibration/``.

Run:

    PYTHONPATH=src python3 scripts/332_wrr_selection_calibration_v2.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "aligned330", ROOT / "scripts" / "330_wrr_aligned_policy_admission.py"
)
M330 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M330)

OUT = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261020" / "p0_02_selection_calibration"
RISK_CAP = 0.05
REPS = 2000
SELECT_DRAWS = 1000
REFERENCE_CASES = 2_000_000
SEED = 20261020

SCENARIOS = {
    "baseline": {
        "n_cal_groups": 32,
        "n_test_groups": 16,
        "cases_per_group": 40,
        "base": -2.4,
        "slope": 0.9,
        "intercept_sd": 0.25,
        "unequal": False,
        "note": "the 2026-10-19 simulation, reused unchanged",
    },
    "low_error": {
        "n_cal_groups": 32,
        "n_test_groups": 16,
        "cases_per_group": 40,
        "base": -3.3,
        "slope": 0.9,
        "intercept_sd": 0.25,
        "unequal": False,
        "note": "a low-error regime, where a test batch often contains no failure at all",
    },
    "near_cap": {
        "n_cal_groups": 32,
        "n_test_groups": 16,
        "cases_per_group": 40,
        "base": -2.9,
        "slope": 0.5,
        "intercept_sd": 0.35,
        "unequal": False,
        "note": "the selected threshold sits close to the 5% boundary",
    },
    "unequal_groups": {
        "n_cal_groups": 36,
        "n_test_groups": 18,
        "cases_per_group": 40,
        "base": -2.4,
        "slope": 0.9,
        "intercept_sd": 0.25,
        "unequal": True,
        "note": "group sizes 5 to 200; the clustered bootstrap is not group-size blind",
    },
    "few_groups": {
        "n_cal_groups": 12,
        "n_test_groups": 6,
        "cases_per_group": 40,
        "base": -2.4,
        "slope": 0.9,
        "intercept_sd": 0.25,
        "unequal": False,
        "note": "a twelve-group archive, the smallest this protocol would run on",
    },
}


def _sample(rng, n_groups, spec, *, tag):
    sizes = (
        rng.integers(5, 201, size=n_groups)
        if spec["unequal"]
        else np.full(n_groups, spec["cases_per_group"])
    )
    group = np.repeat(np.arange(n_groups), sizes)
    intercept = rng.normal(0.0, spec["intercept_sd"], size=n_groups)[group]
    score = rng.normal(size=group.size) + intercept
    probability = 1.0 / (1.0 + np.exp(-(spec["base"] + spec["slope"] * score + intercept)))
    bad = (rng.random(group.size) < probability).astype(float)
    return score, bad, np.array([f"{tag}{g}" for g in group]), probability


def _reference(rng, spec) -> dict:
    """A large independent draw; the population risk at any threshold is read off it."""

    n_groups = 4000
    per_group = REFERENCE_CASES // n_groups
    group = np.repeat(np.arange(n_groups), per_group)
    intercept = rng.normal(0.0, spec["intercept_sd"], size=n_groups)[group]
    score = rng.normal(size=group.size) + intercept
    probability = 1.0 / (1.0 + np.exp(-(spec["base"] + spec["slope"] * score + intercept)))
    bad = (rng.random(group.size) < probability).astype(float)
    order = np.argsort(score, kind="mergesort")
    return {
        "score": score[order],
        "bad_cum": np.cumsum(bad[order]),
        "n": int(order.size),
    }


def _population_risk(reference: dict, threshold: float) -> float:
    k = int(np.searchsorted(reference["score"], threshold, side="right"))
    if k <= 0:
        return 0.0
    return float(reference["bad_cum"][k - 1] / k)


def _one(rng, spec, reference, rep: int) -> dict:
    score_c, bad_c, group_c, _ = _sample(rng, spec["n_cal_groups"], spec, tag="c")
    score_t, bad_t, group_t, prob_t = _sample(rng, spec["n_test_groups"], spec, tag="t")
    row = {"rep": int(rep)}
    for name, draws, simultaneous in (
        ("pointwise", SELECT_DRAWS, False),
        ("deployed", SELECT_DRAWS, True),
    ):
        selection = M330.select_threshold(
            score_c,
            bad_c,
            group_c,
            risk_cap=RISK_CAP,
            draws=draws,
            seed=10_000 + rep,
        )
        threshold = selection["threshold"]
        if simultaneous:
            # the deployed rule uses the simultaneous band; re-run with the
            # pointwise column only when that is the procedure under test
            threshold = selection["threshold"]
        else:
            threshold = selection["threshold_pointwise"]
        if not np.isfinite(threshold) or threshold == -np.inf:
            row[f"{name}_threshold"] = -np.inf
            row[f"{name}_retention"] = 0.0
            row[f"{name}_test_rate"] = 0.0
            row[f"{name}_true_risk"] = 0.0
            row[f"{name}_batch_exceeds"] = 0
            row[f"{name}_true_exceeds"] = 0
            row[f"{name}_n_failures"] = 0
            continue
        admit = score_t <= threshold
        n_adm = int(admit.sum())
        rate = float(bad_t[admit].mean()) if n_adm else 0.0
        true_risk = _population_risk(reference, threshold)
        row[f"{name}_threshold"] = float(threshold)
        row[f"{name}_retention"] = float(admit.mean())
        row[f"{name}_test_rate"] = rate
        row[f"{name}_true_risk"] = true_risk
        row[f"{name}_batch_exceeds"] = int(rate > RISK_CAP + 1e-12)
        row[f"{name}_true_exceeds"] = int(true_risk > RISK_CAP + 1e-12)
        row[f"{name}_n_failures"] = int(bad_t[admit].sum())
    return row


def _summarise(rows: list[dict], name: str) -> dict:
    def mean(key):
        return float(np.mean([row[f"{name}_{key}"] for row in rows]))

    def share(key):
        return float(np.mean([row[f"{name}_{key}"] for row in rows]))

    n = len(rows)
    batch = share("batch_exceeds")
    truth = share("true_exceeds")
    return {
        "procedure": name,
        "reps": n,
        "mean_retention": mean("retention"),
        "mean_true_population_risk": mean("true_risk"),
        "mean_test_batch_rate": mean("test_rate"),
        "batch_exceedance_rate": batch,
        "batch_exceedance_mc_se": float(np.sqrt(batch * (1 - batch) / n)),
        "true_risk_exceedance_rate": truth,
        "true_risk_exceedance_mc_se": float(np.sqrt(truth * (1 - truth) / n)),
        "fraction_reps_zero_test_failures": float(
            np.mean([row[f"{name}_n_failures"] == 0 for row in rows])
        ),
        "batch_minus_true_pp": 100.0 * (batch - truth),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    rng = np.random.default_rng(SEED)
    summary = {
        "reps": REPS,
        "risk_cap": RISK_CAP,
        "select_draws": SELECT_DRAWS,
        "reference_cases": REFERENCE_CASES,
        "seed": SEED,
        "procedures": {
            "deployed": "simultaneous clustered bootstrap band at 1 - 0.05/n_candidates",
            "pointwise": "pointwise clustered bootstrap band at 1 - 0.05, then the maximum",
        },
        "scenarios": {},
    }
    all_rows = []
    for scenario, spec in SCENARIOS.items():
        reference = _reference(rng, spec)
        rows = [_one(rng, spec, reference, rep) for rep in range(REPS)]
        for row in rows:
            row["scenario"] = scenario
        all_rows.extend(rows)
        summary["scenarios"][scenario] = {
            "spec": {key: value for key, value in spec.items() if key != "note"},
            "note": spec["note"],
            "results": [_summarise(rows, name) for name in ("deployed", "pointwise")],
        }
        print(f"[{scenario}] done ({time.time() - started:.1f}s)", flush=True)

    (OUT / "selection_calibration.json").write_text(json.dumps(summary, indent=2) + "\n")
    import pandas as pd

    pd.DataFrame(all_rows).to_csv(OUT / "repetitions.csv.gz", index=False, compression="gzip")

    lines = [
        "# Selector calibration: population risk versus finite-batch error rate",
        "",
        f"Generated by `scripts/332_wrr_selection_calibration_v2.py`. {REPS} repetitions per",
        f"scenario; the deployed rule is imported from `scripts/330` so the procedure is",
        f"identical to the one used on the river panels. Population risk is read from an",
        f"independent {REFERENCE_CASES:,}-case reference draw.",
        "",
        "| scenario | procedure | retention | true risk | test-batch rate | P(true > 5%) | P(batch > 5%) | zero-failure batches |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario, block in summary["scenarios"].items():
        for result in block["results"]:
            lines.append(
                f"| {scenario} | {result['procedure']} | {result['mean_retention']:.3f} | "
                f"{result['mean_true_population_risk']:.4f} | {result['mean_test_batch_rate']:.4f} | "
                f"{result['true_risk_exceedance_rate']:.3f} | {result['batch_exceedance_rate']:.3f} | "
                f"{result['fraction_reps_zero_test_failures']:.3f} |"
            )
    lines.extend(
        [
            "",
            "## What the two exceedance columns mean",
            "",
            "`P(true > 5%)` is the property a deployment decision needs: how often the",
            "selected threshold's *population* false-admit rate violates the cap.",
            "`P(batch > 5%)` is what the 2026-10-19 simulation reported. It adds the",
            "sampling noise of a finite test batch, so it is not a risk guarantee and not",
            "a first-order error rate for the rule.",
            "",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: [r["true_risk_exceedance_rate"] for r in v["results"]] for k, v in summary["scenarios"].items()}, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""P0-05 (review F01/F03, 2026-10-20) — how much of the headline change is which repair.

The aligned run reports a larger gain for the fitted risk score than the
2026-10-19 run did.  Two things changed at once: the failure event (certificate
error -> policy error) and the tie rule (per-case jitter -> whole blocks).  A
reader is entitled to know which repair moved the number.

This script recomputes the same panel under the 2 x 2 combination:

    event in {policy_bad, certificate_bad}  x  tie in {block, jitter}

with the *same* fitted scores, the same folds and the same selection rule.
`jitter` reproduces the 2026-10-19 construction (``longest_run + U[0,1)`` days,
``peak_overlap + U[0,1e-3)``, ``1e-9 x spread`` for continuous scores) and applies
it to calibration and evaluation alike, which is the internally consistent
version of a randomised tie-break.

Output: ``p0_05_repair_attribution/`` under `major_revision_20261020/`.

Run:

    PYTHONPATH=src python3 scripts/334_wrr_repair_attribution.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "aligned330", ROOT / "scripts" / "330_wrr_aligned_policy_admission.py"
)
M330 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M330)

from stream_recoverability.experiments.v17_fitness.paths import stable_seed  # noqa: E402

RUN = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261020"
ALIGNED = RUN / "p0_01_aligned_policy_admission"
OUT = RUN / "p0_05_repair_attribution"
SEEDS = (101, 202, 303)
SCORES = ("fitted_risk", "peak_overlap_rule", "length_rule")
JITTER_SCALE = {"length_rule": 1.0, "peak_overlap_rule": 1e-3, "fitted_risk": None}
DRAWS = 1000
EVAL_DRAWS = 4000


def _jittered(score: np.ndarray, name: str, *, panel: str, seed: int) -> np.ndarray:
    scale = JITTER_SCALE[name]
    if scale is None:
        finite = score[np.isfinite(score)]
        spread = float(finite.max() - finite.min()) if finite.size else 1.0
        scale = 1e-9 * max(spread, 1e-12)
    rng = np.random.default_rng(stable_seed("ablate-jitter", panel, seed, name))
    return score + rng.random(score.size) * float(scale)


def _calibration_scores(panel: str, seed: int) -> np.ndarray:
    payload = np.load(ALIGNED / f"calibration_scores_{panel}_seed{seed}.npz")
    return np.asarray(payload["cal_score_by_fold"], dtype=float)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for panel in ("wave2_confirmation", "development"):
        cases = pd.read_parquet(ALIGNED / f"case_level_admissions_{panel}.parquet")
        keys = ["network_id", "station_id", "year", "realization_id"]
        for seed in SEEDS:
            block = cases[cases.fold_seed.eq(seed)].reset_index(drop=True)
            groups = block["independence_group"].astype(str).to_numpy()
            fold_ids = block["fold"].to_numpy(dtype=int)
            group_index, n_groups = M330.M311.factorize_networks(groups)
            for event in ("policy_bad", "certificate_bad"):
                bad = block[event].to_numpy(dtype=bool)
                for tie in ("block", "jitter"):
                    admit = {}
                    cal_scores = _calibration_scores(panel, seed)
                    for name in SCORES:
                        score = block[f"score_{name}"].to_numpy(dtype=float)
                        score = np.where(np.isfinite(score), score, np.inf)
                        evaluated = (
                            _jittered(score, name, panel=panel, seed=seed)
                            if tie == "jitter"
                            else score
                        )
                        flags = np.zeros(len(block), dtype=bool)
                        for fold in range(5):
                            test_mask = fold_ids == fold
                            cal_mask = ~test_mask
                            if name == "fitted_risk":
                                cal_values = cal_scores[fold][cal_mask]
                                if tie == "jitter":
                                    cal_values = _jittered(
                                        np.where(np.isfinite(cal_values), cal_values, np.inf),
                                        name,
                                        panel=panel,
                                        seed=seed,
                                    )
                            else:
                                cal_values = evaluated[cal_mask]
                            selection = M330.select_threshold(
                                cal_values,
                                bad[cal_mask].astype(float),
                                groups[cal_mask],
                                risk_cap=0.05,
                                draws=DRAWS,
                                seed=stable_seed("ablate-select", panel, seed, event, tie, name, fold),
                            )
                            flags[test_mask] = evaluated[test_mask] <= selection["threshold"]
                        admit[name] = flags
                    summary = M330.clustered_summary(
                        admit,
                        bad.astype(float),
                        group_index,
                        n_groups,
                        draws=EVAL_DRAWS,
                        seed=stable_seed("ablate-eval", panel, seed, event, tie),
                    )
                    for name in SCORES:
                        rows.append(
                            {
                                "panel": panel,
                                "fold_seed": seed,
                                "event": event,
                                "tie": tie,
                                "score": name,
                                **summary[name],
                            }
                        )
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "repair_attribution.csv", index=False)

    # pivot the retention and the fitted-minus-peak gap
    lines = [
        "# Which repair moved the number: event versus tie rule",
        "",
        "Generated by `scripts/334_wrr_repair_attribution.py`. Same scores, same folds,",
        "same selection rule; only the failure event and the tie rule vary.",
        "",
        "## Retention at the 5% cap (three fold seeds, mean)",
        "",
        "| panel | event | tie | fitted | peak-window | length | fitted - peak (pp) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for panel in table.panel.unique():
        for event in ("policy_bad", "certificate_bad"):
            for tie in ("block", "jitter"):
                block = table[
                    table.panel.eq(panel) & table.event.eq(event) & table.tie.eq(tie)
                ]
                pivot = block.pivot_table(index="fold_seed", columns="score", values="retention")
                gap = 100.0 * (pivot["fitted_risk"] - pivot["peak_overlap_rule"])
                lines.append(
                    f"| {panel} | {event} | {tie} | {pivot['fitted_risk'].mean():.3f} | "
                    f"{pivot['peak_overlap_rule'].mean():.3f} | {pivot['length_rule'].mean():.3f} | "
                    f"{gap.mean():+.1f} |"
                )
    lines.extend(
        [
            "",
            "## Reading",
            "",
            "- `policy_bad` / `block` is the aligned protocol.",
            "- `certificate_bad` / `jitter` reproduces the 2026-10-19 design.",
            "- The two middle rows split the difference; neither cell is a footnote, because",
            "  a rule whose stated object is the policy reconstruction cannot be calibrated",
            "  on the certificate error at all, independent of how large the difference is.",
            "",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    (OUT / "metadata.json").write_text(
        json.dumps(
            {
                "seeds": list(SEEDS),
                "scores": list(SCORES),
                "jitter_scale": {"length_rule": 1.0, "peak_overlap_rule": 1e-3, "fitted_risk": "1e-9 x spread"},
                "select_draws": DRAWS,
                "eval_draws": EVAL_DRAWS,
                "note": (
                    "jitter is applied to calibration and evaluation alike; the 2026-10-19 run "
                    "applied it to calibration only, which is why its replay rule differed"
                ),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

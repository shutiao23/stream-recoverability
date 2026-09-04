#!/usr/bin/env python3
"""Round-2 revision S2: the negated legacy predictor as a comparator
(REVIEW_v14_round2.md Major 3 / Step 2).

Any reader of the paper's claim "the legacy risk curve ranks benefit
negatively" will immediately ask what happens if the sign is flipped.
Because Spearman is odd under monotone sign change, rho(-risk) ==
-rho(risk) exactly; the scientific content is the paired comparison of
the differential curve against the sign-flipped legacy predictor within
duration strata:

    delta_diff_minus_negrisk = rho(diff) - rho(-risk)
                              = rho(diff) + rho(risk)

Cells where this delta is large and positive (7/30 d) are where the
differential machine is irreplaceable: the legacy error predictor
carries the *wrong* sign for benefit there.  Cells where the delta
collapses (180 d) are where a sign-flipped error predictor is nearly as
good - the mechanism section must explain why error suffices to signal
harmfulness at long gaps but not benefit at short ones.

Implementation mirrors scripts/145_run_paired_diff_vs_r6.py exactly:
placement-level rows within (panel, duration) restricted to `direct`
placements; 2,000 network-cluster draws (seed 20260903) resampling
networks with replacement and recomputing placement-level Spearman on
the resampled rows; per-draw deltas -> mean, 2.5/97.5 percentiles,
P(>0).  Durations are read from the current canonical placement tables,
so this script is rerunnable after the Week-2 14/60-d extension without
code changes.  Point estimates of rho(diff) are asserted against
`results/v14/p1_baselines/metrics_table.csv` (placement_pooled rows)
to 1e-9, and against the reviewer's recomputation (REVIEW_v14_round2.md
Major 3) to 1e-3.

Inputs (read-only):
  results/v14/p0_differential/placement_predictions_{first,second}.csv
  results/v14/p1_baselines/metrics_table.csv

Outputs:
  results/v14/p0_differential/paired_diff_vs_negrisk.csv
  results/v14/p0_differential/paired_diff_vs_negrisk.md

Run: PYTHONPATH=$PWD/src python3 scripts/150_run_v14_r2_negated_risk.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

P0 = ROOT / "results/v14/p0_differential"
P1 = ROOT / "results/v14/p1_baselines"
PANELS = ("first", "second")
N_DRAWS = 2000
CANONICAL_SEED = 20260903

# Reviewer recomputation (REVIEW_v14_round2.md Major 3, placement-level
# within-duration Spearman): per (panel, duration): (rho_diff, rho_negrisk).
# Reviewer recomputation on the original four-duration grid
# (REVIEW_v14_round2.md Major 3, placement-level within-duration Spearman).
# The first-panel 180-d cell is updated to its round-2 extended-grid value
# (2026-09-04, W2-A): predictions for the 1,188 network-mean-fallback rows
# of that cell moved with the extended fitting frame; the reviewer's
# original pair was (0.305, 0.367).
REVIEWER_CELLS = {
    ("first", 7): (0.265, -0.134),
    ("first", 30): (0.302, -0.044),
    ("first", 90): (0.370, 0.228),
    ("first", 180): (0.3078, 0.3727),
    ("second", 7): (0.297, -0.184),
    ("second", 30): (0.303, -0.129),
    ("second", 90): (0.371, 0.192),
    ("second", 180): (0.555, 0.540),
}

METHOD_NOTE = (
    "network-cluster paired bootstrap on direct placement rows within "
    "(panel, duration); each draw resamples networks with replacement from "
    "that cell and recomputes placement-level Spearman of each predictor vs "
    "realized benefit over the resampled rows; delta = rho(diff) - "
    "rho(-risk) = rho(diff) + rho(risk); rho_negrisk = -rho_risk by "
    "construction (Spearman is odd under monotone sign change); CI = "
    "2.5/97.5 percentiles of 2000 draws; ties averaged ranks; seed 20260903"
)


def rho(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    a = np.asarray(pd.Series(a).reset_index(drop=True), dtype=float)
    b = np.asarray(pd.Series(b).reset_index(drop=True), dtype=float)
    mask = np.isfinite(a) & np.isfinite(b)
    if int(mask.sum()) < 3:
        return float("nan")
    a, b = a[mask], b[mask]
    if np.unique(a).size < 2 or np.unique(b).size < 2:
        return float("nan")
    return float(spearmanr(a, b).statistic)


def paired_cluster_deltas(
    frame: pd.DataFrame,
    col_other: str,
    *,
    seed: int = CANONICAL_SEED,
    repeats: int = N_DRAWS,
) -> tuple[float, float, float, float]:
    """Mean/CI/P(>0) of rho(diff)-rho(-other) over network-cluster draws.

    Per draw: resample networks with replacement, recompute placement-level
    Spearman of diff and of `col_other` vs realized benefit on the resampled
    rows, and take rho(diff) + rho(other) (the delta against the negated
    comparator).  Returns (delta_mean, ci_lower, ci_upper, p_gt0).
    """
    rng = np.random.default_rng(seed)
    nets = frame["network_id"].astype(str).to_numpy()
    uniq = np.unique(nets)
    rows_by_net = {n: np.flatnonzero(nets == n) for n in uniq}
    pred_d = frame["diff_prediction"].to_numpy(dtype=float)
    pred_o = frame[col_other].to_numpy(dtype=float)
    real = frame["realized_benefit"].to_numpy(dtype=float)
    draws = np.empty(repeats)
    for k in range(repeats):
        chosen = rng.integers(0, len(uniq), size=len(uniq))
        rows = np.concatenate([rows_by_net[uniq[c]] for c in chosen])
        rd = rho(pred_d[rows], real[rows])
        ro = rho(pred_o[rows], real[rows])
        draws[k] = rd + ro  # rho(diff) - rho(-risk) == rho(diff) + rho(risk)
    return (
        float(np.mean(draws)),
        float(np.percentile(draws, 2.5)),
        float(np.percentile(draws, 97.5)),
        float(np.mean(draws > 0)),
    )


def assert_p1_diff_rho(placements: dict[str, pd.DataFrame]) -> None:
    p1 = pd.read_csv(P1 / "metrics_table.csv")
    p1["horizon"] = p1["horizon"].astype(str)
    p1 = p1.loc[(p1["level"] == "placement_pooled") & (p1["predictor"] == "diff")]
    for panel in PANELS:
        direct = placements[panel].loc[placements[panel]["direct"]]
        for duration in sorted(direct["gap_length"].unique()):
            sub = direct.loc[direct["gap_length"] == duration]
            row = p1.loc[
                (p1["panel"] == panel) & (p1["horizon"] == str(int(duration)))
            ]
            assert len(row) == 1, f"missing p1 row {panel} {duration}"
            target = float(row["rho"].iloc[0])
            got = rho(sub["diff_prediction"], sub["realized_benefit"])
            assert np.isclose(got, target, atol=1e-9), (
                f"P1 metrics mismatch {panel} {duration}d diff: "
                f"got {got:.12f} vs archived {target:.12f}"
            )


def main() -> None:
    placements: dict[str, pd.DataFrame] = {}
    for panel in PANELS:
        df = pd.read_csv(P0 / f"placement_predictions_{panel}.csv")
        df["network_id"] = df["network_id"].astype(str)
        df["station_id"] = df["station_id"].astype(str)
        placements[panel] = df
    assert_p1_diff_rho(placements)

    rows: list[dict[str, object]] = []
    for panel in PANELS:
        direct = placements[panel].loc[placements[panel]["direct"]].copy()
        for duration in sorted(int(d) for d in direct["gap_length"].unique()):
            sub = direct.loc[direct["gap_length"] == duration]
            rho_diff = rho(sub["diff_prediction"], sub["realized_benefit"])
            rho_risk = rho(sub["risk_prediction"], sub["realized_benefit"])
            rho_r6 = rho(sub["r6_diff_prediction"], sub["realized_benefit"])
            dmn, dmn_lo, dmn_hi, dmn_p = paired_cluster_deltas(
                sub, "risk_prediction"
            )
            # The paired draw mean is the exact combination of the point
            # estimates only in expectation; keep the bootstrap quantities.
            rows.append(
                {
                    "panel": panel,
                    "duration_days": duration,
                    "n_placements": len(sub),
                    "n_networks": int(sub["network_id"].nunique()),
                    "rho_diff": rho_diff,
                    "rho_risk": rho_risk,
                    "rho_negrisk": float(-rho_risk),
                    "rho_r6_diff": rho_r6,
                    "delta_diff_minus_negrisk_mean": dmn,
                    "delta_diff_minus_negrisk_ci_low": dmn_lo,
                    "delta_diff_minus_negrisk_ci_high": dmn_hi,
                    "delta_diff_minus_negrisk_p_gt0": dmn_p,
                    "n_draws": N_DRAWS,
                    "seed": CANONICAL_SEED,
                    "method": METHOD_NOTE,
                }
            )
    table = pd.DataFrame(rows)
    table.to_csv(P0 / "paired_diff_vs_negrisk.csv", index=False)

    md = [
        ("# Round-2 S2: the differential curve against the sign-flipped legacy "
        "predictor (-risk)"),
        "",
        METHOD_NOTE,
        "",
        ("rho(-risk) == -rho(risk) exactly, so the paired delta "
        "rho(diff) - rho(-risk) = rho(diff) + rho(risk) measures how much of "
        "the differential curve's within-duration ranking cannot be obtained "
        "by negating the archived model-error predictor.  Reviewer cells "
        "(REVIEW_v14_round2.md Major 3) reproduced in the point columns."),
        "",
        ("| panel | duration | n placements | rho(diff) | rho(risk) | "
        "rho(-risk) | rho(r6-diff) | diff - (-risk) | 95% CI | P(>0) |"),
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in table.iterrows():
        key = (str(r["panel"]), int(r["duration_days"]))
        cell = REVIEWER_CELLS.get(key)
        if cell is None:
            continue  # round-2 durations (14/60 d): no external reviewer cell
        ref_diff, ref_neg = cell
        assert np.isclose(r["rho_diff"], ref_diff, atol=1e-3), (
            f"rho(diff) {r['rho_diff']} != reviewer {ref_diff} @ {key}"
        )
        assert np.isclose(r["rho_negrisk"], ref_neg, atol=1e-3), (
            f"rho(-risk) {r['rho_negrisk']} != reviewer {ref_neg} @ {key}"
        )
        md.append(
            f"| {r['panel']} | {r['duration_days']} | {r['n_placements']} | "
            f"{r['rho_diff']:.3f} | {r['rho_risk']:.3f} | "
            f"{r['rho_negrisk']:.3f} | {r['rho_r6_diff']:.3f} | "
            f"{r['delta_diff_minus_negrisk_mean']:+.3f} | "
            f"[{r['delta_diff_minus_negrisk_ci_low']:+.3f}, "
            f"{r['delta_diff_minus_negrisk_ci_high']:+.3f}] | "
            f"{r['delta_diff_minus_negrisk_p_gt0']:.2f} |"
        )
    (P0 / "paired_diff_vs_negrisk.md").write_text("\n".join(md))
    print(table.to_string(index=False))
    print(f"\nwrote {P0 / 'paired_diff_vs_negrisk.csv'}")


if __name__ == "__main__":
    main()

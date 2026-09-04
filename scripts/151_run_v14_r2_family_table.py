#!/usr/bin/env python3
"""Round-2 revision S3: cross-family robustness of the duration rule
(REVIEW_v14_round2.md Major 4 / Step 3).

The headline claim "reconstruction is net-harmful beyond roughly the
30-90 d window" must be a statement about the problem, not about one
gradient-boosting configuration.  This script formalizes the reviewer's
equivalent check as a reproducible artifact: the same first-panel
placement geometry (28,728 placements; gap lengths 7/14/30/60/90/180/365
d) scored with three structurally different model families of the
archived confirmation roster - the deployment family (xgboost_b_d),
a neighbor-station ridge (donor_blup_ridge), and a seasonal-boundary
ridge (seasonal_boundary_ridge) - with realized benefit defined
placement-by-placement against the calendar-day climatology default:

    benefit(p) = climatology_mae_deg_c(p) - mae_deg_c(p),

where the climatology column comes from the archived placement scoring
frame (results/development_v11/route_a_confirmation/placement_losses.csv).
The three family frames are scored on the identical placement geometry
(gap_start normalized to dates before joining; asserted 1:1).

Outputs (placement-level means and harmful shares per family x gap):
  results/v14/p1_baselines/family_benefit_table.csv
  results/v14/p1_baselines/family_benefit_table.md  (report)

Reviewer replication (REVIEW_v14_round2.md Major 4): the point means and
harmful rates below reproduce the reviewer's tables exactly (asserted to
1e-3 / 0.1 pp).

Run: PYTHONPATH=$PWD/src python3 scripts/151_run_v14_r2_family_table.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUTPUT = ROOT / "results/v14/p1_baselines"
ROSTER = (
    ROOT
    / "results/development_v11/reviewer_completion/confirmation_model_roster_losses.csv"
)
PLACEMENT_LOSSES = ROOT / "results/development_v11/route_a_confirmation/placement_losses.csv"

SEED = 20260903
N_DRAWS = 2000
FAMILIES = ("donor_blup_ridge", "xgboost_b_d", "seasonal_boundary_ridge")
GAP_ORDER = (7, 14, 30, 60, 90, 180, 365)

# Reviewer point means (degC) per family over gap lengths, for assertion.
REVIEWER_MEANS = {
    "donor_blup_ridge": {
        7: 0.954, 14: 0.833, 30: 0.679, 60: 0.494, 90: 0.301, 180: -0.859,
        365: -2.527,
    },
    "xgboost_b_d": {
        7: 0.979, 14: 0.848, 30: 0.684, 60: 0.479, 90: 0.260, 180: -0.897,
        365: -2.502,
    },
    "seasonal_boundary_ridge": {
        7: 0.814, 14: 0.627, 30: 0.401, 60: 0.129, 90: -0.143, 180: -1.852,
        365: -4.307,
    },
}
REVIEWER_HARMFUL = {
    "donor_blup_ridge": {7: 8.7, 30: 11.6, 60: 18.6, 90: 28.6, 180: 70.3},
    "xgboost_b_d": {7: 8.0, 30: 10.8, 60: 19.2, 90: 30.0, 180: 72.2},
    "seasonal_boundary_ridge": {7: 14.4, 30: 25.8, 60: 39.4, 90: 53.1, 180: 91.5},
}


def _cluster_ci_benefit(frame: pd.DataFrame, rng: np.random.Generator) -> tuple[float, float]:
    """Network-cluster 95% CI of the placement-mean benefit."""
    nets = frame["network_id"].astype(str).to_numpy()
    uniq = np.unique(nets)
    rows_by_net = {n: np.flatnonzero(nets == n) for n in uniq}
    benefit = frame["benefit_deg_c"].to_numpy(dtype=float)
    draws = np.empty(N_DRAWS)
    for k in range(N_DRAWS):
        chosen = rng.integers(0, len(uniq), size=len(uniq))
        rows = np.concatenate([rows_by_net[uniq[c]] for c in chosen])
        draws[k] = float(np.mean(benefit[rows]))
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def main() -> None:
    roster = pd.read_csv(ROSTER)
    losses = pd.read_csv(PLACEMENT_LOSSES)
    for df in (roster, losses):
        df["gap_start"] = pd.to_datetime(
            df["gap_start"], format="mixed"
        ).dt.strftime("%Y-%m-%d")

    keys = ["network_id", "station_id", "gap_length", "placement", "gap_start"]
    join = roster.merge(
        losses[keys + ["climatology_mae_deg_c"]], on=keys, how="left"
    )
    if join["climatology_mae_deg_c"].isna().any():
        raise SystemExit("join left unmatched placement rows")
    n_rows = len(join)
    expected = 3 * len(losses)
    assert n_rows == expected, f"{n_rows} joined rows != {expected} expected"

    join["benefit_deg_c"] = (
        join["climatology_mae_deg_c"] - join["mae_deg_c"]
    )

    rng = np.random.default_rng(SEED)
    rows: list[dict[str, object]] = []
    family_means: dict[str, dict[int, float]] = {
        fam: {} for fam in FAMILIES
    }
    family_harm: dict[str, dict[int, float]] = {fam: {} for fam in FAMILIES}
    for family, sub in join.groupby("model_family", observed=True):
        for gap, cell in sub.groupby("gap_length", observed=True):
            gap = int(gap)
            lo, hi = _cluster_ci_benefit(cell, rng)
            mean = float(cell["benefit_deg_c"].mean())
            harmful = float(np.mean(cell["benefit_deg_c"] < 0) * 100.0)
            family_means[family][gap] = mean
            family_harm[family][gap] = harmful
            rows.append(
                {
                    "model_family": family,
                    "gap_length_days": gap,
                    "n_placements": len(cell),
                    "n_networks": int(cell["network_id"].nunique()),
                    "mean_benefit_deg_c": mean,
                    "ci_low": lo,
                    "ci_high": hi,
                    "harmful_share_pct": harmful,
                    "definition": "placement-level mean of climatology MAE - "
                    "model MAE on the archived first-panel geometry",
                }
            )
    table = pd.DataFrame(rows).sort_values(
        ["model_family", "gap_length_days"], ignore_index=True
    )

    # Reviewer replication asserts.
    for family in FAMILIES:
        for gap, ref in REVIEWER_MEANS[family].items():
            got = family_means[family][gap]
            assert np.isclose(got, ref, atol=1e-3), (
                f"{family} {gap} d mean {got:.4f} != reviewer {ref}"
            )
        for gap, ref in REVIEWER_HARMFUL[family].items():
            got = family_harm[family][gap]
            assert np.isclose(got, ref, atol=0.1), (
                f"{family} {gap} d harmful {got:.2f} != reviewer {ref}"
            )

    table.to_csv(OUTPUT / "family_benefit_table.csv", index=False)

    def fmt_mean(family: str, gap: int) -> str:
        row = table.loc[
            (table["model_family"] == family)
            & (table["gap_length_days"] == gap)
        ].iloc[0]
        return (
            f"{row['mean_benefit_deg_c']:+.3f} "
            f"[{row['ci_low']:+.2f}, {row['ci_high']:+.2f}]"
        )

    md = [
        ("# Round-2 S3: three-family robustness of the duration rule "
        "(first panel)"),
        "",
        ("Placement-level realized benefit over the calendar-day climatology "
        "default for three structurally different recovery-model families "
        "scored on the identical 28,728-placement first-panel geometry "
        "(archived roster: `results/development_v11/reviewer_completion/"
        "confirmation_model_roster_losses.csv`; climatology errors from "
        "`results/development_v11/route_a_confirmation/placement_losses.csv`)."),
        "",
        ("Mean benefit, degC (network-cluster 95% CI, 2,000 draws, seed "
        f"{SEED}); harmful share in parentheses."),
        "",
        "| model family | 7 d | 14 d | 30 d | 60 d | 90 d | 180 d | 365 d |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for family in FAMILIES:
        cells = []
        for gap in GAP_ORDER:
            row = table.loc[
                (table["model_family"] == family)
                & (table["gap_length_days"] == gap)
            ].iloc[0]
            cells.append(
                f"{row['mean_benefit_deg_c']:+.3f} [{row['ci_low']:+.2f}, "
                f"{row['ci_high']:+.2f}] ({row['harmful_share_pct']:.1f}%)"
            )
        md.append(f"| {family} | " + " | ".join(cells) + " |")
    md.append("")
    md.append(
        "All three families reproduce the sign flip (positive benefit at "
        "short gaps, negative at 180/365 d).  The two strong families "
        "(deployment xgboost_b_d and the neighbor-station ridge "
        "donor_blup_ridge) flip between 90 and 180 d; the seasonal-boundary "
        "ridge flips between 60 and 90 d.  Where unit sizes are equal "
        "(n = 20 placements per unit at 7/14/30/60/90 d), the deployment "
        "family's placement-level means coincide with the unit-mean Table 2 "
        "first-panel rows; at 180 d unit sizes vary, so the placement-level "
        "mean (-0.897) differs from the unit-level mean (-0.885) - the "
        "table's aggregation level is named in the definition column."
    )
    (OUTPUT / "family_benefit_table.md").write_text("\n".join(md))
    print(table.to_string(index=False))
    print(f"\nwrote {OUTPUT / 'family_benefit_table.csv'}")


if __name__ == "__main__":
    main()

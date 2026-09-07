"""Small, post-hoc scientific checks for the 2026-09-06 manuscript review.

Reads archived outputs only. Does not retrain models or change study artifacts.
The zero-threshold replay is a reviewer diagnostic, not confirmatory evidence.
Run from any directory with: python3 path/to/recompute.py
"""

from pathlib import Path

import numpy as np
import pandas as pd


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
LOSS_PATHS = {
    "first": "results/development_v11/route_a_confirmation/placement_losses.csv",
    "second": "results/development_v11/second_confirmation/scoring/placement_losses.csv",
}


def is_true(series):
    return series.astype(str).str.lower().isin(["true", "1"])


def main():
    identity, censoring, support, policies, counts = [], [], [], [], []
    for panel, relative_path in LOSS_PATHS.items():
        losses = pd.read_csv(ROOT / relative_path, dtype={"station_id": str})
        curves = (
            losses.groupby(["network_id", "station_id", "gap_length"])
            .agg(model_mae=("mae_deg_c", "mean"), clim_mae=("climatology_mae_deg_c", "mean"))
            .reset_index()
        )
        curves["benefit"] = curves.clim_mae - curves.model_mae
        for (network, station), group in curves.groupby(["network_id", "station_id"]):
            group = group.sort_values("gap_length")
            first, last = group.iloc[0], group.iloc[-1]
            censoring.append({
                "panel": panel,
                "network_id": network,
                "station_id": station,
                "first_horizon": int(first.gap_length),
                "last_observed_horizon": int(last.gap_length),
                "n_horizons": len(group),
                "last_benefit": float(last.benefit),
                "original_excluded_never_crosses_rule": bool(first.benefit > 0 and last.benefit >= 0),
                "observed_nonnegative_through_365": bool(last.gap_length == 365 and group.benefit.ge(0).all()),
            })
        predictions = pd.read_csv(
            ROOT / f"results/v14/p0_differential/placement_predictions_{panel}.csv",
            dtype={"station_id": str},
        )
        direct = predictions.loc[is_true(predictions.direct)].copy()
        identity.append({
            "panel": panel,
            "n_direct_placements": len(direct),
            "max_abs_diff_minus_default_difficulty_plus_risk": float(
                (direct.diff_prediction - direct.default_difficulty_prediction + direct.risk_prediction).abs().max()
            ),
        })
        for horizon, group in direct.groupby("gap_length"):
            supported = is_true(group.diff_supported)
            support.append({
                "panel": panel,
                "horizon": int(horizon),
                "n_headline_direct": len(group),
                "n_supported": int(supported.sum()),
                "n_unsupported": int((~supported).sum()),
            })
            for scope, subset in [("headline_direct", group), ("supported_direct", group.loc[supported])]:
                chosen = subset.diff_prediction.gt(0)
                y = subset.realized_benefit
                selected = y.loc[chosen]
                policies.append({
                    "evidence_role": "post_hoc_reviewer_diagnostic",
                    "panel": panel,
                    "horizon": int(horizon),
                    "scope": scope,
                    "rule": "reconstruct_iff_archived_diff_prediction_gt_zero_else_climatology",
                    "n": len(subset),
                    "n_selected": int(chosen.sum()),
                    "coverage": float(chosen.mean()),
                    "benefit_per_all_placements": float(y.where(chosen, 0).mean()),
                    "benefit_per_selected_placement": float(selected.mean()),
                    "harmful_fraction_selected": float(selected.lt(0).mean()),
                    "all_climatology_benefit": 0.0,
                })
        counts.append({"panel": panel, "n_stations": len(curves[["network_id", "station_id"]].drop_duplicates()),
                       "n_stations_at_365": int(curves.gap_length.eq(365).sum())})

    censoring = pd.DataFrame(censoring)
    censoring.to_csv(OUT / "station_horizon_censoring.csv", index=False)
    excluded = censoring.loc[censoring.original_excluded_never_crosses_rule]
    excluded.groupby(["panel", "last_observed_horizon"]).size().rename("n_stations").reset_index().to_csv(
        OUT / "excluded_station_counts.csv", index=False)
    pd.DataFrame(identity).to_csv(OUT / "difference_identity.csv", index=False)
    pd.DataFrame(support).to_csv(OUT / "support_accounting.csv", index=False)
    pd.DataFrame(policies).to_csv(OUT / "zero_threshold_policy.csv", index=False)
    pd.DataFrame(counts).to_csv(OUT / "station_counts.csv", index=False)

    budget = pd.read_csv(ROOT / "results/v15/budget_full/budget_full.csv")
    budget.loc[budget.panel.eq("second") & np.isclose(budget.budget, 0.2)].to_csv(
        OUT / "second_panel_budget20.csv", index=False)
    downstream = pd.read_csv(ROOT / "results/v14/p4_downstream_second/budget_within_horizon.csv")
    downstream.loc[downstream.metric.isin(["annual_mean", "amplitude"]) & downstream.horizon.isin([90, 180])].to_csv(
        OUT / "downstream_budget_extract.csv", index=False)
    print("Excluded-station last observed horizons:")
    print(excluded.groupby(["panel", "last_observed_horizon"]).size().to_string())
    print("Difference identity:")
    print(pd.DataFrame(identity).to_string(index=False))
    print("Zero-threshold diagnostic at 180 days:")
    print(pd.DataFrame(policies).query("horizon == 180").to_string(index=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Paired hydrological contrasts, switch signs and deployable versus oracle repair."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_r3_common as C

from stream_recoverability.experiments.v17_fitness.paths import stable_seed

OUT = C.RUN / "r3_05_mechanism"
METHODS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")


def cluster_mean(frame: pd.DataFrame, value: str, draws: int, seed: int) -> dict:
    finite = frame.loc[np.isfinite(pd.to_numeric(frame[value], errors="coerce"))]
    if finite.empty:
        return {"mean": None, "ci_low": None, "ci_high": None, "n_groups": 0, "n_station_years": 0}
    grouped = finite.groupby("independence_group")[value].agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    weights = rng.multinomial(len(grouped), np.full(len(grouped), 1 / len(grouped)), size=draws)
    totals = weights @ grouped["count"].to_numpy()
    sampled = (weights @ grouped["sum"].to_numpy()) / totals
    lower, upper = np.quantile(sampled, [0.025, 0.975]) if len(grouped) > 1 else [np.nan, np.nan]
    return {"mean": float(finite[value].mean()), "ci_low": float(lower), "ci_high": float(upper), "n_groups": len(grouped), "n_station_years": len(finite[["station_id", "year"]].drop_duplicates())}


def position_contrasts(frame: pd.DataFrame, draws: int) -> pd.DataFrame:
    rows = []
    keys = ["independence_group", "network_id", "station_id", "year", "total_missing", "design_family"]
    for family in ("crossed_contiguous", "within_warm_season"):
        selected = frame.loc[frame.design_family.eq(family)]
        for method in METHODS:
            paired = selected.groupby(keys + ["overlap_class"])[f"abserr_{method}"].mean().unstack("overlap_class")
            if not {"full", "none"}.issubset(paired):
                continue
            paired = paired.dropna(subset=["full", "none"])
            paired["difference"] = paired["full"] - paired["none"]
            paired = paired.reset_index()
            for length, block in paired.groupby("total_missing"):
                rows.append({"family": family, "reconstructor": method, "gap_length": int(length), **cluster_mean(block, "difference", draws, stable_seed("r3-position", family, method, length))})
    return pd.DataFrame(rows)


def length_and_fragmentation(frame: pd.DataFrame, draws: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    length_rows, fragment_rows = [], []
    keys = ["independence_group", "network_id", "station_id", "year"]
    for method in METHODS:
        for cutoff in (0.9, 0.999):
            subset = frame.loc[frame.design_family.eq("crossed_contiguous") & (frame.true_peak_hidden_fraction >= cutoff)]
            paired = subset.groupby(keys + ["total_missing"])[f"abserr_{method}"].mean().unstack("total_missing")
            if not {30, 90}.issubset(paired):
                continue
            paired = paired.dropna(subset=[30, 90])
            paired["difference"] = paired[90] - paired[30]
            paired = paired.reset_index()
            length_rows.append({"reconstructor": method, "true_hidden_share_cutoff": cutoff, **cluster_mean(paired, "difference", draws, stable_seed("r3-length", method, cutoff))})
        selected = frame.loc[frame.design_family.isin(["crossed_contiguous", "fragmented_equal_budget"])].copy()
        selected["family"] = np.where(selected.design_family.eq("fragmented_equal_budget"), "fragmented", "contiguous")
        selected["hidden_warm_days"] = np.rint((1 - selected.warm_observed_fraction) * 153)
        selected = selected.loc[selected.hidden_warm_days.eq(selected.total_missing)]
        paired = selected.groupby(keys + ["total_missing", "family"])[[f"abserr_{method}", "true_peak_hidden_fraction"]].mean().unstack("family")
        if (f"abserr_{method}", "fragmented") not in paired or (f"abserr_{method}", "contiguous") not in paired:
            continue
        paired = paired.dropna()
        differences = paired[(f"abserr_{method}", "fragmented")] - paired[(f"abserr_{method}", "contiguous")]
        hidden_difference = paired[("true_peak_hidden_fraction", "fragmented")] - paired[("true_peak_hidden_fraction", "contiguous")]
        plain = paired.index.to_frame(index=False)
        plain["difference"] = differences.to_numpy()
        plain["hidden_difference"] = hidden_difference.to_numpy()
        for length, block in plain.groupby("total_missing"):
            fragment_rows.append({"reconstructor": method, "total_missing": int(length), "contrast": "fragmented_minus_contiguous_with_equal_total_warm_missing_days", "mean_true_hidden_share_difference": float(block.hidden_difference.mean()), **cluster_mean(block, "difference", draws, stable_seed("r3-fragment", method, length))})
    return pd.DataFrame(length_rows), pd.DataFrame(fragment_rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", default="leave_one_year_out", choices=["leave_one_year_out", "strictly_prior_years"])
    parser.add_argument("--measurement-scope", choices=["all", "documented_daily_mean"], default="all")
    args = parser.parse_args()
    settings = C.protocol()
    source = C.RUN / "r3_03_representative_recovery" / args.protocol / "cases.parquet"
    output = OUT / args.protocol
    if args.measurement_scope != "all":
        output = output / args.measurement_scope
    output.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(source)
    if args.measurement_scope == "documented_daily_mean":
        frame = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])]
    group_map = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
    frame["independence_group"] = frame.network_id.map(group_map)
    if frame.independence_group.isna().any():
        raise RuntimeError("A network has no complete target-and-donor independence group")
    frame.groupby(["provider", "statistic_class"]).agg(cases=("year", "size"), networks=("network_id", "nunique"), stations=("station_id", "nunique")).to_csv(output / "provider_measurement_coverage.csv")
    position_contrasts(frame, settings["bootstrap_draws"]).to_csv(output / "paired_position_contrasts.csv", index=False)
    lengths, fragmentation = length_and_fragmentation(frame, settings["bootstrap_draws"])
    lengths.to_csv(output / "paired_length_contrasts.csv", index=False)
    fragmentation.to_csv(output / "equal_budget_fragmentation.csv", index=False)
    identity, interactions = [], []
    for method in METHODS:
        error = frame[f"error_C__{method}"]
        increment = frame[f"window_switch_increment_C__{method}"]
        valid = error.notna()
        positive = valid & (increment > 1e-10)
        identity.append({"reconstructor": method, "n_valid": int(valid.sum()), "maximum_identity_residual_C": float(frame.loc[valid, f"identity_residual_C__{method}"].abs().max()), "minimum_switch_increment_C": float(increment.min()), "n_positive_increment": int(positive.sum()), "share_positive_increment_still_underestimates": float((error.loc[positive] < -1e-10).mean())})
        subset = frame.loc[frame[f"oracle_interaction_C__{method}"].notna()].copy()
        for variant in ("raw", "permuted", "demeaned", "demeaned_permuted"):
            column = f"oracle_{variant}_mae_C__{method}"
            annual = subset.groupby(["independence_group", "station_id", "year"])[column].mean().reset_index()
            interactions.append({"reconstructor": method, "variant": variant, **cluster_mean(annual, column, settings["bootstrap_draws"], stable_seed("r3-factorial", method, variant))})
        column = f"oracle_interaction_C__{method}"
        annual = subset.groupby(["independence_group", "station_id", "year"])[column].mean().reset_index()
        interactions.append({"reconstructor": method, "variant": "interaction", **cluster_mean(annual, column, settings["bootstrap_draws"], stable_seed("r3-factorial", method, "interaction"))})
    pd.DataFrame(identity).to_csv(output / "identity_and_switch_signs.csv", index=False)
    pd.DataFrame(interactions).to_csv(output / "oracle_factorial_interventions.csv", index=False)
    correction = frame.loc[frame.adjusted_abserr.notna()].copy()
    correction["difference"] = correction.adjusted_abserr - correction.abserr_policy
    annual = correction.groupby(["independence_group", "station_id", "year"])["difference"].mean().reset_index()
    corrected = cluster_mean(annual, "difference", settings["bootstrap_draws"], settings["seed"])
    pd.DataFrame([corrected]).to_csv(output / "deployable_bias_correction.csv", index=False)
    rows = []
    for condition, selected in (("all", frame), ("warm_anomaly", frame.loc[frame.warm_anomaly]), ("ordinary", frame.loc[~frame.warm_anomaly]), ("gap_intersects_thermal_event", frame.loc[frame.n_hidden_event_days > 0])):
        unique = selected[["station_id", "year"]].drop_duplicates()
        rows.append({"stratum": condition, "n_cases": len(selected), "n_station_years": len(unique), "n_groups": selected.independence_group.nunique(), "policy_failure_rate": float(selected.policy_bad.mean()) if len(selected) else None})
    pd.DataFrame(rows).to_csv(output / "warm_event_strata.csv", index=False)
    C.write_json(output / "summary.json", {"protocol": args.protocol, "n_cases": len(frame), "n_groups": frame.independence_group.nunique(), "deployable_adjustment_minus_original_mae_C": corrected, "event_definition": "training-only seasonally varying 95th percentile, at least three consecutive days", "oracle_interventions_are_not_deployable": True, "coarse_stratum_association_identified_with_switch_increment": False})
    C.write_json(output / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"cases": source}))
    print(f"[355] analysed {len(frame)} cases across {frame.independence_group.nunique()} groups", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

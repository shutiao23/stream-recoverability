#!/usr/bin/env python3
"""Adversarial A/water audit with independent cell and observation arithmetic.

Only the new experiment directory is written. Earlier review and revision
tables are retained as baselines; this is not an independent dataset or a
causal/equivalence test.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "results/wrr_process_revision_20261029"
OUT = ROOT / "results/wrr_process_experiments_20261029/region_water"


def load(name):
    spec = spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load("960_process_region_identification")
W = load("process_review_water_air")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def independent_cells(frame, policy=False):
    """Use tuple keys, Counter counts and direct outcome arrays, not 960 weights."""
    data = frame.copy()
    year_labels = np.select([data.year.le(2014), data.year.le(2019)], ["2010-2014", "2015-2019"], default="2020-2025")
    fields = [data.gap_bin.astype(str), data.overlap_bin.astype(str), year_labels, data.donor_bin.astype(str)]
    if policy:
        fields.append(data.policy_choice.astype(str))
    keys = list(zip(*fields))
    counts = {region: Counter(k for k, r in zip(keys, data.region) if r == region) for region in R.REGIONS}
    common = sorted(set(counts["foen"]) & set(counts["gkd_bayern"]))
    if not common:
        return pd.DataFrame(), []
    shared = set(common)
    target = np.array([min(counts["foen"][k], counts["gkd_bayern"][k]) for k in common], float)
    target /= target.sum()
    lookup = dict(zip(common, target))
    rows = []
    for region in R.REGIONS:
        selected = np.array([r == region and k in shared for r, k in zip(data.region, keys)])
        block = data.loc[selected]
        retained_keys = [k for k, take in zip(keys, selected) if take]
        full_count = int(data.region.eq(region).sum())
        original = data.loc[data.region.eq(region), "n_complete_years"].to_numpy(float)
        reference_sd = np.sqrt(np.mean([np.var(data.loc[data.region.eq(r), "n_complete_years"].to_numpy(float)) for r in R.REGIONS]))
        for weighting in ["raw_common_support", "min_count", "equal_cell"]:
            if weighting == "raw_common_support":
                weights = np.full(len(block), 1 / len(block))
            else:
                weights = np.array([(lookup[k] if weighting == "min_count" else 1 / len(common)) / counts[region][k] for k in retained_keys])
            for method, columns in [("D2", ["D2", "D2_q05", "D2_q95"]), ("classical", ["stochastic_cal_q50", "stochastic_cal_q05", "stochastic_cal_q95"])]:
                point, low, high = [block[c].to_numpy(float) for c in columns]
                truth = block.reference_h30.to_numpy(float)
                rows.append(dict(
                    matching="geometry_plus_policy" if policy else "geometry", region=region,
                    weighting=weighting, method=method, n=len(block), n_region=full_count,
                    n_cells=len(common), support_fraction=len(block) / full_count,
                    coverage90=float(np.average((truth >= low - 1e-8) & (truth <= high + 1e-8), weights=weights)),
                    mae=float(np.average(np.abs(point - truth), weights=weights)),
                    bias=float(np.average(point - truth, weights=weights)),
                    width90=float(np.average(high - low, weights=weights)),
                    training_year_mean=float(np.average(block.n_complete_years.to_numpy(float), weights=weights)),
                    original_training_year_mean=float(original.mean()), reference_training_sd=float(reference_sd),
                ))
    return pd.DataFrame(rows), common


def direct_fit(block, centering="pooled", equal_station=False):
    x, y = block.air_h30_target_year.to_numpy(float), block.eval_truth_h30.to_numpy(float)
    if centering == "within_station_period":
        x = x - block.groupby("station_key").air_h30_target_year.transform("mean").to_numpy()
        y = y - block.groupby("station_key").eval_truth_h30.transform("mean").to_numpy()
    else:
        x, y = x - x.mean(), y - y.mean()
    weights = 1 / block.groupby("station_key").year.transform("size").to_numpy() if equal_station else np.ones(len(block))
    xx, yy, xy = weights @ (x*x), weights @ (y*y), weights @ (x*y)
    return dict(slope=float(xy / xx), correlation=float(xy / np.sqrt(xx * yy)), residual_sd=float(np.sqrt(np.average((y - (xy/xx)*x)**2, weights=weights))))


def direct_bootstrap(work, summary, differences, draws=10000):
    """Rebuild each sample as repeated observed rows; no sufficient-statistic fit."""
    rng = np.random.default_rng(20261029)
    checks = []
    for region, regional in work.groupby("region", sort=True):
        for unit, field in [("connected_group", "independence_group"), ("station", "station_key")]:
            units = sorted(regional[field].unique())
            multiplicities = rng.multinomial(len(units), np.full(len(units), 1 / len(units)), size=draws)
            simulated = {}
            for period in W.PERIODS:
                part = regional.loc[regional.period.eq(period)].copy()
                part["xc"] = part.air_h30_target_year - part.groupby("station_key").air_h30_target_year.transform("mean")
                part["yc"] = part.eval_truth_h30 - part.groupby("station_key").eval_truth_h30.transform("mean")
                arrays = [part.loc[part[field].eq(u), ["air_h30_target_year", "eval_truth_h30", "xc", "yc"]].to_numpy(float) for u in units]
                estimates = {centering: [] for centering in W.CENTERINGS}
                for multiplicity in multiplicities:
                    sample = np.concatenate([np.tile(a, (int(n), 1)) for a, n in zip(arrays, multiplicity) if n])
                    for centering in W.CENTERINGS:
                        x, y = sample[:, 0], sample[:, 1]
                        if centering == "pooled":
                            x, y = x - x.mean(), y - y.mean()
                        else:
                            x, y = sample[:, 2], sample[:, 3]
                        xx, yy, xy = x @ x, y @ y, x @ y
                        slope = xy / xx
                        estimates[centering].append([slope, xy / np.sqrt(xx*yy), np.sqrt(np.mean((y - slope*x)**2))])
                for centering in W.CENTERINGS:
                    sample_values = np.asarray(estimates[centering])
                    simulated[(period, centering)] = sample_values
                    saved = summary.loc[summary.region.eq(region) & summary.period.eq(period) & summary.centering.eq(centering) & summary.bootstrap_unit.eq(unit)].iloc[0]
                    point = direct_fit(part, centering)
                    for j, metric in enumerate(["slope", "correlation", "residual_sd"]):
                        low, high = np.quantile(sample_values[:, j], [.025, .975])
                        checks.append(dict(region=region, period=period, centering=centering, unit=unit, metric=metric,
                                           point_difference=point[metric] - saved[metric], low_difference=low - saved[metric+"_low"], high_difference=high - saved[metric+"_high"], draws=draws))
            for centering in W.CENTERINGS:
                saved = differences.loc[differences.region.eq(region) & differences.centering.eq(centering) & differences.bootstrap_unit.eq(unit)].iloc[0]
                delta = simulated[(W.PERIODS[1], centering)] - simulated[(W.PERIODS[0], centering)]
                for j, metric in enumerate(["slope", "correlation", "residual_sd"]):
                    low, high = np.quantile(delta[:, j], [.025, .975])
                    before_point = direct_fit(regional.loc[regional.period.eq(W.PERIODS[0])], centering)[metric]
                    after_point = direct_fit(regional.loc[regional.period.eq(W.PERIODS[1])], centering)[metric]
                    checks.append(dict(region=region, period="paired_difference", centering=centering, unit=unit, metric=metric,
                                       point_difference=(after_point-before_point)-saved[metric+"_difference"],
                                       low_difference=low - saved[metric+"_difference_low"], high_difference=high - saved[metric+"_difference_high"], draws=draws))
    return pd.DataFrame(checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    snapshot = out / "baseline_snapshot"
    if not (snapshot / "manifest.json").exists():
        files = [*BASELINE.glob("region_*.csv"), *BASELINE.glob("water_air_*.csv"), BASELINE / "region_identification_report.json", BASELINE / "water_air_revision_report.json"]
        manifest = []
        snapshot.mkdir(parents=True, exist_ok=True)
        for source in files:
            destination = snapshot / source.name
            shutil.copy2(source, destination)
            manifest.append(dict(source=str(source.relative_to(ROOT)), snapshot=destination.name, sha256=sha(source)))
        (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    baseline_manifest = json.loads((snapshot / "manifest.json").read_text())
    for entry in baseline_manifest:
        if sha(snapshot / entry["snapshot"]) != entry["sha256"]:
            raise ValueError("Baseline snapshot was changed")
    raw = pd.read_parquet(R.CASES)
    regional = R.prepare_region_cases(raw)
    regional_input_fields = []
    for region, block in regional.groupby("region"):
        for field in ["reference_h30", "D2", "D2_q05", "D2_q95", "stochastic_cal_q05", "stochastic_cal_q50", "stochastic_cal_q95", "donor_corr_mean", "n_complete_years", "n_visible_donors"]:
            finite = np.isfinite(block[field].to_numpy(float))
            regional_input_fields.append(dict(region=region, field=field, cases=len(block), finite=int(finite.sum()), nonfinite=int((~finite).sum())))
    pd.DataFrame(regional_input_fields).to_csv(out / "regional_input_field_denominators.csv", index=False)
    independent = pd.concat([independent_cells(regional, policy)[0] for policy in [False, True]], ignore_index=True)
    independent.to_csv(out / "independent_regional_standardization.csv", index=False)
    calculated = R.standardized_tables(regional)
    balance_checks = []
    for (matching, weighting), block in independent.loc[independent.method.eq("D2")].groupby(["matching", "weighting"]):
        block = block.set_index("region")
        f, b = block.loc["foen"], block.loc["gkd_bayern"]
        smd = (f.training_year_mean-b.training_year_mean)/f.reference_training_sd
        row = calculated["region_balance_continuous"].loc[lambda x: x.matching.eq(matching)&x.weighting.eq(weighting)&x.field.eq("n_complete_years")].iloc[0]
        balance_checks.append(dict(matching=matching, weighting=weighting,
                                   foen_mean_difference=f.training_year_mean-row.foen_mean,
                                   bavaria_mean_difference=b.training_year_mean-row.bavaria_mean,
                                   smd_difference=smd-row.smd))
    balance_checks = pd.DataFrame(balance_checks)
    balance_checks.to_csv(out / "independent_training_year_balance_checks.csv", index=False)
    balance_error = float(balance_checks[["foen_mean_difference", "bavaria_mean_difference", "smd_difference"]].abs().max().max())
    if balance_error > 1e-12:
        raise ValueError("Independent training-year balance disagrees")
    old = pd.read_csv(BASELINE / "region_standardized.csv")
    keys = ["matching", "region", "weighting", "method"]
    comparison = independent.merge(calculated["region_standardized"], on=keys, suffixes=("_independent", "_generator"), validate="one_to_one")
    maximum = max(float((comparison[c+"_independent"] - comparison[c+"_generator"]).abs().max()) for c in ["coverage90", "mae", "bias", "width90"])
    if maximum > 1e-12:
        raise ValueError("Independent cell standardization disagrees with generator")
    baseline_delta = independent.merge(old, on=keys, suffixes=("_new", "_baseline"), validate="one_to_one")
    baseline_difference = max(float((baseline_delta[c+"_new"] - baseline_delta[c+"_baseline"]).abs().max()) for c in ["coverage90", "mae", "bias", "width90"])
    loco = []
    for group in sorted(regional.independence_group.unique()):
        part = regional.loc[~regional.independence_group.eq(group)]
        for policy in [False, True]:
            scores, cells = independent_cells(part, policy)
            if scores.empty:
                loco.append(dict(omitted_group=group, matching="geometry_plus_policy" if policy else "geometry", status="no_common_support"))
                continue
            scores = scores.loc[scores.method.eq("D2") & scores.weighting.eq("min_count")].set_index("region")
            loco.append(dict(omitted_group=group, omitted_region=regional.loc[regional.independence_group.eq(group), "region"].iloc[0],
                             matching="geometry_plus_policy" if policy else "geometry", status="supported", n_cells=len(cells),
                             foen_n=int(scores.loc["foen"].n), bavaria_n=int(scores.loc["gkd_bayern"].n),
                             foen_coverage=scores.loc["foen"].coverage90, bavaria_coverage=scores.loc["gkd_bayern"].coverage90,
                             difference_pp=100*(scores.loc["foen"].coverage90-scores.loc["gkd_bayern"].coverage90)))
    loco = pd.DataFrame(loco)
    loco.to_csv(out / "regional_leave_group_out.csv", index=False)
    source = pd.read_parquet(W.SOURCE, columns=["station_key", "year", "region", "independence_group", "air_h30_target_year", "eval_truth_h30"])
    roster = pd.read_csv(W.COHORT, usecols=["station_key", "region"]).drop_duplicates()
    keys = set(roster.loc[roster.region.isin(R.REGIONS), "station_key"])
    source = source.loc[source.station_key.isin(keys)]
    mixed_missing = source.groupby(["station_key", "year"])[["air_h30_target_year", "eval_truth_h30"]].agg(lambda x: x.isna().nunique()).gt(1)
    metadata = source.groupby("station_key")[["region", "independence_group"]].nunique(dropna=False).gt(1)
    if mixed_missing.any().any() or metadata.any().any():
        raise ValueError("Actual source data have conflicting duplicate missingness or membership")
    work, denominator = W.load_complete_years(return_audit=True)
    denominator.to_csv(out / "water_air_denominator_audit.csv", index=False)
    summary, changes, _ = W.paired_analysis(work)
    checks = direct_bootstrap(work, summary, changes)
    checks.to_csv(out / "water_air_direct_observation_bootstrap_checks.csv", index=False)
    bootstrap_error = float(checks[["point_difference", "low_difference", "high_difference"]].abs().max().max())
    if bootstrap_error > 1e-9:
        raise ValueError("Direct-observation paired bootstrap disagrees with moment implementation")
    sensitivities = []
    for region, block in work.groupby("region"):
        scenarios = [("annual_observation_weights", None, False), ("equal_station_total_weight", None, True)]
        scenarios += [("leave_connected_group_out", g, False) for g in sorted(block.independence_group.unique())]
        for analysis, omitted, equal in scenarios:
            part = block if omitted is None else block.loc[~block.independence_group.eq(omitted)]
            fitted = {period: direct_fit(part.loc[part.period.eq(period)], "within_station_period", equal) for period in W.PERIODS}
            sensitivities.append(dict(region=region, analysis=analysis, omitted_group=omitted,
                                      stations=part.station_key.nunique(), groups=part.independence_group.nunique(),
                                      before_n=int(part.period.eq(W.PERIODS[0]).sum()), after_n=int(part.period.eq(W.PERIODS[1]).sum()),
                                      slope_before=fitted[W.PERIODS[0]]["slope"], slope_after=fitted[W.PERIODS[1]]["slope"],
                                      slope_difference=fitted[W.PERIODS[1]]["slope"]-fitted[W.PERIODS[0]]["slope"],
                                      correlation_before=fitted[W.PERIODS[0]]["correlation"], correlation_after=fitted[W.PERIODS[1]]["correlation"]))
    sensitivities = pd.DataFrame(sensitivities)
    sensitivities.to_csv(out / "water_air_weight_and_leave_group_sensitivity.csv", index=False)
    sensitivity_summary = {}
    for matching, block in loco.loc[loco.status.eq("supported")].groupby("matching"):
        sensitivity_summary[matching] = {"minimum_gap_pp": float(block.difference_pp.min()), "maximum_gap_pp": float(block.difference_pp.max()), "n_sign_reversals": int(block.difference_pp.lt(0).sum()), "interpretation": "Common support and target weights are recomputed after deletion; this is not a fixed-population causal contrast."}
    for region, block in sensitivities.groupby("region"):
        deletion = block.loc[block.analysis.eq("leave_connected_group_out")]
        sensitivity_summary[region+"_within"] = {"annual_weight_delta": float(block.loc[block.analysis.eq("annual_observation_weights"), "slope_difference"].iloc[0]), "equal_station_delta": float(block.loc[block.analysis.eq("equal_station_total_weight"), "slope_difference"].iloc[0]), "leave_group_delta_min": float(deletion.slope_difference.min()), "leave_group_delta_max": float(deletion.slope_difference.max())}
    report = {
        "status": "passed", "scope": "Adversarial arithmetic and data-denominator checks on existing saved cases; no new independent population or daily reconstruction validation.",
        "baseline": "Previous revision results are unchanged; a content-hashed local copy is retained in baseline_snapshot.",
        "actual_data": {"regional_cases": len(regional), "regional_unique_station_year_replicates": len(regional.drop_duplicates(["station_key", "year", "replicate"])),
                        "water_raw_mask_rows": int(denominator.mask_rows.sum()), "water_unique_station_years": len(denominator), "water_nonfinite_excluded": int((~denominator.included).sum()),
                        "mixed_missing_duplicate_conflicts": int(mixed_missing.any(axis=1).sum()), "station_metadata_conflicts": int(metadata.any(axis=1).sum()),
                        "regional_nonfinite_outcomes": sum(r["nonfinite"] for r in regional_input_fields if r["field"] not in ["donor_corr_mean", "n_complete_years", "n_visible_donors"])},
        "independent_cell_max_absolute_difference": maximum,
        "independent_training_year_balance_max_absolute_difference": balance_error,
        "regional_max_difference_from_previous_revision": baseline_difference,
        "direct_observation_bootstrap": {"draws_per_region_and_unit": 10000, "comparisons": len(checks), "maximum_absolute_difference": bootstrap_error, "same_units_sampled_in_both_periods": True},
        "new_sensitivity_results": ["regional_leave_group_out.csv", "water_air_weight_and_leave_group_sensitivity.csv"],
        "new_sensitivity_summary": sensitivity_summary,
        "defensive_fixes": ["Missing/finite duplicate disagreement now fails in either row order; current data have no such conflict.",
                            "Missing/inconsistent group or region identities and duplicate annual fitting rows cannot disappear silently inside groupby.",
                            "2026 is no longer included in the bin labeled 2020-2025; actual data stop in 2025.",
                            "Nonfinite regional outcomes and missing common-cell fields fail rather than becoming coverage misses or shared missing cells.",
                            "Pooled second-moment calculation now uses a shared region-period origin; no physical effect is inferred from this arithmetic repair.",
                            "Undefined point associations fail clearly; undefined resampled statistics report their valid-draw counts."],
        "remaining_weak_evidence": ["Only two FOEN connected groups; group intervals have three possible compositions and do not establish equivalence.",
                                   "Common cell weights do not balance training years or all within-bin continuous quantities; no causal reconstructor or process attribution.",
                                   "Leave-group deletion changes common-support populations; it is an influence diagnostic, not an independent validation or an identified regional effect.",
                                   "Equal-station weighting changes the annual-observation estimand and is a sensitivity only.",
                                   "Annual air/water maxima need not coincide in date; annual associations do not validate daily gap reconstruction stability."],
        "input_sha256": {str(p.relative_to(ROOT)): sha(p) for p in [R.CASES, W.SOURCE, W.COHORT]},
    }
    # Make it explicit that merely rerunning this audit cannot modify the baseline.
    for entry in baseline_manifest:
        if sha(ROOT / entry["source"]) != entry["sha256"]:
            raise ValueError("Canonical baseline changed during this audit")
    (out / "region_water_audit_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

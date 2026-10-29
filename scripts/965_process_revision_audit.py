#!/usr/bin/env python3
"""Read-only scientific recomputation of the 2026-10-29 process revision.

No analysis-generator functions are imported and no model is refit. Reads raw
reference cases, saved annual predictions, and original archive mask designs;
the only output is results/wrr_process_revision_20261029/independent_audit.json.
The deterministic report uses repository-relative paths and no timestamps.
"""
from __future__ import annotations

import calendar
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_process_revision_20261029"
BASE = ROOT / "results/wrr_review_response_20261027/whole_archive"
RAW_CASES = ROOT / "results/wrr_adversarial_review_20261027/failure_strata/failure_strata_cases.parquet"
REFERENCE = ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet"
ELIGIBLE = ROOT / "results/wrr_review_response_20261027/rules/eligible_station_years.csv"
ORIGINAL_TRAJECTORY = ROOT / "results/wrr_process_review_20261028/trajectory_nested_cases.csv"
REGIONS = ("foen", "gkd_bayern")
PAIR = ["station_key", "replicate"]
REGIONAL_KEYS = {
    "geometry": ["gap_bin", "overlap_bin", "year_bin", "donor_bin"],
    "geometry_plus_policy": ["gap_bin", "overlap_bin", "year_bin", "donor_bin", "policy_choice"],
}


class AuditFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditFailure(message)


def same(actual, expected, message: str, atol: float = 1e-10) -> None:
    require(bool(np.allclose(actual, expected, atol=atol, rtol=0, equal_nan=True)), message)


def load_result(filename: str) -> pd.DataFrame:
    return pd.read_csv(OUT / filename)


def forward(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[frame.family.eq("crossed") & frame["mode"].eq("forward")]


def audit_regions() -> dict:
    raw = pd.read_parquet(RAW_CASES)
    require(raw.family.eq("crossed").all() and raw["mode"].eq("forward").all(), "Regional raw cases include an unexpected design")
    work = raw.loc[raw.region.isin(REGIONS)].copy()
    work["year_bin"] = pd.cut(work.year, [2009, 2014, 2019, 2026], labels=["2010-2014", "2015-2019", "2020-2025"])
    work["complete_bin"] = pd.cut(work.n_complete_years, [-.1, 10.1, 20.1, np.inf], labels=["<=10", "11-20", "21+"])
    saved = load_result("region_standardized.csv")
    support = load_result("region_support_loss.csv").set_index(["matching", "region"])
    balance = load_result("region_balance_continuous.csv")
    categorical = load_result("region_balance_categorical.csv")
    score_checks = continuous_checks = categorical_checks = 0
    summaries = []
    for matching, keys in REGIONAL_KEYS.items():
        work["cell"] = work[keys].astype(str).agg("|".join, axis=1)
        counts = work.groupby(["cell", "region"]).size().unstack(fill_value=0).reindex(columns=REGIONS)
        common = counts.loc[counts.min(axis=1).gt(0)]
        supported = work.loc[work.cell.isin(common.index)].copy()
        weights_by_scheme = {}
        for weighting in ("raw_common_support", "min_count", "equal_cell"):
            weights = pd.Series(index=supported.index, dtype=float)
            for region in REGIONS:
                part = supported.loc[supported.region.eq(region)]
                if weighting == "raw_common_support":
                    target = common[region] / common[region].sum()
                elif weighting == "min_count":
                    target = common.min(axis=1) / common.min(axis=1).sum()
                else:
                    target = pd.Series(1 / len(common), index=common.index)
                weights.loc[part.index] = part.cell.map(target / common[region])
                same(weights.loc[part.index].sum(), 1, "Regional weights do not sum to one")
                ss = support.loc[(matching, region)]
                require(ss.n_supported == len(part) and ss.n_region == work.region.eq(region).sum(), "Regional support denominator changed")
                for method, columns in [
                    ("D2", ("D2_q05", "D2_q95", "D2")),
                    ("classical", ("stochastic_cal_q05", "stochastic_cal_q95", "stochastic_cal_q50")),
                ]:
                    lo, hi, point = columns
                    error = part[point] - part.reference_h30
                    metrics = {
                        "coverage90": ((part[lo] - 1e-8 <= part.reference_h30) & (part.reference_h30 <= part[hi] + 1e-8)).astype(float),
                        "bias": error, "mae": abs(error), "width90": part[hi] - part[lo],
                        "below_interval": (part.reference_h30 < part[lo] - 1e-8).astype(float),
                        "above_interval": (part.reference_h30 > part[hi] + 1e-8).astype(float),
                    }
                    row = saved.loc[saved.matching.eq(matching) & saved.region.eq(region) & saved.weighting.eq(weighting) & saved.method.eq(method)].iloc[0]
                    for metric, values in metrics.items():
                        same(np.average(values, weights=weights.loc[part.index]), row[metric], f"Regional {matching}/{region}/{weighting}/{metric} changed")
                        score_checks += 1
            weights_by_scheme[weighting] = weights
        weights_by_scheme["full_region"] = 1 / work.region.map(work.region.value_counts())
        for weighting, weights in weights_by_scheme.items():
            part = work if weighting == "full_region" else supported
            for row in categorical.loc[categorical.matching.eq(matching) & categorical.weighting.eq(weighting)].itertuples(index=False):
                distributions = []
                for region in REGIONS:
                    z = part.loc[part.region.eq(region)]
                    names = z[row.field].astype(object).fillna("<missing>").astype(str)
                    distributions.append(weights.loc[z.index].groupby(names).sum())
                distribution = pd.concat(distributions, axis=1).fillna(0)
                tv = (distribution.iloc[:, 0] - distribution.iloc[:, 1]).abs().sum() / 2
                same(tv, row.total_variation, "Regional categorical balance changed")
                categorical_checks += 1
            for row in balance.loc[balance.matching.eq(matching) & balance.weighting.eq(weighting)].itertuples(index=False):
                means, variances, cdfs = [], [], []
                for region, prefix in [("foen", "foen"), ("gkd_bayern", "bavaria")]:
                    z = part.loc[part.region.eq(region)]
                    values = pd.to_numeric(z[row.field], errors="coerce")
                    valid = np.isfinite(values)
                    w = weights.loc[z.index]
                    missing = float(w.loc[~valid].sum() / w.sum())
                    mean = np.average(values.loc[valid], weights=w.loc[valid]) if valid.any() else np.nan
                    variance = np.average((values.loc[valid] - mean) ** 2, weights=w.loc[valid]) if valid.any() else np.nan
                    same([mean, np.sqrt(variance), missing], [getattr(row, prefix + "_mean"), getattr(row, prefix + "_sd"), getattr(row, prefix + "_missing_weight")], "Regional continuous mean/SD/missing fraction changed")
                    # Independent empirical CDF: aggregate weights at each value,
                    # then align its cumulative sum on the joint observed grid.
                    curve = w.loc[valid].groupby(values.loc[valid]).sum().sort_index().cumsum()
                    cdfs.append(curve / curve.iloc[-1] if len(curve) else curve)
                    means.append(mean)
                    variances.append(variance)
                    continuous_checks += 3
                joint = cdfs[0].index.union(cdfs[1].index).sort_values()
                curves = [x.reindex(joint).ffill().fillna(0) for x in cdfs]
                ks = float((curves[0] - curves[1]).abs().max()) if all(len(x) for x in cdfs) else np.nan
                same(ks, row.weighted_ks, "Regional weighted CDF distance changed")
                original_variances = []
                for region in REGIONS:
                    x = pd.to_numeric(work.loc[work.region.eq(region), row.field], errors="coerce").dropna()
                    original_variances.append(np.mean((x - x.mean()) ** 2))
                denominator = np.sqrt(np.mean(original_variances))
                same(denominator, row.reference_pooled_sd, "Regional reference SD changed")
                same((means[0] - means[1]) / denominator if denominator > 0 else np.nan, row.smd, "Regional fixed-reference SMD changed")
                continuous_checks += 3
        summaries.append(dict(matching=matching, common_cells=len(common), supported_cases={region: int(common[region].sum()) for region in REGIONS}))
    return dict(passed=True, independent_score_comparisons=score_checks, independent_continuous_comparisons=continuous_checks,
                independent_categorical_comparisons=categorical_checks, common_support=summaries,
                scope="Common-cell standardization is descriptive; within-bin residual imbalance and support loss remain.")


def audit_water(reference: pd.DataFrame, cohort: set[str]) -> dict:
    work = reference.loc[reference.station_key.isin(cohort) & reference.region.isin(REGIONS)]
    work = work.drop_duplicates(["station_key", "year"]).dropna(subset=["air_h30_target_year", "eval_truth_h30"]).copy()
    work["period"] = np.where(work.year < 2010, "before_2010", "from_2010")
    summary = load_result("water_air_summary.csv")
    changes = load_result("water_air_paired_changes.csv")
    checks, point_estimates = 0, []
    for (region, period), block in work.groupby(["region", "period"]):
        require(block.station_key.nunique() == work.loc[work.region.eq(region)].station_key.nunique(), "Water station composition differs between periods")
        for centering in ("pooled", "within_station_period"):
            x, y = block.air_h30_target_year, block.eval_truth_h30
            if centering == "within_station_period":
                x = x - block.groupby("station_key").air_h30_target_year.transform("mean")
                y = y - block.groupby("station_key").eval_truth_h30.transform("mean")
            else:
                x, y = x - x.mean(), y - y.mean()
            slope = float(x @ y / (x @ x))
            correlation = float(x @ y / np.sqrt((x @ x) * (y @ y)))
            residual_sd = float(np.sqrt(np.mean((y - slope * x) ** 2)))
            saved = summary.loc[summary.region.eq(region) & summary.period.eq(period) & summary.centering.eq(centering)]
            require(saved.n.eq(len(block)).all(), "Water unique station-year denominator changed")
            same(saved.slope, slope, "Direct water slope differs")
            same(saved.correlation, correlation, "Direct water correlation differs")
            same(saved.residual_sd, residual_sd, "Direct water residual SD differs")
            checks += 3 * len(saved)
            point_estimates.append(dict(region=region, period=period, centering=centering, n=len(block), slope=slope, correlation=correlation))
    # With two groups the paired cluster bootstrap has exactly three possible
    # compositions. Enumerate them directly instead of importing moment helpers.
    foen = work.loc[work.region.eq("foen")]
    groups = sorted(foen.independence_group.unique())
    require(len(groups) == 2, "FOEN no longer has the audited two-group scope")
    deltas = []
    for selected in [(groups[0], groups[0]), tuple(groups), (groups[1], groups[1])]:
        joined = pd.concat([foen.loc[foen.independence_group.eq(group)] for group in selected], ignore_index=True)
        fits = []
        for period in ("before_2010", "from_2010"):
            z = joined.loc[joined.period.eq(period)]
            x = z.air_h30_target_year - z.groupby("station_key").air_h30_target_year.transform("mean")
            y = z.eval_truth_h30 - z.groupby("station_key").eval_truth_h30.transform("mean")
            fits.append(float(x @ y / (x @ x)))
        deltas.append(fits[1] - fits[0])
    saved = changes.loc[changes.region.eq("foen") & changes.centering.eq("within_station_period") & changes.bootstrap_unit.eq("connected_group")].iloc[0]
    same([min(deltas), max(deltas)], [saved.slope_difference_low, saved.slope_difference_high], "FOEN exact cluster-composition endpoints differ")
    return dict(passed=True, direct_point_comparisons=checks, point_estimates=point_estimates,
                foen_exact_group_composition_slope_changes=deltas,
                foen_exact_cluster_endpoints=[min(deltas), max(deltas)],
                scope="Paired group bootstrap is coarse with two FOEN groups; annual maxima need not be concurrent, and no equivalence or daily-model stability is established.")


def regression_slope(years, values) -> float:
    """Independent first-degree least squares, converted to degrees/decade."""
    return float(np.polyfit(np.asarray(years, float), np.asarray(values, float), 1)[0] * 10)


def audit_time(reference: pd.DataFrame) -> dict:
    cases = forward(load_result("time_support_cases.csv"))
    audit = forward(load_result("time_support_archive_audit.csv"))
    decomposition = forward(load_result("time_support_error_decomposition.csv")).set_index("scheme")
    sensitivity = forward(load_result("time_support_zero_mask_sensitivity.csv")).set_index("scheme")
    require(len(cases) == 805 * 4 and cases.independence_group.nunique() == 17, "Time-support primary denominator changed")
    require(cases.groupby(PAIR).scheme.nunique().eq(4).all(), "Time-support schemes are not fully paired")
    same(cases.estimate_error, cases.truth_error + cases.reconstruction, "Casewise E = S + R fails", atol=1e-12)
    for scheme, part in cases.groupby("scheme"):
        mse = float(np.mean(part.estimate_error ** 2))
        year_mse = float(np.mean(part.truth_error ** 2))
        reconstruction_mse = float(np.mean(part.reconstruction ** 2))
        cross = float(2 * np.mean(part.truth_error * part.reconstruction))
        same([mse, year_mse, reconstruction_mse, cross], decomposition.loc[scheme, ["estimate_mse", "year_set_mse", "reconstruction_mse", "twice_cross_term"]].to_numpy(float), "Saved MSE decomposition differs", atol=1e-12)
        same(mse, year_mse + reconstruction_mse + cross, "Signed MSE identity fails", atol=1e-12)
        same(sensitivity.loc[scheme].estimate_rmse ** 2 * 807, mse * 805, "Zero-mask 807 sensitivity differs")
    zero = audit.loc[audit.original_common & ~audit.included]
    require(len(zero) == 2 and zero.design_mask_years.eq(0).all(), "807-to-805 exclusions differ")
    excluded = []
    for row in zero.itertuples(index=False):
        folder = BASE / "crossed/forward" / f"replicate_{row.replicate:02d}" / row.station_key.replace("|", "_")
        require(json.loads((folder / "design.json").read_text())["masks"] == {}, "Excluded archive actually has masks")
        require(row.saved_all_error == row.saved_warm90_error == 0, "Excluded no-mask archive has nonzero error")
        excluded.append(dict(station_key=row.station_key, replicate=int(row.replicate)))
    counts = cases.pivot(index=PAIR, columns="scheme", values="n_incomplete_kept")
    construction_identical = counts.warm90.eq(0) | counts.warm90.eq(counts["all"])
    require(int(construction_identical.sum()) == 337 and int((~construction_identical).sum()) == 468, "Selection opportunity denominators differ")
    selected_years = cases.pivot(index=PAIR, columns="scheme", values="retained_years")
    realized_identical = selected_years.warm90.eq(selected_years.random_same_count) & selected_years.warm90.eq(selected_years.time_balanced)
    lookup = {
        (family, station): part.drop_duplicates("year").set_index("year").eval_truth_h30.sort_index()
        for (family, station), part in reference.groupby(["design_family", "station_key"])
    }
    chosen = cases.loc[cases.scheme.eq("warm90")].sample(20, random_state=883)
    for row in chosen.itertuples(index=False):
        truth = lookup["crossed", row.station_key]
        truth = truth.loc[truth.index >= 2010]
        folder = BASE / "crossed/forward" / f"replicate_{row.replicate:02d}" / row.station_key.replace("|", "_")
        predictions = pd.read_parquet(folder / "annual_predictions.parquet", columns=["year", "D2"]).set_index("year")
        masks = json.loads((folder / "design.json").read_text())["masks"]
        point = truth.copy()
        for year in masks:
            point.loc[int(year)] = predictions.loc[int(year)].D2
        years = [int(year) for year in row.retained_years.split(";")]
        full = regression_slope(truth.index, truth)
        same(regression_slope(years, point.loc[years]) - full, row.estimate_error, "Independent raw archive estimate slope differs")
        same(regression_slope(years, truth.loc[years]) - full, row.truth_error, "Independent raw archive year-set slope differs")
    return dict(passed=True, actual_mask_archives=805, paired_scheme_rows=len(cases), connected_groups=17,
                source_archive_slope_recomputations=len(chosen), sample_seed=883, zero_mask_exclusions=excluded,
                identical_by_construction=int(construction_identical.sum()), selection_opportunity=int((~construction_identical).sum()),
                realized_identical_same_count_year_sets=int(realized_identical.sum()),
                scope="337 counts identical rules by construction; 362 observed identical selections additionally include chance agreement. Year count and position are not separately identified.")


def audit_gaps(cohort: set[str]) -> dict:
    saved = load_result("gap_annual_longest_cases.csv").set_index(["family", "station_key", "replicate", "year"])
    comparison = load_result("gap_common_statistic_comparison.csv")
    annual_rows, design_hash = [], hashlib.sha256()
    n_designs = 0
    for family in ("calendar", "crossed"):
        for path in sorted((BASE / family / "forward").glob("replicate_*/*/design.json")):
            design = json.loads(path.read_text())
            design_hash.update(str(path.relative_to(ROOT)).encode())
            design_hash.update(hashlib.sha256(path.read_bytes()).digest())
            n_designs += 1
            for year, spec in design["masks"].items():
                year = int(year)
                missing = np.zeros(366 if calendar.isleap(year) else 365, dtype=bool)
                for span in spec.split(";"):
                    start, length = map(int, span.split(":"))
                    require(start >= 0 and length > 0 and start + length <= len(missing), "Original missing span extends outside its year")
                    missing[start:start + length] = True
                edges = np.diff(np.r_[False, missing, False].astype(int))
                lengths = np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)
                key = (family, design["station_key"], int(design["replicate"]), year)
                row = saved.loc[key]
                require(row.longest_run == max(lengths) and row.n_runs == len(lengths), "Daily boolean-mask longest run or gap count differs")
                annual_rows.append(dict(family=family, station_key=design["station_key"], year=year, longest_run=int(max(lengths))))
    annual = pd.DataFrame(annual_rows)
    require(len(annual) == len(saved) == 7583, "Expected 7,583 independent daily-mask reconstructions")
    primary = comparison.loc[comparison.primary_comparison].set_index("source")
    for family, part in annual.groupby("family"):
        row = primary.loc[family]
        same([len(part), part.longest_run.median(), part.longest_run.quantile(.9), part.longest_run.ge(30).mean()],
             [row.n, row.median_annual_longest, row.p90_annual_longest, row.share_annual_ge30], "Independent trial gap summary differs")
    observed = pd.read_csv(ELIGIBLE)
    observed = observed.loc[observed.station_key.isin(cohort) & ~observed.complete_year]
    require(len(observed) == 220 and (~observed.edge_year & observed.fully_active).all(), "Observed gap cohort includes edge or partial-active years")
    for period, part in [("1981-2025", observed.loc[observed.year.between(1981, 2025)]),
                         ("2010-2025", observed.loc[observed.year.between(2010, 2025)])]:
        row = comparison.loc[comparison.source.eq("observed") & comparison.period.eq(period)].iloc[0]
        same([len(part), part.longest_run.median(), part.longest_run.ge(30).mean()],
             [row.n, row.median_annual_longest, row.share_annual_ge30], "Independent observed gap summary differs")
    return dict(passed=True, raw_design_files=n_designs, raw_design_set_sha256=design_hash.hexdigest(),
                explicit_daily_mask_reconstructions=len(annual), observed_incomplete_station_years=len(observed),
                scope="Longest contiguous annual run uses one common metric; observations and repeated masks retain distinct row weights. Shared years do not establish same-day outages.")


def audit_archive_counts(reference: pd.DataFrame, cohort: set[str]) -> dict:
    unique = reference.groupby("station_key").year.nunique()
    training = reference.drop_duplicates("station_key").set_index("station_key").n_complete_years
    saved = load_result("archive_complete_year_count_audit.csv").set_index("station_key")
    require(len(unique) == len(saved) == 581, "Archive source station denominator changed")
    same(saved.loc[unique.index].unique_complete_station_years, unique, "Unique complete station-year counts differ")
    same(unique - training.reindex(unique.index), 1, "Held-out-year difference is not one at every station")
    summary = load_result("archive_comparison.csv").set_index("panel")
    in_cohort = unique.index.isin(cohort)
    cohort_median, rest_median = float(unique.loc[in_cohort].median()), float(unique.loc[~in_cohort].median())
    same([cohort_median, rest_median], [summary.loc["trend_cohort"].median_complete_years,
                                      summary.loc["source_remainder"].median_complete_years], "Archive median complete-year counts differ")
    return dict(passed=True, unique_source_stations=len(unique), cohort_stations=int(in_cohort.sum()),
                cohort_median_complete_years=cohort_median, remainder_median_complete_years=rest_median,
                scope="Unique complete station-years include the held-out year; donor summaries retain leave-one-year-out provenance.")


def audit_trajectory() -> dict:
    cases = load_result("trajectory_revision_nested_cases.csv")
    old = pd.read_csv(ORIGINAL_TRAJECTORY).set_index(["station_key", "year", "count"]).sort_index()
    seed_zero = cases.loc[cases.seed.eq(0)].set_index(["station_key", "year", "count"]).sort_index()
    require(seed_zero.index.equals(old.index), "Trajectory seed-zero original case identities differ")
    same(seed_zero[["q05", "q50", "q95"]], old[["q05", "q50", "q95"]], "Original trajectory case quantiles differ", atol=1e-8)
    manifest = load_result("trajectory_revision_frozen_manifest.csv").set_index(["station_key", "year"])
    draws = pd.read_parquet(OUT / "trajectory_revision_h30_draws.parquet")
    lookup = cases.set_index(["seed", "station_key", "year", "count"])
    require(len(cases) == 243 and set(cases.seed) == {0, 1, 2}, "Trajectory seed/case/budget count differs")
    require(cases.groupby(["station_key", "year"]).input_sha256.nunique().eq(1).all(), "Trajectory daily inputs vary by seed")
    checked = 0
    for row in draws.itertuples(index=False):
        source = manifest.loc[(row.station_key, row.year)]
        values = np.asarray(row.h30_draws, float)
        require(len(values) == 500 and np.isfinite(values).all(), "Trajectory full sample is not 500 finite draws")
        for count in (20, 100, 500):
            projected = np.maximum(values[:count], source.bound) if np.isfinite(source.bound) else values[:count]
            q05, q50, q95 = np.quantile(projected, [.05, .5, .95])
            # Sample CRPS identity using sorted ranks, independent of the scorer.
            ordered = np.sort(projected)
            crps = np.mean(abs(projected - source.truth)) - np.dot(2 * np.arange(1, count + 1) - count - 1, ordered) / count ** 2
            covered = float(q05 - 1e-8 <= source.truth <= q95 + 1e-8)
            saved = lookup.loc[(row.seed, row.station_key, row.year, count)]
            same([q05, q50, q95, q95 - q05, covered, crps], saved[["q05", "q50", "q95", "width90", "coverage90", "crps"]].to_numpy(float), "Nested prefix trajectory score differs")
            checked += 1
    status = json.loads((OUT / "trajectory_revision_report.json").read_text())["source_calibration"]
    require(status["source_role_offsets_reestimated"] is False and status["source_role_calibration_sensitivity_executed"] is False,
            "Trajectory report implies unexecuted source-role calibration")
    return dict(passed=True, original_seed_zero_case_budgets=len(seed_zero), independently_rescored_nested_prefixes=checked,
                seeds=[0, 1, 2], source_role_offsets_reestimated=False,
                scope="This 962 audit covers uncalibrated nested prefixes only. Source-role recalibration is the separate 968 experiment; 500 paths still do not establish convergence or fine ranking robustness.")


def main() -> int:
    columns = ["station_key", "year", "region", "independence_group", "design_family", "eval_truth_h30", "air_h30_target_year", "n_complete_years"]
    reference = pd.read_parquet(REFERENCE, columns=columns)
    trends = pd.read_csv(BASE / "trends.csv", usecols=["station_key", "mode"])
    forward_cohort = set(trends.loc[trends["mode"].eq("forward"), "station_key"])
    audited_results = [
        "region_standardized.csv", "region_support_loss.csv", "region_balance_continuous.csv", "region_balance_categorical.csv",
        "water_air_summary.csv", "water_air_paired_changes.csv", "time_support_cases.csv", "time_support_archive_audit.csv",
        "time_support_error_decomposition.csv", "time_support_zero_mask_sensitivity.csv", "gap_annual_longest_cases.csv",
        "gap_common_statistic_comparison.csv", "archive_complete_year_count_audit.csv", "archive_comparison.csv",
        "trajectory_revision_nested_cases.csv", "trajectory_revision_frozen_manifest.csv", "trajectory_revision_h30_draws.parquet",
        "trajectory_revision_report.json",
    ]
    report = {
        "status": "passed", "script": str(Path(__file__).resolve().relative_to(ROOT)),
        "method": "Independent formulas on raw saved inputs; no analysis-generator functions imported; no model refit.",
        "inputs": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in [RAW_CASES, REFERENCE, ELIGIBLE, BASE / "trends.csv", ORIGINAL_TRAJECTORY]},
        "audited_result_sha256": {str((OUT / name).relative_to(ROOT)): hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in audited_results},
        "regional_standardization": audit_regions(),
        "annual_water_air": audit_water(reference, set(trends.station_key)),
        "time_support": audit_time(reference),
        "annual_longest_gaps": audit_gaps(forward_cohort),
        "archive_complete_year_counts": audit_archive_counts(reference, set(trends.station_key)),
        "trajectory_budget": audit_trajectory(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT / "independent_audit.json"
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "report": str(destination.relative_to(ROOT)),
                      "daily_masks_checked": report["annual_longest_gaps"]["explicit_daily_mask_reconstructions"],
                      "archive_slopes_checked": report["time_support"]["source_archive_slope_recomputations"],
                      "nested_prefixes_checked": report["trajectory_budget"]["independently_rescored_nested_prefixes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

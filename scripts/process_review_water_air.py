#!/usr/bin/env python3
"""Annual pooled and station-by-period water--air H30 associations.

Reuses unique observed complete station-years from the saved leave-one-year-out
reference panel. Both annual maxima are computed separately; annual association
does not test coincident daily peaks or missing-period reconstruction stability.
"""
from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet"
COHORT = ROOT / "results/wrr_review_response_20261027/whole_archive/trends.csv"
OUT = ROOT / "results/wrr_process_revision_20261029"
PAPER = ROOT / "paper/wrr_tr"
BOOT = 10000
SEED = 20261029
PERIODS = ("before_2010", "from_2010")
CENTERINGS = ("pooled", "within_station_period")
MOMENTS = ["n", "sx", "sy", "sxx", "syy", "sxy", "wxx", "wyy", "wxy",
           "cx", "cy", "cxx", "cyy", "cxy"]


def deduplicate_complete_years(seed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reject conflicting duplicate values, including missing/finite conflicts.

    A mask replicate is not an additional observed year. Missing metadata or
    inconsistent station membership must not disappear inside pandas groupby.
    """
    identity = ["station_key", "year", "region", "independence_group"]
    if seed[identity].isna().any().any():
        raise ValueError("Missing station-year identity or connected-group metadata")
    if not np.isfinite(seed.year.to_numpy(float)).all() or not seed.year.eq(seed.year.astype(int)).all():
        raise ValueError("Reference years must be finite integers")
    if seed.groupby("station_key")[["region", "independence_group"]].nunique(dropna=False).gt(1).any().any():
        raise ValueError("Station region or connected-group membership is inconsistent")
    values = ["eval_truth_h30", "air_h30_target_year"]
    if seed.groupby(["station_key", "year"])[values].nunique(dropna=False).gt(1).any().any():
        raise ValueError("Inconsistent duplicate complete-year reference values, including missingness")
    counts = seed.groupby(["station_key", "year"]).size()
    unique = seed.drop_duplicates(["station_key", "year"]).copy()
    unique["mask_rows"] = [int(counts.loc[(s, y)]) for s, y in zip(unique.station_key, unique.year)]
    unique["period"] = np.where(unique.year < 2010, PERIODS[0], PERIODS[1])
    audit = unique[identity + ["period", "mask_rows"]].copy()
    audit["finite_water"] = np.isfinite(unique.eval_truth_h30.to_numpy(float))
    audit["finite_air"] = np.isfinite(unique.air_h30_target_year.to_numpy(float))
    audit["included"] = audit.finite_water & audit.finite_air
    audit["exclusion_reason"] = np.select(
        [~audit.finite_water & ~audit.finite_air, ~audit.finite_water, ~audit.finite_air],
        ["nonfinite_air_and_water", "nonfinite_water", "nonfinite_air"], default="included")
    work = unique.loc[audit.included, [*identity, *values, "period"]].copy()
    return work, audit


def load_complete_years(*, return_audit: bool = False) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    columns = ["station_key", "year", "region", "independence_group", "eval_truth_h30", "air_h30_target_year"]
    seed = pd.read_parquet(SOURCE, columns=columns)
    cohort = pd.read_csv(COHORT, usecols=["station_key", "region"]).drop_duplicates()
    if cohort.groupby("station_key").region.nunique(dropna=False).gt(1).any():
        raise ValueError("Cohort station region is inconsistent")
    cohort = cohort.loc[cohort.region.isin(["foen", "gkd_bayern"])].set_index("station_key")
    seed = seed.loc[seed.station_key.isin(cohort.index)].copy()
    if set(seed.station_key) != set(cohort.index):
        raise ValueError("A regional cohort station has no complete-year reference rows")
    if not seed.region.eq(seed.station_key.map(cohort.region)).all():
        raise ValueError("Source station region disagrees with the cohort roster")
    work, audit = deduplicate_complete_years(seed)
    return (work, audit) if return_audit else work


def station_moments(work: pd.DataFrame) -> pd.DataFrame:
    """Sufficient statistics retain each station-period's own centering."""
    if work.duplicated(["station_key", "year"]).any():
        raise ValueError("Water-air fits require unique station-years")
    if work[["region", "station_key", "independence_group", "period"]].isna().any().any():
        raise ValueError("Missing station or period metadata")
    if work.groupby("station_key")[["region", "independence_group"]].nunique().gt(1).any().any():
        raise ValueError("Station membership is inconsistent")
    if not np.isfinite(work[["air_h30_target_year", "eval_truth_h30"]].to_numpy(float)).all():
        raise ValueError("Water-air fitting requires finite paired observations")
    if set(work.period) != set(PERIODS):
        raise ValueError("Both before/from-2010 periods are required")
    anchors = work.groupby(["region", "period"])[["air_h30_target_year", "eval_truth_h30"]].mean()
    rows = []
    for (region, station, group, period), block in work.groupby(
        ["region", "station_key", "independence_group", "period"]
    ):
        x = block.air_h30_target_year.to_numpy(float)
        y = block.eval_truth_h30.to_numpy(float)
        xc, yc = x - x.mean(), y - y.mean()
        anchor = anchors.loc[(region, period)]
        xp, yp = x - anchor.air_h30_target_year, y - anchor.eval_truth_h30
        rows.append(dict(
            region=region, station_key=station, independence_group=group, period=period,
            year_min=int(block.year.min()), year_max=int(block.year.max()), n=len(block),
            sx=x.sum(), sy=y.sum(), sxx=x @ x, syy=y @ y, sxy=x @ y,
            wxx=xc @ xc, wyy=yc @ yc, wxy=xc @ yc,
            cx=xp.sum(), cy=yp.sum(), cxx=xp @ xp, cyy=yp @ yp, cxy=xp @ yp,
            pooled_air_origin=anchor.air_h30_target_year, pooled_water_origin=anchor.eval_truth_h30,
            air_h30_mean=x.mean(), water_h30_mean=y.mean(),
        ))
    return pd.DataFrame(rows)


def fit_moments(moment: np.ndarray, centering: str) -> dict[str, np.ndarray]:
    """Fit original or bootstrap moment totals, with a population residual SD."""
    moment = np.asarray(moment, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        n = moment[..., 0]
        if centering == "pooled":
            # The additional moment columns use a shared region-period origin,
            # avoiding cancellation of large, nearly equal raw second moments.
            sx, sy, sxx, syy, sxy = [moment[..., i] for i in (range(9, 14) if moment.shape[-1] >= 14 else range(1, 6))]
            xx, yy, xy = sxx - sx ** 2 / n, syy - sy ** 2 / n, sxy - sx * sy / n
        elif centering == "within_station_period":
            xx, yy, xy = [moment[..., i] for i in [6, 7, 8]]
        else:
            raise ValueError(f"Unknown centering: {centering}")
        slope = np.where((n > 0) & (xx > 0), xy / xx, np.nan)
        correlation = np.where((n > 0) & (xx > 0) & (yy > 0), xy / np.sqrt(xx * yy), np.nan)
        residual_sd = np.where((n > 0) & (xx > 0), np.sqrt(np.maximum(yy - xy ** 2 / xx, 0) / n), np.nan)
    return {"slope": slope, "correlation": correlation, "residual_sd": residual_sd}


def paired_analysis(work: pd.DataFrame, bootstraps: int = BOOT, seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Resample the same groups or stations in both periods, preserving pairing.

    The group analysis is primary because source stations can share connected
    networks. Station resampling is a sensitivity analysis; it treats stations
    as independent. No annual rows are sampled independently.
    """
    moments = station_moments(work)
    if bootstraps < 1:
        raise ValueError("At least one bootstrap draw is required")
    summaries, differences = [], []
    rng = np.random.default_rng(seed)
    for region, region_moments in moments.groupby("region", sort=True):
        for unit, field in [("connected_group", "independence_group"), ("station", "station_key")]:
            units = np.array(sorted(region_moments[field].unique()))
            multiplicity = rng.multinomial(len(units), np.full(len(units), 1 / len(units)), size=bootstraps)
            fits = {}
            for period in PERIODS:
                part = region_moments.loc[region_moments.period.eq(period)]
                totals = part.groupby(field)[MOMENTS].sum().reindex(units, fill_value=0).to_numpy(float)
                estimate = totals.sum(axis=0)
                draws = multiplicity @ totals
                for centering in CENTERINGS:
                    point = fit_moments(estimate, centering)
                    if not all(np.isfinite(value) for value in point.values()):
                        raise ValueError(f"Undefined water-air association (zero variance or empty period): {region}, {period}, {centering}")
                    simulated = fit_moments(draws, centering)
                    fits[(period, centering)] = (point, simulated)
                    row = dict(
                        region=region, period=period, centering=centering, bootstrap_unit=unit,
                        n=int(part.n.sum()), stations=int(part.station_key.nunique()),
                        groups=int(part.independence_group.nunique()), bootstrap_units=len(units),
                        bootstrap_draws=bootstraps, informative_within_stations=int(part.wxx.gt(0).sum()),
                        year_min=int(part.year_min.min()), year_max=int(part.year_max.max()),
                    )
                    for metric in point:
                        finite = np.isfinite(simulated[metric])
                        row[metric] = float(point[metric])
                        row[f"{metric}_low"], row[f"{metric}_high"] = np.quantile(simulated[metric][finite], [.025, .975]) if finite.any() else (np.nan, np.nan)
                        row[f"{metric}_valid_draws"] = int(finite.sum())
                    summaries.append(row)
            for centering in CENTERINGS:
                before, after = fits[(PERIODS[0], centering)], fits[(PERIODS[1], centering)]
                station_periods = region_moments.groupby("station_key").period.nunique()
                group_periods = region_moments.groupby("independence_group").period.nunique()
                row = dict(
                    region=region, centering=centering, bootstrap_unit=unit,
                    contrast="from_2010 minus before_2010", stations=region_moments.station_key.nunique(),
                    groups=region_moments.independence_group.nunique(),
                    stations_both_periods=int(station_periods.eq(2).sum()),
                    groups_both_periods=int(group_periods.eq(2).sum()),
                    bootstrap_units=len(units), bootstrap_draws=bootstraps,
                )
                for metric in before[0]:
                    delta = after[1][metric] - before[1][metric]
                    finite = np.isfinite(delta)
                    row[f"{metric}_difference"] = float(after[0][metric] - before[0][metric])
                    row[f"{metric}_difference_low"], row[f"{metric}_difference_high"] = np.quantile(delta[finite], [.025, .975]) if finite.any() else (np.nan, np.nan)
                    row[f"{metric}_valid_draws"] = int(finite.sum())
                differences.append(row)
    return pd.DataFrame(summaries), pd.DataFrame(differences), moments


def write_tex(summary: pd.DataFrame, differences: pd.DataFrame) -> None:
    lines = [
        r"\begin{table}[t]\centering\small",
        r"\caption{Annual water--air H30 associations in unique complete station-years. Years and slopes are shown before/from 2010; S/G counts stations/connected groups. Within estimates center both variables within station and period. Slopes and correlations pool the centered annual observations, rather than averaging station coefficients. The paired 95\% percentile intervals resample the same connected groups in both periods; only two FOEN groups and eight Bavaria groups are available, so these intervals are descriptive and coarse. Station-resampling sensitivity results are saved separately.}",
        r"\label{tab:water-air-within}", r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrrr}", r"\toprule",
        r"Region & Fit & Years & S/G & Slopes & $\Delta b$ [95\% interval] \\", r"\midrule",
    ]
    macros = []
    for region, title, rtag in [("foen", "FOEN", "Foen"), ("gkd_bayern", "Bavaria", "Bavaria")]:
        for centering, label, ctag in [("pooled", "Pooled", "Pooled"), ("within_station_period", "Within", "Within")]:
            part = summary.loc[summary.region.eq(region) & summary.centering.eq(centering) & summary.bootstrap_unit.eq("connected_group")].set_index("period")
            delta = differences.loc[differences.region.eq(region) & differences.centering.eq(centering) & differences.bootstrap_unit.eq("connected_group")].iloc[0]
            before, after = part.loc[PERIODS[0]], part.loc[PERIODS[1]]
            lines.append(
                f"{title} & {label} & {int(before.n)}/{int(after.n)} & {int(delta.stations)}/{int(delta.groups)} & "
                f"{before.slope:.3f}/{after.slope:.3f} & {delta.slope_difference:+.3f} [{delta.slope_difference_low:+.3f}, {delta.slope_difference_high:+.3f}] " + r"\\"
            )
            for row, ptag in [(before, "Before"), (after, "After")]:
                for metric, mtag, digits in [("slope", "Slope", 3), ("correlation", "Corr", 3), ("n", "N", 0), ("stations", "Stations", 0), ("groups", "Groups", 0)]:
                    macros.append(r"\newcommand{\PRW" + rtag + ctag + ptag + mtag + "}{" + f"{row[metric]:.{digits}f}" + "}")
            for metric, mtag in [("slope", "Slope"), ("correlation", "Corr")]:
                for suffix, stag in [("difference", "Delta"), ("difference_low", "DeltaLow"), ("difference_high", "DeltaHigh")]:
                    macros.append(r"\newcommand{\PRW" + rtag + ctag + mtag + stag + "}{" + f"{delta[metric+'_'+suffix]:.3f}" + "}")
    lines += [
        r"\bottomrule\end{tabular}}",
        r"\par\footnotesize The air and water H30 maxima need not refer to the same dates. Similar annual within slopes do not establish stable daily residuals, hidden-peak timing, tails or autocorrelation, and are not an equivalence test.",
        r"\end{table}",
    ]
    correlations = [
        r"\begin{table}[t]\centering\small",
        r"\caption{Annual water--air correlations and paired changes. Intervals use connected-group resampling, as in Table~\ref{tab:water-air-within}. Correlations describe annual H30 associations at the stated aggregation scale.}",
        r"\label{tab:water-air-correlation}", r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrr}", r"\toprule",
        r"Region & Fit & $r_{<2010}$ & $r_{\geq2010}$ & $\Delta r$ [95\% interval] \\", r"\midrule",
    ]
    for row in differences.query("bootstrap_unit == 'connected_group'").itertuples(index=False):
        part = summary.loc[summary.region.eq(row.region) & summary.centering.eq(row.centering) & summary.bootstrap_unit.eq("connected_group")].set_index("period")
        title = "FOEN" if row.region == "foen" else "Bavaria"
        label = "Pooled" if row.centering == "pooled" else "Within"
        correlations.append(f"{title} & {label} & {part.loc[PERIODS[0]].correlation:.3f} & {part.loc[PERIODS[1]].correlation:.3f} & {row.correlation_difference:+.3f} [{row.correlation_difference_low:+.3f}, {row.correlation_difference_high:+.3f}] " + r"\\")
    correlations += [r"\bottomrule\end{tabular}}", r"\end{table}"]
    sensitivity = [
        r"\begin{table}[t]\centering\small",
        r"\caption{Paired resampling sensitivity for within-station annual water--air H30 changes (from 2010 minus before 2010). Each resample carries both periods of a selected group or station. Connected groups are the primary sampling unit; station resampling assumes independence across stations. Neither percentile interval establishes equivalence, and FOEN group intervals have only three distinct possible compositions.}",
        r"\label{tab:water-air-paired-sensitivity}", r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrr}", r"\toprule",
        r"Region & Unit & $n$ & $\Delta b$ [95\% interval] & $\Delta r$ [95\% interval] \\", r"\midrule",
    ]
    for row in differences.query("centering == 'within_station_period'").itertuples(index=False):
        title = "FOEN" if row.region == "foen" else "Bavaria"
        label = "Group" if row.bootstrap_unit == "connected_group" else "Station"
        sensitivity.append(f"{title} & {label} & {row.bootstrap_units} & {row.slope_difference:+.3f} [{row.slope_difference_low:+.3f}, {row.slope_difference_high:+.3f}] & {row.correlation_difference:+.3f} [{row.correlation_difference_low:+.3f}, {row.correlation_difference_high:+.3f}] " + r"\\")
    sensitivity += [r"\bottomrule\end{tabular}}", r"\end{table}"]
    for name, content in [("process_water_revision_table.tex", lines), ("process_water_revision_correlation.tex", correlations), ("process_water_revision_uncertainty.tex", sensitivity), ("process_water_revision_values.tex", macros)]:
        (PAPER / name).write_text("\n".join(content) + "\n")


def main() -> int:
    global OUT, PAPER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--paper", type=Path, default=PAPER, help="Destination of generated TeX inputs")
    args = parser.parse_args()
    OUT, PAPER = args.output, args.paper
    OUT.mkdir(parents=True, exist_ok=True)
    PAPER.mkdir(parents=True, exist_ok=True)
    work, denominator_audit = load_complete_years(return_audit=True)
    denominator_audit.to_csv(OUT / "water_air_denominator_audit.csv", index=False)
    summary, differences, moments = paired_analysis(work)
    for name, table in [("water_air_complete_years", work), ("water_air_summary", summary), ("water_air_paired_changes", differences), ("water_air_station_period_moments", moments)]:
        table.to_csv(OUT / f"{name}.csv", index=False)
    write_tex(summary, differences)
    report = {
        "scope": "Descriptive annual pooled and station-by-period centered water--air H30 association in the existing whole-archive cohort's complete reference station-years.",
        "denominator": "Unique station_key-year; duplicate gap masks do not contribute additional annual observations. Finite air and water H30 required.",
        "denominator_counts": {"raw_mask_rows": int(denominator_audit.mask_rows.sum()), "unique_station_years": len(denominator_audit), "included_station_years": int(denominator_audit.included.sum()), "excluded_nonfinite_station_years": int((~denominator_audit.included).sum())},
        "duplicate_validation": "Includes missing/finite disagreement and station region/group identity; conflicts fail rather than depending on row order.",
        "pooled_moment_arithmetic": "Pooled sums use a shared region-period origin to avoid raw-second-moment cancellation; original unshifted moments remain saved too.",
        "within_estimand": "Common annual-observation-weighted slope through station-by-period centered x and y; station intercepts and separate period means are removed.",
        "bootstrap": {"draws": BOOT, "seed": SEED, "primary": "Paired connected-group bootstrap, same sampled groups in both periods.", "sensitivity": "Paired station bootstrap; assumes stations are independent.", "interval": "Pointwise 95% percentile; descriptive, no equivalence margin or multiplicity adjustment.", "small_cluster_limit": "FOEN has two connected groups; Bavaria has eight. Group percentile intervals are coarse, especially with only two clusters; station intervals are not a cure for dependence."},
        "interpretation": "Within-station annual slope point estimates are close across periods; differences remain uncertain. Annual air and water maxima need not be concurrent and cannot confirm stable daily reconstruction errors, hidden peaks, tail errors or autocorrelation.",
        "input_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE, COHORT]},
    }
    (OUT / "water_air_revision_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(summary.query("bootstrap_unit == 'connected_group'").to_string(index=False))
    print(differences.query("bootstrap_unit == 'connected_group'").to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Calendar-gap geometry, 42-versus-581 comparison, and train-eval support.

Reuses saved whole-archive designs and source cases. Does not refit models or
open new stations.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/wrr_review_response_20261027/whole_archive"
CASES = ROOT / "results/wrr_adversarial_review_20261027/failure_strata/failure_strata_cases.parquet"
SEED = ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet"
OUT = ROOT / "results/wrr_process_revision_20261029"
PAPER = ROOT / "paper/wrr_tr"


def season(doy: int) -> str:
    if doy <= 59 or doy >= 335:
        return "DJF"
    if doy <= 151:
        return "MAM"
    if doy <= 243:
        return "JJA"
    return "SON"


def parse_segments(spec: str) -> list[tuple[int, int]]:
    segments = []
    for part in str(spec).split(";"):
        part = part.strip()
        if not part:
            continue
        start, length = part.split(":")
        segments.append((int(start), int(length)))
    return segments


def merged_gap_lengths(segments: list[tuple[int, int]]) -> list[int]:
    """Lengths of contiguous missing runs, joining overlapping/adjacent spans."""
    merged = []
    for start, length in sorted(segments):
        if length <= 0:
            raise ValueError("Gap lengths must be positive")
        stop = start + length
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))
    return [stop - start for start, stop in merged]


def gap_geometry() -> tuple[pd.DataFrame, pd.DataFrame]:
    station_rows = []
    sync_rows = []
    for family in ("calendar", "crossed"):
        for replicate in range(20):
            folder = BASE / family / "forward" / f"replicate_{replicate:02d}"
            if not folder.is_dir():
                continue
            group_year_stations: dict[tuple[str, int], set[str]] = {}
            group_size: dict[str, int] = {}
            for station_dir in sorted(folder.iterdir()):
                design_path = station_dir / "design.json"
                if not design_path.is_file():
                    continue
                design = json.loads(design_path.read_text())
                years = sorted(int(year) for year in design["masks"])
                year_set = set(years)
                lengths = []
                doys = []
                seasons = Counter()
                for spec in design["masks"].values():
                    for doy, length in parse_segments(spec):
                        lengths.append(length)
                        doys.append(doy)
                        seasons[season(doy)] += 1
                adjacent = sum(
                    1 for year in years if (year - 1) in year_set or (year + 1) in year_set
                )
                run = 1
                max_run = 1
                for earlier, later in zip(years, years[1:]):
                    if later == earlier + 1:
                        run += 1
                        max_run = max(max_run, run)
                    else:
                        run = 1
                group = design["independence_group"]
                group_size[group] = group_size.get(group, 0) + 1
                for year in years:
                    group_year_stations.setdefault((group, year), set()).add(design["station_key"])
                n_segments = len(lengths)
                station_rows.append(
                    dict(
                        family=family,
                        replicate=replicate,
                        station_key=design["station_key"],
                        region=design["region"],
                        independence_group=group,
                        n_incomplete=int(design["n_incomplete"]),
                        n_years=int(design["n_years"]),
                        n_segments=n_segments,
                        median_length=float(np.median(lengths)) if lengths else np.nan,
                        mean_length=float(np.mean(lengths)) if lengths else np.nan,
                        p90_length=float(np.quantile(lengths, 0.9)) if lengths else np.nan,
                        median_doy=float(np.median(doys)) if doys else np.nan,
                        frac_jja=seasons["JJA"] / n_segments if n_segments else np.nan,
                        frac_djf=seasons["DJF"] / n_segments if n_segments else np.nan,
                        share_length_ge_30=float(np.mean([length >= 30 for length in lengths])) if lengths else np.nan,
                        consecutive_pairs=int(sum(1 for a, b in zip(years, years[1:]) if b == a + 1)),
                        adjacent_year_fraction=adjacent / len(years) if years else np.nan,
                        max_consecutive=int(max_run),
                    )
                )
            shared = 0
            total = 0
            for stations in group_year_stations.values():
                total += len(stations)
                if len(stations) >= 2:
                    shared += len(stations)
            sync_rows.append(
                dict(
                    family=family,
                    replicate=replicate,
                    stations=sum(group_size.values()),
                    groups=len(group_size),
                    shared_year_fraction=shared / total if total else np.nan,
                    n_station_years=total,
                )
            )
    stations = pd.DataFrame(station_rows)
    sync = pd.DataFrame(sync_rows)
    summary_rows = []
    for family, block in stations.groupby("family"):
        shared = float(sync.loc[sync.family.eq(family), "shared_year_fraction"].mean())
        summary_rows.append(
            dict(
                family=family,
                n_station_replicates=int(len(block)),
                stations=int(block.station_key.nunique()),
                groups=int(block.independence_group.nunique()),
                median_incomplete_years=float(block.n_incomplete.median()),
                median_segment_length=float(block.median_length.median()),
                mean_segment_length=float(block.mean_length.mean()),
                p90_segment_length=float(block.p90_length.median()),
                median_doy=float(block.median_doy.median()),
                mean_jja_fraction=float(block.frac_jja.mean()),
                mean_djf_fraction=float(block.frac_djf.mean()),
                mean_share_length_ge_30=float(block.share_length_ge_30.mean()),
                median_consecutive_pairs=float(block.consecutive_pairs.median()),
                mean_adjacent_year_fraction=float(block.adjacent_year_fraction.mean()),
                median_max_consecutive=float(block.max_consecutive.median()),
                mean_shared_year_fraction=shared,
            )
        )
    return pd.DataFrame(summary_rows), stations


def archive_comparison() -> pd.DataFrame:
    seed = pd.read_parquet(
        SEED,
        columns=[
            "station_key",
            "year",
            "region",
            "independence_group",
            "n_complete_years",
            "statistic_class",
            "regulation_status",
            "n_visible_donors",
            "provider",
        ],
    )
    stations = seed.drop_duplicates("station_key").copy()
    # n_complete_years is the training count in a leave-one-year-out case.
    # The archive descriptor counts each complete station-year once across all
    # design families and mask repetitions, including the held-out year.
    unique_years = seed.groupby("station_key").year.nunique()
    stations["training_complete_years"] = stations.n_complete_years
    stations["n_complete_years"] = stations.station_key.map(unique_years)
    trend_keys = set(
        pd.read_csv(BASE / "trends.csv", usecols=["station_key"]).station_key.unique()
    )
    stations["panel"] = np.where(stations.station_key.isin(trend_keys), "trend_cohort", "source_remainder")
    stations[["station_key", "panel", "training_complete_years", "n_complete_years"]].rename(
        columns={"n_complete_years": "unique_complete_station_years"}
    ).to_csv(OUT / "archive_complete_year_count_audit.csv", index=False)
    rows = []
    for panel, block in stations.groupby("panel"):
        rows.append(
            dict(
                panel=panel,
                stations=int(len(block)),
                groups=int(block.independence_group.nunique()),
                regions=int(block.region.nunique()),
                median_complete_years=float(block.n_complete_years.median()),
                mean_complete_years=float(block.n_complete_years.mean()),
                bavaria=int(block.region.eq("gkd_bayern").sum()),
                foen=int(block.region.eq("foen").sum()),
                usgs=int(block.region.str.startswith("usgs").sum()),
                unmatched_gages=int(block.regulation_status.eq("unmatched_gages").sum()),
                regulated=int(block.regulation_status.eq("regulated").sum()),
                unregulated=int(block.regulation_status.eq("unregulated").sum()),
                daily_mean=int(block.statistic_class.eq("daily_mean").sum()),
                median_visible_donors=float(block.n_visible_donors.median()),
                complete_year_count_definition="unique complete station-years, including held-out year",
                donor_count_source="leave-one-year-out cases, not forward controlled gaps",
            )
        )
    return pd.DataFrame(rows).sort_values("panel", key=lambda s: s.map({"trend_cohort": 0, "source_remainder": 1}))


def train_eval_support() -> pd.DataFrame:
    frame = pd.read_parquet(
        CASES,
        columns=[
            "region",
            "station_key",
            "independence_group",
            "policy_choice",
            "family",
            "mode",
            "hist_reconstructor_oof_daily_bias",
            "hist_historical_mask_h30_bias",
            "hist_historical_mask_h30_abs90",
            "air_warm_z_mean",
            "train_h30_mean",
            "D2",
            "reference_h30",
        ],
    )
    frame = frame.loc[
        frame.family.eq("crossed")
        & frame["mode"].eq("forward")
        & frame.region.isin(["gkd_bayern", "foen"])
        & frame.reference_h30.notna()
        & frame.D2.notna()
    ].copy()
    frame["eval_bias"] = frame.D2 - frame.reference_h30
    rows = []
    for (region, policy), block in frame.groupby(["region", "policy_choice"]):
        stations = block.drop_duplicates("station_key")
        rows.append(
            dict(
                region=region,
                policy_choice=policy,
                n=int(len(block)),
                stations=int(block.station_key.nunique()),
                groups=int(block.independence_group.nunique()),
                hist_daily_bias=float(stations.hist_reconstructor_oof_daily_bias.mean()),
                hist_mask_h30_bias=float(block.hist_historical_mask_h30_bias.mean()),
                hist_mask_h30_abs90=float(block.hist_historical_mask_h30_abs90.mean()),
                eval_bias=float(block.eval_bias.mean()),
                eval_mae=float(block.eval_bias.abs().mean()),
                air_warm_z=float(block.air_warm_z_mean.mean()),
                train_h30=float(stations.train_h30_mean.mean()),
                eval_h30=float(block.reference_h30.mean()),
                train_eval_h30_shift=float(block.reference_h30.mean() - stations.train_h30_mean.mean()),
            )
        )
    return pd.DataFrame(rows)


def observed_gaps() -> pd.DataFrame:
    trends = set(
        pd.read_csv(BASE / "trends.csv", usecols=["station_key"]).station_key.unique()
    )
    eligible = pd.read_csv(
        ROOT / "results/wrr_review_response_20261027/rules/eligible_station_years.csv"
    )
    eligible = eligible.loc[eligible.station_key.isin(trends)].copy()
    incomplete = eligible.loc[~eligible.complete_year].copy()
    adjacent = []
    for station, block in incomplete.groupby("station_key"):
        years = set(block.year.astype(int))
        for year in years:
            adjacent.append(int((year - 1) in years or (year + 1) in years))
    group_year_counts = incomplete.groupby(["independence_group", "year"]).station_key.transform(
        "nunique"
    )
    return pd.DataFrame(
        [
            dict(
                panel="observed_incomplete_years",
                stations_in_observation_archive=int(eligible.station_key.nunique()),
                stations_with_incomplete=int(incomplete.station_key.nunique()),
                incomplete_years=int(len(incomplete)),
                median_longest_run=float(incomplete.longest_run.median()),
                p90_longest_run=float(incomplete.longest_run.quantile(0.9)),
                share_run_ge_30=float((incomplete.longest_run >= 30).mean()),
                share_run_ge_60=float((incomplete.longest_run >= 60).mean()),
                share_run_ge_90=float((incomplete.longest_run >= 90).mean()),
                mean_adjacent_year_fraction=float(np.mean(adjacent)) if adjacent else np.nan,
                mean_shared_year_fraction=float((group_year_counts >= 2).mean()),
                share_julaug_complete=float(incomplete.julaug_complete.mean()),
                median_warm_observed_fraction=float(incomplete.warm_observed_fraction.median()),
            )
        ]
    )


def common_gap_comparison() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use the annual longest contiguous missing run for every source.

    Observed rows weight incomplete station-years equally. Trial rows weight
    incomplete station-year-replicates equally, preserving the actual mask
    sampling rather than pretending 20 repeats are independent observations.
    """
    trend_frame = pd.read_csv(BASE / "trends.csv", usecols=["station_key", "mode"])
    forward_keys = set(trend_frame.loc[trend_frame["mode"].eq("forward"), "station_key"])
    eligible = pd.read_csv(ROOT / "results/wrr_review_response_20261027/rules/eligible_station_years.csv")
    eligible = eligible.loc[eligible.station_key.isin(forward_keys)]
    if eligible.duplicated(["station_key", "year"]).any():
        raise RuntimeError("Observed archive must have unique station-year rows")
    observed = eligible.loc[~eligible.complete_year].copy()
    annual_rows = []
    for family in ("calendar", "crossed"):
        for path in sorted((BASE / family / "forward").glob("replicate_*/*/design.json")):
            design = json.loads(path.read_text())
            for year, spec in design["masks"].items():
                lengths = merged_gap_lengths(parse_segments(spec))
                if not lengths:
                    raise RuntimeError("A masked year must contain at least one gap")
                annual_rows.append(dict(family=family, station_key=design["station_key"],
                                        independence_group=design["independence_group"],
                                        replicate=int(design["replicate"]), year=int(year),
                                        longest_run=max(lengths), n_runs=len(lengths)))
    annual = pd.DataFrame(annual_rows)
    if annual.duplicated(["family", "station_key", "replicate", "year"]).any():
        raise RuntimeError("Trial mask rows are not unique station-year-repliclicates")
    rows = []

    def record(source, period, part, unit, weight):
        group_year_cols = ["independence_group", "year"]
        if source != "observed":
            group_year_cols.insert(0, "replicate")
        shared = part.groupby(group_year_cols).station_key.transform("nunique").ge(2)
        return dict(source=source, period=period, primary_comparison=period == "2010-2025",
                    unit=unit, weight=weight, n=len(part), stations=int(part.station_key.nunique()),
                    groups=int(part.independence_group.nunique()),
                    archive_stations=int(len(forward_keys)),
                    unique_station_years=int(len(part[["station_key", "year"]].drop_duplicates())),
                    replicates=int(part.replicate.nunique()) if source != "observed" else 1,
                    median_annual_longest=float(part.longest_run.median()),
                    p90_annual_longest=float(part.longest_run.quantile(.9)),
                    share_annual_ge30=float(part.longest_run.ge(30).mean()),
                    share_annual_ge60=float(part.longest_run.ge(60).mean()),
                    share_annual_ge90=float(part.longest_run.ge(90).mean()),
                    shared_year_fraction=float(shared.mean()),
                    shared_year_definition="at least two stations in the connected group have missingness in the same year; dates need not coincide")

    for period, part in [("2010-2025", observed.loc[observed.year.between(2010, 2025)]),
                         ("1981-2025", observed.loc[observed.year.between(1981, 2025)])]:
        rows.append(record("observed", period, part, "incomplete_station_year", "equal incomplete station-year"))
    for family, part in annual.groupby("family"):
        if not part.year.between(2010, 2025).all():
            raise RuntimeError("Forward mask comparison extends outside 2010-2025")
        rows.append(record(family, "2010-2025", part, "incomplete_station_year_replicate",
                           "equal incomplete station-year-replicate; 20 repeated masks retained"))
    return pd.DataFrame(rows), annual


def write_gap_tex(comparison: pd.DataFrame, archive: pd.DataFrame):
    primary = comparison.loc[comparison.primary_comparison].set_index("source")
    historic = comparison.loc[comparison.source.eq("observed") & ~comparison.primary_comparison].iloc[0]
    archive = archive.set_index("panel")
    macros = {"PGRObservedN": int(primary.loc["observed"].n),
              "PGRObservedStations": int(primary.loc["observed"].stations),
              "PGRArchiveStations": int(primary.loc["observed"].archive_stations),
              "PGRObservedMedian": f"{primary.loc['observed'].median_annual_longest:.0f}",
              "PGRObservedLongThirty": f"{100*primary.loc['observed'].share_annual_ge30:.2f}",
              "PGRCalendarN": int(primary.loc["calendar"].n),
              "PGRCalendarMedian": f"{primary.loc['calendar'].median_annual_longest:.0f}",
              "PGRCalendarLongThirty": f"{100*primary.loc['calendar'].share_annual_ge30:.2f}",
              "PGRControlledN": int(primary.loc["crossed"].n),
              "PGRControlledMedian": f"{primary.loc['crossed'].median_annual_longest:.0f}",
              "PGRHistoricN": int(historic.n), "PGRHistoricMedian": f"{historic.median_annual_longest:.0f}",
              "PGRHistoricLongThirty": f"{100*historic.share_annual_ge30:.2f}",
              "PGRArchiveTrendComplete": f"{archive.loc['trend_cohort'].median_complete_years:.0f}",
              "PGRArchiveRestComplete": f"{archive.loc['source_remainder'].median_complete_years:.0f}"}
    (PAPER / "process_gap_revision_values.tex").write_text(
        "\n".join("\\newcommand{\\" + name + "}{" + str(value) + "}" for name, value in macros.items()) + "\n")
    names = {"observed": "Observed archive", "calendar": "Empirical calendar", "crossed": "Controlled gaps"}
    lines = [r"\begin{table}[t]\centering\small",
             r"\caption{Common annual-longest-gap comparison in 2010--2025. Each number describes the longest contiguous missing run within an incomplete year. Observations weight incomplete station-years equally; trial rows weight incomplete station-year--replicates equally, retaining all 20 mask replicates. Repetition and station composition differ, so this is descriptive rather than a same-distribution test.}",
             r"\label{tab:observed-gaps}",
             r"\begin{tabular}{lrrrrr}\toprule Source & Rows & Stations & Median (d) & 90th percentile (d) & $\geq30$ d \\\midrule"]
    for source in ("observed", "calendar", "crossed"):
        row = primary.loc[source]
        lines.append(f"{names[source]} & {int(row.n):,} & {int(row.stations)} & {row.median_annual_longest:.0f} & {row.p90_annual_longest:.1f} & {100*row.share_annual_ge30:.2f}\\% " + r"\\")
    lines += [r"\bottomrule\end{tabular}\end{table}"]
    (PAPER / "process_gap_revision_table.tex").write_text("\n".join(lines) + "\n")
    lines = [r"\subsection{Common gap metric and archive count audit}",
             r"The primary comparison uses 2010--2025 to match the forward experiment. The observed eligible archive covers 41 forward-cohort stations; only 29 have incomplete years in this period. There are 109 unique incomplete station-years, without artificial mask repetition. The empirical-calendar and controlled-gap summaries contain 3,806 and 3,777 incomplete station-year--replicate rows, respectively, across the same 41-station forward cohort. Their repeated appearances preserve experimental weighting and do not create new independent observations. All three summaries use each year's longest contiguous missing run, including unions of adjacent or overlapping missing spans.",
             f"As an additional historical description, the observed archive over 1981--2025 contains {int(historic.n)} incomplete station-years at {int(historic.stations)} stations; "
             + f"the median annual longest run is {historic.median_annual_longest:.0f} days and {100*historic.share_annual_ge30:.2f}\\% have a run of at least 30 days. "
             + r"This historical period is supplementary rather than the primary comparison to forward masks. The calendar masks are closer to common observed gap conditions on this metric, whereas 30--90-day controlled masks probe the long-gap tail; differing sampling and repeat weights preclude a same-distribution claim.",
             r"The shared-year fraction counts station-years in which at least one other station in the same connected group also has an incomplete year (within the same replicate for trial masks). It does not require overlapping missing days and therefore does not establish synchronous daily outages or unavailable donors on the same dates.",
             r"Complete-year counts in the cohort comparison count unique complete station-years in the leave-one-year-out source cases, including the held-out year. The previous 30/7 medians counted training years: every one of the 581 stations differs by exactly one year. Correct archive medians are 31/8. Visible-donor summaries derive from leave-one-year-out cases and describe that design, rather than the forward controlled-gap experiment."]
    (PAPER / "process_gap_revision_supporting.tex").write_text("\n\n".join(lines) + "\n")
    lines = [r"\begin{table}[t]\centering\small",
             r"\caption{Long-complete evaluation stations versus the remainder of the 581-station source archive. Complete-year counts are unique complete station-years, including the held-out year, rather than training-year counts. USGS counts follow named hydrologic-unit regions.}",
             r"\label{tab:archive-comparison}",
             r"\begin{tabular}{lrrrrrr}\toprule Panel & Stations & Groups & Median years & Bavaria & Switzerland & USGS \\\midrule"]
    for panel, label in [("trend_cohort", "Trend cohort"), ("source_remainder", "Source remainder")]:
        row = archive.loc[panel]
        lines.append(f"{label} & {int(row.stations)} & {int(row.groups)} & {row.median_complete_years:.0f} & {int(row.bavaria)} & {int(row.foen)} & {int(row.usgs)} " + r"\\")
    lines += [r"\bottomrule\end{tabular}\end{table}"]
    (PAPER / "process_gap_revision_archive_table.tex").write_text("\n".join(lines) + "\n")


def water_air_support() -> pd.DataFrame:
    trends = set(
        pd.read_csv(BASE / "trends.csv", usecols=["station_key"]).station_key.unique()
    )
    seed = pd.read_parquet(
        SEED,
        columns=["station_key", "year", "region", "eval_truth_h30", "air_h30_target_year"],
    )
    seed = (
        seed.loc[seed.station_key.isin(trends) & seed.region.isin(["gkd_bayern", "foen"])]
        .drop_duplicates(["station_key", "year"])
        .dropna(subset=["eval_truth_h30", "air_h30_target_year"])
    )

    def fit(block: pd.DataFrame) -> dict:
        x = block.air_h30_target_year.to_numpy(float)
        y = block.eval_truth_h30.to_numpy(float)
        xc = x - x.mean()
        slope = float((xc @ y) / (xc @ xc))
        corr = float(np.corrcoef(x, y)[0, 1])
        resid = float(np.std(y - (y.mean() + slope * xc)))
        return dict(
            n=int(len(block)),
            stations=int(block.station_key.nunique()),
            slope=slope,
            correlation=corr,
            residual_sd=resid,
        )

    rows = []
    for region, block in seed.groupby("region"):
        for period, part in [("before_2010", block.loc[block.year < 2010]), ("from_2010", block.loc[block.year >= 2010])]:
            row = fit(part)
            row.update(region=region, period=period)
            rows.append(row)
    return pd.DataFrame(rows)


def reconstruction_rmse() -> pd.DataFrame:
    cases = pd.read_csv(OUT / "time_support_cases.csv")
    rows = []
    for (family, mode, scheme), block in cases.groupby(["family", "mode", "scheme"]):
        rows.append(
            dict(
                family=family,
                mode=mode,
                scheme=scheme,
                n=int(len(block)),
                estimate_rmse=float(np.sqrt(np.mean(block.estimate_error**2))),
                truth_rmse=float(np.sqrt(np.mean(block.truth_error**2))),
                reconstruction_rmse=float(np.sqrt(np.mean(block.reconstruction**2))),
                end_weight=float(block.end_weight.mean()),
                span=float(block.span.mean()),
            )
        )
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    summary, stations = gap_geometry()
    summary.to_csv(OUT / "gap_geometry_summary.csv", index=False)
    stations.to_csv(OUT / "gap_geometry_cases.csv", index=False)
    archive = archive_comparison()
    archive.to_csv(OUT / "archive_comparison.csv", index=False)
    train_eval = train_eval_support()
    train_eval.to_csv(OUT / "train_eval_support.csv", index=False)
    recon = reconstruction_rmse()
    recon.to_csv(OUT / "time_support_reconstruction.csv", index=False)
    observed = observed_gaps()
    observed.to_csv(OUT / "observed_gap_summary.csv", index=False)
    common_gaps, annual_masks = common_gap_comparison()
    common_gaps.to_csv(OUT / "gap_common_statistic_comparison.csv", index=False)
    annual_masks.to_csv(OUT / "gap_annual_longest_cases.csv", index=False)
    write_gap_tex(common_gaps, archive)
    (OUT / "gap_archive_revision_report.json").write_text(json.dumps({
        "primary_gap_period": "2010-2025", "supplementary_observed_period": "1981-2025",
        "common_metric": "annual longest contiguous missing run, days",
        "observed_unit_weight": "equal incomplete station-year; no repeated masks",
        "trial_unit_weight": "equal incomplete station-year-replicate; 20 mask repeats retained",
        "shared_year_scope": "same year within connected group (and trial replicate); does not imply overlapping missing dates",
        "archive_complete_year_definition": "unique complete station-years in source cases, including held-out year",
        "donor_count_source": "leave-one-year-out source cases, not forward controlled gaps",
        "review_snapshot_preserved": "results/wrr_process_review_20261028 and results/wrr_process_review_20261029 are not overwritten",
    }, indent=2) + "\n")
    water_air = water_air_support()
    water_air.to_csv(OUT / "water_air_support.csv", index=False)
    print(summary.to_string(index=False), flush=True)
    print(archive.to_string(index=False), flush=True)
    print(train_eval.to_string(index=False), flush=True)
    print(
        recon.loc[recon.family.eq("crossed") & recon["mode"].eq("forward")].to_string(index=False),
        flush=True,
    )
    print(observed.to_string(index=False), flush=True)
    print(water_air.to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

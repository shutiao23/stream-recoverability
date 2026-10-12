#!/usr/bin/env python3
"""Referee probes for the v17 manuscript.

Four checks a referee can run against the authors' own artifacts. None of them
requires data the authors do not already hold; all four bear on claims the
manuscript makes or on assumptions it leaves unstated.

P1  Representativeness of the retained archive.  The manuscript compares rules
    at equal retention but never asks *which stations* each rule keeps.
P2  Stratum-balanced screening.  If P1 finds a bias, is it expensive to remove?
P3  Informative missingness.  Every case in the study is a transplanted outage.
    Are real outages independent of the state of the river, as that requires?
P4  Deployment on the real archive.  2,422 genuinely incomplete station-years
    are excluded from the study for having no truth.  They are the population
    the rule is for.  How often do the two rules disagree on them?

Writes to docs/reviews/wrr_stanford_2026_09_24/probe_output/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
OUT = Path(__file__).resolve().parent / "probe_output"
RESULTS = ROOT / "results" / "v17_fitness"


# ---------------------------------------------------------------- utilities

def load_scored(split: str) -> pd.DataFrame:
    """Cases joined to the certificate the authors scored them with."""
    if split == "development":
        cases = pd.read_parquet(RESULTS / "step3_cases" / "cases.parquet")
        cases = cases.loc[cases["split_role"] == "development"].reset_index(drop=True)
        cert = pd.read_parquet(RESULTS / "step6_screen" / "development_certificates.parquet")
    else:
        cases = pd.read_parquet(RESULTS / "step10_confirmation" / "reserved_cases.parquet").reset_index(drop=True)
        cert = pd.read_parquet(RESULTS / "step10_confirmation" / "reserved_certificates.parquet")
    return cases.join(cert[["certificate_bound", "certificate_abs_error"]])


def retain_global(score: np.ndarray, retention: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    order = np.lexsort((rng.random(len(score)), np.asarray(score, float)))
    keep = np.zeros(len(score), bool)
    keep[order[: int(round(retention * len(score)))]] = True
    return keep


def retain_within(score: np.ndarray, strata: np.ndarray, retention: float, seed: int) -> np.ndarray:
    """Equal retention inside every stratum rather than globally."""
    keep = np.zeros(len(score), bool)
    for offset, value in enumerate(pd.unique(strata)):
        idx = np.where(strata == value)[0]
        rng = np.random.default_rng(seed + offset)
        order = idx[np.lexsort((rng.random(len(idx)), np.asarray(score, float)[idx]))]
        keep[order[: int(round(retention * len(idx)))]] = True
    return keep


# ------------------------------------------------- P1 / P2 representativeness

def probe_representativeness(retention: float = 0.70) -> pd.DataFrame:
    attrs = (
        pd.read_csv(RESULTS / "step21_hydrology" / "station_panel.csv", dtype={"station_id": str})
        .set_index("station_id")[["BFI_AVE", "ELEV_SITE_M", "SLOPE_PCT", "log_area"]]
    )
    rows = []
    for split in ("development", "reserved"):
        cases = load_scored(split)
        cases["station_id"] = cases["station_id"].astype(str)
        consequential = cases["certificate_abs_error"].to_numpy() > 0.5
        masks = {
            "length_rule": retain_global(cases["longest_run"].to_numpy(), retention, 1),
            "screen_global": retain_global(cases["certificate_bound"].to_numpy(), retention, 2),
            "screen_balanced": retain_within(
                cases["certificate_bound"].to_numpy(), cases["donor_regime"].to_numpy(), retention, 2
            ),
        }
        for name, keep in masks.items():
            per_station = pd.Series(keep, index=cases.index).groupby(cases["station_id"]).mean()
            matched = per_station.to_frame("retention").join(attrs, how="inner")
            record = {
                "split": split,
                "rule": name,
                "retention": float(keep.mean()),
                "error_rate_pct": float(consequential[keep].mean() * 100),
                "n_stations_matched": int(len(matched)),
                "archive_mean_peak_c": float(cases.loc[keep, "truth_hottest30"].mean()),
                "archive_mean_peak_shift_c": float(
                    cases.loc[keep, "truth_hottest30"].mean() - cases["truth_hottest30"].mean()
                ),
                "station_retention_sd": float(per_station.std()),
            }
            for attribute in ("ELEV_SITE_M", "SLOPE_PCT", "BFI_AVE", "log_area"):
                test = stats.spearmanr(matched[attribute], matched["retention"])
                record[f"rho_{attribute}"] = float(test.statistic)
                record[f"p_{attribute}"] = float(test.pvalue)
            for regime, value in pd.Series(keep, index=cases.index).groupby(cases["donor_regime"]).mean().items():
                record[f"retention_{regime}"] = float(value)
            rows.append(record)
    return pd.DataFrame(rows)


# ----------------------------------------------- P3 informative missingness

def probe_informative_missingness() -> tuple[pd.DataFrame, dict]:
    from stream_recoverability.experiments.v17_fitness.panel import load_network_panel, station_roster

    roster = station_roster()
    roster = roster.loc[roster["eligible_station"]]
    gaps = []
    for (network_id, source_root), group in roster.groupby(["network_id", "source_root"]):
        try:
            panel = load_network_panel(str(network_id), str(source_root))
        except Exception:
            continue
        for station_id in group["station_id"].astype(str):
            if station_id not in panel.columns:
                continue
            series = pd.to_numeric(panel[station_id], errors="coerce")
            if series.notna().sum() < 400:
                continue
            series = series.loc[series.first_valid_index() : series.last_valid_index()]
            doy = series.index.dayofyear
            climatology = series.groupby(doy).mean()
            anomaly = series - pd.Series(climatology.reindex(doy).to_numpy(), index=series.index)
            missing = series.isna().to_numpy()
            edges = np.diff(np.concatenate([[0], missing.view(np.int8), [0]]))
            for start, end in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]):
                gaps.append(
                    {
                        "network_id": network_id,
                        "station_id": station_id,
                        "start_month": int(series.index[start].month),
                        "length": int(end - start),
                        "pre_anomaly_c": float(anomaly.iloc[max(0, start - 7) : start].mean()) if start else np.nan,
                        "post_anomaly_c": float(anomaly.iloc[end : end + 7].mean()) if end < len(series) else np.nan,
                    }
                )
    frame = pd.DataFrame(gaps)
    long_gaps = frame.loc[frame["length"] >= 30]
    counts = np.zeros(12)
    for month, value in long_gaps["start_month"].value_counts().items():
        counts[month - 1] = value
    uniform = stats.chisquare(counts, np.full(12, counts.sum() / 12))
    summary = {
        "n_gaps": int(len(frame)),
        "n_gaps_30d_plus": int(len(long_gaps)),
        "median_gap_days": float(frame["length"].median()),
        "p95_gap_days": float(frame["length"].quantile(0.95)),
        "start_month_uniformity_chi2": float(uniform.statistic),
        "start_month_uniformity_p": float(uniform.pvalue),
        "share_starting_sep_to_jan_pct": float(long_gaps["start_month"].isin([9, 10, 11, 12, 1]).mean() * 100),
        "share_starting_mar_to_jul_pct": float(long_gaps["start_month"].isin([3, 4, 5, 6, 7]).mean() * 100),
    }
    for low, high, label in ((1, 7, "1-7d"), (8, 29, "8-29d"), (30, 89, "30-89d"), (90, 10_000, "90d+")):
        subset = frame.loc[frame["length"].between(low, high)]
        test = stats.ttest_1samp(subset["pre_anomaly_c"].dropna(), 0)
        summary[f"pre_anomaly_{label}_c"] = float(subset["pre_anomaly_c"].mean())
        summary[f"pre_anomaly_{label}_p"] = float(test.pvalue)
        summary[f"post_anomaly_{label}_c"] = float(subset["post_anomaly_c"].mean())
    return frame, summary


# --------------------------------------------------- P4 archive deployment

def probe_archive_deployment() -> tuple[pd.DataFrame, dict]:
    from stream_recoverability.experiments.v17_fitness.panel import load_network_panel, station_roster

    roster = station_roster()
    roster = roster.loc[roster["eligible_station"]]
    rows = []
    for (network_id, source_root), group in roster.groupby(["network_id", "source_root"]):
        try:
            panel = load_network_panel(str(network_id), str(source_root))
        except Exception:
            continue
        for station_id in group["station_id"].astype(str):
            if station_id not in panel.columns:
                continue
            series = pd.to_numeric(panel[station_id], errors="coerce")
            if series.notna().sum() < 400:
                continue
            series = series.loc[series.first_valid_index() : series.last_valid_index()]
            frame = pd.DataFrame({"value": series.to_numpy()}, index=series.index)
            frame["year"] = frame.index.year
            frame["doy"] = frame.index.dayofyear
            complete = frame.groupby("year")["value"].apply(lambda x: bool(x.notna().all()) and len(x) >= 365)
            complete_years = complete[complete].index
            if len(complete_years) < 2:
                continue
            climatology = (
                frame.loc[frame["year"].isin(complete_years)]
                .groupby("doy")["value"]
                .mean()
                .reindex(range(1, 367))
                .interpolate(limit_direction="both")
            )
            peak_doy = int(climatology.rolling(30, center=True, min_periods=20).mean().idxmax())
            window = (peak_doy - 15, peak_doy + 14)
            for year, block in frame.groupby("year"):
                if len(block) < 360:
                    continue
                missing = block["value"].isna().to_numpy()
                edges = np.diff(np.concatenate([[0], missing.view(np.int8), [0]]))
                starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
                in_window = block["doy"].between(*window).to_numpy()
                rows.append(
                    {
                        "network_id": network_id,
                        "station_id": station_id,
                        "year": int(year),
                        "complete": bool(missing.sum() == 0),
                        "n_missing": int(missing.sum()),
                        "longest_run": int((ends - starts).max()) if len(starts) else 0,
                        "peak_missing_fraction": float(missing[in_window].mean()) if in_window.sum() else np.nan,
                    }
                )
    archive = pd.DataFrame(rows)
    incomplete = archive.loc[~archive["complete"]].dropna(subset=["peak_missing_fraction"])
    length_admits = incomplete["longest_run"] <= 49          # Johnson unfilled limit
    timing_admits = incomplete["peak_missing_fraction"] <= 0.10
    summary = {
        "n_station_years": int(len(archive)),
        "n_complete": int(archive["complete"].sum()),
        "n_incomplete": int((~archive["complete"]).sum()),
        "incomplete_median_missing_days": float(archive.loc[~archive["complete"], "n_missing"].median()),
        "incomplete_over_49d_run_pct": float((archive.loc[~archive["complete"], "longest_run"] > 49).mean() * 100),
        "incomplete_over_140d_run_n": int((archive.loc[~archive["complete"], "longest_run"] > 140).sum()),
        "incomplete_any_peak_day_missing_pct": float((incomplete["peak_missing_fraction"] > 0).mean() * 100),
        "incomplete_half_peak_window_missing_n": int((incomplete["peak_missing_fraction"] > 0.5).sum()),
        "length_admits_pct": float(length_admits.mean() * 100),
        "timing_admits_pct": float(timing_admits.mean() * 100),
        "disagreement_pct": float((length_admits != timing_admits).mean() * 100),
        "admitted_by_length_rejected_by_timing": int((length_admits & ~timing_admits).sum()),
        "rejected_by_length_admitted_by_timing": int((~length_admits & timing_admits).sum()),
    }
    return archive, summary


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    representativeness = probe_representativeness()
    representativeness.to_csv(OUT / "p1_representativeness.csv", index=False)

    gaps, missingness = probe_informative_missingness()
    gaps.to_parquet(OUT / "p3_real_gaps.parquet")
    (OUT / "p3_informative_missingness.json").write_text(json.dumps(missingness, indent=2), encoding="utf-8")

    archive, deployment = probe_archive_deployment()
    archive.to_parquet(OUT / "p4_archive_station_years.parquet")
    (OUT / "p4_archive_deployment.json").write_text(json.dumps(deployment, indent=2), encoding="utf-8")

    print(representativeness.to_string(index=False))
    print(json.dumps(missingness, indent=2))
    print(json.dumps(deployment, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

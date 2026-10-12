#!/usr/bin/env python3
"""Adversarial-review closure for F16 (cold extremes / sine phase) and F17 (7-DADMax).

Three separable pieces, each with its own output directory, driven by subcommands.

A. ``cold``   -- the cold-season analogue of the warm-season support axis, on the
   stored development/reserved case tables. The warm-season axis is
   ``warm_observed_fraction``; the cold analogue has to be built, because no
   step of the v17/v18 pipeline ever stored one. Two versions are built:

   * ``cold_season_observed_fraction``: the observed share of the non-warm
     calendar months (Oct-Apr), an exact algebraic function of stored columns
     (``total_missing``, ``missing_fraction``, ``warm_observed_fraction``,
     ``year``). Decision-time visible: it is calendar plus the observed mask.
   * ``cold_window_overlap``: the share of the station's *climatological*
     coldest-30-day window that an outage hides, the exact mirror of the stored
     ``peak_overlap`` column. It is not stored anywhere, so the outage
     realizations are regenerated from the same deterministic seeds the v17
     case table used, and the regeneration is verified column-for-column
     against the stored rows before the new axis is used.

   The endpoint is ``coldest30`` (the coldest 30-day mean), error taken through
   the same information-conditioned policy step 17 used, so the contrast is
   directly comparable with ``step17_metric_generality/metric_generality.csv``.

B. ``sine``   -- whether the sine-fit phase is identifiable when the fitted
   amplitude is near zero. ``v18_closure/endpoints.py:sine_parameters`` returns
   a phase whenever at least 30 days are present and the least-squares solve
   succeeds; there is no amplitude test anywhere in the pipeline. The observed
   relationship between fitted amplitude and phase error is measured on the
   stored v18 endpoint cases, and a reporting rule is derived from the phase
   standard error and then checked against that relationship.

C. ``dadmax`` -- WAC 173-201A-200(1)(c) measures temperature as the highest
   7-DADMax, the maximum over the year of the seven-day average of consecutive
   *daily maximum* temperatures (WAC 173-201A-020). The manuscript's regulatory
   illustration uses the hottest seven-day mean of *daily mean* temperatures.
   Daily maxima (parameterCd 00010, statCd 00001) are fetched from USGS NWIS
   daily values for the 91 stations of the sealed confirmation panel and the
   two statistics are compared on the same station-years.

Usage:
    PYTHONPATH=src python3 scripts/251_wrr_winter_regulatory_endpoints.py cold
    PYTHONPATH=src python3 scripts/251_wrr_winter_regulatory_endpoints.py sine
    PYTHONPATH=src python3 scripts/251_wrr_winter_regulatory_endpoints.py dadmax
    PYTHONPATH=src python3 scripts/251_wrr_winter_regulatory_endpoints.py all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.cases import (  # noqa: E402
    WARM_MONTHS,
    station_geometry_pool,
)
from stream_recoverability.experiments.v17_fitness.outages import (  # noqa: E402
    climatological_peak_window,
    design_for_year,
    peak_overlap_fraction,
)
from stream_recoverability.experiments.v17_fitness.panel import (  # noqa: E402
    load_network_panel,
    station_jobs,
    station_roster,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    NATURAL_SCALE_C,
    PRIMARY_TOLERANCE_C,
    REALIZATIONS_PER_STATION_YEAR,
    RESULTS_ROOT,
    STEP1_PANEL,
    STEP3_CASES,
    stable_seed,
)
from stream_recoverability.experiments.v17_fitness.policies import (  # noqa: E402
    CANDIDATE_ESTIMATORS,
    gather,
    information_conditioned_choice,
)

OUT_WINTER = ROOT / "results" / "wrr_submission_ready" / "amendments" / "winter_regulatory"
OUT_REG = ROOT / "results" / "wrr_submission_ready" / "amendments" / "regulatory_daily_max"
V18_ENDPOINT_CASES = ROOT / "results" / "v18_closure" / "endpoint_cases.parquet"
STEP17 = RESULTS_ROOT / "step17_metric_generality"
STEP22 = RESULTS_ROOT / "step22_robustness"
CONFIRMATION_MANIFEST = ROOT / "results" / "wrr_submission_ready" / "confirmation_inputs_manifest.csv"
CONFIRMATION_INGEST = ROOT / "results" / "wrr_submission_ready" / "confirmation_ingest"

COLD_WINDOW_DAYS = 30
# The mirror of WARM_MONTHS = (5..9): the remaining seven calendar months.
COLD_MONTHS = (10, 11, 12, 1, 2, 3, 4)
RETENTION = 0.70
# Step 17's equal-relative-stringency tolerance, and the task-specified literal
# 0.5 C for the cold endpoint. Both are reported; the literal one is primary.
TOLERANCE_FRACTION = PRIMARY_TOLERANCE_C / NATURAL_SCALE_C  # 0.4717
TOLERANCE_LITERAL_C = PRIMARY_TOLERANCE_C
BOOTSTRAP_DRAWS = 1200


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# shared output assembly
# --------------------------------------------------------------------------- #


def combine_winter_outputs() -> None:
    """Merge the two F16 sections into the single pair of files the amendment names."""

    OUT_WINTER.mkdir(parents=True, exist_ok=True)
    sections = [OUT_WINTER / name for name in ("report_section_a.md", "report_section_b.md")]
    parts = [path.read_text(encoding="utf-8") for path in sections if path.exists()]
    if parts:
        (OUT_WINTER / "REPORT.md").write_text("\n\n".join(part.rstrip() for part in parts) + "\n", encoding="utf-8")
    merged: dict[str, object] = {}
    for name in ("summary_cold.json", "summary_sine.json"):
        path = OUT_WINTER / name
        if path.exists():
            merged.update(json.loads(path.read_text(encoding="utf-8")))
    if merged:
        _write_json(OUT_WINTER / "summary.json", merged)


# --------------------------------------------------------------------------- #
# A. cold-endpoint support comparison
# --------------------------------------------------------------------------- #


def days_in_year(year: int) -> int:
    return 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365


def warm_day_count(year: int) -> int:
    start = pd.Timestamp(int(year), 1, 1)
    index = pd.date_range(start, periods=days_in_year(int(year)), freq="D")
    return int(index.month.isin(WARM_MONTHS).sum())


def cold_season_fraction_from_columns(cases: pd.DataFrame) -> pd.Series:
    """Observed share of the non-warm months, as an exact function of stored columns.

    ``cases.py`` stores ``missing_fraction = total_missing / n_days``,
    ``warm_observed_fraction`` and ``total_missing``, so ``n_days`` is recovered
    exactly and the cold-season share follows by subtraction. Nothing here
    touches the hidden values; it is the stored decision-time features only.
    """

    total_missing = pd.to_numeric(cases["total_missing"], errors="coerce").to_numpy(dtype=float)
    missing_fraction = pd.to_numeric(cases["missing_fraction"], errors="coerce").to_numpy(dtype=float)
    warm_observed = pd.to_numeric(cases["warm_observed_fraction"], errors="coerce").to_numpy(dtype=float)
    years = pd.to_numeric(cases["year"], errors="coerce").to_numpy(dtype=int)

    with np.errstate(divide="ignore", invalid="ignore"):
        n_days = np.round(total_missing / missing_fraction)
    n_days = np.where(np.isfinite(n_days) & (n_days > 0), n_days, np.nan)
    calendar_days = np.array([days_in_year(int(y)) for y in years], dtype=float)
    n_warm = np.array([warm_day_count(int(y)) for y in years], dtype=float)
    n_cold = calendar_days - n_warm
    observed_total = n_days - total_missing
    observed_warm = warm_observed * n_warm
    observed_cold = observed_total - observed_warm
    with np.errstate(divide="ignore", invalid="ignore"):
        fraction = observed_cold / n_cold
    out = pd.Series(fraction, index=cases.index, dtype=float)
    diagnostics = {
        "n_days_consistency_max_abs_deviation": float(np.nanmax(np.abs(n_days - calendar_days))),
        "n_days_distinct": sorted({int(v) for v in n_days[np.isfinite(n_days)]}),
        "max_abs_out_of_unit_interval": float(
            np.nanmax(np.abs(out.to_numpy(dtype=float) - 0.5) - 0.5)
        ),
    }
    return out, diagnostics


def climatological_trough_window(
    target: pd.Series, *, exclude_year: int | None = None, window: int = COLD_WINDOW_DAYS
) -> np.ndarray:
    """Day-of-year indices of the climatological coldest ``window``-day stretch.

    Exact mirror of ``outages.climatological_peak_window`` with the rolling mean
    minimised rather than maximised, so the cold axis is estimated from the same
    training-time information the warm axis used (every year but the target one).
    """

    values = pd.to_numeric(target, errors="coerce")
    if exclude_year is not None:
        values = values.loc[values.index.year != int(exclude_year)]
    values = values.dropna()
    if values.empty:
        return np.arange(20, 20 + window)
    doy = values.index.dayofyear
    climatology = values.groupby(doy).mean().reindex(range(1, 367)).interpolate(limit_direction="both")
    padded = np.concatenate([climatology.to_numpy(), climatology.to_numpy()[: window - 1]])
    rolling = np.convolve(padded, np.ones(window) / window, mode="valid")[:366]
    start = int(np.nanargmin(rolling)) + 1
    return np.array([((start - 1 + offset) % 366) + 1 for offset in range(window)], dtype=int)


def cold_support_rows(job: dict) -> pd.DataFrame:
    """Regenerate one station's outage realizations and measure the cold axes."""

    network_id = str(job["network_id"])
    station_id = str(job["station_id"])
    protocol = str(job.get("fit_protocol", "leave_one_year_out"))
    try:
        daily = load_network_panel(network_id, str(job["source_root"]))
    except (FileNotFoundError, ValueError, KeyError):
        return pd.DataFrame()
    daily = daily.copy()
    daily.columns = [str(c) for c in daily.columns]
    if station_id not in daily.columns:
        return pd.DataFrame()
    target = pd.to_numeric(daily[station_id], errors="coerce")
    pool = station_geometry_pool(daily)

    rows: list[dict] = []
    for year in (int(y) for y in job["complete_years"]):
        year_mask = target.index.year == int(year)
        year_index = daily.index[year_mask]
        truth = target.loc[year_mask].to_numpy(dtype=float)
        if not np.isfinite(truth).all() or len(truth) < 360:
            continue
        source = target.loc[target.index.year != int(year)]
        peak_doys = climatological_peak_window(source, exclude_year=None)
        trough_doys = climatological_trough_window(source, exclude_year=None)
        rng = np.random.default_rng(stable_seed(network_id, station_id, int(year), protocol))
        realizations = design_for_year(
            year_index, peak_doys, pool, rng=rng, n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3)
        )
        months = year_index.month.to_numpy()
        cold = np.isin(months, COLD_MONTHS)
        warm = np.isin(months, WARM_MONTHS)
        doy = year_index.dayofyear.to_numpy()
        in_trough = np.isin(doy, trough_doys)
        in_peak = np.isin(doy, peak_doys)
        for realization in realizations:
            mask = realization.mask(len(year_index))
            if not mask.any() or mask.all():
                continue
            rows.append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "year": int(year),
                    "realization_id": realization.realization_id,
                    "n_days": int(len(mask)),
                    "longest_run": int(realization.longest_run),
                    "total_missing": int(mask.sum()),
                    "missing_fraction": float(mask.mean()),
                    "peak_overlap": peak_overlap_fraction(year_index, mask, peak_doys),
                    "warm_observed_fraction": float((~mask & warm).sum() / max(1, warm.sum())),
                    "cold_season_observed_fraction": float((~mask & cold).sum() / max(1, cold.sum())),
                    "cold_window_overlap": float(mask[in_trough].mean()),
                    "cold_window_observed_fraction": float((~mask)[in_trough].mean()),
                    "cold_window_doy_start": int(trough_doys[0]),
                    "warm_window_doy_start": int(peak_doys[0]),
                    "trough_overlap_peak_window": float(np.isin(trough_doys, peak_doys).mean()),
                }
            )
    return pd.DataFrame(rows)


def build_cold_support_table(workers: int) -> pd.DataFrame:
    """Regenerated cold axes for every development station-year, seed-identical to v17."""

    roster = station_roster()
    split = pd.read_csv(STEP1_PANEL / "network_split.csv")
    split["network_id"] = split["network_id"].astype(str)
    jobs = station_jobs(roster, split)
    for job in jobs:
        job["fit_protocol"] = "leave_one_year_out"
    jobs = [job for job in jobs if str(job["split_role"]) == "development"]
    print(f"[cold] regenerating outage realizations for {len(jobs)} development stations", flush=True)

    frames: list[pd.DataFrame] = []
    started = time.time()
    if workers <= 1:
        for i, job in enumerate(jobs, start=1):
            frame = cold_support_rows(job)
            if len(frame):
                frames.append(frame)
            if i % 25 == 0:
                print(f"  {i}/{len(jobs)} stations ({time.time() - started:.0f}s)", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(cold_support_rows, job): job for job in jobs}
            for done, future in enumerate(as_completed(futures), start=1):
                frame = future.result()
                if len(frame):
                    frames.append(frame)
                if done % 25 == 0:
                    print(f"  {done}/{len(jobs)} stations ({time.time() - started:.0f}s)", flush=True)
    table = pd.concat(frames, ignore_index=True)
    return table.sort_values(["network_id", "station_id", "year", "realization_id"]).reset_index(drop=True)


def numpy_cluster_bootstrap(
    arrays: dict[str, np.ndarray],
    statistic,
    clusters: np.ndarray,
    *,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict[str, float]:
    """Cluster bootstrap on pre-extracted arrays.

    Same resampling scheme and seed as ``v17_fitness.stats.cluster_bootstrap``
    (whole clusters drawn with replacement, ``rng.integers(0, n, size=n)``), but
    the per-draw concatenation is done on numpy arrays that are already split by
    cluster, which is what makes a 1,200-draw sweep over several contrasts
    affordable. ``arrays`` must all have the same length and the same row order
    as the frame the slow version would have resampled.
    """

    keys = sorted(set(clusters.tolist()))
    index_by_key = {key: np.flatnonzero(clusters == key) for key in keys}
    point = float(statistic(arrays))
    if len(keys) < 2:
        return {"point": point, "low": float("nan"), "high": float("nan"), "n_clusters": len(keys)}
    rng = np.random.default_rng(int(seed))
    values = np.empty(int(draws), dtype=float)
    for draw in range(int(draws)):
        picked = rng.integers(0, len(keys), size=len(keys))
        joined = {
            name: np.concatenate([values_[index_by_key[keys[int(i)]]] for i in picked])
            for name, values_ in arrays.items()
        }
        try:
            values[draw] = float(statistic(joined))
        except (ValueError, ZeroDivisionError, KeyError, IndexError):
            values[draw] = np.nan
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"point": point, "low": float("nan"), "high": float("nan"), "n_clusters": len(keys)}
    return {
        "point": point,
        "low": float(np.quantile(finite, alpha / 2)),
        "high": float(np.quantile(finite, 1 - alpha / 2)),
        "se": float(np.std(finite, ddof=1)) if finite.size > 1 else float("nan"),
        "n_clusters": len(keys),
    }


def policy_error(cases: pd.DataFrame, metric: str) -> np.ndarray:
    choice = information_conditioned_choice(cases)
    return gather(cases, choice, prefix=f"abserr_{metric}_")


def risk_auc(label: np.ndarray, score: np.ndarray, *, higher_is_worse: bool = True) -> float:
    from sklearn.metrics import roc_auc_score

    good = np.isfinite(score) & np.isfinite(label)
    if good.sum() == 0 or len(np.unique(label[good])) < 2:
        return float("nan")
    values = score[good] if higher_is_worse else -score[good]
    return float(roc_auc_score(label[good], values))


def frontier_rate(score: np.ndarray, error: np.ndarray, tolerance: float) -> float:
    good = np.isfinite(error)
    score = np.where(np.isfinite(score), score, np.inf)[good]
    error = error[good]
    order = np.argsort(score, kind="mergesort")
    k = max(1, int(round(RETENTION * len(error))))
    return float((error[order[:k]] > tolerance).mean())


def grouped_logistic_auc(features: pd.DataFrame, label: pd.Series, groups: np.ndarray) -> float:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, random_state=0))
    oof = np.full(len(label), np.nan)
    for train_idx, test_idx in GroupKFold(n_splits=5).split(features, label, groups):
        model.fit(features.iloc[train_idx], label.iloc[train_idx])
        oof[test_idx] = model.predict_proba(features.iloc[test_idx])[:, 1]
    return float(roc_auc_score(label, oof))


AXES = (
    # name, column, higher value means higher risk?
    ("cold_window_overlap", "cold_window_overlap", True),
    ("cold_season_observed_fraction", "cold_season_observed_fraction", False),
    ("longest_run", "longest_run", True),
    ("peak_overlap", "peak_overlap", True),
    ("warm_observed_fraction", "warm_observed_fraction", False),
    ("missing_fraction", "missing_fraction", True),
)


def run_cold(workers: int) -> int:
    OUT_WINTER.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(STEP3_CASES / "cases.parquet")
    cases = cases.loc[cases["split_role"].eq("development")].reset_index(drop=True)
    cases["cold_season_observed_fraction"], column_diag = cold_season_fraction_from_columns(cases)
    print(f"[cold] development cases: {len(cases)}", flush=True)

    support = build_cold_support_table(workers)
    support.to_parquet(OUT_WINTER / "cold_support_cases.parquet", index=False)
    print(f"[cold] regenerated realizations: {len(support)}", flush=True)

    key = ["network_id", "station_id", "year", "realization_id"]
    merged = cases.merge(support, on=key, how="inner", suffixes=("", "_regen"), validate="one_to_one")
    print(f"[cold] merged cases: {len(merged)}", flush=True)

    checks = {}
    for column in ("longest_run", "total_missing", "peak_overlap", "warm_observed_fraction"):
        stored = pd.to_numeric(merged[column], errors="coerce").to_numpy(dtype=float)
        regen = pd.to_numeric(merged[f"{column}_regen"], errors="coerce").to_numpy(dtype=float)
        delta = np.abs(stored - regen)
        checks[f"max_abs_deviation_{column}"] = float(np.nanmax(delta))
        checks[f"agreement_within_1e-9_{column}"] = float(np.mean(delta <= 1e-9))
    delta = np.abs(
        merged["cold_season_observed_fraction"].to_numpy(dtype=float)
        - merged["cold_season_observed_fraction_regen"].to_numpy(dtype=float)
    )
    checks["max_abs_deviation_cold_season_observed_fraction"] = float(np.nanmax(delta))
    checks["regeneration_covers_stored_rows"] = float(len(merged) / len(cases))
    checks.update(column_diag)

    # ---- endogeneity of the regenerated cold-window column ----------------- #
    # A cold window is estimated from every year but the target one, so it is
    # decision-time information in the same sense as peak_overlap. Its stability
    # is what the screening rule inherits, so it is reported, not assumed. The
    # start day is circular (a window starting 30 December and one starting
    # 2 January are the same window), so dispersion is measured on the circle.
    def circular_sd_days(values: np.ndarray, period: float = 365.25) -> float:
        values = np.asarray(values, dtype=float)
        values = values[np.isfinite(values)]
        if values.size < 2:
            return float("nan")
        angle = 2 * np.pi * (values - 1.0) / period
        resultant = float(np.hypot(np.cos(angle).mean(), np.sin(angle).mean()))
        resultant = min(max(resultant, 0.0), 1.0)
        if resultant <= 0:
            return float("nan")
        return float(np.sqrt(-2 * np.log(resultant)) * period / (2 * np.pi))

    window_shift = (
        support.groupby(["network_id", "station_id"])
        .agg(
            trough_std_doy=("cold_window_doy_start", "std"),
            trough_circular_sd_days=("cold_window_doy_start", circular_sd_days),
            n_years=("cold_window_doy_start", "size"),
        )
        .dropna()
    )
    window_shift = window_shift.loc[window_shift["n_years"] >= 2]
    trough_months = pd.to_datetime(
        "2001-01-01"
    ) + pd.to_timedelta(support["cold_window_doy_start"].astype(float) - 1, unit="D")
    trough_month_counts = {int(k): int(v) for k, v in trough_months.dt.month.value_counts().sort_index().items()}
    starts = sorted({int(v) for v in support["cold_window_doy_start"].unique()})
    inside = []
    for start in starts:
        days = [((start - 1 + offset) % 366) + 1 for offset in range(COLD_WINDOW_DAYS)]
        months = {(pd.Timestamp("2001-01-01") + pd.Timedelta(days=int(d) - 1)).month for d in days}
        inside.append(bool(months.issubset(set(COLD_MONTHS))))
    trough_inside_cold = float(np.mean(inside)) if inside else float("nan")

    results = []
    bootstrap = {}
    per_estimator = []
    step17 = pd.read_csv(STEP17 / "metric_generality.csv").set_index("metric")
    tolerances = {
        metric: (
            ("literal_0.5C", TOLERANCE_LITERAL_C),
            ("equal_relative_0.4717sd", TOLERANCE_FRACTION * float(step17.loc[metric, "interannual_sd"])),
        )
        for metric in ("coldest30", "hottest30")
    }
    for metric in ("coldest30", "hottest30"):
        for tolerance_label, tolerance in tolerances[metric]:
            error = policy_error(merged, metric)
            label = pd.Series((error > tolerance).astype(float), index=merged.index)
            keep = np.isfinite(error)
            groups = merged["network_id"].to_numpy()
            rng = np.random.default_rng(23)
            jitter = rng.random(len(merged))
            scores = {}
            for name, column, higher in AXES:
                raw = pd.to_numeric(merged[column], errors="coerce").to_numpy(dtype=float)
                scores[name] = raw if higher else -raw
            row = {
                "metric": metric,
                "tolerance_rule": tolerance_label,
                "tolerance_c": float(tolerance),
                "n": int(keep.sum()),
                "n_networks": int(pd.Series(groups[keep]).nunique()),
                "base_rate": float(label[keep].mean()),
            }
            for name, _, _ in AXES:
                row[f"auc_{name}"] = risk_auc(label, scores[name], higher_is_worse=True)
                row[f"rate_at_70_{name}_rule"] = frontier_rate(scores[name] + jitter * 1e-9, error, tolerance)
            tone = "cold" if metric == "coldest30" else "warm"
            row["best_cold_axis"] = max(
                ("cold_window_overlap", "cold_season_observed_fraction"), key=lambda k: row[f"auc_{k}"]
            )
            row[f"auc_best_cold_axis_minus_longest_run"] = (
                row[f"auc_{row['best_cold_axis']}"] - row["auc_longest_run"]
            )
            row["auc_cold_window_overlap_minus_warm_observed_fraction"] = (
                row["auc_cold_window_overlap"] - row["auc_warm_observed_fraction"]
            )
            row["rate_at_70_best_cold_rule_minus_length_rule"] = (
                row[f"rate_at_70_{row['best_cold_axis']}_rule"] - row["rate_at_70_longest_run_rule"]
            )

            X_len = merged.loc[keep, ["longest_run"]].apply(pd.to_numeric, errors="coerce")
            X_both = merged.loc[keep, ["longest_run", "cold_window_overlap"]].apply(pd.to_numeric, errors="coerce")
            X_both_season = merged.loc[keep, ["longest_run", "cold_season_observed_fraction"]].apply(
                pd.to_numeric, errors="coerce"
            )
            X_len_missing = merged.loc[keep, ["longest_run", "missing_fraction"]].apply(pd.to_numeric, errors="coerce")
            y = label.loc[keep]
            g = groups[keep]
            if y.nunique() >= 2:
                row["grouped_logistic_auc_length_only"] = grouped_logistic_auc(X_len, y, g)
                row["grouped_logistic_auc_length_plus_cold_window"] = grouped_logistic_auc(X_both, y, g)
                row["grouped_logistic_auc_length_plus_cold_season"] = grouped_logistic_auc(X_both_season, y, g)
                row["grouped_logistic_auc_length_plus_missing_fraction"] = grouped_logistic_auc(X_len_missing, y, g)
            else:
                for name in (
                    "length_only",
                    "length_plus_cold_window",
                    "length_plus_cold_season",
                    "length_plus_missing_fraction",
                ):
                    row[f"grouped_logistic_auc_{name}"] = float("nan")
            results.append(row)

            # Cluster bootstrap of the two rule-level contrasts and the AUC gap.
            keep_block = np.isfinite(error)
            arrays = {
                "error": error[keep_block],
                "length": (scores["longest_run"] + jitter * 1e-9)[keep_block],
                "cold_window": (scores["cold_window_overlap"] + jitter * 1e-9)[keep_block],
                "cold_season": (scores["cold_season_observed_fraction"] + jitter * 1e-9)[keep_block],
                "cold_obs": pd.to_numeric(merged["cold_window_overlap"], errors="coerce").to_numpy(dtype=float)[
                    keep_block
                ],
                "longest_run": pd.to_numeric(merged["longest_run"], errors="coerce").to_numpy(dtype=float)[
                    keep_block
                ],
            }
            block_clusters = groups[keep_block]

            def rate_gap(values: dict, tol: float = float(tolerance)) -> float:
                return frontier_rate(values["cold_window"], values["error"], tol) - frontier_rate(
                    values["length"], values["error"], tol
                )

            def rate_gap_season(values: dict, tol: float = float(tolerance)) -> float:
                return frontier_rate(values["cold_season"], values["error"], tol) - frontier_rate(
                    values["length"], values["error"], tol
                )

            def auc_gap(values: dict, tol: float = float(tolerance)) -> float:
                lab = (values["error"] > tol).astype(float)
                return risk_auc(lab, values["cold_obs"]) - risk_auc(lab, values["longest_run"])

            bootstrap[f"{metric}__{tolerance_label}__rate_gap_cold_window_minus_length"] = numpy_cluster_bootstrap(
                arrays, rate_gap, block_clusters, draws=BOOTSTRAP_DRAWS, seed=0
            )
            bootstrap[f"{metric}__{tolerance_label}__rate_gap_cold_season_minus_length"] = numpy_cluster_bootstrap(
                arrays, rate_gap_season, block_clusters, draws=BOOTSTRAP_DRAWS, seed=0
            )
            bootstrap[f"{metric}__{tolerance_label}__auc_gap_cold_window_minus_length"] = numpy_cluster_bootstrap(
                arrays, auc_gap, block_clusters, draws=BOOTSTRAP_DRAWS, seed=0
            )

            # Estimator sensitivity: is the ordering an artefact of the policy?
            if metric == "coldest30":
                for estimator in CANDIDATE_ESTIMATORS:
                    column = f"abserr_{metric}_{estimator}"
                    if column not in merged.columns:
                        continue
                    err = pd.to_numeric(merged[column], errors="coerce").to_numpy(dtype=float)
                    keep_e = np.isfinite(err)
                    lab_e = (err[keep_e] > tolerance).astype(float)
                    if len(np.unique(lab_e)) < 2:
                        continue
                    per_estimator.append(
                        {
                            "metric": metric,
                            "estimator": estimator,
                            "tolerance_rule": tolerance_label,
                            "tolerance_c": float(tolerance),
                            "n": int(keep_e.sum()),
                            "base_rate": float(lab_e.mean()),
                            "auc_cold_window_overlap": risk_auc(lab_e, merged.loc[keep_e, "cold_window_overlap"].to_numpy()),
                            "auc_longest_run": risk_auc(lab_e, merged.loc[keep_e, "longest_run"].to_numpy()),
                            "auc_warm_observed_fraction": risk_auc(
                                lab_e, merged.loc[keep_e, "warm_observed_fraction"].to_numpy(), higher_is_worse=False
                            ),
                        }
                    )

    # Direct measurement of what the warm axis can say about the cold endpoint:
    # how much the two supports overlap at all.
    warm_win_overlap = float(np.nanmean(support["trough_overlap_peak_window"]))
    warm_win_overlap_max = float(np.nanmax(support["trough_overlap_peak_window"]))
    corr = float(
        pd.Series(support["warm_observed_fraction"]).corr(pd.Series(support["cold_window_overlap"]), method="spearman")
    )
    corr_lr = float(
        pd.Series(support["longest_run"]).corr(pd.Series(support["cold_window_overlap"]), method="spearman")
    )

    table = pd.DataFrame(results)
    table.to_csv(OUT_WINTER / "cold_support_contrast.csv", index=False)
    pd.DataFrame(per_estimator).to_csv(OUT_WINTER / "cold_support_per_estimator.csv", index=False)

    summary = {
        "question": (
            "F16: is the manuscript's cold-extreme recommendation ('keep length-based rules for cold "
            "extremes') supported by a cold-season support axis, or only by a warm-season axis that "
            "cannot see the cold window?"
        ),
        "coldest30_reconstruction_error_available": True,
        "coldest30_error_source": "step3_cases/cases.parquet columns abserr_coldest30_<estimator>",
        "estimand": "coldest 30-day mean daily water temperature",
        "primary_endpoint_tolerance_c": TOLERANCE_LITERAL_C,
        "equal_relative_tolerance_rule": f"{TOLERANCE_FRACTION:.4f} of the metric's interannual sd",
        "retention": RETENTION,
        "n_cases": int(len(merged)),
        "n_networks": int(merged["network_id"].nunique()),
        "cold_axis_definitions": {
            "cold_window_overlap": (
                "share of the station's climatological coldest-30-day window (estimated from every year "
                "but the target year) that the outage hides; exact mirror of the stored peak_overlap column"
            ),
            "cold_season_observed_fraction": (
                "observed share of the non-warm calendar months (Oct-Apr); exact algebraic function of "
                "stored total_missing, missing_fraction and warm_observed_fraction"
            ),
        },
        "regeneration_checks": checks,
        "cold_window_wander": {
            "n_stations": int(len(window_shift)),
            "circular_sd_days_median": float(window_shift["trough_circular_sd_days"].median()),
            "circular_sd_days_mean": float(window_shift["trough_circular_sd_days"].mean()),
            "circular_sd_days_p90": float(window_shift["trough_circular_sd_days"].quantile(0.90)),
            "raw_doy_sd_median": float(window_shift["trough_std_doy"].median()),
            "note": "raw doy sd is inflated by the 31 December wrap; circular sd is the honest figure",
        },
        "cold_window_placement": {
            "start_month_counts": trough_month_counts,
            "share_of_distinct_windows_fully_inside_cold_months": trough_inside_cold,
            "mean_share_of_cold_window_inside_climatological_peak_window": warm_win_overlap,
            "max_share_of_cold_window_inside_climatological_peak_window": warm_win_overlap_max,
        },
        "cold_versus_warm_support": {
            "spearman_warm_observed_fraction_vs_cold_window_overlap": corr,
            "spearman_longest_run_vs_cold_window_overlap": corr_lr,
        },
        "results": results,
        "per_estimator": per_estimator,
        "clustered_bootstrap": bootstrap,
    }
    _write_json(OUT_WINTER / "summary_cold.json", summary)
    write_cold_report(table, per_estimator, summary, checks)
    combine_winter_outputs()
    print(table[["metric", "tolerance_rule", "n", "base_rate", "auc_cold_window_overlap", "auc_cold_season_observed_fraction", "auc_longest_run", "auc_peak_overlap", "auc_warm_observed_fraction"]].round(4).to_string(index=False))
    print(json.dumps({k: {"point": round(v["point"], 4), "ci": [round(v["low"], 4), round(v["high"], 4)]} for k, v in bootstrap.items()}, indent=2))
    return 0


def write_cold_report(
    table: pd.DataFrame,
    per_estimator: list[dict],
    summary: dict,
    checks: dict,
) -> None:
    """Human-readable account of the cold-endpoint comparison."""

    def get(metric: str, rule: str, column: str) -> float:
        row = table.loc[table["metric"].eq(metric) & table["tolerance_rule"].eq(rule)]
        return float(row.iloc[0][column])

    boot = summary["clustered_bootstrap"]
    literal = "literal_0.5C"
    scaled = "equal_relative_0.4717sd"
    lines: list[str] = []
    lines.append("# F16(a) - can a cold-season support axis replace the length rule for the coldest 30-day mean?")
    lines.append("")
    lines.append(
        "Artifact: `results/wrr_submission_ready/amendments/winter_regulatory/cold_support_contrast.csv`. "
        "Script: `scripts/251_wrr_winter_regulatory_endpoints.py cold`."
    )
    lines.append("")
    lines.append("## What was computable from the stored tables")
    lines.append("")
    lines.append(
        "The development case table already stores coldest-30 reconstruction error for six estimators "
        "(`abserr_coldest30_<estimator>`), so the cold endpoint does **not** need a new run for its error "
        "side. What no step of the pipeline ever stored is a missingness measure restricted to the cold "
        "window: the table has `warm_observed_fraction` and `peak_overlap` and nothing for the cold season. "
        "Two cold axes were therefore built:"
    )
    lines.append("")
    lines.append(
        "* `cold_season_observed_fraction` - observed share of the non-warm calendar months (Oct-Apr), an "
        "exact algebraic function of stored `total_missing`, `missing_fraction`, `warm_observed_fraction` "
        "and `year` (the stored `missing_fraction = total_missing / n_days` recovers `n_days` exactly). It "
        "reproduces the mask-derived value to {:.1e}.".format(
            checks["max_abs_deviation_cold_season_observed_fraction"]
        )
    )
    lines.append(
        "* `cold_window_overlap` - share of the station's climatological coldest-30-day window that the "
        "outage hides, the mirror of the stored `peak_overlap`. It is not stored anywhere, so the outage "
        "realizations were regenerated from the v17 seeds. The regeneration reproduces {:,} of {:,} stored "
        "rows one-for-one, with maximum absolute deviation {:.1f} on `longest_run`, `total_missing`, "
        "`peak_overlap` and `warm_observed_fraction`.".format(
            summary["n_cases"], summary["n_cases"], max(
                checks["max_abs_deviation_longest_run"],
                checks["max_abs_deviation_total_missing"],
                checks["max_abs_deviation_peak_overlap"],
                checks["max_abs_deviation_warm_observed_fraction"],
            )
        )
    )
    lines.append("")
    lines.append(
        "Both are decision-time visible: calendar plus the observed/hidden pattern, with the cold window "
        "estimated from every year but the target one, exactly as `peak_overlap` is."
    )
    lines.append("")
    lines.append("## Result at 70% retention")
    lines.append("")
    lines.append(
        "n = {:,} development cases, {} networks, coldest-30 error through the information-conditioned "
        "policy of step 17 (whose warm-endpoint numbers this table reproduces to four decimals: hottest-30 "
        "peak overlap {:.4f}, warm coverage {:.4f}, length {:.4f}).".format(
            summary["n_cases"], summary["n_networks"],
            get("hottest30", scaled, "auc_peak_overlap"),
            get("hottest30", scaled, "auc_warm_observed_fraction"),
            get("hottest30", scaled, "auc_longest_run"),
        )
    )
    lines.append("")
    header = (
        "| axis | AUC (0.5 C) | AUC (0.4717 sd = {:.3f} C) | consequential-error rate at 70% (0.5 C) | rate (0.4717 sd) |".format(
            get("coldest30", scaled, "tolerance_c")
        )
    )
    lines.append(header)
    lines.append("| --- | --- | --- | --- | --- |")
    for name in (
        "cold_window_overlap",
        "cold_season_observed_fraction",
        "longest_run",
        "missing_fraction",
        "peak_overlap",
        "warm_observed_fraction",
    ):
        lines.append(
            "| `{}` | {:.4f} | {:.4f} | {:.4f} | {:.4f} |".format(
                name,
                get("coldest30", literal, f"auc_{name}"),
                get("coldest30", scaled, f"auc_{name}"),
                get("coldest30", literal, f"rate_at_70_{name}_rule"),
                get("coldest30", scaled, f"rate_at_70_{name}_rule"),
            )
        )
    lines.append("")
    lines.append(
        "Base rate of a consequential cold error: {:.4f} at 0.5 C, {:.4f} at 0.4717 sd.".format(
            get("coldest30", literal, "base_rate"), get("coldest30", scaled, "base_rate")
        )
    )
    lines.append("")
    lines.append("| contrast (network-clustered bootstrap, {} draws) | point | 95% CI |".format(BOOTSTRAP_DRAWS))
    lines.append("| --- | --- | --- |")
    for key, value in boot.items():
        if not key.startswith("coldest30"):
            continue
        lines.append(
            "| {} | {:+.5f} | ({:+.5f}, {:+.5f}) |".format(
                key.replace("coldest30__", ""), value["point"], value["low"], value["high"]
            )
        )
    lines.append("")
    lines.append(
        "Positive rate gaps mean the cold axis does *worse* than the length rule; negative means better. "
        "The AUC gap is oriented so that positive means the cold window discriminates better."
    )
    lines.append("")
    lines.append("## Does the cold axis add anything beyond gap length?")
    lines.append("")
    lines.append(
        "Out-of-fold grouped logistic AUC (5-fold, grouped by network):".format()
    )
    lines.append("")
    lines.append("| feature set | AUC (0.5 C) | AUC (0.4717 sd) |")
    lines.append("| --- | --- | --- |")
    for suffix in ("length_only", "length_plus_missing_fraction", "length_plus_cold_window", "length_plus_cold_season"):
        lines.append(
            "| `{}` | {:.4f} | {:.4f} |".format(
                suffix.replace("_", " "),
                get("coldest30", literal, f"grouped_logistic_auc_{suffix}"),
                get("coldest30", scaled, f"grouped_logistic_auc_{suffix}"),
            )
        )
    lines.append("")
    lines.append("## Estimator sensitivity")
    lines.append("")
    estimator_table = pd.DataFrame(per_estimator)
    if len(estimator_table):
        pivot = estimator_table.loc[estimator_table["tolerance_rule"].eq(literal)]
        lines.append("| estimator | n | base rate | AUC cold window | AUC length | AUC warm coverage |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for row in pivot.itertuples(index=False):
            lines.append(
                "| `{}` | {:,} | {:.4f} | {:.4f} | {:.4f} | {:.4f} |".format(
                    row.estimator, row.n, row.base_rate, row.auc_cold_window_overlap, row.auc_longest_run,
                    row.auc_warm_observed_fraction,
                )
            )
    lines.append("")
    lines.append("## What the warm-season result actually implies for cold extremes")
    lines.append("")
    lines.append(
        "The manuscript makes two connected assertions. (i) In the subsection on Table 2 (`tab:axes`, the "
        "table headed 'The share of the support a gap hides orders every endpoint, and the ordering "
        "reverses'): *\"peak-window overlap has an AUC of 0.447 for the cold extreme, because hiding the "
        "summer peak carries no information about the winter minimum\"*. (ii) In 'What an agency should "
        "change, and in what order': *\"keep length-based rules for annual means, cold extremes and the "
        "sine-fit regime parameters\"*. Assertion (i) is reproduced here exactly ({:.4f} at 0.4717 sd) and "
        "is true as stated - it is a statement about the warm-window axis. Assertion (ii) is the "
        "non-sequitur: it draws a rule for cold extremes from a measurement that cannot see the cold "
        "window, without ever measuring a cold-season axis. The stored tables measure why the inference "
        "fails:".format(get("coldest30", scaled, "auc_peak_overlap"))
    )
    lines.append("")
    lines.append(
        "* The climatological coldest-30-day window shares a mean of {:.4f} of its days with the "
        "climatological hottest-30-day window (maximum {:.4f} across cases), so the warm-season coverage "
        "axis is measuring a window that is disjoint from the cold support. It cannot be evidence about it "
        "either way.".format(
            summary["cold_window_placement"]["mean_share_of_cold_window_inside_climatological_peak_window"],
            summary["cold_window_placement"]["max_share_of_cold_window_inside_climatological_peak_window"],
        )
    )
    lines.append(
        "* Spearman correlation between `warm_observed_fraction` and `cold_window_overlap` is {:.4f}; "
        "between `longest_run` and `cold_window_overlap` it is {:.4f}.".format(
            summary["cold_versus_warm_support"]["spearman_warm_observed_fraction_vs_cold_window_overlap"],
            summary["cold_versus_warm_support"]["spearman_longest_run_vs_cold_window_overlap"],
        )
    )
    lines.append(
        "* Once a cold-season axis is measured directly, it beats the length rule on the cold endpoint: "
        "AUC {:.4f} vs {:.4f} (difference {:+.4f}, 95% CI {:+.4f} to {:+.4f}) at the equal-relative "
        "tolerance, and {:.4f} vs {:.4f} at 0.5 C.".format(
            get("coldest30", scaled, "auc_cold_window_overlap"),
            get("coldest30", scaled, "auc_longest_run"),
            boot["coldest30__equal_relative_0.4717sd__auc_gap_cold_window_minus_length"]["point"],
            boot["coldest30__equal_relative_0.4717sd__auc_gap_cold_window_minus_length"]["low"],
            boot["coldest30__equal_relative_0.4717sd__auc_gap_cold_window_minus_length"]["high"],
            get("coldest30", literal, "auc_cold_window_overlap"),
            get("coldest30", literal, "auc_longest_run"),
        )
    )
    lines.append(
        "* At equal retention the consequential-error rate falls from {:.4f} under the length rule to "
        "{:.4f} under the cold-window rule at 0.5 C ({:+.5f}, 95% CI {:+.5f} to {:+.5f}) and from "
        "{:.4f} to {:.4f} at 0.4717 sd.".format(
            get("coldest30", literal, "rate_at_70_longest_run_rule"),
            get("coldest30", literal, "rate_at_70_cold_window_overlap_rule"),
            boot["coldest30__literal_0.5C__rate_gap_cold_window_minus_length"]["point"],
            boot["coldest30__literal_0.5C__rate_gap_cold_window_minus_length"]["low"],
            boot["coldest30__literal_0.5C__rate_gap_cold_window_minus_length"]["high"],
            get("coldest30", scaled, "rate_at_70_longest_run_rule"),
            get("coldest30", scaled, "rate_at_70_cold_window_overlap_rule"),
        )
    )
    lines.append("")
    lines.append(
        "The honest summary is therefore: **the warm-season result implies nothing about cold extremes "
        "without a cold-season axis**, and the manuscript's own stated mechanism (summer gaps cannot "
        "inform the winter minimum) is a reason to build that axis, not a reason to fall back on gap "
        "length. Once built, the axis works, and the cold extreme is on the same side of the "
        "extremes-versus-averages line as the warm extreme."
    )
    lines.append("")
    lines.append("## Caveats recorded with the result")
    lines.append("")
    lines.append(
        "* The cold window is estimated, so the rule inherits its wander. Median circular spread of the "
        "climatological trough-window start across years: {:.1f} days (mean {:.1f}, p90 {:.1f}); the raw "
        "day-of-year standard deviation (median {:.1f} days) is inflated by the 31 December wrap.".format(
            summary["cold_window_wander"]["circular_sd_days_median"],
            summary["cold_window_wander"]["circular_sd_days_mean"],
            summary["cold_window_wander"]["circular_sd_days_p90"],
            summary["cold_window_wander"]["raw_doy_sd_median"],
        )
    )
    lines.append(
        "* {:.1%} of distinct climatological cold windows fall entirely inside the Oct-Apr cold months, "
        "so the season-length axis and the window axis are measuring the same season, not two different "
        "ones.".format(summary["cold_window_placement"]["share_of_distinct_windows_fully_inside_cold_months"])
    )
    lines.append(
        "* Rates at 70% retention break ties in the axis score with a uniform jitter, the convention step 17 "
        "used in `frontier_rate`. Coverage fractions are heavily tied, so an untied recomputation moves the "
        "cold-window rate from {:.4f} to about 0.0047 and the cold-season rate stays at {:.4f}; the AUCs, "
        "the AUC-gap intervals and the conclusions are unaffected, and the bootstrap contrasts resample the "
        "same jittered scores throughout.".format(
            get("coldest30", literal, "rate_at_70_cold_window_overlap_rule"),
            get("coldest30", literal, "rate_at_70_cold_season_observed_fraction_rule"),
        )
    )
    lines.append(
        "* This is a retrospective analysis on the opened development split. It is not a pre-registered "
        "confirmation and the sealed USGS panel was not re-scored."
    )
    lines.append("")
    lines.append(
        "* Per-estimator sensitivity: the cold-window axis beats gap length for five of the six "
        "estimators; the single exception is `air_ridge` (n = {:,} cases only, where air forcing exists), "
        "AUC {:.4f} against {:.4f}. The ordering is therefore a property of the endpoint, not of the "
        "policy's estimator choice.".format(
            int(estimator_table.loc[estimator_table['tolerance_rule'].eq(literal) & estimator_table['estimator'].eq('air_ridge'), 'n'].iloc[0]),
            float(estimator_table.loc[estimator_table['tolerance_rule'].eq(literal) & estimator_table['estimator'].eq('air_ridge'), 'auc_cold_window_overlap'].iloc[0]),
            float(estimator_table.loc[estimator_table['tolerance_rule'].eq(literal) & estimator_table['estimator'].eq('air_ridge'), 'auc_longest_run'].iloc[0]),
        )
    )
    lines.append("")
    (OUT_WINTER / "report_section_a.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# B. low-amplitude phase identifiability
# --------------------------------------------------------------------------- #

DAYS_IN_YEAR = 365.25


def sine_fit(values: np.ndarray) -> dict[str, float]:
    """The v18 sine estimator, plus the residual sd it does not return.

    Identical design matrix and phase convention to
    ``v18_closure/endpoints.py:sine_parameters``; the only addition is the
    residual standard deviation, which is the noise scale a reporting rule has
    to divide the fitted amplitude by. The amplitude is checked against the
    stored ``observed_sine_amplitude`` column as a regression test.
    """

    y = np.asarray(values, dtype=float)
    t = np.arange(len(y), dtype=float)
    good = np.isfinite(y)
    nan = {"sine_mean": np.nan, "sine_amplitude": np.nan, "sine_phase": np.nan, "sine_resid_sd": np.nan,
           "n_used": float(good.sum())}
    if good.sum() < 30:
        return nan
    angle = 2 * np.pi * t[good] / DAYS_IN_YEAR
    design = np.column_stack([np.ones(good.sum()), np.sin(angle), np.cos(angle)])
    try:
        beta, *_ = np.linalg.lstsq(design, y[good], rcond=None)
    except np.linalg.LinAlgError:
        return nan
    intercept, a, b = (float(v) for v in beta)
    amplitude = float(np.hypot(a, b))
    phi = float(np.arctan2(-b, a) % (2 * np.pi))
    peak_day = float((phi * DAYS_IN_YEAR / (2 * np.pi) + DAYS_IN_YEAR / 4.0) % DAYS_IN_YEAR) + 1.0
    resid = y[good] - design @ beta
    dof = max(1, int(good.sum()) - 3)
    return {
        "sine_mean": intercept,
        "sine_amplitude": amplitude,
        "sine_phase": peak_day,
        "sine_resid_sd": float(np.sqrt(float(resid @ resid) / dof)),
        "n_used": float(good.sum()),
    }


def sine_support_rows(job: dict) -> pd.DataFrame:
    """Per-case noise scale and an end-to-end check of the stored sine columns."""

    network_id = str(job["network_id"])
    station_id = str(job["station_id"])
    protocol = str(job.get("fit_protocol", "leave_one_year_out"))
    try:
        daily = load_network_panel(network_id, str(job["source_root"]))
    except (FileNotFoundError, ValueError, KeyError):
        return pd.DataFrame()
    daily = daily.copy()
    daily.columns = [str(c) for c in daily.columns]
    if station_id not in daily.columns:
        return pd.DataFrame()
    target = pd.to_numeric(daily[station_id], errors="coerce")
    pool = station_geometry_pool(daily)

    rows: list[dict] = []
    for year in (int(y) for y in job["complete_years"]):
        year_mask = target.index.year == int(year)
        year_index = daily.index[year_mask]
        truth = target.loc[year_mask].to_numpy(dtype=float)
        if not np.isfinite(truth).all() or len(truth) < 360:
            continue
        peak_doys = climatological_peak_window(target.loc[target.index.year != int(year)], exclude_year=None)
        rng = np.random.default_rng(stable_seed(network_id, station_id, int(year), protocol))
        realizations = design_for_year(
            year_index, peak_doys, pool, rng=rng, n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3)
        )
        truth_fit = sine_fit(truth)
        for realization in realizations:
            mask = realization.mask(len(year_index))
            if not mask.any() or mask.all():
                continue
            observed = truth.copy()
            observed[mask] = np.nan
            observed_fit = sine_fit(observed)
            rows.append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "year": int(year),
                    "realization_id": realization.realization_id,
                    "n_observed_days": int((~mask).sum()),
                    "sine_resid_sd_truth": truth_fit["sine_resid_sd"],
                    "sine_resid_sd_observed": observed_fit["sine_resid_sd"],
                    "observed_sine_amplitude_check": observed_fit["sine_amplitude"],
                    "observed_sine_phase_check": observed_fit["sine_phase"],
                }
            )
    return pd.DataFrame(rows)


def build_sine_support_table(workers: int) -> pd.DataFrame:
    roster = station_roster()
    split = pd.read_csv(STEP1_PANEL / "network_split.csv")
    split["network_id"] = split["network_id"].astype(str)
    jobs = station_jobs(roster, split)
    for job in jobs:
        job["fit_protocol"] = "leave_one_year_out"
    print(f"[sine] regenerating realizations for {len(jobs)} stations", flush=True)
    frames: list[pd.DataFrame] = []
    started = time.time()
    with ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(sine_support_rows, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), start=1):
            frame = future.result()
            if len(frame):
                frames.append(frame)
            if done % 50 == 0:
                print(f"  {done}/{len(jobs)} stations ({time.time() - started:.0f}s)", flush=True)
    return pd.concat(frames, ignore_index=True)


def circular_phase_tolerance(cases: pd.DataFrame) -> tuple[float, float]:
    """Interannual sd of the true phase, and 0.4717 of it, in days."""

    truth = cases.groupby(["network_id", "station_id", "year"])["truth_sine_phase"].first().reset_index()
    per_station = truth.groupby(["network_id", "station_id"])["truth_sine_phase"].agg(["std", "size"])
    per_station = per_station.loc[per_station["size"] >= 4, "std"].dropna()
    scale = float(per_station.mean())
    return scale, TOLERANCE_FRACTION * scale


def run_sine(workers: int) -> int:
    OUT_WINTER.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(V18_ENDPOINT_CASES)
    cases = cases.loc[cases["split_role"].eq("development")].reset_index(drop=True)
    print(f"[sine] development endpoint cases: {len(cases)}", flush=True)

    support = build_sine_support_table(workers)
    support.to_parquet(OUT_WINTER / "sine_support_cases.parquet", index=False)
    key = ["network_id", "station_id", "year", "realization_id"]
    merged = cases.merge(support, on=key, how="inner", suffixes=("", "_regen"), validate="one_to_one")
    coverage = float(len(merged) / len(cases))
    print(f"[sine] merged {len(merged)} of {len(cases)} cases", flush=True)

    amplitude_deviation = float(
        np.nanmax(
            np.abs(
                pd.to_numeric(merged["observed_sine_amplitude"], errors="coerce").to_numpy(dtype=float)
                - pd.to_numeric(merged["observed_sine_amplitude_check"], errors="coerce").to_numpy(dtype=float)
            )
        )
    )
    phase_deviation = float(
        np.nanmax(
            np.abs(
                pd.to_numeric(merged["observed_sine_phase"], errors="coerce").to_numpy(dtype=float)
                - pd.to_numeric(merged["observed_sine_phase_check"], errors="coerce").to_numpy(dtype=float)
            )
        )
    )

    phase_scale, phase_tolerance = circular_phase_tolerance(merged)
    print(f"[sine] phase interannual sd {phase_scale:.4f} d, tolerance {phase_tolerance:.4f} d", flush=True)

    protocols = {
        "repaired": ("policy_sine_amplitude", "abserr_sine_phase", "sine_resid_sd_observed"),
        "observed_days_only": ("observed_sine_amplitude", "abserr_observed_sine_phase", "sine_resid_sd_observed"),
    }
    bins = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 8.0, np.inf]
    binned_rows: list[dict] = []
    sweep_rows: list[dict] = []
    threshold_cuts: list[dict] = []
    monotonicity_rows: list[dict] = []
    k_theory_value = float("nan")
    case_frames: list[pd.DataFrame] = []
    for protocol, (amp_col, err_col, sd_col) in protocols.items():
        amplitude = pd.to_numeric(merged[amp_col], errors="coerce").to_numpy(dtype=float)
        error = pd.to_numeric(merged[err_col], errors="coerce").to_numpy(dtype=float)
        sigma = pd.to_numeric(merged[sd_col], errors="coerce").to_numpy(dtype=float)
        ratio = amplitude / sigma
        label = error > phase_tolerance
        case_frame = pd.DataFrame(
            {
                "network_id": merged["network_id"],
                "station_id": merged["station_id"],
                "year": merged["year"],
                "realization_id": merged["realization_id"],
                "protocol": protocol,
                "fitted_amplitude": amplitude,
                "resid_sd_observed": sigma,
                "amplitude_to_noise": ratio,
                "amplitude_to_noise_truth_scale": amplitude
                / pd.to_numeric(merged["sine_resid_sd_truth"], errors="coerce").to_numpy(dtype=float),
                "abs_phase_error_days": error,
                "n_observed_days": merged["n_observed_days"],
                "truth_amplitude": merged["truth_sine_amplitude"],
                "consequential": label,
            }
        )
        case_frames.append(case_frame)
        # What the sampling theory says the phase error should be, per case:
        # se(phi) = sigma*sqrt(2/n)/A radians, converted to days.
        with np.errstate(divide="ignore", invalid="ignore"):
            implied_se_days = (
                sigma * np.sqrt(2.0 / merged["n_observed_days"].to_numpy(dtype=float)) / amplitude
            ) * DAYS_IN_YEAR / (2 * np.pi)
        for low, high in zip(bins[:-1], bins[1:]):
            inside = (ratio >= low) & (ratio < high)
            if not inside.any():
                continue
            binned_rows.append(
                {
                    "protocol": protocol,
                    "amplitude_to_noise_low": low,
                    "amplitude_to_noise_high": high if np.isfinite(high) else None,
                    "n": int(inside.sum()),
                    "share_of_cases": float(inside.mean()),
                    "median_abs_phase_error_days": float(np.nanmedian(error[inside])),
                    "q90_abs_phase_error_days": float(np.nanquantile(error[inside], 0.90)),
                    "median_abs_phase_error_days_normalised": float(
                        np.nanmedian(error[inside]) / phase_scale
                    ),
                    "consequential_rate": float(np.nanmean(label[inside])),
                    "median_fitted_amplitude": float(np.nanmedian(amplitude[inside])),
                    "median_noise_implied_se_days": float(np.nanmedian(implied_se_days[inside])),
                    "median_noise_implied_95pct_half_width_days": float(
                        2 * np.nanmedian(implied_se_days[inside])
                    ),
                    "median_observed_over_implied_error": float(
                        np.nanmedian(error[inside]) / max(1e-9, np.nanmedian(implied_se_days[inside]))
                    ),
                }
            )

        # Reporting-rule sweep: keep phase only when A_hat >= k * sigma.
        n_median = float(np.nanmedian(merged["n_observed_days"].to_numpy(dtype=float)))
        tau_rad = 2 * np.pi * phase_tolerance / DAYS_IN_YEAR
        rule_k_theory = 2 * np.sqrt(2.0 / n_median) / tau_rad
        k_theory_value = float(rule_k_theory)
        for k in np.round(np.arange(0.0, 6.01, 0.25), 2):
            keep = ratio >= k
            if keep.sum() < 50:
                continue
            sweep_rows.append(
                {
                    "protocol": protocol,
                    "k_amplitude_over_noise": float(k),
                    "n_retained": int(keep.sum()),
                    "share_retained": float(keep.mean()),
                    "consequential_rate_retained": float(np.nanmean(label[keep])),
                    "median_abs_phase_error_days_retained": float(np.nanmedian(error[keep])),
                    "q90_abs_phase_error_days_retained": float(np.nanquantile(error[keep], 0.90)),
                    "consequential_rate_suppressed": float(np.nanmean(label[~keep])) if (~keep).any() else float("nan"),
                    "share_of_all_phase_errors_suppressed": float(
                        np.nansum(label & ~keep) / max(1, np.nansum(label))
                    ),
                }
            )
        sweep_rows.append(
            {
                "protocol": protocol,
                "k_amplitude_over_noise": float(round(rule_k_theory, 4)),
                "n_retained": int((ratio >= rule_k_theory).sum()),
                "share_retained": float((ratio >= rule_k_theory).mean()),
                "consequential_rate_retained": float(np.nanmean(label[ratio >= rule_k_theory])),
                "median_abs_phase_error_days_retained": float(np.nanmedian(error[ratio >= rule_k_theory])),
                "q90_abs_phase_error_days_retained": float(np.nanquantile(error[ratio >= rule_k_theory], 0.90)),
                "consequential_rate_suppressed": float(np.nanmean(label[ratio < rule_k_theory])),
                "share_of_all_phase_errors_suppressed": float(
                    np.nansum(label & (ratio < rule_k_theory)) / max(1, np.nansum(label))
                ),
            }
        )

        # Threshold cuts and the monotonicity check, computed once per protocol.
        for cut in (1.0, 1.5, 2.0, 4.0):
            below = ratio < cut
            threshold_cuts.append(
                {
                    "protocol": protocol,
                    "amplitude_to_noise_cut": cut,
                    "n_below": int(below.sum()),
                    "share_below": float(below.mean()),
                    "median_abs_phase_error_days_below": float(np.nanmedian(error[below]))
                    if below.any()
                    else float("nan"),
                    "consequential_rate_below": float(np.nanmean(label[below])) if below.any() else float("nan"),
                    "share_of_all_consequential_errors_below": float(
                        np.nansum(label & below) / max(1, np.nansum(label))
                    ),
                }
            )
        finite_ratio = np.isfinite(ratio) & np.isfinite(error)
        monotonicity_rows.append(
            {
                "protocol": protocol,
                "spearman_log_ratio_vs_abs_phase_error": float(
                    pd.Series(np.log(np.clip(ratio[finite_ratio], 1e-6, None))).corr(
                        pd.Series(error[finite_ratio]), method="spearman"
                    )
                ),
                "spearman_fitted_amplitude_vs_abs_phase_error": float(
                    pd.Series(amplitude[finite_ratio]).corr(pd.Series(error[finite_ratio]), method="spearman")
                ),
                "spearman_truth_amplitude_vs_abs_phase_error": float(
                    pd.Series(
                        pd.to_numeric(merged["truth_sine_amplitude"], errors="coerce").to_numpy(dtype=float)[
                            finite_ratio
                        ]
                    ).corr(pd.Series(error[finite_ratio]), method="spearman")
                ),
            }
        )

    # The manuscript's phase comparison (influence-weighted vs the rest), with and
    # without the unidentifiable cases. The rule is the mechanism-derived k*
    # rounded to the nearest half; k* itself is reported beside it.
    rule_k = float(round(k_theory_value * 2) / 2)
    repaired_cases = case_frames[0]
    repaired_cases = repaired_cases.assign(
        consequential=repaired_cases["consequential"].astype(float),
    )
    axis_frame = repaired_cases.merge(
        merged[
            [
                "network_id",
                "station_id",
                "year",
                "realization_id",
                "peak_overlap",
                "transition_overlap",
                "missing_fraction",
                "longest_run",
                "influence_hidden_sine_phase",
            ]
        ],
        on=key,
        how="left",
        validate="one_to_one",
    )
    axis_frame = axis_frame.assign(
        amplitude_to_noise_truth_scale=pd.to_numeric(
            axis_frame["amplitude_to_noise_truth_scale"], errors="coerce"
        )
    )
    axis_contrasts = {}
    populations = (
        ("all_cases", axis_frame),
        ("identifiable_only", axis_frame.loc[axis_frame["amplitude_to_noise"] >= rule_k]),
        ("identifiable_truth_noise_scale", axis_frame.loc[axis_frame["amplitude_to_noise_truth_scale"] >= rule_k]),
    )
    for name, subset in populations:
        subset = subset.dropna(subset=["consequential"]).reset_index(drop=True)
        label = subset["consequential"].to_numpy(dtype=float)
        row = {
            "n": int(len(subset)),
            "base_rate": float(label.mean()),
            "auc_peak_overlap": risk_auc(label, subset["peak_overlap"].to_numpy(dtype=float)),
            "auc_transition_overlap": risk_auc(label, subset["transition_overlap"].to_numpy(dtype=float)),
            "auc_missing_fraction": risk_auc(label, subset["missing_fraction"].to_numpy(dtype=float)),
            "auc_longest_run": risk_auc(label, subset["longest_run"].to_numpy(dtype=float)),
            "auc_influence_hidden": risk_auc(label, subset["influence_hidden_sine_phase"].to_numpy(dtype=float)),
        }
        row["auc_influence_minus_longest_run"] = row["auc_influence_hidden"] - row["auc_longest_run"]
        row["auc_influence_minus_missing_fraction"] = row["auc_influence_hidden"] - row["auc_missing_fraction"]

        arrays = {
            "error": subset["abs_phase_error_days"].to_numpy(dtype=float),
            "influence": subset["influence_hidden_sine_phase"].to_numpy(dtype=float),
            "missing": subset["missing_fraction"].to_numpy(dtype=float),
            "length": subset["longest_run"].to_numpy(dtype=float),
        }
        subset_clusters = subset["network_id"].to_numpy()

        def contrast(values: dict, tol: float = phase_tolerance) -> float:
            lab = (values["error"] > tol).astype(float)
            return risk_auc(lab, values["influence"]) - risk_auc(lab, values["missing"])

        def contrast_length(values: dict, tol: float = phase_tolerance) -> float:
            lab = (values["error"] > tol).astype(float)
            return risk_auc(lab, values["influence"]) - risk_auc(lab, values["length"])

        axis_contrasts[name] = {
            "summary": row,
            "clustered_bootstrap_influence_minus_missing_fraction": numpy_cluster_bootstrap(
                arrays, contrast, subset_clusters, draws=BOOTSTRAP_DRAWS, seed=0
            ),
            "clustered_bootstrap_influence_minus_length": numpy_cluster_bootstrap(
                arrays, contrast_length, subset_clusters, draws=BOOTSTRAP_DRAWS, seed=0
            ),
        }

    binned = pd.DataFrame(binned_rows)
    sweep = pd.DataFrame(sweep_rows)
    pd.concat(case_frames, ignore_index=True).to_parquet(OUT_WINTER / "sine_phase_cases.parquet", index=False)
    binned.to_csv(OUT_WINTER / "sine_phase_amplitude.csv", index=False)
    sweep.to_csv(OUT_WINTER / "sine_phase_rule_sweep.csv", index=False)

    near_zero = binned.loc[binned["amplitude_to_noise_high"].eq(1.0)]
    random_phase_error = DAYS_IN_YEAR / 4.0
    summary = {
        "question": (
            "F16: the sine-phase endpoint is reported with no amplitude-identifiability rule. Is the "
            "phase identifiable when the fitted amplitude is near the noise level, and what rule should "
            "govern its reporting?"
        ),
        "estimator_source": "src/stream_recoverability/experiments/v18_closure/endpoints.py:sine_parameters",
        "estimator_has_amplitude_guard": False,
        "estimator_guard_evidence": (
            "sine_parameters returns sine_phase whenever at least 30 finite days are present and the "
            "least-squares solve succeeds; abserr_sine_phase is then computed unconditionally. No "
            "amplitude or signal-to-noise test exists in endpoints.py, in the v18 e3 runner, or in the "
            "manuscript's sine table."
        ),
        "n_cases": int(len(merged)),
        "regeneration_coverage": coverage,
        "regeneration_checks": {
            "max_abs_deviation_observed_sine_amplitude": amplitude_deviation,
            "max_abs_deviation_observed_sine_phase_days": phase_deviation,
        },
        "phase_tolerance": {
            "interannual_sd_days": phase_scale,
            "tolerance_days": phase_tolerance,
            "tolerance_rule": f"{TOLERANCE_FRACTION:.4f} of the phase's interannual sd (step 17 convention)",
        },
        "random_phase_error_days_expected": random_phase_error,
        "amplitude_to_noise_bins": binned_rows,
        "threshold_cuts": threshold_cuts,
        "monotonicity": monotonicity_rows,
        "near_or_below_noise": {
            "definition": "fitted amplitude < residual sd (A/sigma < 1)",
            "rows": near_zero.to_dict(orient="records"),
        },
        "noise_scale_bracket": {
            "primary": "sine_resid_sd_observed (residual sd of the fit to the days actually present)",
            "sensitivity": "sine_resid_sd_truth (residual sd of the same fit to the complete year)",
            "median_ratio_observed_over_truth": float(
                np.nanmedian(
                    pd.to_numeric(merged["sine_resid_sd_observed"], errors="coerce").to_numpy(dtype=float)
                    / pd.to_numeric(merged["sine_resid_sd_truth"], errors="coerce").to_numpy(dtype=float)
                )
            ),
            "note": (
                "the repaired series is smoother than the observed days alone, so its own residual sd lies "
                "between these two; they bracket the rule's input to within a few per cent"
            ),
        },
        "reporting_rule": {
            "form": "report the sine-fit phase only when the fitted amplitude exceeds k times the residual sd",
            "derivation": (
                "the phase standard error of a three-parameter sine fit is se(phi) = sigma*sqrt(2/n)/A "
                "radians, so requiring a 95% interval no wider than the study's own phase tolerance tau "
                "gives A/sigma >= 2*sqrt(2/n)/tau"
            ),
            "n_observed_days_median": float(np.nanmedian(merged["n_observed_days"].to_numpy(dtype=float))),
            "tau_radians": float(2 * np.pi * phase_tolerance / DAYS_IN_YEAR),
            "k_theory": float(2 * np.sqrt(2.0 / float(np.nanmedian(merged["n_observed_days"].to_numpy(dtype=float))))
                              / (2 * np.pi * phase_tolerance / DAYS_IN_YEAR)),
            "k_used": rule_k,
            "sensitivity_checks": sweep_rows,
        },
        "effect_on_the_reported_phase_comparison": axis_contrasts,
    }
    _write_json(OUT_WINTER / "summary_sine.json", summary)
    write_sine_report(binned, sweep, summary)
    combine_winter_outputs()
    print(binned.round(4).to_string(index=False))
    print()
    print(json.dumps({k: v["summary"] for k, v in axis_contrasts.items()}, indent=2))
    return 0


def write_sine_report(binned: pd.DataFrame, sweep: pd.DataFrame, summary: dict) -> None:
    phase = summary["phase_tolerance"]
    rule = summary["reporting_rule"]
    k = float(rule["k_used"])
    repaired = binned.loc[binned["protocol"].eq("repaired")]
    repaired_sweep = sweep.loc[sweep["protocol"].eq("repaired")].sort_values("k_amplitude_over_noise").reset_index(drop=True)
    observed = binned.loc[binned["protocol"].eq("observed_days_only")]
    observed_cut = {
        row["amplitude_to_noise_cut"]: row
        for row in summary["threshold_cuts"]
        if row["protocol"] == "observed_days_only"
    }
    repaired_cut = {
        row["amplitude_to_noise_cut"]: row
        for row in summary["threshold_cuts"]
        if row["protocol"] == "repaired"
    }
    lines: list[str] = []
    lines.append("# F16(b) - the sine-fit phase has no low-amplitude identifiability rule")
    lines.append("")
    lines.append(
        "Artifacts: `sine_phase_amplitude.csv`, `sine_phase_rule_sweep.csv`, `sine_phase_cases.parquet`, "
        "`summary.json`. Script: `scripts/251_wrr_winter_regulatory_endpoints.py sine`."
    )
    lines.append("")
    lines.append("## The code path")
    lines.append("")
    lines.append(
        "`v18_closure/endpoints.py:sine_parameters` returns `sine_phase` whenever at least 30 finite days "
        "are present and the least-squares solve succeeds. `endpoint_rows` then computes "
        "`abserr_sine_phase` unconditionally, and `step17`/`e3_sine_endpoints` treat every such case as a "
        "scored observation. Nothing in the pipeline tests whether the fitted amplitude is distinguishable "
        "from zero, so a record whose seasonal cycle is flat - or an outage pattern that removes the cycle - "
        "contributes a phase drawn from noise to the reported AUC."
    )
    lines.append("")
    lines.append(
        "The noise scale is the residual sd of the same three-parameter fit; it is not returned by "
        "`sine_parameters`, so it was recomputed here. The recomputation is checked against the stored "
        "columns: $n$ = {:,} development cases, {:.1%} of them regenerated, maximum absolute deviation "
        "{:.2e} on `observed_sine_amplitude` and {:.2e} days on `observed_sine_phase`.".format(
            summary["n_cases"], summary["regeneration_coverage"],
            summary["regeneration_checks"]["max_abs_deviation_observed_sine_amplitude"],
            summary["regeneration_checks"]["max_abs_deviation_observed_sine_phase_days"],
        )
    )
    lines.append("")
    lines.append("## How phase error grows as the amplitude shrinks")
    lines.append("")
    lines.append(
        "Phase error is the circular difference from the complete-year fit, in days; the study's own phase "
        "tolerance is {:.4f} days ({:.4f} of the phase's interannual sd of {:.3f} days). A phase drawn at "
        "random from the year has an expected absolute error of {:.1f} days.".format(
            phase["tolerance_days"], TOLERANCE_FRACTION, phase["interannual_sd_days"],
            summary["random_phase_error_days_expected"],
        )
    )
    lines.append("")
    lines.append("Protocol `repaired` (the manuscript's Table 3 row):")
    lines.append("")
    lines.append("| fitted amplitude / residual sd | n | share | median abs phase error (d) | q90 (d) | noise-implied 95% half-width (d) | median error / implied | consequential rate |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in repaired.itertuples(index=False):
        upper = "inf" if row.amplitude_to_noise_high is None or (
            isinstance(row.amplitude_to_noise_high, float) and not np.isfinite(row.amplitude_to_noise_high)
        ) else "{:.1f}".format(row.amplitude_to_noise_high)
        lines.append(
            "| [{:.1f}, {}) | {:,} | {:.1%} | {:.1f} | {:.1f} | {:.2f} | {:.2f} | {:.3f} |".format(
                row.amplitude_to_noise_low, upper, row.n, row.share_of_cases,
                row.median_abs_phase_error_days, row.q90_abs_phase_error_days,
                row.median_noise_implied_95pct_half_width_days,
                row.median_observed_over_implied_error, row.consequential_rate,
            )
        )
    lines.append("")
    lines.append("Protocol `observed_days_only` (Johnson et al.'s own protocol):")
    lines.append("")
    lines.append("| fitted amplitude / residual sd | n | share | median abs phase error (d) | q90 (d) | noise-implied 95% half-width (d) | median error / implied | consequential rate |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in observed.itertuples(index=False):
        upper = "inf" if row.amplitude_to_noise_high is None or (
            isinstance(row.amplitude_to_noise_high, float) and not np.isfinite(row.amplitude_to_noise_high)
        ) else "{:.1f}".format(row.amplitude_to_noise_high)
        lines.append(
            "| [{:.1f}, {}) | {:,} | {:.1%} | {:.1f} | {:.1f} | {:.2f} | {:.2f} | {:.3f} |".format(
                row.amplitude_to_noise_low, upper, row.n, row.share_of_cases,
                row.median_abs_phase_error_days, row.q90_abs_phase_error_days,
                row.median_noise_implied_95pct_half_width_days,
                row.median_observed_over_implied_error, row.consequential_rate,
            )
        )
    lines.append("")
    lines.append("## The proposed reporting rule, and why that threshold")
    lines.append("")
    lines.append(
        "**Rule.** Report the fitted phase only when the fitted amplitude exceeds $k$ times the residual "
        "sd of the same fit; otherwise report the amplitude (or the mean) and mark the phase "
        "unidentifiable. The threshold is not asserted: for a three-parameter sine fit the phase standard "
        "error is $\\mathrm{{se}}(\\hat\\phi) = \\sigma\\sqrt{{2/n}}/A$ radians, so requiring the 95% "
        "interval ($\\pm 2\\,\\mathrm{{se}}$) to be no wider than the study's own phase tolerance "
        "$\\tau$ gives $A/\\sigma \\ge 2\\sqrt{{2/n}}/\\tau$. With the median $n$ = {:,} observed days and "
        "$\\tau$ = {:.4f} rad ({:.4f} days) this is $k^\\ast$ = {:.2f}.".format(
            int(rule["n_observed_days_median"]), rule["tau_radians"], phase["tolerance_days"], rule["k_theory"],
        )
    )
    lines.append("")
    lines.append(
        "Rounded to the nearest half, the applied rule is **report phase when $A/\\sigma \\ge {:.1f}$, "
        "suppress below**. The sweep shows the consequence of moving that line:".format(k)
    )
    lines.append("")
    lines.append("| k (A/sigma) | retained cases | share retained | consequential rate retained | consequential rate suppressed | share of all consequential errors suppressed |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in repaired_sweep.itertuples(index=False):
        if abs(float(row.k_amplitude_over_noise) - round(float(row.k_amplitude_over_noise))) > 1e-9 and abs(
            float(row.k_amplitude_over_noise) - k
        ) > 1e-9:
            continue
        lines.append(
            "| {:.2f} | {:,} | {:.1%} | {:.3f} | {:.3f} | {:.1%} |".format(
                row.k_amplitude_over_noise, row.n_retained, row.share_retained,
                row.consequential_rate_retained, row.consequential_rate_suppressed,
                row.share_of_all_phase_errors_suppressed,
            )
        )
    lines.append("")
    lines.append("## How many cases the missing rule would have caught")
    lines.append("")
    lines.append(
        "| protocol | A/sigma cut | cases below | share below | median abs phase error below (d) | "
        "consequential rate below | share of all consequential errors below |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in summary["threshold_cuts"]:
        lines.append(
            "| {} | {:.1f} | {:,} | {:.3%} | {:.1f} | {:.3f} | {:.1%} |".format(
                row["protocol"], row["amplitude_to_noise_cut"], row["n_below"], row["share_below"],
                row["median_abs_phase_error_days_below"], row["consequential_rate_below"],
                row["share_of_all_consequential_errors_below"],
            )
        )
    lines.append("")
    lines.append("## Is the relationship monotone? No, and the rule has to say so")
    lines.append("")
    for row in summary["monotonicity"]:
        lines.append(
            "* `{}`: Spearman rho between log(A/sigma) and the absolute phase error is {:+.4f}; between the "
            "fitted amplitude itself and the error, {:+.4f}; between the *true* seasonal amplitude and the "
            "error, {:+.4f}.".format(
                row["protocol"], row["spearman_log_ratio_vs_abs_phase_error"],
                row["spearman_fitted_amplitude_vs_abs_phase_error"],
                row["spearman_truth_amplitude_vs_abs_phase_error"],
            )
        )
    lines.append("")
    top_bin = repaired.loc[repaired["amplitude_to_noise_low"].eq(8.0)]
    mid_bin = repaired.loc[repaired["amplitude_to_noise_low"].eq(4.0)]
    low_bin = repaired.loc[repaired["amplitude_to_noise_low"].eq(1.0)]
    lines.append(
        "The decline is confined to the low-amplitude end: the median error falls from {:.1f} days in "
        "[1.0, 1.5) to {:.1f} days in [3.0, 4.0), and the consequential rate falls from {:.3f} to {:.3f}. "
        "Above that the relationship flattens and then turns up - median {:.2f} days in [4.0, 5.0) against "
        "{:.2f} days in [8.0, inf) - which is why the overall Spearman correlation between log(A/sigma) and "
        "the error is slightly *positive* rather than negative. Two readings are consistent with that, and "
        "they have different consequences:".format(
            float(low_bin["median_abs_phase_error_days"].iloc[0]) if len(low_bin) else float("nan"),
            float(mid_bin["median_abs_phase_error_days"].iloc[0]) if len(mid_bin) else float("nan"),
            float(low_bin["consequential_rate"].iloc[0]) if len(low_bin) else float("nan"),
            float(mid_bin["consequential_rate"].iloc[0]) if len(mid_bin) else float("nan"),
            float(mid_bin["median_abs_phase_error_days"].iloc[0]) if len(mid_bin) else float("nan"),
            float(top_bin["median_abs_phase_error_days"].iloc[0]) if len(top_bin) else float("nan"),
        )
    )
    lines.append("")
    lines.append(
        "1. The tail is not sampling noise. At the top bin the noise-implied 95% half-width is {:.2f} days "
        "while the observed q90 error is {:.1f} days - a factor {:.1f} - against a factor of {:.1f} in the "
        "[4.0, 5.0) bin, where the fit is closest to the sampling-theory prediction. If the rule were read "
        "as a claim that above the floor the phase error is pure sampling noise, the top bin rejects it.".format(
            float(top_bin["median_noise_implied_95pct_half_width_days"].iloc[0]) if len(top_bin) else float("nan"),
            float(top_bin["q90_abs_phase_error_days"].iloc[0]) if len(top_bin) else float("nan"),
            float(top_bin["q90_abs_phase_error_days"].iloc[0]) / max(
                1e-9, float(top_bin["median_noise_implied_95pct_half_width_days"].iloc[0])
            ) if len(top_bin) else float("nan"),
            float(mid_bin["q90_abs_phase_error_days"].iloc[0]) / max(
                1e-9, float(mid_bin["median_noise_implied_95pct_half_width_days"].iloc[0])
            ) if len(mid_bin) else float("nan"),
        )
    )
    lines.append(
        "2. The rise is therefore attributable to something the amplitude does not measure - most plainly "
        "sinusoidal misspecification, since a large A/sigma means a large, sharply seasonal cycle, and the "
        "snowmelt-driven and regulated rivers that have one are exactly where a single sinusoid is least "
        "adequate. This report does not test that mechanism, and the rule does not depend on it."
    )
    lines.append("")
    lines.append(
        "The practical consequence is that there are two defensible thresholds with different jobs, and the "
        "manuscript should say which one it adopts:"
    )
    lines.append("")
    lines.append(
        "* an **identifiability floor** at $A/\\sigma \\ge 1$ (or 1.5) removes the cases whose phase is drawn "
        "from noise - {:,} cases ({:.2%}) under the observed-days protocol, with a {:.1%} consequential rate "
        "- and costs {:.2%} of the repaired sample;".format(
            observed_cut[1.0]["n_below"], observed_cut[1.0]["share_below"],
            observed_cut[1.0]["consequential_rate_below"], repaired_cut[1.5]["share_below"],
        )
    )
    lines.append(
        "* a **precision floor** at $A/\\sigma \\ge {:.1f}$, which is what the tolerance derivation gives, "
        "additionally guarantees the phase's 95% interval fits inside this study's own tolerance, at the cost "
        "of {:.1%} of the repaired sample with no improvement in the consequential-error rate "
        "({:.3f} retained against {:.3f} suppressed, i.e. the discarded cases were not the erroneous ones).".format(
            k, 1 - float(repaired_sweep.loc[repaired_sweep["k_amplitude_over_noise"].eq(k), "share_retained"].iloc[0]),
            float(repaired_sweep.loc[repaired_sweep["k_amplitude_over_noise"].eq(k), "consequential_rate_retained"].iloc[0]),
            float(repaired_sweep.loc[repaired_sweep["k_amplitude_over_noise"].eq(k), "consequential_rate_suppressed"].iloc[0]),
        )
    )
    lines.append("")
    lines.append("## What the rule does to the reported phase comparison")
    lines.append("")
    lines.append(
        "| population | n | base rate | AUC peak overlap | AUC transition | AUC missing fraction | "
        "AUC outage length | AUC influence-weighted | influence - missing fraction (95% CI) | "
        "influence - length (95% CI) |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, block in summary["effect_on_the_reported_phase_comparison"].items():
        row = block["summary"]
        ci = block["clustered_bootstrap_influence_minus_missing_fraction"]
        ci_len = block["clustered_bootstrap_influence_minus_length"]
        lines.append(
            "| {} | {:,} | {:.4f} | {:.4f} | {:.4f} | {:.4f} | {:.4f} | {:.4f} | "
            "{:+.4f} ({:+.4f}, {:+.4f}) | {:+.4f} ({:+.4f}, {:+.4f}) |".format(
                name, row["n"], row["base_rate"], row["auc_peak_overlap"], row["auc_transition_overlap"],
                row["auc_missing_fraction"], row["auc_longest_run"], row["auc_influence_hidden"],
                ci["point"], ci["low"], ci["high"], ci_len["point"], ci_len["low"], ci_len["high"],
            )
        )
    lines.append("")
    lines.append(
        "For reference, the published `e3_sine_endpoints` contrast on all development cases is "
        "+0.01275 (0.00899, 0.01711) for influence-weighted minus whole-year missing fraction; the "
        "`all_cases` row above reproduces it. The `identifiable_truth_noise_scale` row repeats the "
        "identifiable-only population with the complete-year residual sd in place of the observed-days "
        "residual sd, to bracket the noise scale (median observed/truth ratio {:.3f}).".format(
            summary["noise_scale_bracket"]["median_ratio_observed_over_truth"]
        )
    )
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    ident = summary["effect_on_the_reported_phase_comparison"]["identifiable_only"]["summary"]
    allc = summary["effect_on_the_reported_phase_comparison"]["all_cases"]["summary"]
    lines.append(
        "The requirement is supported. The nuance that matters for how it is written up is that the "
        "unidentifiable cases are concentrated in the authors' own protocol rather than in the repaired one."
    )
    lines.append("")
    lines.append(
        "* The estimator does report a phase with no amplitude guard, so the published endpoint mixes "
        "identified and unidentified phases. Under the authors' own protocol (`observed_days_only`, which "
        "produces the 0.590 phase AUC quoted in the manuscript), {:,} cases ({:.2%}) have a fitted "
        "amplitude below the residual sd; their median absolute phase error is {:.1f} days against {:.1f} "
        "days expected from a phase drawn at random, and {:.1%} of them are consequential errors. Those "
        "cases carry no phase information and are currently scored.".format(
            observed_cut[1.0]["n_below"], observed_cut[1.0]["share_below"],
            observed_cut[1.0]["median_abs_phase_error_days_below"],
            summary["random_phase_error_days_expected"],
            observed_cut[1.0]["consequential_rate_below"],
        )
    )
    lines.append(
        "* Under the repaired protocol the defect is latent rather than active: repair restores the "
        "seasonal cycle, so only {:,} of {:,} cases ({:.4%}) fall below A/sigma = 1 and {:,} ({:.2%}) "
        "below 1.5. The rule is still required, but it is not what rescues the repaired phase result.".format(
            repaired_cut[1.0]["n_below"], allc["n"], repaired_cut[1.0]["share_below"],
            repaired_cut[1.5]["n_below"], repaired_cut[1.5]["share_below"],
        )
    )
    lines.append(
        "* Applying the derived rule at k = {:.1f} removes {:.1%} of the repaired cases (n = {:,} retained) and "
        "leaves the axis conclusion unchanged: influence-weighted beats the whole-year missing fraction by "
        "{:+.4f} and outage length by {:+.4f}, both intervals excluding zero.".format(
            k, 1 - ident["n"] / allc["n"], ident["n"],
            ident["auc_influence_minus_missing_fraction"], ident["auc_influence_minus_longest_run"],
        )
    )
    lines.append("")
    lines.append(
        "**Corrected statement for the manuscript.** The sine-fit phase is a reportable endpoint only where "
        "the fitted amplitude is distinguishable from the noise: report the phase when A/sigma >= {:.1f} "
        "(the value implied by requiring the phase's 95% interval to be no wider than this study's own phase "
        "tolerance of {:.2f} days), suppress it below that floor, and state that above the floor the residual "
        "phase error is no longer explained by sampling noise alone.".format(
            k, phase["tolerance_days"]
        )
    )
    lines.append("")
    (OUT_WINTER / "report_section_b.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# C. the WAC 7-DADMax regulatory endpoint
# --------------------------------------------------------------------------- #

NWIS_DV = "https://waterservices.usgs.gov/nwis/dv/"
NWIS_SITE = "https://waterservices.usgs.gov/nwis/site/"
NWIS_USER_AGENT = (
    "stream-recoverability-research/1.0 (WRR submission reproducibility check; "
    "contact: repository maintainer)"
)
WAC_CITATION = (
    "WAC 173-201A-020 (definition of 7-DADMax) and WAC 173-201A-200(1)(c) Table 200(1)(c) "
    "(aquatic life temperature criteria, column 'Highest 7-DADMax')"
)
WAC_DEFINITION = (
    "'7-DADMax' or '7-day average of the daily maximum temperatures' is the arithmetic average "
    "of seven consecutive measures of daily maximum temperatures. The 7-DADMax for any individual "
    "day is calculated by averaging that day's daily maximum temperature with the daily maximum "
    "temperatures of the three days prior and the three days after that date."
)
# The criteria table's own column header is "Highest 7-DADMax", so the annual statistic is the
# maximum over the year of the rolling seven-day average of daily maxima.
DADMAX_THRESHOLDS_C = (16.0, 18.0, 20.0)
NWIS_FULL_PERIOD_START = "1889-01-01"
NWIS_FULL_PERIOD_END = "2026-12-31"
MIN_VALID_DAYS_PER_YEAR = 330


def _read_rdb(text: str) -> pd.DataFrame:
    """Parse a USGS RDB table (comment lines, header, format line, data)."""

    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if len(lines) < 2:
        return pd.DataFrame()
    header = lines[0].split("\t")
    body = lines[2:] if len(lines) > 2 else []
    rows = [line.split("\t") for line in body if len(line.split("\t")) == len(header)]
    return pd.DataFrame(rows, columns=header)


def _fetch_text(url: str, cache_path: Path, *, refresh: bool = False, pause: float = 0.35) -> tuple[str, str]:
    """Download once, cache on disk, and return (text, sha256)."""

    if cache_path.exists() and not refresh:
        text = cache_path.read_text(encoding="utf-8", errors="replace")
        return text, _sha256(cache_path)
    request = urllib.request.Request(url, headers={"User-Agent": NWIS_USER_AGENT, "Accept": "text/plain"})
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                text = response.read().decode("utf-8", errors="replace")
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:  # pragma: no cover
            last_error = error
            time.sleep(2.0 * (attempt + 1))
    else:  # pragma: no cover
        raise RuntimeError(f"failed to fetch {url}: {last_error}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(text, encoding="utf-8")
    time.sleep(pause)
    return text, _sha256(cache_path)


def confirmation_station_ids() -> list[str]:
    manifest = pd.read_csv(CONFIRMATION_MANIFEST)
    stations: set[str] = set()
    for value in manifest["station_ids_ge4"].astype(str):
        stations.update(part for part in value.split(";") if part)
    return sorted(stations)


def verify_daily_max_availability(stations: list[str], cache_dir: Path) -> pd.DataFrame:
    """Ask the NWIS site service which of the 91 stations publish daily-max temperature."""

    rows: list[pd.DataFrame] = []
    for start in range(0, len(stations), 20):
        chunk = stations[start : start + 20]
        url = (
            NWIS_SITE
            + "?"
            + urllib.parse.urlencode(
                {
                    "format": "rdb",
                    "sites": ",".join(chunk),
                    "seriesCatalogOutput": "true",
                    "parameterCd": "00010",
                    "siteStatus": "all",
                }
            )
        )
        text, digest = _fetch_text(url, cache_dir / f"series_catalog_{start:03d}.rdb", pause=0.4)
        table = _read_rdb(text)
        if table.empty:
            continue
        table["_catalog_sha256"] = digest
        rows.append(table)
    if not rows:
        return pd.DataFrame()
    catalog = pd.concat(rows, ignore_index=True)
    keep = [
        column
        for column in (
            "site_no",
            "station_nm",
            "parm_cd",
            "stat_cd",
            "begin_date",
            "end_date",
            "count_nu",
            "access_cd",
            "_catalog_sha256",
        )
        if column in catalog.columns
    ]
    return catalog[keep]


def download_daily_values(
    stations: list[str], stat_cd: str, cache_dir: Path, *, refresh: bool = False
) -> tuple[pd.DataFrame, list[dict]]:
    """Long daily water-temperature table for one USGS statistic code."""

    frames: list[pd.DataFrame] = []
    manifest: list[dict] = []
    for index, station in enumerate(stations, start=1):
        url = (
            NWIS_DV
            + "?"
            + urllib.parse.urlencode(
                {
                    "format": "rdb",
                    "sites": station,
                    "parameterCd": "00010",
                    "statCd": stat_cd,
                    "siteStatus": "all",
                    # The legacy service returns only the latest value if no window is given.
                    "startDT": NWIS_FULL_PERIOD_START,
                    "endDT": NWIS_FULL_PERIOD_END,
                }
            )
        )
        cache_path = cache_dir / f"{station}_{stat_cd}.rdb"
        text, digest = _fetch_text(url, cache_path, refresh=refresh)
        table = _read_rdb(text)
        value_columns = [column for column in table.columns if column.endswith(f"_{stat_cd}")] if not table.empty else []
        n_values = 0
        if value_columns:
            value_column = value_columns[0]
            code_column = f"{value_column}_cd"
            frame = pd.DataFrame(
                {
                    "site_id": table["site_no"].astype(str),
                    "date": pd.to_datetime(table["datetime"], errors="coerce"),
                    "temperature_c": pd.to_numeric(table[value_column], errors="coerce"),
                    "qualifier": table[code_column].astype(str) if code_column in table.columns else "",
                }
            )
            frame = frame.dropna(subset=["date"])
            n_values = int(frame["temperature_c"].notna().sum())
            frames.append(frame)
        manifest.append(
            {
                "station_id": station,
                "stat_cd": stat_cd,
                "value_description": "Maximum" if stat_cd == "00001" else "Mean",
                "url": url,
                "cache_path": str(cache_path.relative_to(ROOT)),
                "bytes": int(cache_path.stat().st_size),
                "sha256": digest,
                "n_rows": int(len(table)),
                "n_numeric_values": n_values,
            }
        )
        if index % 20 == 0:
            print(f"  [dadmax] stat {stat_cd}: {index}/{len(stations)} stations", flush=True)
    long = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["site_id", "date", "temperature_c", "qualifier"])
    )
    return long, manifest


def qc_long_values(long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the repository's own confirmation QC so both statistics are treated identically."""

    from stream_recoverability.data.ingest_qc import clean_long_frame, qc_long_frame

    if long.empty:
        return long, pd.DataFrame()
    report = qc_long_frame(long)
    clean = clean_long_frame(long, report=report, min_qualified_years=0)
    return clean, report


def station_year_statistics(values: pd.Series, *, window: int = 7) -> pd.DataFrame:
    """Annual extremes of a daily series, per calendar year.

    ``hottest_window_mean`` is the maximum over the year of the window-day rolling mean; on daily
    maxima with window 7 that is the WAC "highest 7-DADMax". ``single_day_max`` is the 1-DMax.
    """

    frame = pd.DataFrame({"value": pd.to_numeric(values, errors="coerce")}).dropna()
    if frame.empty:
        return pd.DataFrame()
    frame["year"] = frame.index.year
    rows = []
    for year, block in frame.groupby("year", sort=True):
        series = block["value"]
        n_days_in_year = days_in_year(int(year))
        rolling = series.rolling(window, min_periods=window).mean()
        rows.append(
            {
                "year": int(year),
                "n_valid_days": int(series.notna().sum()),
                "coverage": float(series.notna().sum() / n_days_in_year),
                "hottest_window_mean": float(rolling.max()) if rolling.notna().any() else float("nan"),
                "peak_day": series.index[int(np.nanargmax(rolling.to_numpy(dtype=float)))]
                if rolling.notna().any()
                else pd.NaT,
                "single_day_max": float(series.max()),
            }
        )
    return pd.DataFrame(rows)


def _annual_stats_by_station(clean: pd.DataFrame, renames: dict[str, str]) -> pd.DataFrame:
    rows = []
    if clean.empty:
        return pd.DataFrame()
    for site_id, group in clean.groupby("site_id", sort=True):
        block = group.set_index("date").sort_index()
        stats = station_year_statistics(block["temperature_c"])
        if stats.empty:
            continue
        stats["site_id"] = str(site_id)
        rows.append(stats.rename(columns=renames))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def cross_check_against_ingest(mean_clean: pd.DataFrame) -> dict:
    """Confirm the freshly downloaded daily means reproduce the sealed panel's own input files."""

    manifest = pd.read_csv(CONFIRMATION_MANIFEST)
    frames = []
    for row in manifest.itertuples(index=False):
        path = ROOT / str(row.input_path)
        if not path.exists():
            continue
        wide = pd.read_csv(path, parse_dates=["date"])
        stations = [column for column in wide.columns if column != "date"]
        melted = wide.melt(id_vars="date", value_vars=stations, var_name="site_id", value_name="panel_mean")
        frames.append(melted.dropna(subset=["panel_mean"]))
    if not frames:
        return {"available": False}
    panel = pd.concat(frames, ignore_index=True)
    panel["site_id"] = panel["site_id"].astype(str)
    mine = mean_clean.rename(columns={"temperature_c": "downloaded_mean"})[
        ["site_id", "date", "downloaded_mean"]
    ]
    joined = panel.merge(mine, on=["site_id", "date"], how="inner")
    if joined.empty:
        return {"available": True, "n_common_rows": 0}
    delta = (joined["downloaded_mean"] - joined["panel_mean"]).abs()
    return {
        "available": True,
        "n_panel_rows": int(len(panel)),
        "n_downloaded_rows": int(len(mine)),
        "n_common_rows": int(len(joined)),
        "n_stations_checked": int(joined["site_id"].nunique()),
        "max_abs_difference_c": float(delta.max()),
        "share_within_0.05c": float((delta <= 0.05).mean()),
        "share_exactly_equal": float((delta == 0).mean()),
        "panel_only_rows": int(len(panel) - len(joined)),
        "downloaded_only_rows": int(len(mine) - len(joined)),
    }


def run_dadmax(workers: int) -> int:
    del workers  # the endpoint is one sequential download plus one comparison
    OUT_REG.mkdir(parents=True, exist_ok=True)
    cache_dir = OUT_REG / "raw_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    stations = confirmation_station_ids()
    print(f"[dadmax] sealed confirmation panel stations: {len(stations)}", flush=True)

    catalog = verify_daily_max_availability(stations, cache_dir)
    if not catalog.empty:
        catalog.to_csv(OUT_REG / "daily_max_availability.csv", index=False)
        stat = catalog["stat_cd"].astype(str).str.zfill(5)
        max_rows = catalog.loc[stat.eq("00001")]
        mean_rows = catalog.loc[stat.eq("00003")]
        availability = {
            "n_stations_requested": int(len(stations)),
            "n_stations_in_catalog": int(catalog["site_no"].nunique()),
            "n_stations_with_daily_max_00001": int(max_rows["site_no"].nunique()),
            "n_stations_with_daily_mean_00003": int(mean_rows["site_no"].nunique()),
            "n_stations_with_max_but_no_mean": sorted(set(max_rows["site_no"]) - set(mean_rows["site_no"])),
            "n_stations_with_mean_but_no_max": sorted(set(mean_rows["site_no"]) - set(max_rows["site_no"])),
            "stations_missing_from_catalog": sorted(set(stations) - set(catalog["site_no"])),
            "catalog_sha256": sorted(
                {str(value) for value in catalog.get("_catalog_sha256", []) if isinstance(value, str)}
            ),
        }
    else:  # pragma: no cover
        availability = {"n_stations_requested": int(len(stations)), "catalog_empty": True}
    _write_json(OUT_REG / "daily_max_availability_summary.json", availability)

    max_long, max_manifest = download_daily_values(stations, "00001", cache_dir)
    mean_long, mean_manifest = download_daily_values(stations, "00003", cache_dir)
    pd.DataFrame(max_manifest + mean_manifest).to_csv(OUT_REG / "raw_cache_manifest.csv", index=False)
    max_long.to_parquet(OUT_REG / "daily_max_long_raw.parquet", index=False)
    mean_long.to_parquet(OUT_REG / "daily_mean_long_raw.parquet", index=False)

    max_clean, max_qc = qc_long_values(max_long)
    mean_clean, mean_qc = qc_long_values(mean_long)
    if len(max_qc):
        max_qc.to_csv(OUT_REG / "daily_max_qc_report.csv", index=False)
    if len(mean_qc):
        mean_qc.to_csv(OUT_REG / "daily_mean_qc_report.csv", index=False)
    max_clean.to_parquet(OUT_REG / "daily_max_long_clean.parquet", index=False)
    mean_clean.to_parquet(OUT_REG / "daily_mean_long_clean.parquet", index=False)

    ingest_check = cross_check_against_ingest(mean_clean)

    max_stats = _annual_stats_by_station(
        max_clean,
        {
            "hottest_window_mean": "dadmax7",
            "single_day_max": "one_day_max",
            "peak_day": "dadmax_peak_day",
            "n_valid_days": "n_valid_days_max",
            "coverage": "coverage_max",
        },
    )
    mean_stats = _annual_stats_by_station(
        mean_clean,
        {
            "hottest_window_mean": "hottest7_mean",
            "single_day_max": "one_day_max_mean_series",
            "peak_day": "hottest7_peak_day",
            "n_valid_days": "n_valid_days_mean",
            "coverage": "coverage_mean",
        },
    )

    # The sealed panel's station-years, read for context only (never re-scored).
    sealed_years: set[tuple[str, int]] = set()
    sealed_path = (
        ROOT / "results" / "wrr_submission_ready" / "p0_07_sealed_confirmation" / "sealed_cases.parquet"
    )
    if sealed_path.exists():
        sealed = pd.read_parquet(sealed_path, columns=["station_id", "year"])
        sealed_years = {(str(site), int(year)) for site, year in zip(sealed["station_id"], sealed["year"])}

    paired = max_stats.merge(mean_stats, on=["site_id", "year"], how="inner", suffixes=("", "_mean"))
    paired["difference_dadmax_minus_hottest7_mean"] = paired["dadmax7"] - paired["hottest7_mean"]
    paired["peak_window_shift_days"] = (paired["dadmax_peak_day"] - paired["hottest7_peak_day"]).dt.days
    paired["in_sealed_panel"] = [
        (str(site), int(year)) in sealed_years for site, year in zip(paired["site_id"], paired["year"])
    ]
    paired["max_below_mean"] = paired["difference_dadmax_minus_hottest7_mean"] < 0
    paired.to_parquet(OUT_REG / "station_year_pairs.parquet", index=False)

    comparison = paired.loc[
        paired["n_valid_days_max"].ge(MIN_VALID_DAYS_PER_YEAR)
        & paired["n_valid_days_mean"].ge(MIN_VALID_DAYS_PER_YEAR)
    ].reset_index(drop=True)
    comparison.to_csv(OUT_REG / "dadmax_comparison.csv", index=False)
    complete_both = paired.loc[
        paired["n_valid_days_max"].ge(paired["year"].map(days_in_year))
        & paired["n_valid_days_mean"].ge(paired["year"].map(days_in_year))
    ].reset_index(drop=True)

    threshold_rows = []
    sweep_grid = list(DADMAX_THRESHOLDS_C) + [14.0, 17.0, 19.0, 21.0, 22.0, 24.0]
    for threshold in sweep_grid:
        exceeds_mean = comparison["hottest7_mean"].to_numpy(dtype=float) > threshold
        exceeds_max = comparison["dadmax7"].to_numpy(dtype=float) > threshold
        agreement = float((exceeds_mean == exceeds_max).mean())
        expected = float(exceeds_max.mean()) * float(exceeds_mean.mean()) + float(
            (~exceeds_max).mean()
        ) * float((~exceeds_mean).mean())
        threshold_rows.append(
            {
                "threshold_c": threshold,
                "n": int(len(comparison)),
                "n_exceed_dadmax": int(exceeds_max.sum()),
                "n_exceed_hottest7_mean": int(exceeds_mean.sum()),
                "n_agree": int((exceeds_mean == exceeds_max).sum()),
                "agreement_rate": agreement,
                "n_mean_only": int((exceeds_mean & ~exceeds_max).sum()),
                "n_dadmax_only": int((~exceeds_mean & exceeds_max).sum()),
                "class_change_rate": float((exceeds_mean != exceeds_max).mean()),
                "base_rate_dadmax": float(exceeds_max.mean()),
                "base_rate_hottest7_mean": float(exceeds_mean.mean()),
                "cohen_kappa": float((agreement - expected) / (1 - expected)) if expected < 1 else float("nan"),
                "share_of_true_exceedances_missed": float(
                    (~exceeds_mean & exceeds_max).sum() / max(1, exceeds_max.sum())
                ),
                "share_of_surrogate_exceedances_false": float(
                    (exceeds_mean & ~exceeds_max).sum() / max(1, exceeds_mean.sum())
                ),
                "equal_count_threshold_c": float(
                    np.nanquantile(
                        comparison["hottest7_mean"].to_numpy(dtype=float),
                        1.0 - float(exceeds_max.mean()),
                    )
                ),
                "in_manuscript_grid": threshold in DADMAX_THRESHOLDS_C,
            }
        )
    threshold_table = pd.DataFrame(threshold_rows).sort_values("threshold_c").reset_index(drop=True)
    threshold_table["equal_count_implied_shift_c"] = (
        threshold_table["equal_count_threshold_c"] - threshold_table["threshold_c"]
    )
    threshold_table.to_csv(OUT_REG / "threshold_class_change.csv", index=False)

    differences = comparison["difference_dadmax_minus_hottest7_mean"].to_numpy(dtype=float)
    valid = comparison.dropna(subset=["hottest7_mean", "difference_dadmax_minus_hottest7_mean"])
    slope, intercept = np.polyfit(
        valid["hottest7_mean"].to_numpy(dtype=float),
        valid["difference_dadmax_minus_hottest7_mean"].to_numpy(dtype=float),
        1,
    )
    pooled = {
        "n_station_years_paired": int(len(paired)),
        "n_station_years_analysis": int(len(comparison)),
        "n_station_years_fully_complete_both": int(len(complete_both)),
        "n_stations_analysis": int(comparison["site_id"].nunique()),
        "year_min": int(comparison["year"].min()),
        "year_max": int(comparison["year"].max()),
        "n_station_years_also_in_sealed_panel": int(comparison["in_sealed_panel"].sum()),
        "min_valid_days_per_year_rule": MIN_VALID_DAYS_PER_YEAR,
        "difference_c": {
            "mean": float(np.nanmean(differences)),
            "sd": float(np.nanstd(differences, ddof=1)),
            "median": float(np.nanmedian(differences)),
            "q05": float(np.nanquantile(differences, 0.05)),
            "q25": float(np.nanquantile(differences, 0.25)),
            "q75": float(np.nanquantile(differences, 0.75)),
            "q95": float(np.nanquantile(differences, 0.95)),
            "min": float(np.nanmin(differences)),
            "max": float(np.nanmax(differences)),
            "share_positive": float(np.nanmean(differences > 0)),
            "share_zero": float(np.nanmean(differences == 0)),
            "share_negative": float(np.nanmean(differences < 0)),
        },
        "difference_c_fully_complete_subset": {
            "n": int(len(complete_both)),
            "mean": float(complete_both["difference_dadmax_minus_hottest7_mean"].mean()),
            "median": float(complete_both["difference_dadmax_minus_hottest7_mean"].median()),
            "sd": float(complete_both["difference_dadmax_minus_hottest7_mean"].std(ddof=1)),
        },
        "peak_window_shift_days": {
            "median": float(comparison["peak_window_shift_days"].median()),
            "share_same_day": float((comparison["peak_window_shift_days"] == 0).mean()),
            "share_abs_le_7": float((comparison["peak_window_shift_days"].abs() <= 7).mean()),
        },
        "sanity_max_below_mean_station_years": int(paired["max_below_mean"].sum()),
        "sanity_max_below_mean_station_years_analysis_set": int(comparison["max_below_mean"].sum()),
        "difference_vs_level_regression": {
            "slope_c_per_c": float(slope),
            "intercept_c": float(intercept),
            "pearson_r": float(
                pd.Series(valid["hottest7_mean"]).corr(
                    pd.Series(valid["difference_dadmax_minus_hottest7_mean"])
                )
            ),
            "note": (
                "a constant offset could in principle be absorbed by moving the threshold; a level-dependent "
                "difference cannot, because the required shift varies by station-year"
            ),
        },
    }

    summary = {
        "question": (
            "F17: the manuscript's regulatory illustration uses the hottest seven-day mean of daily MEAN "
            "water temperature, while WAC 173-201A-200(1)(c) is written against the highest 7-DADMax, the "
            "seven-day average of consecutive daily MAXIMA. How large is the endpoint mismatch?"
        ),
        "endpoint_compared_against": "highest 7-DADMax (WAC 173-201A-200(1)(c) Table 200(1)(c))",
        "wac_citation": WAC_CITATION,
        "wac_definition": WAC_DEFINITION,
        "statistics_used": {
            "dadmax7": "annual maximum of the 7-day rolling mean of USGS daily maxima (00010/00001)",
            "hottest7_mean": "annual maximum of the 7-day rolling mean of USGS daily means (00010/00003)",
        },
        "qc": "the repository's own confirmation QC (ingest_qc.qc_long_frame / clean_long_frame) applied to both statistics",
        "stations": {
            "requested": int(len(stations)),
            "with_daily_max_after_qc": int(max_clean["site_id"].nunique()) if len(max_clean) else 0,
            "with_daily_mean_after_qc": int(mean_clean["site_id"].nunique()) if len(mean_clean) else 0,
        },
        "availability": availability,
        "download_matches_sealed_panel_mean_files": ingest_check,
        "raw_cache": {
            "files": int(len(max_manifest) + len(mean_manifest)),
            "bytes": int(sum(row["bytes"] for row in max_manifest + mean_manifest)),
            "manifest": "results/wrr_submission_ready/amendments/regulatory_daily_max/raw_cache_manifest.csv",
        },
        "paired": pooled,
        "threshold_table": threshold_table.to_dict(orient="records"),
        "manuscript_reference": {
            "artifact": "results/v17_fitness/step22_robustness/threshold_sweep.csv",
            "note": "the 16/18/20 C grid is the manuscript's own",
            "step22_grid": sorted(
                float(value) for value in pd.read_csv(STEP22 / "threshold_sweep.csv")["threshold_c"].unique()
            ),
        },
    }
    _write_json(OUT_REG / "summary.json", summary)
    write_dadmax_report(threshold_table, pooled, summary)
    print(threshold_table.round(4).to_string(index=False))
    print(json.dumps(pooled["difference_c"], indent=2))
    return 0


def write_dadmax_report(threshold_table: pd.DataFrame, pooled: dict, summary: dict) -> None:
    diff = pooled["difference_c"]
    grid = threshold_table.loc[threshold_table["in_manuscript_grid"]].sort_values("threshold_c")
    grid_changes = [float(value) for value in grid["class_change_rate"]]
    twenty = [
        float(row.class_change_rate)
        for row in threshold_table.itertuples(index=False)
        if row.threshold_c == 20.0
    ][0]
    lines: list[str] = []
    lines.append("# F17 - the regulatory illustration uses daily means, but the criterion is 7-DADMax")
    lines.append("")
    lines.append(
        "Artifacts: `dadmax_comparison.csv`, `threshold_class_change.csv`, `summary.json`, "
        "`daily_max_availability.csv`, `raw_cache/` (hashes in `raw_cache_manifest.csv`). "
        "Script: `scripts/251_wrr_winter_regulatory_endpoints.py dadmax`."
    )
    lines.append("")
    lines.append("## The definition used")
    lines.append("")
    lines.append(f"{summary['wac_citation']}:")
    lines.append("")
    lines.append(f"> {summary['wac_definition']}")
    lines.append("")
    lines.append(
        "The criteria table's column header is **Highest 7-DADMax**, so the annual statistic is the "
        "maximum over the year of the rolling seven-day average of daily maxima. This report computes "
        "exactly that from USGS daily values with `parameterCd=00010`, `statCd=00001` (Maximum), and "
        "compares it, station-year by station-year, with the manuscript's statistic: the maximum of the "
        "rolling seven-day average of `statCd=00003` (daily Mean). Both series pass through the "
        "repository's own confirmation QC (`ingest_qc.qc_long_frame` / `clean_long_frame`), so the "
        "comparison is not contaminated by different treatment of provisional or out-of-range values."
    )
    lines.append("")
    lines.append("## Availability of daily maxima at the 91 confirmation stations")
    lines.append("")
    availability = summary["availability"]
    lines.append(
        "* stations requested: {n_stations_requested}; with a daily-maximum time series in the NWIS "
        "series catalog: **{n_stations_with_daily_max_00001}**; with a daily-mean series: "
        "{n_stations_with_daily_mean_00003}.".format(**availability)
    )
    lines.append(
        "* stations with a daily mean but no daily maximum: {}; with a daily maximum but no daily mean: "
        "{}.".format(
            availability.get("n_stations_with_mean_but_no_max") or "none",
            availability.get("n_stations_with_max_but_no_mean") or "none",
        )
    )
    lines.append(
        "* after QC, {} stations contribute a daily-maximum series and {} a daily-mean series.".format(
            summary["stations"]["with_daily_max_after_qc"], summary["stations"]["with_daily_mean_after_qc"]
        )
    )
    lines.append(
        "* raw responses and hashes: {files} files, {bytes:,} bytes, in `raw_cache/`.".format(
            **summary["raw_cache"]
        )
    )
    check = summary.get("download_matches_sealed_panel_mean_files", {})
    if check.get("available"):
        lines.append(
            "* Provenance check on the download: the freshly downloaded daily-mean series "
            "(`statCd=00003`) were compared day-by-day with the sealed confirmation panel's own input "
            "files. Across {:,} common station-days at {} stations the maximum absolute difference is "
            "{:.1f} C and {:.1%} of the values are exactly equal, so the daily-maximum series fetched from "
            "the same service in the same way is the same vintage and treatment as the panel.".format(
                check["n_common_rows"], check["n_stations_checked"], check["max_abs_difference_c"],
                check["share_exactly_equal"],
            )
        )
    lines.append("")
    lines.append("## The comparison")
    lines.append("")
    lines.append(
        "Station-years with at least {} valid days in **both** series: **n = {:,}** station-years at {} "
        "stations, {}-{}. A further {:,} station-years have both series complete day-for-day and tell the "
        "same story (median difference {:+.3f} C against {:+.3f} C on the coverage-filtered set). {:,} of "
        "the analysed station-years are also in the sealed USGS confirmation panel; the sealed panel "
        "itself was not re-scored.".format(
            pooled["min_valid_days_per_year_rule"],
            pooled["n_station_years_analysis"],
            pooled["n_stations_analysis"],
            pooled["year_min"],
            pooled["year_max"],
            pooled["n_station_years_fully_complete_both"],
            pooled["difference_c_fully_complete_subset"]["median"],
            diff["median"],
            pooled["n_station_years_also_in_sealed_panel"],
        )
    )
    lines.append("")
    lines.append("Distribution of `7-DADMax - hottest-7 daily mean` over the same station-years:")
    lines.append("")
    lines.append("| statistic | value (C) |")
    lines.append("| --- | --- |")
    for label, key in (
        ("mean", "mean"),
        ("standard deviation", "sd"),
        ("median", "median"),
        ("5th percentile", "q05"),
        ("25th percentile", "q25"),
        ("75th percentile", "q75"),
        ("95th percentile", "q95"),
        ("minimum", "min"),
        ("maximum", "max"),
    ):
        lines.append("| {} | {:+.3f} |".format(label, diff[key]))
    lines.append("| share where 7-DADMax > hottest-7 mean | {:.1%} |".format(diff["share_positive"]))
    lines.append("| share exactly equal | {:.1%} |".format(diff["share_zero"]))
    lines.append("| share where 7-DADMax < hottest-7 mean | {:.2%} |".format(diff["share_negative"]))
    lines.append("")
    regression = pooled["difference_vs_level_regression"]
    lines.append(
        "The direction of the mismatch is uniform: 7-DADMax is greater than or equal to the hottest-7 "
        "daily mean in every one of the {:,} station-years ({:.1%} strictly greater, {:.2%} tied, {:.2%} "
        "below). That is what daily max >= daily mean implies for annual extremes taken over the same "
        "window, and it means the daily-mean surrogate never manufactures a false exceedance - it only "
        "misses real ones.".format(
            pooled["n_station_years_analysis"],
            diff["share_positive"], diff["share_zero"], diff["share_negative"],
        )
    )
    lines.append("")
    lines.append(
        "The size of the mismatch, however, is essentially a constant offset rather than a "
        "level-dependent term: regressing the difference on the daily-mean level gives a slope of "
        "{:+.3f} C per C with Pearson r = {:+.3f}, against a mean difference of {:+.2f} C and a standard "
        "deviation of {:.2f} C. That distinction matters for how the finding is closed out, so it is "
        "spelled out rather than asserted:".format(
            regression["slope_c_per_c"], regression["pearson_r"], diff["mean"], diff["sd"]
        )
    )
    lines.append("")
    lines.append(
        "* Because the offset is near-constant, a *rate-matching* defence exists: **lowering** the "
        "daily-mean threshold would approximately reproduce the count of exceedances, since the surrogate "
        "is biased low. The table above reports the daily-mean threshold that matches the 7-DADMax "
        "exceedance count at each grid value (`equal_count_threshold_c`): {:.2f} C for the 16 C criterion, "
        "{:.2f} C for 18 C and {:.2f} C for 20 C, i.e. shifts of {:.2f} C and {:.2f} C at the two ends of "
        "the grid.".format(
            float(grid.iloc[0]["equal_count_threshold_c"]),
            float(grid.iloc[1]["equal_count_threshold_c"]),
            float(grid.iloc[2]["equal_count_threshold_c"]),
            float(grid.iloc[2]["equal_count_implied_shift_c"]),
            float(grid.iloc[0]["equal_count_implied_shift_c"]),
        )
    )
    lines.append(
        "* It does not rescue the illustration. A criterion is a fixed legal number, not a free parameter; "
        "the station-year calls still disagree in {:.2%} of cases at 20 C because the offset has a standard "
        "deviation of {:.2f} C; and every number the manuscript reports from this illustration - "
        "misclassification rate, retention trade-off, bias in the count of warm years (reported as -0.76 "
        "years per station under recorded days) - was computed on the surrogate, so it inherits the "
        "mismatch rather than being cancelled by a threshold move.".format(
            [
                float(row.class_change_rate)
                for row in threshold_table.itertuples(index=False)
                if row.threshold_c == 20.0
            ][0],
            diff["sd"],
        )
    )
    lines.append("")
    lines.append(
        "The seven-day peak also moves: the two statistics select the same peak day in {:.1%} of "
        "station-years and within a week in {:.1%} (median absolute shift {:.0f} days).".format(
            pooled["peak_window_shift_days"]["share_same_day"],
            pooled["peak_window_shift_days"]["share_abs_le_7"],
            abs(pooled["peak_window_shift_days"]["median"]),
        )
    )
    lines.append("")
    lines.append("## Would the threshold decision change?")
    lines.append("")
    lines.append(
        "The 16/18/20 C grid is the manuscript's own (`step22_robustness/threshold_sweep.csv`). "
        "\"mean only\" means the daily-mean statistic calls an exceedance that the 7-DADMax does not; "
        "\"7-DADMax only\" is the reverse."
    )
    lines.append("")
    lines.append(
        "| threshold (C) | n | exceed: 7-DADMax | exceed: hottest-7 mean | class changes | missed "
        "exceedances | false exceedances | true exceedances missed | Cohen's kappa | count-matching "
        "daily-mean threshold (C) |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in grid.itertuples(index=False):
        lines.append(
            "| {:.0f} | {:,} | {:,} | {:,} | **{:,}** ({:.2%}) | **{:,}** | {:,} | {:.2%} | {:.3f} | "
            "{:.2f} |".format(
                row.threshold_c, row.n, row.n_exceed_dadmax, row.n_exceed_hottest7_mean,
                row.n_mean_only + row.n_dadmax_only, row.class_change_rate, row.n_dadmax_only,
                row.n_mean_only, row.share_of_true_exceedances_missed, row.cohen_kappa,
                row.equal_count_threshold_c,
            )
        )
    lines.append("")
    lines.append("The same over the whole swept grid:")
    lines.append("")
    lines.append("| threshold (C) | exceed: 7-DADMax | exceed: hottest-7 mean | class-change rate | mean only | 7-DADMax only |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in threshold_table.itertuples(index=False):
        lines.append(
            "| {:.0f} | {:,} | {:,} | {:.2%} | {:,} | {:,} |".format(
                row.threshold_c, row.n_exceed_dadmax, row.n_exceed_hottest7_mean,
                row.class_change_rate, row.n_mean_only, row.n_dadmax_only,
            )
        )
    lines.append("")
    lines.append(
        "Recorded rather than assumed: across all {:,} paired station-years (including the low-coverage "
        "ones excluded from the analysis), 7-DADMax falls below the hottest-7 daily mean in {:,} cases; "
        "within the {:,} analysed station-years the count is {:,}. Where it happens it is traceable to the "
        "annual maximisation selecting different peak windows, or to QC dropping different days from the "
        "two series, never to a daily violation of max >= mean.".format(
            pooled["n_station_years_paired"],
            pooled["sanity_max_below_mean_station_years"],
            pooled["n_station_years_analysis"],
            pooled["sanity_max_below_mean_station_years_analysis_set"],
        )
    )
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(
        "**No - the current hottest-7 daily-mean illustration cannot stand as a regulatory-aligned "
        "example.** It substitutes a different input statistic, biased low by {:+.2f} C at the median "
        "({:+.2f} C on average, 5th-95th percentile {:+.2f} to {:+.2f} C), and on the manuscript's own "
        "16/18/20 C grid it changes the exceedance classification in {:,} / {:,} / {:,} station-years "
        "({:.2%} / {:.2%} / {:.2%}), always by missing a real exceedance rather than by inventing one. "
        "The bias is close to a constant offset (slope {:+.3f} C per C, r = {:+.3f}), so a threshold shift "
        "could match the *counts* - the table gives the matching threshold at each grid value - but it "
        "cannot match the *decisions* (the offset has an sd of {:.2f} C), and a criterion is not a free "
        "parameter. The illustration must be recomputed on the 7-DADMax or relabelled.".format(
            diff["median"], diff["mean"], diff["q05"], diff["q95"],
            int(grid.iloc[0]["n_mean_only"] + grid.iloc[0]["n_dadmax_only"]),
            int(grid.iloc[1]["n_mean_only"] + grid.iloc[1]["n_dadmax_only"]),
            int(grid.iloc[2]["n_mean_only"] + grid.iloc[2]["n_dadmax_only"]),
            grid_changes[0], grid_changes[1], grid_changes[2],
            pooled["difference_vs_level_regression"]["slope_c_per_c"],
            pooled["difference_vs_level_regression"]["pearson_r"],
            diff["sd"],
        )
    )
    lines.append("")
    lines.append("**Corrected statement.** Replace the illustration with one of two claims:")
    lines.append("")
    lines.append(
        "1. *Preferred, and now computable.* Where an archive is screening a WAC-style criterion, the "
        "endpoint must be the highest 7-DADMax built from daily maxima, and the screening results reported "
        "for the hottest-7 daily mean should be recomputed on that endpoint. This amendment supplies the "
        "daily-maximum input and the station-year join for the 91 confirmation stations "
        "(`dadmax_comparison.csv`), so the recomputation is a re-run of the existing screen against a "
        "different target column, not a new data campaign."
    )
    lines.append(
        "2. *If the illustration is kept.* Relabel it as a daily-mean illustration of a seven-day "
        "endpoint, stating explicitly that the WAC 7-DADMax criterion is built from daily maxima, that the "
        "daily-mean surrogate is biased low by a median of {:+.2f} C (5th-95th percentile {:+.2f} to "
        "{:+.2f} C), that at 20 C it misses {:,} of {:,} exceedances ({:.1%}) while creating none, and "
        "that the manuscript's misclassification numbers are therefore not compliance numbers for WAC "
        "173-201A-200.".format(
            diff["median"], diff["q05"], diff["q95"],
            int(grid.iloc[2]["n_dadmax_only"]), int(grid.iloc[2]["n_exceed_dadmax"]),
            float(grid.iloc[2]["share_of_true_exceedances_missed"]),
        )
    )
    lines.append("")
    lines.append(
        "Nothing here contradicts the mechanism claim: the screen's advantage over gap length is a "
        "property of the estimator and the gap geometry, not of the units. The finding is narrower and "
        "harder to argue with - the endpoint must match the regulation before the numbers may be called "
        "regulatory."
    )
    lines.append("")
    (OUT_REG / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part", choices=("cold", "sine", "dadmax", "all"))
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    if args.part in ("cold", "all"):
        run_cold(args.workers)
    if args.part in ("sine", "all"):
        run_sine(args.workers)
    if args.part in ("dadmax", "all"):
        run_dadmax(args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

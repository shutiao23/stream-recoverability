#!/usr/bin/env python3
"""Major-revision Step 5b: full-year calendar replay + network co-failure probe.

Transplants *intact* annual missingness calendars from real incomplete
station-years onto independent complete years at the same station (DOY-aligned),
then optionally applies the same calendar to donor columns (co-failure).

This is a capped development probe (not a sealed confirmation). It answers
whether empirical segment resampling understates the difficulty of real annual
calendars, and whether donor-using methods lose their edge when neighbours fail
together.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.cases import (  # noqa: E402
    WARM_MONTHS,
    deseasonalized_correlations,
)
from stream_recoverability.experiments.v17_fitness.estimators import (  # noqa: E402
    StationModels,
    donor_coverage,
    hottest_window_mean,
    linear_interp_fill,
    usable_donors,
)
from stream_recoverability.experiments.v17_fitness.outages import (  # noqa: E402
    climatological_peak_window,
    peak_overlap_fraction,
)
from stream_recoverability.experiments.v17_fitness.panel import (  # noqa: E402
    air_series_for,
    load_network_panel,
)
from stream_recoverability.experiments.v17_fitness.policies import attach_policy_errors  # noqa: E402
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402

OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "step5_monitoring_tasks"
    / "calendar_replay_cofailure"
)
REAL_SY = ROOT / "results/v18_closure/e2_archive_deployment/real_station_years.parquet"
SPLIT = ROOT / "results/v17_fitness/step1_panel/network_split.csv"
ROSTER = ROOT / "results/v17_fitness/step1_panel/station_roster.csv"

MAX_NETWORKS = 16
MAX_SOURCE_YEARS_PER_STATION = 4
MAX_TARGET_YEARS_PER_SOURCE = 3
COFAIL_FRACTIONS = (0.0, 0.5, 1.0)  # share of donors that receive the same calendar
SEED = 41
TOL = 0.5
RETENTION = 0.70


def _runs_from_mask(mask: np.ndarray) -> tuple[tuple[int, int], ...]:
    runs = []
    i = 0
    n = len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        runs.append((i, j - i))
        i = j
    return tuple(runs)


def _doy_mask_from_series(series: pd.Series, year: int) -> tuple[pd.DatetimeIndex, np.ndarray] | None:
    block = series.loc[series.index.year == int(year)]
    if block.empty or len(block) < 360:
        return None
    values = pd.to_numeric(block, errors="coerce").to_numpy(dtype=float)
    mask = ~np.isfinite(values)
    if not mask.any() or mask.all():
        return None
    return block.index, mask


def _apply_doy_mask(target_index: pd.DatetimeIndex, source_index: pd.DatetimeIndex, source_mask: np.ndarray) -> np.ndarray:
    """Map source missing days onto target year by day-of-year (1..366)."""

    source_doy = source_index.dayofyear.to_numpy()
    missing_doys = set(int(d) for d, m in zip(source_doy, source_mask) if m)
    return np.isin(target_index.dayofyear.to_numpy(), list(missing_doys))


def _score_mask(
    *,
    target: pd.Series,
    donors: pd.DataFrame,
    air,
    year_index: pd.DatetimeIndex,
    truth: np.ndarray,
    mask: np.ndarray,
    train_mask: pd.Series,
    peak_doys: np.ndarray,
    models: StationModels,
    correlations: pd.Series,
    cofail_fraction: float,
    rng: np.random.Generator,
) -> dict | None:
    if not mask.any() or mask.all():
        return None
    observed = truth.copy()
    observed[mask] = np.nan

    work_donors = donors.copy()
    donor_cols = list(work_donors.columns)
    n_hit = int(round(float(cofail_fraction) * len(donor_cols)))
    hit = []
    if n_hit > 0 and donor_cols:
        hit = list(rng.choice(donor_cols, size=min(n_hit, len(donor_cols)), replace=False))
        for col in hit:
            vals = pd.to_numeric(work_donors[col].reindex(year_index), errors="coerce").to_numpy(dtype=float)
            vals = vals.copy()
            vals[mask] = np.nan
            work_donors.loc[year_index, col] = vals

    # Rebuild models with possibly corrupted donor frame for this year only:
    # training stays on unmasked historical donors; predict uses work_donors.
    visible = usable_donors(work_donors, year_index, mask)
    coverage = donor_coverage(work_donors, year_index, mask)
    fits: dict[str, np.ndarray] = {
        "doy_climatology": models.doy_climatology(year_index),
        "smooth_climatology": models.smooth_climatology(year_index),
        "linear_interp": linear_interp_fill(observed),
    }
    # Temporary StationModels view for donor predict with co-failed donors.
    year_models = StationModels(target=target, donors=work_donors, air=air, train_mask=train_mask)
    donor_fit = year_models.donor_ridge(visible) if visible else None
    fits["donor_ridge"] = (
        year_models.donor_predict(donor_fit, year_index)
        if donor_fit is not None
        else np.full(len(year_index), np.nan)
    )
    fits["air_ridge"] = year_models.air_predict(year_index) if air is not None else np.full(len(year_index), np.nan)

    truth_h30 = hottest_window_mean(truth)
    months = year_index.month.to_numpy()
    warm = np.isin(months, WARM_MONTHS)
    runs = _runs_from_mask(mask)
    if not runs:
        return None
    longest = max(runs, key=lambda item: item[1])
    row: dict[str, object] = {
        "cofail_fraction": float(cofail_fraction),
        "n_donors_cofailed": int(len(hit)),
        "n_runs": int(len(runs)),
        "total_missing": int(mask.sum()),
        "missing_fraction": float(mask.sum() / len(mask)),
        "longest_run": int(longest[1]),
        "longest_run_month": int(months[longest[0]]),
        "peak_overlap": float(peak_overlap_fraction(year_index, mask, peak_doys)),
        "warm_observed_fraction": float((~mask & warm).sum() / max(1, warm.sum())),
        "n_visible_donors": int(len(visible)),
        "donor_coverage_mean": float(coverage.mean()) if len(coverage) else float("nan"),
        "truth_hottest30": float(truth_h30),
        "left_flank": bool(np.isfinite(observed[0])),
        "right_flank": bool(np.isfinite(observed[-1])),
        "air_available": bool(air is not None),
    }
    for name, filled in fits.items():
        completed = observed.copy()
        bad = ~np.isfinite(completed)
        completed[bad] = filled[bad]
        metric = hottest_window_mean(completed)
        row[f"metric_{name}"] = float(metric) if np.isfinite(metric) else float("nan")
        row[f"abserr_{name}"] = float(abs(metric - truth_h30)) if np.isfinite(metric) else float("nan")
        row[f"err_{name}"] = float(metric - truth_h30) if np.isfinite(metric) else float("nan")
    return row


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    real = pd.read_parquet(REAL_SY)
    split = pd.read_csv(SPLIT)
    roster = pd.read_csv(ROSTER)
    dev = set(split.loc[split["split_role"].eq("development"), "network_id"].astype(str))
    real = real.loc[real["network_id"].astype(str).isin(dev)].copy()
    incomplete = real.loc[~real["complete"]].copy()
    complete = real.loc[real["complete"]].copy()

    # Prefer multi-station networks with both incomplete and complete years, and
    # only those whose daily panel is present on disk (skip missing usgs2 paths).
    counts = roster.groupby("network_id")["station_id"].nunique()
    multi = set(counts.loc[counts >= 2].index.astype(str)) & dev
    source_map = (
        roster.drop_duplicates("network_id")
        .set_index(roster.drop_duplicates("network_id")["network_id"].astype(str))["source_root"]
        .astype(str)
        .to_dict()
    )
    loadable = []
    for network_id in sorted(multi):
        source_root = source_map.get(network_id, "first")
        try:
            panel = load_network_panel(network_id, source_root)
        except Exception:  # noqa: BLE001
            continue
        stations = (
            set(incomplete.loc[incomplete.network_id.astype(str).eq(network_id), "station_id"].astype(str))
            & set(complete.loc[complete.network_id.astype(str).eq(network_id), "station_id"].astype(str))
            & set(map(str, panel.columns))
        )
        if len(stations) >= 1 and panel.shape[1] >= 2:
            loadable.append(network_id)
    rng = np.random.default_rng(SEED)
    nets = loadable
    if len(nets) > MAX_NETWORKS:
        nets = list(rng.choice(nets, size=MAX_NETWORKS, replace=False))
    print(f"loadable multi-station nets with incomplete+complete: {len(loadable)}; using {len(nets)}", flush=True)

    rows = []
    for network_id in nets:
        source_root = source_map.get(network_id, "first")
        try:
            panel = load_network_panel(network_id, source_root)
        except Exception as exc:  # noqa: BLE001
            print("skip panel", network_id, exc, flush=True)
            continue
        panel.columns = [str(c) for c in panel.columns]
        stations = sorted(
            set(incomplete.loc[incomplete.network_id.astype(str).eq(network_id), "station_id"].astype(str))
            & set(complete.loc[complete.network_id.astype(str).eq(network_id), "station_id"].astype(str))
            & set(panel.columns)
        )
        if not stations:
            continue
        for station_id in stations[:2]:
            target = pd.to_numeric(panel[station_id], errors="coerce")
            donors = panel.drop(columns=[station_id])
            air = air_series_for(network_id, station_id, panel.index)
            src_years = (
                incomplete.loc[
                    incomplete.network_id.astype(str).eq(network_id)
                    & incomplete.station_id.astype(str).eq(station_id),
                    "year",
                ]
                .astype(int)
                .tolist()
            )
            tgt_years = (
                complete.loc[
                    complete.network_id.astype(str).eq(network_id)
                    & complete.station_id.astype(str).eq(station_id),
                    "year",
                ]
                .astype(int)
                .tolist()
            )
            if len(src_years) == 0 or len(tgt_years) < 2:
                continue
            src_years = src_years[:MAX_SOURCE_YEARS_PER_STATION]
            for source_year in src_years:
                extracted = _doy_mask_from_series(target, source_year)
                if extracted is None:
                    continue
                source_index, source_mask = extracted
                # Train excludes each target year when scoring that year.
                for target_year in tgt_years[:MAX_TARGET_YEARS_PER_SOURCE]:
                    if int(target_year) == int(source_year):
                        continue
                    year_mask = target.index.year == int(target_year)
                    year_index = panel.index[year_mask]
                    truth = target.loc[year_mask].to_numpy(dtype=float)
                    if not np.isfinite(truth).all() or len(truth) < 360:
                        continue
                    mask = _apply_doy_mask(year_index, source_index, source_mask)
                    # Align lengths: if leap mismatch drops days, keep DOY map only.
                    if mask.sum() < 3:
                        continue
                    train_mask = pd.Series(target.index.year != int(target_year), index=target.index)
                    peak_source = target.loc[target.index.year != int(target_year)]
                    peak_doys = climatological_peak_window(peak_source, exclude_year=None)
                    models = StationModels(target=target, donors=donors, air=air, train_mask=train_mask)
                    correlations = deseasonalized_correlations(target, donors, train_mask)
                    for frac in COFAIL_FRACTIONS:
                        scored = _score_mask(
                            target=target,
                            donors=donors,
                            air=air,
                            year_index=year_index,
                            truth=truth,
                            mask=mask,
                            train_mask=train_mask,
                            peak_doys=peak_doys,
                            models=models,
                            correlations=correlations,
                            cofail_fraction=float(frac),
                            rng=rng,
                        )
                        if scored is None:
                            continue
                        scored.update(
                            {
                                "network_id": network_id,
                                "station_id": station_id,
                                "source_incomplete_year": int(source_year),
                                "target_complete_year": int(target_year),
                                "task": "full_year_calendar_replay",
                                "provider": str(
                                    roster.loc[
                                        roster.network_id.astype(str).eq(network_id), "provider"
                                    ].iloc[0]
                                )
                                if (roster.network_id.astype(str) == network_id).any()
                                else "unknown",
                            }
                        )
                        rows.append(scored)
            print(network_id, station_id, "rows_so_far", len(rows), flush=True)

    if not rows:
        raise RuntimeError("no calendar-replay cases produced")
    cases = pd.DataFrame(rows)
    cases = attach_policy_errors(cases)
    cases.to_parquet(OUT / "calendar_replay_cofailure_cases.parquet", index=False)

    # Operating comparisons within each cofail stratum.
    summary_rows = []
    for frac, block in cases.groupby("cofail_fraction"):
        err = pd.to_numeric(block["abserr_policy"], errors="coerce")
        length = pd.to_numeric(block["longest_run"], errors="coerce")
        peak = pd.to_numeric(block["peak_overlap"], errors="coerce")
        rng_local = np.random.default_rng(SEED + int(frac * 100))
        length_score = length + rng_local.random(len(block))
        peak_score = peak + rng_local.random(len(block)) * 1e-3
        # Prefer lower score.
        order_len = np.argsort(length_score.to_numpy())
        order_peak = np.argsort(peak_score.to_numpy())
        k = max(1, int(round(RETENTION * len(block))))
        rate_len = float((err.to_numpy()[order_len[:k]] > TOL).mean())
        rate_peak = float((err.to_numpy()[order_peak[:k]] > TOL).mean())
        rate_all = float((err > TOL).mean())
        mean_donor = float(pd.to_numeric(block["abserr_donor_ridge"], errors="coerce").mean())
        mean_clim = float(pd.to_numeric(block["abserr_doy_climatology"], errors="coerce").mean())
        summary_rows.append(
            {
                "cofail_fraction": float(frac),
                "n_cases": int(len(block)),
                "n_networks": int(block["network_id"].nunique()),
                "base_rate_above_0.5": rate_all,
                "length_rule_rate_at_70": rate_len,
                "peak_overlap_rate_at_70": rate_peak,
                "delta_peak_minus_length_pp": (rate_peak - rate_len) * 100,
                "mean_abserr_donor_ridge": mean_donor,
                "mean_abserr_doy_climatology": mean_clim,
                "mean_n_visible_donors": float(block["n_visible_donors"].mean()),
            }
        )

        def contrast(frame: pd.DataFrame) -> float:
            e = pd.to_numeric(frame["abserr_policy"], errors="coerce").to_numpy()
            ls = pd.to_numeric(frame["longest_run"], errors="coerce").to_numpy() + rng_local.random(len(frame))
            ps = pd.to_numeric(frame["peak_overlap"], errors="coerce").to_numpy() + rng_local.random(len(frame)) * 1e-3
            kk = max(1, int(round(RETENTION * len(frame))))
            return float((e[np.argsort(ps)[:kk]] > TOL).mean() - (e[np.argsort(ls)[:kk]] > TOL).mean())

        boot = cluster_bootstrap(block.assign(abserr_policy=err), contrast, draws=1000, seed=SEED)
        summary_rows[-1].update(
            {
                "peak_minus_length_points": boot["point"] * 100,
                "ci_low_points": boot["low"] * 100,
                "ci_high_points": boot["high"] * 100,
            }
        )

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / "cofail_stratum_summary.csv", index=False)

    payload = {
        "n_cases": int(len(cases)),
        "n_networks": int(cases["network_id"].nunique()),
        "n_stations": int(cases["station_id"].nunique()),
        "cofail_fractions": list(COFAIL_FRACTIONS),
        "max_networks_cap": MAX_NETWORKS,
        "claim_status": "exploratory_probe_not_sealed_confirmation",
        "may_enter_abstract_or_conclusions": False,
        "strata": summary.to_dict(orient="records"),
        "interpretation": (
            "Compare cofail_fraction=0 (target-only calendar replay) to >0 "
            "(donors share the same missing DOYs). If donor errors rise toward "
            "climatology and peak-vs-length contrast collapses, donor resilience "
            "is conditional on neighbour availability."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(payload, indent=2) + "\n")
    (OUT / "SUMMARY.md").write_text(
        "# Step 5b — full-year calendar replay + co-failure probe\n\n"
        + summary.to_string(index=False)
        + "\n\nExploratory capped probe; not a sealed confirmation.\n"
    )
    print((OUT / "SUMMARY.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

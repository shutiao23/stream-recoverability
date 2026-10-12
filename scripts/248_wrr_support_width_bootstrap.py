#!/usr/bin/env python3
"""Script 248 — adversarial finding F05 on the E6 support-width law.

What this script does, and why
------------------------------

``scripts/215_v18_support_width.py`` produced
``results/v18_closure/e6_support_width/summary.json`` from nine window widths.
Its headline number is a crossover ("the fixed peak window stops beating the
whole-year missing fraction at k* = 91 days on development, 119 days on the
opened reserved panel"). Three things were missing and one thing was wrong:

1. no uncertainty: the curve was nine point estimates and the crossover an
   interpolation between two adjacent grid points;
2. construction dependence: the conditioning window behind the
   "support-restricted" axis re-seeks the hottest k-day window in the station's
   climatology at every k, so a wider window is not the narrower window dilated
   but a different window in a different place;
3. the pre-registered falsification test in
   ``results/wrr_submission_ready/P0_06_method_freeze.json`` ("Fixed-center
   dilation vs re-seeking wide window on development only") had not been run.

This script therefore

* rebuilds the whole width curve into one joint network-clustered bootstrap
  (>= 1000 draws, default 2000): every width, axis and contrast is evaluated on
  the same resampled networks, and the crossover statistic is derived per
  replicate, giving a CI and the probability of no crossover at all;
* regenerates the v17 outage realizations for the development split from the
  same deterministic seeds the case table used (validated: the regenerated
  window-hidden columns reproduce the stored ``support_hidden_k`` exactly) in
  order to add a fixed-centre dilation axis whose centre is decision-time
  visible and truth-free;
* compares that dilation axis against the re-seeking axis at the same widths.

The width-sweep per-case scores are stored: ``results/v18_closure/
endpoint_cases.parquet`` carries ``abserr_hottest_k`` and ``support_hidden_k``
for every case at every k. The script verifies that table against the frozen
v17 case tables (``step3_cases/cases.parquet`` and
``step10_confirmation/reserved_cases.parquet``) before using it, and reproduces
the frozen summary's point estimates and crossover exactly.

Everything this script writes is `exploratory_post_open` evidence. It is not a
confirmation of anything and must not be headlined in the manuscript.

Usage
-----

    PYTHONPATH=src python3 scripts/248_wrr_support_width_bootstrap.py \
        --draws 2000 --workers 32

Writes ``results/wrr_submission_ready/amendments/e6_support_width_uncertainty/``
and caches the regenerated dilation columns under ``scratch/f05/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from scripts_support import endpoint_jobs  # noqa: E402
from stream_recoverability.experiments.v17_fitness.cases import (  # noqa: E402
    station_geometry_pool,
)
from stream_recoverability.experiments.v17_fitness.estimators import StationModels  # noqa: E402
from stream_recoverability.experiments.v17_fitness.outages import (  # noqa: E402
    climatological_peak_window,
    design_for_year,
    peak_overlap_fraction,
)
from stream_recoverability.experiments.v17_fitness.panel import load_network_panel  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    REALIZATIONS_PER_STATION_YEAR,
    STEP10_CONFIRM,
    STEP3_CASES,
    stable_seed,
)
from stream_recoverability.experiments.v18_closure.analysis import (  # noqa: E402
    auc,
    interannual_scale,
)
from stream_recoverability.experiments.v18_closure.endpoints import (  # noqa: E402
    hottest_k_window,
)
from stream_recoverability.experiments.v18_closure.paths import (  # noqa: E402
    RESULTS_ROOT as V18_RESULTS_ROOT,
    SUPPORT_WIDTHS,
    TOLERANCE_FRACTION,
)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

WIDTHS = tuple(int(w) for w in SUPPORT_WIDTHS)
PRIMARY = "primary"
FRACTIONS = {PRIMARY: float(TOLERANCE_FRACTION), "quarter": 0.25, "one": 1.0}
LABEL = "exploratory_post_open"

ENDPOINT_CASES = V18_RESULTS_ROOT / "endpoint_cases.parquet"
CASES_BY_SPLIT = {
    "development": STEP3_CASES / "cases.parquet",
    "reserved": STEP10_CONFIRM / "reserved_cases.parquet",
}
SPLIT_LABEL = {"development": "development", "reserved": "reserved_open"}

OUT_DIR = ROOT / "results" / "wrr_submission_ready" / "amendments" / "e6_support_width_uncertainty"
SCRATCH = ROOT / "scratch" / "f05"
DILATION_CACHE = SCRATCH / "e6_dilation_columns.parquet"
SEED = 20261012
KEY_COLUMNS = ["network_id", "station_id", "year", "realization_id"]

# Axes carried by the stored endpoint table. Orientation follows script 215: a
# larger value must mean a worse case, so warm_observed_fraction is negated.
AXIS_DEFS = {
    "support_reseeking": lambda frame, w: frame[f"support_hidden_{w}"].to_numpy(float),
    "peak_window_30": lambda frame, w: frame["peak_overlap"].to_numpy(float),
    "missing_fraction": lambda frame, w: frame["missing_fraction"].to_numpy(float),
    "longest_run": lambda frame, w: frame["longest_run"].to_numpy(float),
    "warm_observed_fraction": lambda frame, w: -frame["warm_observed_fraction"].to_numpy(float),
}
DILATION_AXIS_DEFS = {
    "fixed_centre_dilation": lambda frame, w: frame[f"fcd_smooth_hidden_{w}"].to_numpy(float),
    "fixed_centre_dilation_mirror": lambda frame, w: frame[f"fcd_smooth_hi_hidden_{w}"].to_numpy(float),
    "fixed_centre_dilation_raw_peak": lambda frame, w: frame[f"fcd_raw_hidden_{w}"].to_numpy(float),
}

# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _sha256(path: Path, limit: int = 1 << 22) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(limit)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _ci(values: np.ndarray) -> tuple[float, float, float]:
    """Percentile CI and standard error of a bootstrap array, NaN-tolerant."""

    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return float("nan"), float("nan"), float("nan")
    return (
        float(np.quantile(finite, 0.025)),
        float(np.quantile(finite, 0.975)),
        float(np.std(finite, ddof=1)) if finite.size > 1 else float("nan"),
    )


def _interp_first_crossing(curve: np.ndarray, widths=WIDTHS) -> float:
    """Where a contrast curve first goes from positive to non-positive.

    Identical in form to ``scripts/215_v18_support_width.py::crossover`` (log
    width interpolation between the two bracketing grid points), restricted to
    the direction that means "lost its advantage".
    """

    x = np.log(np.asarray(widths, dtype=float))
    y = np.asarray(curve, dtype=float)
    for i in range(len(y) - 1):
        if not np.isfinite(y[i]) or not np.isfinite(y[i + 1]):
            continue
        if y[i] > 0 and y[i + 1] <= 0:
            if y[i + 1] == y[i]:
                return float(np.exp(x[i]))
            t = -y[i] / (y[i + 1] - y[i])
            return float(np.exp(x[i] + t * (x[i + 1] - x[i])))
    return float("nan")


def _script215_first_sign_change(curve: np.ndarray, widths=WIDTHS) -> float:
    """The frozen script's own crossing rule, reproduced for comparability."""

    x = np.log(np.asarray(widths, dtype=float))
    y = np.asarray(curve, dtype=float)
    sign_change = np.where(np.sign(y[:-1]) != np.sign(y[1:]))[0]
    if len(sign_change) == 0:
        return float("nan")
    i = int(sign_change[0])
    if y[i + 1] == y[i]:
        return float(np.exp(x[i]))
    t = -y[i] / (y[i + 1] - y[i])
    return float(np.exp(x[i] + t * (x[i + 1] - x[i])))


def crossover_summary(curve_draws: np.ndarray, point_curve: np.ndarray) -> dict:
    """Crossover distribution of one contrast curve over bootstrap replicates."""

    draws = np.asarray(curve_draws, dtype=float)
    n = draws.shape[0]
    reasons = np.empty(n, dtype=object)
    discrete = np.full(n, np.nan)
    interp = np.full(n, np.nan)
    for row in range(n):
        y = draws[row]
        if not np.any(y > 0):
            reasons[row] = "never_positive_in_range"
        elif np.any((y[:-1] > 0) & (y[1:] <= 0)):
            reasons[row] = "crossed"
            discrete[row] = float(WIDTHS[int(np.flatnonzero(y <= 0)[0])])
        elif y[0] <= 0:
            reasons[row] = "advantage_gained_later_not_lost"
        else:
            reasons[row] = "positive_at_every_width"
        interp[row] = _interp_first_crossing(y)
    crossed = np.isfinite(interp)
    low, high, se = _ci(interp[crossed]) if crossed.any() else (np.nan, np.nan, np.nan)
    dlow, dhigh, _ = _ci(discrete[crossed]) if crossed.any() else (np.nan, np.nan, np.nan)
    counts = {str(k): int(v) for k, v in pd.Series(reasons).value_counts().items()}
    point = np.asarray(point_curve, dtype=float)
    non_positive = np.flatnonzero(point <= 0)
    return {
        "widths_days": [int(w) for w in WIDTHS],
        "point_curve": [float(v) for v in point],
        "point_crossover_days_interpolated": float(_interp_first_crossing(point)),
        "point_crossover_days_script215_rule": float(_script215_first_sign_change(point)),
        "point_crossover_grid_width_days": (
            float(WIDTHS[int(non_positive[0])]) if non_positive.size else float("nan")
        ),
        "n_draws": int(n),
        "p_crossover": float(np.mean(crossed)),
        "p_no_crossover": float(1.0 - np.mean(crossed)),
        "p_no_crossover_reason_counts": counts,
        "p_never_positive_in_range": float(np.mean(reasons == "never_positive_in_range")),
        "p_advantage_gained_later_not_lost": float(
            np.mean(reasons == "advantage_gained_later_not_lost")
        ),
        "p_positive_at_every_width": float(np.mean(reasons == "positive_at_every_width")),
        "p_positive_at_shortest_width": float(np.mean(draws[:, 0] > 0)),
        "p_positive_at_widest_width": float(np.mean(draws[:, -1] > 0)),
        "bootstrap_crossover_days_median": (
            float(np.nanmedian(interp)) if crossed.any() else float("nan")
        ),
        "bootstrap_crossover_days_ci95_low": float(low),
        "bootstrap_crossover_days_ci95_high": float(high),
        "bootstrap_crossover_days_se": float(se),
        "bootstrap_crossover_days_q10": (
            float(np.nanquantile(interp, 0.10)) if crossed.any() else float("nan")
        ),
        "bootstrap_crossover_days_q90": (
            float(np.nanquantile(interp, 0.90)) if crossed.any() else float("nan")
        ),
        "bootstrap_discrete_crossover_ci95_low": float(dlow),
        "bootstrap_discrete_crossover_ci95_high": float(dhigh),
        "bootstrap_discrete_crossover_mode_days": (
            float(pd.Series(discrete[crossed]).mode().iloc[0]) if crossed.any() else float("nan")
        ),
        "p_contrast_positive_by_width": {
            str(w): float(np.mean(draws[:, i] > 0)) for i, w in enumerate(WIDTHS)
        },
        "draw_mean_by_width": {
            str(w): float(np.nanmean(draws[:, i])) for i, w in enumerate(WIDTHS)
        },
    }


# --------------------------------------------------------------------------
# Step 1 — data path and validation against the frozen case tables
# --------------------------------------------------------------------------


def load_stored_curve() -> pd.DataFrame:
    frame = pd.read_parquet(ENDPOINT_CASES)
    frame["network_id"] = frame["network_id"].astype(str)
    frame["station_id"] = frame["station_id"].astype(str)
    return frame


def validate_against_case_tables(frame: pd.DataFrame) -> dict:
    """The stored sweep must be the frozen case tables plus the v18 endpoints."""

    shared = [
        "truth_hottest30",
        "missing_fraction",
        "peak_overlap",
        "longest_run",
        "total_missing",
        "arm",
        "split_role",
    ]
    report: dict[str, object] = {}
    total_rows = 0
    total_unmatched = 0
    all_identical = True
    for split, path in CASES_BY_SPLIT.items():
        cases = pd.read_parquet(path)
        cases["network_id"] = cases["network_id"].astype(str)
        cases["station_id"] = cases["station_id"].astype(str)
        block = frame.loc[frame["split_role"] == split]
        merged = block.merge(
            cases[KEY_COLUMNS + shared], on=KEY_COLUMNS, how="left", suffixes=("", "_frozen")
        )
        unmatched = int(merged["split_role_frozen"].isna().sum())
        diffs = {
            "truth_hottest30": float(
                (merged["truth_hottest_30"] - merged["truth_hottest30"]).abs().max()
            ),
            "missing_fraction": float(
                (merged["missing_fraction"] - merged["missing_fraction_frozen"]).abs().max()
            ),
            "peak_overlap": float(
                (merged["peak_overlap"] - merged["peak_overlap_frozen"]).abs().max()
            ),
            "arm_mismatches": int((merged["arm"] != merged["arm_frozen"]).sum()),
            "longest_run_mismatches": int(
                (merged["longest_run"] != merged["longest_run_frozen"]).sum()
            ),
            "total_missing_mismatches": int(
                (merged["total_missing"] != merged["total_missing_frozen"]).sum()
            ),
            "split_role_mismatches": int(
                (merged["split_role"] != merged["split_role_frozen"]).sum()
            ),
        }
        identical = unmatched == 0 and all(float(v) == 0.0 for v in diffs.values())
        all_identical = all_identical and identical
        total_rows += int(len(merged))
        total_unmatched += unmatched
        report[split] = {
            "case_table": str(path.relative_to(ROOT)),
            "rows_checked": int(len(merged)),
            "unmatched_rows": unmatched,
            "max_abs_diff_or_mismatch_count": diffs,
            "identical": bool(identical),
        }
    report["all_shared_columns_identical"] = bool(all_identical)
    report["rows_checked"] = total_rows
    report["unmatched_rows"] = total_unmatched
    return report


def reproduce_script215(frame: pd.DataFrame) -> dict:
    """Re-run the frozen sweep's point estimates straight from the stored table."""

    out: dict[str, object] = {"development": {}, "reserved": {}}
    for name, split in (("development", "development"), ("reserved", "reserved")):
        block = frame.loc[frame["split_role"] == split]
        rows = {}
        for width in WIDTHS:
            scale = interannual_scale(block, f"truth_hottest_{width}")
            label = (
                block[f"abserr_hottest_{width}"] > TOLERANCE_FRACTION * scale
            ).astype(float).to_numpy()
            a_support = auc(label, block[f"support_hidden_{width}"].to_numpy(dtype=float))
            a_peak = auc(label, block["peak_overlap"].to_numpy(dtype=float))
            a_missing = auc(label, block["missing_fraction"].to_numpy(dtype=float))
            rows[int(width)] = {
                "interannual_sd_c": float(scale),
                "base_rate": float(label.mean()),
                "auc_support_restricted": float(a_support),
                "auc_peak_overlap": float(a_peak),
                "auc_missing_fraction": float(a_missing),
                "support_minus_missing_fraction": float(a_support - a_missing),
                "fixed_peak_window_minus_missing_fraction": float(a_peak - a_missing),
            }
        out[name] = rows
    frozen = json.loads((V18_RESULTS_ROOT / "e6_support_width" / "summary.json").read_text())
    dev_rows = out["development"]
    differences = {
        "P1_advantage_by_width": {
            str(w): abs(
                dev_rows[w]["support_minus_missing_fraction"]
                - frozen["P1_monotone_decay"]["advantage_by_width"][str(w)]
            )
            for w in WIDTHS
        },
        "P2_advantage_by_width": {
            str(w): abs(
                dev_rows[w]["fixed_peak_window_minus_missing_fraction"]
                - frozen["P2_crossover"]["advantage_by_width"][str(w)]
            )
            for w in WIDTHS
        },
        "development_crossover_width_days": abs(
            _interp_first_crossing(
                np.array([dev_rows[w]["fixed_peak_window_minus_missing_fraction"] for w in WIDTHS])
            )
            - frozen["P2_crossover"]["crossover_width_days"]
        ),
        "reserved_crossover_width_days": abs(
            _interp_first_crossing(
                np.array(
                    [
                        out["reserved"][w]["fixed_peak_window_minus_missing_fraction"]
                        for w in WIDTHS
                    ]
                )
            )
            - frozen["reserved_crossover_width_days"]
        ),
    }
    def _leaves(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from _leaves(item)
        else:
            yield float(value)

    out["max_abs_difference_vs_frozen_summary_json"] = float(
        max(_leaves(differences))
    )
    out["differences"] = differences
    return out


# --------------------------------------------------------------------------
# Step 2 — fixed-centre dilation columns, regenerated from the frozen seeds
# --------------------------------------------------------------------------


def dilation_window_positions(centre: float, width: int, n: int, tie: str = "low") -> np.ndarray:
    """The ``width`` positions of a year closest to a fixed circular centre.

    ``centre`` is a (possibly half-integer) position on the 0..n-1 ring. The
    window is the set of ``width`` positions with the smallest circular distance
    to the centre. When two positions tie -- which happens at every odd width
    because a 30-day window's centre sits on a half day -- the tie is broken
    towards the earlier position for ``tie='low'`` and the later one for
    ``tie='high'``. The mirror variant exists because the tie is a genuine
    half-day ambiguity, not a decision the data can make.
    """

    positions = np.arange(n, dtype=float)
    delta = ((positions - centre + n / 2.0) % n) - n / 2.0
    if tie == "low":
        order = np.lexsort((delta, np.abs(delta)))
    else:
        order = np.lexsort((-delta, np.abs(delta)))
    return np.sort(order[: int(width)])


def dilation_doy_window(start_doy: int, width: int, tie: str = "low") -> np.ndarray:
    """Day-of-year window of ``width`` days centred on a climatological peak window.

    Day-of-year space, exactly as ``peak_overlap_fraction`` works, so that the
    width-30 member of the family reproduces the pipeline's own peak window.
    """

    centre = (int(start_doy) - 1) + 14.5
    doy0 = np.arange(366, dtype=float)
    delta = ((doy0 - centre + 183.0) % 366.0) - 183.0
    if tie == "low":
        order = np.lexsort((delta, np.abs(delta)))
    else:
        order = np.lexsort((-delta, np.abs(delta)))
    return np.sort(order[: int(width)]) + 1


def network_dilation_rows(job: dict) -> list[dict]:
    """Regenerate one network's outage realizations and window constructions.

    Only what the windows need is rebuilt -- the panel, the empirical geometry
    pool, the training-year climatologies and the deterministic realization
    design -- not the estimators, because the scores themselves are stored.
    """

    network_id = str(job["network_id"])
    try:
        daily = load_network_panel(network_id, str(job["source_root"]))
    except (FileNotFoundError, ValueError, KeyError):
        return []
    daily = daily.copy()
    daily.columns = [str(c) for c in daily.columns]
    pool = station_geometry_pool(daily)

    rows: list[dict] = []
    for station_id, years in job["stations"]:
        station_id = str(station_id)
        if station_id not in daily.columns:
            continue
        target = pd.to_numeric(daily[station_id], errors="coerce")
        for year in years:
            year = int(year)
            year_mask = target.index.year == year
            year_index = target.index[year_mask]
            truth = target.loc[year_mask].to_numpy(dtype=float)
            if not np.isfinite(truth).all() or len(truth) < 360:
                continue
            n = len(year_index)
            train_mask = pd.Series(~year_mask, index=target.index)
            models = StationModels(
                target=target,
                donors=daily.drop(columns=[station_id]),
                air=None,
                train_mask=train_mask,
            )
            peak_source = target.loc[target.index.year != year]
            peak_doys = climatological_peak_window(peak_source, exclude_year=None)
            climatology = models.smooth_climatology(year_index)
            if not np.isfinite(climatology).all():
                continue
            reseek_windows = {w: hottest_k_window(climatology, w) for w in WIDTHS}
            smooth_centre = (float(reseek_windows[30][0]) + 14.5) % n
            raw_start = int(peak_doys[0])
            raw_windows = {
                w: np.flatnonzero(
                    np.isin(year_index.dayofyear.to_numpy(), dilation_doy_window(raw_start, w))
                )
                for w in WIDTHS
            }
            rng = np.random.default_rng(
                stable_seed(network_id, station_id, year, "leave_one_year_out")
            )
            realizations = design_for_year(
                year_index,
                peak_doys,
                pool,
                rng=rng,
                n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3),
            )
            for realization in realizations:
                mask = realization.mask(n)
                if not mask.any() or mask.all():
                    continue
                row: dict[str, object] = {
                    "network_id": network_id,
                    "station_id": station_id,
                    "year": year,
                    "realization_id": realization.realization_id,
                    "arm": realization.arm,
                    "n_days": int(n),
                    "missing_fraction_regen": float(mask.mean()),
                    "peak_overlap_regen": peak_overlap_fraction(year_index, mask, peak_doys),
                    "peak_start_doy": raw_start,
                    "smooth30_centre": float(smooth_centre),
                }
                for w in WIDTHS:
                    reseek = reseek_windows[w]
                    fixed_smooth = dilation_window_positions(smooth_centre, w, n, tie="low")
                    fixed_smooth_hi = dilation_window_positions(smooth_centre, w, n, tie="high")
                    fixed_raw = raw_windows[w]
                    row[f"reseek_hidden_{w}"] = float(mask[reseek].mean())
                    row[f"fcd_smooth_hidden_{w}"] = float(mask[fixed_smooth].mean())
                    row[f"fcd_smooth_hi_hidden_{w}"] = float(mask[fixed_smooth_hi].mean())
                    row[f"fcd_raw_hidden_{w}"] = (
                        float(mask[fixed_raw].mean()) if len(fixed_raw) else float("nan")
                    )
                    reseek_centre = (float(reseek[0]) + (w - 1) / 2.0) % n
                    row[f"centre_shift_days_{w}"] = float(
                        ((reseek_centre - smooth_centre + n / 2.0) % n) - n / 2.0
                    )
                    row[f"windows_differ_{w}"] = bool(
                        not np.array_equal(np.sort(reseek), np.sort(fixed_smooth))
                    )
                rows.append(row)
    return rows


def build_dilation_columns(workers: int, refresh: bool) -> pd.DataFrame:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    if DILATION_CACHE.exists() and not refresh:
        cached = pd.read_parquet(DILATION_CACHE)
        cached["network_id"] = cached["network_id"].astype(str)
        cached["station_id"] = cached["station_id"].astype(str)
        return cached

    jobs = [j for j in endpoint_jobs() if j["split_role"] == "development"]
    grouped: dict[tuple[str, str], list[tuple[str, tuple[int, ...]]]] = {}
    for job in jobs:
        key = (str(job["network_id"]), str(job["source_root"]))
        grouped.setdefault(key, []).append((str(job["station_id"]), tuple(job["complete_years"])))
    work = [
        {"network_id": net, "source_root": root, "stations": stations}
        for (net, root), stations in sorted(grouped.items())
    ]
    started = time.time()
    if workers <= 1:
        blocks = [network_dilation_rows(job) for job in work]
    else:
        blocks = _parallel(network_dilation_rows, work, workers)
    rows = [row for block in blocks for row in block]
    frame = pd.DataFrame(rows).sort_values(KEY_COLUMNS, kind="mergesort").reset_index(drop=True)
    frame.to_parquet(DILATION_CACHE, index=False)
    print(
        f"[masks] regenerated {len(frame)} development cases from {len(work)} networks "
        f"in {time.time() - started:.1f}s -> {DILATION_CACHE.relative_to(ROOT)}",
        flush=True,
    )
    return frame


def _parallel(func, items, workers: int):
    if workers <= 1:
        return [func(item) for item in items]
    ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() else mp.get_context()
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        return list(pool.map(func, items, chunksize=1))


def validate_regenerated_masks(dilation: pd.DataFrame, stored: pd.DataFrame) -> dict:
    block = stored.loc[stored["split_role"] == "development"]
    merged = dilation.merge(
        block[
            KEY_COLUMNS
            + [f"support_hidden_{w}" for w in WIDTHS]
            + ["peak_overlap", "missing_fraction"]
        ],
        on=KEY_COLUMNS,
        how="left",
    )
    diffs = {
        f"support_hidden_{w}": float(
            (merged[f"reseek_hidden_{w}"] - merged[f"support_hidden_{w}"]).abs().max()
        )
        for w in WIDTHS
    }
    diffs["peak_overlap"] = float(
        (merged["peak_overlap_regen"] - merged["peak_overlap"]).abs().max()
    )
    diffs["missing_fraction"] = float(
        (merged["missing_fraction_regen"] - merged["missing_fraction"]).abs().max()
    )
    # The dilation family must reduce to the re-seeking family at the reference
    # width, otherwise the two are not on the same footing.
    diffs["fcd_smooth_at_30_equals_reseek_at_30"] = float(
        (merged["fcd_smooth_hidden_30"] - merged["reseek_hidden_30"]).abs().max()
    )
    diffs["fcd_smooth_mirror_at_30_equals_reseek_at_30"] = float(
        (merged["fcd_smooth_hi_hidden_30"] - merged["reseek_hidden_30"]).abs().max()
    )
    diffs["fcd_raw_at_30_equals_peak_overlap"] = float(
        (merged["fcd_raw_hidden_30"] - merged["peak_overlap"]).abs().max()
    )
    # leap-year note: the width-365 re-seeking window is a 365-day window even in
    # a 366-day year, so it is not exactly the whole-year missing fraction.
    leap = merged["n_days"] > 365
    diffs["width365_reseek_vs_missing_fraction_leap_years"] = float(
        (merged.loc[leap, "reseek_hidden_365"] - merged.loc[leap, "missing_fraction"]).abs().max()
    )
    return {
        "n_regenerated_cases": int(len(merged)),
        "n_unmatched": int(merged["peak_overlap"].isna().sum()),
        "max_abs_difference": diffs,
        "all_identical": bool(
            max(v for k, v in diffs.items() if not k.startswith("width365")) < 1e-12
        ),
        "leap_year_cases": int(leap.sum()),
        "leap_year_note": (
            "in a 366-day year the width-365 re-seeking window covers 365 of 366 days, so the "
            "axis is not exactly the whole-year missing fraction there; this is inherited from "
            "endpoints.hottest_k_window and is why the point contrast at k=365 is -0.0006 "
            "rather than exactly zero"
        ),
    }


# --------------------------------------------------------------------------
# Step 3 — joint network-clustered bootstrap
# --------------------------------------------------------------------------

_GRIDS: dict[str, dict] = {}


def _resampled_index(grid: dict, pick: np.ndarray) -> np.ndarray:
    keys = grid["keys"]
    groups = grid["groups"]
    return np.concatenate([groups[keys[int(i)]] for i in pick])


def _chunk(task: tuple[str, int, int]):
    name, start, stop = task
    grid = _GRIDS[name]
    if grid["kind"] == "loo":
        index_sets = [
            np.concatenate(
                [grid["groups"][k] for k in grid["keys"] if k != grid["keys"][i]]
            )
            for i in range(start, stop)
        ]
    else:
        picks = grid["picks"][start:stop]
        index_sets = [_resampled_index(grid, pick) for pick in picks]
    out = np.full((len(index_sets), len(grid["pairs"])), np.nan)
    for row, idx in enumerate(index_sets):
        if grid["kind"] == "mean":
            out[row, :] = np.nanmean(grid["extras"][idx], axis=0)
            continue
        for col, (label_key, axis_key) in enumerate(grid["pairs"]):
            out[row, col] = auc(grid["labels"][label_key][idx], grid["axes"][axis_key][idx])
    return name, start, out


def _scale_refit_chunk(task: tuple[str, int, int]):
    """Bootstrap where the tolerance scale is re-estimated inside each draw.

    The frozen curve fixes each endpoint's tolerance at its full-development
    interannual standard deviation, which makes the label a fixed but
    data-dependent quantity. Re-estimating it per replicate is the honest
    alternative, and the gap between the two is itself part of the uncertainty.
    """

    name, start, stop = task
    grid = _GRIDS[name]
    picks = grid["picks"][start:stop]
    abserr = grid["abserr"]
    row_station = grid["row_station"]
    sy_by_network = grid["sy_by_network"]
    sy_station = grid["sy_station"]
    sy_truth = grid["sy_truth"]
    fractions = grid["fractions"]
    axis_names = grid["axis_names"]
    axes = grid["axes"]
    full_scale = grid["full_scale"]
    n_station = int(sy_station.max()) + 1
    out = np.full((len(picks), len(WIDTHS), len(fractions), len(axis_names)), np.nan)
    for row, pick in enumerate(picks):
        sy_idx = np.concatenate([sy_by_network[int(i)] for i in pick])
        codes = sy_station[sy_idx]
        counts = np.bincount(codes, minlength=n_station).astype(float)
        usable = counts >= 3
        row_idx = _resampled_index(grid, pick)
        for wi, _width in enumerate(WIDTHS):
            values = sy_truth[sy_idx, wi]
            sums = np.bincount(codes, weights=values, minlength=n_station)
            sumsq = np.bincount(codes, weights=values**2, minlength=n_station)
            with np.errstate(invalid="ignore", divide="ignore"):
                var = (sumsq - sums**2 / counts) / np.maximum(counts - 1, 1)
            scale = np.full(n_station, np.nan)
            scale[usable] = np.sqrt(np.maximum(var[usable], 0.0))
            row_scale = scale[row_station[row_idx]]
            # stations with fewer than three resampled years cannot supply a
            # within-station sd; they fall back to the full-sample scale rather
            # than silently receiving a zero-variance label
            row_scale = np.where(np.isfinite(row_scale), row_scale, full_scale[wi])
            for fi, (fraction_name, fraction) in enumerate(fractions.items()):
                label = (abserr[row_idx, wi] > fraction * row_scale).astype(float)
                if not np.isfinite(label).any() or label.min() == label.max():
                    continue
                for ai, axis_name in enumerate(axis_names):
                    out[row, wi, fi, ai] = auc(label, axes[(axis_name, WIDTHS[wi])][row_idx])
    return name, start, out


def _dispatch(task: tuple[str, int, int]):
    if task[0].startswith("refit:"):
        return _scale_refit_chunk(task)
    return _chunk(task)


def bootstrap_picks(n_clusters: int, draws: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(int(seed))
    return rng.integers(0, int(n_clusters), size=(int(draws), int(n_clusters)))


def run_grids(grids: dict[str, dict], workers: int) -> dict[str, np.ndarray]:
    _GRIDS.clear()
    _GRIDS.update(grids)
    tasks: list[tuple[str, int, int]] = []
    for name, grid in grids.items():
        size = len(grid["keys"]) if grid["kind"] == "loo" else grid["picks"].shape[0]
        chunk = max(1, size // (max(1, workers) * 8))
        for start in range(0, size, chunk):
            tasks.append((name, start, min(size, start + chunk)))
    results: dict[str, np.ndarray] = {}
    pieces = _parallel(_dispatch, tasks, workers)
    for name, start, block in pieces:
        grid = grids[name]
        size = len(grid["keys"]) if grid["kind"] == "loo" else grid["picks"].shape[0]
        if name not in results:
            results[name] = np.full((size,) + block.shape[1:], np.nan)
        results[name][start : start + block.shape[0]] = block
    _GRIDS.clear()
    return results


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def panel_payload(frame: pd.DataFrame, axes: dict, fractions: dict) -> dict:
    groups = {
        str(k): np.asarray(v) for k, v in frame.groupby("network_id", sort=True).indices.items()
    }
    keys = list(groups)
    scales = {w: float(interannual_scale(frame, f"truth_hottest_{w}")) for w in WIDTHS}
    abserr = np.column_stack([frame[f"abserr_hottest_{w}"].to_numpy(float) for w in WIDTHS])
    labels: dict[tuple[str, int], np.ndarray] = {}
    for name, fraction in fractions.items():
        for i, width in enumerate(WIDTHS):
            labels[(name, width)] = (abserr[:, i] > fraction * scales[width]).astype(float)
    axis_arrays = {
        (axis_name, width): axes[axis_name](frame, width)
        for axis_name in axes
        for width in WIDTHS
    }
    sy = (
        frame.groupby(["network_id", "station_id", "year"], sort=True)[
            [f"truth_hottest_{w}" for w in WIDTHS]
        ]
        .first()
        .reset_index()
    )
    sy_station = pd.factorize(
        sy["network_id"].astype(str) + "\x1f" + sy["station_id"].astype(str)
    )[0]
    sy_truth = sy[[f"truth_hottest_{w}" for w in WIDTHS]].to_numpy(float)
    network_pos = pd.Index(keys).get_indexer(sy["network_id"].astype(str))
    row_keys = pd.MultiIndex.from_frame(frame[["network_id", "station_id", "year"]])
    sy_keys = pd.MultiIndex.from_frame(sy[["network_id", "station_id", "year"]])
    row_sy = sy_keys.get_indexer(row_keys)
    if (row_sy < 0).any():
        raise SystemExit("station-year key mismatch while building the refit grid")
    return {
        "keys": keys,
        "groups": groups,
        "labels": labels,
        "axes": axis_arrays,
        "scales": scales,
        "abserr": abserr,
        "row_station": sy_station[row_sy],
        "sy_station": sy_station,
        "sy_truth": sy_truth,
        "sy_by_network": [np.flatnonzero(network_pos == i) for i in range(len(keys))],
        "n_cases": int(len(frame)),
    }


def auc_grid(payload: dict, fractions: list[str], axes: list[str], picks: np.ndarray) -> tuple[dict, list]:
    pairs = [
        ((fraction, width), (axis_name, width))
        for fraction in fractions
        for width in WIDTHS
        for axis_name in axes
    ]
    return (
        {
            "kind": "auc",
            "keys": payload["keys"],
            "groups": payload["groups"],
            "labels": payload["labels"],
            "axes": payload["axes"],
            "pairs": pairs,
            "picks": picks,
        },
        pairs,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draws", type=int, default=2000, help="bootstrap replicates (>= 1000)")
    parser.add_argument("--workers", type=int, default=min(32, os.cpu_count() or 1))
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--refresh-masks", action="store_true", help="ignore the scratch cache")
    parser.add_argument("--skip-masks", action="store_true", help="reuse the scratch cache")
    args = parser.parse_args()
    if args.draws < 1000:
        raise SystemExit("--draws must be >= 1000 for a reportable interval")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)

    started = time.time()
    stored = load_stored_curve()
    development = stored.loc[stored["split_role"] == "development"].reset_index(drop=True)
    reserved = stored.loc[stored["split_role"] == "reserved"].reset_index(drop=True)

    validation = {
        "stored_table_vs_frozen_case_tables": validate_against_case_tables(stored),
        "script215_point_estimates_reproduced": reproduce_script215(stored),
    }
    print(
        "[validate] stored table reproduces the frozen sweep, max abs diff "
        f"{validation['script215_point_estimates_reproduced']['max_abs_difference_vs_frozen_summary_json']:.2e}",
        flush=True,
    )

    if args.skip_masks:
        dilation = pd.read_parquet(DILATION_CACHE)
        dilation["network_id"] = dilation["network_id"].astype(str)
        dilation["station_id"] = dilation["station_id"].astype(str)
    else:
        dilation = build_dilation_columns(workers=args.workers, refresh=args.refresh_masks)
    validation["regenerated_masks_vs_stored"] = validate_regenerated_masks(dilation, stored)
    print(
        "[validate] regenerated masks identical to stored: "
        f"{validation['regenerated_masks_vs_stored']['all_identical']}",
        flush=True,
    )
    merged = development.merge(dilation, on=KEY_COLUMNS, how="left")
    if merged["reseek_hidden_30"].isna().any():
        raise SystemExit("dilation join lost development cases")

    dev_payload = panel_payload(development, AXIS_DEFS, FRACTIONS)
    res_payload = panel_payload(reserved, AXIS_DEFS, {PRIMARY: FRACTIONS[PRIMARY]})
    dil_payload = panel_payload(merged, {**AXIS_DEFS, **DILATION_AXIS_DEFS}, FRACTIONS)

    # point estimates, full sample, frozen fixed-scale rule -- computed before
    # any bootstrap so that every row of curve_with_ci.csv carries one
    points: dict[tuple[str, float, int, str], float] = {}
    for label, frame in (("development", development), ("reserved_open", reserved)):
        fractions = FRACTIONS if label == "development" else {PRIMARY: FRACTIONS[PRIMARY]}
        axes = AXIS_DEFS if label == "development" else AXIS_DEFS
        for fraction_name, fraction in fractions.items():
            for width in WIDTHS:
                scale = interannual_scale(frame, f"truth_hottest_{width}")
                y = (frame[f"abserr_hottest_{width}"] > fraction * scale).astype(float).to_numpy()
                for axis_name, axis_fn in axes.items():
                    points[(label, fraction_name, width, axis_name)] = float(
                        auc(y, axis_fn(frame, width))
                    )
    # conditioning matrix points (development, primary fraction)
    for endpoint_width in WIDTHS:
        scale = dev_payload["scales"][endpoint_width]
        y = (
            development[f"abserr_hottest_{endpoint_width}"] > FRACTIONS[PRIMARY] * scale
        ).astype(float).to_numpy()
        for conditioning_width in WIDTHS:
            points[("development", PRIMARY, endpoint_width, f"cond_{conditioning_width}")] = float(
                auc(y, development[f"support_hidden_{conditioning_width}"].to_numpy(float))
            )
    # dilation-axis points, on the merged frame the bootstrap actually scores
    for fraction_name, fraction in FRACTIONS.items():
        for width in WIDTHS:
            scale = dev_payload["scales"][width]
            y = (merged[f"abserr_hottest_{width}"] > fraction * scale).astype(float).to_numpy()
            for axis_name, axis_fn in DILATION_AXIS_DEFS.items():
                points[("development", fraction_name, width, axis_name)] = float(
                    auc(y, axis_fn(merged, width))
                )

    dev_picks = bootstrap_picks(len(dev_payload["keys"]), args.draws, args.seed)
    res_picks = bootstrap_picks(len(res_payload["keys"]), args.draws, args.seed + 1)

    curve_axes = list(AXIS_DEFS)
    dil_axes = list(DILATION_AXIS_DEFS) + ["support_reseeking", "peak_window_30", "missing_fraction"]
    grids: dict[str, dict] = {}
    grids["dev_curve"], dev_curve_pairs = auc_grid(dev_payload, list(FRACTIONS), curve_axes, dev_picks)
    grids["res_curve"], res_curve_pairs = auc_grid(res_payload, [PRIMARY], curve_axes, res_picks)
    grids["dev_dilation"], dil_pairs = auc_grid(dil_payload, list(FRACTIONS), dil_axes, dev_picks)

    # conditioning matrix: label at endpoint width k against the re-seeking
    # window at conditioning width c (the diagonal is the estimand's own support)
    cond_pairs = [
        ((PRIMARY, endpoint_width), (f"cond_{conditioning_width}", endpoint_width))
        for endpoint_width in WIDTHS
        for conditioning_width in WIDTHS
    ]
    cond_axes = dict(dev_payload["axes"])
    for endpoint_width in WIDTHS:
        for conditioning_width in WIDTHS:
            cond_axes[(f"cond_{conditioning_width}", endpoint_width)] = development[
                f"support_hidden_{conditioning_width}"
            ].to_numpy(float)
    grids["dev_conditioning"] = {
        "kind": "auc",
        "keys": dev_payload["keys"],
        "groups": dev_payload["groups"],
        "labels": dev_payload["labels"],
        "axes": cond_axes,
        "pairs": cond_pairs,
        "picks": dev_picks,
    }

    refit_axes = list(AXIS_DEFS)
    grids["refit:dev_curve"] = {
        "kind": "refit",
        "keys": dev_payload["keys"],
        "groups": dev_payload["groups"],
        "axes": dev_payload["axes"],
        "fractions": {PRIMARY: FRACTIONS[PRIMARY]},
        "axis_names": refit_axes,
        "abserr": dev_payload["abserr"],
        "row_station": dev_payload["row_station"],
        "sy_by_network": dev_payload["sy_by_network"],
        "sy_station": dev_payload["sy_station"],
        "sy_truth": dev_payload["sy_truth"],
        "full_scale": np.array([dev_payload["scales"][w] for w in WIDTHS], dtype=float),
        "picks": dev_picks,
    }

    loo_pairs = [
        ((PRIMARY, width), (axis_name, width))
        for width in WIDTHS
        for axis_name in ("support_reseeking", "peak_window_30", "missing_fraction")
    ]
    grids["loo_dev"] = {
        "kind": "loo",
        "keys": dev_payload["keys"],
        "groups": dev_payload["groups"],
        "labels": dev_payload["labels"],
        "axes": dev_payload["axes"],
        "pairs": loo_pairs,
        "picks": dev_picks,
    }

    geometry_names: list[str] = []
    geometry_columns: list[np.ndarray] = []
    for width in WIDTHS:
        geometry_names += [
            f"abs_centre_shift_days_{width}",
            f"centre_shift_days_{width}",
            f"windows_differ_{width}",
            f"hidden_difference_fcd_minus_reseek_{width}",
        ]
        geometry_columns += [
            np.abs(merged[f"centre_shift_days_{width}"].to_numpy(float)),
            merged[f"centre_shift_days_{width}"].to_numpy(float),
            merged[f"windows_differ_{width}"].to_numpy(float),
            (merged[f"fcd_smooth_hidden_{width}"] - merged[f"reseek_hidden_{width}"]).to_numpy(float),
        ]
    grids["dev_geometry"] = {
        "kind": "mean",
        "keys": dev_payload["keys"],
        "groups": dev_payload["groups"],
        "labels": {},
        "axes": {},
        "pairs": [(None, name) for name in geometry_names],
        "extras": np.column_stack(geometry_columns),
        "picks": dev_picks,
    }

    n_statistics = sum(
        len(grid["pairs"])
        if grid["kind"] != "refit"
        else len(WIDTHS) * len(grid["fractions"]) * len(grid["axis_names"])
        for grid in grids.values()
    )
    print(
        f"[boot] {args.draws} draws, {len(grids)} grids, {n_statistics} statistics per draw "
        f"on {args.workers} workers",
        flush=True,
    )
    results = run_grids(grids, workers=args.workers)
    if results["refit:dev_curve"].ndim == 4:
        # flatten (draw, width, fraction, axis) into the same pair order the AUC
        # rows use, so that the assembly step treats it like any other grid
        block = results["refit:dev_curve"]
        results["refit:dev_curve"] = block.reshape(block.shape[0], -1)
    print(f"[boot] bootstrap done at {time.time() - started:.1f}s", flush=True)

    return _assemble(
        args, started, results, grids, validation, points, dev_payload, res_payload,
        dil_payload, dev_curve_pairs, res_curve_pairs, dil_pairs, cond_pairs, dil_axes,
        geometry_names,
    )


# --------------------------------------------------------------------------
# assembly and outputs
# --------------------------------------------------------------------------


def _assemble(
    args, started, results, grids, validation, points, dev_payload, res_payload,
    dil_payload, dev_curve_pairs, res_curve_pairs, dil_pairs, cond_pairs, dil_axes,
    geometry_names,
):
    refit_axes = list(AXIS_DEFS)
    refit_pairs = [
        ((PRIMARY, width), (axis_name, width)) for width in WIDTHS for axis_name in refit_axes
    ]
    loo_pairs = [
        ((PRIMARY, width), (axis_name, width))
        for width in WIDTHS
        for axis_name in ("support_reseeking", "peak_window_30", "missing_fraction")
    ]
    records: list[dict] = []
    n_cases = {
        "development": dev_payload["n_cases"],
        "reserved_open": res_payload["n_cases"],
    }
    n_clusters = {name: len(grids[name]["keys"]) for name in grids}

    def auc_rows(
        grid_name, panel, pairs, fraction_names, axes, scale_mode="fixed_full_sample",
        source="curve",
    ):
        draws = results[grid_name]
        for fraction_name in fraction_names:
            for width in WIDTHS:
                for axis_name in axes:
                    col = pairs.index(((fraction_name, width), (axis_name, width)))
                    values = draws[:, col]
                    low, high, se = _ci(values)
                    records.append(
                        {
                            "label": LABEL,
                            "panel": panel,
                            "source": source,
                            "tolerance_fraction": float(FRACTIONS[fraction_name]),
                            "tolerance_fraction_name": fraction_name,
                            "scale_mode": scale_mode,
                            "statistic_kind": "auc",
                            "axis": axis_name,
                            "left": "",
                            "right": "",
                            "width_days": int(width),
                            "conditioning_width_days": -1,
                            "point": (
                                float(points.get((panel, fraction_name, width, axis_name), np.nan))
                                if scale_mode == "fixed_full_sample"
                                else float("nan")
                            ),
                            "boot_mean": float(np.nanmean(values)),
                            "low": float(low),
                            "high": float(high),
                            "se": float(se),
                            "p_at_or_above_null": float(np.mean(values > 0.5)),
                            "n_draws": int(values.size),
                            "n_cases": int(n_cases.get(panel, 0)),
                            "n_clusters": int(n_clusters[grid_name]),
                        }
                    )

    auc_rows("dev_curve", "development", dev_curve_pairs, list(FRACTIONS), list(AXIS_DEFS))
    auc_rows("res_curve", "reserved_open", res_curve_pairs, [PRIMARY], list(AXIS_DEFS))
    auc_rows(
        "dev_dilation", "development", dil_pairs, list(FRACTIONS), list(DILATION_AXIS_DEFS),
        source="dilation",
    )
    auc_rows(
        "refit:dev_curve", "development", refit_pairs, [PRIMARY], refit_axes,
        scale_mode="refit_within_draw", source="refit",
    )

    # conditioning matrix rows
    conditioning: dict[str, dict] = {}
    for endpoint_width in WIDTHS:
        row: dict[str, object] = {}
        for conditioning_width in WIDTHS:
            col = cond_pairs.index(
                ((PRIMARY, endpoint_width), (f"cond_{conditioning_width}", endpoint_width))
            )
            values = results["dev_conditioning"][:, col]
            low, high, se = _ci(values)
            row[str(conditioning_width)] = {
                "auc_mean": float(np.nanmean(values)),
                "low": float(low),
                "high": float(high),
                "se": float(se),
            }
            records.append(
                {
                    "label": LABEL,
                    "panel": "development",
                    "source": "conditioning",
                    "tolerance_fraction": float(FRACTIONS[PRIMARY]),
                    "tolerance_fraction_name": PRIMARY,
                    "scale_mode": "fixed_full_sample",
                    "statistic_kind": "auc",
                    "axis": "support_reseeking",
                    "left": "",
                    "right": "",
                    "width_days": int(endpoint_width),
                    "conditioning_width_days": int(conditioning_width),
                    "point": float(
                        points.get(( "development", PRIMARY, endpoint_width, f"cond_{conditioning_width}"), np.nan)
                    ),
                    "boot_mean": float(np.nanmean(values)),
                    "low": float(low),
                    "high": float(high),
                    "se": float(se),
                    "p_at_or_above_null": float(np.mean(values > 0.5)),
                    "n_draws": int(values.size),
                    "n_cases": int(n_cases["development"]),
                    "n_clusters": int(n_clusters["dev_conditioning"]),
                }
            )
        means = {int(w): row[str(w)]["auc_mean"] for w in WIDTHS}
        best = int(max(means, key=means.get))
        runner_up = max((w for w in means if w != best), key=lambda w: means[w])
        row["best_conditioning_width_days_mean_auc"] = best
        row["second_best_conditioning_width_days"] = int(runner_up)
        row["auc_gap_best_to_second_best"] = float(means[best] - means[runner_up])
        row["auc_gap_best_to_own_support"] = float(means[best] - means[int(endpoint_width)])
        row["penalty_of_universal_conditioning_window"] = {
            str(w): float(means[best] - means[int(w)]) for w in WIDTHS
        }
        separation = {}
        for other in WIDTHS:
            if other == best:
                continue
            diff = results["dev_conditioning"][
                :, cond_pairs.index(((PRIMARY, endpoint_width), (f"cond_{best}", endpoint_width)))
            ] - results["dev_conditioning"][
                :, cond_pairs.index(((PRIMARY, endpoint_width), (f"cond_{other}", endpoint_width)))
            ]
            clow, chigh, _ = _ci(diff)
            separation[str(other)] = {
                "auc_difference": float(np.nanmean(diff)),
                "low": float(clow),
                "high": float(chigh),
                "ci_excludes_zero": bool(clow > 0 or chigh < 0),
            }
        row["separation_of_best_from_other_widths"] = separation
        conditioning[str(endpoint_width)] = row

    # contrasts
    contrast_specs = [
        ("dev_curve", "development", "support_reseeking", "missing_fraction",
         "support_restricted_minus_missing_fraction"),
        ("dev_curve", "development", "peak_window_30", "missing_fraction",
         "fixed_peak_window_30_minus_missing_fraction"),
        ("dev_curve", "development", "support_reseeking", "peak_window_30",
         "support_restricted_minus_fixed_peak_window_30"),
        ("dev_curve", "development", "longest_run", "missing_fraction",
         "longest_run_minus_missing_fraction"),
        ("res_curve", "reserved_open", "support_reseeking", "missing_fraction",
         "support_restricted_minus_missing_fraction"),
        ("res_curve", "reserved_open", "peak_window_30", "missing_fraction",
         "fixed_peak_window_30_minus_missing_fraction"),
        ("res_curve", "reserved_open", "support_reseeking", "peak_window_30",
         "support_restricted_minus_fixed_peak_window_30"),
        ("dev_dilation", "development", "fixed_centre_dilation", "support_reseeking",
         "fixed_centre_dilation_minus_reseeking"),
        ("dev_dilation", "development", "fixed_centre_dilation_mirror", "support_reseeking",
         "fixed_centre_dilation_mirror_minus_reseeking"),
        ("dev_dilation", "development", "fixed_centre_dilation_raw_peak", "support_reseeking",
         "fixed_centre_dilation_raw_peak_minus_reseeking"),
        ("dev_dilation", "development", "fixed_centre_dilation", "missing_fraction",
         "fixed_centre_dilation_minus_missing_fraction"),
        ("dev_dilation", "development", "fixed_centre_dilation_raw_peak", "missing_fraction",
         "fixed_centre_dilation_raw_peak_minus_missing_fraction"),
        ("dev_dilation", "development", "fixed_centre_dilation_mirror", "missing_fraction",
         "fixed_centre_dilation_mirror_minus_missing_fraction"),
    ]
    pairs_by_grid = {
        "dev_curve": dev_curve_pairs,
        "res_curve": res_curve_pairs,
        "dev_dilation": dil_pairs,
    }

    def contrast_draws(grid_name, pairs, fraction_name, width, left, right):
        a = results[grid_name][:, pairs.index(((fraction_name, width), (left, width)))]
        b = results[grid_name][:, pairs.index(((fraction_name, width), (right, width)))]
        return a - b

    crossovers: dict[str, dict] = {}
    for grid_name, panel, left, right, name in contrast_specs:
        pairs = pairs_by_grid[grid_name]
        fraction_names = list(FRACTIONS) if grid_name != "res_curve" else [PRIMARY]
        block: dict[str, dict] = {}
        for fraction_name in fraction_names:
            full = np.column_stack(
                [
                    contrast_draws(grid_name, pairs, fraction_name, w, left, right)
                    for w in WIDTHS
                ]
            )
            point = np.array(
                [
                    points.get((panel, fraction_name, w, left), np.nan)
                    - points.get((panel, fraction_name, w, right), np.nan)
                    for w in WIDTHS
                ]
            )
            if not np.isfinite(point).all():
                point = np.array([np.nanmean(full[:, i]) for i in range(len(WIDTHS))])
            summary = crossover_summary(full, point)
            summary.update(
                {
                    "left": left,
                    "right": right,
                    "panel": panel,
                    "tolerance_fraction": float(FRACTIONS[fraction_name]),
                    "tolerance_fraction_name": fraction_name,
                    "label": LABEL,
                }
            )
            block[fraction_name] = summary
            for i, width in enumerate(WIDTHS):
                clow, chigh, cse = _ci(full[:, i])
                records.append(
                    {
                        "label": LABEL,
                        "panel": panel,
                        "source": "contrast",
                        "tolerance_fraction": float(FRACTIONS[fraction_name]),
                        "tolerance_fraction_name": fraction_name,
                        "scale_mode": "fixed_full_sample",
                        "statistic_kind": "contrast",
                        "axis": name,
                        "left": left,
                        "right": right,
                        "width_days": int(width),
                        "conditioning_width_days": -1,
                        "point": float(point[i]),
                        "boot_mean": float(np.nanmean(full[:, i])),
                        "low": float(clow),
                        "high": float(chigh),
                        "se": float(cse),
                        "p_at_or_above_null": float(np.mean(full[:, i] > 0)),
                        "n_draws": int(full.shape[0]),
                        "n_cases": int(n_cases.get(panel, 0)),
                        "n_clusters": int(n_clusters[grid_name]),
                    }
                )
        crossovers[f"{panel} | {name}"] = block

    # scale-refit sensitivity (development, primary fraction)
    refit_summary: dict[str, dict] = {}
    refit_crossovers: dict[str, dict] = {}
    for width in WIDTHS:
        entry: dict[str, object] = {}
        for axis_name in refit_axes:
            fixed = results["dev_curve"][
                :, dev_curve_pairs.index(((PRIMARY, width), (axis_name, width)))
            ]
            refit_values = results["refit:dev_curve"][
                :, refit_pairs.index(((PRIMARY, width), (axis_name, width)))
            ]
            low, high, _ = _ci(refit_values)
            dlow, dhigh, _ = _ci(refit_values - fixed)
            entry[axis_name] = {
                "auc_refit_mean": float(np.nanmean(refit_values)),
                "auc_refit_low": float(low),
                "auc_refit_high": float(high),
                "auc_fixed_mean": float(np.nanmean(fixed)),
                "difference_refit_minus_fixed_mean": float(np.nanmean(refit_values - fixed)),
                "difference_low": float(dlow),
                "difference_high": float(dhigh),
                "difference_ci_excludes_zero": bool(dlow > 0 or dhigh < 0),
            }
        refit_summary[str(width)] = entry
    for left, right, name in (
        ("support_reseeking", "missing_fraction", "support_restricted_minus_missing_fraction"),
        ("peak_window_30", "missing_fraction", "fixed_peak_window_30_minus_missing_fraction"),
    ):
        curves = np.column_stack(
            [
                results["refit:dev_curve"][:, refit_pairs.index(((PRIMARY, w), (left, w)))]
                - results["refit:dev_curve"][:, refit_pairs.index(((PRIMARY, w), (right, w)))]
                for w in WIDTHS
            ]
        )
        summary = crossover_summary(
            curves,
            np.array(
                [
                    points.get(("development", PRIMARY, w, left), np.nan)
                    - points.get(("development", PRIMARY, w, right), np.nan)
                    for w in WIDTHS
                ]
            ),
        )
        summary.update({"left": left, "right": right, "panel": "development",
                        "tolerance_fraction": float(FRACTIONS[PRIMARY]),
                        "tolerance_fraction_name": PRIMARY, "scale_mode": "refit_within_draw",
                        "label": LABEL})
        refit_crossovers[name] = {PRIMARY: summary}

    # leave-one-network-out jackknife
    jackknife: dict[str, dict] = {}
    for left, right, name in (
        ("support_reseeking", "missing_fraction", "support_restricted_minus_missing_fraction"),
        ("peak_window_30", "missing_fraction", "fixed_peak_window_30_minus_missing_fraction"),
    ):
        curves = np.column_stack(
            [
                results["loo_dev"][:, loo_pairs.index(((PRIMARY, w), (left, w)))]
                - results["loo_dev"][:, loo_pairs.index(((PRIMARY, w), (right, w)))]
                for w in WIDTHS
            ]
        )
        crossings = np.array([_interp_first_crossing(curves[i]) for i in range(curves.shape[0])])
        finite = crossings[np.isfinite(crossings)]
        se = float("nan")
        if finite.size > 1:
            # the usual delete-one jackknife SE: the raw spread of LOO replicates
            # is NOT a confidence interval, because each replicate still holds
            # n-1 of the n networks
            se = float(np.sqrt((finite.size - 1) / finite.size * np.sum((finite - finite.mean()) ** 2)))
        jackknife[name] = {
            "n_replicates": int(curves.shape[0]),
            "n_with_crossover": int(finite.size),
            "p_no_crossover": float(1.0 - finite.size / curves.shape[0]),
            "crossover_days_min": float(finite.min()) if finite.size else float("nan"),
            "crossover_days_max": float(finite.max()) if finite.size else float("nan"),
            "crossover_days_median": float(np.median(finite)) if finite.size else float("nan"),
            "crossover_days_q25": float(np.quantile(finite, 0.25)) if finite.size else float("nan"),
            "crossover_days_q75": float(np.quantile(finite, 0.75)) if finite.size else float("nan"),
            "jackknife_se_days": se,
            "jackknife_ci95_days": (
                [float(finite.mean() - 1.96 * se), float(finite.mean() + 1.96 * se)]
                if np.isfinite(se)
                else [float("nan"), float("nan")]
            ),
            "note": (
                "the raw leave-one-out range is not a confidence interval: removing one of 110 "
                "networks leaves 99% of the data, so it understates sampling variability by "
                "roughly sqrt(n_networks). The jackknife SE and its normal CI are the "
                "comparable quantities"
            ),
            "contrast_positive_at_30_days": float(np.mean(curves[:, WIDTHS.index(30)] > 0)),
            "contrast_positive_at_90_days": float(np.mean(curves[:, WIDTHS.index(90)] > 0)),
            "contrast_positive_at_365_days": float(np.mean(curves[:, WIDTHS.index(365)] > 0)),
        }

    # dilation vs re-seeking table
    geometry = results["dev_geometry"]
    dilation_rows = []
    for width in WIDTHS:
        row: dict[str, object] = {
            "label": LABEL,
            "panel": "development",
            "tolerance_fraction": float(FRACTIONS[PRIMARY]),
            "width_days": int(width),
            "n_cases": int(dev_payload["n_cases"]),
            "n_networks": len(dev_payload["keys"]),
            "n_draws": int(args.draws),
        }
        for axis_name in dil_axes:
            values = results["dev_dilation"][:, dil_pairs.index(((PRIMARY, width), (axis_name, width)))]
            low, high, _ = _ci(values)
            row[f"auc_{axis_name}"] = float(np.nanmean(values))
            row[f"auc_{axis_name}_low"] = float(low)
            row[f"auc_{axis_name}_high"] = float(high)
            row[f"auc_{axis_name}_p_gt_half"] = float(np.mean(values > 0.5))
        for left, right, name in (
            ("fixed_centre_dilation", "support_reseeking", "fcd_minus_reseeking"),
            ("fixed_centre_dilation_mirror", "support_reseeking", "fcd_mirror_minus_reseeking"),
            ("fixed_centre_dilation_raw_peak", "support_reseeking", "fcd_raw_minus_reseeking"),
            ("fixed_centre_dilation", "missing_fraction", "fcd_minus_missing"),
            ("fixed_centre_dilation_mirror", "missing_fraction", "fcd_mirror_minus_missing"),
            ("fixed_centre_dilation_raw_peak", "missing_fraction", "fcd_raw_minus_missing"),
            ("support_reseeking", "missing_fraction", "reseek_minus_missing"),
            ("peak_window_30", "missing_fraction", "peak30_minus_missing"),
        ):
            diff = contrast_draws("dev_dilation", dil_pairs, PRIMARY, width, left, right)
            low, high, _ = _ci(diff)
            row[f"contrast_{name}"] = float(np.nanmean(diff))
            row[f"contrast_{name}_low"] = float(low)
            row[f"contrast_{name}_high"] = float(high)
            row[f"contrast_{name}_p_gt_zero"] = float(np.mean(diff > 0))
        for metric in (
            "abs_centre_shift_days",
            "centre_shift_days",
            "windows_differ",
            "hidden_difference_fcd_minus_reseek",
        ):
            col = geometry_names.index(f"{metric}_{width}")
            values = geometry[:, col]
            low, high, _ = _ci(values)
            row[f"{metric}_mean"] = float(np.nanmean(values))
            row[f"{metric}_low"] = float(low)
            row[f"{metric}_high"] = float(high)
        dilation_rows.append(row)

    curve = pd.DataFrame(records)
    curve.to_csv(OUT_DIR / "curve_with_ci.csv", index=False)
    dilation = pd.DataFrame(dilation_rows)
    dilation.to_csv(OUT_DIR / "dilation_vs_reseek.csv", index=False)

    provenance = {
        "script": str(Path(__file__).relative_to(ROOT)),
        "command": " ".join([sys.executable, *sys.argv]),
        "label": LABEL,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "draws": int(args.draws),
        "seed": int(args.seed),
        "workers": int(args.workers),
        "widths_days": [int(w) for w in WIDTHS],
        "tolerance_fraction_primary": float(FRACTIONS[PRIMARY]),
        "tolerance_fractions": {k: float(v) for k, v in FRACTIONS.items()},
        "inputs": {
            "endpoint_cases": {
                "path": str(ENDPOINT_CASES.relative_to(ROOT)),
                "sha256": _sha256(ENDPOINT_CASES),
            },
            "cases_development": {
                "path": str(CASES_BY_SPLIT["development"].relative_to(ROOT)),
                "sha256": _sha256(CASES_BY_SPLIT["development"]),
            },
            "cases_reserved_open": {
                "path": str(CASES_BY_SPLIT["reserved"].relative_to(ROOT)),
                "sha256": _sha256(CASES_BY_SPLIT["reserved"]),
            },
            "frozen_summary": str(
                (V18_RESULTS_ROOT / "e6_support_width" / "summary.json").relative_to(ROOT)
            ),
        },
        "n_development_cases": int(dev_payload["n_cases"]),
        "n_development_networks": len(dev_payload["keys"]),
        "n_reserved_open_cases": int(res_payload["n_cases"]),
        "n_reserved_open_networks": len(res_payload["keys"]),
        "elapsed_seconds": float(time.time() - started),
    }

    contrast_notes = {
        "support_restricted_minus_missing_fraction": (
            "The E6 P1 contrast: the re-seeked support-restricted axis (share of the estimand's "
            "own climatological hottest-k window that the outage hides) minus the whole-year "
            "missing fraction. At k = 365 the two coincide by construction, except on leap years "
            "(see validation)."
        ),
        "fixed_peak_window_30_minus_missing_fraction": (
            "The E6 P2 contrast and the source of the reported 91-day / 119-day crossover: a "
            "FIXED 30-day climatological peak-window overlap minus the whole-year missing "
            "fraction, evaluated against the label at each endpoint width k. The axis does not "
            "vary with k; only the label does. This is therefore not a statement about window "
            "width at all."
        ),
        "support_restricted_minus_fixed_peak_window_30": (
            "The re-seeked support axis minus the fixed 30-day peak axis."
        ),
        "longest_run_minus_missing_fraction": (
            "The v17 'length' axis (longest single outage run) against mean missingness."
        ),
        "fixed_centre_dilation_minus_reseeking": (
            "F05 falsification test. Both axes are window-hidden fractions at the same width; "
            "the left one dilates a window held at the training-period climatological peak "
            "centre, the right one re-seeks the hottest k-day window in the same climatology. "
            "They are identical at width 30 by construction."
        ),
        "fixed_centre_dilation_raw_peak_minus_missing_fraction": (
            "Dilation of the raw training-year climatological peak window (the window "
            "peak_overlap uses) against the whole-year missing fraction."
        ),
    }

    payload = {
        "__meta__": {
            "label": LABEL,
            "plain_language": (
                "Post-hoc uncertainty analysis of an exploratory result. Not a confirmation. "
                "Nothing here may be moved into a headline."
            ),
            "definitions": {
                "joint_bootstrap": (
                    "whole networks resampled with replacement; every width, axis and contrast "
                    "in a grid shares the same resample within a draw, so cross-width "
                    "correlations are preserved"
                ),
                "crossover": (
                    "smallest width at which a contrast curve first turns non-positive after "
                    "being positive. The interpolated value is the log-width interpolation used "
                    "by scripts/215_v18_support_width.py::crossover, restricted to + -> <= 0"
                ),
                "p_no_crossover": (
                    "fraction of replicates whose contrast curve never turns non-positive after "
                    "being positive within the nine swept widths; the reason counts split it "
                    "into never_positive_in_range, advantage_gained_later_not_lost and "
                    "positive_at_every_width"
                ),
                "scale_refit": (
                    "the frozen rule fixes each endpoint's tolerance at 0.5/1.06 x its "
                    "full-development interannual sd; the refit sensitivity re-estimates that "
                    "scale inside each replicate"
                ),
            },
            "contrast_notes": contrast_notes,
            "validation": validation,
            "provenance": provenance,
        },
        "contrasts": crossovers,
        "scale_refit_sensitivity_development": {
            "auc_by_width": refit_summary,
            "crossovers": refit_crossovers,
        },
        "conditioning_width_matrix_development": conditioning,
        "jackknife_leave_one_network_out": jackknife,
    }
    (OUT_DIR / "crossover.json").write_text(
        json.dumps(_jsonable(payload), indent=2), encoding="utf-8"
    )
    write_report(curve, dilation, payload, provenance)
    print(f"[done] wrote {OUT_DIR.relative_to(ROOT)} at {time.time() - started:.1f}s", flush=True)
    return 0


def _table(lines: list[str], rows: list[dict], columns: list[str], floatfmt: str = ".3f") -> None:
    frame = pd.DataFrame(rows)
    lines.append(frame[columns].to_markdown(index=False, floatfmt=floatfmt))
    lines.append("")


def write_report(curve, dilation, payload, provenance) -> None:
    lines: list[str] = []
    lines.append("# E6 support-width law — uncertainty and construction dependence (F05)")
    lines.append("")
    lines.append(
        "**Evidence class: `exploratory_post_open`.** This is a post-hoc stress test of an "
        "exploratory claim (`results/v18_closure/e6_support_width/`). It is not a confirmation, "
        "it touches no sealed artifact, and it must not be headlined in the manuscript. The "
        "reserved panel appears only as `reserved_open`: v17's confirmation already unblinded "
        "it and script 215 already reported its crossover, so nothing new is unblinded here."
    )
    lines.append("")
    lines.append("## What was tested")
    lines.append("")
    lines.append(
        "1. The nine-point width sweep was rebuilt into one **joint network-clustered "
        f"bootstrap** ({provenance['draws']} draws, seed {provenance['seed']}): every width, "
        "axis and contrast is evaluated on the same resampled networks, so the curve and the "
        "crossover statistic inherit the correlations between widths."
    )
    lines.append(
        "2. The crossover — the width at which a conditioning axis stops beating the whole-year "
        "missing fraction — is reported with a CI, both as a discrete grid crossing and as the "
        "frozen script's log-interpolated value, together with the probability that a replicate "
        "has **no crossover at all**."
    )
    lines.append(
        "3. The pre-registered falsification test in `P0_06_method_freeze.json` — *fixed-centre "
        "dilation vs re-seeking wide window, development only* — was run. The v17 outage "
        "realizations were regenerated from the frozen seeds; the regenerated windows reproduce "
        f"the stored `support_hidden_k` columns exactly ({provenance['n_development_cases']} "
        "development cases, "
        f"{provenance['n_development_networks']} networks), so both axes sit on identical cases."
    )
    lines.append("")
    lines.append("## Validation")
    lines.append("")
    val = payload["__meta__"]["validation"]
    frozen = val["script215_point_estimates_reproduced"]
    lines.append(
        "* stored endpoint table vs frozen case tables: `all_shared_columns_identical = "
        f"{val['stored_table_vs_frozen_case_tables']['all_shared_columns_identical']}` "
        f"({val['stored_table_vs_frozen_case_tables']['rows_checked']} rows, "
        f"{val['stored_table_vs_frozen_case_tables']['unmatched_rows']} unmatched)."
    )
    lines.append(
        "* the frozen sweep is reproduced from the stored table: max abs difference vs "
        f"`e6_support_width/summary.json` = "
        f"{frozen['max_abs_difference_vs_frozen_summary_json']:.2e} (e.g. the development "
        "fixed-peak-window advantage at 90 days is "
        f"{frozen['development'][90]['fixed_peak_window_minus_missing_fraction']:+.4f} AUC, "
        "identical to the frozen summary)."
    )
    lines.append(
        "* regenerated masks vs stored columns: `all_identical = "
        f"{val['regenerated_masks_vs_stored']['all_identical']}`, max abs difference "
        f"{max(val['regenerated_masks_vs_stored']['max_abs_difference'].values()):.2e}."
    )
    lines.append(
        "* the dilation family reduces to the re-seeking family at the reference width 30, and "
        "the raw-peak dilation reduces to `peak_overlap` at width 30 — both checked in the same "
        "block, so the comparison is apples to apples."
    )
    lines.append(
        "* caveat inherited from the frozen pipeline: in a 366-day year the width-365 re-seeking "
        f"window covers 365 days, so it is not exactly the whole-year missing fraction there "
        f"({val['regenerated_masks_vs_stored']['leap_year_cases']} development cases). That is "
        "why the width-365 point contrast is -0.0006 rather than exactly zero."
    )
    lines.append("")
    lines.append("")
    lines.append("## Headline numbers")
    lines.append("")

    def _crow(panel, axis, width):
        block = curve.loc[
            (curve["panel"] == panel)
            & (curve["statistic_kind"] == "contrast")
            & (curve["tolerance_fraction_name"] == PRIMARY)
            & (curve["axis"] == axis)
            & (curve["width_days"] == width)
        ]
        return block.iloc[0] if len(block) else None

    def _xo(key):
        return payload["contrasts"][key][PRIMARY]

    reported_dev = _xo("development | fixed_peak_window_30_minus_missing_fraction")
    reported_res = _xo("reserved_open | fixed_peak_window_30_minus_missing_fraction")
    support_dev = _xo("development | support_restricted_minus_missing_fraction")
    dil_dev = _xo("development | fixed_centre_dilation_minus_missing_fraction")
    raw_dev = _xo("development | fixed_centre_dilation_raw_peak_minus_missing_fraction")
    at90_fixed = _crow("development", "fixed_peak_window_30_minus_missing_fraction", 90)
    at90_dil = _crow("development", "fixed_centre_dilation_minus_missing_fraction", 90)
    at90_re = _crow("development", "support_restricted_minus_missing_fraction", 90)
    at182_fixed = _crow("development", "fixed_peak_window_30_minus_missing_fraction", 182)
    at182_dil = _crow("development", "fixed_centre_dilation_minus_missing_fraction", 182)
    dil_vs_re = dilation["contrast_fcd_minus_reseeking"].abs().max()

    def _fmt(row):
        return (
            f"{row['point']:+.4f} AUC, 95% CI [{row['low']:+.4f}, {row['high']:+.4f}], "
            f"positive in {row['p_at_or_above_null']:.0%} of {row['n_draws']:.0f} replicates"
        )

    lines.append(
        f"* **The reported crossover** (a *fixed* 30-day peak window against the whole-year "
        f"missing fraction, label widening with the endpoint): development "
        f"{reported_dev['point_crossover_days_script215_rule']:.1f} days, bootstrap 95% CI "
        f"[{reported_dev['bootstrap_crossover_days_ci95_low']:.0f}, "
        f"{reported_dev['bootstrap_crossover_days_ci95_high']:.0f}], P(no crossover) = "
        f"{reported_dev['p_no_crossover']:.3f}; opened reserved panel "
        f"{reported_res['point_crossover_days_script215_rule']:.1f} days, CI "
        f"[{reported_res['bootstrap_crossover_days_ci95_low']:.0f}, "
        f"{reported_res['bootstrap_crossover_days_ci95_high']:.0f}]. The two intervals overlap."
    )
    lines.append(
        f"* **The support-restricted axis** against the whole-year missing fraction never loses "
        f"its advantage until the trivial k = 365 coincidence: point crossover "
        f"{support_dev['point_crossover_days_interpolated']:.0f} days, CI "
        f"[{support_dev['bootstrap_crossover_days_ci95_low']:.0f}, "
        f"{support_dev['bootstrap_crossover_days_ci95_high']:.0f}], P(no crossover) = "
        f"{support_dev['p_no_crossover']:.3f}. It is a hump, not a decay: it peaks near 60 days."
    )
    lines.append(
        f"* **Fixed-centre dilation** against the whole-year missing fraction: point crossover "
        f"{dil_dev['point_crossover_days_interpolated']:.0f} days, CI "
        f"[{dil_dev['bootstrap_crossover_days_ci95_low']:.0f}, "
        f"{dil_dev['bootstrap_crossover_days_ci95_high']:.0f}], P(no crossover) = "
        f"{dil_dev['p_no_crossover']:.3f}. The raw-peak dilation has no crossover on the point "
        f"curve at all (P(no crossover) = {raw_dev['p_no_crossover']:.3f})."
    )
    lines.append(
        f"* **At the 90-day grid point the three constructions disagree completely.** Fixed "
        f"30-day window: {_fmt(at90_fixed)}. Fixed-centre dilation: {_fmt(at90_dil)}. Re-seeking "
        f"window: {_fmt(at90_re)}."
    )
    lines.append(
        f"* **At the 182-day grid point** the fixed 30-day window is "
        f"{at182_fixed['point']:+.4f} AUC against whole-year missingness while the dilation is "
        f"{at182_dil['point']:+.4f}: the sign of the 'support width' effect at a given width "
        "depends entirely on whether the conditioning window is dilated or held fixed."
    )
    _cond = payload["conditioning_width_matrix_development"]
    _pen90_narrow = max(
        _cond[str(w)]["penalty_of_universal_conditioning_window"]["90"]
        for w in WIDTHS
        if w <= 90
    )
    _pen90_wide = _cond["365"]["penalty_of_universal_conditioning_window"]["90"]
    _p2 = payload["contrasts"]["development | fixed_peak_window_30_minus_missing_fraction"]
    lines.append(
        f"* **A single universal conditioning window** in the 60-90 day band costs at most "
        f"{_pen90_narrow:.4f} AUC against the per-endpoint optimum for every endpoint up to 90 "
        f"days, but {_pen90_wide:.4f} AUC at the 365-day endpoint. It is a defensible single rule "
        "for the paper's seasonal endpoint family and false as a statement about the continuum."
    )
    lines.append(
        f"* **The crossover also moves with the declared tolerance**: across the frozen sweep's "
        f"own tolerance grid the reported contrast crosses at "
        f"{_p2['quarter']['point_crossover_days_interpolated']:.1f} days (0.25 sd), "
        f"{_p2[PRIMARY]['point_crossover_days_interpolated']:.1f} days (0.47 sd) and "
        f"{_p2['one']['point_crossover_days_interpolated']:.1f} days (1.0 sd)."
    )
    lines.append(
        f"* **Dilation versus re-seeking is statistically detectable but tiny**: the largest "
        f"absolute paired difference across all nine widths is {dil_vs_re:.4f} AUC."
    )
    lines.append("")
    lines.append("## 1. The curve, with intervals")
    lines.append("")
    lines.append(
        "Primary tolerance (0.5 C expressed as 0.5/1.06 of each endpoint's own interannual "
        "standard deviation), development panel. `point` is the full-sample AUC recomputed from "
        "the stored table; `low`/`high` are percentile intervals over network-clustered "
        "replicates; `P(AUC>0.5)` is the share of replicates in which the axis beats chance."
    )
    lines.append("")
    show = curve.loc[
        (curve["panel"] == "development")
        & (curve["tolerance_fraction_name"] == PRIMARY)
        & (curve["statistic_kind"] == "auc")
        & (curve["scale_mode"] == "fixed_full_sample")
        & (curve["source"] == "curve")
    ].sort_values(["axis", "width_days"])
    _table(
        lines,
        show.to_dict("records"),
        ["axis", "width_days", "point", "low", "high", "se", "p_at_or_above_null"],
        ".4f",
    )
    lines.append("Contrasts on the same resamples (paired; the interval is of the difference):")
    lines.append("")
    show = curve.loc[
        (curve["panel"] == "development")
        & (curve["tolerance_fraction_name"] == PRIMARY)
        & (curve["statistic_kind"] == "contrast")
        & (
            curve["axis"].isin(
                [
                    "support_restricted_minus_missing_fraction",
                    "fixed_peak_window_30_minus_missing_fraction",
                    "support_restricted_minus_fixed_peak_window_30",
                ]
            )
        )
    ].sort_values(["axis", "width_days"])
    _table(
        lines,
        show.to_dict("records"),
        ["axis", "width_days", "point", "low", "high", "p_at_or_above_null"],
        ".4f",
    )
    lines.append(
        f"The other two tolerance fractions ({FRACTIONS['quarter']:.2f} and {FRACTIONS['one']:.2f} "
        "of the interannual sd, matching the frozen sweep's own robustness grid) are in "
        "`curve_with_ci.csv` under `tolerance_fraction_name` `quarter` and `one`."
    )
    lines.append("")

    lines.append("## 2. Crossover statistics")
    lines.append("")
    lines.append(
        "| contrast | panel | fraction | point (interp.) | frozen rule | nearest non-positive grid | "
        "bootstrap median | 95% CI | P(no crossover) | no crossover: never positive | "
        "no crossover: gained later | no crossover: positive throughout |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for key, block in payload["contrasts"].items():
        name = key.split(" | ", 1)[-1]
        for fraction_name, summary in block.items():
            ci = (
                f"[{summary['bootstrap_crossover_days_ci95_low']:.1f}, "
                f"{summary['bootstrap_crossover_days_ci95_high']:.1f}]"
            )
            lines.append(
                f"| {name} | {summary['panel']} | {fraction_name} | "
                f"{summary['point_crossover_days_interpolated']:.1f} | "
                f"{summary['point_crossover_days_script215_rule']:.1f} | "
                f"{summary['point_crossover_grid_width_days']:.0f} | "
                f"{summary['bootstrap_crossover_days_median']:.1f} | {ci} | "
                f"{summary['p_no_crossover']:.3f} | "
                f"{summary['p_never_positive_in_range']:.3f} | "
                f"{summary['p_advantage_gained_later_not_lost']:.3f} | "
                f"{summary['p_positive_at_every_width']:.3f} |"
            )
    lines.append("")
    lines.append(
        "`P(no crossover)` is the quantity the original analysis was missing: it is the "
        "probability that a replicate drawn from the same network population has no crossover "
        "anywhere in the swept width range."
    )
    lines.append("")
    lines.append(
        "A third reading note on the `frozen rule` column: "
        "`scripts/215_v18_support_width.py::crossover` fires on any sign change, not on the "
        "loss of an advantage. On curves that start negative (the support axis against the "
        "fixed 30-day window does, and so does the whole `one`-tolerance block) it returns a "
        "number for a crossing that runs the other way — 4.3 or 24.3 days — which is why those "
        "cells disagree with the restricted rule. That fragility is itself part of the finding: "
        "the frozen helper is not a well-posed estimator of the quantity it is quoted for."
    )
    lines.append("")
    lines.append(
        "The crossover also moves with the declared tolerance: across the frozen sweep's own "
        "tolerance grid (0.25, 0.47 and 1.0 interannual sd) the reported contrast crosses at "
        f"{payload['contrasts']['development | fixed_peak_window_30_minus_missing_fraction']['quarter']['point_crossover_days_interpolated']:.1f}, "
        f"{payload['contrasts']['development | fixed_peak_window_30_minus_missing_fraction'][PRIMARY]['point_crossover_days_interpolated']:.1f} and "
        f"{payload['contrasts']['development | fixed_peak_window_30_minus_missing_fraction']['one']['point_crossover_days_interpolated']:.1f} "
        "days respectively."
    )
    lines.append("")
    lines.append(
        "Two reading notes. (i) The row that reproduces the reported 91-day / 119-day number is "
        "`fixed_peak_window_30_minus_missing_fraction`: a **fixed** 30-day peak-window axis "
        "scored against the label at each endpoint width. That contrast is not about window "
        "width — the axis never changes — so its 'crossover' is where the fixed 30-day window "
        "stops predicting errors in a widening endpoint, which is a different claim from the "
        "support-width law. (ii) `fixed_centre_dilation_minus_reseeking` crosses at exactly 30 "
        "days in every replicate by construction, because the two axes are the same window at "
        "width 30; its crossover row is degenerate and the per-width paired intervals in "
        "`dilation_vs_reseek.csv` are the object to read."
    )
    lines.append("")
    lines.append(
        "Leave-one-network-out jackknife on the two primary contrast curves (does one network "
        "carry the crossover?):"
    )
    lines.append("")
    jack = [
        {
            "contrast": name,
            "replicates": block["n_replicates"],
            "P(no crossover)": block["p_no_crossover"],
            "LOO min": block["crossover_days_min"],
            "LOO median": block["crossover_days_median"],
            "LOO max": block["crossover_days_max"],
            "jackknife SE": block["jackknife_se_days"],
            "jackknife 95% CI": (
                f"[{block['jackknife_ci95_days'][0]:.0f}, {block['jackknife_ci95_days'][1]:.0f}]"
            ),
        }
        for name, block in payload["jackknife_leave_one_network_out"].items()
    ]
    _table(lines, jack, ["contrast", "replicates", "P(no crossover)", "LOO min", "LOO median",
                         "LOO max", "jackknife SE", "jackknife 95% CI"], ".2f")
    lines.append(
        "The raw leave-one-out range is **not** a confidence interval — each replicate still "
        "contains 109 of the 110 networks — so read the jackknife SE column. Its normal CI is "
        "the uncertainty from single-network influence; the network-resampling bootstrap CI in "
        "section 2 is the one to quote."
    )
    lines.append("")

    lines.append("## 3. Fixed-centre dilation vs re-seeking (development only)")
    lines.append("")
    lines.append(
        "`re-seek` is the stored axis: the hottest k-day window of the station's smoothed "
        "training-year climatology, re-chosen at every k. `dilate` holds the window centre at "
        "that same climatology's 30-day peak centre and grows the window symmetrically to width "
        "k (`dilate (mirror)` breaks the odd-width half-day tie the other way). "
        "`dilate (raw peak)` instead dilates the raw training-year climatological peak window — "
        "the window `peak_overlap` uses. Every centre is computed from training years only: no "
        "truth enters, so this is decision-time visible."
    )
    lines.append("")
    _table(
        lines,
        dilation.to_dict("records"),
        [
            "width_days", "auc_support_reseeking", "auc_fixed_centre_dilation",
            "auc_fixed_centre_dilation_raw_peak", "auc_missing_fraction",
            "contrast_fcd_minus_reseeking", "contrast_fcd_minus_reseeking_low",
            "contrast_fcd_minus_reseeking_high", "abs_centre_shift_days_mean",
            "windows_differ_mean",
        ],
        ".4f",
    )
    lines.append(
        "Dilation against the whole-year missing fraction — the same comparison the reported "
        "crossover is built on. `reseek` is the support-restricted axis, `dilate` the "
        "fixed-centre dilation, `peak30` the fixed 30-day window whose crossover is the "
        "reported 91-day figure:"
    )
    lines.append("")
    _table(
        lines,
        dilation.to_dict("records"),
        [
            "width_days", "contrast_peak30_minus_missing", "contrast_peak30_minus_missing_low",
            "contrast_peak30_minus_missing_high", "contrast_fcd_minus_missing",
            "contrast_fcd_minus_missing_low", "contrast_fcd_minus_missing_high",
            "contrast_reseek_minus_missing", "contrast_reseek_minus_missing_low",
            "contrast_reseek_minus_missing_high",
        ],
        ".4f",
    )
    for name in (
        "development | fixed_centre_dilation_minus_missing_fraction",
        "development | fixed_centre_dilation_raw_peak_minus_missing_fraction",
        "development | fixed_centre_dilation_mirror_minus_missing_fraction",
    ):
        block = payload["contrasts"].get(name, {}).get(PRIMARY)
        if block:
            lines.append(
                f"* `{name}`: point crossover {block['point_crossover_days_interpolated']:.1f} "
                f"days, bootstrap median {block['bootstrap_crossover_days_median']:.1f}, 95% CI "
                f"[{block['bootstrap_crossover_days_ci95_low']:.1f}, "
                f"{block['bootstrap_crossover_days_ci95_high']:.1f}], P(no crossover) = "
                f"{block['p_no_crossover']:.3f}."
            )
    lines.append("")
    lines.append(
        "How far the re-seeking window actually moves away from the fixed centre, and how often "
        "the two windows are not the same set of days:"
    )
    lines.append("")
    _table(
        lines,
        dilation.to_dict("records"),
        ["width_days", "abs_centre_shift_days_mean", "centre_shift_days_mean",
         "windows_differ_mean", "hidden_difference_fcd_minus_reseek_mean"],
        ".3f",
    )

    lines.append("## 4. Conditioning width and the refit tolerance")
    lines.append("")
    lines.append(
        "For each endpoint width, the re-seeking axis evaluated at every conditioning width. "
        "`separated` counts the competing conditioning widths whose paired AUC difference from "
        "the best is resolved (CI excludes zero); if it is small, the argmax is not identified."
    )
    lines.append("")
    rows = []
    for endpoint_width, block in payload["conditioning_width_matrix_development"].items():
        best = block["best_conditioning_width_days_mean_auc"]
        rows.append(
            {
                "endpoint_width_days": int(endpoint_width),
                "best_conditioning_width_days": best,
                "auc_at_best": block[str(best)]["auc_mean"],
                "auc_at_own_support": block[endpoint_width]["auc_mean"],
                "gap_to_second_best": block["auc_gap_best_to_second_best"],
                "gap_to_own_support": block["auc_gap_best_to_own_support"],
                "separated_from": sum(
                    1
                    for v in block["separation_of_best_from_other_widths"].values()
                    if v["ci_excludes_zero"]
                ),
                "competing_widths": len(block["separation_of_best_from_other_widths"]),
            }
        )
    _table(lines, rows, ["endpoint_width_days", "best_conditioning_width_days", "auc_at_best",
                         "auc_at_own_support", "gap_to_second_best", "gap_to_own_support",
                         "separated_from", "competing_widths"], ".4f")
    lines.append(
        "What a *single universal* conditioning window would cost, in AUC, relative to each "
        "endpoint's own best conditioning width (0.0000 means the universal window is the best "
        "one for that endpoint):"
    )
    lines.append("")
    universal = []
    for endpoint_width, block in payload["conditioning_width_matrix_development"].items():
        penalty = block["penalty_of_universal_conditioning_window"]
        universal.append(
            {
                "endpoint_width_days": int(endpoint_width),
                "best_conditioning_width_days": block["best_conditioning_width_days_mean_auc"],
                "universal_30d_penalty": penalty["30"],
                "universal_60d_penalty": penalty["60"],
                "universal_90d_penalty": penalty["90"],
                "universal_182d_penalty": penalty["182"],
            }
        )
    _table(lines, universal, ["endpoint_width_days", "best_conditioning_width_days",
                              "universal_30d_penalty", "universal_60d_penalty",
                              "universal_90d_penalty", "universal_182d_penalty"], ".4f")
    lines.append(
        "Reading: a universal window in the 60-90 day band costs at most "
        f"{max(max(u['universal_60d_penalty'], u['universal_90d_penalty']) for u in universal if u['endpoint_width_days'] <= 90):.4f} "
        "AUC for every endpoint up to 90 days — that band is a defensible single rule for the "
        "paper's endpoint family — but it costs "
        f"{max(u['universal_90d_penalty'] for u in universal):.4f} AUC at the 365-day endpoint, "
        "where only conditioning on the whole year works. So 'one universal conditioning window' "
        "is supportable for local/seasonal endpoints and false as a statement about the whole "
        "continuum."
    )
    lines.append("")
    lines.append(
        "Re-estimating the tolerance scale inside each replicate (instead of fixing it at each "
        "endpoint's full-development interannual sd) moves the primary AUCs by at most:"
    )
    lines.append("")
    worst = []
    for width, entry in payload["scale_refit_sensitivity_development"]["auc_by_width"].items():
        for axis_name, values in entry.items():
            worst.append(
                {
                    "width_days": int(width),
                    "axis": axis_name,
                    "mean_difference": values["difference_refit_minus_fixed_mean"],
                    "low": values["difference_low"],
                    "high": values["difference_high"],
                    "ci_excludes_zero": values["difference_ci_excludes_zero"],
                }
            )
    worst_frame = pd.DataFrame(worst)
    order = worst_frame["mean_difference"].abs().sort_values(ascending=False).index[:6]
    _table(lines, worst_frame.loc[order].to_dict("records"),
           ["width_days", "axis", "mean_difference", "low", "high", "ci_excludes_zero"], ".4f")
    for name, block in payload["scale_refit_sensitivity_development"]["crossovers"].items():
        summary = block[PRIMARY]
        lines.append(
            f"* refit tolerance, `{name}`: point crossover "
            f"{summary['point_crossover_days_interpolated']:.1f} days, bootstrap median "
            f"{summary['bootstrap_crossover_days_median']:.1f}, 95% CI "
            f"[{summary['bootstrap_crossover_days_ci95_low']:.1f}, "
            f"{summary['bootstrap_crossover_days_ci95_high']:.1f}], P(no crossover) = "
            f"{summary['p_no_crossover']:.3f}."
        )
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    lines.append(_verdict_text(payload, curve, dilation))
    lines.append("")
    lines.append("## Files and provenance")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(_jsonable(provenance), indent=2))
    lines.append("```")
    lines.append("")
    (OUT_DIR / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _verdict_text(payload, curve, dilation) -> str:
    prim = payload["contrasts"]["development | fixed_peak_window_30_minus_missing_fraction"][PRIMARY]
    prim_res = payload["contrasts"]["reserved_open | fixed_peak_window_30_minus_missing_fraction"][PRIMARY]
    support = payload["contrasts"]["development | support_restricted_minus_missing_fraction"][PRIMARY]
    dil = payload["contrasts"]["development | fixed_centre_dilation_minus_missing_fraction"][PRIMARY]
    raw = payload["contrasts"]["development | fixed_centre_dilation_raw_peak_minus_missing_fraction"][PRIMARY]
    reseek_row = dilation.loc[dilation["width_days"] == 90].iloc[0]
    reseek_at_90 = (
        f"{reseek_row['contrast_fcd_minus_reseeking']:+.4f} AUC "
        f"(95% CI [{reseek_row['contrast_fcd_minus_reseeking_low']:+.4f}, "
        f"{reseek_row['contrast_fcd_minus_reseeking_high']:+.4f}])"
    )
    support_ci = (
        f"[{support['bootstrap_crossover_days_ci95_low']:.0f}, "
        f"{support['bootstrap_crossover_days_ci95_high']:.0f}]"
    )
    _p2_verdict = payload["contrasts"]["development | fixed_peak_window_30_minus_missing_fraction"]
    _cond_v = payload["conditioning_width_matrix_development"]
    _pen90_band = max(
        _cond_v[str(w)]["penalty_of_universal_conditioning_window"]["90"] for w in (1, 3, 7, 15, 30, 60)
    )
    _pen90_wide_v = _cond_v["365"]["penalty_of_universal_conditioning_window"]["90"]
    _pen182_v = _cond_v["182"]["penalty_of_universal_conditioning_window"]["90"]
    at90 = curve.loc[
        (curve["panel"] == "development")
        & (curve["statistic_kind"] == "contrast")
        & (curve["tolerance_fraction_name"] == PRIMARY)
        & (curve["axis"] == "fixed_peak_window_30_minus_missing_fraction")
        & (curve["width_days"] == 90)
    ].iloc[0]
    lines = [
        "**Is an exact crossover day supportable? No.**",
        "",
        f"The reported 91.0-day figure is reproduced exactly "
        f"({prim['point_crossover_days_script215_rule']:.1f} days from the stored table, max "
        "difference 0 against the frozen summary), so the arithmetic is not in question. As an "
        "estimate it is not identified. Its value also moves with the declared tolerance "
        f"({_p2_verdict['quarter']['point_crossover_days_interpolated']:.1f} to "
        f"{_p2_verdict['one']['point_crossover_days_interpolated']:.1f} days across the frozen "
        "sweep's own tolerance grid). The network-clustered 95% interval for that same "
        f"crossover is [{prim['bootstrap_crossover_days_ci95_low']:.0f}, "
        f"{prim['bootstrap_crossover_days_ci95_high']:.0f}] days, with "
        f"P(no crossover in the swept range) = {prim['p_no_crossover']:.3f}. "
        f"The opened reserved panel's 118.9-day figure behaves the same way "
        f"({prim_res['point_crossover_days_script215_rule']:.1f} days point, 95% CI "
        f"[{prim_res['bootstrap_crossover_days_ci95_low']:.0f}, "
        f"{prim_res['bootstrap_crossover_days_ci95_high']:.0f}], P(no crossover) = "
        f"{prim_res['p_no_crossover']:.2f}); the two panels' intervals overlap, so the "
        "difference between 91 and 119 days is not a panel difference either. "
        "Leave-one-network-out replicates span "
        f"{payload['jackknife_leave_one_network_out']['fixed_peak_window_30_minus_missing_fraction']['crossover_days_min']:.0f}"
        " to "
        f"{payload['jackknife_leave_one_network_out']['fixed_peak_window_30_minus_missing_fraction']['crossover_days_max']:.0f}"
        " days. The point value is an interpolation across a nine-point grid and the grid "
        "interval it interpolates across is the flat one: at the 90-day grid point the contrast "
        f"is {at90['point']:+.4f} AUC (95% CI [{at90['low']:+.4f}, {at90['high']:+.4f}]), "
        f"positive in only {at90['p_at_or_above_null']:.0%} of replicates, and the first "
        f"non-positive grid point is {prim['point_crossover_grid_width_days']:.0f} days. A "
        "sharp-looking 91.05 is being read off a value that is statistically zero. A single day "
        "cannot be defended; an interval (76-107 days here) can.",
        "",
        "**Is a single universal conditioning window supportable? No.**",
        "",
        "The best conditioning width is 60 or 90 days for every endpoint at or below 60 days, "
        "and the gap between those two is at most 0.005 AUC there: the argmax flips between them "
        "across endpoints on differences that are operationally meaningless, so the *identity* of "
        "an optimum window is not identified even where the paired bootstrap can resolve the "
        "ordering. At the same time a universal window inside that 60-90 day band costs at most "
        f"{_pen90_band:.4f} AUC against each narrow endpoint's own optimum, so the band is a "
        "defensible single rule — for the paper's seasonal endpoint family. It is not a universal "
        "rule: for the 365-day endpoint it costs "
        f"{_pen90_wide_v:.4f} AUC, where only conditioning on the whole year works, and for the "
        "182-day endpoint it costs "
        f"{_pen182_v:.4f} AUC. The supportable statement is therefore a range, not a day count, "
        "and not one number for the whole continuum.",
        "",
        "**Dilation vs re-seeking.**",
        "",
        f"At 90 days the fixed-centre dilation differs from the re-seeking window by "
        f"{reseek_at_90}; the two are identical at width 30 by construction and differ by at "
        "most ~0.008 AUC anywhere, so the *statistical* penalty for not re-seeking is small. "
        "What is not small is what the two constructions say about the crossover. The reported "
        "91-day crossover belongs to the **fixed** 30-day window: held at 30 days, that axis is "
        "-0.095 AUC against whole-year missingness at a 182-day endpoint. Dilate the same window "
        "to the endpoint's own width and the sign flips: "
        f"{dilation.loc[dilation['width_days'] == 182, 'contrast_fcd_minus_missing'].iloc[0]:+.4f} "
        "AUC at 182 days (95% CI "
        f"[{dilation.loc[dilation['width_days'] == 182, 'contrast_fcd_minus_missing_low'].iloc[0]:+.4f}, "
        f"{dilation.loc[dilation['width_days'] == 182, 'contrast_fcd_minus_missing_high'].iloc[0]:+.4f}]) "
        "for the dilation family and "
        f"{dilation.loc[dilation['width_days'] == 182, 'contrast_reseek_minus_missing'].iloc[0]:+.4f} "
        "for the re-seeking family. Both dilation families keep their advantage over whole-year "
        f"missingness out to about {dil['point_crossover_days_interpolated']:.0f} days — the "
        "raw-peak dilation never turns non-positive on the point curve at all "
        f"(P(no crossover) = {raw['p_no_crossover']:.2f}) — and only the trivial k = 365 "
        "coincidence ends it.",
        "",
        "So the 91-day number is not the width at which the support idea stops working. It is "
        "the width at which a *narrow, un-dilated* window stops predicting errors in a widening "
        "estimand. That is a real and useful statement about the v17 screen, whose axis really is "
        "a fixed 30-day window; it is not evidence for a support-width law with a crossover "
        "knob at 91 days.",
        "",
        "**What the law can and cannot carry.**",
        "",
        "Supportable, as exploratory evidence: that conditioning on a window restricted to (or "
        "dilated around) the estimand's support beats whole-year missingness across a broad band "
        "of widths, that the advantage is a hump — it peaks near 60 days at +0.089 AUC and is "
        "still +0.028 at 182 days — and that a *fixed* narrow window loses that advantage as the "
        "estimand widens, crossing zero somewhere between 60 and 182 days.",
        "",
        "Not supportable: an exact crossover day; any claim that the crossover is a property of "
        "the support width rather than of holding the conditioning window fixed; any single "
        f"universal conditioning window (the re-seeking contrast's own crossover is {support_ci} "
        f"days with P(no crossover) = {support['p_no_crossover']:.2f}, i.e. the trivial k = 365 "
        "coincidence, not a support boundary); any claim of monotone decay (the frozen summary's "
        "own P1 fails: the advantage is a hump); and any use of the 91/119-day numbers in an "
        "abstract or a headline. The quotable objects are the intervals, the no-crossover "
        "probabilities and the per-width paired intervals in `crossover.json` and "
        "`dilation_vs_reseek.csv`.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

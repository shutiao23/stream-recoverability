#!/usr/bin/env python3
"""P0-03 (hostile review F04 / F07 / F09): replay the FINAL admission rule.

The step-5b monitoring-calendar probe (``scripts/304_..._cofailure.py``) replays
only the length rule and the peak-window rule, and it silently degrades the
donor reconstructor: when no donor is usable, ``fits["donor_ridge"]`` is an
all-NaN vector, ``completed[bad] = filled[bad]`` leaves the hidden days NaN, and
``hottest_window_mean`` then returns the hottest *fully observed* window mean.
That value was reported under the name ``donor_ridge``.  This script separates
the failure semantics and replays the certificate-based admission rule that the
paper actually recommends.

What is replayed
----------------
The case builder and mask machinery of ``scripts/304`` are reused (real
incomplete station-years transplanted onto independent complete years, with
optional co-failure of donor columns).  Two placement families are produced:

* ``source_calendar_union`` -- every missing day of a real source year, mapped
  by (month, day) onto the target year (the step-5b construction);
* ``source_gap_run`` -- every *contiguous* real missing run that intersects the
  source year, mapped by absolute day offset from the run start.  A run that
  starts in December stays contiguous across 31 December: the gap lives on the
  continuous multi-year daily axis of the panel, and **both** affected calendar
  years are emitted as separate candidates.  Nothing is truncated at the year
  boundary, and every declared gap length is asserted against the masked days.

Failure semantics (never merged)
--------------------------------
For every candidate and every method the outcome is exactly one of

* ``ok``                   -- the method decides and its declared estimator is
                              defined on every hidden day;
* ``degenerate_donor``     -- the donor reconstructor cannot be formed (too few
                              visible donors, or donor predictions undefined on
                              hidden days).  The donor estimate is UNAVAILABLE
                              (NaN) and is never replaced by a fully observed
                              window mean;
* ``observed_window_only`` -- the estimate uses only the target station's own
                              observed days (the incumbent ``observed_days``
                              estimator).  Allowed, but always labelled as its
                              own estimator and never as donor reconstruction;
* ``abstain``              -- the rule declines to decide (no supported
                              estimator, chosen estimator unavailable, or the
                              calibrated bound is above the frozen threshold).

Error is reported twice per method: restricted to the cases where the method is
available (denominator stated) and over ALL candidates with abstentions and
failures counted as failures rather than dropped.

The final rule
--------------
Certificate admission: the selection-conditional multiplicative split-conformal
certificate (``screen.Certificate``) picks the estimator with the smallest
predicted absolute-error bound, and the candidate is admitted iff the calibrated
bound is at or below a threshold that controls the consequential (> 0.5 C)
false-admit rate at a 5 % cap.  Thresholds are cross-fitted with a nested
network-fold: for each held-out replay network the labelled development corpus
(minus that network) is split three ways by network -- 60 % for the certificate
heads, 20 % for the multiplicative conformal scale, 20 % for threshold
calibration -- and the threshold is chosen on the threshold-calibration networks
only; the held-out network's replay cases are then scored.  Replay labels are never used to choose a threshold.  If
the parallel workstream file
``results/wrr_submission_ready/major_revision_20261014/p0_02_frozen_risk_thresholds/final_admission_thresholds.json``
exists, its per-fold thresholds are consumed instead; the path actually used is
recorded in ``protocol_fingerprint.json``.

Replicate honesty (F07/F09)
---------------------------
One row of ``replay_decisions.parquet`` is one candidate *group*
(network x station x source calendar/gap x anchor year x evaluation year).  The
three co-failure levels are repeated measures on the same group and are stored
as suffixed columns of the same row, so they can never be counted as three
independent experiments.

Run: ``PYTHONPATH=src python3 scripts/312_wrr_p0_03_final_method_replay.py``
(``--smoke`` for a small self-test that writes under ``scratch/p0_03``.)
"""

from __future__ import annotations

import os

# Pin BLAS/OpenMP threads before numpy, sklearn or pandas initialise their
# runtimes.  Every parallel step here is process-parallel, so one thread per
# process is both faster and polite on a shared 128-core box; without this the
# loky workers inherit cpu_count()//n_jobs BLAS threads and thrash.
for _var in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMBA_NUM_THREADS",
):
    os.environ.setdefault(_var, "1")

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from joblib import Parallel, delayed  # noqa: E402

from stream_recoverability.experiments.v17_fitness.cases import (  # noqa: E402
    WARM_MONTHS,
    deseasonalized_correlations,
)
from stream_recoverability.experiments.v17_fitness.estimators import (  # noqa: E402
    StationModels,
    donor_coverage,
    hottest_window_mean,
    linear_interp_fill,
    observed_days_metric,
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
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    HOTTEST_WINDOW_DAYS,
    NOMINAL_COVERAGE,
    PRIMARY_TOLERANCE_C,
    donor_regime,
    stable_seed,
)
from stream_recoverability.experiments.v17_fitness.policies import (  # noqa: E402
    attach_policy_errors,
)
from stream_recoverability.experiments.v17_fitness.screen import (  # noqa: E402
    Certificate,
    SCREEN_FEATURES,
    split_networks,
)
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402

# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "p0_03_final_method_replay"
)
SCRATCH = ROOT / "scratch" / "p0_03"
REAL_SY = ROOT / "results/v18_closure/e2_archive_deployment/real_station_years.parquet"
SPLIT = ROOT / "results/v17_fitness/step1_panel/network_split.csv"
ROSTER = ROOT / "results/v17_fitness/step1_panel/station_roster.csv"
CORPUS = ROOT / "results/v17_fitness/step4_ceiling/development_cases.parquet"
FROZEN_CERT = ROOT / "results/v17_fitness/step9_freeze/certificate.joblib"
P0_02_DIR = (
    ROOT / "results" / "wrr_submission_ready" / "major_revision_20261014" / "p0_02_frozen_risk_thresholds"
)
P0_02_THRESHOLDS = P0_02_DIR / "final_admission_thresholds.json"
P0_02_ASSIGNMENTS = P0_02_DIR / "fold_assignments.csv"
P0_02_STORED_CERTIFICATES = ROOT / "results/v17_fitness/step6_screen/development_certificates.parquet" 
FIRST_PANELS = ROOT / "results/development_v11/confirmation_daily_qc/networks"
SECOND_PANELS = ROOT / "results/development_v11/second_confirmation/daily_qc/networks"

# --------------------------------------------------------------------------- #
# frozen constants (declared before the replay was scored; nothing here is
# tuned after seeing the replay numbers)
# --------------------------------------------------------------------------- #
SEED = 41  # same seed as scripts/304 so the same networks are drawn
MAX_NETWORKS = 16
MAX_SOURCE_YEARS_PER_STATION = 4
MAX_TARGET_YEARS_PER_SOURCE = 3
MAX_RUNS_PER_SOURCE = 4
MIN_GAP_DAYS = 3
MAX_GAP_DAYS = 330
MAX_STATIONS_PER_NETWORK = 2
TOL = PRIMARY_TOLERANCE_C  # 0.5 C consequential-error tolerance
RISK_CAP = 0.05  # frozen false-admit cap for the calibrated threshold
MIN_THRESHOLD_ADMITS = 100  # threshold must admit at least this many calibration cases
THRESHOLD_FALLBACK = TOL  # pre-existing published tolerance if no tau qualifies
COVERAGE = NOMINAL_COVERAGE

# published, pre-existing simple-rule limits (manuscript archive-composition
# table; Johnson et al. 2021 imputation limits).  Not tuned here.
LENGTH_RULE_DAYS = 49
LENGTH_RULE_DAYS_WIDE = 140
PEAK_RULE_MAX_OVERLAP = 0.10

BOOT_DRAWS_PRIMARY = 2000
BOOT_DRAWS_SECONDARY = 1000
MAX_FOLD_WORKERS = 8  # memory headroom: the machine is shared with other agents

# p0_02 (scripts/311) pre-registered threshold protocol, re-used here so the
# equivalent cross-fitted thresholds follow the same rule: the largest
# calibration retention in a 0.10..0.95 grid whose calibration false-admit rate
# plus a one-sided 95 % network-clustered bootstrap upper bound is <= 5 %.
P0_02_RETENTION_GRID = tuple(round(float(x), 4) for x in np.arange(0.10, 0.9501, 0.01))
P0_02_SELECT_DRAWS = 1000
P0_02_FOLD_SEED_PRIMARY = 101
P0_02_PANEL = "development"
P0_02_SCORE_FINAL = "calibrated_bound"
P0_02_SCORE_LENGTH = "length_rule"
P0_02_SCORE_PEAK = "peak_overlap_rule"
BOOT_ALPHA = 0.05

LEVELS = (
    ("target_only", "t0", 0.0),
    ("partial_donor_failure", "p5", 0.5),
    ("all_donor_failure", "a1", 1.0),
)
LEVEL_NAMES = tuple(name for name, _, _ in LEVELS)
FRACTIONS = {sfx: frac for _, sfx, frac in LEVELS}

ESTIMATORS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")
NON_DONOR_FILLS = ("doy_climatology", "smooth_climatology", "linear_interp", "air_ridge")

FINAL_RULE_VARIANTS = (
    "final_rule",                    # primary: certificate admission, p0_02 rule threshold in these units
    "final_rule_point_risk",         # threshold-rule sensitivity: point estimate instead of clustered bound
    "final_rule_literal_p002_tau",   # threshold-transfer sensitivity: p0_02 numeric tau, units unverified
)
METHODS = (
    "final_rule",
    "final_rule_fb",                 # primary rule + labelled observed-days fallback
    "final_rule_point_risk",
    "final_rule_literal_p002_tau",
    "peak_window_rule",              # p0_02 frozen per-fold peak-overlap threshold
    "length_rule",                   # p0_02 frozen per-fold length threshold
    "peak_window_rule_pub10",        # published fixed 10 % peak-window limit
    "length_rule_pub49",             # published fixed 49 d limit
    "length_rule_pub140",            # published fixed 140 d limit
    "donor_ridge_path",              # the donor reconstructor itself, strict availability
    "observed_days_path",            # the incumbent observed-days estimator, labelled
)
SECONDARY_METHODS = (
    "final_rule_point_risk",
    "final_rule_literal_p002_tau",
    "peak_window_rule_pub10",
    "length_rule_pub49",
    "length_rule_pub140",
    "frozen_cert_rule",
)
ALL_METHODS = METHODS + ("frozen_cert_rule",)
CONTRAST_PAIRS = (
    ("final_rule", "peak_window_rule"),
    ("final_rule", "length_rule"),
    ("peak_window_rule", "length_rule"),
    ("final_rule_fb", "final_rule"),
    ("final_rule_fb", "peak_window_rule"),
    ("final_rule", "peak_window_rule_pub10"),
    ("final_rule", "length_rule_pub49"),
    ("final_rule", "final_rule_point_risk"),
)

SCREEN_FEATURE_COLUMNS = tuple(SCREEN_FEATURES)
FAILURE_MODES = ("ok", "degenerate_donor", "observed_window_only", "abstain")
# only the columns the Certificate touches; keeps fold workers and their
# pickled payloads small (the full corpus has 148 columns)
CORPUS_KEEP_COLUMNS = (
    ("network_id", "longest_run_month", "donor_regime")
    + tuple(name for name in SCREEN_FEATURES if name not in ("month_sin", "month_cos"))
    + tuple(f"abserr_{name}" for name in ESTIMATORS)
    + tuple(f"err_{name}" for name in ESTIMATORS)
    + tuple(f"metric_{name}" for name in ESTIMATORS)
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), check=True, capture_output=True, text=True
        )
        return out.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"unavailable: {exc}"


def parallel_with_fallback(
    worker, jobs: list, worker_counts: tuple[int, ...], *, verbose: int = 0, unpack: bool = True
) -> list:
    """Run ``worker`` over ``jobs``, reducing parallelism if workers die.

    The machine is shared with other agents; a loky worker killed under memory
    pressure surfaces as ``TerminatedWorkerError``.  Falling back to fewer
    workers keeps a long run alive instead of losing it.
    """

    last_exc: Exception | None = None
    for workers in worker_counts:
        if int(workers) < 1:
            continue
        try:
            with joblib.parallel_backend("loky", inner_max_num_threads=1):
                return Parallel(n_jobs=int(workers), backend="loky", verbose=verbose)(
                    delayed(worker)(*(job if unpack else (job,))) for job in jobs
                )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(f"[warn] parallel run with {workers} workers failed ({type(exc).__name__}); retrying", flush=True)
    raise RuntimeError(f"all parallel attempts failed: {last_exc}")


def runs_from_mask(mask: np.ndarray) -> tuple[tuple[int, int], ...]:
    """(start position, length) of every maximal True run."""

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


def fill_and_metric(values: np.ndarray, observed: np.ndarray, mask: np.ndarray) -> dict:
    """Metric of a completed year, or UNAVAILABLE.

    The strict rule of ``cases.build_station_cases``: if a single hidden day is
    left unfilled the estimator has not produced a completed year and the metric
    is NaN.  The hottest fully observed window mean is never substituted.
    """

    completed = observed.copy()
    completed[mask] = np.asarray(values, dtype=float)[mask]
    unfilled = int((~np.isfinite(completed[mask])).sum())
    if unfilled:
        return {"metric": float("nan"), "available": False, "n_unfilled_hidden_days": unfilled}
    metric = hottest_window_mean(completed)
    return {
        "metric": float(metric) if np.isfinite(metric) else float("nan"),
        "available": bool(np.isfinite(metric)),
        "n_unfilled_hidden_days": 0,
    }


def gather_by_choice(choice: np.ndarray, names: tuple[str, ...], matrix: np.ndarray) -> np.ndarray:
    out = np.full(len(choice), np.nan, dtype=float)
    index = np.array([names.index(str(c)) if str(c) in names else -1 for c in choice], dtype=int)
    good = index >= 0
    if good.any():
        out[good] = matrix[np.arange(len(choice))[good], index[good]]
    return out


def level_name(sfx: str) -> str:
    return [name for name, s, _ in LEVELS if s == sfx][0]


# --------------------------------------------------------------------------- #
# phase 1 - network selection (identical logic to scripts/304)
# --------------------------------------------------------------------------- #
def select_networks(max_networks: int) -> tuple[list[str], dict[str, str], dict[str, str], dict]:
    real = pd.read_parquet(REAL_SY)
    split = pd.read_csv(SPLIT)
    roster = pd.read_csv(ROSTER)
    dev = set(split.loc[split["split_role"].eq("development"), "network_id"].astype(str))
    real = real.loc[real["network_id"].astype(str).isin(dev)].copy()
    incomplete = real.loc[~real["complete"]].copy()
    complete = real.loc[real["complete"]].copy()

    counts = roster.groupby("network_id")["station_id"].nunique()
    multi = set(counts.loc[counts >= 2].index.astype(str)) & dev
    unique_roster = roster.drop_duplicates("network_id").set_index(
        roster.drop_duplicates("network_id")["network_id"].astype(str)
    )
    source_map = unique_roster["source_root"].astype(str).to_dict()
    provider_map = unique_roster["provider"].astype(str).to_dict()
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
    nets = list(loadable)
    if len(nets) > int(max_networks):
        nets = [str(v) for v in rng.choice(nets, size=int(max_networks), replace=False)]
    diag = {
        "n_loadable_multi_station_development_networks": len(loadable),
        "n_selected": len(nets),
        "selected": sorted(nets),
    }
    return nets, source_map, provider_map, diag


# --------------------------------------------------------------------------- #
# phase 2 - case construction (one job per station)
# --------------------------------------------------------------------------- #
def build_station_cases(job: dict) -> tuple[pd.DataFrame, dict]:
    """Every replay candidate contributed by one station; one row per group."""

    network_id = str(job["network_id"])
    station_id = str(job["station_id"])
    source_root = str(job["source_root"])
    incomplete_years = [int(y) for y in job["incomplete_years"]]
    complete_years = sorted(int(y) for y in job["complete_years"])
    diag = {
        "n_station_jobs": 1,
        "n_skipped_no_training_history": 0,
        "n_skipped_eval_year_incomplete": 0,
        "n_skipped_eval_year_fully_masked": 0,
        "n_skipped_short_mask": 0,
        "n_skipped_placement_outside_panel": 0,
        "n_union_groups": 0,
        "n_run_groups": 0,
        "n_cross_year_groups": 0,
        "n_cross_year_placements": 0,
        "n_cross_year_years_skipped_incomplete": 0,
        "n_runs_dropped_by_cap": 0,
        "n_leap_source_days_without_target_date": 0,
        "n_anchor_adjusted_feb29": 0,
    }
    try:
        panel = load_network_panel(network_id, source_root)
    except Exception:  # noqa: BLE001
        return pd.DataFrame(), diag
    panel = panel.copy()
    panel.columns = [str(c) for c in panel.columns]
    if station_id not in panel.columns:
        return pd.DataFrame(), diag
    index = panel.index
    if not isinstance(index, pd.DatetimeIndex):
        return pd.DataFrame(), diag
    full = pd.date_range(index.min(), index.max(), freq="D")
    if len(full) != len(index) or not bool((full == index).all()):
        raise RuntimeError(f"panel index for {network_id}/{station_id} is not a continuous daily axis")

    target = pd.to_numeric(panel[station_id], errors="coerce")
    donors = panel.drop(columns=[station_id]).apply(pd.to_numeric, errors="coerce")
    air = air_series_for(network_id, station_id, index)
    donor_cols = list(donors.columns)
    if not donor_cols:
        return pd.DataFrame(), diag

    year_values = index.year.to_numpy()
    missing_all = ~np.isfinite(target.to_numpy(dtype=float))
    real_runs = runs_from_mask(missing_all)
    record_years = int(pd.unique(year_values).size)
    complete_set = set(complete_years)
    panel_first, panel_last = index.min(), index.max()

    cache: dict[int, dict | None] = {}

    def base_for(year: int) -> dict | None:
        if year in cache:
            return cache[year]
        year_mask = year_values == int(year)
        train_mask = pd.Series(~year_mask, index=index)
        train_values = target.loc[train_mask].dropna()
        if len(train_values) < 365:
            cache[year] = None
            return None
        models = StationModels(target=target, donors=donors, air=air, train_mask=train_mask)
        train_doy = pd.Series(train_values.index.dayofyear, index=train_values.index)
        train_residual = train_values - train_values.groupby(train_doy).transform("mean")
        year_index = index[year_mask]
        clim_peak = hottest_window_mean(models.smooth_climatology(year_index))
        train_metrics = []
        for other in complete_years:
            if int(other) == int(year):
                continue
            block = target.loc[target.index.year == int(other)].to_numpy(dtype=float)
            if np.isfinite(block).all() and len(block) >= 360:
                train_metrics.append(hottest_window_mean(block))
        base = {
            "models": models,
            "train_mask": train_mask,
            "correlations": deseasonalized_correlations(target, donors, train_mask),
            "train_resid_sd": float(train_residual.std()),
            "seasonal_amplitude": (
                float(np.nanmax(models.smooth_climatology(index[train_mask])) - np.nanmin(models.smooth_climatology(index[train_mask])))
            ),
            "train_metric_sd": float(np.std(train_metrics, ddof=1)) if len(train_metrics) > 1 else float("nan"),
            "clim_peak": float(clim_peak) if np.isfinite(clim_peak) else float("nan"),
            "peak_doys": climatological_peak_window(target.loc[target.index.year != int(year)], exclude_year=None),
        }
        cache[year] = base
        return base

    rows: list[dict] = []

    def score_case(
        *,
        eval_year: int,
        year_positions: np.ndarray,
        mask: np.ndarray,
        declared_gap_days: int,
        family: str,
        source_year: int,
        run_id: str,
        run_start: pd.Timestamp | None,
        run_end: pd.Timestamp | None,
        gap_total_days: int,
        anchor_year: int,
        cross_year: bool,
        cross_year_pair_id: str,
        n_leap_dropped: int,
        anchor_adjusted: bool,
    ) -> dict | None:
        base = base_for(eval_year)
        if base is None:
            diag["n_skipped_no_training_history"] += 1
            return None
        year_index = index[year_positions]
        truth = target.loc[year_index].to_numpy(dtype=float)
        if not np.isfinite(truth).all():
            diag["n_skipped_eval_year_incomplete"] += 1
            return None
        if not mask.any():
            diag["n_skipped_short_mask"] += 1
            return None
        if mask.all():
            diag["n_skipped_eval_year_fully_masked"] += 1
            return None
        observed = truth.copy()
        observed[mask] = np.nan
        models: StationModels = base["models"]
        train_mask: pd.Series = base["train_mask"]

        mask_runs = runs_from_mask(mask)
        longest_start, longest_len = max(mask_runs, key=lambda item: item[1])
        months = year_index.month.to_numpy()
        warm = np.isin(months, WARM_MONTHS)
        truth_metric = hottest_window_mean(truth)
        row: dict[str, object] = {
            "network_id": network_id,
            "station_id": station_id,
            "provider": str(job["provider"]),
            "family": family,
            "source_incomplete_year": int(source_year),
            "source_run_id": str(run_id),
            "source_run_start": None if run_start is None else str(run_start.date()),
            "source_run_end": None if run_end is None else str(run_end.date()),
            "gap_total_days": int(gap_total_days),
            "target_anchor_year": int(anchor_year),
            "eval_year": int(eval_year),
            "cross_year": bool(cross_year),
            "cross_year_pair_id": str(cross_year_pair_id),
            # days of the placed gap that fall outside this evaluation year:
            # declared + outside == gap_total_days is the anti-truncation check
            "gap_days_outside_eval_year": int(gap_total_days) - int(declared_gap_days),
            "anchor_adjusted_feb29": bool(anchor_adjusted),
            "n_leap_source_days_without_target_date": int(n_leap_dropped),
            "declared_gap_days": int(declared_gap_days),
            "masked_days": int(mask.sum()),
            "n_days_eval_year": int(len(mask)),
            "missing_fraction": float(mask.sum() / len(mask)),
            "n_runs": int(len(mask_runs)),
            "longest_run": int(longest_len),
            "longest_run_month": int(months[longest_start]),
            "warm_observed_fraction": float((~mask & warm).sum() / max(1, warm.sum())),
            "peak_overlap": float(peak_overlap_fraction(year_index, mask, base["peak_doys"])),
            "left_flank": bool(not mask[0]),
            "right_flank": bool(not mask[-1]),
            "train_resid_sd": base["train_resid_sd"],
            "seasonal_amplitude": base["seasonal_amplitude"],
            "train_metric_sd": base["train_metric_sd"],
            "n_complete_years": int(len(complete_years)),
            "record_years": record_years,
            "clim_peak": base["clim_peak"],
            "truth_hottest30": float(truth_metric) if np.isfinite(truth_metric) else float("nan"),
        }
        corr = base["correlations"]
        row["donor_corr_mean"] = float(corr.mean()) if len(corr) else float("nan")
        row["donor_corr_max"] = float(corr.max()) if len(corr) else float("nan")
        row["donor_corr_min"] = float(corr.min()) if len(corr) else float("nan")

        # ---- level-independent estimators --------------------------------- #
        observed_metric = observed_days_metric(observed, window=HOTTEST_WINDOW_DAYS)
        strict_observed = hottest_window_mean(observed)
        row["metric_observed_days"] = float(observed_metric) if np.isfinite(observed_metric) else float("nan")
        row["available_observed_days"] = bool(np.isfinite(observed_metric))
        row["metric_observed_strict_window"] = float(strict_observed) if np.isfinite(strict_observed) else float("nan")
        row["available_observed_strict_window"] = bool(np.isfinite(strict_observed))
        row["observed_peak"] = row["metric_observed_days"]
        row["has_complete_window"] = bool(np.isfinite(strict_observed))
        row["observed_peak_margin"] = (
            float(observed_metric - base["clim_peak"])
            if np.isfinite(observed_metric) and np.isfinite(base["clim_peak"])
            else float("nan")
        )
        fill_values = {
            "doy_climatology": models.doy_climatology(year_index),
            "smooth_climatology": models.smooth_climatology(year_index),
            "linear_interp": linear_interp_fill(observed),
            "air_ridge": models.air_predict(year_index) if air is not None else np.full(len(year_index), np.nan),
        }
        row["air_available"] = bool(air is not None and np.isfinite(fill_values["air_ridge"]).any())
        for name in NON_DONOR_FILLS:
            scored = fill_and_metric(fill_values[name], observed, mask)
            row[f"metric_{name}"] = scored["metric"]
            row[f"available_{name}"] = bool(scored["available"])
            row[f"n_unfilled_hidden_days_{name}"] = int(scored["n_unfilled_hidden_days"])
            row[f"abserr_{name}"] = (
                abs(scored["metric"] - truth_metric)
                if np.isfinite(scored["metric"]) and np.isfinite(truth_metric)
                else float("nan")
            )

        # ---- co-failure levels (repeated measures on this group) ---------- #
        n_donors = len(donor_cols)
        rng = np.random.default_rng(
            stable_seed(network_id, station_id, source_year, run_id, anchor_year, eval_year, family, SEED)
        )
        perm = rng.permutation(n_donors)
        n_partial = max(1, int(round(FRACTIONS["p5"] * n_donors))) if n_donors else 0
        hits = {
            "t0": [],
            "p5": [donor_cols[i] for i in perm[: min(n_partial, n_donors)]],
            "a1": [donor_cols[i] for i in perm],
        }
        mask_full = np.zeros(len(index), dtype=bool)
        mask_full[year_positions] = mask
        row["n_donors_total"] = int(n_donors)
        row["partial_level_equals_all_donors"] = bool(len(hits["p5"]) == n_donors)
        for _, sfx, _ in LEVELS:
            hit = hits[sfx]
            work = donors
            if hit:
                work = donors.copy()
                for col in hit:
                    work.loc[mask_full, col] = np.nan
            visible = usable_donors(work, year_index, mask)
            coverage = donor_coverage(work, year_index, mask)
            row[f"n_donors_cofailed__{sfx}"] = int(len(hit))
            row[f"n_visible_donors__{sfx}"] = int(len(visible))
            row[f"donor_coverage_mean__{sfx}"] = float(coverage.mean()) if len(coverage) else float("nan")
            row[f"donor_regime__{sfx}"] = donor_regime(len(visible))
            fit = models.donor_ridge(visible) if visible else None
            if fit is None:
                donor_pred = np.full(len(year_index), np.nan)
            else:
                view = StationModels(target=target, donors=work, air=None, train_mask=train_mask)
                donor_pred = view.donor_predict(fit, year_index)
            scored = fill_and_metric(donor_pred, observed, mask)
            row[f"metric_donor_ridge__{sfx}"] = scored["metric"]
            row[f"available_donor_ridge__{sfx}"] = bool(scored["available"])
            row[f"n_unfilled_hidden_days_donor_ridge__{sfx}"] = int(scored["n_unfilled_hidden_days"])
            row[f"donor_status__{sfx}"] = (
                "degenerate_donor" if fit is None else ("ok" if scored["available"] else "donor_incomplete_placement")
            )
            row[f"abserr_donor_ridge__{sfx}"] = (
                abs(scored["metric"] - truth_metric)
                if np.isfinite(scored["metric"]) and np.isfinite(truth_metric)
                else float("nan")
            )
        return row

    for source_year in incomplete_years[:MAX_SOURCE_YEARS_PER_STATION]:
        if source_year not in set(int(v) for v in pd.unique(year_values)):
            continue
        # ---------- family A: the whole source-year calendar (step 5b) ------ #
        source_missing = missing_all & (year_values == int(source_year))
        if source_missing.any():
            source_dates = index[source_missing]
            for anchor in complete_years[:MAX_TARGET_YEARS_PER_SOURCE]:
                mapped: list[pd.Timestamp] = []
                dropped = 0
                for date in source_dates:
                    try:
                        stamp = pd.Timestamp(year=int(anchor), month=int(date.month), day=int(date.day))
                    except ValueError:  # 29 February in a non-leap target year
                        dropped += 1
                        continue
                    if stamp < panel_first or stamp > panel_last:
                        dropped += 1
                        continue
                    mapped.append(stamp)
                diag["n_leap_source_days_without_target_date"] += dropped
                if len(mapped) < MIN_GAP_DAYS:
                    diag["n_skipped_short_mask"] += 1
                    continue
                mapped_index = pd.DatetimeIndex(mapped)
                year_positions = np.flatnonzero(year_values == int(anchor))
                year_index = index[year_positions]
                mask = np.isin(year_index, mapped_index)
                declared = int(mapped_index.isin(year_index).sum())
                if int(mask.sum()) != declared:
                    raise RuntimeError(
                        f"union placement consistency failure {network_id}/{station_id}/{source_year}->{anchor}: "
                        f"mask={int(mask.sum())} declared={declared}"
                    )
                if int(mask.sum()) < MIN_GAP_DAYS:
                    diag["n_skipped_short_mask"] += 1
                    continue
                row = score_case(
                    eval_year=int(anchor),
                    year_positions=year_positions,
                    mask=mask,
                    declared_gap_days=declared,
                    family="source_calendar_union",
                    source_year=int(source_year),
                    run_id="union",
                    run_start=None,
                    run_end=None,
                    gap_total_days=len(mapped),
                    anchor_year=int(anchor),
                    cross_year=False,
                    cross_year_pair_id="",
                    n_leap_dropped=dropped,
                    anchor_adjusted=False,
                )
                if row is not None:
                    rows.append(row)
                    diag["n_union_groups"] += 1

        # ---------- family B: contiguous real runs, cross-year capable ------ #
        intersecting = [
            (start, length)
            for start, length in real_runs
            if MIN_GAP_DAYS <= length <= MAX_GAP_DAYS
            and year_values[start] <= int(source_year) <= year_values[start + length - 1]
        ]
        if len(intersecting) > MAX_RUNS_PER_SOURCE:
            intersecting = sorted(intersecting, key=lambda item: -item[1])[:MAX_RUNS_PER_SOURCE]
            diag["n_runs_dropped_by_cap"] += 1
        for run_ordinal, (start, length) in enumerate(sorted(intersecting)):
            run_dates = index[start : start + length]
            run_start, run_end = run_dates[0], run_dates[-1]
            run_id = f"run{run_ordinal:02d}_{run_start.date()}"
            for anchor in complete_years[:MAX_TARGET_YEARS_PER_SOURCE]:
                anchor_adjusted = False
                try:
                    anchor_date = pd.Timestamp(year=int(anchor), month=int(run_start.month), day=int(run_start.day))
                except ValueError:  # 29 February
                    anchor_date = pd.Timestamp(year=int(anchor), month=2, day=28)
                    anchor_adjusted = True
                    diag["n_anchor_adjusted_feb29"] += 1
                placed = pd.date_range(anchor_date, periods=int(length), freq="D")
                if placed[0] < panel_first or placed[-1] > panel_last:
                    diag["n_skipped_placement_outside_panel"] += 1
                    continue
                affected = sorted({int(stamp.year) for stamp in placed})
                if len(affected) > 1:
                    diag["n_cross_year_placements"] += 1
                    missing_years = [y for y in affected if y not in complete_set]
                    if missing_years:
                        diag["n_cross_year_years_skipped_incomplete"] += len(missing_years)
                for ordinal_year, eval_year in enumerate(affected):
                    if eval_year not in complete_set:
                        diag["n_skipped_eval_year_incomplete"] += 1
                        continue
                    year_positions = np.flatnonzero(year_values == int(eval_year))
                    year_index = index[year_positions]
                    mask = np.isin(year_index, placed)
                    declared = int(placed.isin(year_index).sum())
                    if int(mask.sum()) != declared:
                        raise RuntimeError(
                            f"run placement consistency failure {network_id}/{station_id} {run_id}->{eval_year}: "
                            f"mask={int(mask.sum())} declared={declared}"
                        )
                    if int(mask.sum()) < MIN_GAP_DAYS:
                        diag["n_skipped_short_mask"] += 1
                        continue
                    cross_year = len(affected) > 1
                    if cross_year:
                        other = [y for y in affected if y != eval_year][0]
                        other_positions = np.flatnonzero(year_values == int(other))
                        other_mask = np.isin(index[other_positions], placed)
                        if int(other_mask.sum()) + int(mask.sum()) != int(length):
                            raise RuntimeError(
                                f"cross-year gap truncated {network_id}/{station_id} {run_id} "
                                f"{other}->{eval_year}: {int(other_mask.sum())}+{int(mask.sum())} != {int(length)}"
                            )
                    row = score_case(
                        eval_year=int(eval_year),
                        year_positions=year_positions,
                        mask=mask,
                        declared_gap_days=declared,
                        family="source_gap_run",
                        source_year=int(source_year),
                        run_id=run_id,
                        run_start=run_start,
                        run_end=run_end,
                        gap_total_days=int(length),
                        anchor_year=int(anchor),
                        cross_year=cross_year,
                        cross_year_pair_id=f"{source_year}|{run_id}|{anchor}" if cross_year else "",
                        n_leap_dropped=0,
                        anchor_adjusted=anchor_adjusted,
                    )
                    if row is not None:
                        rows.append(row)
                        diag["n_run_groups"] += 1
                        if cross_year:
                            diag["n_cross_year_groups"] += 1

    return (pd.DataFrame(rows) if rows else pd.DataFrame()), diag


# --------------------------------------------------------------------------- #
# phase 3 - assertions, policy backend
# --------------------------------------------------------------------------- #
def assert_case_consistency(cases: pd.DataFrame) -> dict:
    """Fail loudly if a declared gap length disagrees with the masked days.

    Two independent structural checks:

    * ``masked_days == declared_gap_days`` for every case (the declared gap
      length is the number of masked days);
    * for the contiguous-run family the placed run is partitioned by calendar
      year with nothing dropped: ``declared_gap_days + gap_days_outside_eval_year
      == gap_total_days``, and a cross-year case holds only a strict part of the
      run, so a gap that crosses 31 December is never truncated.
    """

    problems = []
    cross = cases.loc[cases["cross_year"]]
    for row in cases.itertuples(index=False):
        if int(row.masked_days) != int(row.declared_gap_days):
            problems.append(
                f"{row.network_id}/{row.station_id} {row.family} {row.source_run_id}->{row.eval_year}: "
                f"masked_days={row.masked_days} declared_gap_days={row.declared_gap_days}"
            )
        if row.family == "source_gap_run":
            if int(row.declared_gap_days) + int(row.gap_days_outside_eval_year) != int(row.gap_total_days):
                problems.append(
                    f"{row.network_id}/{row.station_id} run {row.source_run_id}->{row.eval_year}: "
                    f"declared {row.declared_gap_days} + outside {row.gap_days_outside_eval_year} != "
                    f"run length {row.gap_total_days} (truncation)"
                )
            if bool(row.cross_year):
                if int(row.declared_gap_days) >= int(row.gap_total_days) or int(row.gap_days_outside_eval_year) <= 0:
                    problems.append(
                        f"{row.network_id}/{row.station_id} cross-year pair {row.cross_year_pair_id} year "
                        f"{row.eval_year}: {row.declared_gap_days} of {row.gap_total_days} days, "
                        f"outside={row.gap_days_outside_eval_year} (should be a strict part)"
                    )
            elif int(row.declared_gap_days) != int(row.gap_total_days):
                problems.append(
                    f"{row.network_id}/{row.station_id} within-year run {row.source_run_id}->{row.eval_year}: "
                    f"declared {row.declared_gap_days} != run length {row.gap_total_days}"
                )
    if problems:
        payload = {"n_checked": int(len(cases)), "n_problems": len(problems), "problems": problems[:50]}
        SCRATCH.mkdir(parents=True, exist_ok=True)
        (SCRATCH / "assertion_failures.json").write_text(json.dumps(payload, indent=2) + "\n")
        raise RuntimeError(
            f"gap-length assertions failed for {len(problems)} cases; see scratch/p0_03/assertion_failures.json"
        )
    report = {
        "status": "pass",
        "n_groups_checked": int(len(cases)),
        "n_cross_year_groups_checked": int(len(cross)),
        "n_cross_year_pairs_checked": int(cross["cross_year_pair_id"].nunique()) if len(cross) else 0,
        "checks": [
            "masked_days == declared_gap_days for every case",
            "declared_gap_days + gap_days_outside_eval_year == gap_total_days for every contiguous-run case",
            "cross-year cases hold a strict part of the run (0 < declared < gap_total_days)",
        ],
    }
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "assertion_report.json").write_text(json.dumps(report, indent=2) + "\n")
    stale = SCRATCH / "assertion_failures.json"
    if stale.is_file():
        stale.unlink()
    return report


def attach_level_policy(cases: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Add the deployed-policy choice/error and the certificate-backend error."""

    out = cases.copy()
    consistent = True
    for _, sfx, _ in LEVELS:
        view = pd.DataFrame(index=out.index)
        for column in ("longest_run", "left_flank", "right_flank", "air_available"):
            view[column] = out[column]
        view["n_visible_donors"] = out[f"n_visible_donors__{sfx}"]
        for name in NON_DONOR_FILLS:
            view[f"abserr_{name}"] = pd.to_numeric(out[f"abserr_{name}"], errors="coerce")
        view["abserr_donor_ridge"] = pd.to_numeric(out[f"abserr_donor_ridge__{sfx}"], errors="coerce")
        scored = attach_policy_errors(view)
        choice = scored["policy_choice"].astype(str).to_numpy()
        out[f"policy_choice__{sfx}"] = choice
        out[f"abserr_policy__{sfx}"] = pd.to_numeric(scored["abserr_policy"], errors="coerce")
        metric_matrix = np.column_stack(
            [pd.to_numeric(out[f"metric_{name}"], errors="coerce").to_numpy(dtype=float) for name in NON_DONOR_FILLS[:3]]
            + [pd.to_numeric(out[f"metric_donor_ridge__{sfx}"], errors="coerce").to_numpy(dtype=float)]
            + [pd.to_numeric(out["metric_air_ridge"], errors="coerce").to_numpy(dtype=float)]
        )
        abserr_matrix = np.column_stack(
            [pd.to_numeric(out[f"abserr_{name}"], errors="coerce").to_numpy(dtype=float) for name in NON_DONOR_FILLS[:3]]
            + [pd.to_numeric(out[f"abserr_donor_ridge__{sfx}"], errors="coerce").to_numpy(dtype=float)]
            + [pd.to_numeric(out["abserr_air_ridge"], errors="coerce").to_numpy(dtype=float)]
        )
        out[f"metric_policy__{sfx}"] = gather_by_choice(choice, ESTIMATORS, metric_matrix)
        gathered = gather_by_choice(choice, ESTIMATORS, abserr_matrix)
        policy = pd.to_numeric(out[f"abserr_policy__{sfx}"], errors="coerce").to_numpy(dtype=float)
        both = np.isfinite(policy) & np.isfinite(gathered)
        if both.any() and not np.allclose(policy[both], gathered[both], atol=1e-9):
            consistent = False
        out[f"available_policy__{sfx}"] = np.isfinite(policy)
    return out, consistent


# --------------------------------------------------------------------------- #
# phase 4 - nested cross-fitted certificate and threshold
# --------------------------------------------------------------------------- #
def certificate_feature_frame(cases: pd.DataFrame, sfx: str) -> pd.DataFrame:
    """Decision-time features only, for one co-failure level."""

    frame = pd.DataFrame(index=cases.index)
    for name in SCREEN_FEATURE_COLUMNS:
        if name in ("month_sin", "month_cos"):
            continue
        if name == "n_visible_donors":
            frame[name] = pd.to_numeric(cases[f"n_visible_donors__{sfx}"], errors="coerce")
            continue
        if name == "donor_coverage_mean":
            frame[name] = pd.to_numeric(cases[f"donor_coverage_mean__{sfx}"], errors="coerce")
            continue
        if name in cases.columns:
            column = cases[name]
            frame[name] = column.astype(float) if column.dtype == bool else pd.to_numeric(column, errors="coerce")
        else:
            frame[name] = np.nan
    frame["longest_run_month"] = pd.to_numeric(cases["longest_run_month"], errors="coerce")
    frame["donor_regime"] = cases[f"donor_regime__{sfx}"].astype(str)
    frame["network_id"] = cases["network_id"].astype(str)
    return frame


def assert_truth_invariance(model: Certificate, features: pd.DataFrame) -> bool:
    """The certificate must not change when truth-like columns are injected."""

    injected = features.copy()
    for name in ("abserr_donor_ridge", "err_donor_ridge", "metric_donor_ridge", "truth_hottest30"):
        injected[name] = 0.0
    a = model.predict(features)
    b = model.predict(injected[features.columns])
    same_choice = a["certificate_choice"].fillna("__na__").equals(b["certificate_choice"].fillna("__na__"))
    same_bound = a["certificate_bound"].fillna(-1.0).equals(b["certificate_bound"].fillna(-1.0))
    return bool(same_choice and same_bound)


def select_threshold_point(
    bound: np.ndarray,
    abserr: np.ndarray,
    *,
    risk_cap: float = RISK_CAP,
    min_admits: int = MIN_THRESHOLD_ADMITS,
    fallback: float = THRESHOLD_FALLBACK,
) -> dict:
    """Largest calibrated-bound threshold whose calibration false-admit <= cap.

    Point-estimate variant; the pre-registered p0_02 rule uses the clustered
    one-sided bound instead (see :func:`select_threshold_clustered`).
    """

    b = np.asarray(bound, dtype=float)
    e = np.asarray(abserr, dtype=float)
    good = np.isfinite(b)
    b = b[good]
    fail = (~np.isfinite(e[good])) | (e[good] > TOL)
    if b.size == 0:
        return {
            "threshold": float(fallback),
            "source": "fallback_no_finite_bounds",
            "n_calibration": 0,
            "n_admitted_calibration": 0,
            "risk_at_threshold_calibration": float("nan"),
        }
    order = np.argsort(b, kind="mergesort")
    b_sorted = b[order]
    fail_sorted = fail[order].astype(float)
    cumulative = np.cumsum(fail_sorted)
    index = np.arange(1, b_sorted.size + 1)
    risk = cumulative / index
    eligible = (risk <= float(risk_cap)) & (index >= int(min_admits))
    if not eligible.any():
        n_fb = int((b <= float(fallback)).sum())
        risk_fb = float(fail_sorted[:n_fb].mean()) if n_fb else float("nan")
        return {
            "threshold": float(fallback),
            "source": "fallback_no_eligible_threshold",
            "n_calibration": int(b.size),
            "n_admitted_calibration": n_fb,
            "risk_at_threshold_calibration": risk_fb,
        }
    j = int(np.flatnonzero(eligible)[-1])
    return {
        "threshold": float(b_sorted[j]),
        "source": "cross_fitted_risk_cap_point",
        "n_calibration": int(b.size),
        "n_admitted_calibration": int(index[j]),
        "risk_at_threshold_calibration": float(risk[j]),
        "threshold_quantile_in_calibration": float(index[j] / b_sorted.size),
    }


def select_threshold_clustered(
    bound: np.ndarray,
    abserr: np.ndarray,
    network: np.ndarray,
    *,
    risk_cap: float = RISK_CAP,
    retention_grid: tuple[float, ...] = P0_02_RETENTION_GRID,
    draws: int = P0_02_SELECT_DRAWS,
    seed: int = 0,
) -> dict:
    """The p0_02 pre-registered rule, re-implemented in this script's units.

    For every calibration retention in the p0_02 grid take the corresponding
    score quantile as the threshold, and keep the largest retention whose
    calibration false-admit rate plus a one-sided 95 % network-clustered
    bootstrap upper bound stays at or below the risk cap.  If no grid point
    qualifies, no case is admitted (the p0_02 rule says so explicitly).
    """

    b = np.asarray(bound, dtype=float)
    e = np.asarray(abserr, dtype=float)
    net = np.asarray(network).astype(str)
    good = np.isfinite(b)
    b = b[good]
    fail = ((~np.isfinite(e[good])) | (e[good] > TOL)).astype(float)
    net = net[good]
    if b.size == 0:
        return {
            "threshold": float("-inf"),
            "source": "p0_02_rule_no_finite_bounds",
            "n_calibration": 0,
            "n_admitted_calibration": 0,
            "risk_at_threshold_calibration": float("nan"),
            "upper_bound_at_threshold_calibration": float("nan"),
            "calibration_retention": 0.0,
            "admits_nothing": True,
        }
    order = np.argsort(b, kind="mergesort")
    b_sorted = b[order]
    fail_sorted = fail[order]
    net_sorted = net[order]
    keys, inverse = np.unique(net_sorted, return_inverse=True)
    n_networks = len(keys)
    rng = np.random.default_rng(int(seed))
    picked = rng.integers(0, n_networks, size=(int(draws), n_networks)) if n_networks >= 2 else None
    best: dict | None = None
    for retention in retention_grid:
        k = int(round(float(retention) * b_sorted.size))
        if k < 1:
            continue
        admitted = slice(0, k)
        point = float(fail_sorted[admitted].mean())
        if picked is not None:
            sums = np.bincount(inverse[admitted], weights=fail_sorted[admitted], minlength=n_networks)
            counts = np.bincount(inverse[admitted], minlength=n_networks).astype(float)
            draws_rate = sums[picked].sum(axis=1) / np.maximum(counts[picked].sum(axis=1), 1.0)
            upper = float(np.quantile(draws_rate, 1.0 - 0.05))
        else:
            upper = point
        if upper <= float(risk_cap) and (best is None or retention > best["calibration_retention"]):
            best = {
                "threshold": float(b_sorted[k - 1]),
                "source": "p0_02_rule_clustered_bound",
                "n_calibration": int(b_sorted.size),
                "n_admitted_calibration": int(k),
                "risk_at_threshold_calibration": point,
                "upper_bound_at_threshold_calibration": upper,
                "calibration_retention": float(retention),
                "threshold_quantile_in_calibration": float(k / b_sorted.size),
                "admits_nothing": False,
            }
    if best is None:
        return {
            "threshold": float("-inf"),
            "source": "p0_02_rule_admits_nothing",
            "n_calibration": int(b_sorted.size),
            "n_admitted_calibration": 0,
            "risk_at_threshold_calibration": float("nan"),
            "upper_bound_at_threshold_calibration": float("nan"),
            "calibration_retention": 0.0,
            "admits_nothing": True,
        }
    return best


def load_p0_02_thresholds(path: Path, assignments_path: Path) -> tuple[dict | None, dict]:
    """Read the parallel workstream's frozen per-fold thresholds when present.

    Recognises the p0_02 ``records[]`` schema (one object per panel x score x
    fold_seed, each with a per-fold ``threshold``) and the older flat
    ``thresholds`` / ``per_fold`` mappings.  Returns the per-fold thresholds
    plus, when the fold-assignment table is present, the network -> fold map.
    """

    if not path.is_file():
        return None, {"path": str(path.relative_to(ROOT)), "exists": False, "used": False}
    try:
        payload = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        return None, {"path": str(path.relative_to(ROOT)), "exists": True, "used": False, "error": str(exc)}
    meta: dict = {
        "path": str(path.relative_to(ROOT)),
        "exists": True,
        "used": False,
        "sha256": sha256_file(path),
        "schema_version": payload.get("schema_version") if isinstance(payload, dict) else None,
        "generated_by": payload.get("generated_by") if isinstance(payload, dict) else None,
    }
    records: dict[tuple[str, int], dict] = {}
    flat: dict[str, float] = {}
    if isinstance(payload, dict):
        for item in payload.get("records", []) or []:
            if not isinstance(item, dict) or "folds" not in item:
                continue
            score = str(item.get("score"))
            seed = int(item.get("fold_seed", -1))
            records[(score, seed)] = {
                "panel": str(item.get("panel")),
                "threshold_units": item.get("threshold_units"),
                "score_definition": item.get("score_definition"),
                "decision_rule_in_words": item.get("decision_rule_in_words"),
                "pooled_eval": item.get("pooled_eval"),
                "folds": {
                    int(fold["fold"]): float(fold["threshold"])
                    for fold in item["folds"]
                    if isinstance(fold, dict) and "threshold" in fold
                },
                "fold_selection_detail": item.get("folds"),
            }
        for key in ("thresholds", "per_fold", "folds", "final_admission_thresholds", "by_network"):
            block = payload.get(key)
            if isinstance(block, dict):
                for name, value in block.items():
                    if isinstance(value, (int, float)):
                        flat[str(name)] = float(value)
                    elif isinstance(value, dict) and "threshold" in value:
                        flat[str(name)] = float(value["threshold"])
            elif isinstance(block, list):
                for item in block:
                    if isinstance(item, dict) and "threshold" in item:
                        name = item.get("network_id") or item.get("fold") or item.get("id")
                        if name is not None:
                            flat[str(name)] = float(item["threshold"])
    network_fold: dict[int, dict[str, int]] = {}
    if assignments_path.is_file():
        assignments = pd.read_csv(assignments_path)
        if {"panel", "network_id"} <= set(assignments.columns):
            for column in assignments.columns:
                if not str(column).startswith("fold_seed_"):
                    continue
                seed = int(str(column).replace("fold_seed_", ""))
                block = assignments.loc[assignments["panel"].astype(str).eq(P0_02_PANEL)]
                network_fold[seed] = {
                    str(row.network_id): int(getattr(row, column)) for row in block.itertuples(index=False)
                }
        meta["assignments_path"] = str(assignments_path.relative_to(ROOT))
        meta["n_assignment_networks"] = {str(seed): len(map_) for seed, map_ in network_fold.items()}
    if not records and not flat:
        meta["error"] = "no per-fold thresholds recognised"
        meta["top_level_keys"] = sorted(payload.keys()) if isinstance(payload, dict) else None
        return None, meta
    meta["used"] = True
    meta["records"] = sorted(f"{score}|seed{seed}" for score, seed in records)
    return {"records": records, "flat": flat, "network_fold": network_fold, "meta": meta}, meta


def thresholds_from_p0_02(
    loaded: dict, score: str, seed: int, networks: list[str], *, fallback: float
) -> tuple[pd.Series, dict]:
    """Per-network frozen threshold for ``score`` under the p0_02 fold seed."""

    record = loaded["records"].get((score, int(seed)))
    detail = {
        "score": score,
        "fold_seed": int(seed),
        "available": record is not None,
        "threshold_units": None if record is None else record.get("threshold_units"),
    }
    if record is None:
        return pd.Series(float(fallback), index=sorted(networks), dtype=float), {**detail, "reason": "record missing"}
    mapping = loaded["network_fold"].get(int(seed), {})
    values = {}
    missing = []
    for network in sorted(networks):
        fold = mapping.get(str(network))
        if fold is None or int(fold) not in record["folds"]:
            missing.append(str(network))
            values[str(network)] = float(fallback)
        else:
            values[str(network)] = float(record["folds"][int(fold)])
    detail.update(
        {
            "n_networks_mapped": int(len(networks) - len(missing)),
            "networks_without_fold": missing,
            "fold_thresholds": {str(k): float(v) for k, v in record["folds"].items()},
            "pooled_eval_development": record.get("pooled_eval"),
        }
    )
    return pd.Series(values, dtype=float), detail


def verify_certificate_table_reproduction(
    corpus_path: str, keep_columns: tuple[str, ...], stored_path: Path, *, fold: int = 0, seed: int = 0
) -> dict:
    """Can the stored certificate table be reproduced with the current screen.py?

    The p0_02 ``calibrated_bound`` thresholds live in the units of the stored
    table.  Transferring a numeric threshold into a differently scaled bound is
    unsound, so this check is run and recorded rather than assumed.
    """

    if not stored_path.is_file():
        return {"path": str(stored_path.relative_to(ROOT)), "exists": False}
    corpus = pd.read_parquet(corpus_path, columns=list(keep_columns)).reset_index(drop=True)
    corpus["network_id"] = corpus["network_id"].astype(str)
    stored = pd.read_parquet(stored_path, columns=["certificate_bound", "certificate_choice"]).reset_index(drop=True)
    if len(stored) != len(corpus):
        return {"path": str(stored_path.relative_to(ROOT)), "exists": True, "error": "row count mismatch"}
    networks = sorted(corpus["network_id"].unique())
    rng = np.random.default_rng(int(seed))
    order = rng.permutation(len(networks))
    folds = {networks[int(i)]: position % 5 for position, i in enumerate(order)}
    assignment = corpus["network_id"].map(folds)
    test = corpus.loc[assignment.eq(int(fold))]
    train = corpus.loc[~assignment.eq(int(fold))]
    fit_ids, cal_ids = split_networks(train["network_id"].unique(), fraction=0.30, seed=int(seed) + int(fold))
    model = Certificate(coverage=COVERAGE).fit(
        train.loc[train["network_id"].isin(fit_ids)], train.loc[train["network_id"].isin(cal_ids)], seed=int(seed) + int(fold)
    )
    predicted = model.predict(test)
    new_bound = pd.to_numeric(predicted["certificate_bound"], errors="coerce").to_numpy(dtype=float)
    old_bound = pd.to_numeric(stored.loc[test.index, "certificate_bound"], errors="coerce").to_numpy(dtype=float)
    both = np.isfinite(new_bound) & np.isfinite(old_bound)
    choice_match = float(
        (predicted["certificate_choice"].astype(str).to_numpy() == stored.loc[test.index, "certificate_choice"].astype(str).to_numpy()).mean()
    )
    return {
        "path": str(stored_path.relative_to(ROOT)),
        "exists": True,
        "probe_fold": int(fold),
        "n_cases_compared": int(both.sum()),
        "max_abs_bound_difference_c": float(np.max(np.abs(new_bound[both] - old_bound[both]))) if both.any() else float("nan"),
        "median_abs_bound_difference_c": float(np.median(np.abs(new_bound[both] - old_bound[both]))) if both.any() else float("nan"),
        "choice_agreement": choice_match,
        "reproduced": bool(both.any() and np.max(np.abs(new_bound[both] - old_bound[both])) < 1e-6),
    }


def cross_fit_fold(network_id: str, corpus_path: str, keep_columns: tuple[str, ...], fold_seed: int) -> dict:
    """One nested fold, entirely network-disjoint from the held-out network.

    The labelled corpus (excluding the held-out network) is split three ways by
    network: certificate fitting, conformal scale calibration, and threshold
    calibration.  The heads never see the scale or the threshold networks, and
    the threshold is therefore selected on labels the heads did not use.

    The corpus is read from disk inside the worker with column selection, so the
    parent never pickles a full case table to fourteen processes.
    """

    corpus = pd.read_parquet(corpus_path, columns=list(keep_columns))
    corpus["network_id"] = corpus["network_id"].astype(str)
    corpus_networks = sorted(set(corpus["network_id"]) - {network_id})
    fit_ids, rest_ids = split_networks(corpus_networks, fraction=0.40, seed=fold_seed)
    scale_ids, threshold_ids = split_networks(sorted(rest_ids), fraction=0.50, seed=fold_seed + 1)
    fit_cases = corpus.loc[corpus["network_id"].astype(str).isin(fit_ids)]
    scale_cases = corpus.loc[corpus["network_id"].astype(str).isin(scale_ids)]
    threshold_cases = corpus.loc[corpus["network_id"].astype(str).isin(threshold_ids)]
    model = Certificate(coverage=COVERAGE).fit(fit_cases, scale_cases, seed=fold_seed)
    applied = model.apply(threshold_cases)
    bound = pd.to_numeric(applied["certificate_bound"], errors="coerce").to_numpy(dtype=float)
    abserr = pd.to_numeric(applied["certificate_abs_error"], errors="coerce").to_numpy(dtype=float)
    network = threshold_cases["network_id"].astype(str).to_numpy()
    clustered = select_threshold_clustered(bound, abserr, network, seed=fold_seed)
    point = select_threshold_point(bound, abserr)
    record = {
        "network_id": network_id,
        "fold_seed": int(fold_seed),
        "n_fit_networks": len(fit_ids),
        "n_scale_calibration_networks": len(scale_ids),
        "n_threshold_calibration_networks": len(threshold_ids),
        "n_fit_cases": int(len(fit_cases)),
        "n_scale_calibration_cases": int(len(scale_cases)),
        "n_threshold_calibration_cases": int(len(threshold_cases)),
        "threshold_clustered": float(clustered["threshold"]),
        "threshold_clustered_source": str(clustered["source"]),
        "threshold_clustered_retention": float(clustered.get("calibration_retention", float("nan"))),
        "threshold_clustered_risk_point": float(clustered.get("risk_at_threshold_calibration", float("nan"))),
        "threshold_clustered_risk_upper": float(clustered.get("upper_bound_at_threshold_calibration", float("nan"))),
        "threshold_clustered_admits_nothing": bool(clustered.get("admits_nothing", False)),
        "threshold_point": float(point["threshold"]),
        "threshold_point_source": str(point["source"]),
        "threshold_point_risk": float(point.get("risk_at_threshold_calibration", float("nan"))),
        "threshold_point_admitted": int(point.get("n_admitted_calibration", 0)),
    }
    return {
        "record": record,
        "model": model,
        "threshold": float(clustered["threshold"]),
        "threshold_point": float(point["threshold"]),
    }


def apply_certificate(model: Certificate, cases: pd.DataFrame, sfx: str) -> dict[str, np.ndarray]:
    predicted = model.predict(certificate_feature_frame(cases, sfx))
    return {
        "choice": predicted["certificate_choice"].astype(object).to_numpy(),
        "bound": pd.to_numeric(predicted["certificate_bound"], errors="coerce").to_numpy(dtype=float),
        "raw_bound": pd.to_numeric(predicted["certificate_raw_bound"], errors="coerce").to_numpy(dtype=float),
    }


# --------------------------------------------------------------------------- #
# phase 5 - method decisions
# --------------------------------------------------------------------------- #
def build_method_columns(cases: pd.DataFrame, thresholds: dict[str, object], frozen: dict | None) -> pd.DataFrame:
    """Every method's decision, failure mode, estimate and error, per level.

    ``thresholds`` holds one per-network threshold series per admission rule:
    the final-rule variants (``final_rule`` plus its threshold sensitivities)
    and the two simple rules (which may be the p0_02 frozen per-fold values or
    the published fixed limits).
    """

    out = cases.copy()
    n = len(out)
    rows = np.arange(n)
    network_ids = out["network_id"].astype(str)

    def tau_for(name: str, default: float) -> np.ndarray:
        series = thresholds.get(name)
        if series is None:
            return np.full(n, float(default))
        if isinstance(series, pd.Series):
            return pd.to_numeric(network_ids.map(series), errors="coerce").to_numpy(dtype=float)
        return np.full(n, float(series))

    tau_primary = tau_for("final_rule", THRESHOLD_FALLBACK)
    est_names = ESTIMATORS + ("observed_days",)
    truth = pd.to_numeric(out["truth_hottest30"], errors="coerce").to_numpy(dtype=float)
    obs_metric_all = pd.to_numeric(out["metric_observed_days"], errors="coerce").to_numpy(dtype=float)
    obs_abserr_all = pd.to_numeric(out["abserr_observed_days"], errors="coerce").to_numpy(dtype=float)
    obs_avail_all = out["available_observed_days"].to_numpy(dtype=bool)

    for _, sfx, _ in LEVELS:
        out = out.copy()  # defragment before adding this level's columns
        metric_matrix = np.column_stack(
            [pd.to_numeric(out[f"metric_{name}"], errors="coerce").to_numpy(dtype=float) for name in NON_DONOR_FILLS[:3]]
            + [pd.to_numeric(out[f"metric_donor_ridge__{sfx}"], errors="coerce").to_numpy(dtype=float)]
            + [pd.to_numeric(out["metric_air_ridge"], errors="coerce").to_numpy(dtype=float)]
            + [obs_metric_all]
        )
        abserr_matrix = np.column_stack(
            [pd.to_numeric(out[f"abserr_{name}"], errors="coerce").to_numpy(dtype=float) for name in NON_DONOR_FILLS[:3]]
            + [pd.to_numeric(out[f"abserr_donor_ridge__{sfx}"], errors="coerce").to_numpy(dtype=float)]
            + [pd.to_numeric(out["abserr_air_ridge"], errors="coerce").to_numpy(dtype=float)]
            + [obs_abserr_all]
        )
        avail_matrix = np.column_stack(
            [out[f"available_{name}"].to_numpy(dtype=bool) for name in NON_DONOR_FILLS[:3]]
            + [out[f"available_donor_ridge__{sfx}"].to_numpy(dtype=bool)]
            + [out["available_air_ridge"].to_numpy(dtype=bool)]
            + [obs_avail_all]
        )
        choice = out[f"certificate_choice__{sfx}"].astype(object).to_numpy()
        idx = np.array([est_names.index(str(c)) if str(c) in est_names else -1 for c in choice], dtype=int)
        safe = np.maximum(idx, 0)
        chosen_metric = np.where(idx >= 0, metric_matrix[rows, safe], np.nan)
        chosen_abserr = np.where(idx >= 0, abserr_matrix[rows, safe], np.nan)
        chosen_avail = np.where(idx >= 0, avail_matrix[rows, safe], False)
        bound = pd.to_numeric(out[f"certificate_bound__{sfx}"], errors="coerce").to_numpy(dtype=float)
        no_support = idx < 0
        is_donor = np.array([str(c) == "donor_ridge" for c in choice])

        def final_rule_block(method: str, tau: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            degenerate = (~no_support) & (~chosen_avail) & is_donor
            unavailable = (~no_support) & (~chosen_avail) & (~is_donor)
            under_bound = np.isfinite(bound) & np.isfinite(tau) & (bound <= tau)
            ok = (~no_support) & chosen_avail & under_bound
            mode = np.select(
                [ok, degenerate, no_support, unavailable],
                ["ok", "degenerate_donor", "abstain", "abstain"],
                default="abstain",
            )
            reason = np.select(
                [ok, degenerate, no_support, unavailable],
                ["admitted", "donor_estimate_unavailable", "no_supported_estimator", "chosen_estimator_unavailable"],
                default="bound_above_threshold",
            )
            out[f"mode__{sfx}__{method}"] = mode
            out[f"decision__{sfx}__{method}"] = ok
            out[f"abstain_reason__{sfx}__{method}"] = reason
            out[f"metric__{sfx}__{method}"] = np.where(ok, chosen_metric, np.nan)
            out[f"abserr__{sfx}__{method}"] = np.where(ok, chosen_abserr, np.nan)
            out[f"source__{sfx}__{method}"] = np.where(ok, choice, "none")
            out[f"threshold__{sfx}__{method}"] = tau
            return ok, degenerate

        ok_primary, degenerate_primary = final_rule_block("final_rule", tau_primary)
        for method in FINAL_RULE_VARIANTS[1:]:
            final_rule_block(method, tau_for(method, THRESHOLD_FALLBACK))

        # --- the labelled observed-days fallback (primary threshold) -------- #
        fb_any = (~no_support) & (~chosen_avail)
        fb_ok = fb_any & obs_avail_all & np.isfinite(tau_primary) & (np.isfinite(bound) & (bound <= tau_primary))
        mode_fb = np.select([ok_primary, fb_ok], ["ok", "observed_window_only"], default="abstain")
        out[f"mode__{sfx}__final_rule_fb"] = mode_fb
        out[f"decision__{sfx}__final_rule_fb"] = ok_primary | fb_ok
        out[f"metric__{sfx}__final_rule_fb"] = np.where(ok_primary, chosen_metric, np.where(fb_ok, obs_metric_all, np.nan))
        out[f"abserr__{sfx}__final_rule_fb"] = np.where(ok_primary, chosen_abserr, np.where(fb_ok, obs_abserr_all, np.nan))
        out[f"source__{sfx}__final_rule_fb"] = np.where(ok_primary, choice, np.where(fb_ok, "observed_days", "none"))
        out[f"threshold__{sfx}__final_rule_fb"] = tau_primary

        # --- simple rules --------------------------------------------------- #
        policy_err = pd.to_numeric(out[f"abserr_policy__{sfx}"], errors="coerce").to_numpy(dtype=float)
        policy_metric = pd.to_numeric(out[f"metric_policy__{sfx}"], errors="coerce").to_numpy(dtype=float)
        policy_ok = np.isfinite(policy_err)
        peak_score = pd.to_numeric(out["peak_overlap"], errors="coerce").to_numpy(dtype=float)
        length_score = pd.to_numeric(out["longest_run"], errors="coerce").to_numpy(dtype=float)
        for method, score, limit in (
            ("peak_window_rule", peak_score, tau_for("peak_window_rule", PEAK_RULE_MAX_OVERLAP)),
            ("length_rule", length_score, tau_for("length_rule", LENGTH_RULE_DAYS)),
            ("peak_window_rule_pub10", peak_score, np.full(n, PEAK_RULE_MAX_OVERLAP)),
            ("length_rule_pub49", length_score, np.full(n, LENGTH_RULE_DAYS)),
            ("length_rule_pub140", length_score, np.full(n, LENGTH_RULE_DAYS_WIDE)),
        ):
            decide = np.isfinite(score) & np.isfinite(limit) & (score <= limit) & policy_ok
            out[f"score__{sfx}__{method}"] = score
            out[f"threshold__{sfx}__{method}"] = limit
            out[f"decision__{sfx}__{method}"] = decide
            out[f"mode__{sfx}__{method}"] = np.where(decide, "ok", "abstain")
            out[f"metric__{sfx}__{method}"] = np.where(decide, policy_metric, np.nan)
            out[f"abserr__{sfx}__{method}"] = np.where(decide, policy_err, np.nan)
            out[f"source__{sfx}__{method}"] = np.where(decide, out[f"policy_choice__{sfx}"].astype(str), "none")

        # --- the two reconstructor paths ----------------------------------- #
        donor_err = pd.to_numeric(out[f"abserr_donor_ridge__{sfx}"], errors="coerce").to_numpy(dtype=float)
        donor_metric = pd.to_numeric(out[f"metric_donor_ridge__{sfx}"], errors="coerce").to_numpy(dtype=float)
        donor_avail = out[f"available_donor_ridge__{sfx}"].to_numpy(dtype=bool)
        out[f"decision__{sfx}__donor_ridge_path"] = donor_avail
        out[f"mode__{sfx}__donor_ridge_path"] = np.where(donor_avail, "ok", "degenerate_donor")
        out[f"abserr__{sfx}__donor_ridge_path"] = np.where(donor_avail, donor_err, np.nan)
        out[f"metric__{sfx}__donor_ridge_path"] = np.where(donor_avail, donor_metric, np.nan)
        out[f"source__{sfx}__donor_ridge_path"] = np.where(donor_avail, "donor_ridge", "none")

        out[f"decision__{sfx}__observed_days_path"] = obs_avail_all
        out[f"mode__{sfx}__observed_days_path"] = np.where(obs_avail_all, "observed_window_only", "abstain")
        out[f"abserr__{sfx}__observed_days_path"] = np.where(obs_avail_all, obs_abserr_all, np.nan)
        out[f"metric__{sfx}__observed_days_path"] = np.where(obs_avail_all, obs_metric_all, np.nan)
        out[f"source__{sfx}__observed_days_path"] = np.where(obs_avail_all, "observed_days", "none")

        # --- secondary: the frozen certificate object ---------------------- #
        if frozen is not None:
            f_choice = frozen["choice"][sfx]
            f_bound = frozen["bound"][sfx]
            f_tau = tau_for("frozen_cert_rule", THRESHOLD_FALLBACK)
            f_idx = np.array([est_names.index(str(c)) if str(c) in est_names else -1 for c in f_choice], dtype=int)
            f_safe = np.maximum(f_idx, 0)
            f_donor = np.array([str(c) == "donor_ridge" for c in f_choice])
            f_avail = np.where(f_idx >= 0, avail_matrix[rows, f_safe], False)
            f_abserr = np.where(f_idx >= 0, abserr_matrix[rows, f_safe], np.nan)
            f_metric = np.where(f_idx >= 0, metric_matrix[rows, f_safe], np.nan)
            f_degen = (f_idx >= 0) & (~f_avail) & f_donor
            f_ok = (f_idx >= 0) & f_avail & np.isfinite(f_bound) & np.isfinite(f_tau) & (f_bound <= f_tau)
            out[f"mode__{sfx}__frozen_cert_rule"] = np.select([f_ok, f_degen], ["ok", "degenerate_donor"], default="abstain")
            out[f"decision__{sfx}__frozen_cert_rule"] = f_ok
            out[f"abserr__{sfx}__frozen_cert_rule"] = np.where(f_ok, f_abserr, np.nan)
            out[f"metric__{sfx}__frozen_cert_rule"] = np.where(f_ok, f_metric, np.nan)
            out[f"source__{sfx}__frozen_cert_rule"] = np.where(f_ok, f_choice, "none")
            out[f"threshold__{sfx}__frozen_cert_rule"] = f_tau

    derived: dict[str, np.ndarray] = {}
    for _, sfx, _ in LEVELS:
        available_methods = [m for m in ALL_METHODS if f"decision__{sfx}__{m}" in out.columns]
        for method in available_methods:
            decision = out[f"decision__{sfx}__{method}"].to_numpy(dtype=bool)
            abserr = pd.to_numeric(out[f"abserr__{sfx}__{method}"], errors="coerce").to_numpy(dtype=float)
            usable = decision & np.isfinite(abserr)
            exceed = np.isfinite(abserr) & (abserr > TOL)
            derived[f"usable__{sfx}__{method}"] = usable
            derived[f"ok__{sfx}__{method}"] = out[f"mode__{sfx}__{method}"].eq("ok").to_numpy()
            derived[f"fail_decided__{sfx}__{method}"] = decision & exceed
            derived[f"fail_all__{sfx}__{method}"] = (~usable) | exceed
            if f"score__{sfx}__{method}" not in out.columns:
                if method in ALL_METHODS and f"threshold__{sfx}__{method}" in out.columns:
                    derived[f"score__{sfx}__{method}"] = pd.to_numeric(
                        out[f"certificate_bound__{sfx}"], errors="coerce"
                    ).to_numpy(dtype=float)
                elif method == "donor_ridge_path":
                    derived[f"score__{sfx}__{method}"] = pd.to_numeric(out["masked_days"], errors="coerce").to_numpy(dtype=float)
                else:
                    derived[f"score__{sfx}__{method}"] = pd.to_numeric(
                        out[f"abserr__{sfx}__{method}"], errors="coerce"
                    ).to_numpy(dtype=float)
    new_columns = pd.DataFrame(derived, index=out.index)
    keep = out.drop(columns=[c for c in new_columns.columns if c in out.columns])
    return pd.concat([keep, new_columns], axis=1)


# --------------------------------------------------------------------------- #
# phase 6 - tables
# --------------------------------------------------------------------------- #
def table_methods(cases: pd.DataFrame, sfx: str) -> list[str]:
    return [m for m in ALL_METHODS if f"mode__{sfx}__{m}" in cases.columns]


def failure_mode_table(cases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, sfx, _ in LEVELS:
        for method in table_methods(cases, sfx):
            mode = cases[f"mode__{sfx}__{method}"].astype(str)
            total = int(len(mode))
            for label in FAILURE_MODES:
                count = int((mode == label).sum())
                rows.append(
                    {
                        "cofail_level": level_name(sfx),
                        "cofail_fraction": FRACTIONS[sfx],
                        "method": method,
                        "secondary_method": bool(method in SECONDARY_METHODS),
                        "failure_mode": label,
                        "n_candidates": total,
                        "n_groups": int(cases["replay_group_id"].nunique()),
                        "n_networks": int(cases["network_id"].nunique()),
                        "n": count,
                        "share": float(count / total) if total else float("nan"),
                    }
                )
    return pd.DataFrame(rows)


def method_error_table(cases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, sfx, _ in LEVELS:
        for method in table_methods(cases, sfx):
            decision = cases[f"decision__{sfx}__{method}"].to_numpy(dtype=bool)
            usable = cases[f"usable__{sfx}__{method}"].to_numpy(dtype=bool)
            ok = cases[f"ok__{sfx}__{method}"].to_numpy(dtype=bool)
            abserr = pd.to_numeric(cases[f"abserr__{sfx}__{method}"], errors="coerce").to_numpy(dtype=float)
            fail_decided = cases[f"fail_decided__{sfx}__{method}"].to_numpy(dtype=bool)
            fail_all = cases[f"fail_all__{sfx}__{method}"].to_numpy(dtype=bool)
            mode = cases[f"mode__{sfx}__{method}"].astype(str)
            n = int(len(cases))
            rows.append(
                {
                    "cofail_level": level_name(sfx),
                    "cofail_fraction": FRACTIONS[sfx],
                    "method": method,
                    "secondary_method": bool(method in SECONDARY_METHODS),
                    "n_candidates": n,
                    "n_groups": int(cases["replay_group_id"].nunique()),
                    "n_networks": int(cases["network_id"].nunique()),
                    "n_decided": int(decision.sum()),
                    "decided_share": float(decision.mean()),
                    "n_usable": int(usable.sum()),
                    "usable_share": float(usable.mean()),
                    "n_strictly_ok": int(ok.sum()),
                    "strict_ok_share": float(ok.mean()),
                    "n_available_for_error": int(usable.sum()),
                    "consequential_error_rate_among_available": float(fail_decided[usable].mean()) if usable.any() else float("nan"),
                    "mean_abserr_among_available": float(np.nanmean(np.where(usable, abserr, np.nan))) if usable.any() else float("nan"),
                    "consequential_error_rate_over_all_candidates": float(fail_all.mean()),
                    "mean_abserr_among_decided": float(np.nanmean(np.where(decision, abserr, np.nan))) if decision.any() else float("nan"),
                    "share_mode_ok": float((mode == "ok").mean()),
                    "share_mode_degenerate_donor": float((mode == "degenerate_donor").mean()),
                    "share_mode_observed_window_only": float((mode == "observed_window_only").mean()),
                    "share_mode_abstain": float((mode == "abstain").mean()),
                }
            )
    return pd.DataFrame(rows)


def estimator_outcome_table(cases: pd.DataFrame) -> pd.DataFrame:
    """Estimator-level availability and error, denominators stated."""

    truth = pd.to_numeric(cases["truth_hottest30"], errors="coerce").to_numpy(dtype=float)
    rows = []
    for _, sfx, _ in LEVELS:
        entries = [(name, f"metric_{name}", f"available_{name}", None) for name in NON_DONOR_FILLS]
        entries += [
            ("observed_days", "metric_observed_days", "available_observed_days", None),
            ("observed_strict_window", "metric_observed_strict_window", "available_observed_strict_window", None),
            (
                "donor_ridge",
                f"metric_donor_ridge__{sfx}",
                f"available_donor_ridge__{sfx}",
                f"n_unfilled_hidden_days_donor_ridge__{sfx}",
            ),
        ]
        for name, metric_col, avail_col, unfilled_col in entries:
            metric = pd.to_numeric(cases[metric_col], errors="coerce").to_numpy(dtype=float)
            avail = cases[avail_col].to_numpy(dtype=bool)
            abserr = np.abs(metric - truth)
            exceed = np.isfinite(abserr) & (abserr > TOL)
            usable = avail & np.isfinite(abserr)
            row = {
                "cofail_level": level_name(sfx),
                "cofail_fraction": FRACTIONS[sfx],
                "estimator": name,
                "n_candidates": int(len(cases)),
                "n_available": int(avail.sum()),
                "available_share": float(avail.mean()),
                "consequential_error_rate_among_available": float(exceed[usable].mean()) if usable.any() else float("nan"),
                "mean_abserr_among_available": float(np.nanmean(np.where(usable, abserr, np.nan))) if usable.any() else float("nan"),
                "consequential_error_rate_over_all_candidates": float(((~usable) | exceed).mean()),
                "n_unfilled_hidden_days_total": int(
                    pd.to_numeric(cases[unfilled_col], errors="coerce").fillna(0).sum() if unfilled_col else 0
                ),
            }
            if name == "donor_ridge":
                status = cases[f"donor_status__{sfx}"].astype(str)
                row["n_no_donor_model_formed"] = int((status == "degenerate_donor").sum())
                row["n_model_formed_but_predictions_incomplete"] = int(
                    (status == "donor_incomplete_placement").sum()
                )
                row["n_no_finite_donor_estimate"] = int(len(cases) - avail.sum())
            rows.append(row)
    return pd.DataFrame(rows)


def degenerate_donor_audit(cases: pd.DataFrame) -> pd.DataFrame:
    """What the old donor column actually contained, and what the honest flags say.

    The step-5b defect: when the donor reconstructor could not be formed,
    ``hottest_window_mean`` returned the hottest *fully observed* window mean and
    the value was still labelled ``donor_ridge``.  This table counts those rows
    and prices the substitution.
    """

    truth = pd.to_numeric(cases["truth_hottest30"], errors="coerce").to_numpy(dtype=float)
    strict = pd.to_numeric(cases["metric_observed_strict_window"], errors="coerce").to_numpy(dtype=float)
    observed = pd.to_numeric(cases["metric_observed_days"], errors="coerce").to_numpy(dtype=float)
    rows = []
    for _, sfx, _ in LEVELS:
        donor_metric = pd.to_numeric(cases[f"metric_donor_ridge__{sfx}"], errors="coerce").to_numpy(dtype=float)
        donor_avail = cases[f"available_donor_ridge__{sfx}"].to_numpy(dtype=bool)
        degenerate = ~donor_avail
        old_finite = degenerate & np.isfinite(strict)
        old_error = np.abs(strict - truth)
        observed_error = np.abs(observed - truth)
        donor_error = np.abs(donor_metric - truth)
        rows.append(
            {
                "cofail_level": level_name(sfx),
                "cofail_fraction": FRACTIONS[sfx],
                "n_candidate_level_rows": int(len(cases)),
                "n_donor_available": int(donor_avail.sum()),
                "n_donor_unavailable": int(degenerate.sum()),
                "share_donor_unavailable": float(degenerate.mean()),
                "n_no_donor_model_formed": int(cases[f"donor_status__{sfx}"].astype(str).eq("degenerate_donor").sum()),
                "n_old_probe_would_report_a_number": int(old_finite.sum()),
                "share_of_degenerate_where_old_probe_reported_a_number": float(old_finite.sum() / max(1, int(degenerate.sum()))),
                "mean_abserr_old_probe_reported_as_donor_ridge": float(np.nanmean(old_error[old_finite])) if old_finite.any() else float("nan"),
                "mean_abserr_labelled_observed_days_on_degenerate": float(np.nanmean(observed_error[degenerate])) if degenerate.any() else float("nan"),
                "mean_abserr_donor_when_available": float(np.nanmean(donor_error[donor_avail])) if donor_avail.any() else float("nan"),
                "n_rows_where_chosen_estimator_was_donor_ridge_but_unavailable": int(
                    cases[f"mode__{sfx}__final_rule"].eq("degenerate_donor").sum()
                ),
                "n_rows_where_strict_rule_abstained": int(cases[f"mode__{sfx}__final_rule"].eq("abstain").sum()),
                "n_rows_where_labelled_fallback_was_used": int(
                    cases[f"mode__{sfx}__final_rule_fb"].eq("observed_window_only").sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def policy_composition_table(cases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, sfx, _ in LEVELS:
        counts = cases[f"policy_choice__{sfx}"].astype(str).value_counts()
        for name, count in counts.items():
            rows.append(
                {
                    "cofail_level": level_name(sfx),
                    "cofail_fraction": FRACTIONS[sfx],
                    "policy_choice": name,
                    "n": int(count),
                    "share": float(count / len(cases)),
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# phase 7 - contrasts
# --------------------------------------------------------------------------- #
def select_matched(block: pd.DataFrame, method: str, sfx: str, k: int) -> np.ndarray:
    score = pd.to_numeric(block[f"score__{sfx}__{method}"], errors="coerce").to_numpy(dtype=float)
    score = np.where(np.isfinite(score), score, np.inf)
    order = np.argsort(score, kind="mergesort")
    return order[: max(0, min(int(k), len(order)))]


def method_stat(block: pd.DataFrame, view: str, stat: str, method: str, sfx: str, k: int | None) -> float:
    decision = block[f"decision__{sfx}__{method}"].to_numpy(dtype=bool)
    usable = block[f"usable__{sfx}__{method}"].to_numpy(dtype=bool)
    ok = block[f"ok__{sfx}__{method}"].to_numpy(dtype=bool)
    fail_decided = block[f"fail_decided__{sfx}__{method}"].to_numpy(dtype=bool)
    fail_all = block[f"fail_all__{sfx}__{method}"].to_numpy(dtype=bool)
    if view == "absolute_admission":
        if stat == "error_rate_among_decided":
            return float(fail_decided[decision].mean()) if decision.any() else float("nan")
        if stat == "usable_share":
            return float(usable.mean())
        if stat == "strict_ok_share":
            return float(ok.mean())
        if stat == "admissible_record_share":
            # decision-relevant combination: the record is used only if the
            # method produces it AND the metric is within tolerance; a failure
            # or an abstention is a lost record, not a free option
            return float((~fail_all).mean())
        raise KeyError(stat)
    selected = select_matched(block, method, sfx, int(k))
    if selected.size == 0:
        return float("nan")
    if stat == "error_rate_among_decided":
        return float(fail_all[selected].mean())
    if stat == "usable_share":
        return float(usable[selected].mean())
    if stat == "admissible_record_share":
        return float((~fail_all[selected]).mean())
    raise KeyError(stat)


def contrast_statistic(block: pd.DataFrame, spec: dict) -> float:
    view, stat = spec["view"], spec["statistic"]
    left, right = spec["left"], spec["right"]
    if spec.get("group_equal"):
        # pooled view: every group contributes once.  Each co-failure level is a
        # repeated measure of the same group, so the three level-specific
        # differences are averaged before any comparison across groups, and no
        # pseudo-replication across levels is possible.
        per_level = []
        for _, level_sfx, _ in LEVELS:
            k = None
            if view == "matched_decided_share":
                k = int(block[f"decision__{level_sfx}__final_rule"].to_numpy(dtype=bool).sum())
            elif view == "matched_70":
                k = max(1, int(round(0.70 * len(block))))
            per_level.append(
                method_stat(block, view, stat, left, level_sfx, k)
                - method_stat(block, view, stat, right, level_sfx, k)
            )
        finite = np.asarray([v for v in per_level if np.isfinite(v)], dtype=float)
        return float(finite.mean()) if finite.size else float("nan")
    sfx = spec["sfx"]
    k = None
    if view == "matched_decided_share":
        k = int(block[f"decision__{sfx}__final_rule"].to_numpy(dtype=bool).sum())
    elif view == "matched_70":
        k = max(1, int(round(0.70 * len(block))))
    return float(method_stat(block, view, stat, left, sfx, k) - method_stat(block, view, stat, right, sfx, k))


def run_contrasts(
    cases: pd.DataFrame,
    *,
    draws_override: int | None = None,
    level_subset: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    specs = []
    for view, draws in (
        ("absolute_admission", BOOT_DRAWS_PRIMARY),
        ("matched_decided_share", BOOT_DRAWS_SECONDARY),
        ("matched_70", BOOT_DRAWS_SECONDARY),
    ):
        stats = ["error_rate_among_decided", "usable_share"]
        if view == "absolute_admission":
            stats = stats + ["strict_ok_share", "admissible_record_share"]
        for stat in stats:
            for _, sfx, _ in LEVELS:
                if level_subset is not None and sfx not in level_subset:
                    continue
                for left, right in CONTRAST_PAIRS:
                    specs.append(
                        {
                            "view": view,
                            "statistic": stat,
                            "left": left,
                            "right": right,
                            "sfx": sfx,
                            "level": level_name(sfx),
                            "group_equal": False,
                            "draws": draws,
                        }
                    )
    pooled_sfx = LEVELS[0][1]
    for left, right in CONTRAST_PAIRS:
        for stat in ("error_rate_among_decided", "usable_share", "admissible_record_share"):
            specs.append(
                {
                    "view": "absolute_admission",
                    "statistic": stat,
                    "left": left,
                    "right": right,
                    "sfx": pooled_sfx,
                    "level": "pooled_group_equal",
                    "group_equal": True,
                    "draws": BOOT_DRAWS_SECONDARY,
                }
            )
    if draws_override is not None:
        for spec in specs:
            spec["draws"] = int(draws_override)

    cols = ["network_id", "replay_group_id"]
    for _, sfx, _ in LEVELS:
        for method in METHODS:
            for prefix in ("decision", "usable", "ok", "fail_decided", "fail_all", "score"):
                column = f"{prefix}__{sfx}__{method}"
                if column in cases.columns:
                    cols.append(column)
    frame = cases[cols].copy()

    def one(spec: dict) -> dict:
        try:
            boot = cluster_bootstrap(
                frame,
                lambda block: contrast_statistic(block, spec),
                cluster="network_id",
                draws=int(spec["draws"]),
                seed=stable_seed(spec["left"], spec["right"], spec["view"], spec["statistic"], spec["sfx"], SEED),
                alpha=BOOT_ALPHA,
            )
            out = {
                "point": float(boot["point"]),
                "low": float(boot["low"]),
                "high": float(boot["high"]),
                "n_clusters": int(boot["n_clusters"]),
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001
            out = {
                "point": float("nan"),
                "low": float("nan"),
                "high": float("nan"),
                "n_clusters": int(cases["network_id"].nunique()),
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {k: spec[k] for k in ("view", "statistic", "left", "right", "level", "sfx", "draws", "group_equal")} | out

    results = parallel_with_fallback(
        one, specs, (min(len(specs), 32), 8, 2, 1), verbose=0, unpack=False
    )
    contrasts = pd.DataFrame(results)
    contrasts["contrast"] = contrasts["left"] + "__minus__" + contrasts["right"]
    contrasts["point_pp"] = contrasts["point"] * 100
    contrasts["ci_low_pp"] = contrasts["low"] * 100
    contrasts["ci_high_pp"] = contrasts["high"] * 100
    contrasts["excludes_zero_95"] = (contrasts["low"] > 0) | (contrasts["high"] < 0)
    contrasts["statistic_label"] = np.select(
        [
            contrasts["statistic"].eq("error_rate_among_decided"),
            contrasts["statistic"].eq("usable_share"),
            contrasts["statistic"].eq("admissible_record_share"),
        ],
        [
            "consequential_error_rate_among_decided",
            "usable_record_share",
            "admissible_record_share",
        ],
        default="strict_ok_share",
    )
    contrasts["n_candidates"] = int(len(cases))
    return contrasts.sort_values(["view", "level", "statistic", "left", "right"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
METHOD_ERROR_COLUMNS = (
    "cofail_level",
    "method",
    "n_candidates",
    "n_groups",
    "n_networks",
    "n_decided",
    "decided_share",
    "usable_share",
    "strict_ok_share",
    "consequential_error_rate_among_available",
    "mean_abserr_among_available",
    "consequential_error_rate_over_all_candidates",
    "share_mode_degenerate_donor",
    "share_mode_observed_window_only",
    "share_mode_abstain",
)
ESTIMATOR_OUTCOME_COLUMNS = (
    "cofail_level",
    "estimator",
    "n_candidates",
    "n_available",
    "available_share",
    "consequential_error_rate_among_available",
    "mean_abserr_among_available",
    "consequential_error_rate_over_all_candidates",
)
CONTRAST_VIEW_COLUMNS = (
    "level",
    "statistic_label",
    "contrast",
    "point_pp",
    "ci_low_pp",
    "ci_high_pp",
    "n_clusters",
    "draws",
    "excludes_zero_95",
)


def _contrast_view(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [name for name in CONTRAST_VIEW_COLUMNS if name in frame.columns]
    out = frame[columns].copy()
    for name in ("point_pp", "ci_low_pp", "ci_high_pp"):
        if name in out.columns:
            out[name] = pd.to_numeric(out[name], errors="coerce").round(3)
    return out


def _find(contrasts: pd.DataFrame, view: str, level: str, statistic: str, left: str, right: str) -> dict | None:
    block = contrasts.loc[
        contrasts["view"].eq(view)
        & contrasts["level"].eq(level)
        & contrasts["statistic"].eq(statistic)
        & contrasts["left"].eq(left)
        & contrasts["right"].eq(right)
    ]
    if block.empty:
        return None
    return block.iloc[0].to_dict()


def _fmt(row: dict | None) -> str:
    if row is None or not np.isfinite(row.get("point", np.nan)):
        return "not computed"
    return f"{row['point_pp']:+.2f} pp [{row['ci_low_pp']:+.2f}, {row['ci_high_pp']:+.2f}]"


def write_summary(
    out_dir: Path,
    cases: pd.DataFrame,
    method_error: pd.DataFrame,
    estimator_outcomes: pd.DataFrame,
    donor_audit: pd.DataFrame,
    contrasts: pd.DataFrame,
    fingerprint: dict,
    extra: dict,
) -> None:
    n_groups = int(len(cases))
    n_levels = len(LEVELS)
    rs = fingerprint["replicate_structure"]
    diag = fingerprint["case_build_diagnostics"]
    repro = fingerprint.get("certificate_table_reproduction", {})
    fold_detail = (fingerprint.get("calibration_fold_detail") or [{}])[0]
    degenerate_counts = {}
    for _, sfx, _ in LEVELS:
        degenerate_counts[level_name(sfx)] = {
            "donor_ridge_path": int(cases[f"mode__{sfx}__donor_ridge_path"].eq("degenerate_donor").sum()),
            "final_rule": int(cases[f"mode__{sfx}__final_rule"].eq("degenerate_donor").sum()),
            "final_rule_abstain": int(cases[f"mode__{sfx}__final_rule"].eq("abstain").sum()),
            "final_rule_fb_observed_window_only": int(cases[f"mode__{sfx}__final_rule_fb"].eq("observed_window_only").sum()),
        }

    def me(level: str, method: str) -> dict | None:
        block = method_error.loc[method_error["cofail_level"].eq(level) & method_error["method"].eq(method)]
        return None if block.empty else block.iloc[0].to_dict()

    lines: list[str] = []
    lines += [
        "# P0-03 — the final admission rule on the monitoring-calendar replay",
        "",
        f"`{fingerprint['script']}` (sha256 `{fingerprint['script_sha256'][:16]}…`), git HEAD `{fingerprint['git_head']}`, "
        f"runtime {fingerprint['runtime_seconds']} s, generated {fingerprint['generated_utc']}.",
        "",
        "## 1. What was replayed, and on how many units",
        "",
        f"- **{n_groups} candidate groups** ({rs['n_networks']} networks, {rs['n_stations']} stations, "
        f"{rs['n_families']}); **{n_groups * n_levels} candidate-level rows** are implied by the three "
        "co-failure levels, but the levels are repeated measures on the same group and are stored as suffixed "
        "columns of one row: the number of experiments is the number of groups, **not** groups x 3.",
        f"- cross-year groups (gap placed on the continuous multi-year axis and evaluated in both affected "
        f"calendar years): **{rs['n_cross_year_groups']}**.",
        f"- gap-length assertions: **{fingerprint['assertions']['status']}** "
        f"({fingerprint['assertions']['n_groups_checked']} groups, "
        f"{fingerprint['assertions']['n_cross_year_pairs_checked']} cross-year pairs).",
        f"- co-failure levels: {', '.join(f'{n} ({f:.1f})' for n, _, f in LEVELS)} donors masked with the target calendar.",
        f"- co-failure realisation: {json.dumps(rs['cofail_realisation'])}; "
        f"{rs['n_groups_single_donor']} of {n_groups} groups have a single donor, and for those the "
        "'partial' level necessarily co-fails that donor and reproduces the all-donor condition "
        "(the strict-partial share is reported above);",
        f"- placement reduction: {fingerprint['reduction_statement']}.",
        "",
        "## 2. Threshold paths actually used",
        "",
        f"- the parallel workstream file exists: **{fingerprint['external_threshold_file'].get('exists')}** "
        f"(`{fingerprint['external_threshold_file'].get('path')}`, sha256 "
        f"`{str(fingerprint['external_threshold_file'].get('sha256'))[:16]}…`, "
        f"{fingerprint['external_threshold_file'].get('generated_by')}).",
        f"- its `{P0_02_SCORE_FINAL}` thresholds live in the units of "
        f"`results/v17_fitness/step6_screen/development_certificates.parquet`.  That table cannot be reproduced "
        f"with the current `screen.py`: on its fold 0 the maximum absolute bound difference is "
        f"**{repro.get('max_abs_bound_difference_c')} °C** and only "
        f"**{repro.get('choice_agreement')}** of the certificate choices agree, so numerically "
        "transferring its threshold into this script's bounds is not sound (the code changed after the table was "
        "built).  The literal transfer is nevertheless reported as the labelled secondary row "
        "`final_rule_literal_p002_tau`.",
        "- **primary path**: the p0_02 pre-registered *rule* (largest calibration retention in a 0.10..0.95 grid "
        "whose calibration false-admit rate plus a one-sided 95 % network-clustered bootstrap upper bound is "
        "<= 5 %; admit iff score <= threshold; if nothing qualifies, admit nothing) re-implemented in these units, "
        "with a per-held-out-network three-way network-disjoint split of the labelled corpus "
        f"({fold_detail.get('n_fit_networks', 'n/a')} networks for the certificate heads / "
        f"{fold_detail.get('n_scale_calibration_networks', 'n/a')} for the conformal scale / "
        f"{fold_detail.get('n_threshold_calibration_networks', 'n/a')} for the threshold); the held-out network is "
        "in none of them.",
        "- the two simple rules **do** consume the parallel workstream's frozen per-fold thresholds "
        f"({json.dumps({k: v.get('fold_thresholds') for k, v in fingerprint['simple_rule_thresholds'].items()})}) "
        "because their units (days, peak-window share) are transferable; the published fixed limits (49 d, 140 d, "
        "10 % overlap) are reported next to them as secondary rows.",
        f"- primary thresholds per held-out network: "
        f"{json.dumps({k: round(v, 4) for k, v in fingerprint['threshold_paths']['final_rule']['thresholds_by_network'].items()})}",
        "- no replay label entered threshold selection; `truth_invariance_verified` = "
        f"{fingerprint['truth_invariance_verified']}.",
        "",
        "## 3. Failure modes and error, per method and per co-failure level",
        "",
        "All shares below are over the same candidate pool "
        f"(denominator = {n_groups} groups, one row per group, levels as repeated measures).",
        "",
        method_error[list(METHOD_ERROR_COLUMNS)].to_string(index=False),
        "",
        "### 3b. Estimator-level availability (donor reconstruction is never substituted)",
        "",
        estimator_outcomes[list(ESTIMATOR_OUTCOME_COLUMNS)].to_string(index=False),
        "",
        "### 3c. What the old donor column actually contained (F04)",
        "",
        donor_audit.to_string(index=False),
        "",
        "## 4. Degenerate-donor accounting",
        "",
        f"- cases where the donor reconstructor could not be formed: {json.dumps(degenerate_counts)}",
        "- the strict final rule treats them as **not admitted** (`degenerate_donor`); the donor estimate stays NaN "
        "and is never replaced by a hottest fully observed window;",
        "- the labelled fallback variant `final_rule_fb` reports them as `observed_window_only`, i.e. the incumbent "
        "`observed_days` estimator named as itself; the donor rows and the observed-window rows are never merged;",
        f"- degenerate-donor rows whose certificate pick was `donor_ridge` but whose estimate could not be formed: "
        f"{donor_audit['n_rows_where_chosen_estimator_was_donor_ridge_but_unavailable'].tolist()} "
        f"({LEVEL_NAMES});",
        f"- the old probe would have reported a hottest fully observed window mean under the donor name for "
        f"{donor_audit['n_old_probe_would_report_a_number'].tolist()} of "
        f"{donor_audit['n_donor_unavailable'].tolist()} donor-unavailable rows, at mean |error| "
        f"{[round(v, 4) for v in donor_audit['mean_abserr_old_probe_reported_as_donor_ridge']]} C, against a true "
        f"donor error of {[round(v, 4) for v in donor_audit['mean_abserr_donor_when_available']]} C on the rows "
        "where donors were available.",
        "",
        "## 5. Final rule vs the simple rules (network-clustered bootstrap)",
        "",
        "Absolute admission (each rule at its own frozen / calibrated threshold):",
        "",
    ]
    headline = contrasts.loc[contrasts["view"].eq("absolute_admission") & ~contrasts["group_equal"]]
    lines.append(_contrast_view(headline).to_string(index=False))
    lines += [
        "",
        "The decision-relevant combination is `admissible_record_share` (a record the agency can use: produced and "
        "within 0.5 C).  `usable_record_share` counts produced records whatever their error; "
        "`consequential_error_rate_among_decided` is the precision of the cases each rule decides, with different "
        "denominators by construction.",
        "",
        "Matched decision counts (forced-decision ranking view, abstention disallowed):",
        "",
        _contrast_view(contrasts.loc[contrasts["view"].isin(["matched_decided_share", "matched_70"])]).to_string(index=False),
        "",
        "Pooled view (each co-failure level difference averaged inside the group first, so the three levels are not "
        "pseudo-replicates):",
        "",
        _contrast_view(contrasts.loc[contrasts["group_equal"]]).to_string(index=False),
        "",
        "## 6. Verdict under all-donor failure",
        "",
    ]
    all_level = "all_donor_failure"
    fr_err = _find(contrasts, "absolute_admission", all_level, "error_rate_among_decided", "final_rule", "peak_window_rule")
    fr_len = _find(contrasts, "absolute_admission", all_level, "error_rate_among_decided", "final_rule", "length_rule")
    fr_use = _find(contrasts, "absolute_admission", all_level, "usable_share", "final_rule", "peak_window_rule")
    fr_use_len = _find(contrasts, "absolute_admission", all_level, "usable_share", "final_rule", "length_rule")
    fr_adm = _find(contrasts, "absolute_admission", all_level, "admissible_record_share", "final_rule", "peak_window_rule")
    fr_adm_pub = _find(contrasts, "absolute_admission", all_level, "admissible_record_share", "final_rule", "length_rule_pub49")
    fr_err_pub = _find(contrasts, "absolute_admission", all_level, "error_rate_among_decided", "final_rule", "length_rule_pub49")
    fr_adm_len = _find(contrasts, "absolute_admission", all_level, "admissible_record_share", "final_rule", "length_rule")
    fe = me(all_level, "final_rule")
    pe = me(all_level, "peak_window_rule")
    le = me(all_level, "length_rule")
    lines += [
        f"- among decided cases (different denominators): final rule minus peak-window rule = {_fmt(fr_err)}; "
        f"minus length rule = {_fmt(fr_len)} (positive means the final rule has the higher consequential-error rate);",
        f"- usable-record share (records produced): final rule minus peak-window rule = {_fmt(fr_use)}; "
        f"minus length rule = {_fmt(fr_use_len)};",
        f"- admissible-record share (produced AND within 0.5 C): final rule minus the frozen-threshold peak-window "
        f"rule = {_fmt(fr_adm)}; minus the frozen-threshold length rule = {_fmt(fr_adm_len)}; versus the published "
        f"49 d length rule = {_fmt(fr_adm_pub)} (error rate among decided {_fmt(fr_err_pub)});",
        f"- over ALL candidates with failures counted as failures: final rule "
        f"{fe['consequential_error_rate_over_all_candidates']:.4f} vs peak-window "
        f"{pe['consequential_error_rate_over_all_candidates']:.4f} vs length "
        f"{le['consequential_error_rate_over_all_candidates']:.4f} "
        "(abstention is a lost record, not a free option);",
        f"- decided shares under all-donor failure: final {fe['decided_share']:.4f}, peak {pe['decided_share']:.4f}, "
        f"length {le['decided_share']:.4f}; strict `ok` shares: final {fe['strict_ok_share']:.4f}, "
        f"peak {pe['strict_ok_share']:.4f}, length {le['strict_ok_share']:.4f}.",
        f"- realised consequential-error rate among the final rule's decided cases: target-only "
        f"{(me('target_only', 'final_rule') or {}).get('consequential_error_rate_among_available', float('nan')):.4f}, "
        f"partial {(me('partial_donor_failure', 'final_rule') or {}).get('consequential_error_rate_among_available', float('nan')):.4f}, "
        f"all-donor {(fe or {}).get('consequential_error_rate_among_available', float('nan')):.4f} against the "
        f"{RISK_CAP:.0%} calibration cap (the threshold transfers conservatively or not, and this is the check);",
        "",
    ]
    if fr_adm is not None and np.isfinite(fr_adm.get("point", np.nan)) and fr_adm["point"] > 0:
        lines.append(
            "**Reading:** under all-donor failure the final rule is a statistical tie with the frozen-threshold "
            f"peak-window rule on both measures (admissible-record share {_fmt(fr_adm)}; consequential-error rate "
            f"among decided {_fmt(fr_err)}), and it retains {_fmt(fr_adm_len)} more admissible records than the "
            f"frozen-threshold length rule at a {_fmt(fr_len)} consequential-error cost among decided cases.  Its "
            f"decided share is the highest of the three ({fe['decided_share']:.4f} vs {pe['decided_share']:.4f} and "
            f"{le['decided_share']:.4f}), so it does not win by abstaining more."
        )
    else:
        lines.append(
            "**Reading:** the final rule does NOT dominate the simple rules under all-donor failure on the "
            "decision-relevant measure; the intervals above say whether the shortfall is resolved."
        )
    if fr_use is not None and np.isfinite(fr_use.get("point", np.nan)) and fr_use["point"] > 0 and (
        fr_err is not None and fr_err.get("low", 0) > 0
    ):
        lines.append(
            "**Caveat:** the extra usable-record share is accompanied by a consequential-error rate among decided "
            "cases whose interval excludes zero, i.e. the final rule is partly buying retention with precision."
        )
    lines += [
        "",
        "## 7. What would falsify the claim that the final rule is usable on real calendars",
        "",
        "1. A cross-fitted calibrated threshold whose consequential-error rate among decided replay cases exceeds "
        f"the {RISK_CAP:.0%} calibration cap by more than the clustered interval allows under target-only failure.",
        "2. An admissible-record share under all-donor failure at or below the simple rules'.",
        "3. A donor-path error among the cases where donors are available that is no better than the labelled "
        "observed-days estimator on the same cases (then the donor reconstructor earns nothing).",
        "4. A degenerate-donor share large enough that the strict rule mostly abstains when neighbours fail.",
        "5. Cross-year gaps behaving differently from within-year gaps of the same length (the requirement that "
        "motivated the continuous-axis placement) in the direction of worse error.",
        "",
        "## 8. What this does NOT prove",
        "",
    ]
    lines += [f"- {item};" for item in fingerprint["not_proven"]]
    lines += [
        "- it does not prove that real simultaneous neighbour outages look like the imposed calendar co-failure;",
        "- it does not prove anything about operational (near-real-time) monitoring admission;",
        f"- it does not establish a universal threshold: the calibrated thresholds are fold-specific "
        f"({len(fingerprint['threshold_paths']['final_rule']['thresholds_by_network'])} values) and are not "
        "tuned on the replay.",
        "",
    ]
    if extra.get("policy_backend_consistency_ok") is False:
        lines += [
            "## Warning",
            "",
            "the policy backend cross-check failed: `attach_policy_errors` and the gathered metric/error columns "
            "disagree; treat the policy-backend columns with care.",
            "",
        ]
    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="small self-test under scratch/, no bootstrap")
    parser.add_argument("--max-networks", type=int, default=MAX_NETWORKS)
    parser.add_argument("--n-jobs", type=int, default=0)
    parser.add_argument("--skip-bootstrap", action="store_true")
    args = parser.parse_args()
    started = time.time()
    out_dir = SCRATCH / "smoke_out" if args.smoke else OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    n_jobs = args.n_jobs if args.n_jobs > 0 else min(64, max(1, os.cpu_count() or 8))
    max_networks = 2 if args.smoke else int(args.max_networks)

    print("== phase 1: network selection", flush=True)
    nets, source_map, provider_map, net_diag = select_networks(max_networks)
    print(json.dumps(net_diag, indent=2), flush=True)

    print("== phase 2: case construction", flush=True)
    real = pd.read_parquet(REAL_SY)
    split = pd.read_csv(SPLIT)
    dev = set(split.loc[split["split_role"].eq("development"), "network_id"].astype(str))
    real = real.loc[real["network_id"].astype(str).isin(dev)].copy()

    jobs = []
    for network_id in sorted(nets):
        source_root = source_map.get(network_id, "first")
        try:
            panel = load_network_panel(network_id, source_root)
        except Exception:  # noqa: BLE001
            continue
        panel_columns = set(map(str, panel.columns))
        block = real.loc[real["network_id"].astype(str).eq(network_id)]
        stations = sorted(
            set(block.loc[~block["complete"], "station_id"].astype(str))
            & set(block.loc[block["complete"], "station_id"].astype(str))
            & panel_columns
        )
        for station_id in stations[:MAX_STATIONS_PER_NETWORK]:
            station_block = block.loc[block["station_id"].astype(str).eq(station_id)]
            complete_years = sorted(station_block.loc[station_block["complete"], "year"].astype(int).tolist())
            src_years = sorted(station_block.loc[~station_block["complete"], "year"].astype(int).tolist())
            if not complete_years or not src_years:
                continue
            jobs.append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "source_root": source_root,
                    "provider": provider_map.get(network_id, "unknown"),
                    "incomplete_years": src_years,
                    "complete_years": complete_years,
                }
            )
    print(f"{len(jobs)} station jobs", flush=True)
    results = parallel_with_fallback(
        build_station_cases,
        jobs,
        (min(n_jobs, 24, len(jobs)), min(8, len(jobs)), 2, 1),
        verbose=5,
        unpack=False,
    )
    frames = [frame for frame, _ in results if len(frame)]
    diags: dict[str, int] = {}
    for _, diag in results:
        for key, value in diag.items():
            diags[key] = diags.get(key, 0) + int(value)
    if not frames:
        raise RuntimeError("no replay cases produced")
    cases = pd.concat(frames, ignore_index=True)
    cases["replay_group_id"] = (
        cases["network_id"].astype(str)
        + "|"
        + cases["station_id"].astype(str)
        + "|"
        + cases["family"].astype(str)
        + "|"
        + cases["source_incomplete_year"].astype(str)
        + "|"
        + cases["source_run_id"].astype(str)
        + "|"
        + cases["target_anchor_year"].astype(str)
        + "|"
        + cases["eval_year"].astype(str)
    )
    print(f"{len(cases)} candidate groups from {cases['network_id'].nunique()} networks", flush=True)

    print("== phase 3: assertions + policy backend", flush=True)
    assertions = assert_case_consistency(cases)
    print(json.dumps(assertions, indent=2), flush=True)
    cases, policy_consistent = attach_level_policy(cases)
    cases["abserr_observed_days"] = np.abs(
        pd.to_numeric(cases["metric_observed_days"], errors="coerce")
        - pd.to_numeric(cases["truth_hottest30"], errors="coerce")
    )

    print("== phase 4: nested cross-fitted certificate + thresholds", flush=True)
    corpus = pd.read_parquet(CORPUS)
    corpus = corpus.loc[corpus["network_id"].astype(str).isin(dev)].copy()
    corpus["network_id"] = corpus["network_id"].astype(str)
    if not set(cases["network_id"].astype(str)).issubset(set(corpus["network_id"])):
        raise RuntimeError("a replay network is absent from the labelled corpus; thresholds cannot be cross-fitted")
    replay_networks = sorted(set(cases["network_id"].astype(str)))
    external, external_meta = load_p0_02_thresholds(P0_02_THRESHOLDS, P0_02_ASSIGNMENTS)
    print(json.dumps(external_meta, indent=2), flush=True)

    print("   checking whether the p0_02 score units are reproducible here", flush=True)
    reproduction = verify_certificate_table_reproduction(
        str(CORPUS), CORPUS_KEEP_COLUMNS, P0_02_STORED_CERTIFICATES, fold=0, seed=0
    )
    print(json.dumps(reproduction, indent=2), flush=True)

    fold_jobs = [
        (network_id, str(CORPUS), CORPUS_KEEP_COLUMNS, stable_seed(network_id, "p0_03_fold", SEED))
        for network_id in replay_networks
    ]
    fold_workers = max(1, min(n_jobs, MAX_FOLD_WORKERS, len(fold_jobs)))
    print(f"fitting {len(fold_jobs)} nested folds on up to {fold_workers} workers", flush=True)
    fold_results = parallel_with_fallback(
        cross_fit_fold,
        fold_jobs,
        (fold_workers, max(1, fold_workers // 2), 2, 1),
        verbose=5,
    )
    folds: dict[str, dict] = {result["record"]["network_id"]: result for result in fold_results}

    # primary: the equivalent cross-fitted threshold, computed with the p0_02
    # pre-registered rule (retention grid + one-sided clustered 95 % bound)
    tau_clustered = pd.Series({net: float(fold["threshold"]) for net, fold in folds.items()}, dtype=float)
    tau_point = pd.Series({net: float(fold["threshold_point"]) for net, fold in folds.items()}, dtype=float)
    thresholds: dict[str, object] = {
        "final_rule": tau_clustered,
        "final_rule_point_risk": tau_point,
    }
    threshold_paths: dict[str, dict] = {
        "final_rule": {
            "path": "computed_equivalent_p0_02_rule",
            "detail": (
                "p0_02's pre-registered rule (largest calibration retention in 0.10..0.95 whose calibration "
                "false-admit rate plus a one-sided 95% network-clustered bootstrap upper bound is <= 5%) "
                "re-implemented on a per-held-out-network three-way network-disjoint split"
            ),
        },
        "final_rule_point_risk": {
            "path": "computed_point_risk_crossfit",
            "detail": "largest threshold whose calibration point false-admit rate is <= 5% (no clustered bound)",
        },
    }

    # literal transfer of the parallel workstream's numeric final thresholds:
    # kept as a labelled sensitivity because the score units are not reproducible
    # (see |reproduction| above)
    literal_available = False
    literal_meta: dict = {"available": False}
    if external is not None:
        literal, literal_meta = thresholds_from_p0_02(
            external, P0_02_SCORE_FINAL, P0_02_FOLD_SEED_PRIMARY, replay_networks, fallback=THRESHOLD_FALLBACK
        )
        literal_available = bool(literal_meta.get("available"))
        if literal_available:
            thresholds["final_rule_literal_p002_tau"] = literal
            threshold_paths["final_rule_literal_p002_tau"] = {
                "path": "literal_p0_02_tau_units_unverified",
                "detail": (
                    "p0_02 numeric thresholds for score=calibrated_bound applied to this script's bounds; the "
                    "stored certificate table is not reproducible with the current screen.py, so the units may "
                    "differ (see certificate_table_reproduction in the fingerprint)"
                ),
            }
    if "final_rule_literal_p002_tau" not in thresholds:
        thresholds["final_rule_literal_p002_tau"] = pd.Series(THRESHOLD_FALLBACK, index=replay_networks, dtype=float)

    # simple rules: consume the parallel workstream's frozen per-fold thresholds
    # (their units -- days and peak-window share -- are transferable), and also
    # report the published fixed limits as secondary rows
    simple_meta: dict[str, dict] = {}
    for key, score, fallback in (
        ("length_rule", P0_02_SCORE_LENGTH, float(LENGTH_RULE_DAYS)),
        ("peak_window_rule", P0_02_SCORE_PEAK, float(PEAK_RULE_MAX_OVERLAP)),
    ):
        if external is not None:
            series, detail = thresholds_from_p0_02(
                external, score, P0_02_FOLD_SEED_PRIMARY, replay_networks, fallback=fallback
            )
            detail["path"] = "consumed_p0_02_frozen_per_fold_threshold" if detail.get("available") else "fallback_published_limit"
            thresholds[key] = series if detail.get("available") else pd.Series(fallback, index=replay_networks, dtype=float)
            simple_meta[key] = detail
        else:
            thresholds[key] = pd.Series(fallback, index=replay_networks, dtype=float)
            simple_meta[key] = {"path": "fallback_published_limit", "available": False}
    print(json.dumps({"literal_final_threshold": literal_meta, "simple_rules": simple_meta}, indent=2), flush=True)

    print("== phase 5: certificate application and method decisions", flush=True)
    truth_invariance = True
    if folds:
        reference = folds[sorted(folds)[0]]["model"]
        for _, sfx, _ in LEVELS:
            features = certificate_feature_frame(cases, sfx)
            try:
                truth_invariance = truth_invariance and assert_truth_invariance(reference, features)
            except Exception:  # noqa: BLE001
                truth_invariance = False
            for network_id, fold in folds.items():
                subset = cases["network_id"].astype(str).eq(network_id).to_numpy()
                if not subset.any():
                    continue
                applied = apply_certificate(fold["model"], cases.loc[subset], sfx)
                cases.loc[subset, f"certificate_choice__{sfx}"] = list(applied["choice"])
                cases.loc[subset, f"certificate_bound__{sfx}"] = applied["bound"]
                cases.loc[subset, f"certificate_raw_bound__{sfx}"] = applied["raw_bound"]
    else:
        if not FROZEN_CERT.is_file():
            raise RuntimeError("no cross-fitted folds and no frozen certificate; cannot score the final rule")
        frozen_model = joblib.load(FROZEN_CERT)
        for _, sfx, _ in LEVELS:
            applied = apply_certificate(frozen_model, cases, sfx)
            cases[f"certificate_choice__{sfx}"] = list(applied["choice"])
            cases[f"certificate_bound__{sfx}"] = applied["bound"]
            cases[f"certificate_raw_bound__{sfx}"] = applied["raw_bound"]
    for _, sfx, _ in LEVELS:
        for column in (f"certificate_choice__{sfx}", f"certificate_bound__{sfx}", f"certificate_raw_bound__{sfx}"):
            if column not in cases.columns:
                cases[column] = np.nan
        cases[f"certificate_choice__{sfx}"] = cases[f"certificate_choice__{sfx}"].astype(object)
    cases["threshold_used"] = pd.to_numeric(cases["network_id"].map(pd.Series(thresholds)), errors="coerce")

    frozen_variant = None
    if FROZEN_CERT.is_file():
        try:
            frozen_model = joblib.load(FROZEN_CERT)
            frozen_bounds, frozen_choices, frozen_thresholds = {}, {}, {}
            for _, sfx, _ in LEVELS:
                applied = apply_certificate(frozen_model, cases, sfx)
                frozen_bounds[sfx] = applied["bound"]
                frozen_choices[sfx] = applied["choice"]
            # one evaluation pass over the labelled corpus, then per-network
            # threshold selection excluding the held-out network's own rows
            corpus_scored = frozen_model.apply(corpus)
            corpus_bound = pd.to_numeric(corpus_scored["certificate_bound"], errors="coerce").to_numpy(dtype=float)
            corpus_abs = pd.to_numeric(corpus_scored["certificate_abs_error"], errors="coerce").to_numpy(dtype=float)
            corpus_network = corpus["network_id"].astype(str).to_numpy()
            for network_id in sorted(set(cases["network_id"].astype(str))):
                keep = corpus_network != network_id
                if not keep.any():
                    frozen_thresholds[network_id] = THRESHOLD_FALLBACK
                    continue
                frozen_thresholds[network_id] = float(
                    select_threshold_point(corpus_bound[keep], corpus_abs[keep])["threshold"]
                )
            frozen_variant = {"bound": frozen_bounds, "choice": frozen_choices, "thresholds": frozen_thresholds}
        except Exception as exc:  # noqa: BLE001
            print(f"frozen-certificate secondary variant unavailable: {exc}", flush=True)
            frozen_variant = None

    if frozen_variant is not None:
        thresholds["frozen_cert_rule"] = pd.Series(frozen_variant["thresholds"], dtype=float)
    cases = build_method_columns(cases, thresholds, frozen=frozen_variant)

    print("== phase 6: tables", flush=True)
    cases.to_parquet(out_dir / "replay_decisions.parquet", index=False)
    failure_mode = failure_mode_table(cases)
    failure_mode.to_csv(out_dir / "failure_mode_table.csv", index=False)
    method_error = method_error_table(cases)
    method_error.to_csv(out_dir / "cofailure_by_level.csv", index=False)
    estimator_outcomes = estimator_outcome_table(cases)
    estimator_outcomes.to_csv(out_dir / "estimator_outcomes.csv", index=False)
    donor_audit = degenerate_donor_audit(cases)
    donor_audit.to_csv(out_dir / "degenerate_donor_audit.csv", index=False)
    policy_composition_table(cases).to_csv(out_dir / "policy_composition.csv", index=False)
    threshold_rows = []
    for network_id in replay_networks:
        row = {"network_id": network_id}
        for name in ("final_rule", "final_rule_point_risk", "length_rule", "peak_window_rule",
                     "final_rule_literal_p002_tau", "frozen_cert_rule"):
            series = thresholds.get(name)
            if isinstance(series, pd.Series):
                row[f"threshold__{name}"] = float(pd.to_numeric(series.get(network_id), errors="coerce"))
        row["p0_02_fold_seed_101"] = int((external or {}).get("network_fold", {}).get(101, {}).get(network_id, -1)) if external else -1
        threshold_rows.append(row)
    pd.DataFrame(threshold_rows).to_csv(out_dir / "thresholds_by_fold.csv", index=False)
    if folds:
        pd.DataFrame([fold["record"] for fold in folds.values()]).to_csv(out_dir / "calibration_fold_detail.csv", index=False)

    print("== phase 7: network-clustered contrasts", flush=True)
    if args.skip_bootstrap:
        contrasts = pd.DataFrame(
            [
                {
                    "view": "skipped",
                    "statistic": "skipped",
                    "left": "skipped",
                    "right": "skipped",
                    "level": "skipped",
                    "sfx": "skipped",
                    "point": float("nan"),
                    "low": float("nan"),
                    "high": float("nan"),
                    "n_clusters": int(cases["network_id"].nunique()),
                    "error": "bootstrap skipped (--skip-bootstrap)",
                }
            ]
        )
    elif args.smoke:
        contrasts = run_contrasts(cases, draws_override=40, level_subset=("t0",))
    else:
        contrasts = run_contrasts(cases)
    contrasts.to_csv(out_dir / "method_contrasts.csv", index=False)

    panel_dirs = {}
    for network_id in sorted(set(cases["network_id"].astype(str))):
        root = FIRST_PANELS if source_map.get(network_id, "first") == "first" else SECOND_PANELS
        path = root / str(network_id) / "daily_wide_temperature.csv"
        if path.is_file():
            panel_dirs[str(path.relative_to(ROOT))] = sha256_file(path)
    cofail_realisation = {}
    for _, sfx, _ in LEVELS:
        hit = pd.to_numeric(cases[f"n_donors_cofailed__{sfx}"], errors="coerce")
        visible = pd.to_numeric(cases[f"n_visible_donors__{sfx}"], errors="coerce")
        cofail_realisation[level_name(sfx)] = {
            "mean_donors_cofailed": float(hit.mean()),
            "median_donors_cofailed": float(hit.median()),
            "min_donors_cofailed": int(hit.min()),
            "max_donors_cofailed": int(hit.max()),
            "mean_visible_donors": float(visible.mean()),
            "share_zero_visible_donors": float((visible <= 0).mean()),
            "share_strict_partial": (
                float(((hit > 0) & (hit < pd.to_numeric(cases["n_donors_total"], errors="coerce"))).mean())
                if sfx == "p5"
                else float("nan")
            ),
        }
    fingerprint = {
        "script": str(Path(__file__).relative_to(ROOT)),
        "script_sha256": sha256_file(Path(__file__)),
        "git_head": git_head(),
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "runtime_seconds": round(time.time() - started, 1),
        "inputs": {
            str(path.relative_to(ROOT)): sha256_file(path) for path in (REAL_SY, SPLIT, ROSTER, CORPUS) if path.is_file()
        },
        "panels": panel_dirs,
        "frozen_certificate": {
            "path": str(FROZEN_CERT.relative_to(ROOT)),
            "exists": FROZEN_CERT.is_file(),
            "used_as_secondary": frozen_variant is not None,
            "sha256": sha256_file(FROZEN_CERT) if FROZEN_CERT.is_file() else None,
        },
        "protocol": {
            "seed": SEED,
            "max_networks": max_networks,
            "cofail_levels": [{"name": n, "suffix": s, "fraction": f} for n, s, f in LEVELS],
            "max_source_years_per_station": MAX_SOURCE_YEARS_PER_STATION,
            "max_target_years_per_source": MAX_TARGET_YEARS_PER_SOURCE,
            "max_runs_per_source": MAX_RUNS_PER_SOURCE,
            "min_gap_days": MIN_GAP_DAYS,
            "max_gap_days": MAX_GAP_DAYS,
            "max_stations_per_network": MAX_STATIONS_PER_NETWORK,
            "tolerance_c": TOL,
            "risk_cap": RISK_CAP,
            "min_threshold_admits": MIN_THRESHOLD_ADMITS,
            "threshold_fallback": THRESHOLD_FALLBACK,
            "coverage": COVERAGE,
            "length_rule_days": LENGTH_RULE_DAYS,
            "length_rule_days_wide": LENGTH_RULE_DAYS_WIDE,
            "peak_rule_max_overlap": PEAK_RULE_MAX_OVERLAP,
            "boot_draws_primary": BOOT_DRAWS_PRIMARY,
            "boot_draws_secondary": BOOT_DRAWS_SECONDARY,
            "screening_features": list(SCREEN_FEATURES),
            "certificate": (
                "selection-conditional multiplicative split conformal; per held-out network the corpus networks are "
                "split three ways by network (60% heads / 20% conformal scale / 20% threshold calibration)"
            ),
            "placement_families": {
                "source_calendar_union": "all missing days of the source year mapped by (month, day)",
                "source_gap_run": "contiguous real missing runs mapped by day offset; cross-year runs evaluated in both affected calendar years",
            },
            "error_backend": "each method's own declared estimator; the simple rules share the deployed information-conditioned policy",
        },
        "threshold_paths": {
            name: {
                **detail,
                "thresholds_by_network": {
                    net: float(val) for net, val in (thresholds.get(name).items() if isinstance(thresholds.get(name), pd.Series) else [])
                },
            }
            for name, detail in threshold_paths.items()
        },
        "simple_rule_thresholds": simple_meta,
        "external_threshold_file": external_meta,
        "certificate_table_reproduction": reproduction,
        "calibration_fold_detail": [fold["record"] for fold in folds.values()],
        "truth_invariance_verified": bool(truth_invariance),
        "policy_backend_consistency_ok": bool(policy_consistent),
        "replicate_structure": {
            "n_candidate_groups": int(len(cases)),
            "n_candidate_level_rows": int(len(cases) * len(LEVELS)),
            "n_networks": int(cases["network_id"].nunique()),
            "n_stations": int(cases["station_id"].nunique()),
            "n_families": {str(k): int(v) for k, v in cases["family"].value_counts().items()},
            "n_cross_year_groups": int(cases["cross_year"].sum()),
            "n_groups_single_donor": int((pd.to_numeric(cases["n_donors_total"], errors="coerce") <= 1).sum()),
            "cofail_realisation": cofail_realisation,
            "note": (
                "one written row is one candidate group; the three co-failure levels are repeated measures "
                "stored as suffixed columns of the same row, so groups*3 is NOT the number of experiments"
            ),
        },
        "case_build_diagnostics": diags,
        "assertions": assertions,
        "reduction_statement": (
            f"at most {MAX_RUNS_PER_SOURCE} longest runs per source year per station, at most "
            f"{MAX_SOURCE_YEARS_PER_STATION} source years per station, at most {MAX_TARGET_YEARS_PER_SOURCE} target "
            f"anchor years per source year, at most {MAX_STATIONS_PER_NETWORK} stations per network; every method "
            "scores every candidate in the resulting pool (no per-method sub-sampling)"
        ),
        "not_proven": [
            "the replay transplants real incomplete-year calendars onto other years of the same station; it is not a real outage at that station",
            "the calibrated thresholds are transferred from designed-outage development cases to real calendars, and the designed corpus is what sets the 5% risk cap",
            "co-failure is imposed by masking donor columns with the target calendar, not by observing real simultaneous neighbour failures",
            "the final rule is a per-fold refit certificate (three-way network-disjoint split), not the frozen step-9 joblib object; the frozen object appears only as the secondary frozen_cert_rule row",
            "no statement about operational monitoring admission; offline archive repair only",
            "the replay networks are development networks, so this is an internal cross-fitted probe, not a sealed confirmation panel",
            "the co-failure levels are repeated measures on the same group and are never independent replicates",
        ],
    }
    (out_dir / "protocol_fingerprint.json").write_text(json.dumps(fingerprint, indent=2, default=str) + "\n")
    if not args.smoke:
        write_summary(
            out_dir,
            cases,
            method_error,
            estimator_outcomes,
            donor_audit,
            contrasts,
            fingerprint,
            {"policy_backend_consistency_ok": policy_consistent},
        )
    print(f"wrote {out_dir} ({fingerprint['runtime_seconds']} s)", flush=True)
    print(
        method_error.loc[method_error["cofail_level"].eq("all_donor_failure")][
            ["method", "n_decided", "usable_share", "consequential_error_rate_among_available", "consequential_error_rate_over_all_candidates"]
        ].to_string(index=False),
        flush=True,
    )
    print(json.dumps({"threshold_paths": {k: v["path"] for k, v in threshold_paths.items()}, "simple": {k: v.get("path") for k, v in simple_meta.items()}, "literal_available": literal_available}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

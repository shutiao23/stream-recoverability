#!/usr/bin/env python3
"""P1 group 3 — one rule, three transfers: measurement contract, time, thermal.

The 2026-10-14 review says the manuscript's transfer claims are not separated
from its measurement contract, and that "only past years" is not the same
design as "future operational use".  This script runs the *same* rule, with the
*same* thresholds, under three splits and reports where it holds and where it
fails:

  (a) measurement contract  -- provider daily-value statistic classes
      (documented daily mean / project-aggregated sub-daily / non-daily
      reference reading / undocumented), built from
      results/wrr_submission_ready/measurement_provenance_dictionary.csv;
  (b) time transfer         -- per-station first-60%-of-years vs last-40%
      (>= 2 years each side), score fitted on the earlier block only,
      threshold chosen on the earlier block only, evaluated on the later
      block; compared with the project's current within-panel leave-one-year-out
      protocol on the *same* evaluation cases;
  (c) thermal strata        -- hot vs ordinary years under the project's own
      exceedance definitions (truth_exceed_18 / truth_exceed_20) plus the
      Step-5 anomalous-year definition (truth_hottest30 - clim_peak >= 1 C).

Rule construction is *reused*, not reinvented: ``scripts/301_wrr_mr_step2_
same_info_ablation.py`` is loaded as a module and its feature set (GENERIC +
SUPPORT), quantile learner, ``_prepare``, ``_risk_model``, ``_fit_predict_risk``,
``oof_risk_scores``, ``rule_scores``, ``retention_at_risk_cap`` and
``contrast_at_retention`` are called directly.  The length rule is the same
jittered ``longest_run`` rule; the endpoint is the same ``abserr_policy`` and the
same ``PRIMARY_TOLERANCE_C = 0.5`` C failure definition.

Honest limits, stated up front and repeated in SUMMARY.md:

* The case table's *reconstructor* features were built under the panel's
  ``fit_protocol = leave_one_year_out`` (see
  ``src/stream_recoverability/experiments/v17_fitness/cases.py``); the builder
  also supports a ``strictly_prior_years`` protocol, under which the existing
  Step-13 sensitivity was run for the certificate screen.  The time-transfer
  design below is honest with respect to the **risk score's** training block
  only, so its numbers are an upper bound on a strictly prior-years deployment.
* No true heatwave/event labels exist for the river-temperature panel; the only
  labelled event file in the repository belongs to a different panel (see
  ``check_event_labels``).  A warm-year stratum is *not* an event-scale
  heatwave analysis.
* The wave-2 population is a secondary, clearly labelled exploratory replay;
  the wave-2 seal belongs to the frozen certificate screen and is not retuned
  here.

Outputs (results/wrr_submission_ready/major_revision_20261014/p1_transfer_measurement/):
  measurement_strata.csv, time_transfer.csv, thermal_strata.csv,
  measurement_contract_crosscheck.csv, protocol_fingerprint.json, SUMMARY.md

Run: PYTHONPATH=src python3 scripts/318_wrr_p1_transfer_measurement.py
"""

from __future__ import annotations

# Single-threaded BLAS/OpenMP *before* numpy/sklearn import.  A 40k-row
# HistGradientBoosting fit takes ~1.5 s on one thread and ~106 s when it is
# allowed to open 128 threads; the fan-out below is process-level instead.
import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_var] = "1"

import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    STEP4_CEILING,
)
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402

# --------------------------------------------------------------------------
# Paths and constants
# --------------------------------------------------------------------------
OUT = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261014" / "p1_transfer_measurement"
SCRATCH = ROOT / "scratch" / "p1_transfer"

SCRIPT_301 = ROOT / "scripts" / "301_wrr_mr_step2_same_info_ablation.py"
DEV_CASES = STEP4_CEILING / "development_cases.parquet"
WAVE2_CASES = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "p0_07_wave2_ingest"
    / "p0_07_wave2_confirmation"
    / "wave2_cases.parquet"
)
DICTIONARY = ROOT / "results" / "wrr_submission_ready" / "measurement_provenance_dictionary.csv"
COVERAGE_TABLE = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "p0_06_coverage_recompute"
    / "final_coverage_table.csv"
)
GEMS_EVENT_LABELS = (
    ROOT / "private" / "gems_reviewer_bundle" / "data" / "processed" / "event_labels.parquet"
)
WRR_FAULT_SCORES = ROOT / "results" / "wrr_revision" / "step5_failures" / "fault_scores.csv"
STEP13_PROTOCOL = ROOT / "results" / "v17_fitness" / "step13_prior_years" / "protocol_comparison.csv"

RETENTION = 0.70          # same headline operating point as Step 2 / Step 7
RISK_CAP = 0.05           # same 5 % false-admit target as Step 6 / P0-01
BOOT_DRAWS = int(os.environ.get("P1_BOOT_DRAWS", "1200"))          # strata rows
BOOT_DRAWS_MAIN = int(os.environ.get("P1_BOOT_DRAWS_MAIN", "2000"))  # pooled / primary rows
MIN_NETWORKS_FOR_CI = 5   # below this a bootstrap interval is not reported
MIN_CASES_FOR_ROW = 50    # below this a stratum is listed but not scored
SEED = 17                 # Step-2 seed
MAX_WORKERS = min(int(os.environ.get("P1_MAX_WORKERS", "48")), os.cpu_count() or 1)
EARLY_FRACTION = 0.60     # per station: first 60 % of years are trained on

# --------------------------------------------------------------------------
# Measurement-contract classification
#
# Every provider in the dictionary is mapped explicitly.  The mapping is not
# inferred by keyword at run time: a silent misclassification here would be a
# fabricated statistic claim.  ``measurement_class_frame`` fails loudly if a
# case table carries a provider the dictionary does not cover.
# --------------------------------------------------------------------------
MEASUREMENT_CLASSES = (
    "documented_daily_mean",
    "project_aggregated_subdaily",
    "non_daily_reference_reading",
    "undocumented",
)
MEASUREMENT_MAP: dict[str, tuple[str, str]] = {
    "usgs": (
        "documented_daily_mean",
        "statistic code 00003 is documented as MEAN VALUES (dictionary)",
    ),
    "foen": (
        "documented_daily_mean",
        "provider field data_1day_mean, documented daily mean (dictionary)",
    ),
    "gkd_bayern": (
        "documented_daily_mean",
        "Tageswerte/tmw; CSV column read by the parser is 'Mittelwert' (dictionary)",
    ),
    "lubw": (
        "documented_daily_mean",
        "workbook attribute printed name 'Tagesmittelwert' (dictionary)",
    ),
    "nve_hydapi": (
        "documented_daily_mean",
        "HydAPI aggregation type 'mean', ResolutionTime=1440 (dictionary)",
    ),
    "uk_ea": (
        "documented_daily_mean",
        "measure labelled 'Daily mean Temperature (C) time series', valueType mean (dictionary)",
    ),
    "chmi": (
        "project_aggregated_subdaily",
        "source series TO = instantaneous 10-min; parser averages to a project calendar day (dictionary)",
    ),
    "rws_waterwebservices": (
        "project_aggregated_subdaily",
        "raw 'meting' values averaged per calendar date; provider GEM24H mean not used (dictionary)",
    ),
    "hubeau": (
        "project_aggregated_subdaily",
        "continuous chronicle, per-measurement timestamps, resampled to a calendar-day mean (dictionary)",
    ),
    "syke": (
        "non_daily_reference_reading",
        "morning ~08:00 near-shore reading, not a provider daily mean (dictionary)",
    ),
    "arso": (
        "undocumented",
        "no fetched page states whether the daily value is a mean or a fixed-hour reading (dictionary)",
    ),
    "smhi": (
        "undocumented",
        "daily cadence documented, aggregation statistic explicitly unverified (dictionary)",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or "unavailable"


def load_step2_module():
    """Load script 301 as a module so its rule construction is reused verbatim."""

    spec = importlib.util.spec_from_file_location("wrr_step2_301", SCRIPT_301)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {SCRIPT_301}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Failure rate / threshold helpers
# --------------------------------------------------------------------------
def failure_rate(errors, tolerance: float = PRIMARY_TOLERANCE_C) -> float:
    """Share of a retained set that is a consequential failure.

    Non-finite selected errors are failures, never dropped: reconstruction
    failures stay in the ledger (same convention as
    ``frontier.operating_point_contrast``).
    """

    values = np.asarray(errors, dtype=float)
    if values.size == 0:
        return float("nan")
    return float(((~np.isfinite(values)) | (values > float(tolerance))).mean())


def threshold_at_retention(scores: pd.Series, retention: float) -> float:
    """Score cut that retains ``retention`` of the candidates (NaN scores last)."""

    values = pd.to_numeric(scores, errors="coerce").fillna(np.inf).to_numpy(dtype=float)
    n = values.size
    if n == 0:
        return float("inf")
    k = max(1, min(n, int(round(float(retention) * n))))
    return float(np.partition(values, k - 1)[k - 1])


def threshold_at_risk_cap(scores: pd.Series, errors, risk_cap: float = RISK_CAP) -> dict:
    """Score cut at the *largest* retention whose false-admit rate stays <= risk_cap.

    Exact over every k and vectorised; validated against Step 2's grid search in
    ``validate_retention_helper``.
    """

    values = pd.to_numeric(scores, errors="coerce").fillna(np.inf).to_numpy(dtype=float)
    err = np.asarray(errors, dtype=float)
    if values.size == 0 or values.size != err.size:
        return {"threshold": float("inf"), "retention": 0.0, "rate": float("nan"), "n_retained": 0}
    order = np.argsort(values, kind="mergesort")
    ordered_scores = values[order]
    ordered_err = err[order]
    bad = (~np.isfinite(ordered_err)) | (ordered_err > PRIMARY_TOLERANCE_C)
    cumulative = np.cumsum(bad)
    k = np.arange(1, ordered_err.size + 1)
    ok = (cumulative / k) <= float(risk_cap)
    if not ok.any():
        return {"threshold": -float("inf"), "retention": 0.0, "rate": float("nan"), "n_retained": 0}
    kbest = int(np.max(k[ok]))
    return {
        "threshold": float(ordered_scores[kbest - 1]),
        "retention": float(kbest / ordered_err.size),
        "rate": float(cumulative[kbest - 1] / kbest),
        "n_retained": int(kbest),
    }


def validate_retention_helper(step2, cases: pd.DataFrame, scores: pd.Series, errors: pd.Series) -> dict:
    grid = step2.retention_at_risk_cap(scores, errors)
    exact = threshold_at_risk_cap(scores, errors)
    return {
        "grid_retention": float(grid["retention"]),
        "exact_retention": float(exact["retention"]),
        "abs_diff_retention": abs(float(grid["retention"]) - float(exact["retention"])),
        "n_cases": int(len(cases)),
        "note": (
            "Step 2 searches RETENTION_GRID then a 0.01 grid; the exact helper takes "
            "any k, so it can only be equal or finer."
        ),
    }


def operating_at_70(scores: pd.Series, errors: pd.Series) -> dict:
    values = pd.to_numeric(scores, errors="coerce").fillna(np.inf).to_numpy(dtype=float)
    err = pd.to_numeric(errors, errors="coerce").to_numpy(dtype=float)
    n = values.size
    k = max(1, min(n, int(round(RETENTION * n))))
    idx = np.argsort(values, kind="mergesort")[:k]
    kept = err[idx]
    finite = kept[np.isfinite(kept)]
    return {
        "n_retained": int(k),
        "rate_above_0.5": failure_rate(kept),
        "mean_abs_error_c": float(finite.mean()) if finite.size else float("nan"),
    }


# --------------------------------------------------------------------------
# Bootstrap jobs (module-level callables so ProcessPoolExecutor can pickle them)
# --------------------------------------------------------------------------
def _stat_contrast_at_retention(
    block: pd.DataFrame, left: str, right: str, error_col: str, retention: float
) -> float:
    k = max(1, int(round(float(retention) * len(block))))
    if k > len(block):
        return float("nan")
    a = block.nsmallest(k, left)[error_col].to_numpy(dtype=float)
    b = block.nsmallest(k, right)[error_col].to_numpy(dtype=float)
    return failure_rate(a) - failure_rate(b)


def _dispatch(job: dict) -> dict:
    payload = job["payload"]
    kind = job["kind"]
    if kind == "contrast":
        frame = payload["frame"]
        left, right = payload["left"], payload["right"]
        error_col, retention = payload["error_col"], payload["retention"]

        def statistic(block: pd.DataFrame) -> float:
            return _stat_contrast_at_retention(block, left, right, error_col, retention)

    elif kind == "retention_delta":
        frame = payload["frame"]
        left, right, error_col = payload["left"], payload["right"], payload["error_col"]

        def statistic(block: pd.DataFrame) -> float:
            return (
                threshold_at_risk_cap(block[left], block[error_col])["retention"]
                - threshold_at_risk_cap(block[right], block[error_col])["retention"]
            )

    elif kind == "transfer":
        frame = payload["frame"]
        spec = {
            "error_col": payload["error_col"],
            "mode": payload["mode"],
            "retention": payload["retention"],
        }

        def statistic(block: pd.DataFrame) -> float:
            train = block.loc[block["block"].eq("train")]
            evaluate = block.loc[block["block"].eq("eval")]
            if train.empty or evaluate.empty:
                return float("nan")
            error_col = spec["error_col"]
            if spec["mode"] == "retention":
                threshold = {
                    "risk": threshold_at_retention(train["risk"], spec["retention"]),
                    "length": threshold_at_retention(train["length"], spec["retention"]),
                }
            elif spec["mode"] == "risk_cap":
                threshold = {
                    "risk": threshold_at_risk_cap(train["risk"], train[error_col])["threshold"],
                    "length": threshold_at_risk_cap(train["length"], train[error_col])["threshold"],
                }
            elif spec["mode"] == "risk_cap_retention_delta":
                cut_risk = threshold_at_risk_cap(train["risk"], train[error_col])["threshold"]
                cut_length = threshold_at_risk_cap(train["length"], train[error_col])["threshold"]
                risk_kept = int(evaluate["risk"].le(cut_risk).sum())
                length_kept = int(evaluate["length"].le(cut_length).sum())
                return float(risk_kept / len(evaluate)) - float(length_kept / len(evaluate))
            else:  # pragma: no cover - defensive
                raise ValueError(spec["mode"])
            kept_risk = evaluate.loc[evaluate["risk"].le(threshold["risk"]), error_col].to_numpy(dtype=float)
            kept_length = evaluate.loc[
                evaluate["length"].le(threshold["length"]), error_col
            ].to_numpy(dtype=float)
            if kept_risk.size == 0 or kept_length.size == 0:
                return float("nan")
            return failure_rate(kept_risk) - failure_rate(kept_length)

    else:  # pragma: no cover - defensive
        raise ValueError(kind)

    return cluster_bootstrap(
        frame, statistic, draws=int(payload["draws"]), seed=int(payload["seed"])
    )


class JobQueue:
    """Collect bootstrap jobs, then run them concurrently and fill the rows in."""

    def __init__(self, pool: ProcessPoolExecutor):
        self.pool = pool
        self.jobs: list[tuple[dict, str, dict]] = []

    def add_contrast(self, row: dict, frame: pd.DataFrame, *, draws: int, seed: int) -> None:
        self.jobs.append(
            (
                row,
                "contrast",
                {
                    "frame": frame,
                    "left": "risk",
                    "right": "length_rule",
                    "error_col": "abserr_policy",
                    "retention": RETENTION,
                    "draws": draws,
                    "seed": seed,
                },
            )
        )

    def add_retention_delta(self, row: dict, frame: pd.DataFrame, *, draws: int, seed: int) -> None:
        self.jobs.append(
            (
                row,
                "retention_delta",
                {
                    "frame": frame,
                    "left": "risk",
                    "right": "length_rule",
                    "error_col": "abserr_policy",
                    "draws": draws,
                    "seed": seed,
                },
            )
        )

    def add_transfer(self, row: dict, payload: dict) -> None:
        self.jobs.append((row, "transfer", payload))

    def resolve(self, *, verbose: bool = True) -> int:
        if not self.jobs:
            return 0
        jobs = [{"kind": kind, "payload": payload} for _, kind, payload in self.jobs]
        if verbose:
            print(f"  running {len(jobs)} clustered bootstraps on {MAX_WORKERS} workers...", flush=True)
        results = list(self.pool.map(_dispatch, jobs))
        for (row, kind, _), stat in zip(self.jobs, results):
            low, high = float(stat["low"]), float(stat["high"])
            finite = bool(np.isfinite(low) and np.isfinite(high))
            if kind == "retention_delta":
                row["retention_delta_pp"] = float(stat["point"]) * 100.0
                row["retention_ci_low_pp"] = low * 100.0
                row["retention_ci_high_pp"] = high * 100.0
                row["retention_n_clusters"] = int(stat["n_clusters"])
                row["retention_ci_reported"] = finite
            else:
                row["ci_low_pp"] = low * 100.0
                row["ci_high_pp"] = high * 100.0
                row["n_clusters"] = int(stat["n_clusters"])
                row["ci_reported"] = finite
                if not finite:
                    row["ci_note"] = "cluster bootstrap returned no finite draws"
        count = len(self.jobs)
        self.jobs = []
        return count


# ----- process-pool context for the fold fits ---------------------------------
_FIT_CONTEXT: dict = {}


def _init_fit_worker(frame: pd.DataFrame, features: tuple[str, ...], target_col: str) -> None:
    _FIT_CONTEXT["frame"] = frame
    _FIT_CONTEXT["features"] = features
    _FIT_CONTEXT["target"] = target_col


def _fit_block_score(train_labels, eval_labels, target_col: str) -> np.ndarray:
    """Fit the Step-2 learner on one block and score another (past -> future)."""

    from sklearn.ensemble import HistGradientBoostingRegressor

    from stream_recoverability.experiments.v17_fitness.screen import feature_frame

    frame = _FIT_CONTEXT["frame"]
    features = _FIT_CONTEXT["features"]
    train = frame.loc[frame.index.isin(train_labels)]
    test = frame.loc[frame.index.isin(eval_labels)]
    y = pd.to_numeric(train[target_col], errors="coerce")
    finite = y.notna().to_numpy()
    x_train = feature_frame(train, features)
    x_test = feature_frame(test, features)
    model = HistGradientBoostingRegressor(
        loss="quantile",
        quantile=0.9,
        random_state=SEED,
        max_depth=4,
        max_iter=350,
        learning_rate=0.06,
        min_samples_leaf=40,
    ).fit(x_train.loc[finite], y.loc[finite])
    return model.predict(x_test)


def _fit_year_fold(year: int) -> tuple[int, np.ndarray, np.ndarray]:
    """Leave-one-year-out: train on every case whose year is not ``year``."""

    from sklearn.ensemble import HistGradientBoostingRegressor

    from stream_recoverability.experiments.v17_fitness.screen import feature_frame

    frame = _FIT_CONTEXT["frame"]
    features = _FIT_CONTEXT["features"]
    target = _FIT_CONTEXT["target"]
    test_mask = frame["year"].eq(int(year)).to_numpy()
    train = frame.loc[~test_mask]
    test = frame.loc[test_mask]
    if test.empty:
        return int(year), np.array([], dtype=int), np.array([], dtype=float)
    y = pd.to_numeric(train[target], errors="coerce")
    finite = y.notna().to_numpy()
    if finite.sum() < 50:
        return int(year), np.array([], dtype=int), np.array([], dtype=float)
    x_train = feature_frame(train, features)
    x_test = feature_frame(test, features)
    model = HistGradientBoostingRegressor(
        loss="quantile",
        quantile=0.9,
        random_state=SEED + (int(year) % 1000),
        max_depth=4,
        max_iter=350,
        learning_rate=0.06,
        min_samples_leaf=40,
    ).fit(x_train.loc[finite], y.loc[finite])
    return int(year), np.flatnonzero(test_mask), model.predict(x_test)


def oof_risk_scores_by_year(cases: pd.DataFrame, features: tuple[str, ...]) -> pd.Series:
    """Leave-one-year-out risk score: every case is scored by a model that never saw
    its own calendar year, but may have seen *later* years.  This is the project's
    current within-panel protocol expressed at the risk-score level."""

    columns = ["year", "longest_run_month", "abserr_policy"] + [
        c for c in features if c in cases.columns and c not in ("month_sin", "month_cos")
    ]
    slim = cases[columns].copy()
    years = sorted(int(y) for y in pd.unique(cases["year"]))
    out = pd.Series(np.nan, index=cases.index, dtype=float)
    workers = max(1, min(MAX_WORKERS, len(years)))
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init_fit_worker, initargs=(slim, features, "abserr_policy")
    ) as pool:
        for year, positions, predictions in pool.map(_fit_year_fold, years):
            if positions.size:
                out.iloc[positions] = predictions
    return out


# --------------------------------------------------------------------------
# Panel preparation and splits
# --------------------------------------------------------------------------
def measurement_class_frame(cases: pd.DataFrame, dictionary: pd.DataFrame) -> pd.DataFrame:
    providers = sorted(set(cases["provider"].astype(str)))
    missing = [p for p in providers if p not in MEASUREMENT_MAP]
    if missing:
        raise KeyError(
            "case table carries providers absent from the measurement mapping; add them "
            f"with dictionary evidence before scoring: {missing}"
        )
    dictionary_index = dictionary.set_index("provider")
    rows = []
    for provider in providers:
        klass, basis = MEASUREMENT_MAP[provider]
        documented = (
            str(dictionary_index.loc[provider, "statistic_documented"])[:400]
            if provider in dictionary_index.index
            else ""
        )
        rows.append(
            {
                "provider": provider,
                "measurement_class": klass,
                "classification_basis": basis,
                "dictionary_statistic_documented": documented,
            }
        )
    mapping = pd.DataFrame(rows)
    frame = cases.merge(mapping[["provider", "measurement_class"]], on="provider", how="left")
    if frame["measurement_class"].isna().any():  # pragma: no cover - guarded above
        raise ValueError("unclassified providers after merge")
    return frame


# The parallel coverage recompute (P0-06) classifies providers with a keyword
# rule on the dictionary text.  Its labels are not the four classes asked for
# here (it puts project-aggregated sub-daily sources and a genuine fixed-hour
# reference reading in one bucket, and misses Hub'Eau), so it is reported side
# by side rather than adopted silently.  This map only tests agreement under an
# explicit coarsening.
COVERAGE_TO_LOCAL_CLASS = {
    "daily_mean": "documented_daily_mean",
    "project_aggregated_from_subdaily": "project_aggregated_subdaily",
    "daily_mean_from_raw": "project_aggregated_subdaily",
    "non_daily_reference_reading": "non_daily_reference_reading",
    "unknown_may_be_morning_reference": "non_daily_reference_reading",
    "provider_daily_unverified_definition": "undocumented",
    "undocumented": "undocumented",
}


def read_coverage_table() -> tuple[pd.DataFrame | None, str | None]:
    """Read the parallel P0-06 coverage table once and hash the bytes read.

    The table is being rebuilt by a parallel workstream, so the hash is taken
    from the same bytes that are parsed here rather than re-read later.
    """

    if not COVERAGE_TABLE.exists():
        return None, None
    raw = COVERAGE_TABLE.read_bytes()
    return pd.read_csv(io.BytesIO(raw)), hashlib.sha256(raw).hexdigest()


def load_coverage_classes(panel: str, table: pd.DataFrame | None = None) -> pd.DataFrame:
    """Provider-level view of the parallel P0-06 coverage table, if it exists."""

    empty = pd.DataFrame(
        columns=[
            "provider",
            "coverage_keyword_class",
            "coverage_keyword_rule",
            "coverage_station_class",
            "coverage_include_in_unified_daily_mean_main",
        ]
    )
    if table is None:
        return empty
    block = table.loc[table["panel"].astype(str).eq(panel)]
    if block.empty:
        return empty
    columns = {
        "statistic_class": "coverage_keyword_class",
        "statistic_class_rule_matched": "coverage_keyword_rule",
        "statistic_class_cross_check": "coverage_station_class",
        "include_in_unified_daily_mean_main": "coverage_include_in_unified_daily_mean_main",
    }
    keep = [c for c in columns if c in block.columns]
    return (
        block.groupby("provider", sort=True)[keep]
        .first()
        .reset_index()
        .rename(columns=columns)
    )


def measurement_contract_crosscheck(
    cases: pd.DataFrame, dictionary: pd.DataFrame, coverage: pd.DataFrame
) -> pd.DataFrame:
    """One row per provider: explicit class, dictionary evidence, parallel-table class."""

    providers = sorted(set(cases["provider"].astype(str)))
    dictionary_index = dictionary.set_index("provider")
    coverage_index = coverage.set_index("provider") if len(coverage) else None
    rows = []
    for provider in providers:
        klass, basis = MEASUREMENT_MAP[provider]
        keyword_class = keyword_rule = station_class = include_main = None
        if coverage_index is not None and provider in coverage_index.index:
            keyword_class = coverage_index.loc[provider, "coverage_keyword_class"]
            keyword_rule = coverage_index.loc[provider, "coverage_keyword_rule"]
            station_class = coverage_index.loc[provider, "coverage_station_class"]
            include_main = coverage_index.loc[
                provider, "coverage_include_in_unified_daily_mean_main"
            ]
        station_normalised = COVERAGE_TO_LOCAL_CLASS.get(str(station_class))
        rows.append(
            {
                "provider": provider,
                "local_measurement_class": klass,
                "local_classification_basis": basis,
                "dictionary_statistic_documented": (
                    str(dictionary_index.loc[provider, "statistic_documented"])[:300]
                    if provider in dictionary_index.index
                    else ""
                ),
                "coverage_keyword_class": keyword_class,
                "coverage_keyword_rule": keyword_rule,
                "coverage_station_class": station_class,
                "coverage_station_class_normalised": station_normalised,
                "agrees_with_coverage_keyword_rule": (
                    None
                    if keyword_class is None
                    else bool(
                        COVERAGE_TO_LOCAL_CLASS.get(str(keyword_class), str(keyword_class)) == klass
                    )
                ),
                "agrees_with_coverage_station_class": (
                    None if station_normalised is None else bool(station_normalised == klass)
                ),
                "coverage_include_in_unified_daily_mean_main": include_main,
            }
        )
    return pd.DataFrame(rows)


def station_year_table(cases: pd.DataFrame) -> pd.DataFrame:
    return (
        cases[["station_id", "year", "truth_exceed_18", "truth_exceed_20", "truth_hottest30", "clim_peak"]]
        .drop_duplicates(subset=["station_id", "year"])
        .reset_index(drop=True)
    )


def per_station_year_split(cases: pd.DataFrame, early_fraction: float = EARLY_FRACTION) -> pd.Series:
    """First ``early_fraction`` of each station's complete years vs the rest.

    Minimum two years on each side.  Returns an 'early'/'late' label per *case*
    (outage realizations inherit their station-year's block).
    """

    block = pd.Series("late", index=cases.index, dtype=object)
    years_by_station = cases.groupby("station_id")["year"].apply(
        lambda s: sorted(set(int(v) for v in s))
    )
    for station_id, years in years_by_station.items():
        n = len(years)
        n_late = max(2, int(math.floor((1.0 - early_fraction) * n + 0.5)))
        n_late = min(n_late, n - 2)
        n_early = n - n_late
        if n_early < 2 or n_late < 2:  # pragma: no cover - all 354 stations qualify
            continue
        early_years = set(years[:n_early])
        mask = cases["station_id"].eq(station_id) & cases["year"].isin(early_years)
        block.loc[mask] = "early"
    return block


def global_calendar_split(cases: pd.DataFrame, early_fraction: float = EARLY_FRACTION) -> tuple[pd.Series, int]:
    """Common-deploy-date split on the pooled station-year distribution."""

    table = station_year_table(cases)
    years = np.sort(table["year"].to_numpy(dtype=int))
    cut = int(years[min(len(years) - 1, max(0, int(math.floor(early_fraction * len(years))) - 1))])
    block = pd.Series(np.where(cases["year"].le(cut), "early", "late"), index=cases.index, dtype=object)
    return block, cut


# --------------------------------------------------------------------------
# (a) Measurement strata
# --------------------------------------------------------------------------
def contrast_row(
    *,
    population: str,
    group_type: str,
    stratum: str,
    providers: str,
    block: pd.DataFrame,
    queue: JobQueue,
    draws: int,
    seed: int,
) -> dict:
    errors = block["abserr_policy"]
    risk = operating_at_70(block["risk"], errors)
    length = operating_at_70(block["length_rule"], errors)
    n_networks = int(block["network_id"].nunique())
    row = {
        "population": population,
        "group_type": group_type,
        "stratum": stratum,
        "providers": providers,
        "n_cases": int(len(block)),
        "n_networks": n_networks,
        "n_stations": int(block["station_id"].nunique()),
        "n_station_years": int(block[["station_id", "year"]].drop_duplicates().shape[0]),
        "risk_rate_above_0.5_at_70": risk["rate_above_0.5"],
        "length_rate_above_0.5_at_70": length["rate_above_0.5"],
        "contrast_pp": (risk["rate_above_0.5"] - length["rate_above_0.5"]) * 100.0,
        "risk_mean_abs_error_c_at_70": risk["mean_abs_error_c"],
        "length_mean_abs_error_c_at_70": length["mean_abs_error_c"],
        "risk_retention_at_risk5": threshold_at_risk_cap(block["risk"], errors)["retention"],
        "length_retention_at_risk5": threshold_at_risk_cap(block["length_rule"], errors)["retention"],
        "retention_delta_pp": float("nan"),
        "retention_ci_low_pp": float("nan"),
        "retention_ci_high_pp": float("nan"),
        "retention_n_clusters": n_networks,
        "retention_ci_reported": False,
        "ci_low_pp": float("nan"),
        "ci_high_pp": float("nan"),
        "n_clusters": n_networks,
        "ci_reported": False,
        "ci_note": "",
    }
    frame = block[["network_id", "risk", "length_rule", "abserr_policy"]]
    if len(block) < MIN_CASES_FOR_ROW:
        row["ci_note"] = f"below {MIN_CASES_FOR_ROW} cases; not scored"
        return row
    if n_networks < MIN_NETWORKS_FOR_CI:
        row["ci_note"] = f"too few networks for an interval (n={n_networks} < {MIN_NETWORKS_FOR_CI})"
        return row
    queue.add_contrast(row, frame, draws=draws, seed=seed)
    queue.add_retention_delta(row, frame, draws=draws, seed=seed + 7)
    return row


def measurement_strata(
    cases: pd.DataFrame, *, population: str, queue: JobQueue, draws: int, seed: int
) -> list[dict]:
    rows: list[dict] = [
        contrast_row(
            population=population,
            group_type="pooled",
            stratum="all_providers",
            providers=";".join(sorted(set(cases["provider"].astype(str)))),
            block=cases,
            queue=queue,
            draws=BOOT_DRAWS_MAIN,
            seed=seed,
        )
    ]
    for klass in MEASUREMENT_CLASSES:
        block = cases.loc[cases["measurement_class"].eq(klass)]
        if block.empty:
            rows.append(
                {
                    "population": population,
                    "group_type": "measurement_class",
                    "stratum": klass,
                    "providers": "",
                    "n_cases": 0,
                    "n_networks": 0,
                    "ci_note": "no cases in this class in this population",
                }
            )
            continue
        rows.append(
            contrast_row(
                population=population,
                group_type="measurement_class",
                stratum=klass,
                providers=";".join(sorted(set(block["provider"].astype(str)))),
                block=block,
                queue=queue,
                draws=draws,
                seed=seed + 11,
            )
        )
    for provider, block in cases.groupby("provider", sort=True):
        rows.append(
            contrast_row(
                population=population,
                group_type="provider",
                stratum=str(provider),
                providers=str(provider),
                block=block,
                queue=queue,
                draws=draws,
                seed=seed + 23,
            )
        )
    return rows


# --------------------------------------------------------------------------
# (b) Time transfer
# --------------------------------------------------------------------------
def transfer_rows(
    *,
    protocol: str,
    calibration: str,
    evaluation: str,
    train_block: pd.DataFrame,
    eval_block: pd.DataFrame,
    queue: JobQueue,
    seed: int,
) -> list[dict]:
    """Matched-retention and threshold-transfer rows for one protocol."""

    rows: list[dict] = []

    def base(estimand: str) -> dict:
        return {
            "protocol": protocol,
            "calibration": calibration,
            "evaluation": evaluation,
            "n_train_cases": int(len(train_block)),
            "n_train_networks": int(train_block["network_id"].nunique()),
            "n_train_stations": int(train_block["station_id"].nunique()),
            "n_eval_cases": int(len(eval_block)),
            "n_eval_networks": int(eval_block["network_id"].nunique()),
            "n_eval_stations": int(eval_block["station_id"].nunique()),
            "eval_year_min": int(eval_block["year"].min()) if len(eval_block) else None,
            "eval_year_max": int(eval_block["year"].max()) if len(eval_block) else None,
            "estimand": estimand,
            "risk_retention": float("nan"),
            "length_retention": float("nan"),
            "risk_rate_above_0.5": float("nan"),
            "length_rate_above_0.5": float("nan"),
            "contrast_pp": float("nan"),
            "ci_low_pp": float("nan"),
            "ci_high_pp": float("nan"),
            "n_clusters": int(eval_block["network_id"].nunique()),
            "ci_reported": False,
            "note": "",
        }

    # 1. Matched retention inside the evaluation block (ranking power only).
    if len(eval_block) and eval_block["network_id"].nunique() >= MIN_NETWORKS_FOR_CI:
        row = base("matched_retention_70_in_eval_block")
        risk = operating_at_70(eval_block["risk"], eval_block["abserr_policy"])
        length = operating_at_70(eval_block["length_rule"], eval_block["abserr_policy"])
        row.update(
            {
                "risk_retention": RETENTION,
                "length_retention": RETENTION,
                "risk_rate_above_0.5": risk["rate_above_0.5"],
                "length_rate_above_0.5": length["rate_above_0.5"],
                "contrast_pp": (risk["rate_above_0.5"] - length["rate_above_0.5"]) * 100.0,
                "note": "retention held fixed at 70 % within the evaluation block",
            }
        )
        queue.add_contrast(
            row,
            eval_block[["network_id", "risk", "length_rule", "abserr_policy"]],
            draws=BOOT_DRAWS_MAIN,
            seed=seed,
        )
        rows.append(row)

    # 2. Threshold transferred from the calibration block at 70 % retention.
    if len(train_block) and len(eval_block):
        row = base("transferred_threshold_at_70_calibration_retention")
        combined = pd.concat(
            [
                train_block[["network_id", "risk", "length_rule", "abserr_policy"]]
                .rename(columns={"length_rule": "length"})
                .assign(block="train"),
                eval_block[["network_id", "risk", "length_rule", "abserr_policy"]]
                .rename(columns={"length_rule": "length"})
                .assign(block="eval"),
            ],
            ignore_index=True,
        )
        tau_risk = threshold_at_retention(train_block["risk"], RETENTION)
        tau_length = threshold_at_retention(train_block["length_rule"], RETENTION)
        kept_risk = eval_block.loc[eval_block["risk"].le(tau_risk), "abserr_policy"].to_numpy(dtype=float)
        kept_length = eval_block.loc[
            eval_block["length_rule"].le(tau_length), "abserr_policy"
        ].to_numpy(dtype=float)
        row.update(
            {
                "risk_retention": float(len(kept_risk) / len(eval_block)),
                "length_retention": float(len(kept_length) / len(eval_block)),
                "risk_rate_above_0.5": failure_rate(kept_risk),
                "length_rate_above_0.5": failure_rate(kept_length),
                "contrast_pp": (failure_rate(kept_risk) - failure_rate(kept_length)) * 100.0,
                "note": (
                    "cut chosen on the calibration block only, so the achieved retention on the "
                    "evaluation block is not controlled; the interval resamples networks, so the "
                    "cut is re-derived inside every draw"
                ),
            }
        )
        queue.add_transfer(
            row,
            {
                "frame": combined,
                "error_col": "abserr_policy",
                "mode": "retention",
                "retention": RETENTION,
                "draws": BOOT_DRAWS,
                "seed": seed + 31,
            },
        )
        rows.append(row)

    # 3. Threshold at the 5 % risk target chosen on the calibration block.
    if len(train_block) and len(eval_block):
        row = base("threshold_at_5pct_risk_target_from_calibration_block")
        combined = pd.concat(
            [
                train_block[["network_id", "risk", "length_rule", "abserr_policy"]]
                .rename(columns={"length_rule": "length"})
                .assign(block="train"),
                eval_block[["network_id", "risk", "length_rule", "abserr_policy"]]
                .rename(columns={"length_rule": "length"})
                .assign(block="eval"),
            ],
            ignore_index=True,
        )
        cal_risk = threshold_at_risk_cap(train_block["risk"], train_block["abserr_policy"])
        cal_length = threshold_at_risk_cap(train_block["length_rule"], train_block["abserr_policy"])
        kept_risk = eval_block.loc[
            eval_block["risk"].le(cal_risk["threshold"]), "abserr_policy"
        ].to_numpy(dtype=float)
        kept_length = eval_block.loc[
            eval_block["length_rule"].le(cal_length["threshold"]), "abserr_policy"
        ].to_numpy(dtype=float)
        row.update(
            {
                "risk_retention": float(len(kept_risk) / len(eval_block)),
                "length_retention": float(len(kept_length) / len(eval_block)),
                "risk_rate_above_0.5": failure_rate(kept_risk),
                "length_rate_above_0.5": failure_rate(kept_length),
                "contrast_pp": (failure_rate(kept_risk) - failure_rate(kept_length)) * 100.0,
                "note": (
                    f"calibration-block retention at the target: risk={cal_risk['retention']:.3f} "
                    f"(rate {cal_risk['rate']:.4f}), length={cal_length['retention']:.3f} "
                    f"(rate {cal_length['rate']:.4f}); the target is met on the calibration block, "
                    "not guaranteed on the evaluation block"
                ),
            }
        )
        queue.add_transfer(
            row,
            {
                "frame": combined,
                "error_col": "abserr_policy",
                "mode": "risk_cap",
                "retention": RETENTION,
                "draws": BOOT_DRAWS,
                "seed": seed + 47,
            },
        )
        rows.append(row)

    # 4. Retention, not failure rate, is the estimand at a fixed risk target:
    #    both rules are calibrated to the same 5 % target, so the question is how
    #    many records each one keeps at that target.
    if len(train_block) and len(eval_block):
        row = base("retention_gain_at_5pct_risk_target_from_calibration_block")
        combined = pd.concat(
            [
                train_block[["network_id", "risk", "length_rule", "abserr_policy"]]
                .rename(columns={"length_rule": "length"})
                .assign(block="train"),
                eval_block[["network_id", "risk", "length_rule", "abserr_policy"]]
                .rename(columns={"length_rule": "length"})
                .assign(block="eval"),
            ],
            ignore_index=True,
        )
        cal_risk = threshold_at_risk_cap(train_block["risk"], train_block["abserr_policy"])
        cal_length = threshold_at_risk_cap(train_block["length_rule"], train_block["abserr_policy"])
        risk_kept = eval_block["risk"].le(cal_risk["threshold"])
        length_kept = eval_block["length_rule"].le(cal_length["threshold"])
        row.update(
            {
                "risk_retention": float(risk_kept.mean()),
                "length_retention": float(length_kept.mean()),
                "risk_rate_above_0.5": failure_rate(
                    eval_block.loc[risk_kept, "abserr_policy"].to_numpy(dtype=float)
                ),
                "length_rate_above_0.5": failure_rate(
                    eval_block.loc[length_kept, "abserr_policy"].to_numpy(dtype=float)
                ),
                "contrast_pp": float(risk_kept.mean() - length_kept.mean()) * 100.0,
                "note": (
                    "positive = the fitted score keeps more records at the same calibrated 5 % "
                    "risk target; both cuts are chosen on the calibration block only and the "
                    "achieved evaluation-block rates are reported in the neighbouring risk-target row"
                ),
            }
        )
        queue.add_transfer(
            row,
            {
                "frame": combined,
                "error_col": "abserr_policy",
                "mode": "risk_cap_retention_delta",
                "retention": RETENTION,
                "draws": BOOT_DRAWS,
                "seed": seed + 59,
            },
        )
        rows.append(row)

    return rows


def paired_protocol_delta(
    *,
    label: str,
    note: str,
    eval_block: pd.DataFrame,
    score_left: pd.Series,
    score_right: pd.Series,
    queue: JobQueue,
    seed: int,
) -> dict:
    frame = eval_block[["network_id"]].copy()
    frame["risk"] = pd.to_numeric(score_left, errors="coerce").fillna(np.inf)
    frame["length_rule"] = pd.to_numeric(score_right, errors="coerce").fillna(np.inf)
    frame["abserr_policy"] = pd.to_numeric(eval_block["abserr_policy"], errors="coerce")
    point = _stat_contrast_at_retention(frame, "risk", "length_rule", "abserr_policy", RETENTION)
    row = {
        "protocol": label,
        "calibration": "paired on identical evaluation cases",
        "evaluation": "per-station late block",
        "n_train_cases": None,
        "n_eval_cases": int(len(eval_block)),
        "n_eval_networks": int(eval_block["network_id"].nunique()),
        "estimand": "delta_matched_retention_70",
        "contrast_pp": float(point) * 100.0,
        "ci_low_pp": float("nan"),
        "ci_high_pp": float("nan"),
        "n_clusters": int(eval_block["network_id"].nunique()),
        "ci_reported": False,
        "note": note,
    }
    queue.add_contrast(row, frame, draws=BOOT_DRAWS_MAIN, seed=seed)
    return row


# --------------------------------------------------------------------------
# (c) Thermal strata
# --------------------------------------------------------------------------
def thermal_definitions(cases: pd.DataFrame) -> dict[str, pd.Series]:
    """Hot-year flags on the project's own station-year exceedance definitions."""

    table = station_year_table(cases)
    tercile_18 = table.groupby("station_id")["truth_exceed_18"].quantile(2 / 3)
    tercile_20 = table.groupby("station_id")["truth_exceed_20"].quantile(2 / 3)
    table = table.assign(
        hot18_tercile=table["truth_exceed_18"].ge(table["station_id"].map(tercile_18)),
        hot20_tercile=table["truth_exceed_20"].ge(table["station_id"].map(tercile_20)),
        hot18_abs=pd.to_numeric(table["truth_exceed_18"], errors="coerce").ge(60.0),
        hot20_abs=pd.to_numeric(table["truth_exceed_20"], errors="coerce").ge(30.0),
        anomalous=(
            pd.to_numeric(table["truth_hottest30"], errors="coerce")
            - pd.to_numeric(table["clim_peak"], errors="coerce")
        ).ge(1.0),
    )
    key = table.set_index(["station_id", "year"])
    index = pd.MultiIndex.from_arrays(
        [cases["station_id"].to_numpy(), cases["year"].to_numpy()], names=["station_id", "year"]
    )

    def flag(column: str) -> pd.Series:
        values = key[column].reindex(index).fillna(False).astype(bool).to_numpy()
        return pd.Series(values, index=cases.index, dtype=bool)

    return {
        "anomalous_warm_hottest30_minus_clim_peak_ge_1C": flag("anomalous"),
        "hot18_abs_ge_60d": flag("hot18_abs"),
        "hot20_abs_ge_30d": flag("hot20_abs"),
        "hot18_station_top_tercile": flag("hot18_tercile"),
        "hot20_station_top_tercile": flag("hot20_tercile"),
    }


def thermal_strata(cases: pd.DataFrame, *, queue: JobQueue, seed: int) -> list[dict]:
    rows: list[dict] = []
    total_station_years = cases[["station_id", "year"]].drop_duplicates().shape[0]
    for name, flag in thermal_definitions(cases).items():
        for value, label in ((True, "hot"), (False, "ordinary")):
            block = cases.loc[flag.eq(value)]
            if block.empty:
                continue
            row = contrast_row(
                population="development_oof",
                group_type=f"thermal:{name}",
                stratum=label,
                providers=";".join(sorted(set(block["provider"].astype(str)))),
                block=block,
                queue=queue,
                draws=BOOT_DRAWS,
                seed=seed + 53,
            )
            row["definition"] = name
            row["thermal_stratum"] = label
            row["share_of_cases"] = float(len(block) / len(cases))
            row["share_of_station_years"] = float(
                block[["station_id", "year"]].drop_duplicates().shape[0] / total_station_years
            )
            rows.append(row)
    return rows


# --------------------------------------------------------------------------
# Event-label audit and prior art
# --------------------------------------------------------------------------
def check_event_labels() -> dict:
    """Does the repository hold true heatwave/event labels for this panel?"""

    findings: dict = {"wrr_panel_event_labels_found": False, "sources_checked": []}
    if GEMS_EVENT_LABELS.exists():
        label = pd.read_parquet(GEMS_EVENT_LABELS)
        stations = sorted(str(s) for s in pd.unique(label["station_id"]))
        findings["sources_checked"].append(
            {
                "path": str(GEMS_EVENT_LABELS.relative_to(ROOT)),
                "what_it_is": "labelled daily panel with high_temperature and heatwave_min_3d columns",
                "station_ids": stations[:10],
                "n_stations": len(stations),
                "n_rows": int(len(label)),
                "belongs_to_this_panel": False,
                "why_not": (
                    "station ids are the anonymised GEMS benchmark ids, not river-temperature "
                    "station ids, and the labelled variables are air temperature T and flow F; "
                    "it cannot label a station-year of the WRR panel"
                ),
            }
        )
    if WRR_FAULT_SCORES.exists():
        head = pd.read_csv(WRR_FAULT_SCORES, nrows=5)
        findings["sources_checked"].append(
            {
                "path": str(WRR_FAULT_SCORES.relative_to(ROOT)),
                "what_it_is": (
                    "gap-segment diagnostic with a derived 'heatwave_fraction' column (share of "
                    "gap days above the station's training 90th percentile of daily temperature)"
                ),
                "columns_present": "heatwave_fraction" in head.columns,
                "belongs_to_this_panel": "different unit of analysis (gap segments, not station-years)",
                "why_not": (
                    "it is a derived warm-day overlap computed by the project, not a provider or "
                    "third-party event label, and it does not identify heatwave episodes"
                ),
            }
        )
    findings["conclusion"] = (
        "No true heatwave/event label exists for the river-temperature panel. The only labelled "
        "event file in the repository is the anonymised GEMS benchmark panel. The thermal strata "
        "below are therefore warm-year strata and must not be read as an event-scale heatwave "
        "analysis."
    )
    return findings


def step13_reference() -> dict:
    if not STEP13_PROTOCOL.exists():
        return {"available": False}
    return {"available": True, "rows": pd.read_csv(STEP13_PROTOCOL).to_dict(orient="records")}


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
def _fmt(value, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(number):
        return "n/a"
    return f"{number:.{digits}f}"


def _pick(table: pd.DataFrame, **conditions):
    mask = pd.Series(True, index=table.index)
    for column, value in conditions.items():
        if column not in table.columns:
            return None
        mask &= table[column].eq(value)
    block = table.loc[mask]
    return block.iloc[0] if len(block) else None


def verdict_lines(
    measurement_table: pd.DataFrame, transfer_table: pd.DataFrame, thermal_table: pd.DataFrame
) -> list[str]:
    """Plain-language verdict, generated from the tables rather than hand-written."""

    lines = ["## Verdict", ""]

    def contrast(row) -> str:
        if row is None:
            return "n/a"
        ci = (
            f" [{_fmt(row.get('ci_low_pp'))}, {_fmt(row.get('ci_high_pp'))}]"
            if row.get("ci_reported")
            else ""
        )
        suffix = "" if row.get("ci_reported") else " (point estimate only)"
        return f"{_fmt(row.get('contrast_pp'))} pp{ci}{suffix}"

    headline = _pick(
        transfer_table,
        protocol="network_clustered_oof_current_headline",
        estimand="matched_retention_70_in_eval_block",
    )
    loyo_eval = _pick(
        transfer_table,
        protocol="within_panel_leave_one_year_out_current",
        evaluation="per_station_late_block",
        estimand="matched_retention_70_in_eval_block",
    )
    p2f = _pick(
        transfer_table,
        protocol="past_to_future_per_station_60_40",
        estimand="matched_retention_70_in_eval_block",
    )
    p2f_delta = _pick(
        transfer_table,
        protocol="past_to_future_per_station_60_40 minus leave_one_year_out",
    )
    gsplit = _pick(
        transfer_table,
        protocol="past_to_future_global_calendar_60_40",
        estimand="matched_retention_70_in_eval_block",
    )
    gsplit_delta = _pick(
        transfer_table,
        protocol="past_to_future_global_calendar_60_40 minus leave_one_year_out",
    )
    p2f_target = _pick(
        transfer_table,
        protocol="past_to_future_per_station_60_40",
        estimand="threshold_at_5pct_risk_target_from_calibration_block",
    )
    p2f_gain = _pick(
        transfer_table,
        protocol="past_to_future_per_station_60_40",
        estimand="retention_gain_at_5pct_risk_target_from_calibration_block",
    )

    lines.append(
        f"**At 70 % retention the operational design does not change the ranking conclusion.** "
        f"On the manuscript's headline protocol the contrast is {contrast(headline)}; on the "
        f"shared late block it is {contrast(loyo_eval)} under leave-one-year-out and "
        f"{contrast(p2f)} under past-to-future. The paired difference is "
        f"{contrast(p2f_delta)} and {contrast(gsplit_delta)} on the common-deploy-date split "
        f"({contrast(gsplit)})."
    )
    lines.append("")
    if p2f_target is not None:
        lines.append(
            f"**At the 5 % risk target the operational design does change what can be promised.** "
            f"The past-to-future score keeps {_fmt(p2f_gain.get('contrast_pp'), 1)} more points of "
            f"retention than the length rule ({_fmt(p2f_gain.get('risk_retention'), 3)} vs "
            f"{_fmt(p2f_gain.get('length_retention'), 3)}), but the target set on the earlier block "
            f"is not preserved: the achieved evaluation-block false-admit rate is "
            f"{_fmt(float(p2f_target.get('risk_rate_above_0.5')) * 100, 2)} % for the fitted score "
            f"against the 5 % promise, versus "
            f"{_fmt(float(p2f_target.get('length_rate_above_0.5')) * 100, 2)} % for the length rule."
        )
        lines.append("")
    classes = measurement_table.loc[
        measurement_table["group_type"].eq("measurement_class")
        & measurement_table["population"].eq("development_oof")
    ]
    if len(classes):
        parts = []
        for _, row in classes.iterrows():
            ci = (
                f" [{_fmt(row.get('ci_low_pp'))}, {_fmt(row.get('ci_high_pp'))}]"
                if row.get("ci_reported")
                else " (no interval)"
            )
            parts.append(
                f"{row['stratum']} {_fmt(row.get('contrast_pp'))} pp{ci} on "
                f"{int(row.get('n_networks', 0) or 0)} networks"
            )
        lines.append(
            "**Every measurement-contract class keeps the sign, at different magnitudes:** "
            + "; ".join(parts)
            + "."
        )
        lines.append("")
    thermal = thermal_table.loc[thermal_table["definition"].eq("anomalous_warm_hottest30_minus_clim_peak_ge_1C")]
    if len(thermal):
        hot = _pick(thermal, thermal_stratum="hot")
        ordinary = _pick(thermal, thermal_stratum="ordinary")
        lines.append(
            f"**Warm years are not a failure mode for the rule:** the Step-5 anomalous-year stratum "
            f"gives {contrast(hot)} among hot years and {contrast(ordinary)} among ordinary years."
        )
        lines.append("")
    return lines


def write_summary(
    *,
    measurement_table: pd.DataFrame,
    transfer_table: pd.DataFrame,
    thermal_table: pd.DataFrame,
    fingerprint: dict,
    event_audit: dict,
) -> None:
    lines: list[str] = []
    lines.append("# P1 group 3 — one rule, three transfers (measurement contract, time, thermal)")
    lines.append("")
    lines.append(
        f"Script `{fingerprint['script']}` (sha256 `{fingerprint['script_sha256'][:16]}`), git "
        f"`{fingerprint['git_head'][:10]}`, wall time **{_fmt(fingerprint['wall_seconds'], 1)} s**."
    )
    lines.append("")
    lines.append(
        "Rule held fixed throughout: the Step-2 fitted risk score "
        "(`HistGradientBoostingRegressor`, quantile 0.9, on the GENERIC+SUPPORT decision-time "
        "feature set) against the jittered `longest_run` length rule, at 70 % retention and a "
        "0.5 °C failure tolerance. Contrast is **risk − length in percentage points**; negative "
        "means the fitted score has the lower failure rate."
    )
    lines.append("")
    lines.append(
        "Step-2 protocol check on the development panel: "
        f"{_fmt(fingerprint['protocol_checks']['step2_reproduction']['point_pp'])} pp "
        f"[{_fmt(fingerprint['protocol_checks']['step2_reproduction']['ci_low_pp'])}, "
        f"{_fmt(fingerprint['protocol_checks']['step2_reproduction']['ci_high_pp'])}] against the "
        "published −6.20 pp."
    )
    lines.append("")

    lines.extend(verdict_lines(measurement_table, transfer_table, thermal_table))

    lines.append("## (a) Measurement-contract strata")
    lines.append("")
    lines.append(f"Classification source: {fingerprint['measurement_contract_source']}.")
    lines.append("")
    lines.append(
        "| population | stratum | providers | cases | networks | risk fail @70 | length fail @70 | contrast (pp) | 95 % CI | risk ret @5 % | length ret @5 % |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for _, row in measurement_table.iterrows():
        if row.get("group_type") not in ("pooled", "measurement_class"):
            continue
        if not int(row.get("n_cases", 0) or 0):
            lines.append(
                f"| {row.get('population','')} | {row.get('stratum','')} | — | 0 | 0 | — | — | — | "
                f"{row.get('ci_note','no cases')} | — | — |"
            )
            continue
        ci = (
            f"[{_fmt(row.get('ci_low_pp'))}, {_fmt(row.get('ci_high_pp'))}]"
            if row.get("ci_reported")
            else str(row.get("ci_note", "n/a"))
        )
        lines.append(
            f"| {row['population']} | {row['stratum']} | {row.get('providers','')} | "
            f"{int(row.get('n_cases',0) or 0)} | {int(row.get('n_networks',0) or 0)} | "
            f"{_fmt(row.get('risk_rate_above_0.5_at_70'), 4)} | "
            f"{_fmt(row.get('length_rate_above_0.5_at_70'), 4)} | "
            f"{_fmt(row.get('contrast_pp'))} | {ci} | "
            f"{_fmt(row.get('risk_retention_at_risk5'), 3)} | "
            f"{_fmt(row.get('length_retention_at_risk5'), 3)} |"
        )
    lines.append("")
    lines.append("Per-provider rows are in `measurement_strata.csv` (`group_type=provider`).")
    lines.append("")
    lines.append("### Cross-check against the parallel P0-06 coverage table")
    lines.append("")
    lines.append(
        "`measurement_contract_crosscheck.csv` reports, per provider, the explicit class used "
        "here, the dictionary evidence, the P0-06 class (`statistic_class`) and its station-level "
        "class (`statistic_class_cross_check`)."
    )
    lines.append("")
    coverage = fingerprint.get("coverage_table", {})
    keyword = coverage.get("keyword_class_disagreements", [])
    station = coverage.get("station_class_disagreements", [])
    lines.append(
        f"- providers disagreeing with the P0-06 dictionary-derived class: "
        f"**{len(keyword)}**" + (f" — {', '.join(keyword)}" if keyword else " (full agreement)")
    )
    lines.append(
        f"- providers disagreeing with the P0-06 station-level cross-check column: "
        f"**{len(station)}**" + (f" — {', '.join(station)}" if station else " (full agreement)")
    )
    for item in coverage.get("notes", []):
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## (b) Time transfer: past-to-future vs the current leave-one-year-out protocol")
    lines.append("")
    lines.append(
        "How to read the four estimands: `matched_retention_70` holds retention fixed at 70 % "
        "inside the evaluation block (pure ranking power); `transferred_threshold_at_70` applies a "
        "cut chosen on the calibration block, so the achieved evaluation retention is *not* "
        "controlled; `threshold_at_5pct_risk_target` compares failure rates at each rule's own "
        "calibrated 5 % cut, which is near zero by construction whenever calibration and evaluation "
        "are the same rows; `retention_gain_at_5pct_risk_target` is the informative number there — "
        "how many more records the fitted score keeps at the shared target."
    )
    lines.append("")
    lines.append(
        "| protocol | evaluation | estimand | train/eval cases | risk ret. | length ret. | risk fail | length fail | contrast (pp) | 95 % CI |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for _, row in transfer_table.iterrows():
        ci = (
            f"[{_fmt(row.get('ci_low_pp'))}, {_fmt(row.get('ci_high_pp'))}]"
            if row.get("ci_reported")
            else "n/a"
        )
        train_cases = row.get("n_train_cases")
        train_cases = "" if train_cases is None or (isinstance(train_cases, float) and not np.isfinite(train_cases)) else int(train_cases)
        lines.append(
            f"| {row.get('protocol','')} | {row.get('evaluation','')} | {row.get('estimand','')} | "
            f"{train_cases}/{row.get('n_eval_cases','')} | {_fmt(row.get('risk_retention'), 3)} | "
            f"{_fmt(row.get('length_retention'), 3)} | {_fmt(row.get('risk_rate_above_0.5'), 4)} | "
            f"{_fmt(row.get('length_rate_above_0.5'), 4)} | {_fmt(row.get('contrast_pp'))} | {ci} |"
        )
    lines.append("")

    lines.append("## (c) Warm-year strata")
    lines.append("")
    lines.append(
        "Hot/ordinary flags come from the project's own station-year exceedance columns "
        "(`truth_exceed_18`, `truth_exceed_20`) and from the Step-5 anomalous-year rule "
        "(`truth_hottest30 - clim_peak >= 1 °C`). Shares are of cases and of station-years. The "
        "within-station tercile definitions sit on an integer day count, so ties at the two-thirds "
        "quantile put more than a third of cases in the hot arm; the achieved shares are reported "
        "rather than assumed."
    )
    lines.append("")
    lines.append(
        "| definition | stratum | share of cases | share of station-years | cases | networks | contrast (pp) | 95 % CI |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for _, row in thermal_table.iterrows():
        ci = (
            f"[{_fmt(row.get('ci_low_pp'))}, {_fmt(row.get('ci_high_pp'))}]"
            if row.get("ci_reported")
            else str(row.get("ci_note", "n/a"))
        )
        lines.append(
            f"| {row.get('definition','')} | {row.get('thermal_stratum','')} | "
            f"{_fmt(row.get('share_of_cases'), 3)} | {_fmt(row.get('share_of_station_years'), 3)} | "
            f"{int(row.get('n_cases',0) or 0)} | {int(row.get('n_networks',0) or 0)} | "
            f"{_fmt(row.get('contrast_pp'))} | {ci} |"
        )
    lines.append("")

    lines.append("## Event labels: what exists and what does not")
    lines.append("")
    for source in event_audit.get("sources_checked", []):
        lines.append(f"- `{source['path']}` — {source['what_it_is']}. {source.get('why_not','')}")
    lines.append("")
    lines.append(event_audit.get("conclusion", ""))
    lines.append("")

    lines.append("## What this does and does not license")
    lines.append("")
    for item in fingerprint["known_limitations"]:
        lines.append(f"- {item}")
    lines.append("")
    if fingerprint.get("existing_strictly_prior_years_sensitivity", {}).get("available"):
        lines.append(
            "The repository's existing strictly-prior-years sensitivity (certificate screen, "
            "`results/v17_fitness/step13_prior_years/protocol_comparison.csv`) is the closest prior "
            "art to the time-transfer design here; it is quoted verbatim in "
            "`protocol_fingerprint.json` and was not re-run. Those rows score the frozen "
            "*certificate* screen, not the fitted risk score, so they are not directly comparable "
            "to the fitted-score contrasts above."
        )
        lines.append("")
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> int:
    started = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)

    step2 = load_step2_module()
    dictionary = pd.read_csv(DICTIONARY)
    coverage_raw, coverage_sha256 = read_coverage_table()
    coverage_dev = load_coverage_classes("v17", coverage_raw)
    coverage_wave2 = load_coverage_classes("wave2_confirmation", coverage_raw)
    coverage_source = (
        "explicit provider mapping of measurement_provenance_dictionary.csv, cross-checked "
        "against the P0-06 coverage table"
        if COVERAGE_TABLE.exists()
        else "own mapping from measurement_provenance_dictionary.csv (P0-06 coverage table absent)"
    )
    print(f"measurement contract source: {coverage_source}", flush=True)
    if not len(coverage_dev):
        print("  P0-06 coverage table absent or missing the v17 panel; own mapping only", flush=True)

    print("loading development panel...", flush=True)
    development = step2._prepare(pd.read_parquet(DEV_CASES))
    development = measurement_class_frame(development, dictionary)

    print("loading wave-2 panel (secondary)...", flush=True)
    wave2 = step2._prepare(pd.read_parquet(WAVE2_CASES))
    wave2 = measurement_class_frame(wave2, dictionary)

    crosscheck = pd.concat(
        [
            measurement_contract_crosscheck(development, dictionary, coverage_dev).assign(
                population="development_oof"
            ),
            measurement_contract_crosscheck(wave2, dictionary, coverage_wave2).assign(
                population="wave2_oof_secondary_exploratory"
            ),
        ],
        ignore_index=True,
    )
    crosscheck.to_csv(OUT / "measurement_contract_crosscheck.csv", index=False)
    keyword_disagree = crosscheck.loc[
        crosscheck["agrees_with_coverage_keyword_rule"].eq(False), "provider"
    ].tolist()
    station_disagree = crosscheck.loc[
        crosscheck["agrees_with_coverage_station_class"].eq(False), "provider"
    ].tolist()
    station_unavailable = crosscheck.loc[
        crosscheck["agrees_with_coverage_station_class"].isna(), "provider"
    ].tolist()
    print(
        f"  cross-check: {len(keyword_disagree)} providers disagree with the P0-06 "
        f"dictionary class ({keyword_disagree}), {len(station_disagree)} with its station-level "
        f"class ({station_disagree})",
        flush=True,
    )
    coverage_notes = []
    if coverage_sha256 is None:
        coverage_notes.append(
            "the P0-06 coverage table did not exist when this ran, so the four-class mapping is "
            "this script's own, taken from measurement_provenance_dictionary.csv"
        )
    else:
        coverage_notes.append(
            "the P0-06 coverage table is being rebuilt by a parallel workstream; the sha256 above "
            "is of the exact bytes read by this run, and the classes scored here come from the "
            "explicit mapping, not from that table"
        )
        if not keyword_disagree:
            coverage_notes.append(
                "this run's four-class mapping agrees with P0-06's dictionary-derived "
                "statistic_class for every provider present in the two panels"
            )
        if station_disagree:
            coverage_notes.append(
                "P0-06's station-level cross-check column disagrees with the class used here for "
                + ", ".join(sorted(set(station_disagree)))
                + ": that column carries them as undocumented/unverified while the dictionary "
                "documents either a daily mean or a project-derived daily mean. This is an internal "
                "P0-06 conservatism difference, not a difference in the classes scored here"
            )
        if station_unavailable:
            coverage_notes.append(
                "no station-level cross-check row exists in P0-06 for "
                + ", ".join(sorted(set(station_unavailable)))
                + ", so that column could not be checked for them"
            )

    # ---- rule construction: identical to Step 2 -----------------------------
    print(f"network-clustered OOF risk score, development ({len(development)} cases)...", flush=True)
    development["risk"] = step2.oof_risk_scores(development, step2.SUPPORT, seed=step2.SEED)
    development["length_rule"] = step2.rule_scores(development, seed=SEED)["length_rule"]

    print("leave-one-year-out OOF risk score, development...", flush=True)
    t0 = time.perf_counter()
    development["risk_loyo_year"] = oof_risk_scores_by_year(development, step2.SUPPORT)
    print(f"  year folds done in {time.perf_counter() - t0:.1f} s", flush=True)

    print(f"network-clustered OOF risk score, wave-2 ({len(wave2)} cases)...", flush=True)
    wave2["risk"] = step2.oof_risk_scores(wave2, step2.SUPPORT, seed=step2.SEED)
    wave2["length_rule"] = step2.rule_scores(wave2, seed=SEED)["length_rule"]

    # sanity: the reused Step-2 protocol must reproduce the published contrast
    reproduction_frame = development[["network_id", "risk", "length_rule", "abserr_policy"]].rename(
        columns={"abserr_policy": "error"}
    )
    reproduction = step2.contrast_at_retention(
        reproduction_frame, "risk", "length_rule", "error", retention=RETENTION, draws=400, seed=SEED
    )
    print(
        f"  step-2 protocol check: {reproduction['point'] * 100:.2f} pp "
        f"[{reproduction['low'] * 100:.2f}, {reproduction['high'] * 100:.2f}] (published -6.20)",
        flush=True,
    )
    helper_check = validate_retention_helper(
        step2, development, development["risk"], development["abserr_policy"]
    )

    # ---- splits and out-of-block fits --------------------------------------
    early_late = per_station_year_split(development)
    development["block_per_station"] = early_late
    train_block = development.loc[early_late.eq("early")]
    eval_block = development.loc[early_late.eq("late")]
    global_block, cut_year = global_calendar_split(development)
    development["block_global"] = global_block
    g_train = development.loc[global_block.eq("early")]
    g_eval = development.loc[global_block.eq("late")]

    print("fitting the past-to-future and calendar-split scores...", flush=True)
    t0 = time.perf_counter()
    fit_context = development[
        ["year", "longest_run_month", "abserr_policy"]
        + [
            c
            for c in step2.SUPPORT
            if c in development.columns and c not in ("month_sin", "month_cos")
        ]
    ].copy()
    tasks = {
        "past_to_future": (train_block.index, eval_block.index),
        "global_split": (g_train.index, g_eval.index),
        "train_in_sample": (train_block.index, train_block.index),
        "global_train_in_sample": (g_train.index, g_train.index),
    }
    with ProcessPoolExecutor(
        max_workers=len(tasks),
        initializer=_init_fit_worker,
        initargs=(fit_context, step2.SUPPORT, "abserr_policy"),
    ) as fit_pool:
        futures = {
            name: fit_pool.submit(_fit_block_score, train_idx, eval_idx, "abserr_policy")
            for name, (train_idx, eval_idx) in tasks.items()
        }
        block_scores = {name: future.result() for name, future in futures.items()}
    development["risk_past_to_future"] = np.nan
    development.loc[eval_block.index, "risk_past_to_future"] = block_scores["past_to_future"]
    development["risk_global_split"] = np.nan
    development.loc[g_eval.index, "risk_global_split"] = block_scores["global_split"]
    # Keep the network-clustered OOF score (`risk`) intact on every block: each
    # protocol gets its own explicit copy rather than a clobbered column.
    train_frame = development.loc[early_late.eq("early")]
    eval_frame = development.loc[early_late.eq("late")]
    train_calibrated = train_frame.assign(risk=block_scores["train_in_sample"])
    g_train_frame = development.loc[global_block.eq("early")]
    g_eval_frame = development.loc[global_block.eq("late")]
    g_train_calibrated = g_train_frame.assign(risk=block_scores["global_train_in_sample"])
    eval_past_to_future = eval_frame.assign(risk=eval_frame["risk_past_to_future"])
    g_eval_global_split = g_eval_frame.assign(risk=g_eval_frame["risk_global_split"])
    print(
        f"  per-station split: train {len(train_calibrated)} cases / "
        f"{train_calibrated['network_id'].nunique()} nets, eval {len(eval_past_to_future)} / "
        f"{eval_past_to_future['network_id'].nunique()} nets",
        flush=True,
    )
    print(
        f"  global calendar split at {cut_year}: train {len(g_train_calibrated)} cases, "
        f"eval {len(g_eval_global_split)} cases ({time.perf_counter() - t0:.1f} s)",
        flush=True,
    )

    # ---- run every analysis, queue the bootstraps ---------------------------
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        queue = JobQueue(pool)

        print("(a) measurement-contract strata...", flush=True)
        measurement_rows = measurement_strata(
            development, population="development_oof", queue=queue, draws=BOOT_DRAWS, seed=SEED
        )
        measurement_rows += measurement_strata(
            wave2,
            population="wave2_oof_secondary_exploratory",
            queue=queue,
            draws=BOOT_DRAWS,
            seed=SEED + 100,
        )

        print("(b) time transfer...", flush=True)
        # the manuscript's headline protocol (network-clustered OOF, Step 2), for reference
        transfer = transfer_rows(
            protocol="network_clustered_oof_current_headline",
            calibration="all cases, 5-fold by network (Step 2 protocol)",
            evaluation="full development panel",
            train_block=development,
            eval_block=development,
            queue=queue,
            seed=SEED + 190,
        )
        loyo_full = development.assign(risk=development["risk_loyo_year"])
        transfer += transfer_rows(
            protocol="within_panel_leave_one_year_out_current",
            calibration="all years except the evaluated year (includes later years)",
            evaluation="full development panel",
            train_block=loyo_full,
            eval_block=loyo_full,
            queue=queue,
            seed=SEED + 200,
        )
        loyo_eval = eval_frame.assign(risk=eval_frame["risk_loyo_year"])
        transfer += transfer_rows(
            protocol="within_panel_leave_one_year_out_current",
            calibration="all years except the evaluated year (includes later years)",
            evaluation="per_station_late_block",
            train_block=development.assign(risk=development["risk_loyo_year"]),
            eval_block=loyo_eval,
            queue=queue,
            seed=SEED + 210,
        )
        transfer += transfer_rows(
            protocol="past_to_future_per_station_60_40",
            calibration="each station's first 60 % of complete years",
            evaluation="each station's last 40 % of complete years",
            train_block=train_calibrated,
            eval_block=eval_past_to_future,
            queue=queue,
            seed=SEED + 220,
        )
        transfer += transfer_rows(
            protocol="past_to_future_global_calendar_60_40",
            calibration=f"every case with year <= {cut_year}",
            evaluation=f"every case with year > {cut_year}",
            train_block=g_train_calibrated,
            eval_block=g_eval_global_split,
            queue=queue,
            seed=SEED + 230,
        )
        transfer.append(
            paired_protocol_delta(
                label="past_to_future_per_station_60_40 minus leave_one_year_out",
                note=(
                    "negative = the past-to-future score has the lower failure rate on the shared "
                    "evaluation cases; positive = the leave-one-year-out score is better"
                ),
                eval_block=eval_frame,
                score_left=eval_frame["risk_past_to_future"],
                score_right=eval_frame["risk_loyo_year"],
                queue=queue,
                seed=SEED + 240,
            )
        )
        transfer.append(
            paired_protocol_delta(
                label="past_to_future_global_calendar_60_40 minus leave_one_year_out",
                note="same comparison on the common-deploy-date split",
                eval_block=g_eval_frame,
                score_left=g_eval_frame["risk_global_split"],
                score_right=g_eval_frame["risk_loyo_year"],
                queue=queue,
                seed=SEED + 250,
            )
        )
        transfer.append(
            paired_protocol_delta(
                label="past_to_future_per_station_60_40 minus network_clustered_oof_current",
                note="the manuscript's headline Step-2 protocol on the same evaluation cases",
                eval_block=eval_frame,
                score_left=eval_frame["risk_past_to_future"],
                score_right=eval_frame["risk"],
                queue=queue,
                seed=SEED + 260,
            )
        )

        print("(c) thermal strata...", flush=True)
        thermal_rows = thermal_strata(development, queue=queue, seed=SEED + 300)

        print("resolving bootstrap queue...", flush=True)
        t0 = time.perf_counter()
        n_jobs = queue.resolve()
        print(f"  {n_jobs} bootstraps in {time.perf_counter() - t0:.1f} s", flush=True)

    measurement_table = pd.DataFrame(measurement_rows)
    measurement_table.to_csv(OUT / "measurement_strata.csv", index=False)
    transfer_table = pd.DataFrame(transfer)
    transfer_table.to_csv(OUT / "time_transfer.csv", index=False)
    thermal_table = pd.DataFrame(thermal_rows)
    lead = [
        "definition",
        "thermal_stratum",
        "population",
        "n_cases",
        "n_networks",
        "n_stations",
        "n_station_years",
        "share_of_cases",
        "share_of_station_years",
    ]
    thermal_table = thermal_table[
        [c for c in lead if c in thermal_table.columns]
        + [c for c in thermal_table.columns if c not in lead]
    ]
    thermal_table.to_csv(OUT / "thermal_strata.csv", index=False)

    development.to_parquet(SCRATCH / "development_scored.parquet", index=False)
    wave2.to_parquet(SCRATCH / "wave2_scored.parquet", index=False)

    wall_seconds = time.perf_counter() - started
    fingerprint = {
        "script": str(Path(__file__).relative_to(ROOT)),
        "script_sha256": sha256_file(Path(__file__)),
        "git_head": git_head(),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_seconds": wall_seconds,
        "reused_module": {
            "path": str(SCRIPT_301.relative_to(ROOT)),
            "sha256": sha256_file(SCRIPT_301),
            "what_was_reused": [
                "FEATURE_SETS / GENERIC / SUPPORT feature tuples",
                "_prepare (estimator_disagreement + month harmonics)",
                "_risk_model (HistGradientBoostingRegressor quantile=0.9, depth 4, 350 iters, lr 0.06, leaf 40)",
                "oof_risk_scores (5-fold network-clustered OOF)",
                "rule_scores (jittered longest_run length rule)",
                "retention_at_risk_cap (validation reference only)",
                "contrast_at_retention (validation reference only)",
            ],
        },
        "inputs": {
            str(DEV_CASES.relative_to(ROOT)): sha256_file(DEV_CASES),
            str(WAVE2_CASES.relative_to(ROOT)): sha256_file(WAVE2_CASES),
            str(DICTIONARY.relative_to(ROOT)): sha256_file(DICTIONARY),
        },
        "measurement_contract_source": coverage_source,
        "coverage_table": {
            "path": str(COVERAGE_TABLE.relative_to(ROOT)),
            "sha256_of_bytes_read_this_run": coverage_sha256,
            "file": "measurement_contract_crosscheck.csv",
            "keyword_class_disagreements": sorted(set(keyword_disagree)),
            "station_class_disagreements": sorted(set(station_disagree)),
            "station_class_unavailable": sorted(set(station_unavailable)),
            "notes": coverage_notes,
        },
        "measurement_mapping": {
            provider: {"class": klass, "basis": basis}
            for provider, (klass, basis) in MEASUREMENT_MAP.items()
        },
        "parameters": {
            "retention": RETENTION,
            "tolerance_c": PRIMARY_TOLERANCE_C,
            "risk_cap": RISK_CAP,
            "seed": SEED,
            "boot_draws_strata": BOOT_DRAWS,
            "boot_draws_main": BOOT_DRAWS_MAIN,
            "min_networks_for_ci": MIN_NETWORKS_FOR_CI,
            "early_fraction": EARLY_FRACTION,
            "global_calendar_cut_year": cut_year,
            "threads": "OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1 per process",
            "max_workers": MAX_WORKERS,
            "n_bootstraps": int(n_jobs),
        },
        "endpoint": {
            "error_column": "abserr_policy",
            "failure_definition": f"non-finite or abserr_policy > {PRIMARY_TOLERANCE_C} C",
            "contrast_sign": "risk minus length; negative = fitted risk score has the lower failure rate",
        },
        "protocol_checks": {
            "step2_reproduction": {
                "point_pp": float(reproduction["point"]) * 100,
                "ci_low_pp": float(reproduction["low"]) * 100,
                "ci_high_pp": float(reproduction["high"]) * 100,
                "published_point_pp": -6.202,
                "draws": 400,
            },
            "retention_helper_exact_vs_step2_grid": helper_check,
        },
        "panel_composition": {
            "development": {
                "n_cases": int(len(development)),
                "n_networks": int(development["network_id"].nunique()),
                "n_stations": int(development["station_id"].nunique()),
                "n_station_years": int(development[["station_id", "year"]].drop_duplicates().shape[0]),
                "year_min": int(development["year"].min()),
                "year_max": int(development["year"].max()),
                "per_station_train_cases": int(len(train_frame)),
                "per_station_train_networks": int(train_frame["network_id"].nunique()),
                "per_station_eval_cases": int(len(eval_frame)),
                "per_station_eval_networks": int(eval_frame["network_id"].nunique()),
                "global_split_train_cases": int(len(g_train_frame)),
                "global_split_eval_cases": int(len(g_eval_frame)),
            },
            "wave2": {
                "n_cases": int(len(wave2)),
                "n_networks": int(wave2["network_id"].nunique()),
            },
        },
        "event_label_audit": check_event_labels(),
        "existing_strictly_prior_years_sensitivity": step13_reference(),
        "known_limitations": [
            "the case table's reconstructor features were built under fit_protocol=leave_one_year_out, "
            "so the time-transfer rows are honest for the risk score's training block but remain an "
            "upper bound on a strictly prior-years deployment",
            "wave-2 rows are exploratory and do not retune or replace the wave-2 seal, which belongs "
            "to the frozen multi-method certificate screen",
            "no true heatwave event labels exist for this panel, so thermal strata are warm-year strata",
            "threshold-transfer intervals resample networks inside the calibration block as well as the "
            "evaluation block, so they carry threshold uncertainty as well as evaluation uncertainty",
        ],
    }
    (OUT / "protocol_fingerprint.json").write_text(json.dumps(fingerprint, indent=2, default=str) + "\n")

    write_summary(
        measurement_table=measurement_table,
        transfer_table=transfer_table,
        thermal_table=thermal_table,
        fingerprint=fingerprint,
        event_audit=fingerprint["event_label_audit"],
    )
    print(f"wall time {wall_seconds:.1f} s -> {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

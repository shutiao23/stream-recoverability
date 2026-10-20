#!/usr/bin/env python3
"""P0-01 (review F01/F03, 2026-10-20) — one reconstruction, one failure event, one rule.

The 2026-10-19 run declared the stored ``policy`` reconstruction as the admitted
object but built the consequential-error event from ``certificate_abs_error``.
Those are two different reconstructions of the same station-year: on the external
panel the two failure flags disagree on 898 of 13,017 cases (408 policy-only, 490
certificate-only), so a threshold calibrated on one event cannot be used to admit
the other.  This script removes the mismatch at the source.

Aligned protocol v2
-------------------
* **Object.** The admitted value is the stored ``policy`` reconstruction.  Every
  failure flag, threshold, contrast and interval in this script is computed from
  ``abserr_policy``.  The certificate bounds survive only as *scores* (a score may
  be a proxy; the evaluated event may not).
* **Event.** ``bad = abserr_policy > 0.5 C``.  A missing policy error is a failure
  (an uncertifiable record is not admissible), never a silent fallback.
* **Folds.** The five folds are the connected components of networks that share a
  station id, exactly as in the 2026-10-19 run.  Nothing here re-draws them.
* **Ties.** No jitter anywhere.  A threshold is an observed value of the raw
  score and admits every case at or below it, so a tie block is admitted whole in
  calibration, in evaluation and at deployment.  The 2026-10-19 run added
  ``longest_run + U[0,1)`` during calibration and compared raw ``longest_run``
  during replay; that is two different rules.
* **Selection.** For each outer fold the threshold is the largest candidate whose
  independence-group clustered bootstrap bound on the *policy* false-admit rate
  is at most 5%.  The bound is the percentile at ``1 - 0.05/n_candidates``, where
  ``n_candidates`` is the number of distinct snapped thresholds actually searched.
* **Baselines.** ``reconstruct_all`` (admit every usable reconstruction) is a
  first-class arm, because an agency's alternative to screening is not a weaker
  screen but no screen.

Outputs go to
``results/wrr_submission_ready/major_revision_20261020/p0_01_aligned_policy_admission/``.

Run:

    PYTHONPATH=src python3 scripts/330_wrr_aligned_policy_admission.py
"""

from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import platform  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.v17_fitness.independence import (  # noqa: E402
    eligibility_row,
    independence_table,
    overlap_pairs,
    shared_station_years_across_folds,
    shared_stations_across_folds,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    STEP4_CEILING,
    STEP6_SCREEN,
    stable_seed,
)

READY = ROOT / "results" / "wrr_submission_ready"
RUN = READY / "major_revision_20261020"
OUT = RUN / "p0_01_aligned_policy_admission"
PREV = READY / "major_revision_20261019" / "p0_02_isolated_risk_thresholds"

TOL_C = float(PRIMARY_TOLERANCE_C)
RISK_CAP = 0.05
RETENTION_GRID = tuple(round(float(x), 4) for x in np.arange(0.10, 0.9501, 0.01))
N_SPLITS = 5
N_INNER_SPLITS = 4
FOLD_SEEDS = (101, 202, 303)
FIXED_RETENTION = 0.70
SELECT_DRAWS = 1000
EVAL_DRAWS = 2000
ALPHA = 0.05

PANELS = {
    "wave2_confirmation": {
        "cases": READY / "p0_07_wave2_ingest" / "p0_07_wave2_confirmation" / "wave2_cases.parquet",
        "certificates": READY
        / "p0_07_wave2_ingest"
        / "p0_07_wave2_confirmation"
        / "wave2_certificates.parquet",
        "expected_cases": 13017,
        "expected_networks": 49,
        "expected_groups": 41,
        "role": "primary external panel (already opened; cross-fit, not a new seal)",
    },
    "development": {
        "cases": STEP4_CEILING / "development_cases.parquet",
        "certificates": STEP6_SCREEN / "development_certificates.parquet",
        "expected_cases": 40704,
        "expected_networks": 110,
        "expected_groups": 110,
        "role": "secondary sanity replication (already used for method selection)",
    },
}

#: Score name -> (raw column or construction, direction).  Every score is
#: label-free at deployment: it is built from the decision-time features and the
#: stored certificate bound, never from an evaluation label.
MODEL_FREE_SCORES = ("length_rule", "peak_overlap_rule", "uncalibrated_bound", "calibrated_bound")
FITTED_SCORES = ("fitted_risk",)
ALL_SCORES = ("fitted_risk", "peak_overlap_rule", "length_rule", "calibrated_bound", "uncalibrated_bound")
ARMS = ALL_SCORES + ("reconstruct_all",)

SCORE_NOTES = {
    "length_rule": "longest consecutive missing run (days); smaller is safer",
    "peak_overlap_rule": "share of the 30-day peak window hidden; smaller is safer",
    "fitted_risk": "quantile GBR on 22 features, target abserr_policy, nested group cross-fit",
    "uncalibrated_bound": "stored certificate raw bound (a proxy score, evaluated on policy error)",
    "calibrated_bound": "stored certificate calibrated bound (a proxy score, evaluated on policy error)",
    "reconstruct_all": "admit every candidate with a defined policy reconstruction",
}


# ---------------------------------------------------------------------------
# utilities
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - diagnostics only
        return "unknown"


def load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M301 = load_script_module("wrr301", ROOT / "scripts" / "301_wrr_mr_step2_same_info_ablation.py")
M311 = load_script_module("wrr311", ROOT / "scripts" / "311_wrr_p0_02_frozen_risk_thresholds.py")
# 311 binds its feature-builder only when it is run as __main__; importing it
# leaves M311.M301 = None.  Bind it explicitly so the imported construction is
# the one 311 actually uses, rather than a re-implementation.
M311.M301 = M301


def case_key(cases: pd.DataFrame) -> np.ndarray:
    """A stable, deployment-available key for deterministic tie-breaks.

    Row order is not a property of a case.  ``(network, station, year,
    realization)`` is, and an agency holds it before the decision is made.
    """

    columns = ["network_id", "station_id", "year", "realization_id"]
    parts = [cases[column].astype(str) for column in columns if column in cases.columns]
    text = parts[0].str.cat(parts[1:], sep="|")
    hashed = pd.util.hash_pandas_object(text, index=False).to_numpy(dtype=np.uint64)
    return hashed


# ---------------------------------------------------------------------------
# target and score construction
# ---------------------------------------------------------------------------
def policy_target(cases: pd.DataFrame, certs: pd.DataFrame) -> dict:
    """The consequential event of the *delivered* reconstruction.

    ``abserr_policy`` is checked against the stored prediction and the reference
    value before it is used, so an alignment error cannot pass silently.
    """

    policy_err = pd.to_numeric(cases["abserr_policy"], errors="coerce").to_numpy(dtype=float)
    choice = cases["policy_choice"].astype(str).to_numpy()
    pred = np.full(len(cases), np.nan)
    for name in ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge"):
        mask = choice == name
        column = f"hottest30_{name}"
        if not mask.any() or column not in cases.columns:
            continue
        pred[mask] = pd.to_numeric(cases.loc[mask, column], errors="coerce").to_numpy(dtype=float)
    truth = pd.to_numeric(cases["truth_hottest30"], errors="coerce").to_numpy(dtype=float)
    recomputed = np.abs(pred - truth)
    finite = np.isfinite(policy_err) & np.isfinite(recomputed)
    if not np.allclose(policy_err[finite], recomputed[finite], atol=1e-6, rtol=0.0):
        worst = float(np.nanmax(np.abs(policy_err[finite] - recomputed[finite])))
        raise RuntimeError(f"abserr_policy is not |hottest30_<policy_choice> - truth|: max {worst}")

    missing = ~np.isfinite(policy_err)
    bad = missing | (policy_err > TOL_C)

    cert_err = pd.to_numeric(certs["certificate_abs_error"], errors="coerce").to_numpy(dtype=float)
    cert_bad = (~np.isfinite(cert_err)) | (cert_err > TOL_C)
    return {
        "error": policy_err,
        "bad": bad.astype(bool),
        "certificate_error": cert_err,
        "certificate_bad": cert_bad.astype(bool),
        "prediction": pred,
        "truth": truth,
        "n_missing_policy_error": int(missing.sum()),
        "n_bad": int(bad.sum()),
        "bad_rate": float(bad.mean()),
        "n_certificate_bad": int(cert_bad.sum()),
        "n_disagree": int((bad != cert_bad).sum()),
        "n_policy_only": int((bad & ~cert_bad).sum()),
        "n_certificate_only": int((~bad & cert_bad).sum()),
        "alignment_proof": (
            "abserr_policy == |hottest30_<policy_choice> - truth_hottest30| for every finite row"
        ),
    }


def raw_scores(cases: pd.DataFrame, certs: pd.DataFrame) -> dict:
    """Raw, unjittered scores.  A missing bound is unsafe, not safe."""

    length = pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy(dtype=float)
    peak = pd.to_numeric(cases["peak_overlap"], errors="coerce").to_numpy(dtype=float)
    raw_bound = pd.to_numeric(certs["certificate_raw_bound"], errors="coerce").to_numpy(dtype=float)
    cal_bound = pd.to_numeric(certs["certificate_bound"], errors="coerce").to_numpy(dtype=float)
    raw_bound = np.where(np.isfinite(raw_bound), raw_bound, np.inf)
    cal_bound = np.where(np.isfinite(cal_bound), cal_bound, np.inf)
    return {
        "length_rule": length,
        "peak_overlap_rule": peak,
        "uncalibrated_bound": raw_bound,
        "calibrated_bound": cal_bound,
    }


# ---------------------------------------------------------------------------
# selection rule with whole tie blocks
# ---------------------------------------------------------------------------
def clustered_draw_counts(n_net: int, draws: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(int(seed))
    return rng.multinomial(int(n_net), np.full(int(n_net), 1.0 / int(n_net)), size=int(draws))


def candidate_thresholds(score_cal: np.ndarray) -> np.ndarray:
    """Distinct snapped thresholds for the 86-point retention grid.

    Snapping a retention grid point to the smallest observed score that reaches
    it, then de-duplicating, keeps the searched family at (at most) 86 thresholds
    while every threshold remains an observed score value.  Admission is
    ``score <= threshold``, so a tie block is never split.
    """

    score = np.asarray(score_cal, dtype=float)
    finite = np.isfinite(score)
    values = np.sort(score[finite], kind="mergesort")
    n = values.size
    if n == 0:
        raise RuntimeError("empty calibration set")
    k = np.maximum(1, np.ceil(np.asarray(RETENTION_GRID, dtype=float) * n).astype(int))
    return np.unique(values[k - 1])


def select_threshold(
    score_cal: np.ndarray,
    bad_cal: np.ndarray,
    group_cal: np.ndarray,
    *,
    risk_cap: float = RISK_CAP,
    draws: int = SELECT_DRAWS,
    seed: int = 0,
) -> dict:
    """Largest whole-block threshold whose simultaneous clustered bound <= cap."""

    score = np.asarray(score_cal, dtype=float)
    bad = np.asarray(bad_cal, dtype=float)
    group = np.asarray(group_cal)
    finite = np.isfinite(score)
    score, bad, group = score[finite], bad[finite], group[finite]
    n = score.size

    candidates = candidate_thresholds(score)
    units, g = np.unique(group, return_inverse=True)
    n_units = int(units.size)

    admitted = np.zeros((n_units, candidates.size))
    badmitted = np.zeros((n_units, candidates.size))
    for column, threshold in enumerate(candidates):
        mask = score <= threshold
        admitted[:, column] = np.bincount(g[mask], minlength=n_units)
        badmitted[:, column] = np.bincount(g[mask], weights=bad[mask], minlength=n_units)

    weights = clustered_draw_counts(n_units, int(draws), seed).astype(float)
    draw_adm = weights @ admitted
    draw_bad = weights @ badmitted
    with np.errstate(invalid="ignore", divide="ignore"):
        draw_rate = np.where(draw_adm > 0, draw_bad / np.maximum(draw_adm, 1e-12), np.nan)

    n_candidates = int(candidates.size)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        upper_simultaneous = np.nanquantile(draw_rate, 1.0 - ALPHA / n_candidates, axis=0)
        upper_pointwise = np.nanquantile(draw_rate, 1.0 - ALPHA, axis=0)

    from scipy.stats import beta as _beta

    admitted_point = admitted.sum(axis=0)
    bad_point = badmitted.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        rate_point = np.where(admitted_point > 0, bad_point / np.maximum(admitted_point, 1e-12), np.nan)
    upper_binomial = np.where(
        bad_point >= admitted_point,
        1.0,
        _beta.ppf(
            1.0 - ALPHA, bad_point + 1.0, np.maximum(admitted_point - bad_point, 1.0)
        ),
    )

    ok = np.where(upper_simultaneous <= risk_cap)[0]
    ok_pointwise = np.where(upper_pointwise <= risk_cap)[0]
    chosen = int(ok.max()) if ok.size else None
    chosen_pointwise = int(ok_pointwise.max()) if ok_pointwise.size else None

    return {
        "n_cal_cases": int(n),
        "n_cal_units": n_units,
        "n_candidates": n_candidates,
        "bootstrap_draws": int(draws),
        "bootstrap_seed": int(seed),
        "candidates": candidates,
        "candidate_retention": admitted_point / float(n),
        "candidate_rate": rate_point,
        "upper_simultaneous": upper_simultaneous,
        "upper_pointwise": upper_pointwise,
        "upper_binomial": upper_binomial,
        "n_admissible": int(ok.size),
        "n_admissible_pointwise": int(ok_pointwise.size),
        "chosen_index": chosen,
        "threshold": float(candidates[chosen]) if chosen is not None else -float("inf"),
        "retention_cal": float(admitted_point[chosen] / n) if chosen is not None else 0.0,
        "rate_cal": float(rate_point[chosen]) if chosen is not None else float("nan"),
        "upper_cal": float(upper_simultaneous[chosen]) if chosen is not None else float("nan"),
        "threshold_pointwise": (
            float(candidates[chosen_pointwise]) if chosen_pointwise is not None else -float("inf")
        ),
        "status": "threshold_found" if chosen is not None else "no_admissible_threshold",
    }


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------
def clustered_summary(
    admit: dict,
    error: np.ndarray,
    group_index: np.ndarray,
    n_groups: int,
    *,
    draws: int,
    seed: int,
) -> dict:
    """Point estimates and group-clustered 95% intervals for each arm."""

    names = list(admit)
    A = np.column_stack([np.asarray(admit[name], dtype=float) for name in names])
    err = np.asarray(error, dtype=float)
    bad = (err > TOL_C).astype(float)
    AB = A * bad[:, None]
    AE = A * np.where(np.isfinite(err), err, 0.0)[:, None]
    n = A.shape[0]
    g = np.asarray(group_index, dtype=np.int64)

    admitted_point = A.sum(axis=0)
    bad_point = AB.sum(axis=0)
    err_point = np.where(np.isfinite(err), err, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        rate_point = np.where(admitted_point > 0, bad_point / np.maximum(admitted_point, 1e-12), np.nan)
        mean_point = np.where(admitted_point > 0, AE.sum(axis=0) / np.maximum(admitted_point, 1e-12), np.nan)

    per_group_adm = np.column_stack(
        [np.bincount(g, weights=A[:, c], minlength=int(n_groups)) for c in range(A.shape[1])]
    )
    per_group_bad = np.column_stack(
        [np.bincount(g, weights=AB[:, c], minlength=int(n_groups)) for c in range(A.shape[1])]
    )
    per_group_err = np.column_stack(
        [np.bincount(g, weights=AE[:, c], minlength=int(n_groups)) for c in range(A.shape[1])]
    )
    per_group_n = np.bincount(g, minlength=int(n_groups)).astype(float)

    weights = clustered_draw_counts(int(n_groups), int(draws), seed).astype(float)
    drawn_total = weights @ per_group_n
    draw_ret = np.full((int(draws), A.shape[1]), np.nan)
    draw_rate = np.full((int(draws), A.shape[1]), np.nan)
    draw_mean = np.full((int(draws), A.shape[1]), np.nan)
    for column in range(A.shape[1]):
        adm = weights @ per_group_adm[:, column]
        badm = weights @ per_group_bad[:, column]
        errm = weights @ per_group_err[:, column]
        draw_ret[:, column] = adm / np.maximum(drawn_total, 1e-12)
        with np.errstate(invalid="ignore", divide="ignore"):
            draw_rate[:, column] = np.where(adm > 0, badm / np.maximum(adm, 1e-12), np.nan)
            draw_mean[:, column] = np.where(adm > 0, errm / np.maximum(adm, 1e-12), np.nan)

    out = {}
    for column, name in enumerate(names):
        ret_lo, ret_hi = _interval(draw_ret[:, column])
        rate_lo, rate_hi = _interval(draw_rate[:, column])
        mean_lo, mean_hi = _interval(draw_mean[:, column])
        out[name] = {
            "n_cases": int(n),
            "n_admitted": int(admitted_point[column]),
            "retention": float(admitted_point[column] / n),
            "retention_ci_low": ret_lo,
            "retention_ci_high": ret_hi,
            "false_admit_rate": float(rate_point[column]),
            "false_admit_rate_ci_low": rate_lo,
            "false_admit_rate_ci_high": rate_hi,
            "n_false_admitted": int(bad_point[column]),
            "mean_abs_error_admitted": float(mean_point[column]),
            "mean_abs_error_ci_low": mean_lo,
            "mean_abs_error_ci_high": mean_hi,
        }
    return out


def _interval(values: np.ndarray) -> tuple:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan"), float("nan")
    return float(np.quantile(finite, ALPHA / 2)), float(np.quantile(finite, 1 - ALPHA / 2))


def clustered_contrast(
    left: np.ndarray,
    right: np.ndarray,
    group_index: np.ndarray,
    n_groups: int,
    *,
    metric: str,
    error: np.ndarray,
    draws: int,
    seed: int,
) -> dict:
    """Paired group-clustered contrast; metric in {'retention', 'false_admit'}."""

    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    bad = ((np.asarray(error, dtype=float) > TOL_C)).astype(float)
    g = np.asarray(group_index, dtype=np.int64)
    weights = clustered_draw_counts(int(n_groups), int(draws), seed).astype(float)

    def point(lhs, rhs):
        if metric == "retention":
            return float(lhs.mean() - rhs.mean())
        la, lb = lhs.sum(), rhs.sum()
        if la <= 0 or lb <= 0:
            return float("nan")
        return float((lhs * bad).sum() / la - (rhs * bad).sum() / lb)

    per_group_l = np.bincount(g, weights=left, minlength=int(n_groups))
    per_group_r = np.bincount(g, weights=right, minlength=int(n_groups))
    per_group_lb = np.bincount(g, weights=left * bad, minlength=int(n_groups))
    per_group_rb = np.bincount(g, weights=right * bad, minlength=int(n_groups))
    per_group_n = np.bincount(g, minlength=int(n_groups)).astype(float)

    draw = np.full(int(draws), np.nan)
    for index in range(int(draws)):
        weight = weights[index]
        if metric == "retention":
            total = weight @ per_group_n
            draw[index] = (weight @ per_group_l - weight @ per_group_r) / max(total, 1e-12)
        else:
            la = weight @ per_group_l
            ra = weight @ per_group_r
            if la <= 0 or ra <= 0:
                continue
            draw[index] = (weight @ per_group_lb) / la - (weight @ per_group_rb) / ra
    lo, hi = _interval(draw)
    return {
        "metric": metric,
        "point": point(left, right),
        "ci_low": lo,
        "ci_high": hi,
        "ci_excludes_zero": bool(np.isfinite(lo) and np.isfinite(hi) and (lo > 0 or hi < 0)),
        "n_groups": int(n_groups),
        "n_cases": int(left.size),
    }


def fixed_retention_admit(score: np.ndarray, folds: np.ndarray, keys: np.ndarray) -> np.ndarray:
    """Admit the safest 70% of each fold, ties broken by a stable case key.

    This is a second deployment rule, not the risk-cap rule: it is defined for
    every score, it hits exactly 70% per fold, and it never changes meaning
    between calibration and deployment.
    """

    admit = np.zeros(len(score), dtype=bool)
    for fold in np.unique(folds):
        mask = folds == fold
        values = score[mask]
        fold_keys = keys[mask]
        k = int(round(FIXED_RETENTION * mask.sum()))
        order = np.lexsort((fold_keys, values))
        chosen = np.zeros(mask.sum(), dtype=bool)
        chosen[order[:k]] = True
        admit[mask] = chosen
    return admit


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draws-select", type=int, default=SELECT_DRAWS)
    parser.add_argument("--draws-eval", type=int, default=EVAL_DRAWS)
    parser.add_argument("--jobs", type=int, default=5)
    parser.add_argument("--stability-draws", type=int, default=10000)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "models").mkdir(parents=True, exist_ok=True)

    panels = {}
    for panel, spec in PANELS.items():
        cases = pd.read_parquet(spec["cases"]).reset_index(drop=True)
        certs = pd.read_parquet(spec["certificates"]).reset_index(drop=True)
        if len(cases) != len(certs):
            raise RuntimeError(f"{panel}: cases and certificates differ in length")
        group_table = independence_table(cases)
        group_of = dict(
            zip(group_table["network_id"].astype(str), group_table["independence_group"].astype(str))
        )
        cases["independence_group"] = cases["network_id"].astype(str).map(group_of)
        if cases["independence_group"].isna().any():
            raise RuntimeError(f"{panel}: network without an independence group")
        target = policy_target(cases, certs)
        prepared = M301._prepare(cases)
        prepared["certificate_abs_error"] = pd.to_numeric(
            certs["certificate_abs_error"], errors="coerce"
        ).to_numpy(dtype=float)
        prepared["independence_group"] = cases["independence_group"].astype(str).to_numpy()
        groups = cases["independence_group"].astype(str).to_numpy()
        panels[panel] = {
            "cases": cases,
            "certs": certs,
            "prepared": prepared,
            "target": target,
            "group_table": group_table,
            "group_of": group_of,
            "groups": groups,
            "n_groups": int(pd.Series(groups).nunique()),
            "key": case_key(cases),
            "scores_model_free": raw_scores(cases, certs),
            "spec": spec,
        }
        print(
            f"[{panel}] {len(cases)} cases / {cases.network_id.nunique()} networks / "
            f"{panels[panel]['n_groups']} groups; policy bad rate {target['bad_rate']:.4f}; "
            f"event disagreement {target['n_disagree']} "
            f"({target['n_policy_only']} policy-only, {target['n_certificate_only']} certificate-only)",
            flush=True,
        )
        if cases.network_id.nunique() != spec["expected_networks"]:
            raise RuntimeError(f"{panel}: expected {spec['expected_networks']} networks")
        if panels[panel]["n_groups"] != spec["expected_groups"]:
            raise RuntimeError(f"{panel}: expected {spec['expected_groups']} groups")

    # --- nested group cross-fit of the fitted score -----------------------
    from joblib import Parallel, delayed

    cache_dir = ROOT / "scratch" / "p0_01_aligned"
    cache_dir.mkdir(parents=True, exist_ok=True)
    features = tuple(M301.SUPPORT)
    tasks = []
    crossfit = {}
    for panel, data in panels.items():
        frame = data["prepared"]
        slim = frame[
            [
                "network_id",
                "independence_group",
                "longest_run_month",
                "abserr_policy",
                "certificate_abs_error",
                *features,
            ]
        ].copy()
        cases_sha = sha256_file(PANELS[panel]["cases"])
        for fold_seed in FOLD_SEEDS:
            key = hashlib.sha256(
                json.dumps(
                    {
                        "panel": panel,
                        "fold_seed": int(fold_seed),
                        "target": "abserr_policy",
                        "features": list(features),
                        "n_splits": N_SPLITS,
                        "n_inner": N_INNER_SPLITS,
                        "cases": cases_sha,
                        "fold_unit": "independence_group",
                        "cache_version": 4,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()[:16]
            npz = cache_dir / f"{panel}__seed{fold_seed}__fitted_risk__{key}.npz"
            model_path = cache_dir / f"{panel}__seed{fold_seed}__fitted_risk__{key}_models.joblib"
            if npz.exists() and model_path.exists() and not args.no_cache:
                payload = np.load(npz)
                import joblib

                crossfit[(panel, int(fold_seed))] = {
                    "test_score": payload["test_score"],
                    "cal_score_by_fold": payload["cal_score_by_fold"],
                    "models": joblib.load(model_path),
                }
                continue
            tasks.append(
                {
                    "panel": panel,
                    "fold_seed": int(fold_seed),
                    "target": "abserr_policy",
                    "frame": slim,
                    "features": features,
                    "n_splits": N_SPLITS,
                    "n_inner_splits": N_INNER_SPLITS,
                    "npz": npz,
                    "model_path": model_path,
                }
            )

    if tasks:
        print(f"[crossfit] fitting {len(tasks)} tasks on {args.jobs} workers", flush=True)

        def _run(task):
            return M311.crossfit_task(task)

        # Threads, not processes: the worker must see the same imported modules,
        # and a loky worker re-creates this script's ``__main__`` globals, which
        # turns the dynamically loaded 311 module into None.
        outputs = Parallel(n_jobs=int(args.jobs), backend="threading", verbose=0)(
            delayed(_run)(task) for task in tasks
        )
        import joblib

        for task, output in zip(tasks, outputs):
            np.savez_compressed(
                task["npz"],
                test_score=output["test_score"],
                cal_score_by_fold=output["cal_score_by_fold"],
            )
            joblib.dump(output["models"], task["model_path"])
            crossfit[(task["panel"], task["fold_seed"])] = output
    else:
        print("[crossfit] served from cache", flush=True)

    # --- the frozen protocol ----------------------------------------------
    fold_rows = []
    pooled_rows = []
    contrast_rows = []
    threshold_rows = []
    admission_frames = {}
    stability_rows = []

    for panel, data in panels.items():
        cases = data["cases"]
        bad = data["target"]["bad"]
        error = data["target"]["error"]
        groups = data["groups"]
        keys = data["key"]
        group_index, n_groups = M311.factorize_networks(groups)
        n = len(cases)

        for fold_seed in FOLD_SEEDS:
            folds_map = M311.assign_folds(groups, N_SPLITS, fold_seed)
            fold_ids = np.array([folds_map[group] for group in groups], dtype=int)
            shared = shared_stations_across_folds(
                cases,
                data["group_table"],
                {network: folds_map[group] for network, group in data["group_of"].items()},
            )
            shared_years = shared_station_years_across_folds(
                cases,
                {network: folds_map[group] for network, group in data["group_of"].items()},
            )
            if shared or shared_years:
                raise RuntimeError(f"[{panel}/seed{fold_seed}] folds share target stations")
            if fold_seed == FOLD_SEEDS[0]:
                pd.DataFrame(
                    {
                        "panel": panel,
                        "network_id": sorted(data["group_of"]),
                        "independence_group": [data["group_of"][x] for x in sorted(data["group_of"])],
                        "fold": [folds_map[data["group_of"][x]] for x in sorted(data["group_of"])],
                    }
                ).to_csv(OUT / f"fold_assignment_{panel}_seed{fold_seed}.csv", index=False)

            fitted = crossfit[(panel, fold_seed)]
            scores = dict(data["scores_model_free"])
            scores["fitted_risk"] = np.asarray(fitted["test_score"], dtype=float)

            admit_riskcap = {}
            thresholds = {}
            for score_name in ALL_SCORES:
                score = np.asarray(scores[score_name], dtype=float)
                admit = np.zeros(n, dtype=bool)
                per_fold = []
                for fold in range(N_SPLITS):
                    test_mask = fold_ids == fold
                    cal_mask = ~test_mask
                    if not test_mask.any() or not cal_mask.any():
                        continue
                    if score_name in FITTED_SCORES:
                        cal_score = np.asarray(fitted["cal_score_by_fold"])[fold][cal_mask]
                    else:
                        cal_score = score[cal_mask]
                    selection = select_threshold(
                        cal_score,
                        bad[cal_mask],
                        groups[cal_mask],
                        risk_cap=RISK_CAP,
                        draws=int(args.draws_select),
                        seed=stable_seed("aligned-select", panel, fold_seed, fold, score_name),
                    )
                    admit[test_mask] = score[test_mask] <= selection["threshold"]
                    threshold_rows.append(
                        {
                            "panel": panel,
                            "fold_seed": int(fold_seed),
                            "fold": int(fold),
                            "score": score_name,
                            "threshold": selection["threshold"],
                            "retention_cal": selection["retention_cal"],
                            "rate_cal": selection["rate_cal"],
                            "upper_cal": selection["upper_cal"],
                            "n_candidates": selection["n_candidates"],
                            "n_admissible": selection["n_admissible"],
                            "status": selection["status"],
                        }
                    )
                    per_fold.append(
                        {
                            "fold": int(fold),
                            "n_cal": int(cal_mask.sum()),
                            "n_test": int(test_mask.sum()),
                            "threshold": selection["threshold"],
                            "retention_cal": selection["retention_cal"],
                            "rate_cal": selection["rate_cal"],
                            "upper_cal": selection["upper_cal"],
                            "n_candidates": selection["n_candidates"],
                        }
                    )
                admit_riskcap[score_name] = admit
                fold_rows.append(
                    {
                        "panel": panel,
                        "fold_seed": int(fold_seed),
                        "score": score_name,
                        "row_type": "folds",
                        "folds": json.dumps(per_fold),
                        "retention": float(admit.mean()),
                        "false_admit_rate": _rate(admit, bad),
                    }
                )

            admit_riskcap["reconstruct_all"] = np.isfinite(error)
            summary = clustered_summary(
                admit_riskcap,
                error,
                group_index,
                n_groups,
                draws=int(args.draws_eval),
                seed=stable_seed("aligned-eval", panel, fold_seed),
            )
            for name, values in summary.items():
                pooled_rows.append(
                    {
                        "panel": panel,
                        "fold_seed": int(fold_seed),
                        "score": name,
                        "row_type": "riskcap",
                        **values,
                    }
                )

            # fixed-70% comparison (a second, always-defined deployment rule)
            fixed_admit = {}
            for score_name in ALL_SCORES:
                score = np.asarray(scores[score_name], dtype=float)
                if not np.isfinite(score).all():
                    score = np.where(np.isfinite(score), score, np.inf)
                fixed_admit[score_name] = fixed_retention_admit(score, fold_ids, keys)
            fixed_summary = clustered_summary(
                fixed_admit,
                error,
                group_index,
                n_groups,
                draws=int(args.draws_eval),
                seed=stable_seed("aligned-fixed70", panel, fold_seed),
            )
            for name, values in fixed_summary.items():
                pooled_rows.append(
                    {
                        "panel": panel,
                        "fold_seed": int(fold_seed),
                        "score": name,
                        "row_type": "fixed70",
                        **values,
                    }
                )

            # contrasts
            pairs = [
                ("fitted_risk", "peak_overlap_rule"),
                ("fitted_risk", "length_rule"),
                ("fitted_risk", "calibrated_bound"),
                ("fitted_risk", "uncalibrated_bound"),
                ("fitted_risk", "reconstruct_all"),
                ("peak_overlap_rule", "length_rule"),
                ("peak_overlap_rule", "calibrated_bound"),
                ("peak_overlap_rule", "reconstruct_all"),
                ("reconstruct_all", "length_rule"),
            ]
            for metric, table in (("retention", admit_riskcap), ("false_admit", fixed_admit)):
                for left, right in pairs:
                    if left not in table or right not in table:
                        continue
                    values = clustered_contrast(
                        table[left],
                        table[right],
                        group_index,
                        n_groups,
                        metric=metric,
                        error=error,
                        draws=int(args.draws_eval),
                        seed=stable_seed("aligned-contrast", panel, fold_seed, metric, left, right),
                    )
                    contrast_rows.append(
                        {
                            "panel": panel,
                            "fold_seed": int(fold_seed),
                            "metric": metric,
                            "left": left,
                            "right": right,
                            **values,
                        }
                    )

            admission_frames.setdefault(panel, []).append(
                pd.DataFrame(
                    {
                        "fold_seed": int(fold_seed),
                        "fold": fold_ids,
                        "network_id": cases["network_id"].astype(str),
                        "station_id": cases["station_id"].astype(str),
                        "year": cases["year"],
                        "independence_group": groups,
                        "provider": cases["provider"].astype(str),
                        "longest_run": pd.to_numeric(cases["longest_run"], errors="coerce"),
                        "peak_overlap": pd.to_numeric(cases["peak_overlap"], errors="coerce"),
                        "true_peak_hidden_fraction": pd.to_numeric(
                            cases["true_peak_hidden_fraction"], errors="coerce"
                        ),
                        "missing_fraction": pd.to_numeric(
                            cases["missing_fraction"], errors="coerce"
                        ),
                        "n_visible_donors": pd.to_numeric(
                            cases["n_visible_donors"], errors="coerce"
                        ),
                        "donor_corr_mean": pd.to_numeric(
                            cases["donor_corr_mean"], errors="coerce"
                        ),
                        "train_resid_sd": pd.to_numeric(
                            cases["train_resid_sd"], errors="coerce"
                        ),
                        "donor_regime": cases["donor_regime"].astype(str),
                        "policy_choice": cases["policy_choice"].astype(str),
                        "policy_error": error,
                        "policy_bad": bad,
                        "certificate_error": data["target"]["certificate_error"],
                        "certificate_bad": data["target"]["certificate_bad"],
                        **{
                            f"score_{name}": np.asarray(scores[name], dtype=float)
                            for name in ALL_SCORES
                        },
                        **{
                            f"admit_riskcap_{name}": admit_riskcap[name]
                            for name in ARMS
                        },
                        **{f"admit_fixed70_{name}": fixed_admit[name] for name in ALL_SCORES},
                    }
                )
            )

    # --- threshold stability at 10x draws ---------------------------------
    for panel, data in panels.items():
        bad = data["target"]["bad"]
        groups = data["groups"]
        for fold_seed in FOLD_SEEDS:
            folds_map = M311.assign_folds(groups, N_SPLITS, fold_seed)
            fold_ids = np.array([folds_map[group] for group in groups], dtype=int)
            fitted = crossfit[(panel, fold_seed)]
            for score_name in ALL_SCORES:
                score = np.asarray(
                    fitted["test_score"] if score_name == "fitted_risk" else data["scores_model_free"][score_name],
                    dtype=float,
                )
                for fold in range(N_SPLITS):
                    cal_mask = fold_ids != fold
                    cal_score = (
                        np.asarray(fitted["cal_score_by_fold"])[fold][cal_mask]
                        if score_name == "fitted_risk"
                        else score[cal_mask]
                    )
                    base = select_threshold(
                        cal_score,
                        bad[cal_mask],
                        groups[cal_mask],
                        draws=int(args.draws_select),
                        seed=stable_seed("aligned-select", panel, fold_seed, fold, score_name),
                    )
                    wide = select_threshold(
                        cal_score,
                        bad[cal_mask],
                        groups[cal_mask],
                        draws=int(args.stability_draws),
                        seed=stable_seed("aligned-select", panel, fold_seed, fold, score_name),
                    )
                    stability_rows.append(
                        {
                            "panel": panel,
                            "fold_seed": int(fold_seed),
                            "fold": int(fold),
                            "score": score_name,
                            "threshold_1000": base["threshold"],
                            "threshold_10x": wide["threshold"],
                            "retention_1000": base["retention_cal"],
                            "retention_10x": wide["retention_cal"],
                            "changed": bool(base["threshold"] != wide["threshold"]),
                        }
                    )

    # --- write -----------------------------------------------------------
    pooled = pd.DataFrame(pooled_rows)
    pooled.to_csv(OUT / "crossfit_table.csv", index=False)
    pd.DataFrame(fold_rows).to_csv(OUT / "fold_level_retention.csv", index=False)
    pd.DataFrame(contrast_rows).to_csv(OUT / "contrasts.csv", index=False)
    pd.DataFrame(threshold_rows).to_csv(OUT / "thresholds_by_fold.csv", index=False)
    stability = pd.DataFrame(stability_rows)
    stability.to_csv(OUT / "threshold_stability.csv", index=False)

    for panel, frames in admission_frames.items():
        pd.concat(frames, ignore_index=True).to_parquet(
            OUT / f"case_level_admissions_{panel}.parquet", index=False
        )

    event_rows = []
    for panel, data in panels.items():
        target = data["target"]
        event_rows.append(
            {
                "panel": panel,
                "n_cases": len(data["cases"]),
                "policy_bad": target["n_bad"],
                "policy_bad_rate": target["bad_rate"],
                "policy_mean_abs_error": float(np.nanmean(target["error"])),
                "certificate_bad": target["n_certificate_bad"],
                "certificate_bad_rate": float(target["n_certificate_bad"] / len(data["cases"])),
                "certificate_mean_abs_error": float(np.nanmean(target["certificate_error"])),
                "both_bad": int((target["bad"] & target["certificate_bad"]).sum()),
                "neither_bad": int((~target["bad"] & ~target["certificate_bad"]).sum()),
                "policy_only": target["n_policy_only"],
                "certificate_only": target["n_certificate_only"],
                "disagreement_rate": float(target["n_disagree"] / len(data["cases"])),
                "missing_policy_error": target["n_missing_policy_error"],
            }
        )
    crosstab = pd.DataFrame(event_rows)
    crosstab.to_csv(OUT / "event_crosstab.csv", index=False)

    # a full alignment table for one panel keeps the object auditable
    for panel, data in panels.items():
        target = data["target"]
        pd.DataFrame(
            {
                "network_id": data["cases"]["network_id"].astype(str),
                "station_id": data["cases"]["station_id"].astype(str),
                "year": data["cases"]["year"],
                "realization_id": data["cases"]["realization_id"].astype(str),
                "policy_choice": data["cases"]["policy_choice"].astype(str),
                "final_prediction": target["prediction"],
                "reference": target["truth"],
                "policy_abs_error": target["error"],
                "policy_failure": target["bad"],
                "certificate_abs_error": target["certificate_error"],
                "certificate_failure": target["certificate_bad"],
            }
        ).to_csv(OUT / f"loss_object_alignment_{panel}.csv.gz", index=False, compression="gzip")

    # thresholds for downstream replay
    threshold_json = {}
    for row in pd.DataFrame(threshold_rows).itertuples(index=False):
        threshold_json.setdefault(f"{row.panel}|{row.score}|{row.fold_seed}", {})[str(row.fold)] = row.threshold
    (OUT / "final_thresholds.json").write_text(json.dumps(threshold_json, indent=2, sort_keys=True) + "\n")

    # per-fold calibration scores, so a downstream diagnostic cannot silently use
    # a test-fold-derived score for calibration
    for (panel, fold_seed), payload in crossfit.items():
        np.savez_compressed(
            OUT / f"calibration_scores_{panel}_seed{fold_seed}.npz",
            cal_score_by_fold=np.asarray(payload["cal_score_by_fold"], dtype=float),
        )

    # models for replay
    import joblib

    model_index = {}
    for (panel, fold_seed), payload in crossfit.items():
        for fold, model in payload["models"].items():
            name = f"model_{panel}_fitted_risk_seed{fold_seed}_fold{fold}.joblib"
            joblib.dump(model, OUT / "models" / name)
            model_index[f"{panel}|{fold_seed}|{fold}"] = name
    (OUT / "model_index.json").write_text(json.dumps(model_index, indent=2, sort_keys=True) + "\n")

    fingerprint = {
        "script": Path(__file__).name,
        "script_sha256": sha256_file(Path(__file__)),
        "git_head": git_head(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "protocol": {
            "admitted_object": "stored policy reconstruction",
            "failure_event": "abserr_policy > 0.5 C; missing policy error counts as failure",
            "fold_unit": "connected component of networks sharing a station_id",
            "fold_seeds": list(FOLD_SEEDS),
            "n_splits": N_SPLITS,
            "retention_grid": [float(RETENTION_GRID[0]), float(RETENTION_GRID[-1]), 0.01],
            "tie_rule": "no jitter; threshold is an observed score; score <= threshold admits whole tie blocks",
            "selection_rule": (
                "largest snapped threshold whose independence-group clustered bootstrap "
                "percentile at 1 - 0.05/n_candidates is <= 0.05"
            ),
            "select_draws": int(args.draws_select),
            "eval_draws": int(args.draws_eval),
            "fixed_retention": FIXED_RETENTION,
            "fixed_retention_tiebreak": "stable case key (network|station|year|realization)",
        },
        "inputs": {panel: sha256_file(spec["cases"]) for panel, spec in PANELS.items()},
        "elapsed_seconds": round(time.time() - started, 1),
    }
    (OUT / "protocol_fingerprint.json").write_text(json.dumps(fingerprint, indent=2) + "\n")

    write_summary(pooled, pd.DataFrame(contrast_rows), crosstab, stability)
    print(f"[330] done in {time.time() - started:.1f}s -> {OUT}", flush=True)
    return 0


def _rate(admit: np.ndarray, bad: np.ndarray) -> float:
    if not admit.any():
        return float("nan")
    return float(bad[admit].mean())


def write_summary(pooled, contrasts, crosstab, stability) -> None:
    lines = [
        "# Aligned admission: one reconstruction, one failure event, one rule",
        "",
        "Generated by `scripts/330_wrr_aligned_policy_admission.py`. Every number below is",
        "computed on `abserr_policy`, the error of the reconstruction the rule admits.",
        "",
        "## Why this run exists",
        "",
        "The 2026-10-19 run calibrated on the certificate error and then replayed on the",
        "policy error. On the external panel the two failure events disagree on 6.9% of",
        "cases. That is the object mismatch this run removes.",
        "",
        "## Failure events",
        "",
        "| panel | cases | policy bad | policy rate | certificate bad | certificate rate | policy-only | certificate-only |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in crosstab.itertuples(index=False):
        lines.append(
            f"| {row.panel} | {row.n_cases} | {row.policy_bad} | {row.policy_bad_rate:.3f} | "
            f"{row.certificate_bad} | {row.certificate_bad_rate:.3f} | {row.policy_only} | "
            f"{row.certificate_only} |"
        )

    risk = pooled[pooled.row_type.eq("riskcap")]
    for panel in risk.panel.unique():
        block = risk[risk.panel.eq(panel)]
        lines.extend(
            [
                "",
                f"## {panel} — retention at the 5% policy-risk cap",
                "",
                "| score | mean retention | false-admit | mean |err| °C | admitted |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for score in (
            "reconstruct_all",
            "calibrated_bound",
            "uncalibrated_bound",
            "fitted_risk",
            "peak_overlap_rule",
            "length_rule",
        ):
            rows = block[block.score.eq(score)]
            if rows.empty:
                continue
            lines.append(
                f"| {score} | {rows.retention.mean():.3f} | {rows.false_admit_rate.mean():.3f} | "
                f"{rows.mean_abs_error_admitted.mean():.3f} | {rows.n_admitted.mean():.0f} |"
            )

    fixed = pooled[pooled.row_type.eq("fixed70")]
    if not fixed.empty:
        for panel in fixed.panel.unique():
            block = fixed[fixed.panel.eq(panel)]
            lines.extend(
                [
                    "",
                    f"## {panel} — false-admit at a fixed 70% retention",
                    "",
                    "| score | retention | false-admit | mean |err| °C |",
                    "|---|---:|---:|---:|",
                ]
            )
            for score in ALL_SCORES:
                rows = block[block.score.eq(score)]
                if rows.empty:
                    continue
                lines.append(
                    f"| {score} | {rows.retention.mean():.3f} | {rows.false_admit_rate.mean():.3f} | "
                    f"{rows.mean_abs_error_admitted.mean():.3f} |"
                )

    lines.extend(["", "## Paired contrasts", "", "| panel | seed | metric | left | right | point | 95% interval | excludes 0 |", "|---|---:|---|---|---|---:|---|---|"])
    for row in contrasts.itertuples(index=False):
        lines.append(
            f"| {row.panel} | {row.fold_seed} | {row.metric} | {row.left} | {row.right} | "
            f"{row.point:+.4f} | [{row.ci_low:+.4f}, {row.ci_high:+.4f}] | "
            f"{'yes' if row.ci_excludes_zero else 'no'} |"
        )

    if not stability.empty:
        changed = int(stability.changed.sum())
        lines.extend(
            [
                "",
                "## Threshold stability at ten times the bootstrap draws",
                "",
                f"- 1000 -> 10000 draws changes the selected threshold in {changed} of "
                f"{len(stability)} fold-score cells.",
                f"- worst retention shift: "
                f"{float((stability.retention_10x - stability.retention_1000).abs().max()):.4f}",
            ]
        )

    lines.append("")
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())

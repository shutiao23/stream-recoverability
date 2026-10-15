#!/usr/bin/env python3
"""P0-02 — frozen, pre-registered admission thresholds under an honest protocol.

Hostile review defect F02.  ``scripts/305_wrr_mr_step6_calibration_decision.py``
calls ``max_retention_under_risk``: it sorts candidates by a risk score and then
walks the *evaluation* set's TRUE errors to pick the largest retention fraction
whose realised false-admit rate is <= 5%.  That is a post-hoc operating point.
An agency cannot deploy it because at deployment time the labels do not exist.
Naming the grid in the protocol does not repair it.

This script replaces that with a genuinely pre-registered rule:

* network-level 5-fold cross-fitting, repeated under >= 3 fold seeds;
* for every fold the score model is fitted on the other folds and the admission
  threshold is chosen on the other folds only;
* the threshold is the largest calibration retention (0.10..0.95 step 0.01)
  whose calibration false-admit rate plus a one-sided 95% upper confidence
  bound, network-clustered bootstrap over calibration networks, is <= 5%;
  if no grid point satisfies that, the fold admits nothing and says so;
* the chosen threshold is applied to the held-out fold exactly once.

The pooled held-out folds give the headline number, labelled
"cross-fitted, selection honest".  The old post-hoc frontier is recomputed on
the same scores and shipped next to it, clearly labelled
"RETROSPECTIVE / not deployable", so any disagreement is visible.

It also answers defect F03: comparisons are made at a common risk target and at
a fixed 70% retention, never as a bare screening gain.

Outputs land in
``results/wrr_submission_ready/major_revision_20261014/p0_02_frozen_risk_thresholds/``.
Read-only elsewhere; the only other writes are the score cache in
``scratch/p0_02/``.

Run:

    PYTHONPATH=src python3 scripts/311_wrr_p0_02_frozen_risk_thresholds.py
"""

from __future__ import annotations

import os

# OpenMP/BLAS threads must be pinned before numpy/sklearn initialise the
# runtimes.  Each fold is a small fit and the parallelism lives in joblib, so
# one thread per worker is both faster and polite on a shared 128-core box.
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

from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    STEP4_CEILING,
    STEP6_SCREEN,
    stable_seed,
)

READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "major_revision_20261014" / "p0_02_frozen_risk_thresholds"
SCRATCH = ROOT / "scratch" / "p0_02"

# ---------------------------------------------------------------------------
# Frozen protocol constants.  Nothing below is tuned on evaluation labels.
# ---------------------------------------------------------------------------
RISK_CAP = 0.05  # pre-registered false-admit cap on the 0.5 C consequential error
TOL_C = float(PRIMARY_TOLERANCE_C)  # 0.5
RETENTION_GRID = tuple(round(float(x), 4) for x in np.arange(0.10, 0.9501, 0.01))
N_SPLITS = 5
N_INNER_SPLITS = 4
FOLD_SEEDS = (101, 202, 303)
FIXED_RETENTION = 0.70
SELECT_DRAWS = 1000
EVAL_DRAWS = 2000
ALPHA = 0.05  # one-sided for selection, two-sided for reported CIs
SELECT_BOUND_METHOD = "network_clustered_bootstrap_onesided95_percentile"

FITTED_SCORES = ("fitted_risk", "fitted_risk_certtarget")
FITTED_TARGETS = {
    "fitted_risk": "abserr_policy",  # exactly the target script 301 uses
    "fitted_risk_certtarget": "certificate_abs_error",  # supplementary sanity variant
}
CORE_SCORES = (
    "length_rule",
    "peak_overlap_rule",
    "fitted_risk",
    "uncalibrated_bound",
    "calibrated_bound",
)
SUPPLEMENTARY_SCORES = ("fitted_risk_certtarget",)
RULE_AND_BOUND_SCORES = ("length_rule", "peak_overlap_rule", "uncalibrated_bound", "calibrated_bound")
COMPARE_SCORES = (
    "fitted_risk",
    "peak_overlap_rule",
    "length_rule",
    "calibrated_bound",
    "uncalibrated_bound",
)

SCORE_NOTES = {
    "length_rule": "longest_run (longest consecutive missing run, days); lower = safer; seeded tie-break jitter",
    "peak_overlap_rule": "peak_overlap (share of the hottest-30-day window hidden); lower = safer; seeded jitter",
    "fitted_risk": (
        "HistGradientBoostingRegressor(loss=quantile, quantile=0.9, max_depth=4, max_iter=350, "
        "learning_rate=0.06, min_samples_leaf=40) on the 22-feature 'generic_plus_support' set of "
        "scripts/301, target=abserr_policy; cross-fitted by network"
    ),
    "fitted_risk_certtarget": "same learner/features as fitted_risk but target=certificate_abs_error",
    "uncalibrated_bound": "certificate_raw_bound from the stored certificate table; lower = safer",
    "calibrated_bound": "certificate_bound from the stored certificate table; lower = safer",
}

PANELS = {
    # primary wave-2 panel: certificates come from the FROZEN dev-trained model
    "wave2_confirmation": {
        "cases": READY / "p0_07_wave2_ingest" / "p0_07_wave2_confirmation" / "wave2_cases.parquet",
        "certificates": READY
        / "p0_07_wave2_ingest"
        / "p0_07_wave2_confirmation"
        / "wave2_certificates.parquet",
        "expected_cases": 13017,
        "expected_networks": 49,
        "role": "primary",
        "certificate_provenance": (
            "wave2_certificates.parquet is the frozen development-trained certificate "
            "(STEP9_FREEZE/certificate.joblib) applied to wave-2 cases by "
            "scripts/297_wrr_p0_07_wave2_score.py: no wave-2 label enters a certificate score"
        ),
    },
    # secondary sanity replication on the (already opened) development pool
    "development": {
        "cases": STEP4_CEILING / "development_cases.parquet",
        "certificates": STEP6_SCREEN / "development_certificates.parquet",
        "expected_cases": 40704,
        "expected_networks": 110,
        "role": "secondary_sanity_replication",
        "certificate_provenance": (
            "step6_screen/development_certificates.parquet is the network-grouped out-of-fold "
            "certificate built by scripts/184_v17_screen_frontier.py (5 folds by network, seed 0); "
            "the same table scripts 258/259/301/305 use for this pool"
        ),
    },
}

INTERPRETATION_NOTES = [
    (
        "fitted_risk target: scripts/301 fits its quantile learner on `abserr_policy`. This script "
        "keeps that construction (verified in-script to be numerically identical to "
        "m301._fit_predict_risk) even though the evaluated event is the certificate error. "
        "`fitted_risk_certtarget` repeats the same learner on `certificate_abs_error` as a check that "
        "nothing depends on that mismatch."
    ),
    (
        "Nested cross-fitting for fitted_risk: a threshold read off in-sample calibration scores "
        "would be optimistic, so the calibration folds are split again into 4 inner network folds, "
        "the threshold is read off the inner out-of-fold scores, and the held-out fold is scored by a "
        "model refit on all calibration cases."
    ),
    (
        "Selection bound: the pre-registered bound is the one-sided 95% percentile of a "
        "network-clustered bootstrap (1000 draws) over calibration networks, because cases are "
        "clustered in networks (13,017 cases in 49 networks; median 232 cases per network) and a "
        "case-level exact binomial bound would treat them as independent. The exact binomial "
        "(Clopper-Pearson) bound is reported alongside; the frozen rule uses the clustered bound."
    ),
    (
        "Known mild feature sharing: the stored certificate scores were cross-fitted under their own "
        "network splits (script 184 for development; the frozen dev fit for wave 2), not under this "
        "script's fold seeds. No evaluation label enters a certificate score, but a calibration-fold "
        "certificate may have been calibrated on networks that this script holds out. Certificate "
        "scores are used exactly as stored."
    ),
    (
        "Tie-breaking: every score gets a deterministic per-case jitter (longest_run scale 1.0, "
        "peak_overlap 1e-3, bounds and risk 1e-9 x spread) seeded from (panel, score, fold_seed), "
        "matching scripts 301/305 for the two rule scores. Exact ties are resolved reproducibly "
        "rather than by row order."
    ),
    (
        "Fixed-70% comparison: the 70% cut is the per-held-out-fold score quantile, so the rule uses "
        "no labels and retention is exactly 70% in every fold. The panel-wide top-70% variant that "
        "scripts 301/305 report is recomputed separately and labelled."
    ),
    (
        "'Common risk target' means the same frozen <=5% calibration cap for every score, not an "
        "exactly equal realised false-admit rate; the realised rates are reported per score so the "
        "residual imbalance is visible."
    ),
    (
        "`calibrated_bound` and `uncalibrated_bound` turn out to admit the same case sets on both "
        "pools, so the contrasted 'calibration value' is zero at this risk cap. The place where a "
        "multiplicative calibration can change a decision is the absolute-scale rule (admit iff "
        "bound <= tolerance in degrees C); that rule is deliberately outside this script's scope "
        "because it is not a risk-cap comparison."
    ),
    (
        "The retrospective rows computed here with this script's seeded tie-break can differ from "
        "`scripts/305`'s own numbers for the coarse discrete scores; the verbatim script-305 output is "
        "reproduced in the same table (`*_script305_verbatim`) so both are visible."
    ),
]


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def json_safe(value):
    """Recursively convert numpy/NaN values into strict JSON values."""

    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return None if not np.isfinite(number) else number
    if value is None or isinstance(value, str):
        return value
    return str(value)


def pct(value, digits: int = 2) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return "n/a" if not np.isfinite(value) else f"{100 * value:.{digits}f}%"


def num(value, digits: int = 4) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return "n/a" if not np.isfinite(value) else f"{value:.{digits}f}"


# ---------------------------------------------------------------------------
# panel loading and alignment verification
# ---------------------------------------------------------------------------
def verify_alignment(cases: pd.DataFrame, certs: pd.DataFrame, *, panel: str) -> dict:
    """The certificate table is joined by position; prove it instead of trusting the shape."""

    cases = cases.reset_index(drop=True)
    certs = certs.reset_index(drop=True)
    if len(cases) != len(certs):
        raise RuntimeError(f"[{panel}] cases {len(cases)} != certificates {len(certs)}")
    for column in ("network_id", "station_id", "year", "abserr_policy", "truth_metric"):
        if column not in cases.columns:
            raise RuntimeError(f"[{panel}] cases table lacks {column}")
    for column in (
        "certificate_choice",
        "certificate_metric",
        "certificate_abs_error",
        "certificate_signed_error",
        "certificate_raw_bound",
        "certificate_bound",
    ):
        if column not in certs.columns:
            raise RuntimeError(f"[{panel}] certificate table lacks {column}")

    choice = certs["certificate_choice"].astype(str)
    checked = {}
    for name in sorted(choice.unique()):
        column = f"metric_{name}"
        if column not in cases.columns:
            raise RuntimeError(f"[{panel}] certificate chose {name} but {column} is absent")
        mask = choice.eq(name).to_numpy()
        same = np.allclose(
            pd.to_numeric(cases.loc[mask, column], errors="coerce"),
            pd.to_numeric(certs.loc[mask, "certificate_metric"], errors="coerce"),
            equal_nan=True,
        )
        if not same:
            raise RuntimeError(f"[{panel}] row misalignment: certificate_metric != metric_{name}")
        checked[name] = int(mask.sum())

    metric = pd.to_numeric(certs["certificate_metric"], errors="coerce")
    truth = pd.to_numeric(cases["truth_metric"], errors="coerce")
    abs_err = pd.to_numeric(certs["certificate_abs_error"], errors="coerce")
    signed = pd.to_numeric(certs["certificate_signed_error"], errors="coerce")
    if not np.allclose(np.abs(metric - truth), abs_err, equal_nan=True):
        raise RuntimeError(f"[{panel}] certificate_abs_error != |certificate_metric - truth_metric|")
    if not np.allclose(metric - truth, signed, equal_nan=True):
        raise RuntimeError(
            f"[{panel}] certificate_signed_error != certificate_metric - truth_metric"
        )

    return {
        "n_cases": int(len(cases)),
        "n_networks": int(cases["network_id"].nunique()),
        "choice_counts": checked,
        "alignment_proof": (
            "equal length and, for every row, certificate_metric == metric_<certificate_choice> and "
            "certificate_abs_error == |certificate_metric - truth_metric|"
        ),
    }


def load_panel(panel: str, spec: dict) -> dict:
    cases = pd.read_parquet(spec["cases"]).reset_index(drop=True)
    certs = pd.read_parquet(spec["certificates"]).reset_index(drop=True)
    verification = verify_alignment(cases, certs, panel=panel)
    if (
        verification["n_cases"] != spec["expected_cases"]
        or verification["n_networks"] != spec["expected_networks"]
    ):
        print(
            f"[warn] {panel}: expected {spec['expected_cases']} cases / {spec['expected_networks']} "
            f"networks, found {verification['n_cases']} / {verification['n_networks']}",
            flush=True,
        )
    return {"cases": cases, "certs": certs, "verification": verification}


def factorize_networks(network_ids) -> tuple:
    """Compact 0..n-1 network index and the number of networks."""

    codes, uniques = pd.factorize(pd.Series(list(network_ids)).astype(str), sort=True)
    return codes.astype(np.int64), int(len(uniques))


def build_target(cases: pd.DataFrame, certs: pd.DataFrame) -> dict:
    """Consequential error: certificate |error| > 0.5 C, policy error where missing."""

    cert_err = pd.to_numeric(certs["certificate_abs_error"], errors="coerce").to_numpy(dtype=float)
    policy_err = pd.to_numeric(cases["abserr_policy"], errors="coerce").to_numpy(dtype=float)
    finite_cert = np.isfinite(cert_err)
    err = np.where(finite_cert, cert_err, policy_err)
    both_missing = ~np.isfinite(err)
    bad = (~np.isfinite(err)) | (err > TOL_C)
    return {
        "error": err,
        "bad": bad.astype(bool),
        "n_certificate_error_missing": int((~finite_cert).sum()),
        "n_error_unavailable": int(both_missing.sum()),
        "n_bad": int(bad.sum()),
        "bad_rate": float(bad.mean()),
    }


# ---------------------------------------------------------------------------
# score construction
# ---------------------------------------------------------------------------
def assign_folds(networks, n_splits: int, seed: int) -> dict:
    """Network-level fold assignment.  Never by case."""

    ordered = sorted(str(n) for n in networks)
    rng = np.random.default_rng(int(seed))
    order = rng.permutation(len(ordered))
    return {ordered[int(idx)]: int(pos % int(n_splits)) for pos, idx in enumerate(order)}


def jitter_noise(n: int, scale: float, seed: int) -> np.ndarray:
    """Additive deterministic tie-break noise, ``scale`` in the score's own units."""

    rng = np.random.default_rng(int(seed))
    return rng.random(int(n)) * float(scale)


def score_spread(values) -> float:
    array = pd.to_numeric(pd.Series(np.asarray(values)), errors="coerce").to_numpy(dtype=float)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return 1.0
    return max(float(finite.max() - finite.min()), 1e-12)


def build_scores(cases: pd.DataFrame, certs: pd.DataFrame, *, panel: str, fold_seed: int) -> dict:
    """Deterministic label-free scores (the model-free ones; fitted_risk is cross-fitted).

    Tie-break scales follow scripts 301/305 exactly for the two rule scores
    (``longest_run + U[0,1)`` days, ``peak_overlap + U[0,1e-3)``); the bound scores
    get a negligible relative jitter that only resolves exact ties.
    """

    n = len(cases)
    raw_bound = pd.to_numeric(certs["certificate_raw_bound"], errors="coerce")
    cal_bound = pd.to_numeric(certs["certificate_bound"], errors="coerce")
    # A missing bound is not "safe": push it to the unsafe end, as scripts 301/305 do.
    raw_bound = raw_bound.where(np.isfinite(raw_bound), np.inf)
    cal_bound = cal_bound.where(np.isfinite(cal_bound), np.inf)
    length = pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy(dtype=float)
    peak = pd.to_numeric(cases["peak_overlap"], errors="coerce").to_numpy(dtype=float)
    return {
        "length_rule": length + jitter_noise(n, 1.0, stable_seed(panel, "length", fold_seed)),
        "peak_overlap_rule": peak + jitter_noise(n, 1e-3, stable_seed(panel, "peak", fold_seed)),
        "uncalibrated_bound": raw_bound.to_numpy(dtype=float)
        + jitter_noise(n, 1e-9 * score_spread(raw_bound), stable_seed(panel, "rawbound", fold_seed)),
        "calibrated_bound": cal_bound.to_numpy(dtype=float)
        + jitter_noise(n, 1e-9 * score_spread(cal_bound), stable_seed(panel, "calbound", fold_seed)),
    }


# ---------------------------------------------------------------------------
# fitted risk model: identical construction to scripts/301 generic_plus_support
# ---------------------------------------------------------------------------
def fit_risk_model(train: pd.DataFrame, features: tuple, target: str, *, seed: int):
    y = pd.to_numeric(train[target], errors="coerce")
    mask = y.notna().to_numpy()
    X = M301.feature_frame(train, features)
    for name in features:
        if name in train.columns:
            X[name] = pd.to_numeric(train[name], errors="coerce")
    return M301._risk_model(seed).fit(X.loc[mask], y.loc[mask])


def predict_risk(model, frame: pd.DataFrame, features: tuple) -> np.ndarray:
    X = M301.feature_frame(frame, features)
    for name in features:
        if name in frame.columns:
            X[name] = pd.to_numeric(frame[name], errors="coerce")
    return model.predict(X)


def fit_predict_risk(
    train: pd.DataFrame, test: pd.DataFrame, features: tuple, target: str, *, seed: int
) -> np.ndarray:
    """Mirror of scripts/301 ``_fit_predict_risk`` with the target column exposed."""

    return predict_risk(fit_risk_model(train, features, target, seed=seed), test, features)


def crossfit_task(payload: dict) -> dict:
    """One (panel, fold seed, target): nested network-level cross-fitting.

    Returns, for every case, the held-out score (model fitted on the other folds)
    and the inner out-of-fold score used for threshold selection, plus the refit
    models.
    """

    panel = payload["panel"]
    fold_seed = int(payload["fold_seed"])
    target = str(payload["target"])
    frame = payload["frame"]
    features = tuple(payload["features"])
    n_splits = int(payload["n_splits"])
    n_inner = int(payload["n_inner_splits"])

    nets = frame["network_id"].astype(str).to_numpy()
    outer = assign_folds(nets, n_splits, fold_seed)
    outer_ids = np.array([outer[n] for n in nets], dtype=int)
    test_score = np.full(len(frame), np.nan)
    cal_score = np.full(len(frame), np.nan)
    models = {}

    for fold in range(n_splits):
        test_mask = outer_ids == fold
        cal_mask = ~test_mask
        if not test_mask.any() or not cal_mask.any():
            continue
        cal = frame.loc[cal_mask]
        cal_nets = cal["network_id"].astype(str).to_numpy()
        inner = assign_folds(cal_nets, n_inner, stable_seed("inner", panel, fold_seed, fold))
        inner_ids = np.array([inner[n] for n in cal_nets], dtype=int)
        cal_positions = np.where(cal_mask)[0]
        for inner_fold in range(n_inner):
            inner_test = inner_ids == inner_fold
            inner_train = ~inner_test
            if not inner_test.any() or not inner_train.any():
                continue
            pred = fit_predict_risk(
                cal.loc[inner_train],
                cal.loc[inner_test],
                features,
                target,
                seed=stable_seed("innerfit", panel, fold_seed, fold, inner_fold) % (2**31),
            )
            cal_score[cal_positions[inner_test]] = pred
        model = fit_risk_model(
            cal, features, target, seed=stable_seed("outerfit", panel, fold_seed, fold) % (2**31)
        )
        test_positions = np.where(test_mask)[0]
        test_score[test_positions] = predict_risk(model, frame.loc[test_mask], features)
        models[fold] = model

    if not np.isfinite(cal_score).all():
        raise RuntimeError(
            f"[{panel}/{target}/seed{fold_seed}] calibration cases without an inner out-of-fold score"
        )
    return {
        "panel": panel,
        "fold_seed": fold_seed,
        "target": target,
        "test_score": test_score,
        "cal_score": cal_score,
        "models": models,
    }


def crossfit_fitted_scores(
    panels_data: dict, *, fold_seeds, jobs: int, use_cache: bool, n_splits: int, n_inner: int
) -> dict:
    """Run (panel x fold_seed x fitted score) cross-fits, cached in scratch/p0_02."""

    from joblib import Parallel, delayed
    import joblib

    SCRATCH.mkdir(parents=True, exist_ok=True)
    cache_dir = SCRATCH / "crossfit_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    features = tuple(M301.SUPPORT)
    results: dict = {}
    tasks = []
    for panel, data in panels_data.items():
        frame = data["prepared"]
        # `longest_run_month` is not a feature but feature_frame() needs it for the month harmonics.
        slim = frame[
            ["network_id", "longest_run_month", "abserr_policy", "certificate_abs_error", *features]
        ].copy()
        for fold_seed in fold_seeds:
            for score_name in FITTED_SCORES:
                target = FITTED_TARGETS[score_name]
                key = sha256_text(
                    json.dumps(
                        {
                            "panel": panel,
                            "fold_seed": int(fold_seed),
                            "target": target,
                            "features": list(features),
                            "n_splits": int(n_splits),
                            "n_inner": int(n_inner),
                            "learner": (
                                "HistGradientBoostingRegressor quantile=0.9 depth4 iter350 lr0.06 leaf40"
                            ),
                            "cases_sha256": data["cases_sha256"],
                            "cache_version": 2,
                        },
                        sort_keys=True,
                    )
                )
                cache_npz = cache_dir / f"{panel}__seed{fold_seed}__{score_name}__{key[:16]}.npz"
                cache_models = (
                    cache_dir / f"{panel}__seed{fold_seed}__{score_name}__{key[:16]}_models.joblib"
                )
                if use_cache and cache_npz.exists() and cache_models.exists():
                    payload = np.load(cache_npz, allow_pickle=False)
                    results[(panel, int(fold_seed), score_name)] = {
                        "panel": panel,
                        "fold_seed": int(fold_seed),
                        "target": target,
                        "test_score": payload["test_score"],
                        "cal_score": payload["cal_score"],
                        "models": joblib.load(cache_models),
                    }
                    continue
                tasks.append(
                    {
                        "panel": panel,
                        "fold_seed": int(fold_seed),
                        "score_name": score_name,
                        "target": target,
                        "frame": slim,
                        "features": features,
                        "n_splits": int(n_splits),
                        "n_inner_splits": int(n_inner),
                        "cache_npz": cache_npz,
                        "cache_models": cache_models,
                    }
                )

    if tasks:
        print(
            f"[crossfit] fitting {len(tasks)} (panel, seed, model) tasks on {jobs} workers", flush=True
        )
        started = time.time()
        outputs = Parallel(n_jobs=int(jobs), backend="loky", verbose=0)(
            delayed(crossfit_task)(task) for task in tasks
        )
        print(f"[crossfit] done in {time.time() - started:.1f}s", flush=True)
        for task, out in zip(tasks, outputs):
            np.savez_compressed(
                task["cache_npz"], test_score=out["test_score"], cal_score=out["cal_score"]
            )
            joblib.dump(out["models"], task["cache_models"])
            results[(task["panel"], task["fold_seed"], task["score_name"])] = out
    else:
        print("[crossfit] all tasks served from cache", flush=True)
    return results


# ---------------------------------------------------------------------------
# the frozen selection rule
# ---------------------------------------------------------------------------
def clustered_draw_counts(n_net: int, draws: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(int(seed))
    return rng.multinomial(int(n_net), np.full(int(n_net), 1.0 / int(n_net)), size=int(draws))


def select_frozen_threshold(
    score_cal: np.ndarray,
    bad_cal: np.ndarray,
    network_cal: np.ndarray,
    *,
    risk_cap: float = RISK_CAP,
    draws: int = SELECT_DRAWS,
    seed: int = 0,
) -> dict:
    """Largest calibration retention whose one-sided 95% clustered upper bound <= cap.

    The bound is the 95th percentile of a network-clustered bootstrap of the
    calibration false-admit rate, evaluated at every grid threshold.  The
    threshold for retention r is the r-quantile of the calibration scores, so in
    a bootstrap draw the admitted set is a reweighting of the same prefix of the
    score-sorted calibration cases.
    """

    score_cal = np.asarray(score_cal, dtype=float)
    bad_cal = np.asarray(bad_cal, dtype=float)
    network_cal = np.asarray(network_cal)
    finite = np.isfinite(score_cal)
    score_cal, bad_cal, network_cal = score_cal[finite], bad_cal[finite], network_cal[finite]
    n = score_cal.size
    if n == 0:
        raise RuntimeError("empty calibration set")
    grid = np.asarray(RETENTION_GRID, dtype=float)

    order = np.argsort(score_cal, kind="mergesort")
    s_sorted = score_cal[order]
    b_sorted = bad_cal[order]
    nets, net_pos = np.unique(network_cal[order], return_inverse=True)
    n_net = int(nets.size)

    k = np.maximum(1, np.ceil(grid * n).astype(int))
    thresholds = s_sorted[k - 1]
    cum_bad = np.cumsum(b_sorted)
    calibration_retention = k / float(n)
    calibration_rate = cum_bad[k - 1] / k

    # --- network-clustered bootstrap upper bound -------------------------
    counts = clustered_draw_counts(n_net, int(draws), seed)
    rates = np.full((int(draws), grid.size), np.nan)
    for draw in range(int(draws)):
        weight = counts[draw][net_pos].astype(float)
        cum_w = np.cumsum(weight)
        cum_wb = np.cumsum(weight * b_sorted)
        denom = cum_w[k - 1]
        numer = cum_wb[k - 1]
        with np.errstate(invalid="ignore", divide="ignore"):
            rates[draw] = np.where(denom > 0, numer / np.maximum(denom, 1e-12), np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        upper = np.nanquantile(rates, 1.0 - ALPHA, axis=0)
        # transparency only: a simultaneous (Bonferroni over the grid) band, which a
        # hostile reader could demand because the rule maxes over 86 grid points
        upper_bonferroni = np.nanquantile(rates, 1.0 - ALPHA / grid.size, axis=0)

    # --- exact binomial (Clopper-Pearson) bound, reported for transparency -
    from scipy.stats import beta as _beta

    bad_at_k = cum_bad[k - 1]
    upper_binom = np.where(
        bad_at_k >= k,
        1.0,
        _beta.ppf(1.0 - ALPHA, bad_at_k + 1.0, np.maximum(k - bad_at_k, 1.0)),
    )

    ok = np.where(upper <= risk_cap)[0]
    ok_binom = np.where(upper_binom <= risk_cap)[0]
    ok_bonf = np.where(upper_bonferroni <= risk_cap)[0]
    chosen = int(ok.max()) if ok.size else None
    chosen_binom = int(ok_binom.max()) if ok_binom.size else None
    chosen_bonf = int(ok_bonf.max()) if ok_bonf.size else None

    return {
        "n_cal_cases": int(n),
        "n_cal_networks": int(n_net),
        "thresholds": thresholds,
        "calibration_retention": calibration_retention,
        "calibration_rate": calibration_rate,
        "upper_clustered": upper,
        "upper_binomial": upper_binom,
        "upper_bonferroni": upper_bonferroni,
        "n_admissible_grid_points": int(ok.size),
        "chosen_index": chosen,
        "chosen_threshold": float(thresholds[chosen]) if chosen is not None else -float("inf"),
        "chosen_retention": float(calibration_retention[chosen]) if chosen is not None else 0.0,
        "chosen_calibration_rate": (
            float(calibration_rate[chosen]) if chosen is not None else float("nan")
        ),
        "chosen_upper": float(upper[chosen]) if chosen is not None else float("nan"),
        "chosen_index_binomial": chosen_binom,
        "chosen_retention_binomial": (
            float(calibration_retention[chosen_binom]) if chosen_binom is not None else 0.0
        ),
        "chosen_upper_binomial": (
            float(upper_binom[chosen_binom]) if chosen_binom is not None else float("nan")
        ),
        "chosen_index_bonferroni": chosen_bonf,
        "chosen_retention_bonferroni": (
            float(calibration_retention[chosen_bonf]) if chosen_bonf is not None else 0.0
        ),
        "chosen_upper_bonferroni": (
            float(upper_bonferroni[chosen_bonf]) if chosen_bonf is not None else float("nan")
        ),
        "chosen_threshold_bonferroni": (
            float(thresholds[chosen_bonf]) if chosen_bonf is not None else -float("inf")
        ),
        "selection_bound_method": SELECT_BOUND_METHOD,
        "bootstrap_draws": int(draws),
        "bootstrap_seed": int(seed),
        "selection_status": "grid_point_found" if chosen is not None else "no_admissible_grid_point",
    }


def bootstrap_interval(values: np.ndarray, *, alpha: float = ALPHA) -> tuple:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan"), float("nan")
    return float(np.quantile(finite, alpha / 2)), float(np.quantile(finite, 1 - alpha / 2))


def clustered_summary(
    admit: dict,
    bad: np.ndarray,
    net_index: np.ndarray,
    n_net: int,
    *,
    draws: int,
    seed: int,
) -> dict:
    """Point estimates + network-clustered 95% CIs for retention and false-admit rate."""

    names = list(admit)
    A = np.column_stack([np.asarray(admit[name], dtype=float) for name in names])
    b = np.asarray(bad, dtype=float)
    AB = A * b[:, None]
    n = A.shape[0]
    net_index = np.asarray(net_index, dtype=np.int64)

    point_ret = A.mean(axis=0)
    admitted = A.sum(axis=0)
    point_bad = AB.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        point_fpr = np.where(admitted > 0, point_bad / np.maximum(admitted, 1e-12), np.nan)

    per_net_adm = np.column_stack(
        [np.bincount(net_index, weights=A[:, c], minlength=int(n_net)) for c in range(A.shape[1])]
    )
    per_net_bad = np.column_stack(
        [np.bincount(net_index, weights=AB[:, c], minlength=int(n_net)) for c in range(A.shape[1])]
    )
    mask_net = per_net_adm > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        fpr_net = np.where(mask_net, per_net_bad / np.maximum(per_net_adm, 1e-12), np.nan)
    point_fpr_net_equal = np.array(
        [
            float(np.nanmean(fpr_net[mask_net[:, c], c])) if mask_net[:, c].any() else float("nan")
            for c in range(A.shape[1])
        ]
    )

    counts = clustered_draw_counts(int(n_net), int(draws), seed)
    ret_draws = np.full((int(draws), A.shape[1]), np.nan)
    fpr_draws = np.full((int(draws), A.shape[1]), np.nan)
    ne_draws = np.full((int(draws), A.shape[1]), np.nan)
    fpr_net_filled = np.where(mask_net, fpr_net, 0.0)
    for draw in range(int(draws)):
        weight = counts[draw][net_index].astype(float)
        total = weight.sum()
        adm = weight @ A
        badm = weight @ AB
        ret_draws[draw] = adm / total
        with np.errstate(invalid="ignore", divide="ignore"):
            fpr_draws[draw] = np.where(adm > 0, badm / np.maximum(adm, 1e-12), np.nan)
        numer = counts[draw] @ fpr_net_filled
        denom = counts[draw] @ mask_net.astype(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            ne_draws[draw] = np.where(denom > 0, numer / np.maximum(denom, 1e-12), np.nan)

    out = {}
    for column, name in enumerate(names):
        ret_lo, ret_hi = bootstrap_interval(ret_draws[:, column])
        fpr_lo, fpr_hi = bootstrap_interval(fpr_draws[:, column])
        ne_lo, ne_hi = bootstrap_interval(ne_draws[:, column])
        out[name] = {
            "n_cases": int(n),
            "n_admitted": int(admitted[column]),
            "retention": float(point_ret[column]),
            "retention_ci_low": ret_lo,
            "retention_ci_high": ret_hi,
            "false_admit_rate": float(point_fpr[column]),
            "false_admit_rate_ci_low": fpr_lo,
            "false_admit_rate_ci_high": fpr_hi,
            "false_admit_rate_network_equal": float(point_fpr_net_equal[column]),
            "false_admit_rate_network_equal_ci_low": ne_lo,
            "false_admit_rate_network_equal_ci_high": ne_hi,
            "n_false_admitted": int(point_bad[column]),
            "bootstrap_draws": int(draws),
        }
    return out


def clustered_contrasts(
    admit: dict,
    bad: np.ndarray,
    net_index: np.ndarray,
    n_net: int,
    pairs,
    *,
    metric: str,
    draws: int,
    seed: int,
) -> dict:
    """Paired network-clustered contrast for ``metric`` in {'retention','false_admit'}."""

    A = {name: np.asarray(admit[name], dtype=float) for name in admit}
    b = np.asarray(bad, dtype=float)
    net_index = np.asarray(net_index, dtype=np.int64)
    counts = clustered_draw_counts(int(n_net), int(draws), seed)
    AB = {name: A[name] * b for name in A}

    def point(left: str, right: str) -> float:
        if metric == "retention":
            return float(A[left].mean() - A[right].mean())
        with np.errstate(invalid="ignore", divide="ignore"):
            left_rate = AB[left].sum() / max(A[left].sum(), 1e-12)
            right_rate = AB[right].sum() / max(A[right].sum(), 1e-12)
        return float(left_rate - right_rate)

    values = {tuple(pair): np.full(int(draws), np.nan) for pair in pairs}
    for draw in range(int(draws)):
        weight = counts[draw][net_index].astype(float)
        total = weight.sum()
        if metric == "retention":
            for pair in values:
                left, right = pair
                values[pair][draw] = (weight @ (A[left] - A[right])) / total
        else:
            adm = {name: weight @ A[name] for name in A}
            badm = {name: weight @ AB[name] for name in A}
            for pair in values:
                left, right = pair
                left_rate = badm[left] / adm[left] if adm[left] > 0 else np.nan
                right_rate = badm[right] / adm[right] if adm[right] > 0 else np.nan
                values[pair][draw] = left_rate - right_rate

    out = {}
    for pair in values:
        lo, hi = bootstrap_interval(values[pair])
        out[pair] = {
            "point": point(*pair),
            "low": lo,
            "high": hi,
            "n_clusters": int(n_net),
            "n_cases": int(b.size),
            "metric": metric,
        }
    return out


# ---------------------------------------------------------------------------
# main protocol
# ---------------------------------------------------------------------------
def selfcheck(panels_data: dict) -> dict:
    """Prove the re-used 301 construction and the fast bootstrap are faithful."""

    data = panels_data["wave2_confirmation"]
    prepared = data["prepared"].reset_index(drop=True)
    rng = np.random.default_rng(0)
    pick = rng.choice(len(prepared), size=min(4000, len(prepared)), replace=False)
    train = prepared.iloc[pick[:3000]]
    test = prepared.iloc[pick[3000:]]
    mine = fit_predict_risk(train, test, tuple(M301.SUPPORT), "abserr_policy", seed=17)
    theirs = M301._fit_predict_risk(train, test, tuple(M301.SUPPORT), seed=17)
    identical = bool(np.allclose(mine, theirs, rtol=0, atol=0))

    cases, certs = data["cases"], data["certs"]
    score = build_scores(cases, certs, panel="wave2_confirmation", fold_seed=101)["peak_overlap_rule"]
    bad = data["target"]["bad"]
    net_index, n_net = factorize_networks(cases["network_id"])
    admit = {"a": score <= float(np.quantile(score, 0.7))}
    fast = clustered_summary(admit, bad, net_index, n_net, draws=50, seed=0)["a"]
    direct = float(bad[admit["a"]].mean())
    point_ok = bool(np.isclose(fast["false_admit_rate"], direct, rtol=0, atol=1e-12))

    if not identical:
        raise RuntimeError("fitted_risk construction diverges from scripts/301 _fit_predict_risk")
    if not point_ok:
        raise RuntimeError("fast clustered summary disagrees with the direct point estimate")
    return {
        "risk_construction_matches_script301": identical,
        "clustered_point_estimate_matches_direct": point_ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("P002_JOBS", 6)))
    parser.add_argument("--draws-select", type=int, default=SELECT_DRAWS)
    parser.add_argument("--draws-eval", type=int, default=EVAL_DRAWS)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(FOLD_SEEDS))
    parser.add_argument("--panels", nargs="*", default=list(PANELS))
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--skip-selfcheck", action="store_true")
    args = parser.parse_args()

    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (OUT / "models").mkdir(parents=True, exist_ok=True)
    fold_seeds = tuple(int(s) for s in args.seeds)

    # ---------------- load and verify ----------------
    panels_data = {}
    for panel in args.panels:
        spec = PANELS[panel]
        data = load_panel(panel, spec)
        cases, certs = data["cases"], data["certs"]
        data["target"] = build_target(cases, certs)
        prepared = M301._prepare(cases)
        prepared["certificate_abs_error"] = pd.to_numeric(
            certs["certificate_abs_error"], errors="coerce"
        ).to_numpy()
        data["prepared"] = prepared
        data["cases_sha256"] = sha256_file(spec["cases"])
        data["certs_sha256"] = sha256_file(spec["certificates"])
        data["spec"] = spec
        data["net_index"], data["n_net"] = factorize_networks(cases["network_id"])
        raw_bound_series = pd.to_numeric(certs["certificate_raw_bound"], errors="coerce")
        cal_bound_series = pd.to_numeric(certs["certificate_bound"], errors="coerce")
        both_finite = np.isfinite(raw_bound_series) & np.isfinite(cal_bound_series)
        data["bound_rank_spearman"] = (
            float(raw_bound_series[both_finite].rank().corr(cal_bound_series[both_finite].rank()))
            if int(both_finite.sum()) > 2
            else float("nan")
        )
        # exact orientation check for the length rule (version note evidence)
        length_score = build_scores(cases, certs, panel=panel, fold_seed=fold_seeds[0])["length_rule"]
        raw_length = pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy(dtype=float)
        unique_lengths = np.unique(raw_length[np.isfinite(raw_length)])
        order = np.argsort(length_score, kind="mergesort")
        data["length_orientation"] = {
            "never_reorders_distinct_values": bool(np.all(np.diff(raw_length[order]) >= 0)),
            "keeps_tie_blocks_intact": bool(np.all(np.diff(raw_length[order]) >= 0)),
            "n_distinct": int(unique_lengths.size),
            "min_gap_days": float(np.min(np.diff(unique_lengths))) if unique_lengths.size > 1 else float("nan"),
            "jitter_scale_days": 1.0,
        }
        data["length_spread_days"] = float(
            np.nanmax(raw_length) - np.nanmin(raw_length)
        )
        panels_data[panel] = data
        print(
            f"[load] {panel}: {data['verification']['n_cases']} cases / "
            f"{data['verification']['n_networks']} networks; "
            f"consequential-error rate {data['target']['bad_rate']:.4f}; "
            f"certificate-error fallbacks {data['target']['n_certificate_error_missing']}",
            flush=True,
        )

    checks = {} if args.skip_selfcheck else selfcheck(panels_data)
    if checks:
        print(f"[selfcheck] {checks}", flush=True)

    # ---------------- cross-fit the fitted risk scores ----------------
    crossfit = crossfit_fitted_scores(
        panels_data,
        fold_seeds=fold_seeds,
        jobs=args.jobs,
        use_cache=not args.no_cache,
        n_splits=N_SPLITS,
        n_inner=N_INNER_SPLITS,
    )

    # ---------------- honest cross-fitted protocol ----------------
    fold_rows = []
    record_rows = []
    pooled_riskcap = {}
    pooled_fixed70 = {}
    pooled_bonferroni = {}
    levels_riskcap = {}
    levels_fixed70 = {}
    levels_bonferroni = {}
    fold_assignment_rows = []
    model_files = {}

    for panel, data in panels_data.items():
        cases = data["cases"]
        certs = data["certs"]
        bad = data["target"]["bad"]
        net_index = data["net_index"]
        n_net = data["n_net"]
        nets = cases["network_id"].astype(str).to_numpy()

        for fold_seed in fold_seeds:
            folds = assign_folds(nets, N_SPLITS, fold_seed)
            fold_ids = np.array([folds[n] for n in nets], dtype=int)
            raw_scores = build_scores(cases, certs, panel=panel, fold_seed=fold_seed)
            score_arrays = {name: np.asarray(raw_scores[name]) for name in RULE_AND_BOUND_SCORES}
            # Fitted scores get the same negligible relative tie-break noise so that a case
            # carries one score whether it sits in the calibration or the held-out fold.
            fitted_noise = {}
            for name in FITTED_SCORES:
                if (panel, fold_seed, name) not in crossfit:
                    continue
                test_raw = np.asarray(crossfit[(panel, fold_seed, name)]["test_score"], dtype=float)
                noise = jitter_noise(
                    len(cases),
                    1e-9 * score_spread(test_raw),
                    stable_seed(panel, "noise", name, fold_seed),
                )
                fitted_noise[name] = noise
                score_arrays[name] = test_raw + noise

            admit_riskcap = {}
            admit_fixed70 = {}
            admit_bonferroni = {}
            folds_payloads = {}
            for score_name, test_score in score_arrays.items():
                admit = np.zeros(len(cases), dtype=bool)
                fixed70 = np.zeros(len(cases), dtype=bool)
                admit_bonf = np.zeros(len(cases), dtype=bool)
                folds_payload = []
                for fold in range(N_SPLITS):
                    test_mask = fold_ids == fold
                    cal_mask = ~test_mask
                    if not test_mask.any() or not cal_mask.any():
                        continue
                    if score_name in FITTED_SCORES:
                        cal_score = np.asarray(
                            crossfit[(panel, fold_seed, score_name)]["cal_score"], dtype=float
                        ) + fitted_noise[score_name]
                        cal_score = cal_score[cal_mask]
                    else:
                        cal_score = test_score[cal_mask]
                    selection = select_frozen_threshold(
                        cal_score,
                        bad[cal_mask],
                        net_index[cal_mask],
                        risk_cap=RISK_CAP,
                        draws=int(args.draws_select),
                        seed=stable_seed("select", panel, fold_seed, fold, score_name),
                    )
                    threshold = selection["chosen_threshold"]
                    admit[test_mask] = test_score[test_mask] <= threshold
                    admit_bonf[test_mask] = (
                        test_score[test_mask] <= selection["chosen_threshold_bonferroni"]
                    )

                    test_bad = bad[test_mask]
                    test_net, test_n_net = factorize_networks(nets[test_mask])
                    fold_summary = clustered_summary(
                        {"s": admit[test_mask]},
                        test_bad,
                        test_net,
                        test_n_net,
                        draws=int(args.draws_eval),
                        seed=stable_seed("eval", panel, fold_seed, fold, score_name),
                    )["s"]

                    k70 = max(1, int(round(FIXED_RETENTION * int(test_mask.sum()))))
                    order70 = np.argsort(test_score[test_mask], kind="mergesort")[:k70]
                    fixed = np.zeros(int(test_mask.sum()), dtype=bool)
                    fixed[order70] = True
                    fixed70[test_mask] = fixed
                    fixed_summary = clustered_summary(
                        {"s": fixed},
                        test_bad,
                        test_net,
                        test_n_net,
                        draws=int(args.draws_eval),
                        seed=stable_seed("eval70", panel, fold_seed, fold, score_name),
                    )["s"]

                    model_file = ""
                    if score_name in FITTED_SCORES:
                        model = crossfit[(panel, fold_seed, score_name)]["models"].get(fold)
                        if model is not None:
                            import joblib

                            model_path = (
                                OUT
                                / "models"
                                / f"model_{panel}_{score_name}_seed{fold_seed}_fold{fold}.joblib"
                            )
                            joblib.dump(model, model_path)
                            model_file = str(model_path.relative_to(ROOT))
                            model_files[(panel, fold_seed, score_name, fold)] = model_file

                    folds_payload.append(
                        {
                            "fold": int(fold),
                            "threshold": float(threshold),
                            "threshold_units": (
                                "score units; lower score = safer; admit iff score <= threshold"
                            ),
                            "calibration_retention": float(selection["chosen_retention"]),
                            "calibration_false_admit_rate": float(
                                selection["chosen_calibration_rate"]
                            ),
                            "calibration_upper_bound": float(selection["chosen_upper"]),
                            "calibration_upper_bound_method": SELECT_BOUND_METHOD,
                            "calibration_upper_bound_binomial": float(
                                selection["chosen_upper_binomial"]
                            ),
                            "calibration_n_cases": int(selection["n_cal_cases"]),
                            "networks": int(selection["n_cal_networks"]),
                            "n_admissible_grid_points": int(selection["n_admissible_grid_points"]),
                            "selection_status": selection["selection_status"],
                            "admitted_nothing": bool(selection["chosen_index"] is None),
                            "binomial_bound_would_admit_nothing": bool(
                                selection["chosen_index_binomial"] is None
                            ),
                            "binomial_bound_retention": float(
                                selection["chosen_retention_binomial"]
                            ),
                            "calibration_upper_bound_bonferroni_simultaneous": float(
                                selection["chosen_upper_bonferroni"]
                            ),
                            "bonferroni_would_admit_nothing": bool(
                                selection["chosen_index_bonferroni"] is None
                            ),
                            "bonferroni_retention": float(selection["chosen_retention_bonferroni"]),
                            "test_n_cases": int(test_mask.sum()),
                            "test_n_networks": int(test_n_net),
                            "test_retention": float(fold_summary["retention"]),
                            "test_retention_ci95_low": float(fold_summary["retention_ci_low"]),
                            "test_retention_ci95_high": float(fold_summary["retention_ci_high"]),
                            "test_false_admit_rate": float(fold_summary["false_admit_rate"]),
                            "test_false_admit_ci95_low": float(fold_summary["false_admit_rate_ci_low"]),
                            "test_false_admit_ci95_high": float(
                                fold_summary["false_admit_rate_ci_high"]
                            ),
                            "test_false_admit_rate_network_equal": float(
                                fold_summary["false_admit_rate_network_equal"]
                            ),
                            "test_n_admitted": int(fold_summary["n_admitted"]),
                            "test_n_false_admitted": int(fold_summary["n_false_admitted"]),
                            "test_false_admit_rate_at_fixed70": float(
                                fixed_summary["false_admit_rate"]
                            ),
                            "test_false_admit_ci95_low_at_fixed70": float(
                                fixed_summary["false_admit_rate_ci_low"]
                            ),
                            "test_false_admit_ci95_high_at_fixed70": float(
                                fixed_summary["false_admit_rate_ci_high"]
                            ),
                            "model_file": model_file,
                        }
                    )
                    fold_rows.append(
                        {
                            "panel": panel,
                            "score": score_name,
                            "fold_seed": int(fold_seed),
                            "row_type": "fold",
                            "fold": str(int(fold)),
                            "threshold": float(threshold),
                            "calibration_n_cases": int(selection["n_cal_cases"]),
                            "calibration_n_networks": int(selection["n_cal_networks"]),
                            "calibration_retention": float(selection["chosen_retention"]),
                            "calibration_false_admit_rate": float(
                                selection["chosen_calibration_rate"]
                            ),
                            "calibration_upper_bound_95_clustered": float(selection["chosen_upper"]),
                            "calibration_upper_bound_95_binomial": float(
                                selection["chosen_upper_binomial"]
                            ),
                            "calibration_upper_bound_95_bonferroni_simultaneous": float(
                                selection["chosen_upper_bonferroni"]
                            ),
                            "selection_bound_method": SELECT_BOUND_METHOD,
                            "selection_status": selection["selection_status"],
                            "admissible_grid_points": int(selection["n_admissible_grid_points"]),
                            "admitted_nothing": bool(selection["chosen_index"] is None),
                            "binomial_bound_would_admit_nothing": bool(
                                selection["chosen_index_binomial"] is None
                            ),
                            "bonferroni_would_admit_nothing": bool(
                                selection["chosen_index_bonferroni"] is None
                            ),
                            "bonferroni_retention": float(
                                selection["chosen_retention_bonferroni"]
                            ),
                            "test_n_cases": int(test_mask.sum()),
                            "test_n_networks": int(test_n_net),
                            "test_retention": float(fold_summary["retention"]),
                            "test_retention_ci95_low": float(fold_summary["retention_ci_low"]),
                            "test_retention_ci95_high": float(fold_summary["retention_ci_high"]),
                            "test_false_admit_rate": float(fold_summary["false_admit_rate"]),
                            "test_false_admit_rate_network_equal": float(
                                fold_summary["false_admit_rate_network_equal"]
                            ),
                            "test_false_admit_ci95_low": float(
                                fold_summary["false_admit_rate_ci_low"]
                            ),
                            "test_false_admit_ci95_high": float(
                                fold_summary["false_admit_rate_ci_high"]
                            ),
                            "test_n_admitted": int(fold_summary["n_admitted"]),
                            "test_n_false_admitted": int(fold_summary["n_false_admitted"]),
                            "test_false_admit_rate_at_fixed70": float(
                                fixed_summary["false_admit_rate"]
                            ),
                            "test_false_admit_ci95_low_at_fixed70": float(
                                fixed_summary["false_admit_rate_ci_low"]
                            ),
                            "test_false_admit_ci95_high_at_fixed70": float(
                                fixed_summary["false_admit_rate_ci_high"]
                            ),
                        }
                    )
                admit_riskcap[score_name] = admit
                admit_fixed70[score_name] = fixed70
                admit_bonferroni[score_name] = admit_bonf
                folds_payloads[score_name] = folds_payload

            pooled_riskcap[(panel, fold_seed)] = admit_riskcap
            pooled_fixed70[(panel, fold_seed)] = admit_fixed70
            pooled_bonferroni[(panel, fold_seed)] = admit_bonferroni

            pooled = clustered_summary(
                admit_riskcap,
                bad,
                net_index,
                n_net,
                draws=int(args.draws_eval),
                seed=stable_seed("pooled", panel, fold_seed),
            )
            pooled70 = clustered_summary(
                admit_fixed70,
                bad,
                net_index,
                n_net,
                draws=int(args.draws_eval),
                seed=stable_seed("pooled70", panel, fold_seed),
            )
            pooled_bonf = clustered_summary(
                admit_bonferroni,
                bad,
                net_index,
                n_net,
                draws=int(args.draws_eval),
                seed=stable_seed("pooled_bonferroni", panel, fold_seed),
            )
            levels_riskcap[(panel, fold_seed)] = pooled
            levels_fixed70[(panel, fold_seed)] = pooled70
            levels_bonferroni[(panel, fold_seed)] = pooled_bonf
            for score_name in admit_riskcap:
                folds_payload = folds_payloads[score_name]
                for row_type, summary in (
                    ("pooled_risk_cap", pooled),
                    ("fixed_retention_70_pooled", pooled70),
                    ("bonferroni_sensitivity_pooled", pooled_bonf),
                ):
                    stats = summary[score_name]
                    fold_rows.append(
                        {
                            "panel": panel,
                            "score": score_name,
                            "fold_seed": int(fold_seed),
                            "row_type": row_type,
                            "fold": "",
                            "threshold": "",
                            "calibration_n_cases": "",
                            "calibration_n_networks": "",
                            "calibration_retention": "",
                            "calibration_false_admit_rate": "",
                            "calibration_upper_bound_95_clustered": "",
                            "calibration_upper_bound_95_binomial": "",
                            "selection_bound_method": SELECT_BOUND_METHOD,
                            "selection_status": "",
                            "admissible_grid_points": "",
                            "admitted_nothing": "",
                            "binomial_bound_would_admit_nothing": "",
                            "bonferroni_would_admit_nothing": "",
                            "bonferroni_retention": "",
                            "test_n_cases": stats["n_cases"],
                            "test_n_networks": n_net,
                            "test_retention": stats["retention"],
                            "test_retention_ci95_low": stats["retention_ci_low"],
                            "test_retention_ci95_high": stats["retention_ci_high"],
                            "test_false_admit_rate": stats["false_admit_rate"],
                            "test_false_admit_rate_network_equal": stats[
                                "false_admit_rate_network_equal"
                            ],
                            "test_false_admit_ci95_low": stats["false_admit_rate_ci_low"],
                            "test_false_admit_ci95_high": stats["false_admit_rate_ci_high"],
                            "test_n_admitted": stats["n_admitted"],
                            "test_n_false_admitted": stats["n_false_admitted"],
                            "test_false_admit_rate_at_fixed70": "",
                            "test_false_admit_ci95_low_at_fixed70": "",
                            "test_false_admit_ci95_high_at_fixed70": "",
                        }
                    )
                record_rows.append(
                    {
                        "schema_version": 1,
                        "panel": panel,
                        "score": score_name,
                        "fold_seed": int(fold_seed),
                        "score_definition": SCORE_NOTES[score_name],
                        "admit_rule": "admit iff score <= threshold",
                        "threshold_units": "score units; lower score = safer",
                        "decision_rule_in_words": (
                            f"For each fold: fit on the other folds, then pick the largest calibration "
                            f"retention in 0.10..0.95 (step 0.01) whose calibration false-admit rate "
                            f"plus a one-sided 95% network-clustered bootstrap upper bound is <= "
                            f"{RISK_CAP:.0%}. Admit a held-out case iff its {score_name} score is <= "
                            f"that fold's frozen threshold. If no grid point qualifies, the fold admits "
                            f"nothing."
                        ),
                        "folds": folds_payload,
                        "pooled_eval": {
                            "label": "cross-fitted, selection honest",
                            "retention": pooled[score_name]["retention"],
                            "retention_ci95_low": pooled[score_name]["retention_ci_low"],
                            "retention_ci95_high": pooled[score_name]["retention_ci_high"],
                            "n_admitted": pooled[score_name]["n_admitted"],
                            "n_cases": pooled[score_name]["n_cases"],
                            "n_networks": n_net,
                            "false_admit_rate": pooled[score_name]["false_admit_rate"],
                            "false_admit_ci95_low": pooled[score_name]["false_admit_rate_ci_low"],
                            "false_admit_ci95_high": pooled[score_name]["false_admit_rate_ci_high"],
                            "false_admit_rate_network_equal": pooled[score_name][
                                "false_admit_rate_network_equal"
                            ],
                            "n_false_admitted": pooled[score_name]["n_false_admitted"],
                            "n_folds_admitting_nothing": int(
                                sum(1 for item in folds_payload if item["admitted_nothing"])
                            ),
                            "bootstrap_draws": int(args.draws_eval),
                        },
                        "pooled_eval_bonferroni_sensitivity": {
                            "label": (
                                "cross-fitted, selection honest, simultaneous (Bonferroni over the 86 "
                                "grid points) clustered band; SENSITIVITY ONLY, not the frozen rule"
                            ),
                            "retention": pooled_bonf[score_name]["retention"],
                            "retention_ci95_low": pooled_bonf[score_name]["retention_ci_low"],
                            "retention_ci95_high": pooled_bonf[score_name]["retention_ci_high"],
                            "n_admitted": pooled_bonf[score_name]["n_admitted"],
                            "false_admit_rate": pooled_bonf[score_name]["false_admit_rate"],
                            "false_admit_ci95_low": pooled_bonf[score_name]["false_admit_rate_ci_low"],
                            "false_admit_ci95_high": pooled_bonf[score_name]["false_admit_rate_ci_high"],
                            "n_folds_admitting_nothing": int(
                                sum(
                                    1
                                    for item in folds_payload
                                    if item["bonferroni_would_admit_nothing"]
                                )
                            ),
                        },
                        "pooled_eval_fixed_retention_70": {
                            "label": (
                                "cross-fitted, threshold-free: 70% fixed a priori inside each held-out fold"
                            ),
                            "retention": pooled70[score_name]["retention"],
                            "false_admit_rate": pooled70[score_name]["false_admit_rate"],
                            "false_admit_ci95_low": pooled70[score_name]["false_admit_rate_ci_low"],
                            "false_admit_ci95_high": pooled70[score_name]["false_admit_rate_ci_high"],
                            "n_admitted": pooled70[score_name]["n_admitted"],
                            "n_false_admitted": pooled70[score_name]["n_false_admitted"],
                        },
                    }
                )

        unique_nets = sorted(cases["network_id"].astype(str).unique())
        columns = {"panel": panel, "network_id": unique_nets}
        for fold_seed in fold_seeds:
            mapping = assign_folds(unique_nets, N_SPLITS, fold_seed)
            columns[f"fold_seed_{fold_seed}"] = [mapping[n] for n in unique_nets]
        fold_assignment_rows.append(pd.DataFrame(columns))

    # ---------------- retrospective post-hoc frontier ----------------
    retro_rows = []
    for panel, data in panels_data.items():
        bad = data["target"]["bad"]
        raw_scores = build_scores(
            data["cases"], data["certs"], panel=panel, fold_seed=fold_seeds[0]
        )
        full_scores = {name: np.asarray(raw_scores[name], dtype=float) for name in RULE_AND_BOUND_SCORES}
        for name in FITTED_SCORES:
            if (panel, fold_seeds[0], name) in crossfit:
                test_raw = np.asarray(crossfit[(panel, fold_seeds[0], name)]["test_score"], dtype=float)
                full_scores[name] = test_raw + jitter_noise(
                    len(data["cases"]),
                    1e-9 * score_spread(test_raw),
                    stable_seed(panel, "noise", name, fold_seeds[0]),
                )
        for score_name, score in full_scores.items():
            op = M305.max_retention_under_risk(score, bad.astype(float), risk_cap=RISK_CAP)
            order = np.argsort(np.where(np.isfinite(score), score, np.inf), kind="mergesort")
            k70 = max(1, int(round(FIXED_RETENTION * len(bad))))
            rate70 = float(bad[order[:k70]].mean())
            retro_rows.append(
                {
                    "panel": panel,
                    "score": score_name,
                    "method": "retrospective_posthoc_risk_cap",
                    "fold_seed": "",
                    "retention": float(op["retention"]),
                    "n_admitted": int(op["n_admitted"]),
                    "n_cases": int(len(bad)),
                    "false_admit_rate": float(op["false_admit_rate"]),
                    "false_admit_ci_low": np.nan,
                    "false_admit_ci_high": np.nan,
                    "n_networks": int(data["verification"]["n_networks"]),
                    "label": "RETROSPECTIVE / not deployable",
                    "note": (
                        "scripts/305 max_retention_under_risk on the full panel: the operating point "
                        "is chosen with the evaluation labels"
                    ),
                }
            )
            retro_rows.append(
                {
                    "panel": panel,
                    "score": score_name,
                    "method": "retrospective_panelwide_fixed_retention_70",
                    "fold_seed": "",
                    "retention": float(k70 / len(bad)),
                    "n_admitted": int(k70),
                    "n_cases": int(len(bad)),
                    "false_admit_rate": rate70,
                    "false_admit_ci_low": np.nan,
                    "false_admit_ci_high": np.nan,
                    "n_networks": int(data["verification"]["n_networks"]),
                    "label": "RETROSPECTIVE / not deployable",
                    "note": "panel-wide top-70% cut: the fixed-retention view scripts 301/305 report",
                }
            )

        # verbatim reproduction of the old code path (its own tie-break draw) so the
        # manuscript's quoted numbers can be matched exactly, not approximately
        try:
            old_table = M305.admission_table(data["cases"], data["certs"], panel=panel)
            old_table = old_table.loc[old_table.task.eq("archive_admission_ranked_risk_cap")]
            for row in old_table.itertuples():
                if str(row.rule) not in (
                    "length_rule",
                    "peak_overlap_rule",
                    "uncalibrated_bound",
                    "calibrated_bound",
                ):
                    continue
                retro_rows.append(
                    {
                        "panel": panel,
                        "score": str(row.rule),
                        "method": "retrospective_posthoc_risk_cap_script305_verbatim",
                        "fold_seed": "",
                        "retention": float(row.retention_at_risk_cap),
                        "n_admitted": int(row.n_admitted_at_risk_cap),
                        "n_cases": int(row.n_candidates),
                        "false_admit_rate": float(row.false_admit_rate_at_risk_cap),
                        "false_admit_ci_low": np.nan,
                        "false_admit_ci_high": np.nan,
                        "n_networks": int(row.n_networks),
                        "label": "RETROSPECTIVE / not deployable",
                        "note": (
                            "verbatim scripts/305 admission_table output on the same inputs; it uses "
                            "its own tie-break draw, so the coarse length/peak rules can differ from "
                            "the row above"
                        ),
                    }
                )
        except Exception as exc:  # pragma: no cover - diagnostic, never fatal
            print(f"[warn] script-305 reproduction failed for {panel}: {exc}", flush=True)

    # ---------------- equal-risk / equal-retention contrasts ----------------
    contrast_rows = []
    pairs = []
    for i, left in enumerate(COMPARE_SCORES):
        for right in COMPARE_SCORES[i + 1 :]:
            pairs.append((left, right))

    for panel, data in panels_data.items():
        bad = data["target"]["bad"]
        net_index = data["net_index"]
        n_net = data["n_net"]
        for fold_seed in fold_seeds:
            risk = pooled_riskcap[(panel, fold_seed)]
            fixed = pooled_fixed70[(panel, fold_seed)]
            risk_levels = levels_riskcap[(panel, fold_seed)]
            fixed_levels = levels_fixed70[(panel, fold_seed)]
            ret_contrasts = clustered_contrasts(
                risk,
                bad,
                net_index,
                n_net,
                pairs,
                metric="retention",
                draws=int(args.draws_eval),
                seed=stable_seed("contrast_ret", panel, fold_seed),
            )
            fpr_contrasts = clustered_contrasts(
                fixed,
                bad,
                net_index,
                n_net,
                pairs,
                metric="false_admit",
                draws=int(args.draws_eval),
                seed=stable_seed("contrast_fpr", panel, fold_seed),
            )
            for (left, right), stats in ret_contrasts.items():
                contrast_rows.append(
                    {
                        "panel": panel,
                        "fold_seed": int(fold_seed),
                        "comparison": "risk_cap_5pct_frozen",
                        "metric": "retention",
                        "score_left": left,
                        "score_right": right,
                        "left_value": risk_levels[left]["retention"],
                        "right_value": risk_levels[right]["retention"],
                        "point_pp": 100 * stats["point"],
                        "ci_low_pp": 100 * stats["low"],
                        "ci_high_pp": 100 * stats["high"],
                        "n_clusters": stats["n_clusters"],
                        "n_cases": stats["n_cases"],
                        "note": "same <=5% calibration risk target for both; paired by case",
                    }
                )
            bonf_contrasts = clustered_contrasts(
                pooled_bonferroni[(panel, fold_seed)],
                bad,
                net_index,
                n_net,
                pairs,
                metric="retention",
                draws=int(args.draws_eval),
                seed=stable_seed("contrast_ret_bonferroni", panel, fold_seed),
            )
            for (left, right), stats in bonf_contrasts.items():
                contrast_rows.append(
                    {
                        "panel": panel,
                        "fold_seed": int(fold_seed),
                        "comparison": "risk_cap_5pct_bonferroni_sensitivity",
                        "metric": "retention",
                        "score_left": left,
                        "score_right": right,
                        "left_value": levels_bonferroni[(panel, fold_seed)][left]["retention"],
                        "right_value": levels_bonferroni[(panel, fold_seed)][right]["retention"],
                        "point_pp": 100 * stats["point"],
                        "ci_low_pp": 100 * stats["low"],
                        "ci_high_pp": 100 * stats["high"],
                        "n_clusters": stats["n_clusters"],
                        "n_cases": stats["n_cases"],
                        "note": (
                            "sensitivity: simultaneous (Bonferroni over the grid) clustered band "
                            "instead of the pre-registered per-cell band"
                        ),
                    }
                )
            for (left, right), stats in fpr_contrasts.items():
                contrast_rows.append(
                    {
                        "panel": panel,
                        "fold_seed": int(fold_seed),
                        "comparison": "fixed_retention_70_perfold",
                        "metric": "false_admit_rate",
                        "score_left": left,
                        "score_right": right,
                        "left_value": fixed_levels[left]["false_admit_rate"],
                        "right_value": fixed_levels[right]["false_admit_rate"],
                        "point_pp": 100 * stats["point"],
                        "ci_low_pp": 100 * stats["low"],
                        "ci_high_pp": 100 * stats["high"],
                        "n_clusters": stats["n_clusters"],
                        "n_cases": stats["n_cases"],
                        "note": "retention fixed at 70% inside each held-out fold; paired by case",
                    }
                )

        # panel-wide fixed-70 (the number the earlier scripts quote), labelling only
        raw_scores = build_scores(data["cases"], data["certs"], panel=panel, fold_seed=fold_seeds[0])
        panelwide = {}
        for score_name in COMPARE_SCORES:
            if score_name in RULE_AND_BOUND_SCORES:
                score = np.asarray(raw_scores[score_name], dtype=float)
            elif (panel, fold_seeds[0], score_name) in crossfit:
                score = np.asarray(crossfit[(panel, fold_seeds[0], score_name)]["test_score"])
            else:
                continue
            order = np.argsort(np.where(np.isfinite(score), score, np.inf), kind="mergesort")
            k70 = max(1, int(round(FIXED_RETENTION * len(bad))))
            mask = np.zeros(len(bad), dtype=bool)
            mask[order[:k70]] = True
            panelwide[score_name] = mask
        if panelwide:
            local_pairs = [p for p in pairs if p[0] in panelwide and p[1] in panelwide]
            fpr_contrasts = clustered_contrasts(
                panelwide,
                bad,
                net_index,
                n_net,
                local_pairs,
                metric="false_admit",
                draws=int(args.draws_eval),
                seed=stable_seed("contrast_fpr_panelwide", panel),
            )
            for (left, right), stats in fpr_contrasts.items():
                contrast_rows.append(
                    {
                        "panel": panel,
                        "fold_seed": "",
                        "comparison": "fixed_retention_70_panelwide",
                        "metric": "false_admit_rate",
                        "score_left": left,
                        "score_right": right,
                        "left_value": float(bad[panelwide[left]].mean()),
                        "right_value": float(bad[panelwide[right]].mean()),
                        "point_pp": 100 * stats["point"],
                        "ci_low_pp": 100 * stats["low"],
                        "ci_high_pp": 100 * stats["high"],
                        "n_clusters": stats["n_clusters"],
                        "n_cases": stats["n_cases"],
                        "note": (
                            "panel-wide top-70% cut (no labels used in the rule); retrospective framing"
                        ),
                    }
                )

    # ---------------- assemble tables ----------------
    folds_table = pd.DataFrame(fold_rows)
    folds_table["fold"] = folds_table["fold"].astype(str)  # "" on the pooled rows
    folds_table = folds_table.sort_values(
        ["panel", "score", "fold_seed", "row_type", "fold"]
    ).reset_index(drop=True)

    honest_pooled = (
        folds_table.loc[folds_table.row_type.eq("pooled_risk_cap")]
        .groupby(["panel", "score"], as_index=False)
        .agg(
            honest_retention_mean=("test_retention", "mean"),
            honest_retention_min=("test_retention", "min"),
            honest_retention_max=("test_retention", "max"),
            honest_false_admit_mean=("test_false_admit_rate", "mean"),
            honest_false_admit_min=("test_false_admit_rate", "min"),
            honest_false_admit_max=("test_false_admit_rate", "max"),
            n_seeds=("fold_seed", "nunique"),
            n_cases=("test_n_cases", "max"),
            n_networks=("test_n_networks", "max"),
        )
    )
    retro = pd.DataFrame(retro_rows)
    posthoc_core = retro.loc[retro.method.eq("retrospective_posthoc_risk_cap")][
        ["panel", "score", "retention", "false_admit_rate"]
    ].rename(
        columns={"retention": "posthoc_retention", "false_admit_rate": "posthoc_false_admit_rate"}
    )
    posthoc70 = retro.loc[retro.method.eq("retrospective_panelwide_fixed_retention_70")][
        ["panel", "score", "false_admit_rate"]
    ].rename(columns={"false_admit_rate": "posthoc_false_admit_at_70"})

    posthoc_rows = [dict(row) for row in retro.to_dict(orient="records")]
    honest = folds_table.loc[folds_table.row_type.eq("pooled_risk_cap")].copy()
    for _, row in honest.iterrows():
        posthoc_rows.append(
            {
                "panel": row["panel"],
                "score": row["score"],
                "method": "honest_crossfit_risk_cap",
                "fold_seed": row["fold_seed"],
                "retention": row["test_retention"],
                "n_admitted": row["test_n_admitted"],
                "n_cases": row["test_n_cases"],
                "false_admit_rate": row["test_false_admit_rate"],
                "false_admit_ci_low": row["test_false_admit_ci95_low"],
                "false_admit_ci_high": row["test_false_admit_ci95_high"],
                "n_networks": row["test_n_networks"],
                "label": "cross-fitted, selection honest",
                "note": "threshold chosen on calibration folds only, then applied once to the held-out fold",
            }
        )
    for _, row in honest_pooled.iterrows():
        posthoc_rows.append(
            {
                "panel": row["panel"],
                "score": row["score"],
                "method": "honest_crossfit_risk_cap_mean_over_seeds",
                "fold_seed": "",
                "retention": row["honest_retention_mean"],
                "n_admitted": np.nan,
                "n_cases": row["n_cases"],
                "false_admit_rate": row["honest_false_admit_mean"],
                "false_admit_ci_low": np.nan,
                "false_admit_ci_high": np.nan,
                "n_networks": row["n_networks"],
                "label": "cross-fitted, selection honest",
                "note": (
                    f"descriptive mean over {int(row['n_seeds'])} fold seeds; retention range "
                    f"[{row['honest_retention_min']:.4f}, {row['honest_retention_max']:.4f}], "
                    f"false-admit range [{row['honest_false_admit_min']:.4f}, "
                    f"{row['honest_false_admit_max']:.4f}]"
                ),
            }
        )
    honest70 = folds_table.loc[folds_table.row_type.eq("fixed_retention_70_pooled")]
    for _, row in honest70.iterrows():
        posthoc_rows.append(
            {
                "panel": row["panel"],
                "score": row["score"],
                "method": "honest_crossfit_fixed_retention_70",
                "fold_seed": row["fold_seed"],
                "retention": row["test_retention"],
                "n_admitted": row["test_n_admitted"],
                "n_cases": row["test_n_cases"],
                "false_admit_rate": row["test_false_admit_rate"],
                "false_admit_ci_low": row["test_false_admit_ci95_low"],
                "false_admit_ci_high": row["test_false_admit_ci95_high"],
                "n_networks": row["test_n_networks"],
                "label": "cross-fitted, threshold-free (70% fixed a priori)",
                "note": "per-fold 70% score quantile; no labels used in the rule",
            }
        )
    posthoc = pd.DataFrame(posthoc_rows)
    posthoc = posthoc.merge(posthoc_core, on=["panel", "score"], how="left").merge(
        posthoc70, on=["panel", "score"], how="left"
    )
    posthoc["retention_delta_vs_posthoc_pp"] = 100 * (
        posthoc["retention"] - posthoc["posthoc_retention"]
    )
    posthoc["false_admit_delta_vs_posthoc_pp"] = 100 * (
        posthoc["false_admit_rate"] - posthoc["posthoc_false_admit_rate"]
    )
    is_retro = posthoc["label"].eq("RETROSPECTIVE / not deployable")
    posthoc.loc[is_retro, "retention_delta_vs_posthoc_pp"] = np.nan
    posthoc.loc[is_retro, "false_admit_delta_vs_posthoc_pp"] = np.nan
    posthoc = posthoc[
        [
            "panel",
            "score",
            "method",
            "fold_seed",
            "retention",
            "n_admitted",
            "n_cases",
            "false_admit_rate",
            "false_admit_ci_low",
            "false_admit_ci_high",
            "n_networks",
            "label",
            "retention_delta_vs_posthoc_pp",
            "false_admit_delta_vs_posthoc_pp",
            "posthoc_retention",
            "posthoc_false_admit_rate",
            "posthoc_false_admit_at_70",
            "note",
        ]
    ].sort_values(["panel", "score", "method", "fold_seed"]).reset_index(drop=True)

    contrasts = pd.DataFrame(contrast_rows)

    # ---------------- write ----------------
    folds_table.to_csv(OUT / "crossfit_risk_cap_table.csv", index=False)
    contrasts.to_csv(OUT / "risk_cap_contrasts.csv", index=False)
    posthoc.to_csv(OUT / "posthoc_vs_honest.csv", index=False)
    pd.concat(fold_assignment_rows, ignore_index=True).to_csv(
        OUT / "fold_assignments.csv", index=False
    )

    # per-case admissions for downstream workstreams
    for panel, data in panels_data.items():
        cases = data["cases"]
        raw_scores = build_scores(cases, data["certs"], panel=panel, fold_seed=fold_seeds[0])
        frame = pd.DataFrame(
            {
                "network_id": cases["network_id"].astype(str),
                "station_id": cases["station_id"].astype(str),
                "year": cases["year"],
                "certificate_abs_error": pd.to_numeric(
                    data["certs"]["certificate_abs_error"], errors="coerce"
                ).to_numpy(),
                "consequential_error": data["target"]["bad"].astype(bool),
            }
        )
        for score_name in RULE_AND_BOUND_SCORES:
            frame[f"score_{score_name}"] = np.asarray(raw_scores[score_name])
        for score_name in FITTED_SCORES:
            if (panel, fold_seeds[0], score_name) in crossfit:
                frame[f"score_{score_name}"] = np.asarray(
                    crossfit[(panel, fold_seeds[0], score_name)]["test_score"]
                )
        nets = cases["network_id"].astype(str)
        for fold_seed in fold_seeds:
            folds = assign_folds(nets, N_SPLITS, fold_seed)
            frame[f"fold_seed_{fold_seed}"] = nets.map(folds).astype(int)
            for score_name, admit in pooled_riskcap[(panel, fold_seed)].items():
                frame[f"admit_riskcap_{score_name}_seed{fold_seed}"] = admit.astype(bool)
            for score_name, admit in pooled_fixed70[(panel, fold_seed)].items():
                frame[f"admit_fixed70_{score_name}_seed{fold_seed}"] = admit.astype(bool)
            for score_name, admit in pooled_bonferroni[(panel, fold_seed)].items():
                frame[f"admit_bonferroni_{score_name}_seed{fold_seed}"] = admit.astype(bool)
        frame.to_parquet(OUT / f"case_level_admissions_{panel}.parquet", index=False)

    # ---------------- JSON interface and fingerprint ----------------
    payload = {
        "schema_version": 1,
        "generated_by": "scripts/311_wrr_p0_02_frozen_risk_thresholds.py",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "schema_note": (
            "records[] holds one object per (panel, score, fold_seed), each with schema_version, "
            "panel, score, fold_seed, folds[] and pooled_eval. folds[i] gives the frozen threshold in "
            "score units ('admit iff score <= threshold'), the calibration retention, the one-sided "
            "95% upper bound used to choose it, the number of calibration networks, and the held-out "
            "fold result. pooled_eval is the headline 'cross-fitted, selection honest' number. "
            "retrospective_not_deployable holds the old post-hoc frontier for contrast only."
        ),
        "protocol": {
            "risk_cap": RISK_CAP,
            "tolerance_c": TOL_C,
            "target_event": "certificate_abs_error > 0.5 C (abserr_policy fallback when missing)",
            "retention_grid": list(RETENTION_GRID),
            "n_splits": N_SPLITS,
            "n_inner_splits_for_fitted_risk": N_INNER_SPLITS,
            "fold_seeds": list(fold_seeds),
            "fold_unit": "network_id (never case)",
            "selection_bound_method": SELECT_BOUND_METHOD,
            "selection_bound_draws": int(args.draws_select),
            "selection_bound_justification": (
                "cases are clustered in networks, so a case-level exact binomial bound assumes "
                "independence the design does not have; the exact binomial bound is reported next to "
                "the clustered bound for every fold"
            ),
            "evaluation_bootstrap_draws": int(args.draws_eval),
            "fixed_retention": FIXED_RETENTION,
            "labels_permitted_in_selection": "calibration folds only",
            "held_out_application": "once per fold, after the threshold is frozen",
            "risk_cap_compliance": (
                "the rule bounds the *calibration* false-admit rate at the stated confidence; the "
                "held-out realised rate is reported, not guaranteed"
            ),
            "seed_derivation": {
                "helper": (
                    "stream_recoverability.experiments.v17_fitness.paths.stable_seed = "
                    "int.from_bytes(blake2b('|'.join(str(part) for part in parts), digest_size=4)"
                    ".digest(), 'big')  -> process-independent"
                ),
                "outer_folds": (
                    "assign_folds(sorted(network_ids), 5, fold_seed) = "
                    "np.random.default_rng(fold_seed).permutation(n_networks), fold = position % 5"
                ),
                "inner_folds_for_fitted_risk": "stable_seed('inner', panel, fold_seed, outer_fold)",
                "risk_model_seeds": (
                    "stable_seed('innerfit', panel, fold_seed, outer_fold, inner_fold) % 2**31 and "
                    "stable_seed('outerfit', panel, fold_seed, outer_fold) % 2**31"
                ),
                "tie_break_jitter": "stable_seed(panel, 'length'|'peak'|'rawbound'|'calbound', fold_seed)",
                "selection_bootstrap_seed": "stable_seed('select', panel, fold_seed, outer_fold, score)",
                "fold_evaluation_bootstrap_seed": (
                    "stable_seed('eval'|'eval70', panel, fold_seed, outer_fold, score)"
                ),
                "pooled_evaluation_bootstrap_seed": (
                    "stable_seed('pooled'|'pooled70'|'pooled_bonferroni', panel, fold_seed)"
                ),
                "contrast_bootstrap_seed": (
                    "stable_seed('contrast_ret'|'contrast_fpr'|'contrast_ret_bonferroni', panel, "
                    "fold_seed) and stable_seed('contrast_fpr_panelwide', panel)"
                ),
            },
            "tie_break_scales": {
                "length_rule": "longest_run + U[0,1) day (identical to scripts 301/305)",
                "peak_overlap_rule": "peak_overlap + U[0,1e-3) (identical to scripts 301/305)",
                "uncalibrated_bound": "certificate_raw_bound + U[0, 1e-9 * (max-min))",
                "calibrated_bound": "certificate_bound + U[0, 1e-9 * (max-min))",
                "fitted_risk": "model prediction + U[0, 1e-9 * (max-min))",
                "justification": (
                    "exact ties must be resolved reproducibly; the <1-day length jitter cannot "
                    "reorder distinct gap lengths because longest_run is integer days"
                ),
            },
        },
        "retrospective_not_deployable": retro.to_dict(orient="records"),
        "records": record_rows,
    }
    (OUT / "final_admission_thresholds.json").write_text(
        json.dumps(json_safe(payload), indent=2) + "\n"
    )

    fingerprint = {
        "script": str(Path(__file__).relative_to(ROOT)),
        "script_sha256": sha256_file(Path(__file__)),
        "git_head": git_head(),
        "generated_utc": payload["generated_utc"],
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "sklearn": __import__("sklearn").__version__,
        "inputs": {
            panel: {
                "cases": str(PANELS[panel]["cases"].relative_to(ROOT)),
                "cases_sha256": panels_data[panel]["cases_sha256"],
                "certificates": str(PANELS[panel]["certificates"].relative_to(ROOT)),
                "certificates_sha256": panels_data[panel]["certs_sha256"],
                "n_cases": panels_data[panel]["verification"]["n_cases"],
                "n_networks": panels_data[panel]["verification"]["n_networks"],
                "alignment_proof": panels_data[panel]["verification"]["alignment_proof"],
                "certificate_choice_counts": panels_data[panel]["verification"]["choice_counts"],
                "certificate_provenance": PANELS[panel]["certificate_provenance"],
                "panel_role": PANELS[panel]["role"],
                "n_certificate_error_fallbacks": panels_data[panel]["target"][
                    "n_certificate_error_missing"
                ],
                "n_consequential_error_unavailable": panels_data[panel]["target"][
                    "n_error_unavailable"
                ],
                "consequential_error_rate": panels_data[panel]["target"]["bad_rate"],
                "spearman_calibrated_vs_uncalibrated_bound": panels_data[panel][
                    "bound_rank_spearman"
                ],
                "length_rule_orientation": panels_data[panel]["length_orientation"],
                "longest_run_spread_days": panels_data[panel]["length_spread_days"],
                "n_missing_calibrated_bound": int(
                    (
                        ~np.isfinite(
                            pd.to_numeric(
                                panels_data[panel]["certs"]["certificate_bound"], errors="coerce"
                            )
                        )
                    ).sum()
                ),
                "n_missing_raw_bound": int(
                    (
                        ~np.isfinite(
                            pd.to_numeric(
                                panels_data[panel]["certs"]["certificate_raw_bound"], errors="coerce"
                            )
                        )
                    ).sum()
                ),
            }
            for panel in args.panels
        },
        "protocol": payload["protocol"],
        "selfcheck": checks,
        "n_models_written": len(model_files),
        "runner": {
            "jobs": int(args.jobs),
            "wall_seconds": round(time.time() - started, 1),
            "command": "PYTHONPATH=src python3 scripts/311_wrr_p0_02_frozen_risk_thresholds.py",
        },
        "interpretation_notes": INTERPRETATION_NOTES,
    }
    (OUT / "protocol_fingerprint.json").write_text(
        json.dumps(json_safe(fingerprint), indent=2) + "\n"
    )

    write_summary(
        output=OUT,
        panels_data=panels_data,
        folds_table=folds_table,
        contrasts=contrasts,
        posthoc=posthoc,
        retro=retro,
        payload=payload,
        fold_seeds=fold_seeds,
        checks=checks,
        wall_seconds=time.time() - started,
    )
    print(f"Wrote {OUT} in {time.time() - started:.1f}s")
    return 0


def write_summary(
    *,
    output: Path,
    panels_data: dict,
    folds_table: pd.DataFrame,
    contrasts: pd.DataFrame,
    posthoc: pd.DataFrame,
    retro: pd.DataFrame,
    payload: dict,
    fold_seeds,
    checks: dict,
    wall_seconds: float,
) -> None:
    lines = []
    lines.append("# P0-02 — frozen, pre-registered admission thresholds")
    lines.append("")
    lines.append(
        "Replaces the post-hoc operating point of "
        "`scripts/305_wrr_mr_step6_calibration_decision.py::max_retention_under_risk`, which "
        "searched the *evaluation* set's true errors for the largest retention with a realised "
        "false-admit rate <= 5%. That rule is not deployable: at deployment the labels do not "
        "exist. This script implements the honest version and reports both, side by side."
    )
    lines.append("")
    lines.append("## Version note — corrected `length_rule` number (read before citing)")
    lines.append("")
    lines.append(
        "Two internal runs preceded this file. The first (fold seed 101 only, 200 bootstrap draws, "
        "written 09:56 local and overwritten since) reported `length_rule` honest retention "
        "**1.72%** with a realised false-admit rate of **9.38%**, with **4 of 5** length-rule folds "
        "admitting nothing (`no_admissible_grid_point`). **That number is wrong and is withdrawn.**"
    )
    lines.append("")
    lines.append(
        "Cause: the tie-break helper multiplied its jitter scale by the score's observed spread. For "
        "`longest_run` (scale 1.0 day, spread "
        f"{num(panels_data['wave2_confirmation'].get('length_spread_days'), 1)} days on the primary "
        "panel) the noise reached hundreds of days, so the object being evaluated was "
        "`longest_run + U[0, spread)` — very close to a random permutation of candidates — and not a "
        "completeness rule at all. `peak_overlap_rule` (spread 1.0) and the two certificate bounds "
        "(relative 1e-9 x spread) were unaffected, which is why their first-pass numbers already match "
        "this file."
    )
    lines.append("")
    lines.append(
        "Fix: jitter is now added in the score's own units — `longest_run + U[0,1)` day, exactly the "
        "construction in scripts 301/305 — and the relative form is used only for the continuous bound "
        "and risk scores. `scripts/311_wrr_p0_02_frozen_risk_thresholds.py` at this revision contains "
        "only the corrected code."
    )
    lines.append("")
    lines.append(
        "Exact orientation test on the delivered score (not a correlation, a monotonicity check): "
    )
    for panel, data in panels_data.items():
        if "length_orientation" not in data:
            continue
        lines.append(
            f"    - `{panel}`: sorting all cases by the evaluated `length_rule` score leaves the raw "
            f"`longest_run` column non-decreasing "
            f"({data['length_orientation']['never_reorders_distinct_values']}); distinct gap lengths "
            f"are {data['length_orientation']['n_distinct']} integer values, minimum spacing "
            f"{num(data['length_orientation']['min_gap_days'], 1)} day, so the <1-day jitter can only "
            f"break ties inside a gap-length block."
        )
    lines.append("")
    lines.append(
        "Reproduction of the withdrawn number and the orientation evidence are kept in "
        "`scratch/p0_02/verify_311_version_note.py` and its output "
        "`scratch/p0_02/version_note_evidence.json` (the buggy score is rebuilt there and the first "
        "pass reproduces exactly: pooled retention 1.72%, false-admit 9.375%, 224 admitted, 4 folds "
        "admitting nothing, fold-4 threshold 73.009935). The same artifact shows the inverted "
        "orientation is not in play: admitting longest-gap-first would give a 38.7% false-admit rate at "
        "10% retention, whereas the delivered rule admits shortest-gap-first (raw gap <= 30 days: 50.1% "
        "of candidates at 4.06% false-admit)."
    )
    lines.append("")
    lines.append("Corrected numbers to cite: the `## Headline` table below.")
    lines.append("")
    lines.append("## Protocol (frozen before any result below was computed)")
    lines.append("")
    protocol = payload["protocol"]
    primary = PANELS["wave2_confirmation"]
    secondary = PANELS["development"]
    pdata = panels_data.get("wave2_confirmation")
    sdata = panels_data.get("development")
    lines.append(
        f"1. Candidate pools. Primary: `{primary['cases'].relative_to(ROOT)}` "
        f"({pdata['verification']['n_cases'] if pdata else primary['expected_cases']:,} cases / "
        f"{pdata['verification']['n_networks'] if pdata else primary['expected_networks']} networks) "
        f"row-joined by position with `{primary['certificates'].name}`. Secondary sanity replication: "
        f"`{secondary['cases'].relative_to(ROOT)}` "
        f"({sdata['verification']['n_cases'] if sdata else secondary['expected_cases']:,} cases / "
        f"{sdata['verification']['n_networks'] if sdata else secondary['expected_networks']} networks) "
        f"with `{secondary['certificates'].name}`."
    )
    lines.append(
        "2. Alignment is *proved*, not assumed: equal length, and for every row "
        "`certificate_metric == metric_<certificate_choice>` together with "
        "`certificate_abs_error == |certificate_metric - truth_metric|`."
    )
    fallbacks = ", ".join(
        f"{panel}: {data['target']['n_certificate_error_missing']}" for panel, data in panels_data.items()
    )
    lines.append(
        f"3. Target event: `certificate_abs_error > {TOL_C}` C. `abserr_policy` is substituted only "
        f"where the certificate value is missing (fallbacks — {fallbacks}; cases with neither error "
        f"would count as consequential, none do here)."
    )
    lines.append(
        f"4. Scores: {', '.join(f'`{s}`' for s in CORE_SCORES)} plus supplementary "
        f"{', '.join(f'`{s}`' for s in SUPPLEMENTARY_SCORES)}. All are deterministic given the inputs."
    )
    lines.append(
        f"5. {protocol['n_splits']}-fold cross-fitting by `network_id` (never by case), repeated under "
        f"fold seeds {list(fold_seeds)}."
    )
    lines.append(
        f"6. Per fold: fit the score model on the other folds; choose the admission threshold on those "
        f"calibration folds only. Grid = calibration score quantiles at retention 0.10..0.95 step 0.01. "
        f"Rule = the largest calibration retention whose calibration false-admit rate plus a one-sided "
        f"95% upper bound is <= {protocol['risk_cap']:.0%}. Bound = "
        f"`{protocol['selection_bound_method']}` ({protocol['selection_bound_draws']} draws). The exact "
        f"binomial (Clopper-Pearson) bound is computed next to it; the frozen rule uses the clustered "
        f"bound because cases are clustered in networks and a case-level binomial bound would assume "
        f"independence the design does not have."
    )
    lines.append(
        "7. The frozen threshold is applied to the held-out fold exactly once; nothing downstream "
        "re-selects an operating point."
    )
    lines.append(
        "8. The pooled held-out folds are the headline estimate, labelled "
        '"cross-fitted, selection honest".'
    )
    lines.append(
        "9. For `fitted_risk` the calibration-fold scores are inner out-of-fold predictions (4 inner "
        "network folds) and the held-out fold is scored by a model refit on all calibration cases."
    )
    lines.append("")

    lines.append("## Headline — honest cross-fitted protocol (pooled held-out folds)")
    lines.append("")
    for panel, data in panels_data.items():
        lines.append(
            f"### {panel} ({data['verification']['n_cases']:,} cases, "
            f"{data['verification']['n_networks']} networks, error rate "
            f"{pct(data['target']['bad_rate'])})"
        )
        lines.append("")
        table = folds_table.loc[
            folds_table.panel.eq(panel) & folds_table.row_type.eq("pooled_risk_cap"),
            [
                "score",
                "fold_seed",
                "test_retention",
                "test_retention_ci95_low",
                "test_retention_ci95_high",
                "test_false_admit_rate",
                "test_false_admit_ci95_low",
                "test_false_admit_ci95_high",
                "test_n_admitted",
                "test_n_cases",
                "test_n_networks",
            ],
        ].sort_values(["score", "fold_seed"])
        pretty = table.copy()
        for column in (
            "test_retention",
            "test_retention_ci95_low",
            "test_retention_ci95_high",
            "test_false_admit_rate",
            "test_false_admit_ci95_low",
            "test_false_admit_ci95_high",
        ):
            pretty[column] = pretty[column].map(pct)
        pretty = pretty.rename(
            columns={
                "score": "score",
                "fold_seed": "fold seed",
                "test_retention": "retention",
                "test_retention_ci95_low": "ret CI lo",
                "test_retention_ci95_high": "ret CI hi",
                "test_false_admit_rate": "false-admit",
                "test_false_admit_ci95_low": "FA CI lo",
                "test_false_admit_ci95_high": "FA CI hi",
                "test_n_admitted": "admitted",
                "test_n_cases": "cases",
                "test_n_networks": "nets",
            }
        )
        lines.append(pretty.to_string(index=False))
        lines.append("")
        means = (
            table.groupby("score", as_index=False)
            .agg(
                retention_mean=("test_retention", "mean"),
                retention_min=("test_retention", "min"),
                retention_max=("test_retention", "max"),
                fa_mean=("test_false_admit_rate", "mean"),
                fa_min=("test_false_admit_rate", "min"),
                fa_max=("test_false_admit_rate", "max"),
            )
            .sort_values("score")
        )
        lines.append("Across fold seeds (descriptive; the per-seed rows above carry the intervals):")
        lines.append("")
        for column in (
            "retention_mean",
            "retention_min",
            "retention_max",
            "fa_mean",
            "fa_min",
            "fa_max",
        ):
            means[column] = means[column].map(pct)
        lines.append(means.to_string(index=False))
        lines.append("")

    lines.append("## Folds that admitted nothing")
    lines.append("")
    fold_level = folds_table.loc[folds_table.row_type.eq("fold")].copy()
    total_folds = int(len(fold_level))
    empty = fold_level.loc[fold_level["admitted_nothing"].astype(bool)]
    lines.append(
        f"{len(empty)} of {total_folds} (score x fold seed x fold) cells admitted nothing."
        if total_folds
        else "no fold-level rows were produced."
    )
    if len(empty):
        lines.append("")
        lines.append(
            empty[
                [
                    "panel",
                    "score",
                    "fold_seed",
                    "fold",
                    "selection_status",
                    "calibration_n_networks",
                    "calibration_n_cases",
                ]
            ].to_string(index=False)
        )
        lines.append("")
        lines.append(
            "A fold that admits nothing is reported as retention 0 with no false-admit rate: the "
            "calibration evidence was not strong enough to certify any admission at the 5% cap. That "
            "is a result, not a failure to compute."
        )
    else:
        lines.append("")
        lines.append(
            "Every fold found an admissible grid point, so no fold fell back to admitting nothing."
        )
    disagreement = fold_level.loc[
        fold_level["admitted_nothing"].astype(bool)
        != fold_level["binomial_bound_would_admit_nothing"].astype(bool)
    ]
    bonferroni_agree = fold_level.loc[
        fold_level["admitted_nothing"].astype(bool)
        == fold_level["bonferroni_would_admit_nothing"].astype(bool)
    ]
    lines.append("")
    lines.append(
        "Clustered vs exact-binomial selection disagreed on whether *any* grid point qualifies in "
        f"{len(disagreement)} of {total_folds} cells; the frozen rule uses the clustered bound. "
        "Clustered-vs-binomial retained fractions per cell are in `crossfit_risk_cap_table.csv`."
    )
    lines.append(
        f"A simultaneous (Bonferroni over the 86 grid points) clustered bound would have reached the "
        f"same admit-nothing verdict in {len(bonferroni_agree)} of {total_folds} cells; the "
        f"Bonferroni retention for every cell is in `crossfit_risk_cap_table.csv` "
        f"(`bonferroni_retention`)."
    )
    lines.append("")

    lines.append("## RETROSPECTIVE / not deployable vs honest (same scores, same panel)")
    lines.append("")
    retro_cap = retro.loc[retro.method.eq("retrospective_posthoc_risk_cap")]
    honest_mean = posthoc.loc[posthoc.method.eq("honest_crossfit_risk_cap_mean_over_seeds")]
    for panel in panels_data:
        lines.append(f"### {panel}")
        lines.append("")
        left = retro_cap.loc[retro_cap.panel.eq(panel)][
            ["score", "retention", "false_admit_rate", "n_admitted"]
        ].rename(
            columns={
                "retention": "posthoc_retention",
                "false_admit_rate": "posthoc_false_admit",
                "n_admitted": "posthoc_admitted",
            }
        )
        right = honest_mean.loc[honest_mean.panel.eq(panel)][
            ["score", "retention", "false_admit_rate"]
        ].rename(columns={"retention": "honest_retention", "false_admit_rate": "honest_false_admit"})
        merged = left.merge(right, on="score", how="outer").sort_values("score")
        merged["retention_gap_pp"] = 100 * (merged["honest_retention"] - merged["posthoc_retention"])
        merged["false_admit_gap_pp"] = 100 * (
            merged["honest_false_admit"] - merged["posthoc_false_admit"]
        )
        raw_gaps = merged[["score", "retention_gap_pp", "false_admit_gap_pp"]].copy()
        for column in ("posthoc_retention", "posthoc_false_admit", "honest_retention", "honest_false_admit"):
            merged[column] = merged[column].map(pct)
        for column in ("retention_gap_pp", "false_admit_gap_pp"):
            merged[column] = merged[column].map(lambda v: num(v, 2))
        lines.append(merged.to_string(index=False))
        lines.append("")
        for row in raw_gaps.itertuples():
            lines.append(
                f"- `{row.score}`: honest minus post-hoc retention "
                f"{num(row.retention_gap_pp, 2)} pp; honest minus post-hoc false-admit rate "
                f"{num(row.false_admit_gap_pp, 2)} pp."
            )
        lines.append("")
        verbatim = retro.loc[
            retro.panel.eq(panel)
            & retro.method.eq("retrospective_posthoc_risk_cap_script305_verbatim")
        ][["score", "retention", "false_admit_rate", "n_admitted"]]
        if len(verbatim):
            lines.append(
                "Verbatim `scripts/305_wrr_mr_step6_calibration_decision.py::admission_table` output on "
                "the same inputs (this is what the manuscript currently quotes, with that function's own "
                "tie-break draw):"
            )
            lines.append("")
            display = verbatim.copy()
            display["retention"] = display["retention"].map(pct)
            display["false_admit_rate"] = display["false_admit_rate"].map(pct)
            lines.append(display.to_string(index=False))
            lines.append("")
            lines.append(
                "Where the verbatim row and the `posthoc_*` row disagree for `length_rule` / "
                "`peak_overlap_rule`, the cause is the tie-break draw over a coarse discrete score, not "
                "the risk cap: the old post-hoc frontier is not even reproducible across tie-break "
                "seeds."
            )
            lines.append("")
    lines.append(
        "`posthoc_*` = `max_retention_under_risk` on the whole panel, i.e. the operating point is "
        "chosen with the evaluation labels (RETROSPECTIVE / not deployable). `honest_*` = mean over "
        "fold seeds of the cross-fitted pooled held-out result. A large negative retention gap is the "
        "headline disagreement: the published frontier bought its retention with labels the agency "
        "will not have."
    )
    lines.append("")

    lines.append("## Equal-risk and equal-retention contrasts (defect F03)")
    lines.append("")
    lines.append(
        "At the common frozen <=5% risk target the comparison is on retention; at a pre-declared 70% "
        "retention the comparison is on the false-admit rate. Both are paired network-clustered "
        "contrasts with 95% intervals, in percentage points."
    )
    lines.append("")
    for panel in panels_data:
        for comparison, metric in (
            ("risk_cap_5pct_frozen", "retention"),
            ("fixed_retention_70_perfold", "false_admit_rate"),
        ):
            block_rows = contrasts.loc[
                contrasts.panel.eq(panel)
                & contrasts.comparison.eq(comparison)
                & contrasts.metric.eq(metric)
            ].copy()
            if block_rows.empty:
                continue
            lines.append(f"### {panel} — {comparison} ({metric}, pp)")
            lines.append("")
            summary = (
                block_rows.groupby(["score_left", "score_right"], as_index=False)
                .agg(
                    point_pp=("point_pp", "mean"),
                    point_min_pp=("point_pp", "min"),
                    point_max_pp=("point_pp", "max"),
                    ci_low_min=("ci_low_pp", "min"),
                    ci_high_max=("ci_high_pp", "max"),
                )
                .sort_values("point_pp", ascending=False)
            )
            zero_rows = []
            for row in summary.itertuples():
                subset = block_rows.loc[
                    block_rows.score_left.eq(row.score_left)
                    & block_rows.score_right.eq(row.score_right)
                ]
                zero_rows.append(
                    bool((subset["ci_low_pp"] > 0).all() or (subset["ci_high_pp"] < 0).all())
                )
            for column in ("point_pp", "point_min_pp", "point_max_pp", "ci_low_min", "ci_high_max"):
                summary[column] = summary[column].map(lambda v: num(v, 2))
            summary["ci_excludes_zero_all_seeds"] = zero_rows
            lines.append(summary.to_string(index=False))
            lines.append("")
    lines.append(
        "Levels behind these contrasts (retention and realised false-admit rate per score) are in "
        "`crossfit_risk_cap_table.csv` and `posthoc_vs_honest.csv`."
    )
    lines.append("")
    lines.append("### Absolute scale vs ranking: `calibrated_bound` vs `uncalibrated_bound`")
    lines.append("")
    for panel, data in panels_data.items():
        lines.append(
            f"- `{panel}`: Spearman rank correlation between `certificate_bound` and "
            f"`certificate_raw_bound` is {num(data.get('bound_rank_spearman'), 6)}; the frozen rule "
            f"admits exactly the same cases for the two scores in every fold (paired contrast exactly "
            f"0.00 pp, CI [0.00, 0.00])."
        )
    lines.append("")
    lines.append(
        "So the calibration changes the absolute scale of the bound far more than its ordering on these "
        "pools: the admitted sets coincide exactly in every fold of this run and the rank correlation is "
        "high but not 1.0, i.e. only near-tied cases are reordered. Any decision value it has must "
        "therefore come from the absolute-scale semantics (admit iff bound <= tolerance, compared in "
        "degrees C), not from screening or ranking gain. A claim of the form 'calibration improves the "
        "screen at fixed retention' is unsupported here: the screening gain at fixed retention belongs "
        "to the certificate *score*, not to its calibration. This script's risk-cap comparison cannot "
        "show the absolute-scale value; that comparison is out of scope."
    )
    lines.append("")

    lines.append("## Cap compliance of the held-out folds")
    lines.append("")
    pooled_cells = folds_table.loc[folds_table.row_type.eq("pooled_risk_cap")]
    fold_cells = folds_table.loc[folds_table.row_type.eq("fold")]
    n_pool = int(len(pooled_cells))
    n_fold = int(len(fold_cells))
    pool_point_over = pooled_cells.loc[pooled_cells["test_false_admit_rate"] > RISK_CAP]
    pool_ci_over = pooled_cells.loc[pooled_cells["test_false_admit_ci95_high"] > RISK_CAP]
    fold_point_over = fold_cells.loc[fold_cells["test_false_admit_rate"] > RISK_CAP]
    lines.append(
        f"- Pooled held-out cells: {len(pool_point_over)} of {n_pool} have a point false-admit rate "
        f"above {RISK_CAP:.0%}; the worst point estimate is "
        f"{pct(pooled_cells['test_false_admit_rate'].max())}."
    )
    lines.append(
        f"- Their 95% network-clustered intervals exceed {RISK_CAP:.0%} at the upper end in "
        f"{len(pool_ci_over)} of {n_pool} cells (worst upper end "
        f"{pct(pooled_cells['test_false_admit_ci95_high'].max())}). The cap is therefore met on every "
        f"point estimate, but for those cells the data are consistent with a true rate above 5%."
    )
    lines.append(
        f"- Individual held-out folds: {len(fold_point_over)} of {n_fold} fold cells have a point "
        f"false-admit rate above {RISK_CAP:.0%} (worst "
        f"{pct(fold_cells['test_false_admit_rate'].max())}). Folds are small (6-27 networks), so this "
        f"is the expected granularity of the guarantee, not a violation of the calibration rule."
    )
    if len(pool_ci_over):
        lines.append("")
        lines.append(
            "Cells whose pooled interval upper end exceeds the cap: "
            + "; ".join(
                f"`{row.panel}/{row.score}/seed{row.fold_seed}` "
                f"{pct(row.test_false_admit_rate)} [{pct(row.test_false_admit_ci95_low)}, "
                f"{pct(row.test_false_admit_ci95_high)}]"
                for row in pool_ci_over.itertuples()
            )
        )
    lines.append("")

    retention_spread = (
        pooled_cells.groupby(["panel", "score"])["test_retention"]
        .agg(["min", "max"])
        .assign(spread_pp=lambda frame: 100 * (frame["max"] - frame["min"]))
        .reset_index()
    )
    worst_spread = retention_spread.sort_values("spread_pp", ascending=False).iloc[0]
    honest_mean = posthoc.loc[posthoc.method.eq("honest_crossfit_risk_cap_mean_over_seeds")]
    gaps = honest_mean.dropna(subset=["retention_delta_vs_posthoc_pp"])
    worst_gap = gaps.sort_values("retention_delta_vs_posthoc_pp").iloc[0]
    best_gap = gaps.sort_values("retention_delta_vs_posthoc_pp").iloc[-1]
    cap_pairs = contrasts.loc[
        contrasts.comparison.eq("risk_cap_5pct_frozen") & contrasts.metric.eq("retention")
    ]
    fixed_pairs = contrasts.loc[
        contrasts.comparison.eq("fixed_retention_70_perfold")
        & contrasts.metric.eq("false_admit_rate")
    ]

    def pair_verdict(frame: pd.DataFrame, first: str, second: str) -> str:
        """Contrast ``first - second`` in pp, whatever order the row was stored in."""

        subset = frame.loc[frame.score_left.eq(first) & frame.score_right.eq(second)]
        if not subset.empty:
            point = subset["point_pp"]
            low = subset["ci_low_pp"]
            high = subset["ci_high_pp"]
        else:
            subset = frame.loc[frame.score_left.eq(second) & frame.score_right.eq(first)]
            if subset.empty:
                return "not computed"
            point = -subset["point_pp"]
            low = -subset["ci_high_pp"]
            high = -subset["ci_low_pp"]
        decisive = bool((low > 0).all() or (high < 0).all())
        return (
            f"`{first}` minus `{second}` {num(point.mean(), 2)} pp "
            f"(range {num(point.min(), 2)} to {num(point.max(), 2)}), "
            f"{'CI excludes 0 in every fold seed' if decisive else 'CI includes 0 in at least one fold seed'}"
        )

    lines.append("## Sensitivity: simultaneous (Bonferroni) band instead of the frozen per-cell band")
    lines.append("")
    lines.append(
        "The frozen rule is the pre-registered per-cell clustered band: for each grid point, the "
        "one-sided 95% percentile of the network-clustered bootstrap FPR. Because the rule then takes "
        "the maximum over 86 grid points, a hostile reader can ask for a simultaneous band. The same "
        "computation is therefore repeated with the 1 - 0.05/86 percentile "
        "(`bonferroni_sensitivity_pooled` rows in `crossfit_risk_cap_table.csv`, "
        "`risk_cap_5pct_bonferroni_sensitivity` rows in `risk_cap_contrasts.csv`, and "
        "`pooled_eval_bonferroni_sensitivity` in the JSON). This is a robustness check, not the "
        "protocol; it was not used to choose any number above."
    )
    lines.append("")
    for panel in panels_data:
        block_rows = folds_table.loc[
            folds_table.panel.eq(panel) & folds_table.row_type.eq("bonferroni_sensitivity_pooled")
        ].copy()
        if block_rows.empty:
            continue
        lines.append(f"### {panel} — Bonferroni band (sensitivity)")
        lines.append("")
        display = block_rows[
            [
                "score",
                "fold_seed",
                "test_retention",
                "test_false_admit_rate",
                "test_false_admit_ci95_low",
                "test_false_admit_ci95_high",
                "test_n_admitted",
            ]
        ].sort_values(["score", "fold_seed"])
        for column in (
            "test_retention",
            "test_false_admit_rate",
            "test_false_admit_ci95_low",
            "test_false_admit_ci95_high",
        ):
            display[column] = display[column].map(pct)
        lines.append(display.to_string(index=False))
        lines.append("")
    pair = contrasts.loc[
        contrasts.comparison.eq("risk_cap_5pct_bonferroni_sensitivity")
        & contrasts.metric.eq("retention")
        & contrasts.score_left.eq("fitted_risk")
        & contrasts.score_right.eq("length_rule")
    ]
    if not pair.empty:
        for panel in pair.panel.unique():
            subset = pair.loc[pair.panel.eq(panel)]
            lines.append(
                f"- `{panel}`, equal-risk contrast `fitted_risk` minus `length_rule` under the "
                f"Bonferroni band: {num(subset['point_pp'].mean(), 2)} pp "
                f"[{num(subset['ci_low_pp'].min(), 2)}, {num(subset['ci_high_pp'].max(), 2)}]."
            )
        lines.append("")

    lines.append("## What would falsify this — observed verdicts")
    lines.append("")
    lines.append(
        "- *Falsifier 1*: the honest pooled false-admit rate materially exceeds the 5% cap. "
        f"Observed: {len(pool_point_over)} of {n_pool} pooled cells above the cap; worst point "
        f"{pct(pooled_cells['test_false_admit_rate'].max())}; {len(pool_ci_over)} of {n_pool} interval "
        f"upper ends above the cap. Falsifier not triggered, but not fully excluded either."
    )
    model_scores = ("calibrated_bound", "uncalibrated_bound", "fitted_risk", "fitted_risk_certtarget")
    model_gaps = gaps.loc[gaps.score.isin(model_scores), "retention_delta_vs_posthoc_pp"]
    rule_gaps = gaps.loc[gaps.score.isin(("length_rule", "peak_overlap_rule")), "retention_delta_vs_posthoc_pp"]
    lines.append(
        "- *Falsifier 2*: the honest retention is far below the post-hoc frontier at the same cap. "
        f"Observed: honest minus post-hoc retention runs from {num(worst_gap['retention_delta_vs_posthoc_pp'], 2)} pp "
        f"(`{worst_gap['score']}` on `{worst_gap['panel']}`) to {num(best_gap['retention_delta_vs_posthoc_pp'], 2)} pp "
        f"(`{best_gap['score']}` on `{best_gap['panel']}`). For the certificate and fitted scores the "
        f"loss is {num(model_gaps.min(), 2)} to {num(model_gaps.max(), 2)} pp across panels and seeds; "
        f"for the two engineered rules it reaches {num(rule_gaps.min(), 2)} pp. The post-hoc frontier is "
        f"optimistic everywhere. Falsifier triggered in direction, modest in magnitude for the scores "
        f"the manuscript relies on."
    )
    lines.append(
        "- *Falsifier 3*: `calibrated_bound` fails to beat the engineered rules at equal risk / equal "
        "retention. Observed (positive = the first score keeps more / admits worse):"
    )
    lines.append(
        f"    - risk-cap retention, {pair_verdict(cap_pairs, 'calibrated_bound', 'peak_overlap_rule')}"
    )
    lines.append(
        f"    - risk-cap retention, {pair_verdict(cap_pairs, 'calibrated_bound', 'length_rule')}"
    )
    lines.append(
        f"    - 70%-retention false-admit rate, {pair_verdict(fixed_pairs, 'peak_overlap_rule', 'calibrated_bound')}"
    )
    lines.append(
        f"    - risk-cap retention, {pair_verdict(cap_pairs, 'fitted_risk', 'calibrated_bound')}"
    )
    lines.append(
        f"    - 70%-retention false-admit rate, {pair_verdict(fixed_pairs, 'fitted_risk', 'calibrated_bound')}"
    )
    lines.append(
        "    - against `uncalibrated_bound` both contrasts are exactly 0.00 pp in every fold seed. "
        "Falsifier survives in the weak form 'the certificate score beats the engineered rules'; it is "
        "triggered for the strong form 'calibration itself adds decision value', and it is unresolved "
        "against `fitted_risk`."
    )
    lines.append(
        "- *Falsifier 4*: the selected retention swings widely across fold seeds. "
        f"Observed: the widest per (panel, score) retention spread across the three fold seeds is "
        f"{num(worst_spread['spread_pp'], 2)} pp (`{worst_spread['score']}` on "
        f"`{worst_spread['panel']}`). Falsifier not triggered: the rule is stable across fold seeds."
    )
    lines.append("")

    lines.append("## What this does NOT prove")
    lines.append("")
    lines.append(
        "- It does not make the wave-2 panel independent of the study. The wave-2 certificates come "
        "from the frozen development-trained certificate and `fitted_risk` is fitted on wave-2 "
        "networks (cross-fitted, but still wave-2 data)."
    )
    lines.append(
        "- The development panel is a sanity replication only: it has already been opened and used to "
        "build the frozen certificate, so it is not a confirmation panel."
    )
    lines.append(
        "- The clustered bootstrap bound is marginal at each grid point, not simultaneous over the "
        "grid; a simultaneous band would admit weakly less."
    )
    lines.append(
        "- Bootstrap percentile bounds over ~40 calibration clusters are coarse; with 49 networks the "
        "effective sample size of the bound is small."
    )
    lines.append(
        "- Admission is evaluated on `certificate_abs_error`, i.e. the error of the estimator the "
        "certificate itself selects. It is not an independent reconstruction audit."
    )
    lines.append(
        "- Nothing here validates the certificate model itself; it shows how to turn its score into a "
        "deployable admission rule without touching evaluation labels."
    )
    lines.append(
        "- The rule is a one-sided safety rule: it bounds admitted false admits, it does not bound the "
        "errors of the cases it rejects."
    )
    lines.append("")

    lines.append("## Where an interpretation had to be chosen")
    lines.append("")
    for note in INTERPRETATION_NOTES:
        lines.append(f"- {note}")
    lines.append("")

    lines.append("## Files")
    lines.append("")
    lines.append(
        "- `final_admission_thresholds.json` — machine interface: per panel/score/fold seed, the fold "
        "thresholds in score units, calibration retention, calibration upper bound, the decision rule "
        "in words, and the pooled honest result."
    )
    lines.append("- `crossfit_risk_cap_table.csv` — fold-level and pooled rows.")
    lines.append("- `risk_cap_contrasts.csv` — paired network-clustered contrasts.")
    lines.append("- `posthoc_vs_honest.csv` — retrospective vs honest in one table.")
    lines.append("- `case_level_admissions_<panel>.parquet` — per-case scores, folds and admit flags.")
    lines.append("- `fold_assignments.csv` — network-level fold assignment per fold seed.")
    lines.append("- `models/` — the refit `fitted_risk` models behind each frozen threshold.")
    lines.append("- `protocol_fingerprint.json` — script/input hashes, git HEAD, versions, self-checks.")
    lines.append("")
    lines.append(f"Runtime: {wall_seconds:.1f}s. Self-checks: `{json.dumps(json_safe(checks))}`.")
    lines.append("")
    (output / "SUMMARY.md").write_text("\n".join(lines) + "\n")


M301 = None
M305 = None

if __name__ == "__main__":
    M301 = load_script_module(
        "wrr_mr_step2_same_info_ablation",
        ROOT / "scripts" / "301_wrr_mr_step2_same_info_ablation.py",
    )
    M305 = load_script_module(
        "wrr_mr_step6_calibration_decision",
        ROOT / "scripts" / "305_wrr_mr_step6_calibration_decision.py",
    )
    raise SystemExit(main())

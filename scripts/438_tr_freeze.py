#!/usr/bin/env python3
"""TR-E7a: freeze the target-recovery pipeline before the sealed Australian test.

Final models are fitted on every source case; admission thresholds come from
the source out-of-fold scores (deployment population), one per information
layer and one marginal, at a nominal 5% admitted risk. frozen/pipeline.json
records the selection, the thresholds and the model files that the Australian
evaluation reads. Nothing here reads Australian water temperature.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

import wrr_tr_common as T
import wrr_tr_features as F

OUT = T.OUT / "e2_prereg"
FROZEN = OUT / "frozen"
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, n_jobs=32)
SCORE_COLUMNS = {
    "R7a_target_aware": ("score::R7a_target_aware_pfail (D2* distribution)", "fail_D2"),
    "R7b_direct_D2": ("score::R7b_direct_failure_probability (D2*)", "fail_D2"),
    "R6_law": ("score::R6_recovery_law_pfail", "fail_P0"),
    "R7b_direct_P0": ("score::R7b_direct_failure_probability (P0)", "fail_P0"),
}


def threshold(score: np.ndarray, fail: np.ndarray, weight: np.ndarray, alpha: float) -> float:
    order = np.argsort(score, kind="mergesort")
    s, f, w = score[order], fail[order], weight[order]
    risk = np.cumsum(w * f) / np.maximum(np.cumsum(w), 1e-12)
    last = np.r_[s[1:] != s[:-1], True]
    ok = np.flatnonzero(last & (risk <= alpha))
    return float(s[ok[-1]]) if len(ok) else float("-inf")


def main() -> int:
    settings = T.settings()
    FROZEN.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    selection = json.loads((T.OUT / "e4_estimators/d2_selection.json").read_text())
    d2, levels = selection["d2"], selection["levels"]
    oof = pd.read_parquet(T.OUT / "e4_estimators/oof_predictions.parquet")
    scores = pd.read_parquet(T.OUT / "e5_rules/scores.parquet")
    if not (scores.realization_id.to_numpy() == cases.realization_id.to_numpy()).all():
        raise RuntimeError("Scores are not aligned with cases")
    tolerance = settings["tolerance_c"]
    names = [f"q{int(level * 100):02d}" for level in levels]
    d2_point = cases.state_h30_q50 if d2 == "P3" else (cases.raw_h30_q50 if d2 == "P3raw" else oof[f"h30__{d2}_q50"])
    cases["fail_D2"] = ((d2_point - cases.eval_truth_h30).abs() > tolerance).astype(int)
    cases["fail_P0"] = ((cases.h30__policy - cases.eval_truth_h30).abs() > tolerance).astype(int)
    residual = cases.eval_truth_h30 - cases.h30__policy
    files = {}
    plain, simulated = F.design_matrix(cases, "h30", simulation=False), F.design_matrix(cases, "h30", simulation=True)
    p2 = lgb.LGBMRegressor(objective="l2", random_state=settings["seed"], **PARAMS).fit(plain, residual)
    files["P2"] = FROZEN / "p2_regressor.joblib"
    joblib.dump({"model": p2, "columns": list(plain.columns)}, files["P2"])
    for name, matrix in (("P5a", plain), ("P5b", simulated)):
        models = [lgb.LGBMRegressor(objective="quantile", alpha=level, random_state=settings["seed"], **PARAMS).fit(matrix, residual) for level in levels]
        files[name] = FROZEN / f"{name.lower()}_quantiles.joblib"
        joblib.dump({"models": models, "levels": levels, "columns": list(matrix.columns), "simulation": name == "P5b"}, files[name])
    for label in ("fail_P0", "fail_D2"):
        classifier = lgb.LGBMClassifier(objective="binary", random_state=settings["seed"], **PARAMS).fit(simulated, cases[label])
        files[label] = FROZEN / f"classifier_{label}.joblib"
        joblib.dump({"model": classifier, "columns": list(simulated.columns)}, files[label])
    weight = T.population_weights(cases, "deploy").to_numpy()
    layer = cases.policy_choice.where(cases.policy_choice.isin(["donor_ridge", "air_ridge"]), "other").to_numpy()
    thresholds = {}
    for score_name, (column, label) in SCORE_COLUMNS.items():
        s, f = scores[column].to_numpy(dtype=float), cases[label].to_numpy()
        keep = (weight > 0) & np.isfinite(s)
        entry = {"__marginal__": threshold(s[keep], f[keep], weight[keep], 0.05)}
        for value in np.unique(layer):
            mask = keep & (layer == value)
            if mask.sum() >= 50:
                entry[value] = threshold(s[mask], f[mask], weight[mask], 0.05)
        thresholds[score_name] = entry
    T.write_json(FROZEN / "thresholds.json", {"alpha": 0.05, "population": "deploy", "thresholds": thresholds})
    files["thresholds"] = FROZEN / "thresholds.json"
    pipeline = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "d2": d2, "levels": levels, "tolerance_c": tolerance,
        "files": {name: str(path.relative_to(T.ROOT)) for name, path in files.items()},
        "n_source_cases": len(cases), "thresholds": thresholds,
    }
    T.write_json(FROZEN / "pipeline.json", pipeline)
    print(json.dumps({"d2": d2, "thresholds": thresholds}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

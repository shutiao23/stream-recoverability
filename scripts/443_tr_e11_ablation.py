#!/usr/bin/env python3
"""TR-E11: which part of the design carries the gain?

Estimator ablations come from the E4 table (shrinkage, state conditioning,
simulation inputs, functional debiasing). Score ablations refit the direct
failure classifier leave-one-region-out with nested feature sets, including the
old uncertain-peak-window summaries, and read retention at 5% realised risk.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import json

import lightgbm as lgb
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.isotonic import IsotonicRegression

import wrr_tr_common as T
import wrr_tr_features as F
from stream_recoverability.seeds import plain_seed

OUT = T.OUT / "e11_ablation"
E5 = T.load_script("tr_e5_for_e11", T.ROOT / "scripts/436_tr_e5_rules.py")
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, n_jobs=2)
WINDOW = ("win_probabilistic_hidden_support", "win_hidden_support_sd", "win_hidden_support_upper90", "win_peak_start_sd_days", "win_peak_start_entropy", "win_peak_competition_margin_C", "win_direct_h30_uncertainty", "win_support_uncertainty_interaction")
GEOMETRY = ("total_missing", "missing_fraction", "n_runs", "longest_run", "warm_observed_fraction", "peak_overlap")


def feature_sets(cases: pd.DataFrame, law: pd.Series) -> dict[str, pd.DataFrame]:
    full = F.design_matrix(cases, "h30", simulation=True)
    plain = F.design_matrix(cases, "h30", simulation=False)
    window = cases[[c for c in WINDOW if c in cases]].astype(float)
    return {
        "geometry_only": cases[list(GEOMETRY)].astype(float),
        "geometry_plus_layer": pd.concat([cases[list(GEOMETRY)].astype(float), plain[[c for c in plain if c.startswith("layer_")]]], axis=1),
        "no_simulation": plain,
        "full (R7b)": full,
        "full_plus_old_window_summaries": pd.concat([full, window], axis=1),
        "full_plus_law": full.assign(law_pfail=law.to_numpy()),
    }


def fold(x: pd.DataFrame, y: pd.Series, train: np.ndarray, test: np.ndarray, seed: int) -> np.ndarray:
    model = lgb.LGBMClassifier(objective="binary", random_state=seed, **PARAMS).fit(x.iloc[train], y.iloc[train])
    return model.predict_proba(x.iloc[test])[:, 1]


def main() -> int:
    settings = T.settings()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    law = pd.read_parquet(T.OUT / "e3_recovery_law/law_predictions.parquet")
    fail = ((cases.h30__policy - cases.eval_truth_h30).abs() > settings["tolerance_c"]).astype(int)
    regions = sorted(cases.region.unique())
    sets = feature_sets(cases, law.law_pfail_050)
    scores = {}
    for k, (name, x) in enumerate(sets.items()):
        jobs = [(np.flatnonzero(cases.region.ne(r).to_numpy()), np.flatnonzero(cases.region.eq(r).to_numpy())) for r in regions]
        parts = Parallel(n_jobs=48)(delayed(fold)(x, fail, train, test, plain_seed(k, i)) for i, (train, test) in enumerate(jobs))
        score = np.empty(len(cases))
        for (train, test), values in zip(jobs, parts):
            score[test] = values
        scores[name] = score
    # Law alone, recalibrated by isotonic regression leave-one-region-out (monotone, so ranking is unchanged).
    scores["law_only"] = law.law_pfail_050.to_numpy()
    if "law_v3_pfail_050" in law:
        scores["replay_law_only"] = law.law_v3_pfail_050.to_numpy()
    scores["law_v1_only"] = law.law_v1_pfail_050.to_numpy()
    scores["daily_disagreement_only"] = cases.daily_estimator_disagreement.to_numpy()
    scores["target_disagreement_only"] = cases.estimator_disagreement.to_numpy()
    rows = []
    for population in ("deploy", "mech"):
        w = T.population_weights(cases, population).to_numpy()
        keep = (w > 0)
        base = float(np.average(fail[keep], weights=w[keep]))
        for name, score in scores.items():
            valid = keep & np.isfinite(score)
            c = E5.curve(score[valid], fail.to_numpy()[valid].astype(float), w[valid])
            c["coverage"] *= w[valid].sum() / w[keep].sum()
            brier = float(np.average((np.clip(score[valid], 0, 1) - fail.to_numpy()[valid]) ** 2, weights=w[valid])) if np.nanmax(score[valid]) <= 1 else np.nan
            rows.append({"population": population, "score": name, "retention_at_025": E5.retention_at(c, 0.025), "retention_at_050": E5.retention_at(c, 0.05), "retention_at_100": E5.retention_at(c, 0.10), "aurc": E5.aurc(c), "augrc": E5.augrc(c), "brier": brier, "base_rate": base})
    score_table = pd.DataFrame(rows)
    score_table.to_csv(OUT / "score_ablation.csv", index=False)

    # Estimator ablations from E4 and the unshrunk air regression.
    metrics = pd.read_csv(T.OUT / "e4_estimators/estimator_metrics.csv")
    pick = metrics.loc[metrics.target.eq("h30") & metrics.population.isin(["mech", "deploy"]) & metrics.stratum.isin(["all", "peak_half_hidden", "air_layer_half_hidden", "warm_anomaly_half_hidden"])]
    pick.to_csv(OUT / "estimator_ablation_from_e4.csv", index=False)
    air = cases.policy_choice.eq("air_ridge") & cases.eval_true_peak_hidden_fraction.ge(0.5)
    shrink = []
    for population in ("mech", "deploy"):
        w = T.population_weights(cases, population)
        sel = air & (w > 0) & cases.h30__air_ols.notna()
        for name, column in (("air_ridge (P0)", "h30__air_ridge"), ("air_ols (no shrinkage)", "h30__air_ols"), ("air2stream3", "h30__air2stream3")):
            s = sel & cases[column].notna()
            e = cases.loc[s, column] - cases.loc[s, "eval_truth_h30"]
            shrink.append({"population": population, "estimator": name, "n": int(s.sum()), "bias": float(np.average(e, weights=w[s])), "mae": float(np.average(e.abs(), weights=w[s])), "failure_rate": float(np.average(e.abs() > settings["tolerance_c"], weights=w[s]))})
    pd.DataFrame(shrink).to_csv(OUT / "shrinkage_ablation.csv", index=False)
    print(score_table.to_string(), flush=True)
    print(pd.DataFrame(shrink).to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""TR-E7b: the evaluation of the frozen pipeline on the sealed Australian cases.

Reads the selection, thresholds and model files recorded by the freeze
(script 438). Reports estimators, the rule comparison, the frozen admission
thresholds and the recovery law's prediction against what happened, with
network-level bootstrap intervals.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import wrr_tr_common as T
import wrr_tr_features as F
import wrr_tr_law as L
import wrr_tr_rules as R

OUT = T.OUT / "e7_sealed"
PIPELINE = T.OUT / "e2_prereg/frozen/pipeline.json"
E4 = T.load_script("tr_e4_metrics", T.ROOT / "scripts/432_tr_e4_estimators.py")
E5 = T.load_script("tr_e5_rules", T.ROOT / "scripts/436_tr_e5_rules.py")
E7 = T.load_script("tr_e7_transfer", T.ROOT / "scripts/437_tr_e7_transfer.py")


def dry_run_pipeline() -> dict:
    """Small throwaway models on source data, only to exercise the evaluation code path."""

    import lightgbm as lgb

    folder = T.SCRATCH / "sealed_dry_run" / "frozen"
    folder.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet").sample(20000, random_state=1)
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()]
    params = dict(n_estimators=20, verbose=-1, n_jobs=8)
    residual = cases.eval_truth_h30 - cases.h30__policy
    plain, simulated = F.design_matrix(cases, "h30", False), F.design_matrix(cases, "h30", True)
    levels = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
    files = {}
    joblib.dump({"model": lgb.LGBMRegressor(**params).fit(plain, residual), "columns": list(plain.columns)}, folder / "p2.joblib")
    files["P2"] = folder / "p2.joblib"
    for name, matrix in (("P5a", plain), ("P5b", simulated)):
        joblib.dump({"models": [lgb.LGBMRegressor(objective="quantile", alpha=q, **params).fit(matrix, residual) for q in levels], "levels": levels, "columns": list(matrix.columns), "simulation": name == "P5b"}, folder / f"{name}.joblib")
        files[name] = folder / f"{name}.joblib"
    for label in ("fail_P0", "fail_D2"):
        y = (residual.abs() > 0.5).astype(int)
        joblib.dump({"model": lgb.LGBMClassifier(**params).fit(simulated, y), "columns": list(simulated.columns)}, folder / f"{label}.joblib")
        files[label] = folder / f"{label}.joblib"
    thresholds = {name: {"__marginal__": 0.1, "air_ridge": 0.1, "donor_ridge": 0.1} for name in ("R7a_target_aware", "R7b_direct_D2", "R6_law", "R7b_direct_P0")}
    return {"d2": "P5b", "levels": levels, "tolerance_c": 0.5, "thresholds": thresholds, "files": {k: str(v.relative_to(T.ROOT)) for k, v in files.items()}}


def predict(cases: pd.DataFrame, pipeline: dict) -> tuple[pd.DataFrame, dict]:
    frozen = {name: joblib.load(T.ROOT / path) for name, path in pipeline["files"].items() if path.endswith(".joblib")}
    point = cases.h30__policy
    out = pd.DataFrame(index=cases.index)
    p2 = frozen["P2"]
    out["h30__P2"] = point + p2["model"].predict(F.design_matrix(cases, "h30", simulation=False)[p2["columns"]])
    for name in ("P5a", "P5b"):
        bundle = frozen[name]
        matrix = F.design_matrix(cases, "h30", simulation=bundle["simulation"])[bundle["columns"]]
        q = np.sort(np.column_stack([model.predict(matrix) for model in bundle["models"]]), axis=1)
        for level, values in zip(bundle["levels"], q.T):
            out[f"h30__{name}_q{int(level * 100):02d}"] = point + values
    probabilities = {}
    simulated = F.design_matrix(cases, "h30", simulation=True)
    for label in ("fail_P0", "fail_D2"):
        bundle = frozen[label]
        probabilities[label] = bundle["model"].predict_proba(simulated[bundle["columns"]])[:, 1]
    return out, probabilities


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-source", action="store_true", help="exercise the code on one source region with models trained there; writes to scratch only")
    args = parser.parse_args()
    global OUT
    if args.dry_run_source:
        pipeline = dry_run_pipeline()
        OUT = T.SCRATCH / "sealed_dry_run"
        OUT.mkdir(parents=True, exist_ok=True)
        cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
        cases = cases.loc[cases.region.eq("foen") | cases.region.eq("arso")].reset_index(drop=True)
        cases.to_parquet(OUT / "cases.parquet", index=False)
    else:
        pipeline = json.loads(PIPELINE.read_text())
    target = OUT / "sealed_results.json"
    settings = T.settings()
    tolerance = pipeline["tolerance_c"]
    cases = pd.read_parquet(OUT / "cases.parquet")
    n_all = len(cases)
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    oof, probabilities = predict(cases, pipeline)
    d2, levels = pipeline["d2"], tuple(pipeline["levels"])
    names = [f"q{int(level * 100):02d}" for level in levels]
    if d2 == "P3":
        d2_quantiles = cases[[f"state_h30_{n}" for n in names]].to_numpy()
    elif d2 == "P3raw":
        d2_quantiles = cases[[f"raw_h30_{n}" for n in names]].to_numpy()
    else:
        d2_quantiles = oof[[f"h30__{d2}_{n}" for n in names]].to_numpy()
    d2_point = d2_quantiles[:, list(levels).index(0.5)]
    cases["d2_point"] = d2_point
    cases["fail_P0"] = ((cases.h30__policy - cases.eval_truth_h30).abs() > tolerance).astype(int)
    cases["fail_D2"] = ((cases.d2_point - cases.eval_truth_h30).abs() > tolerance).astype(int)
    law = L.apply_law(cases, tolerance, True, "v2")
    law3 = L.apply_law(cases, tolerance, True, "v3") if "law_replay_errors" in cases else None

    # Estimators.
    table = E4.estimator_table(cases, oof, "h30")
    metrics = []
    for population in ("mech", "deploy"):
        weight = pd.Series(np.where(cases.design_family.eq("crossed" if population == "mech" else "calendar"), 1.0, 0.0), index=cases.index)
        frame = E4.metrics(cases, table, "h30", weight, tolerance)
        frame.insert(0, "population", population)
        metrics.append(frame)
    metrics = pd.concat(metrics, ignore_index=True)
    metrics.to_csv(OUT / "sealed_estimator_metrics.csv", index=False)

    # Rules and scores on the deployment population.
    features = R.mask_features(cases)
    fixed = R.fixed_rules(features, cases)
    scores = {
        **R.parametric_scores(features, cases),
        "R4_daily_disagreement": cases.daily_estimator_disagreement, "R5_h30_target_disagreement": cases.estimator_disagreement,
        "R6_recovery_law_pfail": law.law_pfail, "R7a_target_aware_pfail (D2* distribution)": pd.Series(E5.predictive_pfail(d2_quantiles, levels, d2_point, tolerance)),
        "R7b_direct_failure_probability (P0)": pd.Series(probabilities["fail_P0"]), "R7b_direct_failure_probability (D2*)": pd.Series(probabilities["fail_D2"]),
    }
    if law3 is not None:
        scores["R6b_replay_law_pfail"] = law3.law_pfail
    delivered = {"P0": cases.h30__policy, "Pobs": cases.h30__observed_days, "D2*": cases.d2_point}
    rows = []
    for population, family in (("deploy", "calendar"), ("mech", "crossed")):
        weight = np.where(cases.design_family.eq(family), 1.0, 0.0)
        frame, curves = E5.evaluate(cases, scores, fixed, delivered, weight, tolerance, settings["risk_levels"])
        frame.insert(0, "population", population)
        rows.append(frame)
        curves.insert(0, "population", population)
        curves.to_parquet(OUT / f"sealed_curves_{population}.parquet", index=False)
    rule_table = pd.concat(rows, ignore_index=True)
    rule_table.to_csv(OUT / "sealed_risk_retention.csv", index=False)
    current = list(fixed) + ["R1_annual_missing_fraction", "R2_warm_missing_fraction", "R3_observed_lower_bound (NRFA-type)"]
    deploy_weight = np.where(cases.design_family.eq("calendar"), 1.0, 0.0)
    gain = E5.endpoint(cases, scores, fixed, delivered, deploy_weight, tolerance, current, "P0", "D2*", "R7a_target_aware_pfail (D2* distribution)")

    # Frozen thresholds.
    cases["layer_group"] = cases.policy_choice.where(cases.policy_choice.isin(["donor_ridge", "air_ridge"]), "other")
    score_values = {"R7a_target_aware": scores["R7a_target_aware_pfail (D2* distribution)"].to_numpy(), "R7b_direct_D2": probabilities["fail_D2"], "R6_law": law.law_pfail.to_numpy(), "R7b_direct_P0": probabilities["fail_P0"]}
    labels = {"R7a_target_aware": "fail_D2", "R7b_direct_D2": "fail_D2", "R6_law": "fail_P0", "R7b_direct_P0": "fail_P0"}
    threshold_rows = []
    for population, family in (("deploy", "calendar"), ("mech", "crossed")):
        block = cases.loc[cases.design_family.eq(family)].copy()
        for name, values in score_values.items():
            block["score"] = values[cases.design_family.eq(family).to_numpy()]
            for method, mondrian in (("marginal", False), ("mondrian_layer", True)):
                accept = E7.apply(block, "score", pipeline["thresholds"][name], mondrian)
                f = block[labels[name]].to_numpy()
                frame = pd.DataFrame({"independence_group": block.independence_group.to_numpy(), "a": accept, "f": f})

                def risk_of(sample: pd.DataFrame) -> float:
                    admitted = sample.loc[sample.a]
                    return float(admitted.f.mean()) if len(admitted) else np.nan

                boot = T.group_bootstrap(frame, "independence_group", risk_of, settings["bootstrap_draws"], settings["seed"])
                threshold_rows.append({
                    "population": population, "score": name, "method": method, "n_cases": len(block), "n_groups": int(block.independence_group.nunique()),
                    "retention": float(accept.mean()), "risk": risk_of(frame), "risk_lower95": float(np.nanquantile(boot, 0.025)), "risk_upper95": float(np.nanquantile(boot, 0.975)),
                    "unscreened_risk": float(f.mean()),
                })
    thresholds = pd.DataFrame(threshold_rows)
    thresholds.to_csv(OUT / "sealed_frozen_thresholds.csv", index=False)

    hidden = cases.eval_true_peak_hidden_fraction.ge(0.5)
    stratum = cases.design_family.eq("crossed") & cases.policy_choice.eq("air_ridge") & hidden
    bias0 = float((cases.h30__policy - cases.eval_truth_h30)[stratum].mean())
    bias2 = float((cases.d2_point - cases.eval_truth_h30)[stratum].mean())
    lower = np.array([np.interp(0.05, levels, row) for row in d2_quantiles[stratum.to_numpy()]])
    upper = np.array([np.interp(0.95, levels, row) for row in d2_quantiles[stratum.to_numpy()]])
    truth = cases.eval_truth_h30.to_numpy()[stratum.to_numpy()]
    main_threshold = thresholds.loc[(thresholds.population == "deploy") & (thresholds.score == "R7a_target_aware") & (thresholds.method == "mondrian_layer")].iloc[0]
    result = {
        "evaluated_utc": datetime.now(timezone.utc).isoformat(), "d2": d2, "n_cases_built": n_all, "n_cases": len(cases),
        "n_station_years": int(cases[["station_key", "year"]].drop_duplicates().shape[0]), "n_stations": int(cases.station_key.nunique()), "n_networks": int(cases.independence_group.nunique()),
        "layer_shares": cases.policy_choice.value_counts(normalize=True).to_dict(),
        "P1_air_half_hidden": {"n": int(stratum.sum()), "bias_P0": bias0, "bias_D2": bias2, "reduction": float(1 - abs(bias2) / abs(bias0)) if bias0 else None, "coverage90": float(np.mean((truth >= lower) & (truth <= upper))) if len(truth) else None},
        "P2_retention_gain_at_5pct_deploy": gain,
        "P3_frozen_mondrian_realised_risk_deploy": float(main_threshold.risk), "P3_risk_upper95": float(main_threshold.risk_upper95), "P3_retention": float(main_threshold.retention),
        "P3_mech_realised_risk": float(thresholds.loc[(thresholds.population == "mech") & (thresholds.score == "R7a_target_aware") & (thresholds.method == "mondrian_layer"), "risk"].iloc[0]),
        "P3_sealed_success": bool(main_threshold.risk <= 0.07 and thresholds.loc[(thresholds.population == "mech") & (thresholds.score == "R7a_target_aware") & (thresholds.method == "mondrian_layer"), "risk"].iloc[0] <= 0.07),
        "law_predicted_failure_rate_deploy": float(law.law_pfail[cases.design_family.eq("calendar")].mean()),
        "observed_P0_failure_rate_deploy": float(cases.fail_P0[cases.design_family.eq("calendar")].mean()),
        "law_predicted_failure_rate_mech": float(law.law_pfail[cases.design_family.eq("crossed")].mean()),
        "observed_P0_failure_rate_mech": float(cases.fail_P0[cases.design_family.eq("crossed")].mean()),
    }
    T.write_json(target, result)
    print(json.dumps(result, indent=2), flush=True)
    print(thresholds.to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""TR2: candidate final models for the round-2 freeze, and the Australian development check.

Fits on every round-2 source case: the P5b quantile models of the H30 plug-in
error (D2*), and the direct failure classifier (R7b) of the conformally
calibrated D2* median. The bundle also carries the conformal offsets by
difficulty group (script 451) and the expected-risk factor k (script 453).
``apply_bundle`` turns any case table into calibrated D2* quantiles, R7a, R7b
and expected-risk admissions; with ``--au-check`` it is applied to the opened
Australian development cases.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

import wrr_tr_common as T
import wrr_tr_features as F

BUNDLE = T.OUT / "e2_prereg" / "candidate_bundle"
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, n_jobs=32)
CQR = T.load_script("tr2_cqr_for_bundle", T.ROOT / "scripts/451_tr2_cqr.py")
E5 = T.load_script("tr2_e5_for_bundle", T.ROOT / "scripts/436_tr_e5_rules.py")
RULE = T.load_script("tr2_rule_for_bundle", T.ROOT / "scripts/453_tr2_expected_risk.py")


def source_cases() -> pd.DataFrame:
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    return cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)


def build() -> dict:
    settings = T.settings()
    cases = source_cases()
    calibrated = pd.read_parquet(T.OUT / "e4_estimators/oof_calibrated.parquet")
    if not (calibrated.realization_id.to_numpy() == cases.realization_id.to_numpy()).all():
        raise RuntimeError("Calibrated quantiles are not aligned with the cases")
    BUNDLE.mkdir(parents=True, exist_ok=True)
    residual = cases.eval_truth_h30 - cases.h30__policy
    simulated = F.design_matrix(cases, "h30", simulation=True)
    models = [lgb.LGBMRegressor(objective="quantile", alpha=level, random_state=settings["seed"], **PARAMS).fit(simulated, residual) for level in F.QUANTILES]
    joblib.dump({"models": models, "levels": list(F.QUANTILES), "columns": list(simulated.columns)}, BUNDLE / "p5b_quantiles.joblib")
    fail = ((calibrated.h30__D2c_q50 - cases.eval_truth_h30).abs() > settings["tolerance_c"]).astype(int)
    classifier = lgb.LGBMClassifier(objective="binary", random_state=settings["seed"], **PARAMS).fit(simulated, fail)
    joblib.dump({"model": classifier, "columns": list(simulated.columns), "label": "fail of the calibrated D2* median"}, BUNDLE / "r7b_classifier.joblib")
    offsets = json.loads((T.OUT / "e4_estimators/conformal_offsets.json").read_text())
    rule = json.loads((T.OUT / "e7_transfer/expected_risk_rule.json").read_text())
    meta = {
        "levels": list(F.QUANTILES), "tolerance_c": settings["tolerance_c"], "conformal": offsets,
        "expected_risk": {"alpha": rule["alpha"], "factor_k": rule["final_factor_k"], "primary_score": rule["primary_score"]},
        "n_source_cases": len(cases), "season_mode": T.SEASON_MODE, "rule_reference_peak_doy": settings["rule_reference_peak_doy"],
    }
    T.write_json(BUNDLE / "bundle.json", meta)
    return meta


def apply_bundle(cases: pd.DataFrame, bundle_dir: Path = BUNDLE) -> pd.DataFrame:
    """Calibrated D2* quantiles, R7a, R7b and expected-risk admissions for a case table (no labels used)."""

    meta = json.loads((bundle_dir / "bundle.json").read_text())
    quantile_bundle = joblib.load(bundle_dir / "p5b_quantiles.joblib")
    classifier = joblib.load(bundle_dir / "r7b_classifier.joblib")
    simulated = F.design_matrix(cases, "h30", simulation=True)
    raw = np.sort(np.column_stack([model.predict(simulated[quantile_bundle["columns"]]) for model in quantile_bundle["models"]]), axis=1) + cases.h30__policy.to_numpy()[:, None]
    settings = T.settings()
    groups = CQR.difficulty_groups(cases, settings)
    known = meta["conformal"]["groups"]
    groups = groups.where(groups.isin(list(known)), groups.str.replace("|other", "|air_ridge", regex=False))
    shift = np.vstack([known[g] for g in groups])
    calibrated = np.sort(raw + shift, axis=1)
    levels = tuple(meta["levels"])
    out = pd.DataFrame(index=cases.index)
    for level, values in zip(levels, calibrated.T):
        out[f"d2_q{int(level * 100):02d}"] = values
    out["d2_point"] = calibrated[:, levels.index(0.5)]
    out["difficulty_group"] = groups.to_numpy()
    out["R7a"] = E5.predictive_pfail(calibrated, levels, out.d2_point.to_numpy(), meta["tolerance_c"])
    out["R7b"] = classifier["model"].predict_proba(simulated[classifier["columns"]])[:, 1]
    return out


def expected_risk_admission(scores: np.ndarray, weight: np.ndarray, alpha: float, factor: float) -> np.ndarray:
    return RULE.admit(scores, weight, alpha, factor) & (weight > 0)


def au_check() -> dict:
    """Opened Australian development cases: does the label-free rule hold at a high base failure rate?"""

    meta = json.loads((BUNDLE / "bundle.json").read_text())
    cases = pd.read_parquet(T.OUT / "e7_au_development/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    scored = apply_bundle(cases)
    tolerance = meta["tolerance_c"]
    fail_d2 = ((scored.d2_point - cases.eval_truth_h30).abs() > tolerance).astype(float).to_numpy()
    fail_p0 = ((cases.h30__policy - cases.eval_truth_h30).abs() > tolerance).astype(float).to_numpy()
    rows = []
    for population, family in (("deploy", "calendar"), ("mech", "crossed")):
        weight = cases.design_family.eq(family).to_numpy().astype(float)
        for name in ("R7b", "R7a"):
            for factor_label, factor in (("k1", 1.0), ("k", meta["expected_risk"]["factor_k"][name])):
                accept = expected_risk_admission(scored[name].to_numpy(), weight, meta["expected_risk"]["alpha"], factor)
                frame = pd.DataFrame({"g": cases.independence_group, "a": accept, "f": fail_d2})
                frame = frame.loc[weight > 0]
                boot = T.group_bootstrap(frame, "g", lambda f: float(f.loc[f.a, "f"].mean()) if f.a.any() else np.nan, 1000, 7)
                rows.append({
                    "population": population, "score": name, "factor": factor_label, "factor_value": factor, "retention": float(accept[weight > 0].mean()),
                    "risk": float(fail_d2[accept].mean()) if accept.any() else np.nan, "risk_upper95": float(np.nanquantile(boot, 0.975)),
                    "unscreened_risk_D2": float(fail_d2[weight > 0].mean()), "unscreened_risk_P0": float(fail_p0[weight > 0].mean()),
                })
    table = pd.DataFrame(rows)
    hidden = cases.eval_true_peak_hidden_fraction.ge(0.5)
    stratum = cases.design_family.eq("crossed") & cases.policy_choice.eq("air_ridge") & hidden
    covered = (cases.eval_truth_h30 >= scored.d2_q05) & (cases.eval_truth_h30 <= scored.d2_q95)
    coverage = covered.groupby([cases.design_family, scored.difficulty_group]).agg(["mean", "size"]).reset_index()
    out = T.OUT / "e7_au_development"
    table.to_csv(out / "development_check.csv", index=False)
    coverage.to_csv(out / "development_coverage.csv", index=False)
    summary = {
        "role": "development region (Australia was the round-1 test region); not a validation",
        "n_cases": len(cases), "n_station_years": int(cases[["station_key", "year"]].drop_duplicates().shape[0]), "n_networks": int(cases.independence_group.nunique()),
        "window_at_year_edge_share": float(cases.drop_duplicates(["station_key", "year"]).eval_truth_window_at_year_edge.mean()),
        "P1_bias_P0": float((cases.h30__policy - cases.eval_truth_h30)[stratum].mean()), "P1_bias_D2": float((scored.d2_point - cases.eval_truth_h30)[stratum].mean()),
        "P1_coverage90": float(covered[stratum].mean()), "mech_coverage90": float(covered[cases.design_family.eq("crossed")].mean()),
        "hardest_bin_coverage90_mech": float(covered[cases.design_family.eq("crossed") & scored.difficulty_group.str.startswith("bin4")].mean()),
        "rule": table.to_dict("records"),
    }
    summary["P1_reduction"] = float(1 - abs(summary["P1_bias_D2"]) / abs(summary["P1_bias_P0"])) if summary["P1_bias_P0"] else None
    T.write_json(out / "development_check.json", summary)
    print(table.round(4).to_string(), flush=True)
    print({k: v for k, v in summary.items() if k != "rule"}, flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--au-check", action="store_true")
    args = parser.parse_args()
    if not args.au_check:
        meta = build()
        print(json.dumps({k: v for k, v in meta.items() if k != "conformal"}, indent=2), flush=True)
    else:
        au_check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

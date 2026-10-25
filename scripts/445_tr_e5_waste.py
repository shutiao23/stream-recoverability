#!/usr/bin/env python3
"""TR-E5b (exploratory): what each published rule throws away, and the risk at its retention.

For every fixed completeness rule on the deployment population: the share of
rejected incomplete years whose H30 would have been within tolerance with the
plug-in or with D2*, and the realised risk of the target-aware rule at exactly
the rule's retention.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import wrr_tr_common as T

OUT = T.OUT / "e5_rules"
E5 = T.load_script("tr_e5_for_waste", T.ROOT / "scripts/436_tr_e5_rules.py")


def risk_at_retention(score: np.ndarray, fail: np.ndarray, weight: np.ndarray, retention: float) -> float:
    """Risk at a given retention; tied scores are admitted in random order (linear interpolation)."""

    c = E5.curve(score, fail, weight)
    coverage = np.r_[0.0, c.coverage.to_numpy()]
    failures = np.r_[0.0, (c.coverage * c.risk).to_numpy()]
    return float(np.interp(retention, coverage, failures) / retention)


def main() -> int:
    settings = T.settings()
    tolerance = settings["tolerance_c"]
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    oof = pd.read_parquet(T.OUT / "e4_estimators/oof_predictions.parquet")
    scores = pd.read_parquet(OUT / "scores.parquet")
    # The delivered D2* (round 2: conformally calibrated quantiles).
    _, _, d2_point, _ = E5.d2_distribution(cases, oof)
    d2_point = pd.Series(d2_point, index=cases.index)
    fail = {
        "P0": ((cases.h30__policy - cases.eval_truth_h30).abs() > tolerance).to_numpy(),
        "Pobs": (~np.isfinite(cases.h30__observed_days) | ((cases.h30__observed_days - cases.eval_truth_h30).abs() > tolerance)).to_numpy(),
        "D2*": ((d2_point - cases.eval_truth_h30).abs() > tolerance).to_numpy(),
    }
    target_score = scores["score::R7a_target_aware_pfail (D2* distribution)"].to_numpy()
    rows = []
    for population in ("deploy", "mnar1", "mech"):
        w = T.population_weights(cases, population).to_numpy()
        keep = w > 0
        for column in [c for c in scores if c.startswith("rule::")]:
            accept = scores[column].to_numpy().astype(bool)
            rejected = keep & ~accept
            accepted = keep & accept
            retention = float(w[accepted].sum() / w[keep].sum())
            rows.append({
                "population": population, "rule": column.replace("rule::", ""), "retention": retention,
                "risk_rule_Pobs": float(np.average(fail["Pobs"][accepted], weights=w[accepted])) if accepted.any() else np.nan,
                "risk_rule_P0": float(np.average(fail["P0"][accepted], weights=w[accepted])) if accepted.any() else np.nan,
                "rejected_share_usable_P0": float(np.average(~fail["P0"][rejected], weights=w[rejected])) if rejected.any() else np.nan,
                "rejected_share_usable_D2": float(np.average(~fail["D2*"][rejected], weights=w[rejected])) if rejected.any() else np.nan,
                "target_aware_risk_at_same_retention": risk_at_retention(target_score[keep], fail["D2*"][keep].astype(float), w[keep], retention) if retention > 0 else np.nan,
                "target_aware_risk_all": float(np.average(fail["D2*"][keep], weights=w[keep])),
            })
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "rule_waste.csv", index=False)
    print(table.loc[table.population.eq("deploy")].round(4).to_string(), flush=True)
    print(table.loc[table.population.eq("mech")].round(4).to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

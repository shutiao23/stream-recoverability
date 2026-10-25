#!/usr/bin/env python3
"""TR sensitivity: the preregistered tolerances 0.25 and 1.0 C beside the primary 0.5 C.

For each tolerance and population: unscreened failure rates of P0, recorded-day
values and D2*; retention at 5% realised risk of the target-aware score
(recomputed for the tolerance from the D2* quantiles) and of the best fixed rule;
and the P1 bias stratum is unchanged because bias does not depend on tolerance.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import wrr_tr_common as T
import wrr_tr_rules as R

OUT = T.OUT / "e5_rules"
E5 = T.load_script("tr_e5_for_tolerance", T.ROOT / "scripts/436_tr_e5_rules.py")


def main() -> int:
    settings = T.settings()
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    oof = pd.read_parquet(T.OUT / "e4_estimators/oof_predictions.parquet")
    _, levels, point, q = E5.d2_distribution(cases, oof)
    features = R.mask_features(cases)
    fixed = R.fixed_rules(features, cases)
    truth = cases.eval_truth_h30.to_numpy()
    rows = []
    for tolerance in settings["tolerance_sensitivity_c"]:
        score = E5.predictive_pfail(q, levels, point, tolerance)
        fail = {
            "P0": np.abs(cases.h30__policy.to_numpy() - truth) > tolerance,
            "Pobs": ~np.isfinite(cases.h30__observed_days.to_numpy()) | (np.abs(cases.h30__observed_days.to_numpy() - truth) > tolerance),
            "D2*": np.abs(point - truth) > tolerance,
        }
        for population in ("deploy", "mech"):
            w = T.population_weights(cases, population).to_numpy()
            keep = w > 0
            row = {"tolerance_c": tolerance, "population": population}
            for name, f in fail.items():
                row[f"unscreened_risk_{name}"] = float(np.average(f[keep], weights=w[keep]))
            for level in settings["risk_levels"]:
                c = E5.curve(score[keep], fail["D2*"][keep].astype(float), w[keep])
                row[f"target_aware_retention_at_{int(level * 1000):03d}"] = E5.retention_at(c, level)
                best = 0.0
                for name, accept in fixed.items():
                    a = accept.to_numpy() & keep
                    for value in ("P0", "Pobs"):
                        if a.any() and np.average(fail[value][a], weights=w[a]) <= level:
                            best = max(best, float(w[a].sum() / w[keep].sum()))
                row[f"best_fixed_rule_retention_at_{int(level * 1000):03d}"] = best
            rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "tolerance_sensitivity.csv", index=False)
    print(table.round(3).to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

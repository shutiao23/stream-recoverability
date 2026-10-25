#!/usr/bin/env python3
"""TR-E6: is a record's usability a property of the record or of the target?

For six annual targets with preregistered tolerances: agreement of usability
between targets (Cohen's kappa, Spearman of absolute errors), the false
acceptance and false rejection of each completeness rule per target, and the
retention at 5% realised risk of the best rule against a target-aware score
built from that target's own predictive distribution.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import json
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import wrr_tr_common as T
import wrr_tr_rules as R

OUT = T.OUT / "e6_multitarget"
E5 = T.load_script("tr_e5_for_e6", T.ROOT / "scripts/436_tr_e5_rules.py")
TARGETS = ("h30", "h7", "annual_mean", "c30", T.DEGREE_DAYS, "days_above_20")


def kappa(a: np.ndarray, b: np.ndarray, w: np.ndarray) -> float:
    po = np.average(a == b, weights=w)
    pa, pb = np.average(a, weights=w), np.average(b, weights=w)
    pe = pa * pb + (1 - pa) * (1 - pb)
    return float((po - pe) / (1 - pe)) if pe < 1 else np.nan


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tolerance = T.target_tolerances()
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    oof = pd.read_parquet(T.OUT / "e4_estimators/oof_predictions.parquet")
    d2 = json.loads((T.OUT / "e4_estimators/d2_selection.json").read_text())["d2"]
    family = d2 if d2 in ("P5a", "P5b") else "P5b"
    errors, d2_errors, pfail = {}, {}, {}
    for target in TARGETS:
        truth = cases[f"eval_truth_{target}"]
        errors[target] = (cases[f"{target}__policy"] - truth).to_numpy()
        levels = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95) if target == "h30" else (0.05, 0.25, 0.5, 0.75, 0.95)
        q = oof[[f"{target}__{family}_q{int(level * 100):02d}" for level in levels]].to_numpy()
        if target == "h30":
            # H30 uses the delivered D2* (round 2: conformally calibrated); other targets keep P5b.
            _, levels, _, q = E5.d2_distribution(cases, oof)
        point = q[:, list(levels).index(0.5)]
        d2_errors[target] = point - truth.to_numpy()
        pfail[target] = E5.predictive_pfail(q, levels, point, tolerance[target])
    features = R.mask_features(cases)
    fixed = R.fixed_rules(features, cases)
    rows_agree, rows_rule, rows_frontier = [], [], []
    for population in ("deploy", "mech"):
        w = T.population_weights(cases, population).to_numpy()
        keep = w > 0
        fail = {t: (np.abs(errors[t]) > tolerance[t]) for t in TARGETS}
        for a, b in combinations(TARGETS, 2):
            rho = spearmanr(np.abs(errors[a][keep]), np.abs(errors[b][keep])).statistic
            rows_agree.append({
                "population": population, "target_a": a, "target_b": b, "kappa_usable": kappa(~fail[a][keep], ~fail[b][keep], w[keep]),
                "spearman_abs_error": float(rho), "share_unusable_a_usable_b": float(np.average(fail[a][keep] & ~fail[b][keep], weights=w[keep])),
                "share_usable_a_unusable_b": float(np.average(~fail[a][keep] & fail[b][keep], weights=w[keep])),
            })
        for target in TARGETS:
            f = fail[target]
            rows_rule.append({"population": population, "target": target, "rule": "none (reconstruct all)", "retention": 1.0, "risk": float(np.average(f[keep], weights=w[keep])), "false_acceptance": float(np.average(f[keep], weights=w[keep])), "false_rejection": 0.0})
            for name, accept in fixed.items():
                acc = accept.to_numpy()
                rows_rule.append({
                    "population": population, "target": target, "rule": name, "retention": float(np.average(acc[keep], weights=w[keep])),
                    "risk": float(np.average(f[keep & acc], weights=w[keep & acc])) if (keep & acc).any() else np.nan,
                    "false_acceptance": float(np.average((acc & f)[keep], weights=w[keep])), "false_rejection": float(np.average((~acc & ~f)[keep], weights=w[keep])),
                })
            # Frontier: best fixed rule (delivering P0) against the target-aware score (delivering the target's distribution median).
            best = 0.0
            for name, accept in fixed.items():
                acc = accept.to_numpy() & keep
                if acc.any() and np.average(f[acc], weights=w[acc]) <= 0.05:
                    best = max(best, float(w[acc].sum() / w[keep].sum()))
            fd = (np.abs(d2_errors[target]) > tolerance[target]).astype(float)
            c = E5.curve(pfail[target][keep], fd[keep], w[keep])
            target_aware = E5.retention_at(c, 0.05)
            c0 = E5.curve(pfail[target][keep], f[keep].astype(float), w[keep])
            rows_frontier.append({"population": population, "target": target, "tolerance": tolerance[target], "unscreened_risk_P0": float(np.average(f[keep], weights=w[keep])), "unscreened_risk_D2": float(np.average(fd[keep], weights=w[keep])), "best_rule_retention_at_5pct": best, "target_aware_retention_at_5pct": target_aware, "target_aware_score_on_P0_retention_at_5pct": E5.retention_at(c0, 0.05)})
    # Does the H30 score transfer to other targets? Use the H30 target-aware score to admit records for each target.
    for population in ("deploy", "mech"):
        w = T.population_weights(cases, population).to_numpy()
        keep = w > 0
        for target in TARGETS:
            fd = (np.abs(d2_errors[target]) > tolerance[target]).astype(float)
            c = E5.curve(pfail["h30"][keep], fd[keep], w[keep])
            rows_frontier.append({"population": f"{population}|scored_by_h30", "target": target, "tolerance": tolerance[target], "target_aware_retention_at_5pct": E5.retention_at(c, 0.05)})
    pd.DataFrame(rows_agree).to_csv(OUT / "target_agreement.csv", index=False)
    pd.DataFrame(rows_rule).to_csv(OUT / "rule_misjudgement_by_target.csv", index=False)
    frontier = pd.DataFrame(rows_frontier)
    frontier.to_csv(OUT / "target_frontier.csv", index=False)
    print(pd.DataFrame(rows_agree).loc[lambda f: f.population.eq("deploy")].to_string(), flush=True)
    print(frontier.to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

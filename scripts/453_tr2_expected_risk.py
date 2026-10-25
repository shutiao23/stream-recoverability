#!/usr/bin/env python3
"""TR2-M3: the label-free expected-risk threshold, developed leave-one-region-out.

In a region the cases are admitted in increasing order of their predicted
failure probability while the mean of k times the predicted probability among
admitted cases stays at or below alpha = 5%. No label of the region is used.
The conservative factor k is the 80th percentile, over the other regions, of
the ratio between realised and predicted risk at k = 1 (so k for region r never
uses region r). The direct failure classifier (R7b, D2* value) is the primary
score; the D2* predictive failure probability (R7a, conformally calibrated) is
reported beside it. Australia (round-2 definitions) is an opened development
region scored by the candidate final models (script 455) when they exist.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import wrr_tr_common as T

OUT = T.OUT / "e7_transfer"
SCORES = {"R7b": ("score::R7b_direct_failure_probability (D2*)", "fail_D2"), "R7a": ("score::R7a_target_aware_pfail (D2* distribution)", "fail_D2")}


def admit(score: np.ndarray, weight: np.ndarray, alpha: float, factor: float) -> np.ndarray:
    """Largest prefix (by increasing score) whose weighted mean of factor * score is at most alpha."""

    order = np.argsort(score, kind="mergesort")
    s, w = score[order], weight[order]
    expected = np.cumsum(w * factor * s) / np.maximum(np.cumsum(w), 1e-12)
    last = np.r_[s[1:] != s[:-1], True]
    ok = np.flatnonzero(last & (expected <= alpha))
    threshold = s[ok[-1]] if len(ok) else -np.inf
    return score <= threshold


def region_result(score: np.ndarray, fail: np.ndarray, weight: np.ndarray, alpha: float, factor: float) -> dict:
    accept = admit(score, weight, alpha, factor) & (weight > 0)
    w = weight
    return {
        "retention": float(w[accept].sum() / w[w > 0].sum()) if (w > 0).any() else np.nan,
        "risk": float(np.average(fail[accept], weights=w[accept])) if w[accept].sum() > 0 else np.nan,
        "predicted": float(np.average(score[accept], weights=w[accept])) if w[accept].sum() > 0 else np.nan,
        "unscreened_risk": float(np.average(fail[w > 0], weights=w[w > 0])) if (w > 0).any() else np.nan,
        "n_cases": int((w > 0).sum()),
    }


def source_development(alpha: float, quantile: float) -> tuple[pd.DataFrame, dict]:
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    scores = pd.read_parquet(T.OUT / "e5_rules/scores.parquet")
    calibrated = pd.read_parquet(T.OUT / "e4_estimators/oof_calibrated.parquet")
    if not (scores.realization_id.to_numpy() == cases.realization_id.to_numpy()).all():
        raise RuntimeError("Scores are not aligned with cases")
    cases["fail_D2"] = ((calibrated.h30__D2c_q50 - cases.eval_truth_h30).abs() > T.settings()["tolerance_c"]).astype(int)
    eligible = cases.groupby("region").independence_group.nunique()
    regions = sorted(eligible.index[eligible >= T.settings()["region_min_blocks"]])
    rows = []
    for population in ("mech", "deploy"):
        weight_all = T.population_weights(cases, population).to_numpy()
        for name, (column, label) in SCORES.items():
            score_all = scores[column].to_numpy(dtype=float)
            fail_all = cases[label].to_numpy(dtype=float)
            base = {}
            for region in regions:
                held = cases.region.eq(region).to_numpy() & (weight_all > 0) & np.isfinite(score_all)
                base[region] = region_result(score_all[held], fail_all[held], weight_all[held], alpha, 1.0)
            ratios = {r: v["risk"] / v["predicted"] for r, v in base.items() if v["predicted"] and v["predicted"] > 0 and np.isfinite(v["risk"])}
            for region in regions:
                others = [ratio for r, ratio in ratios.items() if r != region]
                factor = max(1.0, float(np.quantile(others, quantile))) if others else 1.0
                held = cases.region.eq(region).to_numpy() & (weight_all > 0) & np.isfinite(score_all)
                result = region_result(score_all[held], fail_all[held], weight_all[held], alpha, factor)
                rows.append({"population": population, "score": name, "region": region, "factor_k": factor, "k1_risk": base[region]["risk"], "k1_retention": base[region]["retention"], "k1_predicted": base[region]["predicted"], **result, "n_groups": int(cases.loc[held, "independence_group"].nunique())})
    table = pd.DataFrame(rows)
    final = {}
    for name in SCORES:
        mech = table.loc[(table.population == "mech") & (table.score == name)]
        ratios = (mech.k1_risk / mech.k1_predicted).replace([np.inf, -np.inf], np.nan).dropna()
        final[name] = max(1.0, float(np.quantile(ratios, quantile)))
    return table, final


def main() -> int:
    settings = T.settings()
    alpha, quantile = settings["expected_risk_alpha"], settings["expected_risk_factor_quantile"]
    table, factors = source_development(alpha, quantile)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "expected_risk_development.csv", index=False)
    summary_rows = []
    for (population, score), block in table.groupby(["population", "score"]):
        summary_rows.append({
            "population": population, "score": score, "n_regions": len(block), "share_risk_le_7pct": float((block.risk <= 0.07).mean()),
            "median_risk": float(block.risk.median()), "worst_region_risk": float(block.risk.max()), "median_retention": float(block.retention.median()),
            "k1_share_risk_le_7pct": float((block.k1_risk <= 0.07).mean()), "k1_median_risk": float(block.k1_risk.median()), "k1_worst_region_risk": float(block.k1_risk.max()),
        })
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / "expected_risk_development_summary.csv", index=False)
    payload = {"alpha": alpha, "factor_quantile": quantile, "final_factor_k": factors, "primary_score": "R7b", "summary": summary.to_dict("records")}
    T.write_json(OUT / "expected_risk_rule.json", payload)
    print(summary.round(4).to_string(), flush=True)
    print({"final_factor_k": factors}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

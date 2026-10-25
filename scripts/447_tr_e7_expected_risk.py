#!/usr/bin/env python3
"""TR-E7d: a label-free threshold set from the score's own expected risk in the new region.

If a failure probability stays calibrated across regions, the admitted risk at
threshold t is about the mean score among admitted cases, which needs no label
from the new region. The threshold is the largest t with that mean <= alpha.
Source leave-one-region-out is the development test; Australia is reported
post hoc, because the rule was formulated after the sealed evaluation.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import wrr_tr_common as T

OUT = T.OUT / "e7_transfer"
DIAG = T.load_script("tr_diag_for_e7d", T.ROOT / "scripts/446_tr_sealed_diagnostics.py")
ALPHA = 0.05


def expected_risk_threshold(score: np.ndarray, weight: np.ndarray, alpha: float) -> float:
    order = np.argsort(score, kind="mergesort")
    s, w = score[order], weight[order]
    expected = np.cumsum(w * s) / np.maximum(np.cumsum(w), 1e-12)
    last = np.r_[s[1:] != s[:-1], True]
    ok = np.flatnonzero(last & (expected <= alpha))
    return float(s[ok[-1]]) if len(ok) else -np.inf


def evaluate(frame: pd.DataFrame, score: str, label: str, weight: np.ndarray) -> dict:
    t = expected_risk_threshold(frame[score].to_numpy(), weight, ALPHA)
    accept = frame[score].to_numpy() <= t
    fail = frame[label].to_numpy().astype(float)
    w = weight
    return {
        "threshold": t, "retention": float(w[accept].sum() / w.sum()), "risk": float(np.average(fail[accept], weights=w[accept])) if accept.any() else np.nan,
        "expected_risk": float(np.average(frame[score].to_numpy()[accept], weights=w[accept])) if accept.any() else np.nan,
        "unscreened_risk": float(np.average(fail, weights=w)), "n_groups": int(frame.independence_group.nunique()),
    }


def main() -> int:
    settings = T.settings()
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    scores = pd.read_parquet(T.OUT / "e5_rules/scores.parquet")
    oof = pd.read_parquet(T.OUT / "e4_estimators/oof_predictions.parquet")
    d2 = json.loads((T.OUT / "e4_estimators/d2_selection.json").read_text())["d2"]
    cases["fail_D2"] = ((oof[f"h30__{d2}_q50"] - cases.eval_truth_h30).abs() > settings["tolerance_c"]).astype(int)
    cases["fail_P0"] = ((cases.h30__policy - cases.eval_truth_h30).abs() > settings["tolerance_c"]).astype(int)
    cases["R7a"] = scores["score::R7a_target_aware_pfail (D2* distribution)"].to_numpy()
    cases["R7b"] = scores["score::R7b_direct_failure_probability (D2*)"].to_numpy()
    cases["R6"] = scores["score::R6_recovery_law_pfail"].to_numpy()
    eligible = cases.groupby("region").independence_group.nunique()
    regions = sorted(eligible.index[eligible >= settings["region_min_blocks"]])
    rows = []
    for population in ("deploy", "mech"):
        weight = T.population_weights(cases, population)
        for region in regions:
            selected = cases.region.eq(region) & (weight > 0)
            frame = cases.loc[selected]
            for score, label in (("R7a", "fail_D2"), ("R7b", "fail_D2"), ("R6", "fail_P0")):
                rows.append({"domain": "source_loro", "population": population, "region": region, "score": score, **evaluate(frame, score, label, weight[selected].to_numpy())})
    pipeline = json.loads(DIAG.SEALED.PIPELINE.read_text())
    au = DIAG.prepare(T.OUT / "e7_sealed/cases.parquet", pipeline)
    _, probabilities = DIAG.SEALED.predict(au, pipeline)
    au["R7b"] = probabilities["fail_D2"]
    au = au.rename(columns={"score": "R7a"})
    for population, family in (("deploy", "calendar"), ("mech", "crossed")):
        frame = au.loc[au.design_family.eq(family)]
        for score in ("R7a", "R7b"):
            rows.append({"domain": "australia_post_hoc", "population": population, "region": "bom", "score": score, **evaluate(frame, score, "fail_D2", np.ones(len(frame)))})
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "expected_risk_threshold.csv", index=False)
    summary = table.loc[table.domain.eq("source_loro")].groupby(["population", "score"]).agg(
        n_regions=("region", "size"), share_risk_le_7pct=("risk", lambda s: float((s <= 0.07).mean())), median_risk=("risk", "median"), max_risk=("risk", "max"), median_retention=("retention", "median"),
    ).reset_index()
    summary.to_csv(OUT / "expected_risk_threshold_summary.csv", index=False)
    print(summary.round(4).to_string(), flush=True)
    print(table.loc[table.domain.eq("australia_post_hoc")].round(4).to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

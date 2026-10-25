#!/usr/bin/env python3
"""TR-E5: target-aware applicability against the completeness rules people use.

Every rule and score is placed on one risk-retention plane per population.
Point rules give one point; scores give a curve. Retention is compared at equal
realised risk (2.5, 5, 10 percent), with AURC, AUGRC, partial area below 5%,
group-equal and worst-group risk, and the share of the oracle gap closed.
The delivered value is crossed with the rule: P0, observed days or D2*.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import json

import lightgbm as lgb
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_tr_common as T
import wrr_tr_features as F
import wrr_tr_rules as R
from stream_recoverability.seeds import plain_seed

OUT = T.OUT / "e5_rules"
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, n_jobs=2)


def d2_selection() -> dict:
    return json.loads((T.OUT / "e4_estimators/d2_selection.json").read_text())


def d2_distribution(cases: pd.DataFrame, oof: pd.DataFrame) -> tuple[str, tuple[float, ...], np.ndarray, np.ndarray]:
    """The delivered D2* distribution: round 2 uses the conformally calibrated quantiles (script 451)."""

    calibrated = T.OUT / "e4_estimators/oof_calibrated.parquet"
    if T.SEASON_MODE == "hot_year" and calibrated.exists():
        frame = pd.read_parquet(calibrated)
        if not (frame.realization_id.to_numpy() == cases.realization_id.to_numpy()).all():
            raise RuntimeError("Calibrated quantiles are not aligned with the cases")
        levels = F.QUANTILES
        quantiles = frame[[f"h30__D2c_q{int(q * 100):02d}" for q in levels]].to_numpy()
        return "P5b+conformal", levels, quantiles[:, levels.index(0.5)], quantiles
    selection = d2_selection()
    d2, levels = selection["d2"], tuple(selection["levels"])
    if d2 == "P3":
        quantiles = cases[[f"state_h30_q{int(q * 100):02d}" for q in levels]].to_numpy()
    elif d2 == "P3raw":
        quantiles = cases[[f"raw_h30_q{int(q * 100):02d}" for q in levels]].to_numpy()
    else:
        quantiles = oof[[f"h30__{d2}_q{int(q * 100):02d}" for q in levels]].to_numpy()
    return d2, levels, quantiles[:, list(levels).index(0.5)], quantiles


def loro_threshold_table(cases: pd.DataFrame, pairs: dict, weights: dict[str, np.ndarray], tolerance: float, levels: list[float]) -> pd.DataFrame:
    """Thresholds chosen on the other regions at a target realised risk, applied to the held-out region."""

    truth = cases.eval_truth_h30.to_numpy()
    regions = cases.region.to_numpy()
    rows = []
    for (score_name, value_name), (score, value) in pairs.items():
        s = np.asarray(score, dtype=float)
        v = np.asarray(value, dtype=float)
        fail = (~np.isfinite(v) | (np.abs(v - truth) > tolerance)).astype(float)
        for population, w in weights.items():
            for alpha in levels:
                admitted_w = failed_w = total_w = 0.0
                region_rows = []
                for region in np.unique(regions):
                    held = (regions == region) & (w > 0) & np.isfinite(s)
                    other = (regions != region) & (w > 0) & np.isfinite(s)
                    if held.sum() < 30 or other.sum() < 100:
                        continue
                    c = curve(s[other], fail[other], w[other])
                    ok = c.loc[c.risk <= alpha + 1e-12]
                    threshold = float(ok.threshold.max()) if len(ok) else -np.inf
                    accept = held & (s <= threshold)
                    total_w += w[held].sum()
                    admitted_w += w[accept].sum()
                    failed_w += (w * fail)[accept].sum()
                    region_rows.append(float((w * fail)[accept].sum() / w[accept].sum()) if w[accept].sum() > 0 else np.nan)
                risks = np.array([r for r in region_rows if np.isfinite(r)])
                rows.append({
                    "population": population, "score": score_name, "delivered": value_name, "alpha": alpha,
                    "retention": admitted_w / total_w if total_w else np.nan, "risk": failed_w / admitted_w if admitted_w else np.nan,
                    "n_regions": len(region_rows), "share_regions_risk_le_alpha_plus_2pp": float((risks <= alpha + 0.02).mean()) if len(risks) else np.nan,
                    "worst_region_risk": float(risks.max()) if len(risks) else np.nan,
                })
    return pd.DataFrame(rows)


def predictive_pfail(quantiles: np.ndarray, levels: tuple[float, ...], point: np.ndarray, tolerance: float) -> np.ndarray:
    """P(|H - point| > tolerance) from interpolated predictive quantiles."""

    levels = np.asarray(levels)
    out = np.empty(len(point))
    for i, (row, centre) in enumerate(zip(quantiles, point)):
        lo = np.interp(centre - tolerance, row, levels, left=0.0, right=1.0)
        hi = np.interp(centre + tolerance, row, levels, left=0.0, right=1.0)
        # Tails beyond the outer stored levels are extrapolated linearly in probability.
        out[i] = lo + (1 - hi)
    return np.clip(out, 0, 1)


def classifier_fold(train: pd.DataFrame, test: pd.DataFrame, label: str, seed: int) -> pd.Series:
    model = lgb.LGBMClassifier(objective="binary", random_state=seed, **PARAMS)
    model.fit(F.design_matrix(train), train[label])
    return pd.Series(model.predict_proba(F.design_matrix(test))[:, 1], index=test.index)


def curve(score: np.ndarray, fail: np.ndarray, weight: np.ndarray) -> pd.DataFrame:
    """Accept in increasing score order; ties are accepted together."""

    order = np.argsort(score, kind="mergesort")
    s, f, w = score[order], fail[order], weight[order]
    cw, cf = np.cumsum(w), np.cumsum(w * f)
    last = np.r_[s[1:] != s[:-1], True]
    return pd.DataFrame({"threshold": s[last], "coverage": cw[last] / w.sum(), "risk": cf[last] / np.maximum(cw[last], 1e-12)})


def retention_at(curve_frame: pd.DataFrame, risk: float) -> float:
    ok = curve_frame.loc[curve_frame.risk <= risk + 1e-12]
    return float(ok.coverage.max()) if len(ok) else 0.0


def aurc(curve_frame: pd.DataFrame) -> float:
    coverage = np.r_[0.0, curve_frame.coverage.to_numpy()]
    risk = np.r_[curve_frame.risk.iloc[0], curve_frame.risk.to_numpy()]
    return float(np.trapz(risk, coverage))


def augrc(curve_frame: pd.DataFrame) -> float:
    """Area under the generalised risk (joint probability of acceptance and failure)."""

    coverage = np.r_[0.0, curve_frame.coverage.to_numpy()]
    joint = np.r_[0.0, (curve_frame.coverage * curve_frame.risk).to_numpy()]
    return float(np.trapz(joint, coverage))


def partial_area(curve_frame: pd.DataFrame, cap: float = 0.05) -> float:
    """Coverage-weighted area of (cap - risk) where risk stays below the cap."""

    coverage = np.r_[0.0, curve_frame.coverage.to_numpy()]
    slack = np.r_[cap - curve_frame.risk.iloc[0], np.clip(cap - curve_frame.risk.to_numpy(), 0, None)]
    return float(np.trapz(slack, coverage))


def group_risk(accept: np.ndarray, fail: np.ndarray, groups: np.ndarray, minimum: int = 20) -> tuple[float, float]:
    frame = pd.DataFrame({"a": accept, "f": fail, "g": groups})
    admitted = frame.loc[frame.a]
    counts = admitted.groupby("g").f.agg(["size", "mean"])
    counts = counts.loc[counts["size"] >= minimum]
    if counts.empty:
        return np.nan, np.nan
    return float(counts["mean"].mean()), float(counts["mean"].max())


def evaluate(cases: pd.DataFrame, scores: dict, fixed: dict, delivered: dict, weight: np.ndarray, tolerance: float, risk_levels: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    truth = cases.eval_truth_h30.to_numpy()
    groups = cases.independence_group.astype(str).to_numpy()
    rows, curves = [], []
    for value_name, value in delivered.items():
        value = np.asarray(value, dtype=float)
        fail = ~np.isfinite(value) | (np.abs(value - truth) > tolerance)
        fail = fail.astype(float)
        keep = weight > 0
        base = {"delivered": value_name, "unscreened_risk": float(np.average(fail[keep], weights=weight[keep]))}
        for name, accept in fixed.items():
            a = accept.to_numpy() & keep
            retention = float(weight[a].sum() / weight[keep].sum())
            risk = float(np.average(fail[a], weights=weight[a])) if a.any() else np.nan
            equal, worst = group_risk(a, fail.astype(bool), groups)
            rows.append({**base, "rule": name, "kind": "fixed", "retention": retention, "risk": risk, "group_equal_risk": equal, "worst_group_risk": worst})
        oracle = np.abs(np.nan_to_num(value, nan=1e6) - truth)
        for name, score in {**scores, "R8_oracle_error_order": oracle}.items():
            s = np.asarray(score, dtype=float)
            valid = keep & np.isfinite(s)
            if valid.sum() < 50:
                continue
            c = curve(s[valid], fail[valid], weight[valid])
            # Cases without a score are rejected, so coverage is relative to the whole population.
            c["coverage"] *= weight[valid].sum() / weight[keep].sum()
            row = {**base, "rule": name, "kind": "score", "aurc": aurc(c), "augrc": augrc(c), "partial_area_5": partial_area(c)}
            for level in risk_levels:
                row[f"retention_at_{int(level * 1000):03d}"] = retention_at(c, level)
                ok = c.loc[c.risk <= level + 1e-12]
                if len(ok):
                    threshold = float(ok.loc[ok.coverage.idxmax(), "threshold"])
                    a = valid & (s <= threshold)
                    equal, worst = group_risk(a, fail.astype(bool), groups)
                    row[f"group_equal_risk_at_{int(level * 1000):03d}"] = equal
                    row[f"worst_group_risk_at_{int(level * 1000):03d}"] = worst
            rows.append(row)
            sampled = c.iloc[np.unique(np.linspace(0, len(c) - 1, 400).astype(int))].copy()
            sampled.insert(0, "rule", name)
            sampled.insert(0, "delivered", value_name)
            curves.append(sampled)
    return pd.DataFrame(rows), pd.concat(curves, ignore_index=True)


def endpoint(cases: pd.DataFrame, scores: dict, fixed: dict, delivered: dict, weight: np.ndarray, tolerance: float, rule_names: list[str], best_value: str, target_value: str, target_score: str) -> float:
    """Retention of the target-aware rule minus the best current-practice rule at 5% realised risk."""

    truth = cases.eval_truth_h30.to_numpy()
    keep = weight > 0

    def fail_of(value):
        value = np.asarray(value, dtype=float)
        return (~np.isfinite(value) | (np.abs(value - truth) > tolerance)).astype(float)

    best = 0.0
    for value_name in ("P0", "Pobs"):
        fail = fail_of(delivered[value_name])
        for name in rule_names:
            if name in fixed:
                a = fixed[name].to_numpy() & keep
                if a.any() and np.average(fail[a], weights=weight[a]) <= 0.05:
                    best = max(best, weight[a].sum() / weight[keep].sum())
            elif name in scores:
                s = np.asarray(scores[name], dtype=float)
                valid = keep & np.isfinite(s)
                c = curve(s[valid], fail[valid], weight[valid])
                c["coverage"] *= weight[valid].sum() / weight[keep].sum()
                best = max(best, retention_at(c, 0.05))
    fail = fail_of(delivered[target_value])
    s = np.asarray(scores[target_score], dtype=float)
    valid = keep & np.isfinite(s)
    c = curve(s[valid], fail[valid], weight[valid])
    c["coverage"] *= weight[valid].sum() / weight[keep].sum()
    return retention_at(c, 0.05) - best


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(T.OUT / "e2_cases/cases.parquet"))
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--draws", type=int, default=300)
    args = parser.parse_args()
    settings = T.settings()
    tolerance = settings["tolerance_c"]
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(args.cases)
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    oof = pd.read_parquet(T.OUT / "e4_estimators/oof_predictions.parquet")
    law = pd.read_parquet(T.OUT / "e3_recovery_law/law_predictions.parquet")
    if len(oof) != len(cases) or len(law) != len(cases) or not (oof.realization_id.to_numpy() == cases.realization_id.to_numpy()).all():
        raise RuntimeError("E4/E3 predictions are not aligned with the case table")
    d2, levels, d2_point, d2_quantiles = d2_distribution(cases, oof)
    cases["d2_point"] = d2_point
    cases["fail_P0"] = ((cases.h30__policy - cases.eval_truth_h30).abs() > tolerance).astype(int)
    cases["fail_D2"] = ((cases.d2_point - cases.eval_truth_h30).abs() > tolerance).astype(int)
    regions = sorted(cases.region.unique())
    jobs = [(label, region, plain_seed(i, j)) for i, label in enumerate(("fail_P0", "fail_D2")) for j, region in enumerate(regions)]
    parts = Parallel(n_jobs=args.workers)(delayed(classifier_fold)(cases.loc[cases.region.ne(r)], cases.loc[cases.region.eq(r)], label, seed) for label, r, seed in jobs)
    direct = {label: pd.concat([p for (l, _, _), p in zip(jobs, parts) if l == label]).sort_index() for label in ("fail_P0", "fail_D2")}
    d2_pfail = predictive_pfail(d2_quantiles, levels, d2_point, tolerance)
    features = R.mask_features(cases)
    fixed = R.fixed_rules(features, cases, as_written=T.SEASON_MODE == "hot_year")
    scores = {
        **R.parametric_scores(features, cases),
        "R4_daily_disagreement": cases.daily_estimator_disagreement,
        "R5_h30_target_disagreement": cases.estimator_disagreement,
        "R6_recovery_law_pfail": law.law_pfail_050,
        "R6b_replay_law_pfail": law.law_v3_pfail_050,
        "R7a_target_aware_pfail (D2* distribution)": pd.Series(d2_pfail),
        "R7b_direct_failure_probability (P0)": direct["fail_P0"],
        "R7b_direct_failure_probability (D2*)": direct["fail_D2"],
    }
    delivered = {"P0": cases.h30__policy, "Pobs": cases.h30__observed_days, "D2*": cases.d2_point}
    pd.DataFrame({"realization_id": cases.realization_id, "station_key": cases.station_key, "year": cases.year, **{f"score::{k}": np.asarray(v) for k, v in scores.items()}, **{f"rule::{k}": v.to_numpy() for k, v in fixed.items()}}).to_parquet(OUT / "scores.parquet", index=False)
    all_rows, all_curves = [], []
    for population in ("deploy", "mech", "mnar1", "mnar2", "mnar_upper"):
        weight = T.population_weights(cases, population).to_numpy()
        rows, curves = evaluate(cases, scores, fixed, delivered, weight, tolerance, settings["risk_levels"])
        rows.insert(0, "population", population)
        curves.insert(0, "population", population)
        all_rows.append(rows)
        all_curves.append(curves)
        # Difficulty strata visible at decision time.
        for label, selected in {"overlap_none": cases.peak_overlap.eq(0), "overlap_partial": cases.peak_overlap.gt(0) & cases.peak_overlap.lt(0.5), "overlap_half": cases.peak_overlap.ge(0.5), **{f"layer_{k}": cases.policy_choice.eq(k) for k in F.LAYERS}}.items():
            w = weight * selected.to_numpy()
            if (w > 0).sum() < 200:
                continue
            rows, _ = evaluate(cases, scores, fixed, delivered, w, tolerance, settings["risk_levels"])
            rows.insert(0, "population", f"{population}|{label}")
            all_rows.append(rows)
    table = pd.concat(all_rows, ignore_index=True)
    table.to_csv(OUT / "risk_retention.csv", index=False)
    pd.concat(all_curves, ignore_index=True).to_parquet(OUT / "curves.parquet", index=False)

    # Free thresholds chosen leave-one-region-out, as for every learned component.
    pairs = {}
    for name in ("R1_annual_missing_fraction", "R2_warm_missing_fraction", "R3_observed_lower_bound (NRFA-type)"):
        for value_name in ("Pobs", "P0"):
            pairs[(name, value_name)] = (scores[name], delivered[value_name])
    for name in ("R5_h30_target_disagreement", "R6_recovery_law_pfail", "R7b_direct_failure_probability (P0)"):
        pairs[(name, "P0")] = (scores[name], delivered["P0"])
    for name in ("R7a_target_aware_pfail (D2* distribution)", "R7b_direct_failure_probability (D2*)"):
        pairs[(name, "D2*")] = (scores[name], delivered["D2*"])
    loro = loro_threshold_table(cases, pairs, {population: T.population_weights(cases, population).to_numpy() for population in ("deploy", "mech")}, tolerance, [0.025, 0.05])
    loro.to_csv(OUT / "loro_thresholds.csv", index=False)

    # Primary endpoint P2 with an independence-group bootstrap on the deploy population.
    current = list(fixed) + ["R1_annual_missing_fraction", "R2_warm_missing_fraction", "R3_observed_lower_bound (NRFA-type)"]
    target_score = "R7a_target_aware_pfail (D2*)" if False else "R7a_target_aware_pfail (D2* distribution)"
    weight = T.population_weights(cases, "deploy").to_numpy()
    point = endpoint(cases, scores, fixed, delivered, weight, tolerance, current, "P0", "D2*", target_score)
    point_direct = endpoint(cases, scores, fixed, delivered, weight, tolerance, current, "P0", "D2*", "R7b_direct_failure_probability (D2*)")
    labels = cases.independence_group.astype(str).to_numpy()
    unique = np.unique(labels)
    positions = {label: np.flatnonzero(labels == label) for label in unique}
    rng = np.random.default_rng(settings["seed"])

    def one(draw: int) -> tuple[float, float]:
        chosen = np.random.default_rng(settings["seed"] + draw).choice(unique, size=len(unique), replace=True)
        rows = np.concatenate([positions[label] for label in chosen])
        sub = cases.iloc[rows].reset_index(drop=True)
        sub_fixed = {k: v.iloc[rows].reset_index(drop=True) for k, v in fixed.items()}
        sub_scores = {k: pd.Series(np.asarray(v)[rows]) for k, v in scores.items()}
        sub_delivered = {k: pd.Series(np.asarray(v)[rows]) for k, v in delivered.items()}
        return (
            endpoint(sub, sub_scores, sub_fixed, sub_delivered, weight[rows], tolerance, current, "P0", "D2*", target_score),
            endpoint(sub, sub_scores, sub_fixed, sub_delivered, weight[rows], tolerance, current, "P0", "D2*", "R7b_direct_failure_probability (D2*)"),
        )

    boot = np.array(Parallel(n_jobs=args.workers)(delayed(one)(draw) for draw in range(args.draws)))
    summary = {
        "d2": d2, "endpoint_P2_retention_gain_at_5pct": point, "endpoint_P2_lower95": float(np.quantile(boot[:, 0], 0.025)), "endpoint_P2_upper95": float(np.quantile(boot[:, 0], 0.975)),
        "direct_classifier_gain_at_5pct": point_direct, "direct_lower95": float(np.quantile(boot[:, 1], 0.025)), "direct_upper95": float(np.quantile(boot[:, 1], 0.975)),
        "n_bootstrap": int(args.draws), "n_cases": len(cases), "n_groups": int(len(unique)),
        "success_rule": ">= 0.10 and lower95 > 0",
    }
    summary["endpoint_P2_success"] = bool(summary["endpoint_P2_retention_gain_at_5pct"] >= 0.10 and summary["endpoint_P2_lower95"] > 0)
    T.write_json(OUT / "summary.json", summary)
    view = table.loc[table.population.eq("deploy")]
    print(view[["delivered", "rule", "kind", "retention", "risk", "retention_at_050", "aurc", "augrc"]].to_string(), flush=True)
    print(summary, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""TR-E7: does an admission threshold calibrated elsewhere hold in a new region?

Leave-one-region-out on the source archive. For each held-out region the
threshold of a failure-probability score is set on the other regions' out-of-fold
scores at a nominal 5% admitted risk by (i) marginal calibration, (ii) one
threshold per information layer (Mondrian), (iii) covariate-shift weights
estimated from the held-out region's unlabelled features, and (iv) local
recalibration from k = 2, 4, 8, 16 blocks of the region itself. Realised risk
and retention are read in the region. A random-effects model on the logit
risk gives the predictive distribution of a new region's risk. Shift is split
into a score-distribution part and a P(failure | score) part.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse

import lightgbm as lgb
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.special import expit, logit
from scipy.stats import binom, ks_2samp, t as student_t

import wrr_tr_common as T
import wrr_tr_features as F
from stream_recoverability.seeds import plain_seed

OUT = T.OUT / "e7_transfer"
E5 = T.load_script("tr_e5_for_e7", T.ROOT / "scripts/436_tr_e5_rules.py")
SCORES = {
    "R7a_target_aware": ("score::R7a_target_aware_pfail (D2* distribution)", "fail_D2"),
    "R7b_direct_D2": ("score::R7b_direct_failure_probability (D2*)", "fail_D2"),
    "R6_law": ("score::R6_recovery_law_pfail", "fail_P0"),
    "R7b_direct_P0": ("score::R7b_direct_failure_probability (P0)", "fail_P0"),
}


def threshold(score: np.ndarray, fail: np.ndarray, weight: np.ndarray, alpha: float) -> float:
    """Largest threshold whose weighted admitted risk on the calibration set is at most alpha."""

    order = np.argsort(score, kind="mergesort")
    s, f, w = score[order], fail[order], weight[order]
    risk = np.cumsum(w * f) / np.maximum(np.cumsum(w), 1e-12)
    last = np.r_[s[1:] != s[:-1], True]
    ok = np.flatnonzero(last & (risk <= alpha))
    return float(s[ok[-1]]) if len(ok) else -np.inf


def layer_thresholds(frame: pd.DataFrame, score: str, label: str, alpha: float, weight: np.ndarray | None = None) -> dict[str, float]:
    out = {}
    w_all = np.ones(len(frame)) if weight is None else weight
    for layer, block in frame.groupby("layer_group"):
        rows = frame.index.get_indexer(block.index)
        if len(block) < 50:
            continue
        out[layer] = threshold(block[score].to_numpy(), block[label].to_numpy(), w_all[rows], alpha)
    out["__marginal__"] = threshold(frame[score].to_numpy(), frame[label].to_numpy(), w_all, alpha)
    return out


def apply(frame: pd.DataFrame, score: str, thresholds: dict[str, float], mondrian: bool) -> np.ndarray:
    if not mondrian:
        return frame[score].to_numpy() <= thresholds["__marginal__"]
    limits = frame.layer_group.map(lambda layer: thresholds.get(layer, thresholds["__marginal__"])).to_numpy()
    return frame[score].to_numpy() <= limits


def shift_weights(source: pd.DataFrame, target: pd.DataFrame, seed: int) -> np.ndarray:
    """Density-ratio weights for the calibration cases from a source-vs-target classifier."""

    xs, xt = F.design_matrix(source), F.design_matrix(target)
    x = pd.concat([xs, xt], ignore_index=True)
    y = np.r_[np.zeros(len(xs)), np.ones(len(xt))]
    model = lgb.LGBMClassifier(n_estimators=150, learning_rate=0.05, num_leaves=15, min_child_samples=100, subsample=0.8, subsample_freq=1, verbose=-1, n_jobs=2, random_state=seed)
    model.fit(x, y)
    p = np.clip(model.predict_proba(xs)[:, 1], 0.01, 0.99)
    w = p / (1 - p) * len(xs) / len(xt)
    return np.clip(w / w.mean(), 0, 20)


def held_out(frame: pd.DataFrame, region: str, score: str, label: str, alpha: float, seed: int, draws: int) -> list[dict]:
    source, target = frame.loc[frame.region.ne(region)], frame.loc[frame.region.eq(region)]
    rows = []

    def record(method: str, accept: np.ndarray, extra: dict | None = None) -> None:
        f = target[label].to_numpy()
        rows.append({
            "region": region, "method": method, "n_cases": len(target), "n_groups": int(target.independence_group.nunique()),
            "retention": float(accept.mean()), "risk": float(f[accept].mean()) if accept.any() else np.nan,
            "n_admitted": int(accept.sum()), "n_admitted_failures": int(f[accept].sum()),
            "unscreened_risk": float(f.mean()), **(extra or {}),
        })

    marginal = layer_thresholds(source, score, label, alpha)
    record("marginal", apply(target, score, marginal, False))
    record("mondrian_layer", apply(target, score, marginal, True))
    weights = shift_weights(source, target, seed)
    weighted = layer_thresholds(source, score, label, alpha, weights)
    record("weighted_mondrian", apply(target, score, weighted, True))
    groups = target.independence_group.astype(str).unique()
    rng = np.random.default_rng(seed)
    for k in (2, 4, 8, 16):
        if len(groups) < k + 2:
            continue
        for repeat in range(draws):
            local = rng.choice(groups, size=k, replace=False)
            calibration = target.loc[target.independence_group.astype(str).isin(local)]
            test = target.loc[~target.independence_group.astype(str).isin(local)]
            pooled = pd.concat([source, calibration])
            pooled_weight = np.r_[np.full(len(source), 1.0), np.full(len(calibration), max(1.0, len(source) / max(len(calibration), 1) / 4))]
            for method, thresholds in (("local_only_mondrian", layer_thresholds(calibration, score, label, alpha)), ("pooled_upweighted_mondrian", layer_thresholds(pooled, score, label, alpha, pooled_weight))):
                accept = apply(test, score, thresholds, True)
                f = test[label].to_numpy()
                rows.append({"region": region, "method": f"{method}_k{k}", "repeat": repeat, "n_cases": len(test), "n_groups": int(test.independence_group.nunique()), "retention": float(accept.mean()), "risk": float(f[accept].mean()) if accept.any() else np.nan, "n_admitted": int(accept.sum()), "n_admitted_failures": int(f[accept].sum()), "unscreened_risk": float(f.mean())})
    # Shift diagnostics: score distribution and P(fail | score).
    ks = ks_2samp(source[score], target[score]).statistic
    bins = np.quantile(source[score], np.linspace(0, 1, 11))
    source_rate = source.groupby(np.digitize(source[score], bins[1:-1]))[label].mean()
    target_rate = target.groupby(np.digitize(target[score], bins[1:-1]))[label].mean()
    joined = pd.concat([source_rate.rename("s"), target_rate.rename("t"), target.groupby(np.digitize(target[score], bins[1:-1])).size().rename("n")], axis=1).dropna()
    conditional_gap = float(np.average(joined.t - joined.s, weights=joined.n)) if len(joined) else np.nan
    for row in rows:
        row.update({"ks_score_shift": float(ks), "conditional_shift_failure_gap": conditional_gap, "air_layer_share": float(target.layer_group.eq("air_ridge").mean())})
    return rows


def random_effects(table: pd.DataFrame) -> dict:
    """Normal random-effects model on the logit admitted risk with a half-t(3) prior on tau (grid posterior)."""

    data = table.dropna(subset=["risk"]).loc[lambda f: f.n_admitted >= 30]
    if len(data) < 3:
        return {}
    # Cases within a region are clustered; the design effect uses the number of groups.
    effective = np.minimum(data.n_admitted, data.n_groups * 30).astype(float)
    p = (data.n_admitted_failures + 0.5) / (data.n_admitted + 1.0)
    y = logit(p)
    v = 1 / (effective * p * (1 - p))
    mus, taus = np.linspace(y.min() - 1, y.max() + 1, 241), np.linspace(0.001, 3, 300)
    mu_grid, tau_grid = np.meshgrid(mus, taus, indexing="ij")
    loglik = np.zeros_like(mu_grid)
    for yi, vi in zip(y, v):
        s2 = vi + tau_grid**2
        loglik += -0.5 * np.log(s2) - 0.5 * (yi - mu_grid) ** 2 / s2
    logprior = student_t.logpdf(tau_grid, df=3, scale=1.0)
    post = np.exp(loglik + logprior - (loglik + logprior).max())
    post /= post.sum()
    rng = np.random.default_rng(1)
    flat = rng.choice(post.size, size=20000, p=post.ravel())
    mu_s, tau_s = mu_grid.ravel()[flat], tau_grid.ravel()[flat]
    new = expit(rng.normal(mu_s, tau_s))
    return {"predictive_median_risk": float(np.median(new)), "predictive_q90_risk": float(np.quantile(new, 0.9)), "p_new_region_risk_le_7pct": float((new <= 0.07).mean()), "p_new_region_risk_le_5pct": float((new <= 0.05).mean()), "tau_median": float(np.median(tau_s)), "n_regions": len(data)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--draws", type=int, default=30)
    args = parser.parse_args()
    settings = T.settings()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    scores = pd.read_parquet(T.OUT / "e5_rules/scores.parquet")
    if not (scores.realization_id.to_numpy() == cases.realization_id.to_numpy()).all():
        raise RuntimeError("Scores are not aligned with cases")
    selection = pd.read_json(T.OUT / "e4_estimators/d2_selection.json", typ="series")
    oof = pd.read_parquet(T.OUT / "e4_estimators/oof_predictions.parquet")
    d2 = selection["d2"]
    _, _, d2_point, _ = E5.d2_distribution(cases, oof)
    d2_point = pd.Series(d2_point, index=cases.index)
    cases["fail_D2"] = ((d2_point - cases.eval_truth_h30).abs() > settings["tolerance_c"]).astype(int)
    cases["fail_P0"] = ((cases.h30__policy - cases.eval_truth_h30).abs() > settings["tolerance_c"]).astype(int)
    cases["layer_group"] = cases.policy_choice.where(cases.policy_choice.isin(["donor_ridge", "air_ridge"]), "other")
    for column in scores.columns:
        if column.startswith("score::"):
            cases[column] = scores[column].to_numpy()
    regions = cases.region.value_counts()
    regions = sorted(regions.index[cases.groupby("region").independence_group.nunique().reindex(regions.index) >= settings["region_min_blocks"]])
    all_rows = []
    for p, population in enumerate(("deploy", "mech")):
        weight = T.population_weights(cases, population)
        frame = cases.loc[weight > 0].copy()
        for s, (name, (score, label)) in enumerate(SCORES.items()):
            jobs = [delayed(held_out)(frame, region, score, label, 0.05, plain_seed(p, s, r), args.draws) for r, region in enumerate(regions)]
            for rows in Parallel(n_jobs=args.workers)(jobs):
                for row in rows:
                    all_rows.append({"population": population, "score": name, **row})
    table = pd.DataFrame(all_rows)
    table.to_csv(OUT / "loro_transfer.csv", index=False)
    fixed = table.loc[table.method.isin(["marginal", "mondrian_layer", "weighted_mondrian"])]
    summary_rows = []
    for (population, score, method), block in fixed.groupby(["population", "score", "method"]):
        valid = block.dropna(subset=["risk"])
        summary_rows.append({
            "population": population, "score": score, "method": method, "n_regions": len(block),
            "share_risk_le_7pct": float((valid.risk <= 0.07).mean()), "median_risk": float(valid.risk.median()), "max_risk": float(valid.risk.max()),
            "median_retention": float(block.retention.median()), **random_effects(block),
        })
        # Leave one region out of the summary: does the share flip below 0.8?
        shares = [float((valid.loc[valid.region != r].risk <= 0.07).mean()) for r in valid.region]
        summary_rows[-1]["share_min_drop_one"] = float(min(shares)) if shares else np.nan
    local = table.loc[table.method.str.contains("_k")].copy()
    local["k"] = local.method.str.extract(r"_k(\d+)").astype(int)
    local["scheme"] = local.method.str.replace(r"_k\d+", "", regex=True)
    curve = local.groupby(["population", "score", "scheme", "k"]).apply(lambda f: pd.Series({"n_regions": f.region.nunique(), "median_risk": f.risk.median(), "p_risk_le_7pct": (f.risk <= 0.07).mean(), "median_retention": f.retention.median()})).reset_index()
    curve.to_csv(OUT / "local_recalibration_curve.csv", index=False)
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / "transfer_summary.csv", index=False)
    certifiable = pd.DataFrame({"n_groups": np.arange(5, 121, 1)})
    certifiable["zero_failure_upper95"] = 1 - 0.05 ** (1 / certifiable.n_groups)
    certifiable.to_csv(OUT / "certifiable_risk_by_groups.csv", index=False)
    endpoint = {"success_rule": "share >= 0.80 and median <= 0.05 in both the mech and the deploy population (source part); sealed Australia evaluated separately"}
    successes = []
    for population in ("mech", "deploy"):
        main_row = summary.loc[(summary.population == population) & (summary.score == "R7a_target_aware") & (summary.method == "mondrian_layer")]
        if not len(main_row):
            continue
        share, median = float(main_row.share_risk_le_7pct.iloc[0]), float(main_row.median_risk.iloc[0])
        endpoint[f"{population}_share_risk_le_7pct"] = share
        endpoint[f"{population}_median_risk"] = median
        endpoint[f"{population}_n_regions"] = int(main_row.n_regions.iloc[0])
        endpoint[f"{population}_predictive_p_new_region_le_7pct"] = main_row.get("p_new_region_risk_le_7pct", pd.Series([np.nan])).iloc[0]
        successes.append(share >= 0.8 and median <= 0.05)
    endpoint["P3_source_success"] = bool(successes and all(successes))
    T.write_json(OUT / "endpoint_P3_source.json", endpoint)
    print(summary.to_string(), flush=True)
    print(curve.loc[curve.population.eq("deploy")].to_string(), flush=True)
    print(endpoint, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Full group-disjoint outer-region refits for 20 independently redrawn sources.

The fourth-round redesign is exploratory; it does not replace the historical
registered P1--P4 verdicts. No calibration outcome can reach an outer model.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
import argparse
import json
import time
from pathlib import Path
import lightgbm as lgb
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.stats import norm, t as student_t
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
import wrr_tr_common as T
import wrr_tr_features as F
import wrr_tr_law as L
from stream_recoverability.seeds import plain_seed
from stream_recoverability.experiments.v19_revision.risk import select_group_threshold
from stream_recoverability.experiments.tr_revision.statistics import random_effects_ratio

CONFIG = json.loads((T.ROOT / "configs/wrr_review_completion_20261024.json").read_text())
OUT = T.ROOT / CONFIG["out"]
LEVELS = np.asarray(F.QUANTILES)
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1, verbose=-1, n_jobs=1)
KEYS = ["network_id", "station_key", "year", "design_family", "realization_id", "policy_choice"]


def difficulty(c):
    b = np.where(c.peak_overlap <= 0, 0, np.searchsorted([0, .25, .5, .75, 1], c.peak_overlap, side="left"))
    layer = c.policy_choice.where(c.policy_choice.isin(["air_ridge", "donor_ridge"]), "other")
    return pd.Series([f"{i}|{j}" for i, j in zip(b, layer)], index=c.index)


def prefix_admit(score, weight=None, alpha=.05, factor=1):
    s = np.asarray(score, float)
    w = np.ones(len(s)) if weight is None else np.asarray(weight, float)
    valid = np.isfinite(s) & (w > 0)
    order = np.flatnonzero(valid)[np.argsort(s[valid], kind="mergesort")]
    if not len(order):
        return np.zeros(len(s), bool)
    expected = np.cumsum(s[order] * w[order] * factor) / np.cumsum(w[order])
    tied_end = np.r_[s[order][1:] != s[order][:-1], True]
    eligible = np.flatnonzero(tied_end & (expected <= alpha))
    return valid & (s <= s[order[eligible[-1]]]) if len(eligible) else np.zeros(len(s), bool)


def roles(c, region, seed):
    held = c.region.eq(region)
    if "training_partition" in c:
        held &= c.training_partition.eq("test")
    held_groups = set(c.loc[held, "independence_group"])
    eligible = c.loc[~c.independence_group.isin(held_groups)]
    if "training_partition" in eligible:
        eligible = eligible.loc[eligible.training_partition.eq("train")]
    groups = np.array(sorted(eligible.independence_group.unique()))
    rng = np.random.default_rng(seed)
    rng.shuffle(groups)
    cuts = np.maximum.accumulate(np.round(np.cumsum(CONFIG["fit_role_shares"])[:-1] * len(groups)).astype(int))
    parts = np.split(groups, cuts)
    if any(len(p) < 2 for p in parts):
        raise RuntimeError(f"Insufficient group-disjoint roles for {region}")
    role_groups = {name: list(map(str, part)) for name, part in zip(CONFIG["fit_role_names"], parts)}
    # Bootstrap within each already disjoint role. Repeated copies cannot enter another role.
    weights = {}
    for name, part in zip(CONFIG["fit_role_names"], parts):
        choice = rng.choice(part, len(part), replace=True)
        count = pd.Series(choice).value_counts()
        weights[name] = c.independence_group.map(count).fillna(0).to_numpy(dtype=float)
        if "training_partition" in c:
            weights[name] *= c.training_partition.eq("train").to_numpy()
    return held.to_numpy(), role_groups, weights


def group_ratio(c, score, fail):
    frame = pd.DataFrame({"group": c.independence_group.to_numpy(), "score": score, "fail": fail})
    # Equal independent groups within each region; delta variance based on groups.
    by_group = frame.groupby("group").agg(o=("fail", "mean"), e=("score", "mean"))
    if len(by_group) < 3 or by_group.e.sum() <= 0:
        return None
    o, e = float(by_group.o.sum()), float(by_group.e.sum())
    ratio = (o + .5) / (e + .5)
    influence = (by_group.o - ratio * by_group.e) / max(float(by_group.e.mean()), 1e-8)
    # A zero-error collection of three independent groups is not near-certain
    # calibration. Retain a conservative half-event group-unit variance floor.
    variance = max(float(influence.var(ddof=1) / len(by_group) / max(ratio**2, 1e-8)), 1/(o+.5))
    return o, e, variance


def fit_region(seed, region, split="leave_one_year_out", case_path=None, deployment_only=False):
    folder = OUT / "refits" / split / f"seed_{seed:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    stem = region.replace("/", "_")
    target = folder / f"{stem}.parquet"
    if target.exists() and target.with_suffix(".json").exists() and (folder/"calibration"/target.name).exists() and (seed!=0 or target.with_suffix(".joblib").exists()):
        return {"seed": seed, "region": region, "cached": True}
    path = Path(case_path) if case_path else OUT / "cases" / split / f"seed_{seed:02d}.parquet"
    c = pd.read_parquet(path)
    # A missing simulation feature is supported by the tree's missing-value
    # branch. Keep the case so baseline availability denominators remain honest.
    c = c.loc[c.policy_choice.ne("unavailable") & c.eval_truth_h30.notna()].reset_index(drop=True)
    if c.duplicated(KEYS).any():
        raise RuntimeError("Nonunique case identity; realization_id alone is never a join key")
    region_number = sorted(set(c.region.unique())|({region} if deployment_only else set())).index(region)
    random_seed = plain_seed(7, seed, region_number)
    held, role_groups, weights = roles(c, region, random_seed)
    x = F.design_matrix(c, simulation=True)
    xp = F.design_matrix(c, simulation=False)
    y = c.eval_truth_h30.to_numpy()
    point = c.h30__policy.to_numpy()
    fit = weights["estimator"] > 0
    cal = weights["interval_calibration"] > 0
    learning_groups = np.array(role_groups["risk_learning"])
    classifier_groups, probability_groups = np.split(learning_groups, [max(2, int(len(learning_groups)*.75))])
    scorefit = c.independence_group.isin(classifier_groups).to_numpy() & (weights["risk_learning"] > 0)
    probabilityfit = c.independence_group.isin(probability_groups).to_numpy() & (weights["risk_learning"] > 0)
    rulecal = weights["rule_calibration"] > 0
    predictions = []
    fitted_quantiles=[]
    for level in LEVELS:
        model = lgb.LGBMRegressor(objective="quantile", alpha=float(level), random_state=random_seed, **PARAMS)
        model.fit(x.loc[fit], (y-point)[fit], sample_weight=weights["estimator"][fit])
        fitted_quantiles.append(model)
        predictions.append(point + model.predict(x))
    q = np.sort(np.column_stack(predictions), axis=1)
    raw = q.copy()
    d = difficulty(c)
    fitted_offsets={}
    # Only the interval-calibration role determines offsets, including fallback.
    for group in d.unique():
        pool = cal & d.eq(group).to_numpy()
        if pool.sum() < 50:
            pool = cal
        error = y[pool, None] - q[pool]
        error = np.repeat(error,weights["interval_calibration"][pool].astype(int),axis=0)
        offset = np.array([np.quantile(error[:, j], float(level), method="higher" if level >= .5 else "lower") for j, level in enumerate(LEVELS)])
        q[d.eq(group)] += offset
        fitted_offsets[group]=offset
    q = np.sort(q, axis=1)
    median = q[:, np.flatnonzero(LEVELS == .5)[0]]
    fail = (np.abs(median-y) > .5).astype(int)
    mean_model = lgb.LGBMRegressor(objective="l2", random_state=random_seed, **PARAMS)
    mean_model.fit(xp.loc[fit], (y-point)[fit], sample_weight=weights["estimator"][fit])
    p2 = point[held] + mean_model.predict(xp.loc[held]) if held.any() else np.array([])
    classifier=None
    calibrator=None
    if np.unique(fail[scorefit]).size == 2:
        classifier = lgb.LGBMClassifier(objective="binary", random_state=random_seed, **PARAMS)
        classifier.fit(x.loc[scorefit], fail[scorefit], sample_weight=weights["risk_learning"][scorefit])
        probability = classifier.predict_proba(x)[:, 1]
    else:
        probability = np.full(len(c), float(np.mean(fail[scorefit])))
    calibrated_probability = probability.copy()
    if probabilityfit.sum() >= 50 and np.unique(fail[probabilityfit]).size == 2:
        logit = np.log(np.clip(probability, 1e-6, 1-1e-6) / np.clip(1-probability, 1e-6, 1))[:, None]
        calibrator = LogisticRegression(C=10).fit(logit[probabilityfit], fail[probabilityfit],sample_weight=weights["risk_learning"][probabilityfit])
        calibrated_probability = calibrator.predict_proba(logit)[:, 1]
    # Overlapping-group empirical post-calibration. This is explicitly NOT the
    # finite-sample conditional-coverage algorithm of Gibbs et al.
    group_probability = calibrated_probability.copy()
    labels = {
        "difficulty": d,
        "layer": c.policy_choice,
        "regulation": c.regulation_status,
    }
    for grouping in labels.values():
        for label in grouping.unique():
            pool = probabilityfit & grouping.eq(label).to_numpy()
            if pool.sum() >= 30:
                factor = (fail[pool].sum()+.5)/(calibrated_probability[pool].sum()+.5)
                selected = grouping.eq(label).to_numpy()
                group_probability[selected] = np.maximum(group_probability[selected], np.minimum(1, calibrated_probability[selected]*max(1, factor)))
    if deployment_only:
        import joblib
        deployment=OUT/"deployment";deployment.mkdir(parents=True,exist_ok=True)
        bundle=deployment/"global_source_candidate.joblib"
        joblib.dump({"quantile_models":fitted_quantiles,"mean_model":mean_model,"classifier":classifier,"calibrator":calibrator,"offsets":fitted_offsets,"features":list(x.columns),"plain_features":list(xp.columns),"constant_probability":float(np.mean(fail[scorefit])),"roles":role_groups},bundle,compress=3)
        diagnostics=c.loc[rulecal,["region","independence_group","design_family","policy_choice","peak_overlap"]].copy()
        diagnostics["D2_failure"]=fail[rulecal];diagnostics["risk_score"]=probability[rulecal]
        diagnostics.to_parquet(deployment/"source_rule_calibration_diagnostics.parquet",index=False)
        T.write_json(deployment/"candidate.json",{"seed":seed,"training_data":"opened source seed zero only; all source regions eligible; four independent-group roles","roles":role_groups,"source_stations":int(c.station_key.nunique()),"source_groups":int(c.independence_group.nunique()),"point_for_release":"calibrated distribution-regression median, exactly the failure classifier's target","individual_score_cap":.1,"batch_individual_cap":.3,"model_file":str(bundle.relative_to(T.ROOT)),"group_or_individual_guarantee":False,"registration_status":"draft candidate, not publicly registered","target_water_temperature_read":False,"scope":"this candidate supports the studied D2 release rule; comparable classical estimation remains a separate source finding"})
        return {"deployment_candidate":str(bundle),"n_source":len(c)}
    # Table baselines trained on the estimator role only.
    cell = c.design_family + "|" + c.gap_length.astype(str).where(c.design_family.eq("crossed"), "calendar") + "|" + d
    lookup_frame=pd.DataFrame({"cell":cell[fit],"error":(point[fit]-y[fit])*weights["estimator"][fit],"failure":(np.abs(point[fit]-y[fit])>.5).astype(float)*weights["estimator"][fit],"weight":weights["estimator"][fit]}).groupby("cell").sum()
    lookup_error=lookup_frame.error/lookup_frame.weight
    lookup_failure=lookup_frame.failure/lookup_frame.weight
    debias = point[held] - cell[held].map(lookup_error).fillna(float(np.average((point-y)[fit], weights=weights["estimator"][fit]))).to_numpy()
    pfail_table = cell[held].map(lookup_failure).fillna(float((np.abs(point[fit]-y[fit]) > .5).mean())).to_numpy()
    out = c.loc[held].copy()
    out["P2"] = p2
    out["lookup_debias"] = debias
    out["lookup_pfail"] = pfail_table
    out["D2"] = median[held]
    out["D2_raw"] = raw[held, 3]
    out["risk_score"] = probability[held]
    out["risk_score_calibrated"] = calibrated_probability[held]
    out["risk_score_group_adjusted"] = group_probability[held]
    out["difficulty"] = d[held].to_numpy()
    out["decision_hot"] = c.loc[held, "air_warm_z_mean"].to_numpy() >= float(c.loc[fit, "air_warm_z_mean"].quantile(.9))
    out["out_of_training_range"] = (c.loc[held, "h30__policy"] > c.loc[fit, "train_h30_mean"].quantile(.99)).to_numpy()
    for j, level in enumerate(LEVELS):
        out[f"D2_q{int(100*level):02d}"] = q[held, j]
        out[f"D2_raw_q{int(100*level):02d}"] = raw[held, j]
    law = L.apply_law(out)
    out["recovery_probability"] = law.law_pfail.to_numpy()
    out["recovery_bias"] = law.law_bias.to_numpy()
    # t5 sensitivity matches the stored nominal scale proxy; law_sd is not the
    # exact truncated-mixture variance. No held-out fitting is used.
    scale = np.maximum(law.law_sd.to_numpy(), .001) * np.sqrt(3/5)
    out["recovery_probability_t5"] = np.clip(student_t.cdf((-.5-law.law_bias.to_numpy())/scale, 5) + student_t.sf((.5-law.law_bias.to_numpy())/scale, 5), 0, 1)
    meta = dict(seed=seed, region=region, split=split, held_groups=sorted(c.loc[held, "independence_group"].unique()), roles=role_groups, role_effective_groups={name:int(np.unique(c.loc[w > 0,"independence_group"]).size) for name,w in weights.items()}, method="four disjoint grouped roles plus independent held region; bootstrap within roles", rule_details={})
    for family in ["calendar", "crossed"]:
        local = out.design_family.eq(family).to_numpy()
        pool = rulecal & c.design_family.eq(family).to_numpy()
        held_score = probability[held]
        # Random effects based on calibration groups grouped by source region.
        ratios = []
        for source_region in sorted(c.loc[pool,"region"].unique()):
            sel = pool & c.region.eq(source_region).to_numpy()
            admit = prefix_admit(probability[sel])
            r = group_ratio(c.loc[sel].iloc[np.flatnonzero(admit)], probability[sel][admit], fail[sel][admit]) if admit.any() else None
            if r is not None:
                ratios.append(r)
        re = random_effects_ratio(*map(np.asarray, zip(*ratios))) if len(ratios)>=3 else {"upper":None, "ratio":None, "n":len(ratios)}
        k_values = [o/e for o,e,_ in ratios if e>0]
        k80 = max(1,float(np.quantile(k_values,.8))) if k_values else 1
        kre = max(1,float(re["upper"])) if re.get("upper") is not None and np.isfinite(re["upper"]) else np.inf
        for label, factor in [("average", k80),("average_cap",k80),("random_effects",kre)]:
            out.loc[out.index[local], f"admit_{label}"] = prefix_admit(held_score[local], factor=factor)
        out.loc[out.index[local],"admit_average_cap"] &= out.loc[out.index[local],"risk_score"].le(.3)
        # Mondrian application within each independent deployment group.
        for _, idx in out.loc[local].groupby("independence_group").groups.items():
            out.loc[idx,"admit_mondrian"] = prefix_admit(out.loc[idx,"risk_score"].to_numpy(), factor=k80) & out.loc[idx,"risk_score"].le(.3).to_numpy()
        candidates = np.array([.01,.025,.05,.075,.1,.15,.2,.3])
        certificate = select_group_threshold(probability[pool], fail[pool], c.loc[pool,"independence_group"].to_numpy(), candidates) if pool.any() else None
        threshold = certificate.threshold if certificate else -np.inf
        out.loc[out.index[local],"admit_group_certificate"] = held_score[local] <= threshold
        # Source-fixed ATC threshold: matching labeled calibration accuracy by
        # a confidence threshold; no target labels used in deployment.
        grid = np.unique(probability[pool])
        desired = float(fail[pool].mean()) if pool.any() else 1
        if len(grid):
            atc_cut = float(np.quantile(probability[pool], 1-desired))
            out.loc[out.index[local],"admit_atc"] = held_score[local] <= min(atc_cut,.3)
        meta["rule_details"][family] = {"k80":k80,"random_effects":re,"certificate_threshold":float(threshold) if np.isfinite(threshold) else None,"certificate_status":certificate.status if certificate else "no_calibration_cases","calibration_groups":certificate.n_groups if certificate else 0}
    for column in [col for col in out if col.startswith("admit_")]:
        out[column] = out[column].fillna(False).astype(bool)
    calibration_folder=folder/"calibration"
    calibration_folder.mkdir(exist_ok=True)
    calibration=c.loc[rulecal,["independence_group","region","design_family","peak_overlap","missing_fraction","train_h30_mean","train_h30_sd","air_warm_z_mean","policy_choice"]].copy()
    calibration["risk_score"]=probability[rulecal]
    calibration["failure"]=fail[rulecal]
    calibration.to_parquet(calibration_folder/f"{stem}.parquet",index=False)
    out.to_parquet(target, index=False)
    T.write_json(target.with_suffix(".json"), meta)
    if seed==0:
        import joblib
        joblib.dump({"quantile_models":fitted_quantiles,"mean_model":mean_model,"classifier":classifier,"calibrator":calibrator,"offsets":fitted_offsets,"features":list(x.columns),"plain_features":list(xp.columns),"constant_probability":float(np.mean(fail[scorefit])),"roles":role_groups},target.with_suffix(".joblib"),compress=3)
    return {"seed":seed,"region":region,"n":len(out)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seeds",nargs="+",type=int,default=CONFIG["seeds"])
    p.add_argument("--split",default="leave_one_year_out")
    p.add_argument("--workers",type=int,default=48)
    p.add_argument("--case-path")
    p.add_argument("--regions",nargs="+")
    a=p.parse_args()
    jobs=[]
    for seed in a.seeds:
        path=Path(a.case_path) if a.case_path else OUT/"cases"/a.split/f"seed_{seed:02d}.parquet"
        import pyarrow.parquet as pq
        columns=["region"]+(["training_partition"] if "training_partition" in pq.ParquetFile(path).schema_arrow.names else [])
        region_frame=pd.read_parquet(path,columns=columns)
        if "training_partition" in region_frame:
            region_frame=region_frame.loc[region_frame.training_partition.eq("test")]
        regions=sorted(region_frame.region.unique())
        jobs.extend((seed,r) for r in regions if not a.regions or r in a.regions)
    print(f"refitting {len(jobs)} complete outer-region models",flush=True)
    start=time.monotonic()
    result=Parallel(n_jobs=a.workers,verbose=10)(delayed(fit_region)(seed,region,a.split,a.case_path) for seed,region in jobs)
    if result and all(r.get("cached") for r in result) and (OUT/"refits"/a.split/"summary.json").exists():
        print("All regional refits already complete; preserving the original execution summary",flush=True)
        return 0
    T.write_json(OUT/"refits"/a.split/"summary.json",{"jobs":result,"elapsed_seconds":time.monotonic()-start,"seeds":a.seeds,"evidence_role":"exploratory redesign; not repeated registered endpoints"})
    return 0


if __name__=="__main__":
    raise SystemExit(main())

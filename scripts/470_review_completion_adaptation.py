#!/usr/bin/env python3
"""Shift diagnostics and independent-group small-label learning curves.

EM, ATC and importance weighting are assumption-dependent comparisons. Only
the bounded-group certificate is called a guarantee. PPI estimates mean risk
with labeled-group residuals; its normal interval is an asymptotic diagnostic,
not a simultaneous finite-sample selective-risk certificate.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed
from stream_recoverability.experiments.v19_revision.risk import select_group_threshold

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]
CANDIDATES=np.array([.01,.025,.05,.075,.1,.15,.2,.3])


def em_prior(score,source_prior,iterations=100):
    p=np.clip(score,1e-6,1-1e-6);prior=float(np.clip(source_prior,1e-6,1-1e-6));target=prior
    for _ in range(iterations):
        a=p*target/prior
        b=(1-p)*(1-target)/(1-prior)
        posterior=a/(a+b)
        updated=float(posterior.mean())
        if abs(updated-target)<1e-8:
            break
        target=updated
    return posterior,target


def atc_failure(source_score,source_failure,target_score):
    # Confidence is 1-p(error). Select threshold whose calibration count of
    # low-confidence cases matches observed error; estimate target error count.
    threshold=float(np.quantile(source_score,1-np.mean(source_failure)))
    return float(np.mean(np.asarray(target_score)>threshold)),threshold


def small_labels(frame,seed,repeats=100):
    rng=np.random.default_rng(seed)
    units=np.array(sorted(frame.independence_group.unique()))
    rows=[]
    for budget in [2,4,8,10,16,32,64]:
        if len(units)<=budget:
            continue
        for repetition in range(repeats):
            chosen=rng.choice(units,budget,replace=False)
            cal=frame.independence_group.isin(chosen).to_numpy()
            test=~cal
            score=frame.risk_score.to_numpy()
            failure=frame.failure.to_numpy(bool)
            certificate=select_group_threshold(score[cal],failure[cal],frame.independence_group.to_numpy()[cal],CANDIDATES)
            accept=test&(score<=certificate.threshold)
            group=frame.loc[accept].groupby("independence_group").failure.agg(["size","mean"])
            group=group.loc[group["size"]>=20]
            # Semisupervised residual control variate: independent-group units.
            residual=frame.loc[cal].assign(residual=lambda f:f.failure-f.risk_score).groupby("independence_group").residual.mean()
            mean_prediction=frame.loc[test].groupby("independence_group").risk_score.mean().mean()
            ppi=float(np.clip(mean_prediction+residual.mean(),0,1))
            ppi_upper=float(np.clip(ppi+norm.ppf(.95)*residual.std(ddof=1)/np.sqrt(len(residual)),0,1))
            rows.append(dict(budget_groups=budget,repeat=repetition,certificate_status=certificate.status,retention=float(accept.sum()/test.sum()),risk=float(failure[accept].mean()) if accept.any() else np.nan,n_admitted=int(accept.sum()),fraction_groups_above_10=float((group["mean"]>.1).mean()) if len(group) else np.nan,ppi_group_equal_failure_estimate=ppi,ppi_asymptotic_upper=ppi_upper,actual_group_equal_failure=float(frame.loc[test].groupby("independence_group").failure.mean().mean())))
    return rows


def analyse(seed):
    folder=OUT/"adaptation"/f"seed_{seed:02d}";folder.mkdir(parents=True,exist_ok=True)
    predictions=OUT/"refits/leave_one_year_out"/f"seed_{seed:02d}"
    rows,small=[],[]
    for i,path in enumerate(sorted(predictions.glob("*.parquet"))):
        c=pd.read_parquet(path)
        cal_path=predictions/"calibration"/path.name
        if not cal_path.exists():
            continue
        cal=pd.read_parquet(cal_path)
        c["failure"]=(c.D2-c.eval_truth_h30).abs()>.5
        for family in ["calendar","crossed"]:
            target=c.loc[c.design_family.eq(family)].copy()
            source=cal.loc[cal.design_family.eq(family)].copy()
            if target.empty or source.empty:
                continue
            actual=float(target.failure.mean())
            posterior,prior=em_prior(target.risk_score.to_numpy(),float(source.failure.mean()))
            atc,threshold=atc_failure(source.risk_score.to_numpy(),source.failure.to_numpy(),target.risk_score.to_numpy())
            features=["peak_overlap","missing_fraction","train_h30_mean","train_h30_sd","air_warm_z_mean"]
            x=pd.concat([source[features],target[features]],ignore_index=True)
            domain=np.r_[np.zeros(len(source)),np.ones(len(target))]
            classifier=make_pipeline(SimpleImputer(),StandardScaler(),LogisticRegression(max_iter=300)).fit(x,domain)
            propensity=np.clip(classifier.predict_proba(source[features])[:,1],.01,.99)
            weight=np.clip(propensity/(1-propensity)*len(source)/len(target),.05,20)
            weighted=float(np.average(source.failure,weights=weight))
            for method,estimate in [("average_confidence",float(target.risk_score.mean())),("prior_EM",prior),("ATC",atc),("importance_weighted",weighted)]:
                rows.append(dict(seed=seed,region=path.stem,family=family,shift="observed_region",method=method,estimated_risk=estimate,actual_risk=actual,absolute_error=abs(estimate-actual),assumption="unverified on an unseen deployment population"))
            labelcurve=small_labels(target,plain_seed(seed,i,0 if family=="calendar" else 1),repeats=100)
            small.extend(dict(seed=seed,region=path.stem,family=family,**r) for r in labelcurve)
            # Known-probability synthetic tests deliberately violate distinct
            # assumptions. Hidden labels are generated from q, not recycled.
            rng=np.random.default_rng(plain_seed(seed,i,9))
            score=source.risk_score.to_numpy()
            for shift in ["base_rate","gap_pattern","hot_climate","conditional_shift"]:
                if shift=="base_rate":
                    # Exact discrete label shift under a known calibrated
                    # source posterior: preserve P(X|Y), change P(Y).
                    prior0=float(np.clip(score.mean(),1e-6,1-1e-6))
                    prior1=min(.8,3*prior0)
                    marginal=score*prior1/prior0+(1-score)*(1-prior1)/(1-prior0)
                    chosen=rng.choice(len(score),len(score),replace=True,p=marginal/marginal.sum())
                    target_score=score[chosen]
                    q=(score*prior1/prior0/marginal)[chosen]
                elif shift=="gap_pattern":
                    marginal=np.exp(np.log(5)*source.peak_overlap.to_numpy())
                    chosen=rng.choice(len(score),len(score),replace=True,p=marginal/marginal.sum())
                    target_score=score[chosen];q=target_score.copy()
                elif shift=="hot_climate":
                    air=np.clip(source.air_warm_z_mean.fillna(0).to_numpy(),-3,3)
                    marginal=np.exp(air*np.log(3))
                    chosen=rng.choice(len(score),len(score),replace=True,p=marginal/marginal.sum())
                    target_score=score[chosen];q=target_score.copy()
                else:
                    target_score=score.copy();q=np.minimum(1,score+.15)
                observed=rng.random(len(q))<q
                synthetic_posterior,synthetic_prior=em_prior(target_score,float(score.mean()))
                for method,p in [("unchanged_score",target_score),("prior_EM",synthetic_posterior),("oracle_probability",q)]:
                    accept=p<=.1
                    rows.append(dict(seed=seed,region=path.stem,family=family,shift=shift,method=method,estimated_risk=float(p[accept].mean()) if accept.any() else np.nan,actual_risk=float(observed[accept].mean()) if accept.any() else np.nan,true_expected_risk=float(q[accept].mean()) if accept.any() else np.nan,retention=float(accept.mean()),assumption="fully specified synthetic truth; unchanged covariates can conceal conditional shift"))
    pd.DataFrame(rows).to_csv(folder/"risk_estimation.csv",index=False)
    pd.DataFrame(small).to_csv(folder/"small_label_curve.csv",index=False)
    return seed


def main():
    p=argparse.ArgumentParser();p.add_argument("--seeds",type=int,nargs="+",default=CONFIG["seeds"]);p.add_argument("--workers",type=int,default=16);a=p.parse_args()
    from joblib import Parallel,delayed
    Parallel(n_jobs=a.workers,verbose=10)(delayed(analyse)(seed) for seed in a.seeds)
    return 0


if __name__=="__main__":
    raise SystemExit(main())

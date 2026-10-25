#!/usr/bin/env python3
"""Frozen-admission group deletion audit, including the historical N1 endpoint.

No mask, estimator, calibration role or historical verdict is changed. The
best published comparator is selected on opened evaluation outcomes; this is
an influence diagnostic, never a deployable threshold-selection procedure.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.robustness import minimum_risk_failure, minimum_retention_reversal
from stream_recoverability.experiments.tr_revision.screening import published_rules

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]
DEST=OUT/"robustness"


def counts(group, accepted, failed, labels):
    frame=pd.DataFrame({"group":group,"a":accepted.astype(int),"b":(accepted&failed).astype(int)})
    return frame.groupby("group")[["a","b"]].sum().reindex(labels,fill_value=0)


def annotate(result, labels, a, b, ar=None, br=None):
    result=dict(result)
    removed=result.pop("removed")
    keep=np.ones(len(labels),bool);keep[removed]=False
    result.update(removed_groups=";".join(str(labels[i]) for i in removed),
                  remaining_admitted=int(a[keep].sum()),
                  remaining_risk=float(b[keep].sum()/a[keep].sum()) if a[keep].sum() else np.nan)
    if ar is not None:
        result.update(remaining_reference_admitted=int(ar[keep].sum()),
                      remaining_reference_risk=float(br[keep].sum()/ar[keep].sum()) if ar[keep].sum() else np.nan)
    return result


def source(seed):
    columns=["independence_group","design_family","D2","eval_truth_h30","year","mask_runs","warm_months","peak_center_doy","longest_run","peak_overlap","risk_score","risk_score_group_adjusted","admit_average","admit_average_cap"]
    c=pd.concat([pd.read_parquet(p,columns=columns) for p in sorted((OUT/f"refits/leave_one_year_out/seed_{seed:02d}").glob("*.parquet"))],ignore_index=True)
    if c.empty or not np.isfinite(c.D2).all():
        raise RuntimeError("Require complete finite D2 predictions")
    fixed=published_rules(c)
    rules={"average":c.admit_average.to_numpy(bool),"average_cap":c.admit_average_cap.to_numpy(bool),
           "individual_0.1":c.risk_score.le(.1).to_numpy(),"individual_group_adjusted":c.risk_score_group_adjusted.le(.1).to_numpy()}
    failure=(c.D2-c.eval_truth_h30).abs().gt(.5).to_numpy()
    rows=[]
    for family in ["calendar","crossed"]:
        base=c.design_family.eq(family).to_numpy();labels=np.array(sorted(c.loc[base,"independence_group"].unique()))
        refs={name:counts(c.independence_group,admit&base,failure,labels) for name,admit in fixed.items()}
        eligible=[name for name,g in refs.items() if g.a.sum() and g.b.sum()<=.05*g.a.sum()]
        if not eligible:
            raise RuntimeError("No nonempty published rule meets 5% full-data point risk")
        best=max(eligible,key=lambda name:(refs[name].a.sum(),name));reference=refs[best]
        for name,admit in rules.items():
            a=counts(c.independence_group,admit&base,failure,labels)
            comparisons={best:reference,"one_feature_50":counts(c.independence_group,c.peak_overlap.lt(.5).to_numpy()&base,failure,labels)}
            risk=minimum_risk_failure(a.a,a.b,.05)
            for ref,rg in comparisons.items():
                # A cheap geometric screen can itself miss 5% under controlled
                # gaps. Only a qualifying reference supports a same-cap test.
                if not rg.a.sum() or rg.b.sum()>.05*rg.a.sum():
                    continue
                ret=minimum_retention_reversal(a.a,a.b,rg.a,rg.b,.05)
                for endpoint,result in [("risk_above_5pct",risk),("retention_advantage_lost",ret)]:
                    row=dict(seed=seed,family=family,rule=name,reference=ref,endpoint=endpoint,
                             n_groups=len(labels),risk_cap=.05,full_retention=float(a.a.sum()/base.sum()),
                             full_risk=float(a.b.sum()/a.a.sum()) if a.a.sum() else np.nan,
                             reference_retention=float(rg.a.sum()/base.sum()),reference_risk=float(rg.b.sum()/rg.a.sum()),
                             reference_selection="best published at <=5% evaluation risk, or fixed one-feature screen; exploratory",
                             scope="fixed predictions and original admissions; no refit or prefix reapplication")
                    row.update(annotate(result,labels,a.a.to_numpy(),a.b.to_numpy(),rg.a.to_numpy(),rg.b.to_numpy()))
                    rows.append(row)
    frame=pd.DataFrame(rows);folder=DEST/f"seed_{seed:02d}";folder.mkdir(parents=True,exist_ok=True)
    frame.to_csv(folder/"group_deletions.csv",index=False)
    print(f"group deletion audit seed {seed} complete",flush=True)
    return frame


def historical_n1():
    original=T.OUT/"e10_sealed_usgs"
    old=json.loads((original/"sealed_results.json").read_text())
    bundle=T.load_script("r4_historical_influence_bundle",T.ROOT/"scripts/455_tr2_final_models.py")
    rule=T.load_script("r4_historical_influence_rule",T.ROOT/"scripts/453_tr2_expected_risk.py")
    c=pd.read_parquet(original/"cases.parquet")
    c=c.loc[c.policy_choice.ne("unavailable")&c.eval_truth_h30.notna()&c.state_h30_q50.notna()].reset_index(drop=True)
    scored=bundle.apply_bundle(c)
    meta=json.loads((bundle.BUNDLE/"bundle.json").read_text());factor=meta["expected_risk"]["factor_k"]["R7b"];alpha=meta["expected_risk"]["alpha"]
    score=scored.R7b.to_numpy();bad=(scored.d2_point-c.eval_truth_h30).abs().gt(meta["tolerance_c"]).to_numpy()
    rows=[]
    for population,family in [("deploy","calendar"),("mech","crossed")]:
        base=c.design_family.eq(family).to_numpy();admit=np.zeros(len(c),bool)
        admit[base]=rule.admit(score[base],np.ones(base.sum()),alpha,factor)
        risk=float(bad[admit].mean());retention=float(admit[base].mean())
        assert abs(risk-old["N1_expected_risk_R7b"][population]["risk"])<1e-12
        assert abs(retention-old["N1_expected_risk_R7b"][population]["retention"])<1e-12
        labels=np.array(sorted(c.loc[base,"independence_group"].unique()))
        g=counts(c.independence_group,admit,bad,labels)
        result=minimum_risk_failure(g.a,g.b,.07)
        detail=annotate(result,labels,g.a.to_numpy(),g.b.to_numpy())
        removed=set(detail["removed_groups"].split(";")) if detail["removed_groups"] else set()
        remaining=base&~c.independence_group.isin(removed).to_numpy()
        # Show what reapplying the batch rule at this witness does. This is a
        # witness only, never called the exact minimum for the reapplied rule.
        reapplied=rule.admit(score[remaining],np.ones(remaining.sum()),alpha,factor)
        detail.update(population=population,full_risk=risk,full_retention=retention,n_groups=len(labels),risk_cap=.07,
                      reapplied_witness_risk=float(bad[remaining][reapplied].mean()) if reapplied.any() else np.nan,
                      reapplied_witness_retention=float(reapplied.mean()),
                      original_endpoint="N1 point risk <=7% and nonempty in both populations; CI descriptive",
                      evidence_status="already opened; fixed original admissions; original verdict unchanged")
        rows.append(detail)
    frame=pd.DataFrame(rows);frame.to_csv(DEST/"historical_N1_deletions.csv",index=False)
    return frame


def main():
    p=argparse.ArgumentParser();p.add_argument("--seeds",type=int,nargs="+",default=CONFIG["seeds"]);p.add_argument("--workers",type=int,default=8);p.add_argument("--skip-historical",action="store_true");a=p.parse_args()
    DEST.mkdir(parents=True,exist_ok=True)
    frames=Parallel(n_jobs=a.workers,verbose=10)(delayed(source)(seed) for seed in a.seeds)
    combined=pd.concat(frames,ignore_index=True);combined.to_csv(DEST/"group_deletions_all_seeds.csv",index=False)
    if not a.skip_historical:
        historical_n1()
    T.write_json(DEST/"summary.json",{"seeds":a.seeds,"scope":"exact independent-group deletions of frozen predictions and admissions; no refit; published baseline fixed before deletions","unknown_solutions":int(combined.status.eq("optimality_unproven").sum()),"historical_N1":"original point-risk endpoint reproduced; batch-rule witness reapplication is separate"})
    return 0


if __name__=="__main__":
    raise SystemExit(main())

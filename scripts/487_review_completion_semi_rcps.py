#!/usr/bin/env python3
"""Formal general-loss SS-RCPS comparator at independent-group label budgets."""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import json
import numpy as np
import pandas as pd
from joblib import Parallel,delayed
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed
from stream_recoverability.experiments.tr_revision.semisupervised import general_rcps,labeled_rcps

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text());OUT=T.ROOT/CONFIG["out"]
CANDIDATES=np.array([.01,.025,.05,.075,.1,.15,.2,.3])


def analyse(seed,repeats):
    rows=[]
    for region_index,path in enumerate(sorted((OUT/f"refits/leave_one_year_out/seed_{seed:02d}").glob("*.parquet"))):
        c=pd.read_parquet(path,columns=["independence_group","design_family","D2","eval_truth_h30","risk_score"])
        for family_index,family in enumerate(["calendar","crossed"]):
            target=c.loc[c.design_family.eq(family)].copy();units=np.array(sorted(target.independence_group.unique()))
            group=pd.Categorical(target.independence_group,categories=units).codes
            size=np.bincount(group,minlength=len(units));score=target.risk_score.to_numpy();failure=(target.D2-target.eval_truth_h30).abs().gt(.5).to_numpy()
            admitted=score[:,None]<=CANDIDATES[None,:]
            A=np.column_stack([np.bincount(group,weights=admitted[:,j],minlength=len(units))/size for j in range(len(CANDIDATES))])
            B=np.column_stack([np.bincount(group,weights=admitted[:,j]&failure,minlength=len(units))/size for j in range(len(CANDIDATES))])
            P=np.column_stack([np.bincount(group,weights=admitted[:,j]*score,minlength=len(units))/size for j in range(len(CANDIDATES))])
            loss=B+.05*(1-A);pseudo=P+.05*(1-A)
            # Same labeled group choices as script 470. The remaining groups
            # split into disjoint unlabeled calibration and untouched test.
            rng=np.random.default_rng(plain_seed(seed,region_index,family_index))
            for budget in [2,4,8,10,16,32,64]:
                if len(units)<=budget:continue
                for repetition in range(repeats):
                    chosen=rng.choice(units,budget,replace=False)
                    lab=np.array([int(np.flatnonzero(units==name)[0]) for name in chosen]);rest=np.flatnonzero(~np.isin(units,chosen))
                    # A separate stream keeps labeled choices identical to the
                    # existing comparator. IDs, not outcomes, fix this split.
                    split_rng=np.random.default_rng(plain_seed(87,seed,region_index,family_index,budget,repetition))
                    perm=split_rng.permutation(rest)
                    n_unlabel=budget*(len(rest)//(2*budget))
                    unlabel=perm[:n_unlabel];test=perm[n_unlabel:]
                    selections={"labeled_WSR_RCPS":labeled_rcps(loss[lab],CANDIDATES),
                                "semi_supervised_general_WSR_RCPS":general_rcps(loss[lab],pseudo[lab],pseudo[unlabel],CANDIDATES)}
                    for method,result in selections.items():
                        column=int(np.searchsorted(CANDIDATES,result["threshold"])) if np.isfinite(result["threshold"]) else None
                        a=A[test,column] if column is not None else np.zeros(len(test))
                        b=B[test,column] if column is not None else np.zeros(len(test))
                        case=target.independence_group.isin(units[test]).to_numpy();accept=case&(score<=result["threshold"])
                        rows.append(dict(seed=seed,region=path.stem,family=family,budget_groups=budget,repeat=repetition,method=method,
                                         certificate_status=result["status"],threshold=result["threshold"],n_distinct_unlabeled_calibration_groups=result["used_unlabeled_groups"],
                                         n_untouched_test_groups=len(test),retention_group_equal=float(a.mean()),
                                         selected_risk_group_equal=float(b.sum()/a.sum()) if a.sum() else np.nan,
                                         retention_case_weighted=float(accept.sum()/case.sum()),risk_case_weighted=float(failure[accept].mean()) if accept.any() else np.nan,
                                         n_admitted=int(accept.sum()),first_UCB=result["upper_bounds"][0] if result["upper_bounds"] else np.nan))
    dest=OUT/f"semi_rcps/seed_{seed:02d}";dest.mkdir(parents=True,exist_ok=True)
    frame=pd.DataFrame(rows);frame.to_csv(dest/"small_label_curve.csv",index=False)
    print(f"formal semi-supervised RCPS seed {seed}: {len(frame)} rows",flush=True)
    return seed


def main():
    p=argparse.ArgumentParser();p.add_argument("--seeds",type=int,nargs="+",default=CONFIG["seeds"]);p.add_argument("--workers",type=int,default=8);p.add_argument("--repeats",type=int,default=100);a=p.parse_args()
    Parallel(n_jobs=a.workers,verbose=10)(delayed(analyse)(seed,a.repeats) for seed in a.seeds)
    frames=[pd.read_csv(OUT/f"semi_rcps/seed_{seed:02d}/small_label_curve.csv") for seed in a.seeds]
    all_rows=pd.concat(frames,ignore_index=True)
    summary=all_rows.groupby(["family","method","budget_groups"]).agg(n_runs=("n_admitted","size"),nonempty_fraction=("n_admitted",lambda x:float(x.gt(0).mean())),retention=("retention_group_equal","mean"),risk_among_nonempty=("selected_risk_group_equal","mean"),unlabeled_budget_insufficient=("certificate_status",lambda x:float(x.eq("insufficient_distinct_unlabeled_groups").mean()))).reset_index()
    summary.to_csv(OUT/"semi_rcps/summary.csv",index=False)
    T.write_json(OUT/"semi_rcps/design.json",{"source":"Einbinder, Ringel, Romano arXiv:2412.11174v2 Algorithms 1 and 4","seeds":a.seeds,"repeats":a.repeats,"unit":"independent connected group, equal group weights","target":"E[B_g]/E[A_g] <= .05 via bounded loss B_g+.05(1-A_g)","testing":"fixed ascending threshold sequence; stop at first failure; delta .05","unlabeled":"distinct held-region groups, balanced disjoint blocks; leftovers by index discarded; test groups untouched","scope":"finite-sample result requires iid groups, labeled/unlabeled/test same distribution and source predictor fixed; no every-group or arbitrary-shift guarantee"})
    return 0


if __name__=="__main__":raise SystemExit(main())

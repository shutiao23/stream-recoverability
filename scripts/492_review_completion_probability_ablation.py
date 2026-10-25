#!/usr/bin/env python3
"""Separate global probability calibration from empirical group adjustment."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from pathlib import Path
import wrr_tr_common as T

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text());OUT=T.ROOT/CONFIG["out"]


def main():
    rows=[]
    for seed in CONFIG["seeds"]:
        paths=sorted((OUT/f"refits/leave_one_year_out/seed_{seed:02d}").glob("*.parquet"))
        c=pd.concat([pd.read_parquet(p,columns=["independence_group","design_family","D2","eval_truth_h30","risk_score","risk_score_calibrated","risk_score_group_adjusted"]) for p in paths],ignore_index=True)
        failure=(c.D2-c.eval_truth_h30).abs().gt(.5).to_numpy()
        for family,b in c.groupby("design_family"):
            mask=c.design_family.eq(family).to_numpy()
            for name,column in [("raw_classifier","risk_score"),("Platt_probability_calibration","risk_score_calibrated"),("Platt_plus_empirical_groups","risk_score_group_adjusted")]:
                a=mask&c[column].le(.1).to_numpy()
                g=pd.DataFrame({"group":c.loc[a,"independence_group"],"failure":failure[a]}).groupby("group").failure.agg(["size","mean"])
                valid=g.loc[g["size"].ge(20)]
                rows.append(dict(seed=seed,family=family,method=name,cap=.1,retention=float(a.sum()/mask.sum()),risk=float(failure[a].mean()) if a.any() else np.nan,
                                 n_evaluable_groups=len(valid),fraction_groups_above_10=float(valid["mean"].gt(.1).mean()) if len(valid) else np.nan,
                                 worst_group_risk=float(valid["mean"].max()) if len(valid) else np.nan))
    frame=pd.DataFrame(rows);dest=OUT/"probability_ablation";dest.mkdir(parents=True,exist_ok=True)
    frame.to_csv(dest/"per_seed.csv",index=False)
    summary=frame.groupby(["family","method"])[["retention","risk","fraction_groups_above_10","worst_group_risk"]].median().reset_index()
    summary.to_csv(dest/"summary.csv",index=False)
    T.write_json(dest/"design.json",{"seeds":CONFIG["seeds"],"decision":"same cap .1, same D2 point and identical evaluation cases","calibration":"Platt map and empirical group factors learned from source probability-calibration groups; held-region labels excluded","purpose":"isolate a global probability-map effect from extra overlapping-group adjustment; neither is the formal conditional-conformal method"})
    print(summary.to_string(index=False),flush=True)
    return 0


if __name__=="__main__":raise SystemExit(main())

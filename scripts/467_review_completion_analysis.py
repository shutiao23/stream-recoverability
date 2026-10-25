#!/usr/bin/env python3
"""Decision-time scorecard, utility, recovery discrimination and trend stresses."""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.special import expit
from scipy.stats import norm,t as student_t
from sklearn.metrics import roc_auc_score
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed
from stream_recoverability.experiments.tr_revision.statistics import ensemble_crps, interval_score, quantile_samples, lower_bound_trend, removal_count, event_metrics
from stream_recoverability.experiments.tr_revision.screening import published_rules

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]
LEVELS=(.05,.1,.25,.5,.75,.9,.95)
POINTS={"plug_in":"h30__policy","observed_days":"h30__observed_days","lookup_debias":"lookup_debias","functional_debias":"P2","distribution_regression":"D2","triage_hybrid":"triage_hybrid","MOVE1_annual":"h30__move1_annual","MOVE1_warm":"h30__move1_warm","MOVE1_H30":"h30__move1_h30","stochastic_regression":"h30__stochastic_regression","stochastic_regression_calibrated":"stochastic_cal_q50","air2stream3":"h30__air2stream3","air_state_simulation":"state_h30_q50","air_state_calibrated":"state_cal_q50"}


def load(seed,split):
    files=sorted((OUT/"refits"/split/f"seed_{seed:02d}").glob("*.parquet"))
    if not files:
        raise RuntimeError(f"No complete outer-region predictions for seed {seed}, {split}")
    frame=pd.concat([pd.read_parquet(f) for f in files],ignore_index=True)
    frame=apply_bridge_repairs(frame,seed,split)
    return frame


def apply_bridge_repairs(frame,seed,split):
    repair=OUT/"repairs"/split/f"seed_{seed:02d}.parquet"
    if repair.exists():
        updates=pd.read_parquet(repair)
        if len(updates):
            keys=["network_id","station_key","year","design_family","realization_id","policy_choice","mask_runs"]
            updates=updates.set_index(keys)
            positions=updates.index.get_indexer(pd.MultiIndex.from_frame(frame[keys]))
            good=positions>=0
            for column in ["h30__stochastic_regression","stochastic_h30_draws"]+[f"stochastic_h30_q{int(q*100):02d}" for q in LEVELS]:
                if column in updates:
                    frame.loc[frame.index[good],column]=updates.iloc[positions[good]][column].to_numpy()
    return frame


def calibrate_classical(c,seed,split):
    """Apply the identical disjoint calibration budget to simple distributions."""
    if split=="opened_transfer":
        return c
    import pyarrow.parquet as pq
    path=OUT/"cases"/split/f"seed_{seed:02d}.parquet"
    schema=pq.ParquetFile(path).schema_arrow.names
    keys=["network_id","station_key","year","design_family","realization_id","policy_choice","mask_runs"]
    columns=list(dict.fromkeys(keys+["independence_group","region","peak_overlap","eval_truth_h30","stochastic_h30_draws","h30__stochastic_regression"]+[f"{prefix}_h30_q{int(q*100):02d}" for prefix in ["stochastic","state"] for q in LEVELS]+(["training_partition"] if "training_partition" in schema else [])))
    source=pd.read_parquet(path,columns=columns)
    source=source.loc[source.policy_choice.ne("unavailable")&source.eval_truth_h30.notna()].reset_index(drop=True)
    source=apply_bridge_repairs(source,seed,split)
    refit=T.load_script("r4_classical_cal_roles",T.ROOT/"scripts/466_review_completion_refit.py")
    target_positions=pd.MultiIndex.from_frame(source[keys]).get_indexer(pd.MultiIndex.from_frame(c[keys]))
    if (target_positions<0).any():
        raise RuntimeError("Classical calibration cases do not match source identities")
    groups=refit.difficulty(source);regions=sorted(source.region.unique());truth=source.eval_truth_h30.to_numpy()
    outputs={prefix:np.full((len(c),len(LEVELS)),np.nan) for prefix in ["stochastic","state"]}
    qsource={prefix:source[[f"{prefix}_h30_q{int(q*100):02d}" for q in LEVELS]].to_numpy(float) for prefix in outputs}
    for region in sorted(c.region.unique()):
        _,role_groups,weights=refit.roles(source,region,plain_seed(7,seed,regions.index(region)))
        actual=json.loads((OUT/"refits"/split/f"seed_{seed:02d}"/f"{region}.json").read_text())
        if role_groups!=actual["roles"]:
            raise RuntimeError("Baseline calibration roles differ from the estimator roles")
        cal_weight=weights["interval_calibration"];held=c.region.eq(region).to_numpy()
        for prefix,q in qsource.items():
            valid=np.isfinite(q).all(axis=1);prediction=q[target_positions[held]].copy()
            target_groups=groups.iloc[target_positions[held]].to_numpy()
            for group in np.unique(target_groups):
                pool=(cal_weight>0)&valid&groups.eq(group).to_numpy()
                if pool.sum()<50:pool=(cal_weight>0)&valid
                if pool.sum()<2:continue
                residual=np.repeat(truth[pool,None]-q[pool],cal_weight[pool].astype(int),axis=0)
                offset=np.array([np.quantile(residual[:,j],level,method="higher" if level>=.5 else "lower") for j,level in enumerate(LEVELS)])
                prediction[target_groups==group]+=offset
            outputs[prefix][held]=np.sort(prediction,axis=1)
    for prefix,q in outputs.items():
        for j,level in enumerate(LEVELS):
            c[f"{prefix}_cal_q{int(100*level):02d}"]=q[:,j]
    return c


def stratification(c):
    strata={"all":np.ones(len(c),bool),"danger":c.peak_overlap.ge(.5).to_numpy(),"decision_hot_danger":(c.peak_overlap.ge(.5)&c.decision_hot).to_numpy()}
    bins=np.where(c.peak_overlap<=0,0,np.searchsorted([0,.25,.5,.75,1],c.peak_overlap,side="left"))
    for b in range(5):
        for layer in sorted(c.policy_choice.unique()):
            strata[f"overlap{b}|{layer}"]=(bins==b)&c.policy_choice.eq(layer).to_numpy()
    return strata


def retained_at_risk(score,fail,cap=.05):
    keep=np.isfinite(score)
    if not keep.any():
        return np.nan
    s,f=np.asarray(score)[keep],np.asarray(fail)[keep]
    order=np.argsort(s,kind="mergesort")
    risk=np.cumsum(f[order])/np.arange(1,len(order)+1)
    tied_end=np.r_[s[order][1:]!=s[order][:-1],True]
    valid=np.flatnonzero((risk<=cap)&tied_end)
    return float((valid[-1]+1)/len(score)) if len(valid) else 0.


def point_metrics(error):
    return {"bias":float(np.mean(error)),"mae":float(np.mean(np.abs(error))),"failure_rate":float(np.mean(np.abs(error)>.5))}


def scorecard(c,seed):
    truth=c.eval_truth_h30.to_numpy()
    strata=stratification(c)
    rows,pairs,events,units,distribution_pairs=[],[],[],[],[]
    d2_sample=quantile_samples(c[[f"D2_q{int(q*100):02d}" for q in LEVELS]].to_numpy(),LEVELS)
    d2_crps=ensemble_crps(d2_sample,truth)
    d2_twcrps=ensemble_crps(d2_sample,truth,c.train_h30_q90.to_numpy())
    for name,column in POINTS.items():
        if column not in c:
            continue
        point=c[column].to_numpy(dtype=float)
        sample=None
        if name=="distribution_regression":
            sample=d2_sample
        elif name=="stochastic_regression" and "stochastic_h30_draws" in c:
            sample=np.vstack([np.asarray(v,float) if np.ndim(v)==1 and len(v)==20 else np.full(20,np.nan) for v in c.stochastic_h30_draws])
        elif name=="air_state_simulation":
            sample=quantile_samples(c[[f"state_h30_q{int(q*100):02d}" for q in LEVELS]].to_numpy(),LEVELS)
        elif name in ["stochastic_regression_calibrated","air_state_calibrated"]:
            prefix="stochastic" if name.startswith("stochastic") else "state"
            sample=quantile_samples(c[[f"{prefix}_cal_q{int(q*100):02d}" for q in LEVELS]].to_numpy(),LEVELS)
        if sample is not None:
            crps=ensemble_crps(sample,truth)
            twcrps=ensemble_crps(sample,truth,c.train_h30_q90.to_numpy())
            low,high=np.quantile(sample,[.05,.95],axis=1)
            iscore=interval_score(low,high,truth)
        for family in ("calendar","crossed"):
            base=c.design_family.eq(family).to_numpy()
            for stratum,s in strata.items():
                eligible=base&s
                valid=eligible&np.isfinite(point)
                if not valid.any():
                    if eligible.any():
                        rows.append({"seed":seed,"family":family,"stratum":stratum,"estimator":name,"n":0,"eligible":int(eligible.sum()),"availability":0.,"bias":np.nan,"mae":np.nan,"failure_rate":np.nan})
                    continue
                row={"seed":seed,"family":family,"stratum":stratum,"estimator":name,"n":int(valid.sum()),"eligible":int(eligible.sum()),"availability":float(valid.sum()/eligible.sum()),**point_metrics(point[valid]-truth[valid])}
                if sample is not None:
                    good=valid&np.isfinite(crps)
                    if good.any():
                        row.update(crps=float(np.mean(crps[good])),twcrps=float(np.mean(twcrps[good])),interval_score90=float(np.mean(iscore[good])),coverage90=float(np.mean((truth[good]>=low[good])&(truth[good]<=high[good]))),width90=float(np.mean(high[good]-low[good])))
                rows.append(row)
            valid=base&np.isfinite(point)
            for scope,s in [("all",np.ones(len(c),bool)),("danger",c.peak_overlap.ge(.5).to_numpy()),("heatwave_2003_2018_2022",c.year.isin([2003,2018,2022]).to_numpy())]:
                selected=valid&s
                if selected.any():
                    events.append({"seed":seed,"family":family,"estimator":name,"scope":scope,"n":int(selected.sum()),**event_metrics(truth[selected]>c.train_h30_q90.to_numpy()[selected],point[selected]>c.train_h30_q90.to_numpy()[selected])})
            if name!="distribution_regression":
                common=base&c.peak_overlap.ge(.5).to_numpy()&np.isfinite(point)&np.isfinite(c.D2)
                per=pd.DataFrame({"station":c.station_key,"group":c.independence_group,"delta":np.abs(c.D2-truth)-np.abs(point-truth),"ref":np.abs(point-truth),"selected":common}).loc[lambda f:f.selected]
                for unit in ["station","group"]:
                    b=per.groupby(unit)[["delta","ref"]].mean()
                    units.extend(dict(seed=seed,family=family,reference=name,unit=unit,unit_id=str(index),paired_mae_difference=float(r.delta),reference_mae=float(r.ref)) for index,r in b.iterrows())
                    pairs.append({"seed":seed,"family":family,"reference":name,"unit":unit,"n_units":len(b),"fraction_D2_no_worse":float((b.delta<=0).mean()),"mean_paired_mae_difference":float(b.delta.mean()),"median_relative_mae_change":float((b.delta/b.ref.replace(0,np.nan)).median())})
                    pairs[-1].update(case_mae_D2=float((per.ref+per.delta).mean()),case_mae_reference=float(per.ref.mean()),case_relative_reduction=float(-per.delta.mean()/per.ref.mean()) if per.ref.mean()>0 else np.nan)
                if sample is not None:
                    selected=base&c.peak_overlap.ge(.5).to_numpy()&np.isfinite(crps)&np.isfinite(d2_crps)
                    distribution_pairs.append(dict(seed=seed,family=family,reference=name,n_common=int(selected.sum()),crps_D2=float(d2_crps[selected].mean()),crps_reference=float(crps[selected].mean()),crps_difference=float((d2_crps[selected]-crps[selected]).mean()),twcrps_difference=float((d2_twcrps[selected]-twcrps[selected]).mean())))
    return pd.DataFrame(rows),pd.DataFrame(pairs),pd.DataFrame(events),pd.DataFrame(units),pd.DataFrame(distribution_pairs)


def rule_analysis(c,seed):
    fail=(c.D2-c.eval_truth_h30).abs().gt(.5).to_numpy()
    methods={"all":np.ones(len(c),bool),"none":np.zeros(len(c),bool),"one_feature_25":c.peak_overlap.lt(.25).to_numpy(),"one_feature_50":c.peak_overlap.lt(.5).to_numpy(),"warm_90":c.warm_observed_fraction.ge(.9).to_numpy(),"gap_49":c.longest_run.le(49).to_numpy()}
    fixed_published=published_rules(c)
    methods.update({"published_"+name:value for name,value in fixed_published.items()})
    methods.update({f"individual_{cap:g}":c.risk_score.le(cap).to_numpy() for cap in CONFIG["individual_caps"]})
    methods["individual_group_adjusted"]=c.risk_score_group_adjusted.le(.1).to_numpy()
    for col in c:
        if col.startswith("admit_"):
            methods[col.removeprefix("admit_")]=c[col].to_numpy(bool)
    rows,groups,economic=[],[],[]
    for family in ("calendar","crossed"):
        base=c.design_family.eq(family).to_numpy()
        # Same deployment decision set and same delivered value for all rules.
        for name,admit in methods.items():
            a=admit&base
            g=pd.DataFrame({"group":c.loc[a,"independence_group"],"fail":fail[a]}).groupby("group").fail.agg(["size","mean"])
            g=g.loc[g["size"]>=20]
            for group,v in g.iterrows():
                groups.append(dict(seed=seed,family=family,rule=name,group=group,n_admitted=int(v["size"]),risk=float(v["mean"])))
            rows.append(dict(seed=seed,family=family,rule=name,delivery="distribution_regression",n_total=int(base.sum()),n_admitted=int(a.sum()),retention=float(a.sum()/base.sum()),risk=float(fail[a].mean()) if a.any() else np.nan,n_groups_evaluable=len(g),fraction_groups_above_7=float((g["mean"]>.07).mean()) if len(g) else np.nan,fraction_groups_above_10=float((g["mean"]>.1).mean()) if len(g) else np.nan,worst_group_risk=float(g["mean"].max()) if len(g) else np.nan,max_admitted_probability=float(c.loc[a,"risk_score"].max()) if a.any() else np.nan,failures_per_1000=float(1000*np.mean(admit[base]&fail[base]))))
        for delivery,column in [("plug_in","h30__policy"),("observed_days","h30__observed_days")]:
            value=c[column].to_numpy();available=np.isfinite(value)
            local_fail=np.abs(value-c.eval_truth_h30.to_numpy())>.5
            for name,admit in {**{"published_"+k:v for k,v in fixed_published.items()},"one_feature_25":methods["one_feature_25"],"one_feature_50":methods["one_feature_50"]}.items():
                a=base&admit&available
                g=pd.DataFrame({"group":c.loc[a,"independence_group"],"failure":local_fail[a]}).groupby("group").failure.agg(["size","mean"]);g=g.loc[g["size"]>=20]
                rows.append(dict(seed=seed,family=family,rule=name,delivery=delivery,n_total=int(base.sum()),n_admitted=int(a.sum()),retention=float(a.sum()/base.sum()),risk=float(local_fail[a].mean()) if a.any() else np.nan,n_groups_evaluable=len(g),fraction_groups_above_7=float(g["mean"].gt(.07).mean()) if len(g) else np.nan,fraction_groups_above_10=float(g["mean"].gt(.1).mean()) if len(g) else np.nan,worst_group_risk=float(g["mean"].max()) if len(g) else np.nan,max_admitted_probability=np.nan,failures_per_1000=float(1000*(a&local_fail).sum()/base.sum())))
        for ratio in np.geomspace(.1,100,31):
            best_reference=min(float(ratio*fail[base].mean()),float((~fail[base]).mean()))
            for name,admit in methods.items():
                loss=float(np.mean(ratio*(admit[base]&fail[base])+(~admit[base]&~fail[base])))
                economic.append(dict(seed=seed,family=family,cost_ratio=float(ratio),rule=name,loss=loss,relative_economic_value=1-loss/best_reference if best_reference>0 else np.nan))
            economic.append(dict(seed=seed,family=family,cost_ratio=float(ratio),rule="cost_optimal_from_score",loss=float(np.mean(ratio*((c.risk_score.to_numpy()[base]<=1/(1+ratio))&fail[base])+((c.risk_score.to_numpy()[base]>1/(1+ratio))&~fail[base]))),relative_economic_value=np.nan))
    return pd.DataFrame(rows),pd.DataFrame(groups),pd.DataFrame(economic)


def recovery_analysis(c,seed):
    rows=[]
    f0=(c.h30__policy-c.eval_truth_h30).abs().gt(.5).to_numpy()
    f2=(c.D2-c.eval_truth_h30).abs().gt(.5).to_numpy()
    for family in ("calendar","crossed"):
        for scope,subset in [("all",np.ones(len(c),bool)),("danger",c.peak_overlap.ge(.5).to_numpy())]:
            for name,column,label in [("one_feature","peak_overlap",f0),("lookup","lookup_pfail",f0),("recovery_model","recovery_probability",f0),("recovery_t5","recovery_probability_t5",f0),("risk_classifier","risk_score",f2)]:
                s=c[column].to_numpy()
                valid=c.design_family.eq(family).to_numpy()&subset&np.isfinite(s)
                if valid.sum()<20 or np.unique(label[valid]).size<2:
                    continue
                y,p=label[valid],s[valid]
                base=y.mean()
                total=c.design_family.eq(family).to_numpy()&subset
                rows.append(dict(seed=seed,family=family,scope=scope,model=name,n=int(valid.sum()),availability=float(valid.sum()/max(total.sum(),1)),auc=float(roc_auc_score(y,p)),brier=float(np.mean((p-y)**2)),brier_skill=1-float(np.mean((p-y)**2))/(base*(1-base)),diagnostic_retention_at_5=retained_at_risk(p,y)))
            for name,column,label in [("oracle_plugin","h30__policy",f0),("oracle_D2","D2",f2)]:
                error=(c[column]-c.eval_truth_h30).abs().to_numpy()
                valid=c.design_family.eq(family).to_numpy()&subset&np.isfinite(error)
                if valid.any():
                    rows.append(dict(seed=seed,family=family,scope=scope,model=name,n=int(valid.sum()),auc=1. if np.unique(label[valid]).size==2 else np.nan,diagnostic_retention_at_5=retained_at_risk(error[valid],label[valid]),information="hidden-label oracle, diagnostic upper benchmark"))
        cell=c.loc[c.design_family.eq(family)].groupby(["gap_length","difficulty"])
        aucs,counts=[],[]
        for _,block in cell:
            valid=block.recovery_probability.notna()
            y=(block.loc[valid,"h30__policy"]-block.loc[valid,"eval_truth_h30"]).abs().gt(.5)
            if len(y)>=200 and y.nunique()==2:
                aucs.append(roc_auc_score(y,block.loc[valid,"recovery_probability"]))
                counts.append(len(y))
        if counts:
            rows.append(dict(seed=seed,family=family,scope="within_cell",model="recovery_model",n=sum(counts),auc=float(np.average(aucs,weights=counts)),n_cells=len(counts)))
    return pd.DataFrame(rows)


def archive_per_1000(c,seed):
    """Post-stratify to actual incomplete years; unsupported mass stays unknown."""
    real=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e9_application/real_year_estimates.parquet",columns=["provider","policy_choice","peak_overlap"])
    def cell(frame):
        overlap=np.where(frame.peak_overlap.eq(0),"zero",np.where(frame.peak_overlap.lt(.5),"partial","danger"))
        return frame.provider.astype(str)+"|"+frame.policy_choice.astype(str)+"|"+overlap
    calendar=c.loc[c.design_family.eq("calendar")].copy()
    target_share=cell(real).value_counts(normalize=True)
    strata=cell(calendar);counts=strata.value_counts()
    weight=strata.map(target_share/counts).fillna(0).to_numpy()
    supported=float(weight.sum())
    decisions={"all":np.ones(len(calendar),bool),"one_feature_25":calendar.peak_overlap.lt(.25).to_numpy(),"one_feature_50":calendar.peak_overlap.lt(.5).to_numpy(),"warm90":calendar.warm_observed_fraction.ge(.9).to_numpy()}
    decisions.update({f"individual_{cap:g}":calendar.risk_score.le(cap).to_numpy() for cap in CONFIG["individual_caps"]})
    rows=[]
    for delivery,column in [("plug_in","h30__policy"),("observed_days","h30__observed_days"),("distribution_regression","D2"),("triage_hybrid","triage_hybrid")]:
        value=calendar[column].to_numpy();truth=calendar.eval_truth_h30.to_numpy()
        finite=np.isfinite(value)&np.isfinite(truth)
        for rule,admit in decisions.items():
            # The score estimates D2 failure. Do not use it as if it estimated
            # observed-day or plug-in failure probabilities.
            if rule.startswith("individual_") and delivery!="distribution_regression":
                continue
            used=admit&finite
            delivered=float(weight[used].sum())
            failed=float(np.sum(weight[used]*(np.abs(value[used]-truth[used])>.5)))
            rows.append(dict(seed=seed,delivery=delivery,rule=rule,used_per_1000=1000*delivered,failures_per_1000=1000*failed,risk=failed/delivered if delivered>0 else np.nan,expected_absolute_error_among_used=float(np.average(np.abs(value[used]-truth[used]),weights=weight[used])) if delivered>0 else np.nan,unsupported_population_per_1000=1000*(1-supported),unavailable_prediction_per_1000=float(1000*weight[admit&~finite].sum())))
    return pd.DataFrame(rows)


def group_coverage_curve(c,seed):
    failure=(c.D2-c.eval_truth_h30).abs().gt(.5).to_numpy()
    rows=[]
    for family in ["calendar","crossed"]:
        family_mask=c.design_family.eq(family).to_numpy()
        for model,column in [("raw_classifier","risk_score"),("overlap_group_adjustment","risk_score_group_adjusted")]:
            score=c[column].to_numpy()
            for threshold in np.r_[np.linspace(0,.3,31),.5,1.]:
                accept=family_mask&(score<=threshold)
                groups=pd.DataFrame({"group":c.loc[accept,"independence_group"],"failure":failure[accept]}).groupby("group").failure.agg(["size","mean"])
                groups=groups.loc[groups["size"]>=20]
                rows.append(dict(seed=seed,family=family,score=model,threshold=threshold,retention=float(accept.sum()/family_mask.sum()),overall_risk=float(failure[accept].mean()) if accept.any() else np.nan,worst_group_risk=float(groups["mean"].max()) if len(groups) else np.nan,n_evaluable_groups=len(groups),fraction_groups_above_10=float(groups["mean"].gt(.1).mean()) if len(groups) else np.nan))
    return pd.DataFrame(rows)


def specification_sensitivity(c,seed):
    rows=[]
    for target in ["h7","h30"]:
        truth=c[f"eval_truth_{target}"].to_numpy()
        for estimator,column in [("plug_in",f"{target}__policy"),("observed_days",f"{target}__observed_days")]+([("distribution_regression","D2"),("functional_debias","P2")] if target=="h30" else []):
            for tolerance in [.25,.5,1.]:
                for cap in [.05,.1,.2,.3]:
                    valid=c.design_family.eq("calendar").to_numpy()&np.isfinite(c[column])
                    if target=="h30" and estimator=="distribution_regression":
                        valid&=c.risk_score.le(cap).to_numpy()
                    for overlap_cutoff in [.25,.5,.75,1.01]:
                        a=valid&c.peak_overlap.lt(overlap_cutoff).to_numpy()
                        error=c[column].to_numpy()[a]-truth[a]
                        rows.append(dict(seed=seed,window_days=7 if target=="h7" else 30,estimator=estimator,tolerance=tolerance,score_cap=cap,overlap_cutoff=overlap_cutoff,n=int(a.sum()),risk=float(np.mean(np.abs(error)>tolerance)) if len(error) else np.nan,mae=float(np.mean(np.abs(error))) if len(error) else np.nan,interpretation="fixed predictions and source H30 .5-degree score; changed tolerances/windows are descriptive sensitivities, not recalibrated guarantees"))
    return pd.DataFrame(rows)


def primary_analogues(c,seed):
    """Registered-style quantities under the redesigned split, explicitly exploratory."""
    selected=c.design_family.eq("crossed")&c.policy_choice.eq("air_ridge")&c.eval_true_peak_hidden_fraction.ge(.5)
    b=c.loc[selected]
    e0=b.h30__policy-b.eval_truth_h30
    rows=[]
    for version,point,low,high in [("raw_redesign","D2_raw","D2_raw_q05","D2_raw_q95"),("calibrated_redesign","D2","D2_q05","D2_q95")]:
        error=b[point]-b.eval_truth_h30
        reduction=1-abs(float(error.mean()))/abs(float(e0.mean())) if len(b) and abs(e0.mean())>0 else np.nan
        coverage=float(((b.eval_truth_h30>=b[low])&(b.eval_truth_h30<=b[high])).mean())
        rows.append(dict(seed=seed,endpoint="P1_analogue",version=version,n=len(b),bias_plugin=float(e0.mean()),bias=float(error.mean()),reduction=reduction,coverage90=coverage,criterion_met=bool(reduction>=.5 and .85<=coverage<=.95),historical_registered_verdict="unchanged, not met; these refits are exploratory"))
    b=c.loc[c.design_family.eq("calendar")]
    fail0=(b.h30__policy-b.eval_truth_h30).abs().gt(.5).to_numpy();fail2=(b.D2-b.eval_truth_h30).abs().gt(.5).to_numpy()
    lower=retained_at_risk(1-b.warm_observed_fraction.to_numpy(),fail0)
    upper=retained_at_risk(b.risk_score.to_numpy(),fail2)
    rows.append(dict(seed=seed,endpoint="P2_analogue",version="diagnostic equal-realized-risk ranking",retention_baseline=lower,retention_learned=upper,gain=upper-lower,criterion_met=bool(upper-lower>=.1),historical_registered_verdict="unchanged, not met; thresholds here use evaluation labels and are diagnostic"))
    return pd.DataFrame(rows)


def station_trends(block,seed,replicates=200,scenarios=None,include_censored=True):
    station=block.station_key.iloc[0]
    years=np.array(sorted(block.year.unique()))
    if len(years)<20:
        return []
    b=[block.loc[block.year.eq(y)] for y in years]
    truth=np.array([v.eval_truth_h30.iloc[0] for v in b])
    air=np.array([v.air_warm_z_mean.iloc[0] for v in b])
    x=(years-years.mean())/10
    xx=np.dot(x,x)
    slope=float(np.dot(x,truth)/xx)
    rng=np.random.default_rng(plain_seed(seed,int(block.index.min()),8))
    rows=[]
    hot_air=air>=np.nanquantile(air,.9)
    strong_probability=np.where(hot_air,.9,.18)
    matched_marginal=float(strong_probability.mean())
    for scenario in (scenarios or ["mcar","strong_heat","non_air_trend"]):
        probability=np.full(len(years),matched_marginal)
        extra=np.zeros(len(years))
        if scenario=="strong_heat":
            probability=strong_probability.copy()
        if scenario=="non_air_trend":
            extra=.2*x
        expected_slope=slope+(.2 if scenario=="non_air_trend" else 0)
        y=truth+extra
        for rep in range(replicates):
            missing=rng.random(len(years))<probability
            selected=[v.iloc[int(rng.integers(len(v)))] for v in b]
            keep=np.array([r.warm_observed_fraction>=.9 for r in selected])|~missing
            observed=np.array([r.h30__observed_days for r in selected])+extra
            plug=np.array([r.h30__policy for r in selected])
            d2=np.array([r.D2 for r in selected])
            # The original imputation does not condition on the added trend:
            # it receives no synthetic target offset for missing days/years.
            lower=np.array([r["observed_lower_bound__observed_days"] for r in selected])+extra
            exact=np.where(missing,np.nan,y)
            methods=["A0","A1","plug_in","MOVE1_warm","D2_multiple_imputation","stochastic_regression_MI","stochastic_calibrated_MI"]
            if include_censored:methods.append("censored_trend")
            for method in methods:
                n=len(years)
                critical=1.96
                missing_cover=np.nan
                if method=="censored_trend":
                    fit=lower_bound_trend(years,exact,lower)
                    estimate,se=fit["slope"],fit["se"]
                    n=fit["n_exact"]+fit["n_censored"]
                elif method in ["D2_multiple_imputation","stochastic_regression_MI","stochastic_calibrated_MI"]:
                    if method in ["D2_multiple_imputation","stochastic_calibrated_MI"]:
                        prefix="D2" if method=="D2_multiple_imputation" else "stochastic_cal"
                        q=np.array([[r.get(f"{prefix}_q{int(level*100):02d}",np.nan) for level in LEVELS] for r in selected])
                        u=rng.random((CONFIG["multiple_imputations"],len(years)))
                        draws=np.column_stack([np.interp(u[:,j],LEVELS,q[j]) for j in range(len(years))])
                    else:
                        if any("stochastic_h30_draws" not in r for r in selected):
                            continue
                        draws=np.column_stack([rng.choice(np.asarray(r.stochastic_h30_draws),CONFIG["multiple_imputations"],replace=True) for r in selected])
                    draws[:,~missing]=y[~missing]
                    slopes=draws@x/xx
                    estimate=float(slopes.mean())
                    within=np.mean(np.sum((draws-draws.mean(axis=1)[:,None]-slopes[:,None]*x)**2,axis=1)/(len(x)-2)/xx)
                    between=np.var(slopes,ddof=1)
                    total=within+(1+1/len(draws))*between
                    se=float(np.sqrt(total))
                    gamma=(1+1/len(draws))*between/max(total,1e-12)
                    complete_df=len(years)-2
                    rubin_df=(len(draws)-1)/max(gamma,1e-12)**2
                    observed_df=(complete_df+1)/(complete_df+3)*complete_df*(1-gamma)
                    df=1/(1/rubin_df+1/max(observed_df,1e-12))
                    critical=float(student_t.ppf(.975,min(df,1e6)))
                    missing_se=np.sqrt((1+1/len(draws))*between)
                    missing_cover=bool(abs(estimate-expected_slope)<=1.96*missing_se) if missing_se>0 else bool(abs(estimate-expected_slope)<1e-9)
                else:
                    valid=~missing if method=="A0" else keep if method=="A1" else np.ones(n,bool)
                    z=y.copy()
                    if method=="A1":
                        z[missing]=observed[missing]
                    elif method=="plug_in":
                        z[missing]=plug[missing]
                    elif method=="MOVE1_warm":
                        alternate=np.array([r.get("h30__move1_warm",np.nan) for r in selected])
                        z[missing]=alternate[missing]
                    valid&=np.isfinite(z)
                    n=int(valid.sum())
                    if n<5 or np.ptp(x[valid])==0:
                        estimate=se=np.nan
                    else:
                        xv=x[valid]-x[valid].mean()
                        estimate=float(xv@z[valid]/(xv@xv))
                        se=float(np.sqrt(np.sum((z[valid]-z[valid].mean()-estimate*xv)**2)/(n-2)/(xv@xv)))
                rows.append(dict(seed=seed,station=station,group=block.independence_group.iloc[0],region=block.region.iloc[0],scenario=scenario,replicate=rep,pipeline=method,n_years=n,slope=estimate,full_slope=expected_slope,error=estimate-expected_slope,se=se,coverage=bool(abs(estimate-expected_slope)<=critical*se) if np.isfinite(estimate+se) else np.nan,missing_component_coverage=missing_cover))
    return rows


def analyse(seed,split,replicates,skip_trends=False):
    c=load(seed,split)
    c=calibrate_classical(c,seed,split)
    c["triage_hybrid"]=np.where(c.peak_overlap.lt(.5),c.h30__policy,c.D2)
    folder=OUT/"analyses"/split/f"seed_{seed:02d}"
    folder.mkdir(parents=True,exist_ok=True)
    tables={}
    cohorts=list(c.groupby("evaluation_dataset")) if split=="opened_transfer" else [("source",c)]
    for dataset,cohort in cohorts:
        score,pairs,events,units,distribution_pairs=scorecard(cohort,seed)
        rules,groups,economic=rule_analysis(cohort,seed)
        recovery=recovery_analysis(cohort,seed)
        for name,table in [("scorecard",score),("paired_effects",pairs),("distribution_paired_effects",distribution_pairs),("events",events),("unit_paired_effects",units),("rules",rules),("group_risks",groups),("economic_value",economic),("recovery",recovery),("primary_analogues",primary_analogues(cohort,seed))]:
            table["dataset"]=dataset
            tables.setdefault(name,[]).append(table)
    for name,parts in tables.items():
        pd.concat(parts,ignore_index=True).to_csv(folder/f"{name}.csv",index=False)
    if split=="leave_one_year_out":
        archive_per_1000(c,seed).to_csv(folder/"archive_per_1000.csv",index=False)
        group_coverage_curve(c,seed).to_csv(folder/"group_risk_coverage_curve.csv",index=False)
        specification_sensitivity(c,seed).to_csv(folder/"specification_sensitivity.csv",index=False)
    if not skip_trends:
        output=[]
        for _,block in c.loc[c.design_family.eq("calendar")].groupby("station_key"):
            output.extend(station_trends(block,seed,replicates,scenarios=["mcar","strong_heat"] if split=="non_air_refit" else None))
        pd.DataFrame(output).to_parquet(folder/"trends.parquet",index=False)
    T.write_json(folder/"summary.json",{"seed":seed,"split":split,"analysis_version":CONFIG["analysis_version"],"n_cases":len(c),"n_groups":int(c.independence_group.nunique()),"n_stations":int(c.station_key.nunique()),"case_score_convention":"128 midpoint samples of stored quantiles, constant tails outside .05-.95; exact ensemble score for stochastic regression","baseline_calibration":"same disjoint source calibration roles, bootstrap multiplicities and difficulty offsets as D2","trend_missingness":"station-specific marginal matched to the .9/.18 heat-associated scenario","complete":True,"trend_replicates":0 if skip_trends else replicates})
    print(f"analysed seed {seed}, {len(c)} cases",flush=True)
    return seed


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seeds",nargs="+",type=int,default=CONFIG["seeds"])
    p.add_argument("--split",default="leave_one_year_out")
    p.add_argument("--workers",type=int,default=16)
    p.add_argument("--replicates",type=int,default=CONFIG["trend_replicates"])
    p.add_argument("--skip-trends",action="store_true")
    a=p.parse_args()
    Parallel(n_jobs=a.workers,verbose=10)(delayed(analyse)(s,a.split,a.replicates,a.skip_trends) for s in a.seeds)
    return 0


if __name__=="__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Rebuild source risk fitting, target scores, selections and aggregates.

The same source cases, target archives and feature code are used. This checks
reproduction and group separation, not independent data or a risk guarantee.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import json
from pathlib import Path
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
M=T.load_script('projected_risk_audit_inputs',ROOT/'scripts/701_projected_risk_fit.py')
KEY=['family','station_key','replicate','year']

def independent_cutoff(score,groups):
    g=pd.Series(groups).reset_index(drop=True)
    n=g.map(g.value_counts()).to_numpy(float)
    weight=1/n
    choices=[(abs(0.-.8),0.,None)]
    s=np.asarray(score,float)
    for value in np.unique(s):
        rate=float(weight[s<=value].sum()/weight.sum())
        choices.append((abs(rate-.8),rate,float(value)))
    return min(choices,key=lambda x:(x[0],x[1]))[1:]

def check_source(plan):
    inference=T.load_script('projected_risk_audit_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    repair=T.load_script('projected_risk_audit_repair',ROOT/'scripts/467_review_completion_analysis.py')
    raw=pd.read_parquet(M.INPUT/'candidate_cases/before_2010/seed_00.parquet')
    forbidden={r:set(g.independence_group) for r,g in raw.groupby('region')}
    source=raw[raw.policy_choice.ne('unavailable')&raw.eval_truth_h30.notna()&raw.training_partition.eq('train')].reset_index(drop=True)
    if source.year.ge(2010).any():raise ValueError('Source year cutoff failed')
    source=repair.apply_bridge_repairs(source,0,'before_2010')
    support=pd.read_csv(M.OUT/'source_support.csv').set_index('region')
    cutoffs=pd.read_csv(M.OUT/'source_cutoffs.csv').set_index(['region','family'])
    roster=pd.read_csv(M.PRIVATE/'roster.csv'); max_difference=0.;cutoff_checks=0
    for index,region in enumerate(sorted(roster.region.unique())):
        bundle=joblib.load(M.INPUT/'refits/before_2010/seed_00'/f'{region}.joblib')
        cal=json.loads((M.INPUT/'calibrations/forward'/f'{region}.json').read_text());bundle['offsets']=cal['D2_offsets']
        roles={k:set(v) for k,v in bundle['roles'].items()}
        target_groups=set(roster.loc[roster.region.eq(region),'independence_group'])
        for role,groups in roles.items():
            if groups & forbidden.get(region,set()):raise ValueError('Target region source overlap')
            if groups & target_groups:raise ValueError('Target connected group source overlap')
            if any(groups & roles[other] for other in roles if other!=role):raise ValueError('Source roles overlap')
        training=source[source.independence_group.isin(roles['risk_learning'])].copy()
        train=inference.predict(training,bundle)
        train=train[np.isfinite(train.D2.to_numpy(float)) & np.isfinite(train.eval_truth_h30.to_numpy(float))].copy()
        y=(np.abs(train.D2.to_numpy(float)-train.eval_truth_h30.to_numpy(float))>.5).astype(int)
        expected=support.loc[region]
        if len(train)!=expected.training_cases or train.independence_group.nunique()!=expected.training_groups or y.sum()!=expected.training_events or (y==0).sum()!=expected.training_nonevents:
            raise ValueError('Source training support differs')
        counts=train.independence_group.map(train.independence_group.value_counts()).to_numpy(float)
        w=1/counts;w=w*len(w)/w.sum()
        totals=pd.DataFrame({'group':train.independence_group.to_numpy(),'weight':w}).groupby('group').weight.sum()
        if not np.allclose(totals,totals.iloc[0],rtol=0,atol=1e-10):raise ValueError('Training group weights differ')
        params=dict(plan['model_parameters']);params.pop('random_seed');params['random_state']=700+index
        rebuilt=lgb.LGBMClassifier(**params)
        rebuilt.fit(M.features(train,bundle),y,sample_weight=w)
        saved=joblib.load(M.PRIVATE/'models'/f'{region}.joblib')
        rule=source[source.independence_group.isin(roles['rule_calibration'])].copy()
        prediction=inference.predict(rule,bundle)
        X=M.features(prediction,bundle).reindex(columns=saved['features'])
        old=saved['model'].predict_proba(X)[:,1];new=rebuilt.predict_proba(X)[:,1]
        difference=float(np.max(np.abs(old-new))) if len(old) else 0.
        max_difference=max(max_difference,difference)
        if not np.allclose(old,new,rtol=0,atol=1e-12):raise ValueError('Rebuilt source classifier predictions differ')
        prediction['projected_score']=new
        for family in ['calendar','crossed']:
            c=prediction[prediction.design_family.eq(family)]
            valid=np.isfinite(c.D2.to_numpy(float))&np.isfinite(c.risk_score.to_numpy(float))&np.isfinite(c.projected_score.to_numpy(float))
            c=c.loc[valid];row=cutoffs.loc[(region,family)]
            if len(c)!=row.rule_cases or c.independence_group.nunique()!=row.rule_groups:raise ValueError('Rule source support differs')
            for name,scorecol in [('original','risk_score'),('projected','projected_score')]:
                rate,value=independent_cutoff(c[scorecol].to_numpy(float),c.independence_group.to_numpy())
                if not np.isclose(value,row[name+'_cutoff'],rtol=0,atol=1e-12) or not np.isclose(rate,row[name+'_source_rate'],rtol=0,atol=1e-12):raise ValueError('Source cutoff differs')
                cutoff_checks+=1
    return {'source_models_refitted':len(roster.region.unique()),'source_family_cutoffs_checked':cutoff_checks,'max_source_model_score_difference':max_difference}

def check_target(plan):
    t=pd.read_parquet(M.PRIVATE/'target_scores.parquet')
    if t.duplicated(KEY).any():raise ValueError('Duplicate saved target')
    saved=t.set_index(KEY);roster=pd.read_csv(M.PRIVATE/'roster.csv').set_index('station_key')
    models={r:joblib.load(M.PRIVATE/'models'/f'{r}.joblib') for r in sorted(roster.region.unique())}
    bundles={r:joblib.load(M.INPUT/'refits/before_2010/seed_00'/f'{r}.joblib') for r in models}
    paths=sorted(p for family in ('calendar','crossed') for p in (M.INPUT/'whole_archive'/family/'forward').glob('replicate_*/*/annual_predictions.parquet'))
    count=0;missing_count=0
    for path in paths:
        family,_,rep,_=path.relative_to(M.INPUT/'whole_archive').parts[:4]
        design=json.loads((path.parent/'design.json').read_text());station=design['station_key'];replicate=int(rep.removeprefix('replicate_'))
        region=roster.loc[station,'region'];group=roster.loc[station,'independence_group']
        all_years=set(map(int,design['masks']))
        p=pd.read_parquet(path)
        pred_years=set(map(int,p.year)) if len(p) else set()
        if not pred_years.issubset(all_years):raise ValueError('Unmasked target forecast')
        for year in all_years-pred_years:
            row=saved.loc[(family,station,replicate,year)]
            if np.isfinite(row.D2) or row.common_predictable:raise ValueError('Absent forecast marked as supported')
            missing_count+=1
        if len(p):
            x=M.features(p,bundles[region]).reindex(columns=models[region]['features'])
            score=models[region]['model'].predict_proba(x)[:,1]
            for i,r in enumerate(p.itertuples(index=False)):
                s=saved.loc[(family,station,replicate,int(r.year))]
                if s.region!=region or s.independence_group!=group:raise ValueError('Target group mismatch')
                if np.isfinite(r.eval_truth_h30):raise ValueError('Expected unscored candidate cache truth to be absent')
                for old,new in [(s.D2,r.D2),(s.original_score,r.risk_score),(s.projected_score,score[i]),
                                (s.observed_lower_bound,r.observed_lower_bound__observed_days)]:
                    if not np.isclose(old,new,rtol=0,atol=1e-10,equal_nan=True):raise ValueError('Target prediction or reference differs')
                count+=1
    if count+missing_count!=len(t) or len(paths)!=plan['target_prediction_files']:raise ValueError('Target denominator differs')
    cuts=pd.read_csv(M.OUT/'source_cutoffs.csv').set_index(['region','family'])
    matches=0
    for (region,family),group in t.groupby(['region','family'],sort=True):
        cutoff=cuts.loc[(region,family)]
        valid=np.isfinite(group.D2)&np.isfinite(group.original_score)&np.isfinite(group.projected_score)
        original=valid & group.original_score.le(cutoff.original_cutoff)
        projected=valid & group.projected_score.le(cutoff.projected_cutoff)
        if not np.array_equal(original.to_numpy(),group.original_selected.to_numpy()) or not np.array_equal(projected.to_numpy(),group.projected_selected.to_numpy()):
            raise ValueError('Source-threshold selection differs')
        hashes=pd.util.hash_pandas_object(group[KEY],index=False).to_numpy(dtype='uint64')
        ordering=sorted((float(row.projected_score),int(hashes[i]),tuple(getattr(row,k) for k in KEY),i)
                        for i,row in enumerate(group.itertuples(index=False)) if valid.iloc[i])
        indices={item[-1] for item in ordering[:int(original.sum())]}
        matched=np.array([i in indices for i in range(len(group))],dtype=bool)
        if not np.array_equal(matched,group.matched_projected_selected.to_numpy(bool)):raise ValueError('Matched score selection differs')
        matches+=len(group)
    return t,{'target_archives_checked':len(paths),'target_masked_cases_checked':len(t),
              'target_predictions_checked':count,'masked_cases_without_predictions':missing_count,'selection_cases_checked':matches}

def check_summary(target):
    out=pd.read_csv(M.OUT/'summary.csv');loo=pd.read_csv(M.OUT/'leave_region_out.csv')
    rng=np.random.default_rng(701);cells=region_cells=0
    for family,g in target.groupby('family',sort=True):
        for comparison,column in [('source_threshold','projected_selected'),('matched_target_count','matched_projected_selected')]:
            row=out[(out.family==family)&(out.comparison==comparison)]
            if len(row)!=1:raise ValueError('Summary cell missing')
            row=row.iloc[0]
            old=g.original_selected.to_numpy(bool);new=g[column].to_numpy(bool)
            truth=g.reference_h30.to_numpy(float);point=g.D2.to_numpy(float)
            ev=np.isfinite(truth)&np.isfinite(point);bad=ev&(np.abs(point-truth)>.5)
            expected={'n_masked':len(g),'n_common_predictable':int(g.common_predictable.sum()),'n_reference_evaluable':int(ev.sum()),
                      'old_selected':int(old.sum()),'new_selected':int(new.sum()),
                      'old_selected_evaluable':int((old&ev).sum()),'new_selected_evaluable':int((new&ev).sum()),
                      'old_bad':int((old&bad).sum()),'new_bad':int((new&bad).sum()),'n_bad_all_evaluable':int(bad.sum()),
                      'old_bad_rejected':int((bad&~old).sum()),'new_bad_rejected':int((bad&~new).sum())}
            for name,value in expected.items():
                if int(row[name])!=value:raise ValueError('Summary denominator/count mismatch: '+name)
            groups=sorted(g.independence_group.unique());draws=rng.integers(len(groups),size=(4000,len(groups)))
            counts=[]
            for name in groups:
                part=g.independence_group.eq(name).to_numpy();counts.append([int(part.sum()),int((part&old).sum()),int((part&new).sum()),
                    int((part&old&ev).sum()),int((part&new&ev).sum()),int((part&old&bad).sum()),int((part&new&bad).sum())])
            c=np.asarray(counts);resampled=c[draws].sum(axis=1);ok=(resampled[:,3]>0)&(resampled[:,4]>0)
            difference=resampled[ok,6]/resampled[ok,4]-resampled[ok,5]/resampled[ok,3]
            retention=(resampled[:,2]-resampled[:,1])/resampled[:,0]
            for name,value in [('risk_difference_low',np.quantile(difference,.025)),('risk_difference_high',np.quantile(difference,.975)),
                               ('retention_difference_low',np.quantile(retention,.025)),('retention_difference_high',np.quantile(retention,.975))]:
                if not np.isclose(row[name],value,rtol=0,atol=1e-12):raise ValueError('Bootstrap mismatch: '+name)
            for region in sorted(g.region.unique()):
                item=loo[(loo.family==family)&(loo.comparison==comparison)&(loo.removed_region==region)]
                if len(item)!=1:raise ValueError('Region deletion missing')
                keep=g.region.ne(region).to_numpy();a=old&keep;b=new&keep;item=item.iloc[0]
                if item.n_masked!=keep.sum() or item.old_selected!=a.sum() or item.new_selected!=b.sum():raise ValueError('Region deletion count differs')
                for name,choose in [('old_failure',a),('new_failure',b)]:
                    value=(choose&bad).sum()/(choose&ev).sum() if (choose&ev).sum() else np.nan
                    if not np.isclose(item[name],value,rtol=0,atol=1e-12,equal_nan=True):raise ValueError('Region deletion risk differs')
                region_cells+=1
            cells+=1
    return {'summary_cells_checked':cells,'region_deletion_cells_checked':region_cells,'group_resamples_per_cell':4000}

def main():
    plan=M.verify_source_freeze()
    reference=T.load_script('projected_risk_reference_audit',ROOT/'scripts/703_projected_risk_reference_scoring.py')
    amendment=json.loads((M.OUT/'reference_score_amendment.json').read_text())
    first=pd.read_parquet(M.PRIVATE/'target_scores_unscored.parquet')
    annual=pd.read_parquet(reference.ANNUAL,columns=KEY+['mode','output_state','region','independence_group','eval_reference_h30'])
    original=pd.read_parquet(reference.SOURCE,columns=['station_key','year','design_family','eval_truth_h30']).rename(columns={'design_family':'family'})
    rebuilt=reference.attach_reference(first,annual,original).set_index(KEY).sort_index()
    final=pd.read_parquet(M.PRIVATE/'target_scores.parquet').set_index(KEY).sort_index()
    for name in ['reference_h30','D2','original_score','projected_score','common_predictable','original_selected','projected_selected','matched_projected_selected']:
        if not rebuilt[name].equals(final[name]):raise ValueError('Reference attachment or saved selection changed: '+name)
    source=check_source(plan);target,checks=check_target(plan);summary=check_summary(target)
    status={'status':'passed',**source,**checks,**summary,'reference_cases_rechecked':len(rebuilt),
            'scope':'Re-fits classifiers on the same source data and feature implementation, reconstructs disjoint roles and source cutoffs, rechecks reference attachment against two saved records and checks target predictions, label-free selections and aggregates. It does not independently reconstruct physical observations or prove prospective group risk.'}
    (M.OUT/'independent_audit.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps(status,indent=2),flush=True)

if __name__=='__main__':main()

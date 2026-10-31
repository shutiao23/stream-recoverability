#!/usr/bin/env python3
"""Fit and evaluate a post-hoc projected-point failure classifier.

Training and thresholds use separate, strict-region source groups before 2010.
This is an empirical comparison on already-opened archives, not a probability
calibration or group-risk guarantee. Case-level data and models remain private.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
os.umask(0o077)
import argparse
import json
from pathlib import Path
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import wrr_tr_common as T
import wrr_tr_features as F

ROOT=T.ROOT
REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'projected_risk_sensitivity'
INPUT=ROOT/'private/wrr_open_source_sensitivity_20261026'
PRIVATE=ROOT/'private/wrr_projected_risk_sensitivity_20261027'
KEY=['family','station_key','replicate','year']

def verify_plan():
    plan=json.loads((OUT/'plan.json').read_text())
    manifest=PRIVATE/'input_manifest.json'
    return plan

def equal_group_weights(groups):
    groups=pd.Series(groups).reset_index(drop=True)
    if groups.isna().any() or groups.empty:raise ValueError('Missing or empty source groups')
    counts=groups.map(groups.value_counts())
    weights=1/counts.to_numpy(float)
    return weights*len(weights)/weights.sum()

def features(frame,bundle):
    x=F.design_matrix(frame,simulation=True).reindex(columns=bundle['features']).copy()
    x['projected_interval_width']=frame.D2_q95.to_numpy(float)-frame.D2_q05.to_numpy(float)
    x['projected_point_above_bound']=frame.D2.to_numpy(float)-frame.observed_lower_bound__observed_days.to_numpy(float)
    if any(c.startswith(('eval_','reference','truth','risk_score')) for c in x.columns):
        raise ValueError('Forbidden evaluation or original risk feature')
    return x.replace([np.inf,-np.inf],np.nan)

def select_matched(frame,n):
    if frame.duplicated(KEY).any():raise ValueError('Duplicate target case identity')
    valid=np.isfinite(frame.projected_score.to_numpy(float)) & np.isfinite(frame.original_score.to_numpy(float)) & np.isfinite(frame.D2.to_numpy(float))
    indices=np.flatnonzero(valid)
    if n<0 or n>len(indices):raise ValueError('Matched count unavailable')
    selected=np.zeros(len(frame),dtype=bool)
    if n:
        rank=frame.iloc[indices][KEY+['projected_score']].copy()
        rank['tie']=pd.util.hash_pandas_object(rank[KEY],index=False).to_numpy(dtype='uint64')
        rank['position']=indices
        rank=rank.sort_values(['projected_score','tie']+KEY,kind='mergesort')
        selected[rank.position.iloc[:n].to_numpy(int)]=True
    return selected

def fit_source():
    plan=verify_plan()
    if (OUT/'source_freeze.json').exists():raise FileExistsError('Frozen source classifier exists; preserve original')
    inference=T.load_script('projected_risk_source_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    repair=T.load_script('projected_risk_source_repair',ROOT/'scripts/467_review_completion_analysis.py')
    cutoff=T.load_script('projected_risk_threshold',ROOT/'scripts/558_source_calibrated_release.py')
    source=pd.read_parquet(INPUT/'candidate_cases/before_2010/seed_00.parquet')
    forbidden_by_region={region:set(g.independence_group) for region,g in source.groupby('region')}
    source=source[source.policy_choice.ne('unavailable') & source.eval_truth_h30.notna() & source.training_partition.eq('train')].reset_index(drop=True)
    if source.year.ge(2010).any():raise ValueError('Forward source contains post-2009 observations')
    source=repair.apply_bridge_repairs(source,0,'before_2010')
    roster=pd.read_csv(PRIVATE/'roster.csv');models=PRIVATE/'models';models.mkdir(exist_ok=True,mode=0o700)
    support=[];thresholds=[];manifest={}
    for index,region in enumerate(sorted(roster.region.unique())):
        bundle=joblib.load(INPUT/'refits/before_2010/seed_00'/f'{region}.joblib')
        calibration=json.loads((INPUT/'calibrations/forward'/f'{region}.json').read_text())
        bundle['offsets']=calibration['D2_offsets']
        roles={k:set(v) for k,v in bundle['roles'].items()}
        if any(roles[a]&roles[b] for i,a in enumerate(roles) for b in list(roles)[i+1:]):raise ValueError('Source roles overlap')
        forbidden=forbidden_by_region.get(region,set())
        if any(groups & forbidden for groups in roles.values()):raise ValueError('Source role overlaps target region')
        training=source[source.independence_group.isin(roles['risk_learning'])].copy()
        rule=source[source.independence_group.isin(roles['rule_calibration'])].copy()
        train=inference.predict(training,bundle)
        finite=np.isfinite(train.D2.to_numpy(float)) & np.isfinite(train.eval_truth_h30.to_numpy(float))
        train=train.loc[finite].copy()
        label=(np.abs(train.D2.to_numpy(float)-train.eval_truth_h30.to_numpy(float))>.5).astype(int)
        n_groups=train.independence_group.nunique()
        status='supported' if n_groups>=4 and np.unique(label).size==2 else 'insufficient_training_groups_or_classes'
        record={'region':region,'status':status,'training_cases':len(train),'training_groups':n_groups,
                'training_events':int(label.sum()),'training_nonevents':int((label==0).sum()),
                'assigned_rule_groups':len(roles['rule_calibration'])}
        support.append(record)
        if status!='supported':
            for family in ['calendar','crossed']:
                thresholds.append({'region':region,'family':family,'status':status})
            continue
        params=dict(plan['model_parameters']);params.pop('random_seed');params['random_state']=700+index
        classifier=lgb.LGBMClassifier(**params)
        classifier.fit(features(train,bundle),label,sample_weight=equal_group_weights(train.independence_group))
        model_path=models/f'{region}.joblib'
        joblib.dump({'model':classifier,'features':list(features(train.iloc[:1],bundle).columns),'source_roles':{k:sorted(v) for k,v in roles.items()}},model_path,compress=3)
        candidate=inference.predict(rule,bundle)
        candidate['projected_score']=classifier.predict_proba(features(candidate,bundle))[:,1]
        for family in ['calendar','crossed']:
            c=candidate[candidate.design_family.eq(family)].copy()
            valid=np.isfinite(c.D2.to_numpy(float)) & np.isfinite(c.risk_score.to_numpy(float)) & np.isfinite(c.projected_score.to_numpy(float))
            c=c.loc[valid].copy();ng=c.independence_group.nunique()
            if ng<3 or c.empty:
                thresholds.append({'region':region,'family':family,'status':'insufficient_rule_groups','rule_cases':len(c),'rule_groups':ng});continue
            weights=equal_group_weights(c.independence_group)
            old_cut,old_rate=cutoff.fit_threshold(c.risk_score,np.ones(len(c),bool),weights,.8)
            new_cut,new_rate=cutoff.fit_threshold(c.projected_score,np.ones(len(c),bool),weights,.8)
            thresholds.append({'region':region,'family':family,'status':'supported','rule_cases':len(c),'rule_groups':ng,
                               'original_cutoff':old_cut,'projected_cutoff':new_cut,'original_source_rate':old_rate,'projected_source_rate':new_rate})
        print('Fitted source-only projected risk model:',region,flush=True)
    support=pd.DataFrame(support);cuts=pd.DataFrame(thresholds)
    if len(support)!=6 or len(cuts)!=12 or cuts.duplicated(['region','family']).any():raise ValueError('Incomplete source model plan')
    support.to_csv(OUT/'source_support.csv',index=False);cuts.to_csv(OUT/'source_cutoffs.csv',index=False)
    frozen={'status':'source_models_and_cutoffs_frozen_before_new_target_scoring','limitation':'Prior source and target datasets already opened; group disjointness is not a prospective registration or exchangeability guarantee.'}
    (OUT/'source_freeze.json').write_text(json.dumps(frozen,indent=2)+'\n')
    print(json.dumps({'source_models_supported':int(support.status.eq('supported').sum()),'family_thresholds_supported':int(cuts.status.eq('supported').sum())}),flush=True)

def verify_source_freeze():
    plan=verify_plan();f=json.loads((OUT/'source_freeze.json').read_text())
    if f['status']!='source_models_and_cutoffs_frozen_before_new_target_scoring':
        raise ValueError('Source model/cutoff freeze changed')
    return plan

def target_frames(plan):
    roster=pd.read_csv(PRIVATE/'roster.csv').set_index('station_key')
    cuts=pd.read_csv(OUT/'source_cutoffs.csv').set_index(['region','family'])
    models={};bundles={};rows=[]
    for region in sorted(roster.region.unique()):
        model_path=PRIVATE/'models'/f'{region}.joblib'
        if model_path.exists():models[region]=joblib.load(model_path)
        bundles[region]=joblib.load(INPUT/'refits/before_2010/seed_00'/f'{region}.joblib')
    paths=sorted(p for family in ('calendar','crossed') for p in (INPUT/'whole_archive'/family/'forward').glob('replicate_*/*/annual_predictions.parquet'))
    if len(paths)!=plan['target_prediction_files']:raise ValueError('Target archive count differs')
    for path in paths:
        family,mode,rep,_=path.relative_to(INPUT/'whole_archive').parts[:4]
        replicate=int(rep.removeprefix('replicate_'));design=json.loads((path.parent/'design.json').read_text())
        station=design['station_key'];region=roster.loc[station,'region'];group=roster.loc[station,'independence_group']
        receipt=json.loads((path.parent/'open_source_receipt.json').read_text())
        model=INPUT/'refits/before_2010/seed_00'/f'{region}.joblib';cal=INPUT/'calibrations/forward'/f'{region}.json'
        old=REV/'whole_archive'/path.relative_to(INPUT/'whole_archive')
        years=pd.DataFrame({'year':list(map(int,design['masks'].keys()))})
        pred=pd.read_parquet(path)
        if len(pred) and pred.year.duplicated().any() or not set(pred.year).issubset(set(years.year)):raise ValueError('Target masked years do not align')
        base=years.assign(family=family,station_key=station,replicate=replicate,region=region,independence_group=group)
        base['D2']=np.nan;base['original_score']=np.nan;base['projected_score']=np.nan;base['reference_h30']=np.nan;base['observed_lower_bound']=np.nan
        if len(pred):
            pred=pred.set_index('year').reindex(base.year)
            base['D2']=pred.D2.to_numpy(float);base['original_score']=pred.risk_score.to_numpy(float)
            base['reference_h30']=pred.eval_truth_h30.to_numpy(float)
            base['observed_lower_bound']=pred.observed_lower_bound__observed_days.to_numpy(float)
            if region in models:
                x=features(pred,bundles[region]).reindex(columns=models[region]['features'])
                base['projected_score']=models[region]['model'].predict_proba(x)[:,1]
        setting=cuts.loc[(region,family)]
        common=np.isfinite(base.D2.to_numpy(float)) & np.isfinite(base.original_score.to_numpy(float)) & np.isfinite(base.projected_score.to_numpy(float))
        supported=setting.status=='supported' and region in models
        base['common_predictable']=common & supported
        base['original_selected']=base.common_predictable & (base.original_score<=setting.original_cutoff) if supported else False
        base['projected_selected']=base.common_predictable & (base.projected_score<=setting.projected_cutoff) if supported else False
        rows.append(base)
    result=pd.concat(rows,ignore_index=True)
    if result.duplicated(KEY).any():raise ValueError('Target identities are not unique')
    result['matched_projected_selected']=False
    for (_,family),idx in result.groupby(['region','family'],sort=True).groups.items():
        part=result.loc[idx].copy().reset_index(drop=True)
        count=int(part.original_selected.sum());selection=select_matched(part,count)
        result.loc[idx,'matched_projected_selected']=selection
    return result

def metric_summary(target):
    rows=[];regions=[];rng=np.random.default_rng(701)
    for family,g in target.groupby('family',sort=True):
        for method,field in [('source_threshold','projected_selected'),('matched_target_count','matched_projected_selected')]:
            old=g.original_selected.to_numpy(bool);new=g[field].to_numpy(bool)
            truth=g.reference_h30.to_numpy(float);point=g.D2.to_numpy(float)
            evaluable=np.isfinite(truth)&np.isfinite(point);bad=evaluable&(np.abs(point-truth)>.5)
            group=pd.DataFrame({'group':g.independence_group.to_numpy(),'old_selected':old.astype(int),'new_selected':new.astype(int),
                'old_evaluable':(old&evaluable).astype(int),'new_evaluable':(new&evaluable).astype(int),
                'old_bad':(old&bad).astype(int),'new_bad':(new&bad).astype(int),
                'old_bound':(old & np.isfinite(g.observed_lower_bound.to_numpy(float))).astype(int),
                'new_bound':(new & np.isfinite(g.observed_lower_bound.to_numpy(float))).astype(int),
                'n_masked':1,'bad':bad.astype(int),'old_bad_rejected':(bad&~old).astype(int),'new_bad_rejected':(bad&~new).astype(int)})
            by=group.groupby('group',sort=True).sum()
            ix=rng.integers(len(by),size=(4000,len(by)))
            a=by.old_bad.to_numpy()[ix].sum(axis=1);b=by.new_bad.to_numpy()[ix].sum(axis=1)
            na=by.old_evaluable.to_numpy()[ix].sum(axis=1);nb=by.new_evaluable.to_numpy()[ix].sum(axis=1)
            valid=(na>0)&(nb>0);risk=b[valid]/nb[valid]-a[valid]/na[valid]
            ret=(by.new_selected.to_numpy()[ix].sum(axis=1)-by.old_selected.to_numpy()[ix].sum(axis=1))/by.n_masked.to_numpy()[ix].sum(axis=1)
            row={'family':family,'comparison':method,'n_masked':len(g),'n_common_predictable':int(g.common_predictable.sum()),
                 'n_reference_evaluable':int(evaluable.sum()),'n_groups':len(by),'n_stations':g.station_key.nunique(),
                 'old_selected':int(old.sum()),'new_selected':int(new.sum()),'old_selected_evaluable':int((old&evaluable).sum()),
                 'new_selected_evaluable':int((new&evaluable).sum()),'old_bad':int((old&bad).sum()),'new_bad':int((new&bad).sum()),
                 'n_bad_all_evaluable':int(bad.sum()),'old_bad_rejected':int((bad&~old).sum()),'new_bad_rejected':int((bad&~new).sum()),
                 'old_selected_with_bound':int((old&np.isfinite(g.observed_lower_bound.to_numpy(float))).sum()),
                 'new_selected_with_bound':int((new&np.isfinite(g.observed_lower_bound.to_numpy(float))).sum()),
                 'old_retention':float(old.mean()),'new_retention':float(new.mean()),
                 'old_failure':float((old&bad).sum()/(old&evaluable).sum()) if (old&evaluable).sum() else np.nan,
                 'new_failure':float((new&bad).sum()/(new&evaluable).sum()) if (new&evaluable).sum() else np.nan,
                 'risk_difference_low':float(np.quantile(risk,.025)) if len(risk) else np.nan,
                 'risk_difference_high':float(np.quantile(risk,.975)) if len(risk) else np.nan,
                 'retention_difference_low':float(np.quantile(ret,.025)),'retention_difference_high':float(np.quantile(ret,.975)),
                 'risk_bootstrap_valid':int(valid.sum())}
            rows.append(row)
            for region,b in g.groupby('region',sort=True):
                idx=g.region.ne(region).to_numpy();o=old&idx;n=new&idx
                regions.append({'family':family,'comparison':method,'removed_region':region,'n_masked':int(idx.sum()),
                    'old_selected':int(o.sum()),'new_selected':int(n.sum()),
                    'old_failure':float((o&bad).sum()/(o&evaluable).sum()) if (o&evaluable).sum() else np.nan,
                    'new_failure':float((n&bad).sum()/(n&evaluable).sum()) if (n&evaluable).sum() else np.nan})
    return pd.DataFrame(rows),pd.DataFrame(regions)

def score_target():
    plan=verify_source_freeze()
    if (OUT/'status.json').exists():raise FileExistsError('Target risk results already exist')
    target=target_frames(plan)
    target.to_parquet(PRIVATE/'target_scores.parquet',index=False)
    summary,regional=metric_summary(target)
    summary.to_csv(OUT/'summary.csv',index=False);regional.to_csv(OUT/'leave_region_out.csv',index=False)
    status={'status':'computed','target_masked_cases':len(target),'target_archives':plan['target_prediction_files'],
            'reference_used_to_choose_threshold_or_match':False,'groups_in_target':int(target.independence_group.nunique()),
            'source_models_and_cutoffs_frozen_first':True,
            'limitations':plan['limitations']}
    (OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(summary.to_string(index=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['fit-source','score-target']);a=p.parse_args()
    fit_source() if a.action=='fit-source' else score_target()

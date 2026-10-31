#!/usr/bin/env python3
"""Independently re-predict, re-rank and recount annual group-max sensitivity.

The same source and target data/models are used; this audit cannot establish
exchangeability, physical measurement accuracy or external coverage.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
import json
import hashlib
import math
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
M=T.load_script('groupmax_audit_inputs',ROOT/'scripts/720_groupmax_annual_calibration.py')
KEY=['family','mode','replicate','station_key','year']
TOL=1e-8

def close(a,b,label):
    if not np.isclose(float(a),float(b),rtol=0,atol=1e-9,equal_nan=True):raise ValueError('Mismatch: '+label)

def verify_repair_dependency(root,out):
    """Fail closed: the historic repair helper otherwise silently skips data."""
    dependency=json.loads((out/'source_repair_dependency.json').read_text())
    if dependency.get('status')!='passed' or not dependency.get('repaired_source_group_maxima_reproduced'):
        raise ValueError('Bridge-repair dependency audit is incomplete')
    root=root.resolve()
    repair=Path(dependency['repair_path'])
    if repair.is_absolute() or '..' in repair.parts:
        raise ValueError('Unsafe bridge-repair input path')
    for path in [root/repair, out/'plan.json',
                     out/'source_freeze.json', out/'source_repair_effect.csv',
                     root/'scripts/729_bridge_repair_dependency.py']:
        expected=dependency.get('input_sha256',{}).get(str(path.relative_to(root)))
        if (not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root)
                or not expected or hashlib.sha256(path.read_bytes()).hexdigest()!=expected):
            raise ValueError('Required bridge-repair input changed or missing: '+str(path))
    return dependency

def audit_source():
    inf=T.load_script('groupmax_audit_inference',ROOT/'scripts/495_review_completion_independent_analysis.py')
    repair=T.load_script('groupmax_audit_repair',ROOT/'scripts/467_review_completion_analysis.py')
    raw=pd.read_parquet(M.INPUT/'candidate_cases/before_2010/seed_00.parquet')
    forbidden={region:set(g.independence_group) for region,g in raw.groupby('region')}
    source=raw[raw.policy_choice.ne('unavailable') & raw.eval_truth_h30.notna() & raw.training_partition.eq('train')].reset_index(drop=True)
    if source.year.ge(2010).any():raise ValueError('Source year cutoff violated')
    source=repair.apply_bridge_repairs(source,0,'before_2010')
    roster=pd.read_csv(ROOT/'private/wrr_projected_risk_sensitivity_20261027/roster.csv')
    support=pd.read_csv(M.OUT/'source_support.csv').set_index(['region','family','estimator'])
    stored=pd.read_parquet(M.PRIVATE/'source_group_scores.parquet')
    records=0;groups_checked=0;probes=0
    for region in sorted(roster.region.unique()):
        bundle=joblib.load(M.INPUT/'refits/before_2010/seed_00'/f'{region}.joblib')
        cal=json.loads((M.INPUT/'calibrations/forward'/f'{region}.json').read_text());bundle['offsets']=cal['D2_offsets']
        roles={name:set(groups) for name,groups in bundle['roles'].items()}
        for name,groups in roles.items():
            if any(groups & roles[other] for other in roles if other!=name):raise ValueError('Source group roles overlap')
        pool=roles['risk_learning']|roles['rule_calibration']
        held=set(roster.loc[roster.region.eq(region),'independence_group'])
        if pool&(forbidden.get(region,set())|held|roles['estimator']|roles['interval_calibration']):
            raise ValueError('Calibration group overlaps target or numeric model fitting')
        source_region=source[source.independence_group.isin(pool)]
        for family in ['calendar','crossed']:
            part=source_region[source_region.design_family.eq(family)]
            pred=inf.classical_predictions(inf.predict(part,bundle),cal)
            probe=part.iloc[:25].copy();altered=dict(bundle);altered['classifier']=None;altered['constant_probability']=.987
            x=inf.classical_predictions(inf.predict(probe,bundle),cal);y=inf.classical_predictions(inf.predict(probe,altered),cal)
            for prefix in M.METHODS.values():
                for q in ['05','10','25','50','75','90','95']:
                    if not np.allclose(x[f'{prefix}_q{q}'],y[f'{prefix}_q{q}'],rtol=0,atol=1e-10,equal_nan=True):raise ValueError('Classifier affects numeric quantiles')
            probes+=len(probe)
            for method,prefix in M.METHODS.items():
                truth=pred.eval_truth_h30.to_numpy(float);lo=pred[f'{prefix}_q05'].to_numpy(float);hi=pred[f'{prefix}_q95'].to_numpy(float)
                bound=pred.observed_lower_bound__observed_days.to_numpy(float);group=pred.independence_group
                valid=np.isfinite(truth)&np.isfinite(lo)&np.isfinite(hi)&np.isfinite(bound)&group.notna().to_numpy()
                nonconformity=np.maximum(np.maximum(lo[valid]-truth[valid],truth[valid]-hi[valid]),0.)
                calculated=pd.DataFrame({'group':group.to_numpy()[valid],'score':nonconformity}).groupby('group',sort=True).score.agg(['max','size']).reset_index()
                prior=stored[(stored.region==region)&(stored.family==family)&(stored.estimator==method)].sort_values('group').reset_index(drop=True)
                identity_match=calculated.group.equals(prior.group)
                size_match=calculated['size'].equals(prior['size'])
                max_match=len(calculated)==len(prior) and np.allclose(calculated['max'],prior['max'],rtol=0,atol=1e-10)
                if not identity_match or not size_match or not max_match:
                    max_delta=float(np.max(np.abs(calculated['max'].to_numpy(float)-prior['max'].to_numpy(float)))) if len(calculated)==len(prior) and len(prior) else None
                    raise ValueError(f'Source group maxima differ for {region}/{family}/{method}: '
                                     f'group_ids_match={identity_match}, group_sizes_match={size_match}, max_values_match={max_match}, max_delta={max_delta}')
                row=support.loc[(region,family,method)];n=len(calculated);rank=math.ceil(.9*(n+1)-1e-12)
                value=float(sorted(calculated['max'])[rank-1]) if rank<=n else np.nan
                expected='insufficient_source_groups' if rank>n else ('zero_source_correction' if value<=TOL else 'supported_exploratory')
                if int(row.n_cases)!=valid.sum() or int(row.n_groups)!=n or int(row['rank'])!=rank or row.status!=expected:raise ValueError('Source group rank/support differs')
                close(row.radius,value,'source radius')
                records+=int(valid.sum());groups_checked+=n
    return {'source_prediction_rows_rechecked':records,'source_group_maxima_checked':groups_checked,'classifier_perturbation_cases':probes}

def audit_target():
    source=T.load_script('groupmax_audit_target',ROOT/'scripts/672_single_year_source_calibration.py')
    target,_=source.target_cases();target=target[target['mode'].eq('forward')].copy()
    evidence=pd.read_parquet(M.PRIVATE/'target_scores.parquet')
    support=pd.read_csv(M.OUT/'source_support.csv').set_index(['region','family','estimator'])
    old=pd.read_csv(M.OLD/'single_year_source_support.csv');old=old[old['mode'].eq('forward')].set_index(['region','family','estimator'])
    old_both=old.status.eq('supported_exploratory').groupby(level=['region','family']).all()
    new_both=support.status.eq('supported_exploratory').groupby(level=['region','family']).all()
    if evidence.duplicated(KEY+['estimator']).any() or len(evidence)!=2*len(target):raise ValueError('Target score identities differ')
    n=0
    for method,prefix in M.METHODS.items():
        saved=evidence[evidence.estimator.eq(method)]
        p=target.merge(saved,on=KEY,how='outer',suffixes=('','_saved'),indicator='_audit_merge',validate='one_to_one')
        if not p._audit_merge.eq('both').all() or not p.region.eq(p.region_saved).all() or not p.stratum.eq(p.stratum_saved).all() or not p.independence_group_old.eq(p.independence_group_old_saved).all():
            raise ValueError('Target score alignment differs')
        y=p.reference_h30.to_numpy(float);bound=p.observed_lower_bound__observed_days_old.to_numpy(float)
        lo=p[f'{prefix}_q05_candidate'].to_numpy(float);hi=p[f'{prefix}_q95_candidate'].to_numpy(float)
        radius=[];old_radius=[];flags=[];both_flags=[];old_flags=[]
        for region,family in p[['region','family']].itertuples(index=False,name=None):
            s=support.loc[(region,family,method)];e=old.loc[(region,family,method)]
            flag=s.status=='supported_exploratory';oldflag=e.status=='supported_exploratory'
            flags.append(flag);both_flags.append(bool(new_both.loc[(region,family)]));old_flags.append(bool(old_both.loc[(region,family)]))
            radius.append(float(s.radius) if flag else 0.);old_radius.append(float(e.empirical_radius) if oldflag else 0.)
        if not np.array_equal(flags,p.groupmax_supported) or not np.array_equal(both_flags,p.both_groupmax_supported) or not np.array_equal(old_flags,p.both_empirical_supported):
            raise ValueError('Source support mapping differs')
        for name,r in [('baseline',np.zeros(len(p))),('groupmax',np.asarray(radius)),('empirical',np.asarray(old_radius))]:
            lower=np.maximum(lo-r,bound);upper=hi+r
            result={'coverage90':((y>=lower-TOL)&(y<=upper+TOL)).astype(float),'width90':upper-lower,
                    'interval_score90':upper-lower+20*(np.maximum(lower-y,0)+np.maximum(y-upper,0))}
            for metric,value in result.items():
                if not np.allclose(value,p[name+'_'+metric],rtol=0,atol=1e-9):raise ValueError('Target interval score differs: '+name+'/'+metric)
        n+=len(p)
    return evidence,{'target_case_method_rows_rechecked':n,'target_unique_cases_rechecked':len(target)}

def audit_summary(evidence):
    saved=pd.read_csv(M.OUT/'summary.csv');loo=pd.read_csv(M.OUT/'leave_region_out.csv')
    rng=np.random.default_rng(720);cells=deletions=0
    for (family,estimator),all_cases in evidence.groupby(['family','estimator'],sort=True):
      for stratum in ['all','unobserved_peak_excess']:
       subset=all_cases if stratum=='all' else all_cases[all_cases.stratum.eq(stratum)]
       for scope in ['both_groupmax_supported','both_groupmax_and_empirical_supported']:
        flags=subset.both_groupmax_supported.to_numpy(dtype=bool,copy=True)
        if scope=='both_groupmax_and_empirical_supported':flags &= subset.both_empirical_supported.to_numpy(bool)
        g=subset.loc[flags];groups=sorted(g.independence_group_old.unique())
        row=saved[(saved.family==family)&(saved.estimator==estimator)&(saved.stratum==stratum)&(saved.scope==scope)]
        if len(row)!=1:raise ValueError('Summary cell missing')
        row=row.iloc[0]
        if int(row.n_eligible)!=len(subset) or int(row.n_supported)!=len(g) or int(row.groups)!=len(groups):raise ValueError('Target summary denominator differs')
        for version in ['baseline','groupmax']+(['empirical'] if scope=='both_groupmax_and_empirical_supported' else []):
            for metric in ['coverage90','width90','interval_score90']:
                close(g[version+'_'+metric].mean(),row[version+'_'+metric],'target summary')
            if int(row[version+'_groups_all_cases_covered'])!=int(g.groupby('independence_group_old')[version+'_coverage90'].min().sum()):
                raise ValueError('Target simultaneous group count differs')
        if groups:
            labels=g.independence_group_old.to_numpy();draw=rng.integers(len(groups),size=(4000,len(groups)))
            for metric in ['coverage90','width90','interval_score90']:
                d=(g['groupmax_'+metric]-g['baseline_'+metric]).to_numpy(float)
                totals=np.array([d[labels==group].sum() for group in groups]);sizes=np.array([(labels==group).sum() for group in groups])
                sample=totals[draw].sum(axis=1)/sizes[draw].sum(axis=1)
                close(np.mean(totals/sizes),row[metric+'_difference_group_equal'],'group-equal change')
                close(np.quantile(sample,.025),row[metric+'_difference_ci_low'],'bootstrap lower')
                close(np.quantile(sample,.975),row[metric+'_difference_ci_high'],'bootstrap upper')
        for region in sorted(g.region.unique()):
            r=loo[(loo.family==family)&(loo.estimator==estimator)&(loo.stratum==stratum)&(loo.scope==scope)&(loo.removed_region==region)]
            if len(r)!=1:raise ValueError('Leave-region cell missing')
            r=r.iloc[0];remain=g[g.region.ne(region)]
            if int(r.n_supported)!=len(remain):raise ValueError('Leave-region denominator differs')
            for metric in ['coverage90','width90','interval_score90']:
                d=(remain['groupmax_'+metric]-remain['baseline_'+metric]).mean()
                close(d,r[metric+'_difference'],'leave-region difference')
            deletions+=1
        cells+=1
    if cells!=len(saved) or deletions!=len(loo):raise ValueError('Extra summary rows')
    return {'summary_cells_checked':cells,'leave_region_cells_checked':deletions,'group_resamples_per_supported_cell':4000}

def main():
    M.verify_source()
    verify_repair_dependency(ROOT,M.OUT)
    status=json.loads((M.OUT/'status.json').read_text())
    correction=json.loads((M.OUT/'summary_correction.json').read_text())
    if not status['source_frozen_first'] or not status['summary_denominator_corrected']:
        raise ValueError('Source radius freeze or summary correction missing')
    src=audit_source();target,count=audit_target();summary=audit_summary(target)
    result={'status':'passed',**src,**count,**summary,
            'scope':'Independent group-max ranking and interval arithmetic using the same source models, target masks and stored data; checks classifier perturbations and roles. Not an independent dataset, exchangeability proof or group-risk guarantee.'}
    (M.OUT/'independent_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()

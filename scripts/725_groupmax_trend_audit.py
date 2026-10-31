#!/usr/bin/env python3
"""Independently reconstruct group-max annual-to-trend sensitivities."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import ndtri

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/groupmax_annual_calibration'
PRIVATE=ROOT/'private/wrr_groupmax_annual_calibration_20261027';STAGE=PRIVATE/'trend_propagation'
INPUT=ROOT/'private/wrr_open_source_sensitivity_20261026';CANDIDATE=INPUT/'whole_archive/crossed/forward'
PREVIOUS=INPUT/'single_year_trend_propagation/full'
LEVELS=np.array([.05,.1,.25,.5,.75,.9,.95]);METHODS=['D2','stochastic_calibrated']
DEP=['independent','shared_parameters','residual_blocks'];SCHEMES=['baseline','endpoint_only','tapered'];TOL=1e-8

def draw(q,bound):
    u=(np.arange(256)+.5)/256;z=ndtri(u);knots=ndtri(LEVELS)
    result=np.column_stack([np.interp(u,LEVELS,row) for row in q])
    left=u<LEVELS[0];right=u>LEVELS[-1]
    for i,row in enumerate(q):
        result[left,i]=row[0]+(row[1]-row[0])/(knots[1]-knots[0])*(z[left]-knots[0])
        result[right,i]=row[-1]+(row[-1]-row[-2])/(knots[-1]-knots[-2])*(z[right]-knots[-1])
    return np.maximum(result,bound[None,:])

def modified(q,bound,mask,radius,scheme):
    weights={'baseline':np.zeros(7),'endpoint_only':np.array([-1,0,0,0,0,0,1.]),
             'tapered':np.array([-1,-.8,-.4,0,.4,.8,1.])}[scheme]
    out=q.copy();out[mask]=q[mask]+radius*weights;out=np.maximum(out,bound[:,None])
    if (np.diff(out,axis=1)<-TOL).any() or not np.allclose(out[:,3],q[:,3],rtol=0,atol=TOL) or not np.allclose(out[~mask],q[~mask],rtol=0,atol=TOL):
        raise ValueError('Quantile order, median or complete observation changed')
    return out

def independently_check(folder,receipt,support):
    candidate=CANDIDATE/f'replicate_{int(receipt["replicate"]):02d}'/receipt['station_key'].replace('|','_')
    rows=pd.read_csv(folder/'metrics.csv');saved=pd.read_csv(candidate/'trends.csv')
    if len(rows)!=18 or rows.duplicated(['estimator','scheme','dependence']).any():raise ValueError('Incomplete sampled trend treatments')
    with np.load(folder/'marginals_and_ranks.npz',allow_pickle=False) as n:
        years=n['years'].astype(float);truth=n['truth'].astype(float);bound=n['bounds'].astype(float);mask=n['mask'].astype(bool)
        if len(years)!=len(truth) or len(mask)!=len(years) or not np.isfinite(truth).all() or not np.isfinite(bound).all() or not mask.any():raise ValueError('Invalid stored annual inputs')
        if not np.allclose(bound[~mask],truth[~mask],atol=TOL,rtol=0):raise ValueError('Observed years have altered bounds')
        cov=(years-years.mean())/10;denom=np.sum(cov*cov);target=float(np.dot(truth,cov)/denom)
        for estimator in METHODS:
            q=n['q_'+estimator];radius=float(n['radius_'+estimator])
            row=support.loc[support.family.eq('crossed')&support.region.eq(receipt['region'])&support.estimator.eq(estimator)]
            if len(row)!=1 or row.iloc[0].status!='supported_exploratory' or not np.isclose(radius,row.iloc[0].radius,atol=1e-12,rtol=0):raise ValueError('Radius differs from frozen source support')
            if (q<bound[:,None]-TOL).any() or (np.diff(q,axis=1)<-TOL).any():raise ValueError('Source quantiles violate support')
            point=truth.copy();point[mask]=q[mask,3];point_slope=float(np.dot(point,cov)/denom)
            endpoint=modified(q,bound,mask,radius,'endpoint_only');taper=modified(q,bound,mask,radius,'tapered')
            if not np.allclose(endpoint[:,[0,-1]],taper[:,[0,-1]],rtol=0,atol=TOL):raise ValueError('Annual 90% endpoints differ')
            for scheme,q2 in [('baseline',q),('endpoint_only',endpoint),('tapered',taper)]:
                samples=draw(q2,bound);sorted_samples=np.sort(samples,axis=0)
                for dep in DEP:
                    ranks=n['rank_'+dep]
                    if ranks.shape!=samples.shape or not np.isfinite(ranks).all():raise ValueError('Invalid saved ranks')
                    ordered=np.empty_like(samples)
                    for k in range(len(years)):
                        order=np.argsort(ranks[:,k],kind='stable');ordered[order,k]=sorted_samples[:,k]
                    slopes=ordered@cov/denom;lower,upper=np.quantile(slopes,[.025,.975])
                    computed={'truth_slope':target,'slope':point_slope,'error':point_slope-target,
                              'squared_error':(point_slope-target)**2,'lower95':lower,'upper95':upper,'width95':upper-lower,
                              'interval_score95':upper-lower+40*(max(lower-target,0)+max(target-upper,0)),
                              'missing_coverage95':bool(lower-1e-12<=target<=upper+1e-12)}
                    r=rows.loc[rows.estimator.eq(estimator)&rows.scheme.eq(scheme)&rows.dependence.eq(dep)]
                    if len(r)!=1:raise ValueError('Trend treatment missing')
                    for name,value in computed.items():
                        if name=='missing_coverage95':
                            if bool(r.iloc[0][name])!=value:raise ValueError('Reconstructed coverage differs')
                        elif not np.isclose(r.iloc[0][name],value,atol=1e-8,rtol=0):raise ValueError('Reconstructed trend statistic differs: '+name)
                    if scheme=='baseline':
                        old=saved.loc[saved.estimator.eq(estimator)&saved.retention.eq('all')&saved.dependence.eq(dep)]
                        if len(old)!=1 or not bool(old.iloc[0].available):raise ValueError('Baseline candidate trend absent')
                        for name in ['truth_slope','slope','lower95','upper95','interval_score95']:
                            if not np.isclose(old.iloc[0][name],computed[name],atol=1e-8,rtol=0):raise ValueError('Prior baseline interval differs')
    return rows

def independently_check_exclusion(receipt):
    candidate=CANDIDATE/f'replicate_{int(receipt["replicate"]):02d}'/receipt['station_key'].replace('|','_')
    design=json.loads((candidate/'design.json').read_text());masks=design['masks']
    if len(masks)!=receipt['n_incomplete'] or design['station_key']!=receipt['station_key'] or design['hidden_values_present_in_visible_archive']!=0:
        raise ValueError('Excluded archive mask identity differs')
    status=receipt['status']
    if status=='no_incomplete_years':
        if masks:raise ValueError('No-incomplete exclusion has masked years')
        return
    cases=pd.read_parquet(candidate/'annual_predictions.parquet')
    if cases.empty:
        if status!='one_or_both_annual_distributions_unavailable':
            raise ValueError('Empty annual data do not support exclusion reason')
        return
    if cases.duplicated('year').any() or not set(cases.year.astype(str)).issubset(set(masks)):
        raise ValueError('Excluded annual cases do not match masks')
    qcols=[f'{prefix}_q{int(100*q):02d}' for prefix in ['D2','stochastic_cal'] for q in LEVELS]
    qfinite=len(cases)==len(masks) and np.isfinite(cases[qcols].to_numpy(float)).all()
    if status=='one_or_both_annual_distributions_unavailable':
        if qfinite:raise ValueError('Annual-distribution exclusion is not supported')
    elif status=='missing_observed_bound':
        if not qfinite or np.isfinite(cases.observed_lower_bound__observed_days.to_numpy(float)).all():
            raise ValueError('Missing-bound exclusion is not supported')
    elif status=='one_or_more_rank_constructions_unavailable':
        if not qfinite or not np.isfinite(cases.observed_lower_bound__observed_days.to_numpy(float)).all():
            raise ValueError('Rank exclusion has an earlier unavailable input')
        saved=pd.read_csv(candidate/'trends.csv')
        selected=saved.loc[saved.estimator.isin(METHODS)&saved.retention.eq('all')&saved.dependence.isin(DEP)]
        if len(selected)!=6 or selected.available.fillna(False).all():raise ValueError('Rank exclusion not reflected in baseline availability')
    else:raise ValueError('Unexpected exclusion reason')

def paired_bootstrap(frame,delta,draws=4000,seed=678):
    g=pd.DataFrame({'group':frame.independence_group.to_numpy(),'delta':np.asarray(delta,float)})
    if g.group.isna().any() or not np.isfinite(g.delta).all() or g.empty:raise ValueError('Invalid group bootstrap data')
    sums=g.groupby('group',sort=True).delta.agg(['sum','size']);rng=np.random.default_rng(seed)
    picks=rng.integers(0,len(sums),size=(draws,len(sums)))
    values=sums['sum'].to_numpy()[picks].sum(axis=1)/sums['size'].to_numpy()[picks].sum(axis=1)
    return float(g.delta.mean()),float((sums['sum']/sums['size']).mean()),*map(float,np.quantile(values,[.025,.975]))

def main():
    planpath=OUT/'trend_plan.json';plan=json.loads(planpath.read_text());execution=json.loads((OUT/'trend_execution.json').read_text())
    if execution['status']!='complete' or execution['archive_settings']!=plan['expected_archive_settings']:
        raise ValueError('Propagation execution is incomplete')
    manifest=PRIVATE/'trend_input_manifest.json'
    support=pd.read_csv(OUT/'source_support.csv');receipts=sorted(STAGE.glob('replicate_*/*/propagation_receipt.json'))
    if len(receipts)!=plan['expected_archive_settings']:raise ValueError('Trend setting count differs from plan')
    frames=[];statuses={};skips=[];previous_frames=[];overlap_checked=0
    for p in receipts:
        receipt=json.loads(p.read_text());s=receipt['status'];statuses[s]=statuses.get(s,0)+1
        if s=='passed':
            frames.append(independently_check(p.parent,receipt,support))
            old=PREVIOUS/f'replicate_{int(receipt["replicate"]):02d}'/receipt['station_key'].replace('|','_')
            if (old/'marginals_and_ranks.npz').is_file():
                fields=['years','truth','bounds','mask','q_D2','q_stochastic_calibrated','rank_independent','rank_shared_parameters','rank_residual_blocks']
                with np.load(p.parent/'marginals_and_ranks.npz') as new,np.load(old/'marginals_and_ranks.npz') as prior:
                    for field in fields:
                        if new[field].shape!=prior[field].shape or not np.allclose(new[field],prior[field],rtol=0,atol=1e-10,equal_nan=True):raise ValueError('Previous empirical rank or marginal differs: '+field)
                previous_frames.append(pd.read_csv(old/'metrics.csv'));overlap_checked+=1
        else:
            if s not in {'no_incomplete_years','one_or_both_annual_distributions_unavailable','missing_observed_bound','one_or_more_rank_constructions_unavailable'}:raise ValueError('Unexpected exclusion reason')
            independently_check_exclusion(receipt)
            skips.append(receipt)
    if statuses!=execution['status_counts'] or not frames or overlap_checked!=execution['previous_marginal_and_rank_checks']:
        raise ValueError('Execution status, overlap or common sample differs')
    cases=pd.concat(frames,ignore_index=True);keys=['station_key','replicate','estimator','dependence']
    if cases.duplicated(keys+['scheme']).any():raise ValueError('Duplicate trend treatment identity')
    n_common=cases.loc[cases.scheme.eq('baseline')].groupby(['estimator','dependence']).size()
    if n_common.nunique()!=1:raise ValueError('Methods and dependence constructions do not have a common cohort')
    summary=[];contrast=[];loo=[]
    for (estimator,dependence),f in cases.groupby(['estimator','dependence'],sort=True):
        wide=f.pivot(index=['station_key','replicate','independence_group','region'],columns='scheme',values=['missing_coverage95','width95','interval_score95'])
        if len(wide)!=len(frames) or wide.isna().any().any():raise ValueError('Paired trend treatments incomplete')
        index=wide.reset_index()[['station_key','replicate','independence_group','region']]
        for scheme in SCHEMES:
            row={'family':'crossed','mode':'forward','estimator':estimator,'dependence':dependence,'scheme':scheme,
                 'n':len(wide),'stations':index.station_key.nunique(),'groups':index.independence_group.nunique()}
            for metric in ['missing_coverage95','width95','interval_score95']:row[metric]=float(pd.to_numeric(wide[(metric,scheme)]).mean())
            summary.append(row)
        for left,right in [('endpoint_only','baseline'),('tapered','baseline'),('tapered','endpoint_only')]:
            for metric in ['missing_coverage95','width95','interval_score95']:
                delta=pd.to_numeric(wide[(metric,left)]).to_numpy(float)-pd.to_numeric(wide[(metric,right)]).to_numpy(float)
                avg,equal,lower,upper=paired_bootstrap(index,delta)
                contrast.append({'family':'crossed','mode':'forward','estimator':estimator,'dependence':dependence,
                  'contrast':left+'_minus_'+right,'metric':metric,'n':len(wide),'groups':index.independence_group.nunique(),
                  'difference':avg,'equal_group_difference':equal,'bootstrap_low':lower,'bootstrap_high':upper})
                for region in sorted(index.region.unique()):
                    keep=index.region.ne(region).to_numpy()
                    if not keep.any():continue
                    loo.append({'estimator':estimator,'dependence':dependence,'contrast':left+'_minus_'+right,
                                'metric':metric,'excluded_region':region,'n':int(keep.sum()),
                                'groups':index.loc[keep,'independence_group'].nunique(),'difference':float(delta[keep].mean())})
    pd.DataFrame(summary).to_csv(OUT/'trend_summary.csv',index=False)
    pd.DataFrame(contrast).to_csv(OUT/'trend_paired_contrasts.csv',index=False)
    pd.DataFrame(loo).to_csv(OUT/'trend_leave_region_out.csv',index=False)
    if not previous_frames:raise ValueError('Previous empirical trend overlap is unavailable')
    old=pd.concat(previous_frames,ignore_index=True)
    identity=['station_key','replicate','estimator','dependence','scheme']
    paired=old.merge(cases,on=identity,how='left',suffixes=('_empirical','_groupmax'),indicator=True,validate='one_to_one')
    if not paired._merge.eq('both').all() or len(paired)!=18*overlap_checked:
        raise ValueError('Previous empirical trend case identities differ')
    baseline=paired[paired.scheme.eq('baseline')]
    for metric in ['truth_slope','slope','lower95','upper95','width95','interval_score95']:
        if not np.allclose(baseline[metric+'_empirical'],baseline[metric+'_groupmax'],rtol=0,atol=1e-8):raise ValueError('Empirical and group-max baseline differs: '+metric)
    overlap=[]
    for (method,dep,scheme),g in paired.groupby(['estimator','dependence','scheme'],sort=True):
        row={'estimator':method,'dependence':dep,'scheme':scheme,'n':len(g),
             'stations':g.station_key.nunique(),'groups':g.independence_group_empirical.nunique()}
        for version in ['empirical','groupmax']:
            for metric in ['missing_coverage95','width95','interval_score95']:
                row[version+'_'+metric]=float(pd.to_numeric(g[metric+'_'+version]).mean())
        overlap.append(row)
    pd.DataFrame(overlap).to_csv(OUT/'trend_empirical_overlap.csv',index=False)
    report={'status':'passed','source_supported_archive_settings':len(receipts),'status_counts':statuses,
       'matched_nontrivial_archives':len(frames),'stations':cases.station_key.nunique(),'groups':cases.independence_group.nunique(),
       'per_case_treatment_rows_checked':len(cases),'baseline_reproduced':True,'same_marginals_and_ranks_checked':True,
       'previous_empirical_overlap_archives':overlap_checked,'previous_empirical_rows_compared':len(paired),
       'bootstrap_draws':4000,'limitations':plan['limitations'],
       'audit_scope':'independent reconstruction from stored per-case quantiles and rank arrays, not regeneration of ranks from raw histories or proof of provider rights'}
    (OUT/'trend_independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(pd.DataFrame(summary).to_string(index=False));print(json.dumps(report,indent=2))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        (OUT/'trend_independent_audit.json').write_text(json.dumps({'status':'failed','error':f'{type(exc).__name__}: {exc}'},indent=2)+'\n')
        raise

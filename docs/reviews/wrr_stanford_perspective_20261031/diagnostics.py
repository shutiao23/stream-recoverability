#!/usr/bin/env python3
"""Exploratory reviewer diagnostics on already-opened annual outputs.

No model fitting, raw-data download, manuscript edits or confirmatory claims.
The iid linear-reference benchmark is a working diagnostic, not a hydrological
model, a causal attribution, or a calibrated uncertainty estimate.
"""
from pathlib import Path
import hashlib
import itertools
import json
import math

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'results/wrr_review_response_20261027/whole_archive'
REF=ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet'
OLD=ROOT/'results/wrr_process_revision_20261029/time_support_cases.csv'
OUT=ROOT/'results/wrr_stanford_perspective_20261031'
KEY=['station_key','replicate','independence_group']
OUT.mkdir(parents=True,exist_ok=True)
BOOT=10000
SEED=20261031


def weights(years):
    x=(np.asarray(years,float)-np.mean(years))/10
    return x/np.dot(x,x)


def geometry(years, selected):
    y=np.asarray(selected,int);grid=np.arange(years.min(),years.max()+1)
    cdf=float(np.mean(((y[:,None]<=grid).mean(axis=0)-(years[:,None]<=grid).mean(axis=0))**2))
    sxx=float(np.sum((y-y.mean())**2)/100)
    return cdf,sxx


def paired_interval(frame, name, baseline='warm90'):
    wide=frame.pivot(index=KEY,columns='scheme',values='estimate_mse')[[baseline,name]].dropna()
    labels=wide.index.get_level_values('independence_group');groups=sorted(set(labels))
    counts=np.array([(labels==g).sum() for g in groups])
    rng=np.random.default_rng(SEED);m=rng.multinomial(len(groups),np.full(len(groups),1/len(groups)),size=BOOT)
    ss={s:np.array([wide.loc[labels==g,s].sum() for g in groups]) for s in [baseline,name]}
    change=np.sqrt(m@ss[name]/(m@counts))-np.sqrt(m@ss[baseline]/(m@counts))
    return dict(n=len(wide),stations=wide.index.get_level_values('station_key').nunique(),groups=len(groups),contrast=name+' minus '+baseline,
                rmse_difference=float(np.sqrt(wide[name].mean())-np.sqrt(wide[baseline].mean())),
                ci_low=float(np.quantile(change,.025)),ci_high=float(np.quantile(change,.975)),seed=SEED,bootstraps=BOOT)


def retention_geometry():
    reference=pd.read_parquet(REF,columns=['station_key','year','design_family','eval_truth_h30'])
    reference=reference.loc[reference.year.ge(2010)]
    assert reference.groupby(['station_key','year','design_family']).eval_truth_h30.nunique().max()==1
    reference=reference.drop_duplicates(['station_key','year','design_family'])
    lookup={(family,station):p.set_index('year').eval_truth_h30.sort_index() for (family,station),p in reference.groupby(['design_family','station_key'])}
    legacy=pd.read_csv(OLD);legacy=legacy.loc[legacy['mode'].eq('forward')]
    rows=[];accounting=[];input_digest=hashlib.sha256();max_identity_error=0.
    for family in ['crossed','calendar']:
        roster=legacy.loc[legacy.family.eq(family)&legacy.scheme.eq('warm90')].sort_values(KEY)
        for case in roster.itertuples(index=False):
            folder=BASE/family/'forward'/f'replicate_{case.replicate:02d}'/case.station_key.replace('|','_')
            design_path=folder/'design.json';pred_path=folder/'annual_predictions.parquet'
            for path in [design_path,pred_path]:input_digest.update(str(path.relative_to(ROOT)).encode()+hashlib.sha256(path.read_bytes()).digest())
            design=json.loads(design_path.read_text());ref=lookup[family,case.station_key];years=ref.index.to_numpy(int);truth=ref.to_numpy(float)
            pred=pd.read_parquet(pred_path).set_index('year').reindex(years)
            missing=np.isin(years,list(map(int,design['masks'])))
            point=truth.copy();point[missing]=pred.D2.to_numpy(float)[missing]
            assert np.isfinite(point).all() and len(years)==design['n_years']
            warm=~missing | pred.warm_observed_fraction.ge(.9).to_numpy()
            assert warm.sum()==case.n_years and missing.sum()==case.n_candidate_incomplete
            complete=years[~missing];candidates=years[missing];k=int(np.sum(warm&missing))
            wfull=weights(years);beta=float(wfull@truth)
            x=(years-years.mean())/10;residual=truth-truth.mean()-beta*x
            sigma2=float(np.sum(residual**2)/(len(years)-2))
            ident=dict(family=family,station_key=case.station_key,replicate=int(case.replicate),independence_group=case.independence_group,region=case.region)
            # Form every optimization input using only calendar geometry.
            options=[]
            for selected_incomplete in itertools.combinations(candidates,k):
                selected=np.sort(np.r_[complete,selected_incomplete]).astype(int);cdf,sxx=geometry(years,selected)
                options.append(dict(chosen=tuple(selected_incomplete),selected=selected,cdf=cdf,sxx=sxx))
            assert len(options)==math.comb(len(candidates),k)
            cdf=min(options,key=lambda z:(round(z['cdf'],14),-round(z['sxx'],14),z['chosen']))
            sxx=min(options,key=lambda z:(-round(z['sxx'],14),round(z['cdf'],14),z['chosen']))
            selections={'warm90':years[warm],'cdf_all_years':cdf['selected'],'sxx_all_years':sxx['selected'],'all':years}
            accounting.append(ident|dict(n_full=len(years),n_incomplete=len(candidates),k=k,n_subsets=len(options),choice=0<k<len(candidates),all_incomplete_kept=k==len(candidates),no_incomplete_kept=k==0))
            def score(selected):
                nonlocal max_identity_error
                take=np.isin(years,selected);ws=np.zeros(len(years));ws[take]=weights(selected);d=ws-wfull
                year_error=float(d@truth);rec=float(ws@(point-truth));estimate=float(ws@point-beta)
                checks=[abs(year_error-float(d@residual)),abs(d.sum()),abs(float(d@x)),abs(estimate-year_error-rec)]
                max_identity_error=max(max_identity_error,*checks);assert max(checks)<1e-10
                g=float(d@d)
                selected_x=(years[take]-years[take].mean())/10
                g_formula=float(1/np.dot(selected_x,selected_x)-1/np.dot(x,x))
                assert abs(g-g_formula)<1e-10
                return dict(estimate_error=estimate,year_set_error=year_error,reconstruction_error=rec,estimate_mse=estimate**2,year_set_mse=year_error**2,reconstruction_mse=rec**2,cross_term=2*year_error*rec,weight_distance_squared=g,iid_linear_expected_year_set_mse=sigma2*g,
                            reference_slope=beta,reference_residual_variance=sigma2,slope_sign_disagreement=int((estimate+beta)*beta<0),retained_years=';'.join(map(str,selected)),n_retained=len(selected))
            for scheme,selected in selections.items():
                scored=score(selected)
                if scheme=='warm90':assert abs(scored['estimate_error']-case.estimate_error)<1e-10
                rows.append(ident|dict(scheme=scheme)|scored)
            sampled=[score(option['selected']) for option in options]
            metrics=['estimate_mse','year_set_mse','reconstruction_mse','cross_term','weight_distance_squared','iid_linear_expected_year_set_mse','slope_sign_disagreement']
            rows.append(ident|dict(scheme='uniform_exact',n_retained=int(warm.sum()),reference_slope=beta)|{name:float(np.mean([a[name] for a in sampled])) for name in metrics})
        print(family,len(roster),'archives checked',flush=True)
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'retention_geometry_cases.csv',index=False)
    account=pd.DataFrame(accounting);account.to_csv(OUT/'retention_choice_counts.csv',index=False)
    summaries=[];intervals=[]
    for (family,scheme),b in frame.groupby(['family','scheme']):
        summaries.append(dict(family=family,scheme=scheme,n=len(b),stations=b.station_key.nunique(),groups=b.independence_group.nunique(),estimate_rmse=float(np.sqrt(b.estimate_mse.mean())),year_set_rmse=float(np.sqrt(b.year_set_mse.mean())),reconstruction_rmse=float(np.sqrt(b.reconstruction_mse.mean())),iid_linear_working_year_set_rmse=float(np.sqrt(b.iid_linear_expected_year_set_mse.mean())),cross_term=float(b.cross_term.mean()),mean_years=float(b.n_retained.mean()),sign_disagreement_count_or_expectation=float(b.slope_sign_disagreement.sum())))
    for family,b in frame.groupby('family'):
        for scheme in ['cdf_all_years','sxx_all_years','uniform_exact','all']:
            intervals.append(dict(family=family)|paired_interval(b,scheme))
    pd.DataFrame(summaries).to_csv(OUT/'retention_geometry_summary.csv',index=False)
    pd.DataFrame(intervals).to_csv(OUT/'retention_paired_intervals.csv',index=False)
    return dict(max_exact_weight_identity_error=max_identity_error,annual_design_prediction_digest=input_digest.hexdigest(),case_rows=len(frame),archives=len(account),scope='Post-hoc reviewer diagnostics. The iid linear variance benchmark is assumption-dependent; no percentage of error is causally attributed to geometry. Calendar tests are simulated empirical-calendar masks, not accuracy validation on genuinely unknown missing values.')


def estimator_tradeoff():
    trends=pd.read_csv(BASE/'trends.csv')
    selected=trends.loc[trends['mode'].eq('forward')&trends.dependence.eq('point')&trends.retention.eq('all')]
    rows=[];paired=[];unavailable=[]
    for family,b in selected.groupby('family'):
        for method,p in b.groupby('estimator'):
            avail=p.loc[p.available & p.error.notna()]
            rows.append(dict(family=family,estimator=method,available=len(avail),total=len(p),available_rmse=float(np.sqrt(avail.squared_error.mean()))))
        valid=b.loc[b.available & b.error.notna()]
        wide=valid.pivot(index=KEY,columns='estimator',values='error')
        for other in ['plug_in','stochastic_calibrated']:
            pair=wide[['D2',other]].dropna();case=pair.rename(columns={other:'comparator'}).reset_index().melt(id_vars=KEY,value_vars=['D2','comparator'],var_name='scheme',value_name='error');case['estimate_mse']=case.error**2
            interval=paired_interval(case,'D2',baseline='comparator')
            paired.append(dict(family=family,comparator=other,D2_rmse=float(np.sqrt(pair.D2.pow(2).mean())),comparator_rmse=float(np.sqrt(pair[other].pow(2).mean())))|interval)
        miss=wide.loc[wide.stochastic_calibrated.isna()&wide.D2.notna(),'D2']
        unavailable.append(dict(family=family,classical_unavailable_D2_available=len(miss),D2_rmse_on_that_subset=float(np.sqrt(miss.pow(2).mean()))))
    pd.DataFrame(rows).to_csv(OUT/'point_estimator_availability.csv',index=False)
    pd.DataFrame(paired).to_csv(OUT/'point_estimator_paired_comparison.csv',index=False)
    pd.DataFrame(unavailable).to_csv(OUT/'point_estimator_unavailable_subset.csv',index=False)


if __name__=='__main__':
    inputs=[REF,OLD,BASE/'trends.csv',ROOT/'paper/wrr_tr/review_completion_article.tex',ROOT/'scripts/980_final_release.py']
    before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    report=retention_geometry();estimator_tradeoff()
    assert before=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    report.update(date='2026-10-31 Asia/Shanghai',exploratory=True,new_models_fit=False,manuscript_or_existing_outputs_changed=False,seed=SEED,bootstraps=BOOT,input_sha256=before)
    (OUT/'scope.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

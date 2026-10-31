#!/usr/bin/env python3
"""Reviewer arithmetic and release checks, separate from manuscript generators.

Reads saved draws/annual inputs and writes only the new reviewer directory.
No daily models are fitted and no publication outputs are changed.
"""
from pathlib import Path
import hashlib
import itertools
import json
import math
import subprocess
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'results/wrr_multiview_review_20261031'
EXP = ROOT / 'results/wrr_process_experiments_20261029'
CAL = EXP / 'source_calibration'
KEY = ['station_key', 'replicate', 'independence_group']
Q = ['q05', 'q10', 'q25', 'q50', 'q75', 'q90', 'q95']
P = np.array([.05,.10,.25,.50,.75,.90,.95])
OUT.mkdir(parents=True, exist_ok=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def project(q, bound):
    return np.maximum(q, np.where(np.isfinite(bound), bound, -np.inf)[:,None])


def source_calibration():
    source = pd.read_parquet(CAL/'source_union_cases.parquet').set_index('case_id')
    roles = pd.read_csv(CAL/'source_role_cases.csv')
    draws = pd.read_parquet(CAL/'full/source_nested_draws.parquet')
    native = draws.loc[draws.seed.eq(0)].set_index('case_id').reindex(source.index)
    native_error = max(np.max(abs(np.asarray(a)-np.asarray(b))) for a,b in zip(native.native20, source.stochastic_h30_draws))
    assert native_error == 0 and len(source)==2370
    stored = pd.read_csv(CAL/'full/source_reestimated_offsets.csv').set_index(['region','seed','count','cell'])
    targets = pd.read_csv(CAL/'fixed_target_cases.csv').set_index(['station_key','year'])
    target_draws = pd.read_parquet(CAL/'full/target_nested_draws.parquet').set_index(['station_key','year','seed'])
    scored = pd.read_csv(CAL/'full/target_three_layer_cases.csv').set_index(['station_key','year','seed','count','layer'])
    old = json.loads((ROOT/'results/wrr_review_response_20261027/whole_archive/classical_calibration.json').read_text())['forward']
    errors, target_errors, pools, corrections = [], [], [], {}
    for region, role in roles.groupby('calibration_region'):
        assert role.year.lt(2010).all() and role.training_partition.eq('train').all()
        assert not set(role.independence_group)&set(targets.loc[targets.region.eq(region),'independence_group'])
        assert role.groupby('independence_group').calibration_weight.nunique().eq(1).all()
        local=source.loc[role.case_id]; weight=role.calibration_weight.to_numpy(int)
        pools.append(dict(region=region, cases=len(role), stations=int(role.station_key.nunique()), groups=int(role.independence_group.nunique()), multiplicity_rows=int(weight.sum())))
        for seed in [0,1,2]:
            samples=np.stack(draws.loc[draws.seed.eq(seed)].set_index('case_id').loc[role.case_id,'draws'].to_numpy())
            for count in [20,100,500]:
                q=project(np.quantile(samples[:,:count],P,axis=1).T, local.observed_lower_bound__observed_days.to_numpy(float))
                for cell in old[region]['offsets']['stochastic']:
                    selected=local.difficulty.eq(cell).to_numpy()
                    if cell=='__pooled__' or selected.sum()<50:
                        selected=np.ones(len(local), dtype=bool)
                    residual=local.eval_truth_h30.to_numpy(float)[selected,None]-q[selected]
                    expanded=np.repeat(residual,weight[selected],axis=0)
                    c=np.array([np.quantile(expanded[:,j],p,method='lower' if p<.5 else 'higher') for j,p in enumerate(P)])
                    saved=stored.loc[(region,seed,count,cell)]
                    error=float(np.max(abs(c-saved[[f'offset{int(p*100):02d}' for p in P]].to_numpy(float))))
                    errors.append(error); corrections[region,seed,count,cell]=c
                    assert int(selected.sum())==saved.selected_pool_cases
    for (station,year), case in targets.iterrows():
        for seed in [0,1,2]:
            values=np.asarray(target_draws.loc[(station,year,seed),'draws'])
            for count in [20,100,500]:
                q=project(np.quantile(values[:count],P)[None,:],np.array([case.bound]))[0]
                for layer, correction in [('uncalibrated',np.zeros(7)),('fixed_old_offset',old[case.region]['offsets']['stochastic'][case.difficulty]),('reestimated_source_offset',corrections[case.region,seed,count,case.difficulty])]:
                    final=project(np.sort(q+correction)[None,:],np.array([case.bound]))[0]
                    saved=scored.loc[(station,year,seed,count,layer)]
                    target_errors.append(float(np.max(abs(final-saved[Q].to_numpy(float)))))
                    assert abs(abs(final[3]-case.truth)-saved.mae)<1e-10
    assert max(errors)<1e-10 and max(target_errors)<1e-10
    summary=scored.reset_index().groupby(['seed','count','layer','region']).agg(n=('mae','size'),mae=('mae','mean'),crps=('crps256_normal','mean'),width=('width90','mean'),covered=('covered90','sum')).reset_index()
    summary.to_csv(OUT/'calibration_score_recheck.csv',index=False)
    write('source_calibration_arithmetic.json',dict(status='passed',source_cases=len(source),source_roles=pools,source_native20_draw_max_error=float(native_error),offset_vectors_checked=len(errors),max_offset_error=max(errors),target_distributions_checked=len(target_errors),max_target_quantile_error=max(target_errors),scope='Independent arithmetic from stored source and target draws; daily fitting and fresh trajectory generation are separate checks.'))


def geometry(years, full):
    y=np.asarray(years,float); f=np.asarray(full,float); grid=np.arange(f.min(),f.max()+1)
    distance=float(np.mean(((y[:,None]<=grid).mean(axis=0)-(f[:,None]<=grid).mean(axis=0))**2))
    return distance,float(np.sum((y-y.mean())**2)/100)


def slope(years, values):
    x=(np.asarray(years,float)-np.mean(years))/10
    return float(np.linalg.lstsq(np.column_stack([np.ones(len(x)),x]),values,rcond=None)[0][1])


def time_selection():
    inputs=pd.read_parquet(EXP/'time_frozen_replay/annual_inputs.parquet')
    accounting=pd.read_parquet(EXP/'time_archive_accounting.parquet').set_index(KEY)
    subsets=pd.read_parquet(EXP/'time_all_feasible_subsets.parquet').set_index(KEY+['subset_id'])
    fixed=pd.read_parquet(EXP/'time_fixed_geometry_selections.parquet').set_index(KEY+['scheme'])
    rows, max_error, choices_checked = [], 0., 0
    for key, data in inputs.groupby(KEY,sort=True):
        data=data.sort_values('year'); years=data.year.to_numpy(int)
        y=data.truth_h30.to_numpy(float); pred=data.point_h30.to_numpy(float)
        full_slope=slope(years,y); a=accounting.loc[key]
        if not a.original_common: continue
        complete=years[~data.missing.to_numpy(bool)]; incomplete=years[data.missing.to_numpy(bool)]
        candidates=[]
        for i,chosen in enumerate(itertools.combinations(incomplete,int(a.k))):
            kept=np.sort(np.r_[complete,chosen]).astype(int); take=np.isin(years,kept)
            s=slope(kept,y[take])-full_slope; e=slope(kept,pred[take])-full_slope; r=e-s
            saved=subsets.loc[key+(i,)]
            assert ';'.join(map(str,kept))==saved.retained_years
            max_error=max(max_error,float(np.max(abs(np.array([e,s,r])-saved[['estimate_error','year_set_error','reconstruction_error']].to_numpy(float)))))
            d,spread=geometry(kept,years)
            assert abs(d-saved.cdf_distance)<1e-12 and abs(spread-saved.sxx)<1e-12
            candidates.append(dict(subset_id=i,years=kept,chosen=chosen,distance=d,spread=spread,e=e,s=s,r=r))
        assert len(candidates)==math.comb(len(incomplete),int(a.k))
        cdf=min(candidates,key=lambda c:(round(c['distance'],14),-round(c['spread'],14),c['chosen']))
        sxx=min(candidates,key=lambda c:(-round(c['spread'],14),round(c['distance'],14),c['chosen']))
        for scheme,c in [('cdf_all_years',cdf),('sxx_all_years',sxx)]:
            assert ';'.join(map(str,c['years']))==fixed.loc[key+(scheme,),'retained_years']; choices_checked+=1
        if not a.primary: continue
        for scheme in ['warm90','cdf_all_years','sxx_all_years','all']:
            saved=fixed.loc[key+(scheme,)]; kept=np.array(list(map(int,saved.retained_years.split(';')))); take=np.isin(years,kept)
            e=slope(kept,pred[take])-full_slope
            rows.append(dict(zip(KEY,key))|dict(region=data.region.iloc[0],scheme=scheme,n_years=len(kept),reference_slope=full_slope,error=e,squared_error=e*e))
    assert max_error<1e-10
    result=pd.DataFrame(rows);result.to_csv(OUT/'time_independent_cases.csv',index=False)
    summary=result.groupby('scheme').agg(n=('error','size'),mse=('squared_error','mean'),mean_years=('n_years','mean'));summary['rmse']=np.sqrt(summary.mse)
    summary.reset_index().to_csv(OUT/'time_primary_recheck.csv',index=False)
    heterogeneity=[]
    for unit in ['station_key','independence_group']:
        w=result.groupby([unit,'scheme']).squared_error.mean().unstack().pow(.5)
        for label,row in w.iterrows():
            heterogeneity.append(dict(unit=unit,label=label,**row.to_dict(),all_minus_warm=row['all']-row.warm90,sxx_minus_warm=row.sxx_all_years-row.warm90,cdf_minus_warm=row.cdf_all_years-row.warm90))
    pd.DataFrame(heterogeneity).to_csv(OUT/'time_station_group_heterogeneity.csv',index=False)
    w=result.pivot(index=KEY,columns='scheme',values='squared_error');g=w.index.get_level_values('independence_group'); unique=sorted(set(g));n=np.array([(g==v).sum() for v in unique]);rng=np.random.default_rng(2026102969)
    multiplicity=rng.multinomial(len(unique),np.full(len(unique),1/len(unique)),size=10000); denominator=multiplicity@n
    baseline=np.array([w.loc[g==v,'warm90'].sum() for v in unique]); contrasts=[]
    for name in ['cdf_all_years','sxx_all_years','all']:
        ss=np.array([w.loc[g==v,name].sum() for v in unique]); delta=np.sqrt(multiplicity@ss/denominator)-np.sqrt(multiplicity@baseline/denominator)
        contrasts.append(dict(scheme=name,n=len(w),groups=len(unique),rmse_difference=float(np.sqrt(w[name].mean())-np.sqrt(w.warm90.mean())),low=float(np.quantile(delta,.025)),high=float(np.quantile(delta,.975))))
    pd.DataFrame(contrasts).to_csv(OUT/'time_paired_intervals_recheck.csv',index=False)
    slopes=result.loc[result.scheme.eq('all'),'reference_slope']
    write('time_selection_arithmetic.json',dict(status='passed',raw_archives=len(accounting),common_archives=int(accounting.original_common.sum()),masked_common_archives=int(accounting.primary.sum()),choices_checked=choices_checked,feasible_sets=len(subsets),max_saved_error_discrepancy=max_error,reference_slope_median=float(slopes.median()),reference_slope_q25=float(slopes.quantile(.25)),reference_slope_q75=float(slopes.quantile(.75)),scope='Independent least-squares fits and geometry optimization from frozen annual inputs; group bootstrap matches the stated seed and sampling scheme.'))


def release_state():
    archive=ROOT/'dist/wrr_process_experiments_20261029.zip'; mismatches=[]; missing=[]; checked=0
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if info.is_dir() or info.filename in ['REVIEW_PACKAGE_README.txt','dependency_inventory.json']: continue
            path=ROOT/info.filename
            if not path.exists(): missing.append(info.filename);continue
            checked+=1
            packaged=hashlib.sha256(z.read(info)).hexdigest(); current=sha(path)
            if packaged!=current: mismatches.append(dict(path=info.filename,package_sha256=packaged,current_sha256=current))
    validation=json.loads((EXP/'validation.json').read_text())
    pdf=[]
    for name in ['review_completion_article.pdf','review_completion_supporting.pdf']:
        path=ROOT/'paper/wrr_tr'/name; metadata=subprocess.check_output(['pdfinfo',str(path)],text=True);pages=int(next(line.split(':',1)[1] for line in metadata.splitlines() if line.startswith('Pages:')))
        old=validation['manuscripts'][str(path.relative_to(ROOT))]
        pdf.append(dict(path=str(path.relative_to(ROOT)),pages=pages,sha256=sha(path),receipt_pages=old['pages'],receipt_sha256=old['sha256'],receipt_matches=old['sha256']==sha(path)))
    write('current_release_state.json',dict(package=str(archive.relative_to(ROOT)),package_sha256=sha(archive),files_compared=checked,changed_files=mismatches,missing_current_files=missing,manuscripts=pdf,note='An older package is not evidence for current uncommitted manuscript changes; this check does not rebuild or alter the package.'))


if __name__=='__main__':
    sources=[ROOT/'paper/wrr_tr/review_completion_article.tex',ROOT/'paper/wrr_tr/review_completion_article.pdf',ROOT/'paper/wrr_tr/review_completion_supporting.tex',ROOT/'paper/wrr_tr/review_completion_supporting.pdf',ROOT/'scripts/968_process_source_calibration.py',ROOT/'scripts/969_time_gap_sensitivity.py',EXP/'time_frozen_replay/annual_inputs.parquet',CAL/'full/source_nested_draws.parquet',CAL/'full/source_reestimated_offsets.csv',CAL/'full/target_three_layer_cases.csv']
    initial={str(p.relative_to(ROOT)):sha(p) for p in sources}
    source_calibration();print('source calibration arithmetic passed',flush=True)
    time_selection();print('time selection arithmetic passed',flush=True)
    release_state();print('release state recorded',flush=True)
    assert initial=={str(p.relative_to(ROOT)):sha(p) for p in sources}
    write('audit_scope.json',dict(date='2026-10-31 Asia/Shanghai',head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),inputs_sha256=initial,scope='Current workspace review; saved-result arithmetic and version identity; not raw-data or whole-model reproduction',scientific_outputs_modified=False))

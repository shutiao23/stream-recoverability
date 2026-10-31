#!/usr/bin/env python3
"""Audit donor-panel provenance in the candidate source-model sensitivity.

Provider labels and catalog matches are evidence of recorded provenance, not a
licence decision. Reconstruct donor visibility from saved masks and processed
panels; do not alter model training, predictions or historical analysis plans.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.estimators import DONOR_COVERAGE_FOR_USE
from stream_recoverability.seeds import plain_seed

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026/donor_provenance'
SOURCE=ROOT/'private/wrr_open_source_sensitivity_20261026/candidate_cases'
SPLITS={'offline':'leave_one_year_out','forward':'before_2010'}

def source_jobs():
    core=T.load_script('donor_provenance_jobs',ROOT/'scripts/431_tr_cases.py')
    return pd.DataFrame(core.jobs_for('source'))

def freeze():
    out=OUT/'donor_provenance_plan.json'
    if out.exists():raise FileExistsError('Preserve existing provenance plan')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE.relative_to(ROOT))+'/test'],cwd=ROOT).returncode:raise ValueError('Private destination is not ignored')
    original=json.loads((OUT/'plan.json').read_text());jobs=source_jobs();allowed=set(original['allowed_providers'])
    paths=sorted(set(jobs.loc[jobs.provider.isin(allowed),'input_path']))
    required=[Path(__file__),OUT/'plan.json',ROOT/'scripts/431_tr_cases.py',ROOT/'scripts/351_wrr_representative_recovery.py',
              ROOT/'src/stream_recoverability/experiments/v17_fitness/estimators.py',T.E1/'station_years.parquet',T.COVERAGE,T.E1/'usgs_site_metadata.csv']
    required += [SOURCE/s/'seed_00.parquet' for s in SPLITS.values()]
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);OUT.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for p in list(dict.fromkeys(required+[Path(x) for x in paths])):
        p=p.resolve()
        if not p.is_relative_to(ROOT.resolve()) or not p.is_file():raise ValueError('Required input outside workspace or unavailable')
        manifest.append({'path':str(p.relative_to(ROOT)),})
    mf=PRIVATE/'input_manifest.json';mf.write_text(json.dumps(manifest,indent=2)+'\n');mf.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'posthoc after candidate source model and a preliminary panel header scan; not preregistered',
          'scope':'Candidate source cases, seed zero, offline and before-2010 modes; source panel column labels and visible donor identities reconstructed from saved mask runs.',
          'visibility':'Use each panel and 90% masked-day donor availability threshold, separately for each saved case; compare reconstructed donor count to recorded n_visible_donors. A finite stored donor-ridge H30 indicates the donor estimator completed on the recorded visible set, conditional on the checked implementation and unchanged panel.',
          'catalogs':'Classify donor identities by matching provider, network and station against the station-year inventory and coverage table; additionally check USGS station identifier in the local USGS metadata. A match is an attribution clue, not a legal or sensor-quality determination. A nonmatch is unresolved, not proof of restricted origin.',
          'roles':'Summarize all eligible candidate cases and source cases with positive original bootstrap weight for each mode, target region and source role. These repeat station-years and masks.',
          'limits':'The same processed panels and saved source cases are reused. This does not independently reproduce every daily regression or its historical inputs, prove actual provider-native lineage, determine derivative permissions, or grant publication rights.',
          }
    out.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded post-hoc donor provenance audit plan')

def visible_columns(notna,mask):
    mask=np.asarray(mask,bool)
    if not mask.any():raise ValueError('No hidden days in source case')
    return np.mean(notna[mask],axis=0)>=DONOR_COVERAGE_FOR_USE

def verify_inputs():
    plan=json.loads((OUT/'donor_provenance_plan.json').read_text());mf=PRIVATE/'input_manifest.json'
    return plan

def main_run():
    plan=verify_inputs();original=json.loads((OUT/'plan.json').read_text());allowed=set(original['allowed_providers'])
    jobs=source_jobs();jobs=jobs.loc[jobs.provider.isin(allowed)].copy()
    if jobs.duplicated(['network_id','station_id']).any():raise ValueError('Ambiguous network/station job')
    station=pd.read_parquet(T.E1/'station_years.parquet',columns=['network_id','provider','station_id'])
    coverage=pd.read_csv(T.COVERAGE,dtype=str,usecols=['network_id','provider','station_id'])
    station_keys=set(zip(station.network_id.astype(str),station.provider.astype(str),station.station_id.astype(str)))
    coverage_keys=set(zip(coverage.network_id.astype(str),coverage.provider.astype(str),coverage.station_id.astype(str)))
    usgs=set(pd.read_csv(T.E1/'usgs_site_metadata.csv',dtype={'site_no':str}).site_no.astype(str))
    source={}
    for mode,split in SPLITS.items():
        frame=pd.read_parquet(SOURCE/split/'seed_00.parquet')
        frame=frame.loc[frame.policy_choice.ne('unavailable')&frame.eval_truth_h30.notna()].copy().reset_index(drop=True)
        if len(frame)!=original['splits'][split]['candidate_case_rows_after_filter']:raise ValueError('Source eligibility differs')
        frame['station_id']=frame.station_id.astype(str);source[mode]=frame
    jobkeys=set(zip(jobs.network_id.astype(str),jobs.station_id.astype(str)))
    for mode,frame in source.items():
        if not set(zip(frame.network_id.astype(str),frame.station_id)).issubset(jobkeys):raise ValueError('Case is missing source-panel job')
    job_by_key={(str(r.network_id),str(r.station_id)):r for r in jobs.itertuples(index=False)}
    records={mode:[] for mode in SPLITS};panels=[]
    used_keys=set().union(*(set(zip(f.network_id.astype(str),f.station_id)) for f in source.values()))
    paths=sorted({job_by_key[k].input_path for k in used_keys})
    for position,path in enumerate(paths,1):
        group=jobs[jobs.input_path.eq(path)];providers=set(group.provider.astype(str));networks=set(group.network_id.astype(str))
        if len(providers)!=1 or len(networks)!=1:raise ValueError('Panel has ambiguous job provider or network')
        provider=next(iter(providers));network=next(iter(networks))
        with open(path,encoding='utf-8-sig',newline='') as f:header=next(csv.reader(f))
        if header[0]!='date' or len(set(header))!=len(header):raise ValueError('Ambiguous source panel columns')
        panel=read_temperature_panel(path).asfreq('D');panel.columns=panel.columns.astype(str)
        if list(panel.columns)!=header[1:]:raise ValueError('Panel columns differ from raw header')
        # All candidate source networks are Northern Hemisphere; fail closed on a nonzero shift.
        if any(T.hemisphere_shift_days(x)!=0 for x in group.latitude):raise ValueError('Analysis date shift needs separate audit')
        names=np.array(panel.columns,dtype=str);in_station=np.array([(network,provider,c) in station_keys for c in names])
        in_coverage=np.array([(network,provider,c) in coverage_keys for c in names])
        in_usgs=np.array([provider=='usgs' and c in usgs for c in names])
        outside_all=~(in_station|in_coverage|in_usgs);outside_station=~in_station
        panels.append({'provider':provider,'columns':len(names),'outside_station_inventory':int(outside_station.sum()),
                       'outside_all_local_catalogs':int(outside_all.sum())})
        for mode,frame in source.items():
            subset=frame.loc[frame.network_id.astype(str).eq(network)]
            if subset.empty:continue
            for (station_id,year),cases in subset.groupby(['station_id','year'],sort=False):
                if station_id not in panel:raise ValueError('Target missing in source panel')
                idx=panel.index.year==int(year);arr=panel.loc[idx].notna().to_numpy();names_without_target=names!=station_id
                if len(arr) not in (365,366):raise ValueError('Source case year is not a full daily index')
                for runs,group_rows in cases.groupby('mask_runs',sort=False,dropna=False):
                    mask=T.mask_from_runs(str(runs),len(arr));visible=visible_columns(arr,mask)&names_without_target
                    outside1=bool(np.any(visible&outside_station));outside3=bool(np.any(visible&outside_all))
                    if not group_rows.n_visible_donors.astype(int).eq(int(visible.sum())).all():
                        raise ValueError('Visible donor count differs from saved cases')
                    records[mode].append(pd.DataFrame({'row':group_rows.index.to_numpy(),'visible_outside_station_inventory':outside1,
                        'visible_outside_all_local_catalogs':outside3,'visible_count':int(visible.sum())}))
        print(f'Candidate donor panels checked: {position}/{len(paths)}',flush=True)
    strict=T.load_script('donor_provenance_strict',ROOT/'scripts/610_strict_region_refit.py').strict_module()
    summary=[];roles_summary=[]
    for mode,frame in source.items():
        marks=pd.concat(records[mode],ignore_index=True)
        if marks.row.duplicated().any() or len(marks)!=len(frame) or set(marks.row)!=set(frame.index):raise ValueError('Incomplete visibility reconstruction')
        marks=marks.set_index('row').reindex(frame.index);frame=frame.join(marks)
        frame['finite_donor_estimate']=np.isfinite(pd.to_numeric(frame.h30__donor_ridge,errors='coerce'))
        for provider,group in frame.groupby('provider',sort=True):
            summary.append({'mode':mode,'provider':provider,'cases':len(group),'stations':group.station_key.nunique(),
                'visible_outside_station_inventory':int(group.visible_outside_station_inventory.sum()),
                'visible_outside_all_local_catalogs':int(group.visible_outside_all_local_catalogs.sum()),
                'finite_donor_estimate_outside_all_catalogs':int((group.finite_donor_estimate&group.visible_outside_all_local_catalogs).sum()),
                'policy_donor_outside_all_catalogs':int((group.policy_choice.eq('donor_ridge')&group.visible_outside_all_local_catalogs).sum())})
        safe=frame[['network_id','station_id','year','design_family','mask_runs','visible_outside_station_inventory',
                    'visible_outside_all_local_catalogs','finite_donor_estimate','policy_choice']]
        path=PRIVATE/(mode+'_case_flags.parquet');safe.to_parquet(path,index=False);path.chmod(0o600)
        regions=sorted(frame.region.unique())
        for item in original['target_mode_region_stations']:
            if item['mode']!=mode:continue
            region=item['region'];seed=plain_seed(7,0,regions.index(region));_,selected,weights=strict.roles(frame,region,seed)
            saved=json.loads((ROOT/'private/wrr_open_source_sensitivity_20261026/refits'/SPLITS[mode]/'seed_00'/(region+'.json')).read_text())
            if saved.get('roles')!=selected:raise ValueError('Reconstructed source roles differ from saved model metadata')
            for role,weight in weights.items():
                positive=np.asarray(weight)>0;unresolved=frame.visible_outside_all_local_catalogs.to_numpy(bool)
                finite=frame.finite_donor_estimate.to_numpy(bool)
                roles_summary.append({'mode':mode,'target_region':region,'role':role,'positive_case_rows':int(positive.sum()),
                    'positive_groups':int(frame.loc[positive,'independence_group'].nunique()),
                    'visible_outside_all_local_catalogs':int((positive&unresolved).sum()),
                    'finite_donor_estimate_outside_all_catalogs':int((positive&unresolved&finite).sum())})
    pd.DataFrame(panels).groupby('provider',as_index=False).sum().to_csv(OUT/'donor_provenance_panels.csv',index=False)
    pd.DataFrame(summary).to_csv(OUT/'donor_provenance_cases.csv',index=False)
    pd.DataFrame(roles_summary).to_csv(OUT/'donor_provenance_roles.csv',index=False)
    audit={'status':'completed_with_unresolved_provenance','source_cases':{m:len(f) for m,f in source.items()},
           'source_panels_checked':len(paths),'donor_visibility_counts_match_saved_cases':True,
           'roles_checked':len(roles_summary),'limits':plan['limits'],'privacy':'Station-case flags and input manifest are retained locally in an ignored directory.'}
    (OUT/'donor_provenance_status.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args()
    if a.action=='freeze':freeze()
    else:main_run()

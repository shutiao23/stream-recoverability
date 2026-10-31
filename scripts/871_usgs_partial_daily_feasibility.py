#!/usr/bin/env python3
"""Assess previously acquired USGS daily references and partial histories."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;REV=ROOT/'results/wrr_review_response_20261027';OUT=REV/'external_usgs_partial_daily';USGS=ROOT/'results/additional_usgs_observed';DATA=ROOT/'data/external/additional_usgs_observed';PRIVATE=ROOT/'private/wrr_usgs_partial_daily_20261027'

def valid_daily(frame):
    d=frame.copy();d['date']=pd.to_datetime(d.date)
    if d.date.duplicated().any():raise ValueError('Duplicate processed date')
    finite=np.isfinite(pd.to_numeric(d.water_c,errors='coerce'))
    usable=finite&d.reported.fillna(False)&~d.unapproved.fillna(True)&~d.ambiguous.fillna(True)&~d.estimated.fillna(True)
    return pd.Series(pd.to_numeric(d.water_c,errors='coerce').where(usable).to_numpy(float),index=d.date).sort_index()

def history_ok(s):
    """Apply every part of the frozen partial-history availability rule."""
    a=s.isna().to_numpy();edges=np.diff(np.r_[False,a,False].astype(int));runs=np.flatnonzero(edges==-1)-np.flatnonzero(edges==1)
    return bool(len(s) in (365,366) and s.notna().mean()>=.75 and not a[0] and not a[-1]
                and (len(runs)==0 or int(runs.max())<=45))

def freeze():
    OUT.mkdir(parents=True,exist_ok=True);path=OUT/'feasibility_plan.json'
    if path.exists():raise FileExistsError('Preserve feasibility plan')
    initial=json.loads((USGS/'status.json').read_text());snapshot=json.loads((REV/'audit/usgs_observed_reproduction.json').read_text())
    if initial['n_acquired']!=10 or snapshot['status']!='passed':raise ValueError('Prior cohort not verified')
    cohort=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str});files=[USGS/'cohort_metadata.csv',USGS/'qualification.csv',USGS/'status.json',REV/'audit/usgs_observed_reproduction.json',Path(__file__),ROOT/'src/stream_recoverability/experiments/tr_revision/national.py']
    files.extend(DATA/'daily'/(str(site)+'.parquet') for site in cohort.station_id)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
      'status':'posthoc after all ten USGS station records, qualification outcomes and observation-only witnesses were examined; no model scores for this cohort have been computed',
      'cohort':'All ten previously acquired additional USGS stations; consider every full calendar year within 1981-2025. Do not select by H30 magnitude or model prediction.',
      'reference':'A target year needs every calendar day finite, approved, not ambiguous and no qualifier recognized as estimated by the existing parser. The source is USGS daily mean, not proven complete subdaily observations or error-free physical truth.',
      'history':'For each target, retain other years with >=75% finite usable days, finite endpoints and longest missing run <=45 days. Mark actual fully complete history count separately. This exploratory availability rule was already used in the reservoir partial-history analysis and was fixed before this USGS history scan; it is not a known accuracy guarantee.',
      'future_evaluation':'Any qualifying target with at least three other eligible histories may enter an explicitly posthoc partial-history model sensitivity. Do not score until a separate cohort, source exposure, time convention, weather and scoring plan is fixed. Do not call this the original four-complete-year protocol.',
      'limitations':'Previously opened, selected and nonrandom stations; approved does not mean error-free or nonestimated when qualifier vocabulary is incomplete. Daily values may conceal subdaily gaps, ice, repairs and timing changes. No source-network or independent-climate conclusion is available from this scan.',
      'stations':len(cohort),}
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen ten-site partial-history feasibility design')

def run():
    p=json.loads((OUT/'feasibility_plan.json').read_text())
    roster=pd.read_csv(USGS/'cohort_metadata.csv',dtype={'station_id':str,'hydrologic_unit_code':str});rows=[];target=[]
    for r in roster.itertuples(index=False):
        s=valid_daily(pd.read_parquet(DATA/'daily'/(r.station_id+'.parquet')));annual=[]
        for year in range(1981,2026):
            idx=pd.date_range(f'{year}-01-01',f'{year}-12-31');a=s.reindex(idx);missing=a.isna().to_numpy();edges=np.diff(np.r_[False,missing,False].astype(int));runs=np.flatnonzero(edges==-1)-np.flatnonzero(edges==1)
            annual.append({'station_id':r.station_id,'year':year,'days':len(a),'usable_days':int(a.notna().sum()),
              'max_missing_run':int(max(runs,default=0)),'complete_reference_daily':bool(a.notna().all()),'eligible_history':history_ok(a)})
        annual=pd.DataFrame(annual);rows.extend(annual.to_dict('records'))
        valid_history=set(annual.loc[annual.eligible_history,'year'].astype(int));complete=set(annual.loc[annual.complete_reference_daily,'year'].astype(int))
        for year in sorted(complete):
            history=sorted(valid_history-{year});target.append({'station_id':r.station_id,'year':year,'history_years':';'.join(map(str,history)),
               'eligible_histories':len(history),'complete_history_years':len(complete.intersection(history)),
               'eligible_partial_history':len(history)>=3,'latitude':r.latitude,'longitude':r.longitude,'native_zone':r.native_zone,
               'huc2':str(r.hydrologic_unit_code)[:2]})
    df=pd.DataFrame(rows);chosen=pd.DataFrame(target);PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name,frame in [('daily_year_feasibility.csv',df),('daily_target_roster.csv',chosen)]:
        file=PRIVATE/name;frame.to_csv(file,index=False);file.chmod(0o600)
    out={'status':'completed_feasibility_only','stations':len(roster),'station_years_checked':len(df),'complete_approved_no_detected_estimate_target_years':len(chosen),
      'stations_with_target_years':int(chosen.station_id.nunique()) if len(chosen) else 0,
      'target_years_with_three_partial_histories':int(chosen.eligible_partial_history.sum()) if len(chosen) else 0,
      'stations_with_three_partial_histories':int(chosen.loc[chosen.eligible_partial_history,'station_id'].nunique()) if len(chosen) else 0,
      'model_predictions_calculated':False,'target_h30_calculated_in_this_scan':False,'limitations':p['limitations']}
    (OUT/'feasibility_status.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()

#!/usr/bin/env python3
"""Prepare NASA POWER forcing for frozen exploratory NS sites, not strict validation."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'

def main():
    plan=json.loads((OUT/'plan.json').read_text());lock=json.loads((OUT/'source_calibration_lock.json').read_text())
    ref=json.loads((OUT/'reference_status.json').read_text())
    if ref['status']!='reported_clock_reference_built' or ref['model_scoring_performed']:raise RuntimeError('reference not in expected pre-score state')
    roster=pd.read_csv(OUT/'reference_year_roster.csv',dtype={'station_id':str})
    helper=T.load_script('ns_power_source',ROOT/'scripts/544_bc_exploratory_score.py')
    folder=OUT/'weather';folder.mkdir(parents=True,exist_ok=True)
    parts=[];records=[]
    for site,group in roster.groupby('station_id',sort=True):
        coords=group[['forcing_latitude','forcing_longitude']].drop_duplicates()
        if len(coords)!=1:raise ValueError('site has inconsistent forcing coordinates')
        row={'station_number':site,'latitude':float(coords.iloc[0].forcing_latitude),'longitude':float(coords.iloc[0].forcing_longitude)}
        f,reason=helper.weather(row,folder)
        if reason is None:
            f['network_id']='ns_'+site
            if f.date.duplicated().any():raise ValueError('duplicate forcing dates')
            f=f.sort_values('date');parts.append(f)
            by_date=f.set_index('date').air_temperature_c
            for year in sorted(group.year.astype(int)):
                dates=pd.date_range(f'{year}-01-01',f'{year+1}-01-01',freq='D',inclusive='left')
                vals=by_date.reindex(dates).to_numpy(float)
                records.append({'station_id':site,'year':year,'required_days':len(dates),'finite_days':int(np.isfinite(vals).sum()),'complete':bool(np.isfinite(vals).all()),'reason':None})
        else:
            for year in sorted(group.year.astype(int)):
                dates=pd.date_range(f'{year}-01-01',f'{year+1}-01-01',freq='D',inclusive='left')
                records.append({'station_id':site,'year':year,'required_days':len(dates),'finite_days':0,'complete':False,'reason':reason})
        print('Checked forcing for',site,'available',reason is None,flush=True)
    table=pd.DataFrame(records);table.to_csv(OUT/'forcing_qualification.csv',index=False)
    if len(parts):
        data=pd.concat(parts,ignore_index=True);path=OUT/'air_forcing.parquet'
        if path.exists():
            old=pd.read_parquet(path)
            try:pd.testing.assert_frame_equal(old,data,check_dtype=True,check_exact=True)
            except AssertionError as exc:raise RuntimeError('existing forcing differs; preserve it') from exc
        else:data.to_parquet(path,index=False)
    ok=len(table)==len(roster) and table.complete.all()
    status={'status':'forcing_complete' if ok else 'forcing_unavailable','candidate_station_years':len(roster),
        'forcing_complete_station_years':int(table.complete.sum()),'coordinates':'provincial map, rounded to 0.01 degree',
        'source':'NASA POWER T2M, daily local solar time','strict_reference_qualified':False,'model_scoring_performed':False,
        'limitation':'POWER is a gridded forcing, not station measurements; reported water day timezone remains unverified'}
    (OUT/'forcing_status.json').write_text(json.dumps(status,indent=2)+'\n');print(table.to_string(index=False));print(json.dumps(status,indent=2))
    if not ok:raise SystemExit(2)

if __name__=='__main__':main()

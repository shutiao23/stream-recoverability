#!/usr/bin/env python3
"""Post-hoc regulation labels and two-station influence sensitivity."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'summer_window_comparison'
SNAP=REV/'open_observed_record_snapshot'
TOL=5e-6

def describe(frame,label):
    if frame.empty:raise ValueError('Empty influence cohort')
    gap=frame.full_minus_summer
    return {'cohort':label,'complete_station_years':len(frame),'stations':frame.station_key.nunique(),
            'connected_groups':frame.independence_group.nunique(),
            'years_above_tolerance':int(gap.gt(TOL).sum()),'years_above_0p1_c':int(gap.gt(.1).sum()),
            'years_above_0p5_c':int(gap.gt(.5).sum()),'mean_gap_c':float(gap.mean()),
            'median_gap_c':float(gap.median()),'max_gap_c':float(gap.max())}

def run(output):
    plan=json.loads((OUT/'influence_plan.json').read_text())
    data=pd.read_csv(OUT/'complete_year_windows.csv')
    labels=pd.read_csv(OUT/'station_regulation_labels.csv')
    data=data.merge(labels,on='station_key',how='left',validate='many_to_one')
    if data.regulation_status.isna().any():raise ValueError('Missing project regulation label')
    chosen=set(plan['influence_excluded_stations'])
    rows=[describe(data,'all_95_stations'),describe(data[~data.station_key.isin(chosen)],'excluding_two_posthoc_stations')]
    rows.extend(describe(g,'label_'+str(label)) for label,g in data.groupby('regulation_status',sort=True))
    daily=pd.read_parquet(SNAP/'daily_temperature.parquet');daily['date']=pd.to_datetime(daily.date)
    daily=daily[daily.station_key.isin(chosen)]
    station_data={k:g.set_index('date').water_c.sort_index().astype(float) for k,g in daily.groupby('station_key',observed=True)}
    details=[]
    for r in data[data.station_key.isin(chosen)].itertuples(index=False):
        dates=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31')
        series=station_data[r.station_key].reindex(dates)
        if not np.isfinite(series.to_numpy()).all():raise ValueError('Selected complete reference year has missing values')
        rolling=series.rolling(30,min_periods=30).mean()
        end=rolling.idxmax();start=end-pd.Timedelta(days=29)
        if not np.isclose(rolling.loc[end],r.full_h30,atol=1e-10,rtol=0):raise ValueError('Peak-window location differs')
        details.append({'station_key':r.station_key,'year':int(r.year),'first_maximum_start':str(start.date()),
                        'first_maximum_end':str(end.date()),'full_h30':float(r.full_h30),
                        'summer_h30':float(r.summer_h30),'full_minus_summer':float(r.full_minus_summer)})
    details=pd.DataFrame(details)
    summary=pd.DataFrame(rows)
    output.mkdir(parents=True,exist_ok=True)
    summary.to_csv(output/'influence_summary.csv',index=False)
    details.to_csv(output/'selected_station_peak_windows.csv',index=False)
    (output/'influence_status.json').write_text(json.dumps({'status':'computed','labels':'original project metadata, unmatched does not mean unregulated',
        'selection':'the two sites were selected after observing individual annual gaps',
        'limitations':'no causal inference about dam operations; no independent sensor quality or physical error validation; first tied maximum is not necessarily unique'},indent=2)+'\n')
    print(summary.to_string(index=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=OUT);a=p.parse_args();run(a.output)

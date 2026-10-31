#!/usr/bin/env python3
"""Independently check post-hoc regulation labels and window locations."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
REV=ROOT/'results/wrr_review_response_20261027'
OUT=REV/'summer_window_comparison'
SNAP=REV/'open_observed_record_snapshot'


def main():
    plan=json.loads((OUT/'influence_plan.json').read_text())
    raw_labels=pd.read_csv(REV/'rules/eligible_station_years.csv',usecols=['station_key','regulation_status']).drop_duplicates()
    saved_labels=pd.read_csv(OUT/'station_regulation_labels.csv')
    labels=saved_labels.merge(raw_labels,on='station_key',how='left',suffixes=('_saved','_original'),validate='one_to_one')
    if labels.regulation_status_original.isna().any() or not labels.regulation_status_saved.eq(labels.regulation_status_original).all():
        raise ValueError('Project regulation labels differ')
    c=pd.read_csv(OUT/'complete_year_windows.csv').merge(saved_labels,on='station_key',validate='many_to_one')
    saved=pd.read_csv(OUT/'influence_summary.csv').set_index('cohort')
    cohorts={'all_95_stations':c,'excluding_two_posthoc_stations':c[~c.station_key.isin(plan['influence_excluded_stations'])]}
    cohorts.update({'label_'+name:g for name,g in c.groupby('regulation_status')})
    if set(saved.index)!=set(cohorts):raise ValueError('Influence cohort names differ')
    for name,frame in cohorts.items():
        row=saved.loc[name];gap=frame.full_h30.to_numpy(float)-frame.summer_h30.to_numpy(float)
        expected={'complete_station_years':len(frame),'stations':frame.station_key.nunique(),
                  'connected_groups':frame.independence_group.nunique(),'years_above_tolerance':int((gap>5e-6).sum()),
                  'years_above_0p1_c':int((gap>.1).sum()),'years_above_0p5_c':int((gap>.5).sum())}
        for key,value in expected.items():
            if int(row[key])!=value:raise ValueError('Influence count differs: '+name+'/'+key)
        for key,value in [('mean_gap_c',np.mean(gap)),('median_gap_c',np.median(gap)),('max_gap_c',np.max(gap))]:
            if not np.isclose(row[key],value,rtol=0,atol=1e-10):raise ValueError('Influence statistic differs: '+name+'/'+key)
    daily=pd.read_parquet(SNAP/'daily_temperature.parquet');daily['date']=pd.to_datetime(daily.date)
    daily=daily[daily.station_key.isin(plan['influence_excluded_stations'])]
    station={k:g.set_index('date').water_c.sort_index() for k,g in daily.groupby('station_key',observed=True)}
    windows=pd.read_csv(OUT/'selected_station_peak_windows.csv')
    for r in windows.itertuples(index=False):
        dates=pd.date_range(f'{r.year}-01-01',f'{r.year}-12-31')
        values=station[r.station_key].reindex(dates).to_numpy(float)
        means=np.convolve(values,np.ones(30),mode='valid')/30
        # np.argmax chooses the first exact maximum, as did pandas idxmax.
        start=int(np.argmax(means));end=start+29
        if str(dates[start].date())!=r.first_maximum_start or str(dates[end].date())!=r.first_maximum_end:
            raise ValueError('First maximizing window date differs')
        if not np.isclose(means[start],r.full_h30,rtol=0,atol=1e-10):raise ValueError('Selected full-window mean differs')
    expected=c[c.station_key.isin(plan['influence_excluded_stations'])][['station_key','year']]
    merged=expected.merge(windows[['station_key','year']],on=['station_key','year'],how='outer',indicator=True,validate='one_to_one')
    if not merged._merge.eq('both').all():raise ValueError('Selected-site years differ')
    report={'status':'passed','station_labels_checked':len(labels),'influence_cohorts_checked':len(cohorts),
            'selected_station_year_windows_checked':len(windows),
            'scope':'Independent sums and NumPy window reconstruction on the same processed records and existing project regulation metadata. It does not validate labels, infer causal effects, or independently verify sensor observations.'}
    (OUT/'influence_independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()

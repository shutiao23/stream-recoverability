#!/usr/bin/env python3
"""Screen frozen candidates using USGS approved-day counts, not temperatures."""
import calendar
import json
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_count_screen'
URL='https://api.waterdata.usgs.gov/statistics/v0/observationIntervals'


def extract_counts(doc, roster):
    index=roster.set_index('station_id')
    rows=[]
    seen=set()
    for feature in doc['features']:
        prop=feature['properties']; site=prop['monitoring_location_id'].removeprefix('USGS-')
        if site not in index.index: raise ValueError('Server returned unexpected site')
        for series in prop.get('data',[]):
            # This field identifies the daily value series that produced the statistic.
            if str(series.get('parent_time_series_id')) != str(index.loc[site,'series_id']) or str(series.get('parent_statistic_id')) != '00003': continue
            for val in series.get('values',[]):
                if val.get('interval_type')!='calendar_year' or val.get('approval_status')!='approved': continue
                start=pd.Timestamp(val['start_date']); end=pd.Timestamp(val['end_date']); y=start.year
                expected=366 if calendar.isleap(y) else 365
                if y not in range(2010,2025): continue
                if end.year != y: raise ValueError('Calendar statistic crossed years')
                full_year = start==pd.Timestamp(y,1,1) and end==pd.Timestamp(y,12,31)
                key=(site,y)
                if key in seen: raise ValueError(f'Duplicate series/year statistic: {key}')
                seen.add(key)
                count=int(val['sample_count'])
                rows.append(dict(station_id=site,year=y,approved_daily_count=count,expected_days=expected, interval_full_year=bool(full_year),
                                 count_complete=bool(full_year and count==expected)))
    return pd.DataFrame(rows,columns=['station_id','year','approved_daily_count','expected_days','interval_full_year','count_complete'])


def main():
    if not (OUT/'plan.json').exists(): raise RuntimeError('Freeze the candidate roster first')
    roster=pd.read_csv(OUT/'candidate_roster.csv',dtype=str)
    p=[('monitoring_location_id','USGS-'+x) for x in roster.station_id]+[
       ('parameter_code','00010'),('start_date','2010-01-01'),('end_date','2024-12-31'),
       ('interval_type','CY'),('computation_type','arithmetic_mean'),('page_size','100')]
    response=requests.get(URL,params=p,timeout=90,headers={'User-Agent':'stream-temperature reference research'})
    response.raise_for_status(); doc=response.json()
    if any(x.get('rel')=='next' for x in doc.get('links',[])):
        raise RuntimeError('Result paginated; do not silently treat first page as complete')
    # Only date/count metadata are retained; published annual means are discarded.
    counts=extract_counts(doc,roster)
    counts.to_csv(OUT/'approved_counts.csv',index=False)
    complete=counts.groupby('station_id').count_complete.sum().rename('n_count_complete_years')
    candidates=roster.merge(complete,on='station_id',how='left',validate='one_to_one')
    candidates['statistics_returned'] = candidates.station_id.isin(counts.station_id)
    candidates.n_count_complete_years=candidates.n_count_complete_years.astype('Int64')
    candidates['count_preflight_pass']=candidates.n_count_complete_years.ge(4).fillna(False)
    candidates.to_csv(OUT/'candidate_counts.csv',index=False)
    # Predeclared ranking by availability only, then distinct network components.
    eligible=candidates.loc[candidates.count_preflight_pass].sort_values(
        ['HUC2_region_proxy','n_count_complete_years','station_id'],ascending=[True,False,True])
    eligible=eligible.drop_duplicates('provisional_network_index_component')
    eligible=eligible.groupby('HUC2_region_proxy',sort=True,group_keys=False).head(2)
    selected=OUT/'cohort.csv'
    if selected.exists():
        prior=pd.read_csv(selected,dtype=str)
        if prior.series_id.tolist()!=eligible.series_id.tolist(): raise RuntimeError('Count-selected cohort changed; preserve prior roster')
    else: eligible.to_csv(selected,index=False)
    status={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'request_url':response.url,
            'metadata_candidates':len(roster),'statistics_features':len(doc['features']),
            'preflight_pass':int(candidates.count_preflight_pass.sum()),'statistics_not_returned':int((~candidates.statistics_returned).sum()),'selected':len(eligible),
            'annual_values_saved':False,'quality_caveat':'counts contain approved values, potentially including estimated or otherwise flagged values; verify individually',
            'design':'availability-selected unregistered exploratory roster; not a random sample or proof of independent climates'}
    (OUT/'preflight_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(candidates[['station_id','station_name','n_count_complete_years','count_preflight_pass']].to_string(index=False))
    print(json.dumps(status,indent=2))

if __name__=='__main__':main()

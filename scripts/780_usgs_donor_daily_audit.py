#!/usr/bin/env python3
"""Independent streaming/CSV recomputation of the USGS donor-date comparison."""
import csv
import gzip
import json
import math
from collections import Counter,defaultdict
from pathlib import Path
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026/donor_provenance';DAILY=PRIVATE/'usgs_daily';META=PRIVATE/'usgs_metadata'


def main():
    summary=json.loads((OUT/'donor_usgs_daily_comparison.json').read_text());receipt=json.loads((DAILY/'acquisition.json').read_text())
    if summary['status']!='computed_posthoc' or any(r['status']!='completed' for r in receipt):raise ValueError('Comparison or acquisition incomplete')
    observations=defaultdict(list);qualifiers=Counter();series=set()
    for batch in receipt:
        with gzip.open(DAILY/f"batch_{batch['batch']:02d}.json.gz",'rt') as f:response=json.load(f)
        for t in response['value']['timeSeries']:
            site=t['sourceInfo']['siteCode'][0]['value']
            for group in t['values']:
                for item in group.get('value',[]):
                    try:value=float(item['value'])
                    except (ValueError,TypeError):continue
                    if not math.isfinite(value) or value==-999999.:continue
                    observations[(site,str(item['dateTime'])[:10])].append(value)
                    qualifiers[';'.join(sorted(item.get('qualifiers',[])))]+=1;series.add((site,t.get('name','')))
    roster=pd.read_csv(META/'unresolved_columns.csv',dtype=str)
    jobs=pd.DataFrame(T.load_script('daily_independent_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source'))
    total=Counter();maximum=0.;distance_sum=0.;with_comparison=0;rows=0
    for network,group in roster.groupby('network_id'):
        paths=jobs[jobs.network_id.eq(network)&jobs.provider.eq('usgs')].input_path.unique()
        if len(paths)!=1:raise ValueError('Panel path ambiguous')
        sites=group.station_id.tolist();matched_by_site=Counter();seen=set()
        with open(paths[0],encoding='utf-8-sig',newline='') as f:
            for record in csv.DictReader(f):
                date=record['date']
                if date in seen:raise ValueError('Duplicate local dates')
                seen.add(date)
                for site in sites:
                    try:local=float(record[site])
                    except (ValueError,TypeError):continue
                    if not math.isfinite(local):continue
                    total['local_finite_days']+=1;values=observations.get((site,date),[])
                    if not values:continue
                    total['source_days']+=1
                    if max(values)-min(values)>1e-10:total['ambiguous_source_days']+=1;continue
                    delta=abs(local-min(values));total['compared_days']+=1;matched_by_site[site]+=1;distance_sum+=delta;maximum=max(maximum,delta)
                    if delta<=1e-6:total['equal_1e_6']+=1
                    if delta<=.01:total['equal_0_01']+=1
                    if delta>.1:total['different_over_0_1']+=1
        with_comparison+=sum(matched_by_site[site]>0 for site in sites);rows+=len(sites)
    for key in ['local_finite_days','source_days','ambiguous_source_days','compared_days','equal_1e_6','equal_0_01','different_over_0_1']:
        if total[key]!=summary[key]:raise AssertionError('Aggregate mismatch: '+key)
    if rows!=summary['panel_columns'] or with_comparison!=summary['columns_with_comparisons'] or len(series)!=summary['series_returned']:
        raise AssertionError('Site or series count differs')
    if dict(qualifiers)!=summary['source_qualifier_counts']:raise AssertionError('Qualifier counts differ')
    if total['compared_days'] and (not math.isclose(maximum,summary['maximum_absolute_difference'],abs_tol=1e-9)
            or not math.isclose(distance_sum/total['compared_days'],summary['mean_absolute_difference'],abs_tol=1e-10)):
        raise AssertionError('Difference magnitudes differ')
    result={'status':'passed','panel_columns':rows,'source_series':len(series),'compared_panel_column_days':total['compared_days'],
            'implementation':'Independent Python dictionaries, CSV parser and scalar comparisons; recomputes all returned daily values and all panel-column comparisons.',
            'limitations':'Same current USGS responses and local processed panels; does not reconstruct historical API responses, verify raw sensors, validate rights or assess independent-climate predictions.'}
    (OUT/'donor_usgs_daily_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()

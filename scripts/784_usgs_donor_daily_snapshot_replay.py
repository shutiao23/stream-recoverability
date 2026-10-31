#!/usr/bin/env python3
"""Offline integrity and source-observation audit of public USGS responses."""
import argparse
from collections import Counter,defaultdict
import gzip
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity';SNAP=OUT/'donor_usgs_daily_snapshot'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,default=ROOT/'results/wrr_review_response_20261027/audit/donor_usgs_daily_snapshot_replay.json');a=parser.parse_args()
    manifest=json.loads((SNAP/'request_manifest.json').read_text());summary=json.loads((OUT/'donor_usgs_daily_comparison.json').read_text())
    unique=set();qualifiers=Counter();source_dates=defaultdict(list);sites=set()
    for batch in manifest['batches']:
        path=SNAP/batch['file']
        requested=set(batch['sites'])
        if sites&requested:raise ValueError('Duplicate requested sites')
        sites |= requested
        with gzip.open(path,'rt') as f:payload=json.load(f)
        for ts in payload['value']['timeSeries']:
            site=ts['sourceInfo']['siteCode'][0]['value'];variable=ts['variable']
            if site not in requested or variable['variableCode'][0]['value']!='00010' or not any(x.get('optionCode')=='00003' for x in variable.get('options',{}).get('option',[])):
                raise ValueError('Unexpected site or statistic')
            for group in ts['values']:
                for v in group.get('value',[]):
                    try:value=float(v['value'])
                    except (TypeError,ValueError):continue
                    if not math.isfinite(value) or value==-999999:continue
                    unique.add((site,ts.get('name','')));qualifiers[';'.join(sorted(v.get('qualifiers',[])))]+=1
                    source_dates[(site,str(v['dateTime'])[:10])].append(value)
    if len(sites)!=69 or len(unique)!=summary['series_returned'] or dict(qualifiers)!=summary['source_qualifier_counts']:
        raise ValueError('USGS source summary differs')
    ambiguous=sum(max(v)-min(v)>1e-10 for v in source_dates.values())
    result={'status':'passed','requested_sites':len(sites),'source_series_with_numeric_values':len(unique),
            'numeric_source_values':sum(qualifiers.values()),'unique_site_dates':len(source_dates),
            'source_site_dates_with_different_values':ambiguous,'responses':len(manifest['batches']),
            'scope':'Offline replays the public USGS API responses only. It does not contain or recompute the locally cached water values, panel-column mapping, local comparisons, historical vintage, source quality or derivative permissions.'}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()

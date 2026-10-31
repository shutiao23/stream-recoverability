#!/usr/bin/env python3
"""Describe multi-valued USGS days after examining the primary comparison."""
import argparse
from datetime import datetime,timezone
import gzip
import json
import math
from collections import Counter,defaultdict
from pathlib import Path
import csv
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026/donor_provenance';DAILY=PRIVATE/'usgs_daily';META=PRIVATE/'usgs_metadata'

def freeze():
    dest=OUT/'donor_usgs_ambiguous_plan.json'
    if dest.exists():raise FileExistsError('Preserve ambiguity plan')
    base=json.loads((OUT/'donor_usgs_daily_comparison.json').read_text());audit=json.loads((OUT/'donor_usgs_daily_independent_audit.json').read_text())
    if base['status']!='computed_posthoc' or audit['status']!='passed':raise ValueError('Primary daily comparison incomplete')
    result={'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'posthoc after observing the 1,525 ambiguous panel-column days and inspecting one example; not a prespecified performance analysis',
        'cohort':'All panel-column days for the previously fixed 69 USGS site identifiers in the saved responses; no additional sites or network requests.',
        'questions':'For source days with distinct daily values, count whether the local value equals at least one or none of those values, the number of distinct values, and reported qualifier and method-set diversity. Report the unmatched source days separately.',
        'interpretation':'An any-value match is selected after seeing all returned alternatives and does not identify which source record produced the local value; it is weaker than a unique-source match.',
        }
    dest.write_text(json.dumps(result,indent=2)+'\n');print('Recorded post-hoc ambiguity analysis')

def run():
    plan=json.loads((OUT/'donor_usgs_ambiguous_plan.json').read_text())
    source=defaultdict(list)
    for batch in json.loads((DAILY/'acquisition.json').read_text()):
        path=DAILY/f"batch_{batch['batch']:02d}.json.gz"
        with gzip.open(path,'rt') as f:response=json.load(f)
        for ts in response['value']['timeSeries']:
            site=ts['sourceInfo']['siteCode'][0]['value']
            for block in ts['values']:
                methods=json.dumps(block.get('method',[]),sort_keys=True,separators=(',',':'))
                for x in block.get('value',[]):
                    try:value=float(x['value'])
                    except (ValueError,TypeError):continue
                    if not math.isfinite(value) or value==-999999:continue
                    source[(site,str(x['dateTime'])[:10])].append((value,tuple(sorted(x.get('qualifiers',[]))),methods))
    rows=pd.read_csv(META/'unresolved_columns.csv',dtype=str);jobs=pd.DataFrame(T.load_script('ambiguity_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source'))
    stats=Counter();spreads=[];distinct_counts=Counter();qualifier_patterns=Counter()
    for network,g in rows.groupby('network_id'):
        paths=jobs[jobs.network_id.eq(network)&jobs.provider.eq('usgs')].input_path.unique()
        if len(paths)!=1:raise ValueError('Panel path ambiguous')
        sites=g.station_id.tolist()
        with open(paths[0],encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                for site in sites:
                    try:local=float(row[site])
                    except (TypeError,ValueError):continue
                    if not math.isfinite(local):continue
                    values=source.get((site,row['date']),[])
                    if not values:stats['no_finite_source_days']+=1;continue
                    numbers=sorted({x[0] for x in values})
                    if numbers[-1]-numbers[0]<=1e-10:continue
                    stats['ambiguous_panel_column_days']+=1;distinct_counts[str(len(numbers))]+=1;spreads.append(numbers[-1]-numbers[0])
                    hits=[x for x in numbers if abs(local-x)<=1e-6]
                    stats['matches_at_least_one']+=bool(hits);stats['matches_none']+=not bool(hits)
                    stats['at_least_two_recorded_methods']+=len({x[2] for x in values})>1
                    qualifiers={x[1] for x in values};stats['multiple_qualifier_sets']+=len(qualifiers)>1
                    qualifier_patterns[' | '.join(';'.join(q) if q else '(none)' for q in sorted(qualifiers))]+=1
    base=json.loads((OUT/'donor_usgs_daily_comparison.json').read_text())
    if stats['ambiguous_panel_column_days']!=base['ambiguous_source_days'] or stats['no_finite_source_days']!=base['local_finite_days']-base['source_days']:
        raise AssertionError('Ambiguous or missing count differs from primary analysis')
    result={'status':'computed_posthoc',**{k:int(v) for k,v in stats.items()},'distinct_value_counts':dict(distinct_counts),
            'qualifier_set_patterns':dict(qualifier_patterns),'max_range_c':max(spreads) if spreads else None,
            'median_range_c':float(pd.Series(spreads).median()) if spreads else None,
            'limitations':plan['interpretation']+' Same-day multiple values may represent different series or methods; identifying their historical relationship requires provider documentation.'}
    (OUT/'donor_usgs_ambiguous_summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args();freeze() if a.action=='freeze' else run()

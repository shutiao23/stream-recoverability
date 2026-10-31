#!/usr/bin/env python3
"""Recompute reported-day field diagnostics using Python CSV and datetimes.

Both implementations reuse the same unverified timestamps and source files;
this is an arithmetic audit, not a time-matched or independent sensor test.
"""
from __future__ import annotations
from collections import Counter,defaultdict
import csv
from datetime import datetime,timedelta
import gzip
import json
import math
from pathlib import Path
import statistics
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_nova_field_checks'
PRIVATE=ROOT/'private/wrr_nova_scotia_field_checks_20261027';DATA=PRIVATE/'nova_scotia_field_v6.csv'
PORTAL=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified/portal_acquisition.json'
ROSTER=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory/reference_year_roster.csv'

def finite(value):
    try:x=float(value)
    except (ValueError,TypeError):return None
    return x if math.isfinite(x) else None

def same(a,b,label):
    if a is None:
        if not pd.isna(b):raise ValueError('Expected unavailable '+label)
    elif pd.isna(b) or not math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-10):
        raise ValueError('Aggregate differs: '+label)

def main():
    plan=json.loads((OUT/'comparison_plan.json').read_text());membership=json.loads((OUT/'hour_membership_plan.json').read_text())
    with ROSTER.open(newline='',encoding='utf-8') as f:selected={(r['station_id'],int(r['year'])) for r in csv.DictReader(f)}
    if len(selected)!=8:
        raise ValueError('Modeled reference-year roster differs')
    fields=[]
    with DATA.open(newline='',encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            site=row['MonitoringLocationID']
            if site not in plan['site_ids'] or row['CharacteristicName']!='Temperature, water' or row['ResultUnit']!='deg C':continue
            try:day=datetime.strptime(row['ActivityStartDate'],'%Y-%m-%d').date()
            except ValueError:raise ValueError('Invalid candidate field date') from None
            if day.year not in plan['years']:continue
            if row['ActivityStartTime'] or row['ActivityStartTimeZone'] or row['ResultStatusID']!='Preliminary':
                raise ValueError('Field timing or quality metadata differs')
            metadata=tuple((k,v) for k,v in row.items() if k!='ResultValue')
            fields.append({'site':site,'day':day,'value':finite(row['ResultValue']),'metadata':metadata})
    if len(fields)!=146:raise ValueError('Field case denominator differs')
    receipt=json.loads(PORTAL.read_text());hourly=defaultdict(list);ids=defaultdict(set)
    for page in receipt['pages']:
        site=page['station_id']
        if site not in plan['site_ids']:continue
        content=gzip.decompress((ROOT/page['file']).read_bytes())
        for row in json.loads(content):
            if row.get('station_number')!=site or row.get(':id') in ids[site] or ':id' not in row:raise ValueError('Portal row identity mismatch')
            ids[site].add(row[':id'])
            label=None
            for fmt in ('%Y-%m-%d %H:%M','%Y-%m-%d %H:%M:%S','%Y-%m-%d %H:%M:%S.%f'):
                try:label=datetime.strptime(row['date'][:10]+' '+row['time'],fmt);break
                except (KeyError,ValueError):pass
            if label is None:raise ValueError('Unparseable portal clock label')
            hourly[site,label.date()].append((label.hour,label.minute,label.second,label.microsecond,finite(row.get('temperature_c'))))
    days={}
    for key,items in hourly.items():
        if len(items)!=24 or {(h,m,s,u) for h,m,s,u,_ in items}!={(h,0,0,0) for h in range(24)} or any(v is None for *_,v in items):continue
        days[key]=[v for *_,v in sorted(items)]
    cases=[]
    for item in fields:
        site,day,value=item['site'],item['day'],item['value'];one=days.get((site,day));adj=[days.get((site,day+timedelta(days=k))) for k in (-1,0,1)]
        triple=[v for block in adj for v in block] if all(block is not None for block in adj) else None
        r={'site':site,'day':day,'value':value,'selected':(site,day.year) in selected}
        for name,arr in [('single',one),('triple',triple)]:
            if arr is None or value is None:r[name+'_range']=None;r[name+'_distance']=None
            else:
                r[name+'_range']=max(min(arr)-value,value-max(arr),0.)
                r[name+'_distance']=min(abs(v-value) for v in arr)
        cases.append(r)
    range_tables=[pd.read_csv(OUT/'range_summary.csv'),pd.read_csv(OUT/'selected_year_range_summary.csv')]
    range_table=pd.concat(range_tables,ignore_index=True);prox=pd.read_csv(OUT/'hour_membership_summary.csv')
    range_checked=prox_checked=0
    for scope,subset in [('all_2009_2017',cases),('modeled_years',[x for x in cases if x['selected']]),('other_years',[x for x in cases if not x['selected']])]:
        for site in ['both_sites',*plan['site_ids']]:
            g=subset if site=='both_sites' else [x for x in subset if x['site']==site]
            for window,source in [('same_day','single'),('three_day','triple')]:
                valid=[x for x in g if x[source+'_range'] is not None];events=defaultdict(list)
                for x in valid:events[x['site'],x['day']].append(x[source+'_range'])
                values=[x[source+'_range'] for x in valid]
                row=range_table[(range_table.scope==scope)&(range_table.site==site)&(range_table.window==window)]
                if len(row)!=1:raise ValueError('Range summary identity missing')
                row=row.iloc[0]
                quantities={'field_rows':len(g),'numeric_field_rows':sum(x['value'] is not None for x in g),
                            'site_dates':len({(x['site'],x['day']) for x in g}),'compared_rows':len(valid),
                            'compared_site_dates':len(events),'rows_outside_range':sum(v>0 for v in values),
                            'rows_over_0_5_c_outside':sum(v>.5 for v in values),'site_dates_any_outside':sum(max(v)>0 for v in events.values()),
                            'site_dates_any_over_0_5_c_outside':sum(max(v)>.5 for v in events.values()),
                            'median_range_excess_c':statistics.median(values) if values else None,
                            'maximum_range_excess_c':max(values) if values else None}
                for k,v in quantities.items():same(v,row[k],k)
                range_checked+=1
                ps={'all_2009_2017':'all','modeled_years':'modeled_years','other_years':'other_years'}[scope]
                prow=prox[(prox.scope==ps)&(prox.site==site)&(prox.window==source)]
                if len(prow)!=1:raise ValueError('Proximity summary identity missing')
                prow=prow.iloc[0];dist=[x[source+'_distance'] for x in valid];p_events=defaultdict(list)
                for x in valid:p_events[x['site'],x['day']].append(x[source+'_distance'])
                quantities={'field_rows':len(g),'compared_rows':len(valid),'compared_site_dates':len(p_events),
                            'rows_within_1e_6_c':sum(v<=1e-6 for v in dist),'rows_within_0_01_c':sum(v<=.01+1e-12 for v in dist),
                            'site_dates_within_1e_6_c':sum(min(v)<=1e-6 for v in p_events.values()),
                            'site_dates_within_0_01_c':sum(min(v)<=.01+1e-12 for v in p_events.values()),
                            'median_nearest_difference_c':statistics.median(dist) if dist else None,
                            'maximum_nearest_difference_c':max(dist) if dist else None}
                for k,v in quantities.items():same(v,prow[k],k)
                prox_checked+=1
    if range_checked!=len(range_table) or prox_checked!=len(prox):raise ValueError('Unchecked aggregate rows remain')
    groups=Counter((x['site'],x['day']) for x in cases)
    status=json.loads((OUT/'status.json').read_text())
    multiplicity=Counter(groups.values())
    observed={str(k):v for k,v in sorted(multiplicity.items())}
    distinct=defaultdict(set)
    metadata_distinct=defaultdict(set)
    for x in cases:
        if x['value'] is not None:distinct[x['site'],x['day']].add(x['value'])
    for x in fields:metadata_distinct[x['site'],x['day']].add(x['metadata'])
    if observed!=status['site_date_multiplicity'] or sum(len(v)>1 for v in distinct.values())!=status['site_dates_with_multiple_distinct_numeric_values']:
        raise ValueError('Field duplicate or distinct-value counts differ')
    if any(len(v)!=1 for v in metadata_distinct.values()):raise ValueError('Same-day field metadata differ')
    report={'status':'passed','field_rows_rechecked':len(cases),'field_site_dates':len(groups),
            'reported_day_range_rows_rechecked':range_checked,'hour_proximity_rows_rechecked':prox_checked,
            'portal_complete_reported_days':len(days),'all_nonvalue_metadata_equal_within_each_site_date':True,
            'scope':'Separate Python CSV/datetime implementation recounts range and proximity summaries from the same field and portal files. It does not resolve absent field times, preliminary flags, sensor identity, timestamp zone, physical measurement quality or independent climate.'}
    (OUT/'independent_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Check open-portal counterparts of the fixed Nova Scotia candidate roster.

The workbooks have already been inspected for completeness; this is neither
blind nor an independent validation. First request only station-level counts.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import gzip
import importlib.util
import json
import math
import numbers
from pathlib import Path
import tempfile
import time
import pandas as pd
import requests
import numpy as np
import openpyxl

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified'
DATA=ROOT/'data/external/wrr_nova_scotia_open_20261026'
WORKBOOKS=ROOT/'private/wrr_nova_scotia_verified_20261026'
URL='https://data.novascotia.ca/resource/bkfi-mjgw.json'

def freeze():
    if not (OUT/'reported_label_status.json').is_file():raise RuntimeError('Complete the workbook label screen first')
    roster=pd.read_csv(OUT/'candidate_roster.csv',dtype=str)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'stations':roster.station_id.tolist(),
       'years':list(range(2009,2018)),'first_step':'request only site-level counts and date ranges, not temperatures',
       'possible_next_step':'if official portal has records, compare all four already-fixed sites and 2009-2017 values to their provincial verified workbooks; never select on prediction errors',
       'license':'open data portal dataset is described under Open Government Licence – Nova Scotia; do not infer that the separate legacy workbook has identical terms',
       'prior_access':'same sites and time period already examined for workbook numeric completeness; unregistered nonblind provenance comparison, not independent source validation',
       'limitation':'public portal lists no per-record temperature quality flags and timestamp zone remains to be confirmed'}
    path=OUT/'portal_comparison_plan.json'
    if path.exists():
        old=json.loads(path.read_text())
        if old['stations']!=plan['stations'] or old['years']!=plan['years']:raise RuntimeError('frozen portal plan changed')
    else:path.write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(plan,indent=2))

def count():
    if not (OUT/'portal_comparison_plan.json').exists():raise RuntimeError('freeze portal plan first')
    plan=json.loads((OUT/'portal_comparison_plan.json').read_text())
    quoted=','.join("'"+s.replace("'","''")+"'" for s in plan['stations'])
    params={'$select':'station_number,count(*) as row_count,min(date) as first_date,max(date) as last_date',
      '$where':f"station_number in ({quoted}) AND date >= '2009-01-01T00:00:00' AND date < '2018-01-01T00:00:00'",
      '$group':'station_number','$order':'station_number','$limit':100}
    response=requests.get(URL,params=params,timeout=45,headers={'User-Agent':'stream-temperature reference research'})
    response.raise_for_status();data=response.json()
    f=pd.DataFrame(data,columns=['station_number','row_count','first_date','last_date'])
    if f.station_number.duplicated().any() or not set(f.station_number).issubset(plan['stations']):raise ValueError('unexpected station groups')
    f.to_csv(OUT/'portal_station_counts.csv',index=False)
    state={'status':'portal_counts_received','fixed_candidates':len(plan['stations']),'stations_returned':len(f),
           'candidate_ids_not_returned':sorted(set(plan['stations'])-set(f.station_number)),
           'temperature_values_requested':False,'prediction_errors_computed_in_this_count_screen':False,
           'separate_exploratory_score_exists':(ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory/score_status.json').exists(),
           'limitation':plan['limitation'],'request_url':response.url}
    (OUT/'portal_count_status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(f.to_string(index=False));print(json.dumps(state,indent=2))

def freeze_value_comparison():
    if not (OUT/'portal_count_status.json').exists():raise RuntimeError('Complete the portal count preflight first')
    plan=json.loads((OUT/'portal_comparison_plan.json').read_text())
    state=json.loads((OUT/'portal_count_status.json').read_text())
    if state['stations_returned']!=len(plan['stations']):raise RuntimeError('not all frozen sites returned')
    spec={'created_utc':datetime.now(timezone.utc).isoformat(),'stations':plan['stations'],'years':plan['years'],
          'comparison':'all records from each of the four frozen sites in 2009–2017, irrespective of prior completeness result; no prediction outcomes used',
          'columns':'portal station ID, reported date, reported time, temperature and unique system record ID; match to workbook by station and reported timestamp',
          'temperature_difference_tolerance_c':1e-6,'matching':'do not silently combine duplicate timestamps; report unmatched, missing, duplicated and mismatched values separately',
          'purpose':'determine whether openly licensed portal data numerically reproduce the separately obtained provider-verified workbooks, not independent validation of either source',
          'prior_access':'workbook time-label completeness and numeric-value presence previously examined; the workbook and portal may be different releases of the same programme',
          'limits':'timezone and per-observation quality remain unresolved regardless of an exact match; sources and fixed sites cannot be treated as independent climates'}
    path=OUT/'portal_value_comparison_plan.json'
    if path.exists():
        previous=json.loads(path.read_text())
        if previous['stations']!=spec['stations'] or previous['years']!=spec['years']:raise RuntimeError('frozen value-comparison plan changed')
    else:path.write_text(json.dumps(spec,indent=2)+'\n')
    print(json.dumps(spec,indent=2))

def key_probe():
    if not (OUT/'portal_value_comparison_plan.json').exists():raise RuntimeError('Freeze the value comparison first')
    plan=json.loads((OUT/'portal_value_comparison_plan.json').read_text());site=plan['stations'][0]
    params={'$select':'station_number,date,time,:id','$where':f"station_number = '{site}' AND date >= '2009-01-01T00:00:00' AND date < '2018-01-01T00:00:00'",
            '$order':'date,time,:id','$limit':1}
    response=requests.get(URL,params=params,timeout=45,headers={'User-Agent':'stream-temperature reference research'})
    response.raise_for_status();data=response.json()
    if len(data)!=1 or data[0].get('station_number')!=site:raise ValueError('portal key probe has unexpected shape')
    # The source time label, not the water temperature, is recorded for parser design.
    x=data[0];record={'status':'key_probe_passed','station_id':site,'field_names':sorted(x),
        'date_label_example':x.get('date'),'time_label_example':x.get('time'),'system_record_id_present':':id' in x,
        'temperature_values_requested':False,'limitation':'timestamp examples do not establish a timezone or source quality'}
    (OUT/'portal_key_probe.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))

def acquire():
    if not (OUT/'portal_value_comparison_plan.json').exists() or not (OUT/'portal_key_probe.json').exists():
        raise RuntimeError('Freeze and probe the portal value comparison first')
    plan=json.loads((OUT/'portal_value_comparison_plan.json').read_text())
    counts=pd.read_csv(OUT/'portal_station_counts.csv',dtype={'station_number':str}).set_index('station_number')
    DATA.mkdir(parents=True,exist_ok=True)
    checkpoint=OUT/'portal_acquisition_in_progress.json';final=OUT/'portal_acquisition.json'
    old=json.loads(final.read_text()) if final.exists() else (json.loads(checkpoint.read_text()) if checkpoint.exists() else {})
    known={(x['station_id'],x['offset']):x for x in old.get('pages',[])}
    pages=[];site_totals={};limit=50000
    for site in plan['stations']:
        seen=set();total=0;offset=0
        while True:
            path=DATA/f'{site}_{offset:06d}.json.gz'
            if path.exists():
                if (site,offset) not in known:raise RuntimeError('existing portal page lacks a recorded receipt')
                raw=gzip.decompress(path.read_bytes());
            else:
                params={'$select':'station_number,date,time,temperature_c,:id',
                  '$where':f"station_number = '{site}' AND date >= '2009-01-01T00:00:00' AND date < '2018-01-01T00:00:00'",
                  '$order':'date,time,:id','$limit':limit,'$offset':offset}
                response=None
                for attempt in range(3):
                    try:
                        response=requests.get(URL,params=params,timeout=60,headers={'User-Agent':'stream-temperature reference research'})
                    except requests.RequestException:
                        if attempt==2:raise
                        print('Portal connection interrupted; retrying the same page',flush=True);time.sleep(3*(attempt+1));continue
                    if response.status_code not in (429,502,503,504):break
                    try:delay=min(30,max(1,int(response.headers.get('Retry-After','5'))))
                    except ValueError:delay=5
                    if attempt<2:
                        print('Portal temporarily unavailable; waiting',delay,'seconds',flush=True);time.sleep(delay)
                response.raise_for_status();raw=response.content;
                # Validate before retaining, and publish each page atomically.
                parsed=json.loads(raw)
                if not isinstance(parsed,list):raise ValueError('portal page is not a JSON array')
                with tempfile.NamedTemporaryFile(dir=DATA,prefix='page_',suffix='.partial',delete=False) as f:
                    temporary=Path(f.name)
                    with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as z:z.write(raw)
                temporary.replace(path)
            data=json.loads(raw)
            if not isinstance(data,list) or any(x.get('station_number')!=site or ':id' not in x for x in data):raise ValueError('portal page contains unexpected station or record identifiers')
            ids=[x[':id'] for x in data]
            if len(set(ids))!=len(ids) or seen.intersection(ids):raise ValueError('duplicate portal record identifier across pages')
            seen.update(ids);total+=len(data)
            pages.append({'station_id':site,'offset':offset,'rows':len(data),'file':str(path.relative_to(ROOT)),
                          'uncompressed_bytes':len(raw)})
            checkpoint.write_text(json.dumps({'status':'in_progress','pages':pages},indent=2)+'\n')
            print('Acquired portal page',site,offset,'rows',len(data),flush=True)
            if len(data)<limit:break
            offset+=limit
        if total!=int(counts.loc[site,'row_count']):raise ValueError('portal row total differs from earlier count preflight')
        site_totals[site]=total
    state={'status':'portal_pages_acquired','pages':pages,'site_totals':site_totals,
           'source':'Government of Nova Scotia Open Data Portal, bkfi-mjgw; Open Government Licence – Nova Scotia',
           'scope':'frozen sites and 2009-2017; data contain temperatures, but no model scoring has been performed',
           'limitation':'concurrent provider revisions cannot be ruled out by a stable row count; per-observation quality and timezone remain unresolved'}
    final.write_text(json.dumps(state,indent=2)+'\n');print(json.dumps({'status':state['status'],'site_totals':site_totals},indent=2))

def workbook_records(path):
    """Read only reported timestamp and temperature cells from a local workbook."""
    book=openpyxl.load_workbook(path,read_only=True,data_only=True)
    if len(book.worksheets)!=1:raise ValueError('unexpected workbook sheet count')
    records=[];unparsed=0
    for row in book.worksheets[0].iter_rows(values_only=True):
        label,value=row[0],row[1] if len(row)>1 else None
        numeric=isinstance(value,numbers.Real) and not isinstance(value,bool) and math.isfinite(float(value))
        if isinstance(label,datetime):timestamp=label
        elif isinstance(label,str):
            timestamp=pd.to_datetime(label,errors='coerce',format='mixed')
            if pd.isna(timestamp):
                if numeric:unparsed+=1
                continue
        else:
            if numeric:unparsed+=1
            continue
        if getattr(timestamp,'tzinfo',None) is not None:raise ValueError('timezone-aware workbook label requires review')
        if 2009<=timestamp.year<=2017:records.append((timestamp,float(value) if numeric else np.nan))
    book.close()
    return pd.DataFrame(records,columns=['timestamp','value']),unparsed

def portal_records(site,pages):
    rows=[]
    for item in pages:
        if item['station_id']!=site:continue
        raw=gzip.decompress((ROOT/item['file']).read_bytes())
        rows.extend(json.loads(raw))
    if not rows:return pd.DataFrame(columns=['timestamp','value']),0
    f=pd.DataFrame(rows)
    if not f.station_number.eq(site).all() or f[':id'].duplicated().any():raise ValueError('portal site or row identity mismatch')
    dates=f.get('date',pd.Series('',index=f.index)).fillna('').astype(str).str.slice(0,10)
    times=f.get('time',pd.Series('',index=f.index)).fillna('').astype(str)
    timestamps=pd.to_datetime(dates+' '+times,errors='coerce',format='mixed')
    if getattr(timestamps.dt,'tz',None) is not None:raise ValueError('timezone-aware portal label requires review')
    vals=pd.to_numeric(f.get('temperature_c',pd.Series(np.nan,index=f.index)),errors='coerce')
    return pd.DataFrame({'timestamp':timestamps,'value':vals}),int(timestamps.isna().sum())

def compare_series(workbook,portal,tolerance=1e-6):
    """Compare unique clock labels, keeping duplicate and missing cases visible."""
    w=workbook.dropna(subset=['timestamp']).copy();p=portal.dropna(subset=['timestamp']).copy()
    wd=w.timestamp.duplicated(keep=False);pd_=p.timestamp.duplicated(keep=False)
    wu=w.loc[~wd];pu=p.loc[~pd_]
    merged=wu.merge(pu,on='timestamp',how='outer',suffixes=('_workbook','_portal'),indicator=True,validate='one_to_one')
    both=merged.loc[merged._merge.eq('both')]
    a=both.value_workbook.to_numpy(float);b=both.value_portal.to_numpy(float)
    af=np.isfinite(a);bf=np.isfinite(b);both_numeric=af&bf
    diff=np.abs(a[both_numeric]-b[both_numeric]);equal=diff<=tolerance
    return {'workbook_rows':len(workbook),'portal_rows':len(portal),
        'workbook_duplicate_label_rows':int(wd.sum()),'portal_duplicate_label_rows':int(pd_.sum()),
        'workbook_unparsed_labels':int(workbook.timestamp.isna().sum()),'portal_unparsed_labels':int(portal.timestamp.isna().sum()),
        'shared_unique_labels':len(both),'workbook_only_unique_labels':int(merged._merge.eq('left_only').sum()),
        'portal_only_unique_labels':int(merged._merge.eq('right_only').sum()),
        'both_numeric':int(both_numeric.sum()),'numeric_equal':int(equal.sum()),'numeric_different':int((~equal).sum()),
        'both_nonnumeric_or_missing':int((~af&~bf).sum()),'one_numeric_other_missing':int((af^bf).sum()),
        'max_numeric_abs_difference_c':float(diff.max()) if len(diff) else None}

def portal_completeness():
    """Recompute public portal label completeness without private workbooks."""
    if not (OUT/'portal_acquisition.json').exists():raise RuntimeError('Acquire frozen portal pages first')
    portal=json.loads((OUT/'portal_acquisition.json').read_text());plan=json.loads((OUT/'portal_value_comparison_plan.json').read_text())
    spec=importlib.util.spec_from_file_location('verified_label_counter',ROOT/'scripts/589_nova_scotia_verified_intake.py')
    counter=importlib.util.module_from_spec(spec);spec.loader.exec_module(counter)
    rows=[];unparsed={}
    for site in plan['stations']:
        frame,n=portal_records(site,portal['pages']);unparsed[site]=n
        labels=pd.DataFrame({'timestamp':frame.timestamp,'numeric_temperature':np.isfinite(frame.value.to_numpy(float))})
        for year in plan['years']:
            row=counter.label_completeness(labels,year);row['station_id']=site;rows.append(row)
    result=pd.DataFrame(rows);result.to_csv(OUT/'portal_label_completeness.csv',index=False)
    site_summary=result.groupby('station_id').agg(possible_complete_label_years=('complete_label_year','sum'),years_checked=('year','size')).reset_index()
    site_summary['at_least_four_possible_years']=site_summary.possible_complete_label_years.ge(4)
    site_summary.to_csv(OUT/'portal_label_site_summary.csv',index=False)
    state={'status':'portal_label_completeness_computed','stations':len(site_summary),'station_years':len(result),
        'complete_reported_label_years':int(result.complete_label_year.sum()),
        'stations_with_four_complete_label_years':int(site_summary.at_least_four_possible_years.sum()),
        'unparsed_timestamp_rows':unparsed,'strict_reference_qualified_stations':0,'strict_reference_status':'not established',
        'prediction_errors_computed_in_this_label_screen':False,
        'separate_exploratory_score_exists':(ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory/score_status.json').exists(),
        'limitation':'reported labels and numeric cells only; timezone, estimated-value treatment, per-observation QA and climate independence are not established'}
    (OUT/'portal_label_status.json').write_text(json.dumps(state,indent=2)+'\n');print(site_summary.to_string(index=False));print(json.dumps(state,indent=2))

def compare(workbook_dir=WORKBOOKS):
    if not (OUT/'portal_acquisition.json').exists():raise RuntimeError('Acquire frozen portal pages first')
    portal=json.loads((OUT/'portal_acquisition.json').read_text());workbooks=json.loads((OUT/'acquisition.json').read_text())
    plan=json.loads((OUT/'portal_value_comparison_plan.json').read_text());module_path=ROOT/'scripts/589_nova_scotia_verified_intake.py'
    spec=importlib.util.spec_from_file_location('verified_label_counter',module_path);counter=importlib.util.module_from_spec(spec);spec.loader.exec_module(counter)
    summary=[];portal_years=[]
    for item in workbooks['files']:
        site=item['station_id'];path=workbook_dir/item['workbook']
        w,unparsed=workbook_records(path);p,p_unparsed=portal_records(site,portal['pages'])
        if unparsed or p_unparsed:print('Timestamp parse issues for',site,unparsed,p_unparsed,flush=True)
        row=compare_series(w,p,plan['temperature_difference_tolerance_c']);row.update(station_id=site,workbook_numeric_with_unparsed_timestamp=unparsed)
        summary.append(row)
        labels=pd.DataFrame({'timestamp':p.timestamp,'numeric_temperature':np.isfinite(p.value.to_numpy(float))})
        for year in plan['years']:
            s=counter.label_completeness(labels,year);s['station_id']=site;portal_years.append(s)
        print('Compared provider sources for',site,flush=True)
    result=pd.DataFrame(summary);year_table=pd.DataFrame(portal_years)
    prior=OUT/'portal_label_completeness.csv'
    if prior.exists():
        expected=pd.read_csv(prior).sort_values(['station_id','year']).reset_index(drop=True)
        actual=year_table.sort_values(['station_id','year']).reset_index(drop=True)
        try:pd.testing.assert_frame_equal(expected,actual,check_dtype=False)
        except AssertionError as exc:raise ValueError('portal label totals disagree with standalone calculation') from exc
    else:year_table.to_csv(prior,index=False)
    result.to_csv(OUT/'portal_workbook_comparison.csv',index=False)
    state={'status':'comparison_computed','stations':len(result),'shared_unique_labels':int(result.shared_unique_labels.sum()),
        'both_numeric':int(result.both_numeric.sum()),'numeric_equal':int(result.numeric_equal.sum()),
        'numeric_different':int(result.numeric_different.sum()),'one_numeric_other_missing':int(result.one_numeric_other_missing.sum()),
        'portal_complete_reported_label_years':int(year_table.complete_label_year.sum()),
        'temperature_difference_tolerance_c':plan['temperature_difference_tolerance_c'],
        'scope':'two releases of the same provincial monitoring programme; comparison of reported clock labels, not independent sensors',
        'limitation':'timestamps lack a fully verified common timezone; per-observation quality and estimated-value status are not established; shared data values are not evidence of independent accuracy'}
    (OUT/'portal_workbook_status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(result.to_string(index=False));print(json.dumps(state,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['freeze','count','freeze_values','key_probe','acquire','portal_completeness','compare'])
    p.add_argument('--workbooks',type=Path,default=WORKBOOKS,help='local restricted workbook directory, used only for compare')
    a=p.parse_args()
    if a.phase=='compare':compare(a.workbooks)
    else:{'freeze':freeze,'count':count,'freeze_values':freeze_value_comparison,'key_probe':key_probe,'acquire':acquire,'portal_completeness':portal_completeness}[a.phase]()

if __name__=='__main__':main()

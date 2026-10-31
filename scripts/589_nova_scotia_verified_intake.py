#!/usr/bin/env python3
"""Freeze and inspect Nova Scotia's provider-labelled verified river workbooks.

The public landing page names historical workbooks as verified. That label is
not assumed to identify per-hour quality, nonestimated values or time zone.
Candidates are fixed from metadata before any workbook is opened.
"""
from __future__ import annotations
import argparse
from datetime import date,datetime,timezone
import json
from pathlib import Path
import re
import math
import numbers
import tempfile
import zipfile
import openpyxl
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified'
DATA=ROOT/'private/wrr_nova_scotia_verified_20261026'
BASE='https://novascotia.ca/nse/surface.water/docs/'
SITES=[
 ('NS01DL0009','Kelley River','Kelley-River-Verified-2009-2017.xlsx',2009),
 ('NS01EF0002','LaHave River','LaHave-River-Verified-2008-2017.xlsx',2008),
 ('NS01FB0001','North East Margaree River','North-East-Margaree-River--Verified_2008-2017.xlsx',2008),
 ('NS01ED9111','Shelburne River','Shelburne-River-Verified-2008-2017.xlsx',2008),
]

def freeze():
    OUT.mkdir(parents=True,exist_ok=True)
    candidates=pd.DataFrame([{'station_id':sid,'station_name':name,'workbook':f,'metadata_first_year':start,
         'metadata_last_year':2017,'url':BASE+f} for sid,name,f,start in SITES])
    path=OUT/'candidate_roster.csv'
    if path.exists():
        old=pd.read_csv(path,dtype=str)
        if old.station_id.tolist()!=candidates.station_id.tolist():raise RuntimeError('frozen site roster changed')
    else:candidates.to_csv(path,index=False)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'candidate_count':len(candidates),
       'selection':'all four named river sites with provider-labelled verified historical workbooks on the provincial monitoring page; exclude Pockwock Lake; no target temperature or outcome used',
       'candidate_ids':candidates.station_id.tolist(),'reference_years':list(range(2009,2018)),
       'reference_target':'at least four complete calendar years, each with 24 distinct valid nonestimated hourly records per day, and at least three other complete years for local history',
       'quality_rule':'provider labels the historical files verified, but per-observation verification, estimated-value handling and time zone must be established before treating any year as strict reference',
       'prior_contact':'no exact candidate IDs found in named prior ECCC aggregate inventory or text paths; previous metadata and cross-agency geographic overlap remain best-effort only',
       'independence':'four sites in one province are not four independent climatic replicates; station-to-station catchment links must be checked',
       'rights':'the Open Data Portal dataset identifies the Nova Scotia open government licence; separate legacy workbook reuse terms have not been established; keep downloaded workbooks local',
       'data_before_freeze':'landing page and dataset metadata consulted; no candidate workbook contents or prediction errors inspected'}
    p=OUT/'plan.json'
    if p.exists():
        old=json.loads(p.read_text())
        if old['candidate_ids']!=plan['candidate_ids']:raise RuntimeError('existing plan changed')
    else:p.write_text(json.dumps(plan,indent=2)+'\n')
    print(candidates.to_string(index=False));print(json.dumps(plan,indent=2))

def acquire():
    if not (OUT/'plan.json').is_file():raise RuntimeError('freeze metadata roster first')
    roster=pd.read_csv(OUT/'candidate_roster.csv',dtype=str);DATA.mkdir(parents=True,exist_ok=True,mode=0o700);DATA.chmod(0o700)
    existing=OUT/'acquisition.json';checkpoint=OUT/'acquisition_in_progress.json'
    prior=json.loads(existing.read_text()) if existing.exists() else (json.loads(checkpoint.read_text()) if checkpoint.exists() else {})
    known={x['workbook']:x for x in prior.get('files',[])};receipts=[]
    for row in roster.itertuples(index=False):
        path=DATA/row.workbook
        if path.exists() and row.workbook not in known:raise RuntimeError('existing workbook lacks receipt; preserve it for inspection')
        if not path.exists():
            with tempfile.NamedTemporaryFile(dir=DATA,prefix='download_',suffix='.partial',delete=False) as f:
                temp=Path(f.name)
                try:
                    with requests.get(row.url,stream=True,timeout=(15,90),headers={'User-Agent':'stream-temperature reference research'}) as r:
                        r.raise_for_status()
                        for block in r.iter_content(1024*1024):
                            if block:f.write(block)
                    f.flush()
                    if not zipfile.is_zipfile(temp):raise ValueError('response is not an XLSX workbook')
                except Exception:temp.unlink(missing_ok=True);raise
            temp.chmod(0o600);temp.replace(path)
        if row.workbook in known:raise RuntimeError('source workbook changed; preserve existing version')
        receipts.append({'station_id':row.station_id,'workbook':row.workbook,'bytes':path.stat().st_size})
        checkpoint.write_text(json.dumps({'status':'in_progress','files':receipts},indent=2)+'\n')
        print('Acquired',row.station_id,'bytes',path.stat().st_size,flush=True)
    state={'status':'acquired','files':receipts,'scope':'provider-labelled verified legacy workbooks; station selection fixed before acquisition',
           'redistribution':'legacy workbook licence unresolved; files retained only in private directory',
           'prior_contact':'candidate workbook temperature values have now been acquired; validation remains unregistered and exploratory'}
    existing.write_text(json.dumps(state,indent=2)+'\n');print(json.dumps(state,indent=2))

def inspect_headers():
    if not (OUT/'acquisition.json').is_file():raise RuntimeError('acquire the frozen workbooks first')
    receipt=json.loads((OUT/'acquisition.json').read_text());rows=[]
    for item in receipt['files']:
        path=DATA/item['workbook']
        book=openpyxl.load_workbook(path,read_only=True,data_only=True)
        sheets=[]
        for sheet in book.worksheets:
            # Header and provider notes only: report strings, omit every numeric,
            # date, formula and measurement cell. Limit to the first 12 rows.
            text=[]
            for row in sheet.iter_rows(min_row=1,max_row=min(sheet.max_row or 12,12),values_only=True):
                # Do not traverse observation rows when dates or numeric cells begin.
                if any(isinstance(value,(datetime,date,int,float)) and not isinstance(value,bool) for value in row if value is not None):break
                for value in row:
                    if isinstance(value,str) and len(value)<=160 and not re.search(r'^\s*[-+]?\d',value):
                        value=value.strip()
                        if value and value not in text:text.append(value)
            sheets.append({'name':sheet.title,'max_rows':sheet.max_row,'max_columns':sheet.max_column,'first_rows_text':text[:60]})
        book.close();rows.append({'station_id':item['station_id'],'workbook':item['workbook'],'sheets':sheets})
    result={'status':'headers_inspected','workbooks':rows,'scope':'sheet names and text in first 12 rows; all numeric and date cells omitted; does not qualify daily observations or prove quality flags',
        'source_rights':'legacy workbooks retained locally pending specific reuse terms'}
    (OUT/'workbook_schema.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))

def freeze_completeness():
    if not (OUT/'workbook_schema.json').is_file():raise RuntimeError('Inspect workbook headers before defining completeness accounting')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'station_ids':[x[0] for x in SITES],
        'years':list(range(2009,2018)),
        'method':'count 24 distinct on-the-hour reported timestamp labels with finite numeric temperature cells for every calendar day; any duplicate, absent, nonnumeric or off-hour record makes a day incomplete',
        'scope':'reported wall-clock labels only, with no assumed timezone conversion and no numerical-temperature threshold; input temperature values are not stored in derived artifacts',
        'interpretation':'an upper bound on completeness only: numeric cells do not establish nonestimated data, unique physical hourly coverage, sensor accuracy or point-level QA',
        'prior_access':'provider landing page, site names, workbook headers and initial cell types examined; workbook temperature values acquired locally but no prediction outcomes inspected',
        'time_zone':'LaHave header states UTC-04:00; other workbook headers did not identify an offset. This plan does not assume either fixed offset or daylight-saving behavior',
        'model_scoring':'none; any complete-looking year remains strictly unqualified until time and point-level quality semantics are verified'}
    path=OUT/'completeness_plan.json'
    if path.exists():
        old=json.loads(path.read_text())
        if old['station_ids']!=plan['station_ids'] or old['years']!=plan['years']:raise RuntimeError('frozen completeness plan changed')
    else:path.write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(plan,indent=2))

def label_completeness(records,year):
    """Count exact reported hour labels; does not assess physical time or quality."""
    times=pd.to_datetime(records['timestamp'],errors='coerce',format='mixed')
    if getattr(times.dt,'tz',None) is not None:raise ValueError('timestamp labels have unexpected timezone information')
    chosen=records.loc[times.dt.year.eq(year)].copy();chosen['timestamp']=times.loc[chosen.index]
    expected=pd.date_range(f'{year}-01-01',f'{year+1}-01-01',freq='D',inclusive='left')
    if chosen.empty:
        return dict(year=year,days=len(expected),source_rows=0,complete_label_days=0,incomplete_label_days=len(expected),
            duplicate_rows=0,off_hour_rows=0,nonnumeric_temperature_rows=0,complete_label_year=False)
    t=chosen.timestamp;on_hour=t.dt.minute.eq(0)&t.dt.second.eq(0)&t.dt.microsecond.eq(0)&t.dt.nanosecond.eq(0)
    chosen['_day']=t.dt.floor('D');chosen['_on_hour']=on_hour.to_numpy()
    by_day=chosen.groupby('_day').agg(rows=('timestamp','size'),unique=('timestamp','nunique'),
        on_hour=('_on_hour','sum'),numeric=('numeric_temperature','sum')).reindex(expected)
    complete=by_day[['rows','unique','on_hour','numeric']].eq(24).all(axis=1)
    return dict(year=year,days=len(expected),source_rows=len(chosen),complete_label_days=int(complete.sum()),
        incomplete_label_days=int((~complete).sum()),duplicate_rows=int(t.duplicated(keep=False).sum()),
        off_hour_rows=int((~on_hour).sum()),nonnumeric_temperature_rows=int((~chosen.numeric_temperature).sum()),
        complete_label_year=bool(complete.all()))

def completeness():
    if not (OUT/'completeness_plan.json').is_file():raise RuntimeError('Freeze the label completeness plan first')
    plan=json.loads((OUT/'completeness_plan.json').read_text());receipt=json.loads((OUT/'acquisition.json').read_text())
    all_rows=[];parse_counts=[]
    for item in receipt['files']:
        path=DATA/item['workbook']
        book=openpyxl.load_workbook(path,read_only=True,data_only=True)
        if len(book.worksheets)!=1:raise ValueError('unexpected workbook sheet count')
        sheet=book.worksheets[0];records=[];unparsed_with_value=0;types={}
        for row in sheet.iter_rows(values_only=True):
            timestamp,value=row[0],row[1] if len(row)>1 else None
            # Rows before the first data timestamp are provider labels/units.
            if isinstance(timestamp,datetime):parsed=timestamp
            elif isinstance(timestamp,str):
                parsed=pd.to_datetime(timestamp,errors='coerce',format='mixed')
                if pd.isna(parsed):
                    if isinstance(value,numbers.Real) and not isinstance(value,bool) and math.isfinite(float(value)):
                        unparsed_with_value+=1
                    continue
            else:
                if isinstance(value,numbers.Real) and not isinstance(value,bool) and math.isfinite(float(value)):
                    unparsed_with_value+=1
                continue
            if getattr(parsed,'tzinfo',None) is not None:raise ValueError('timezone-aware record requires source-specific review')
            kind=type(value).__name__;types[kind]=types.get(kind,0)+1
            numeric=isinstance(value,numbers.Real) and not isinstance(value,bool) and math.isfinite(float(value))
            records.append((parsed,bool(numeric)))
        book.close()
        frame=pd.DataFrame(records,columns=['timestamp','numeric_temperature'])
        for year in plan['years']:
            result=label_completeness(frame,year);result['station_id']=item['station_id'];all_rows.append(result)
        parse_counts.append({'station_id':item['station_id'],'parseable_timestamp_rows':len(frame),
                             'numeric_values_with_unparseable_timestamp':unparsed_with_value,'temperature_cell_types':types})
        print('Counted reported timestamp labels for',item['station_id'],flush=True)
    result=pd.DataFrame(all_rows);result=result[['station_id']+[x for x in result.columns if x!='station_id']]
    result.to_csv(OUT/'reported_label_completeness.csv',index=False)
    station=result.groupby('station_id').agg(possible_complete_label_years=('complete_label_year','sum'),years_checked=('year','size')).reset_index()
    station['at_least_four_possible_years']=station.possible_complete_label_years.ge(4)
    station.to_csv(OUT/'reported_label_site_summary.csv',index=False)
    state={'status':'label_completeness_computed','stations':len(station),'station_years':len(result),
        'complete_reported_label_years':int(result.complete_label_year.sum()),
        'stations_with_four_complete_label_years':int(station.at_least_four_possible_years.sum()),
        'strict_quality_qualified_stations':0,'strict_quality_status':'not established',
        'prediction_errors_computed_in_this_label_screen':False,
        'separate_exploratory_score_exists':(ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory/score_status.json').exists(),
        'temperature_values_retained_in_summaries':False,
        'parse_counts':parse_counts,'limitation':plan['interpretation']+'; '+plan['time_zone']}
    (OUT/'reported_label_status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(result.to_string(index=False));print(json.dumps(state,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['freeze','acquire','headers','freeze_completeness','completeness']);a=p.parse_args()
    {'freeze':freeze,'acquire':acquire,'headers':inspect_headers,'freeze_completeness':freeze_completeness,'completeness':completeness}[a.phase]()

if __name__=='__main__':main()

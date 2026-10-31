#!/usr/bin/env python3
"""Freeze then qualify the 2019--2024 Nechako 15-minute author archive.

The source locations were published before this analysis. Selection uses only
published site type and period metadata. The target shares a river and climate
with an earlier BC exploratory case: it is not a new independent climate.
"""
from __future__ import annotations
import argparse
import calendar
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nechako_nhg'
DATA=ROOT/'data/external/wrr_nechako_nhg_20261026'
ARTICLE='https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12205680/fullTextXML'
RECORD='https://zenodo.org/api/records/15053907'
ALLOWED={'P','A'}
YEARS=[2020,2021,2022,2023]

def get(url,timeout=60):
    r=requests.get(url,timeout=timeout,headers={'User-Agent':'stream-temperature reference research'});r.raise_for_status();return r

def parse_roster(content):
    root=ET.fromstring(content);tables=[]
    for table in root.findall('.//table-wrap'):
        caption=table.find('caption')
        if caption is not None and 'Historical and currently active water temperature sites' in ' '.join(caption.itertext()):tables.append(table)
    if len(tables)!=1:raise ValueError('published site table missing or not unique')
    rows=[]
    for tr in tables[0].findall('.//tr'):
        values=[' '.join(' '.join(x.itertext()).split()) for x in list(tr)]
        if not values or not values[0].isdigit():continue
        if len(values)!=7:raise ValueError('unexpected site table columns')
        n,name,site,lat,lon,elev,period=values
        start,end=period.split(' - ')
        start=pd.to_datetime(start,format='%m/%d/%Y');end=pd.to_datetime(end,format='%m/%d/%Y')
        def coord(text):return float(re.sub('[^0-9.+-]','',text)) * (-1 if text.endswith(('W','S')) else 1)
        waterbody='lake_or_spillway' if name.startswith(('Cheslatta Lake','Nadina Lake','Ness Lake','Skins Lake Spillway')) else 'river_or_creek'
        full=[year for year in YEARS if start.date()<pd.Timestamp(year,1,1).date() and end.date()>pd.Timestamp(year,12,31).date()]
        rows.append(dict(site_code=site,station_name=name.rstrip(' *'),latitude=coord(lat),longitude=coord(lon),elevation_m=int(elev),
            metadata_start=str(start.date()),metadata_end=str(end.date()),waterbody_name_class=waterbody,
            metadata_possible_full_years=';'.join(map(str,full)),n_metadata_possible_full_years=len(full),
            candidate=waterbody=='river_or_creek' and len(full)>=4))
    f=pd.DataFrame(rows)
    if len(f)!=32 or f.site_code.duplicated().any():raise ValueError('published roster incomplete or duplicate')
    return f

def freeze():
    OUT.mkdir(parents=True,exist_ok=True)
    roster=parse_roster(get(ARTICLE).content)
    rec=get(RECORD).json();meta=rec['metadata'];items=[x for x in rec['files'] if x['key']=='01_Data.zip']
    if meta.get('license',{}).get('id')!='cc-by-4.0' or len(items)!=1:raise ValueError('source license or archive metadata changed')
    selected=roster.loc[roster.candidate].copy()
    if selected.site_code.tolist()!=['01FW013']:raise ValueError('published metadata selection differs; preserve existing plan')
    old=OUT/'metadata_roster.csv';candidate=OUT/'candidate_roster.csv';plan=OUT/'plan.json'
    if old.exists():
        previous=pd.read_csv(candidate,dtype={'site_code':str})
        if previous.site_code.tolist()!=selected.site_code.tolist():raise RuntimeError('existing frozen roster changed')
    else:roster.to_csv(old,index=False);selected.to_csv(candidate,index=False)
    item=items[0]
    design={'created_utc':datetime.now(timezone.utc).isoformat(),'dataset_doi':'10.5281/zenodo.15053907',
        'license':'CC BY 4.0','published_site_count':len(roster),'candidate_count':len(selected),
        'selection':'all named river or creek sites whose published date range strictly extends beyond both boundaries of 2020, 2021, 2022 and 2023; exclude named lakes and reservoir spillway',
        'candidate_sites':selected.site_code.tolist(),'years_utc':YEARS,
        'reference_rule':'each UTC calendar day has exactly 96 distinct quarter-hour timestamps with finite values and author QC flag P or A; any missing, duplicate, off-grid or other flagged value fails the day',
        'quality_flag_basis':'authors identify P as pass, A as average of valid simultaneous loggers and C when an averaged input has a warning; all other flags excluded',
        'independence':'same Nechako River and Fraser basin as previously scored BC site 08JA017; targeted exploratory comparison, not an independent climate or blinded confirmation',
        'contact':'published metadata inspected before freeze; no source temperature values or prediction errors inspected before freeze; repository text search found no matching new site identifier/name in named paths, but absence does not prove no prior contact',
        'archive_url':item['links']['self'],'archive_bytes':item['size'],'limitations':'single selected candidate, no population incidence, no natural-outage reference; sensor accuracy and catchment dependence remain'}
    if not plan.exists():plan.write_text(json.dumps(design,indent=2)+'\n')
    else:
        saved=json.loads(plan.read_text())
        if saved['candidate_sites']!=design['candidate_sites']:raise RuntimeError('frozen plan or source version changed')
    print(selected.to_string(index=False));print(json.dumps(design,indent=2))

def acquire():
    path=OUT/'plan.json'
    if not path.is_file():raise RuntimeError('Freeze the candidate and reference rule first')
    plan=json.loads(path.read_text());DATA.mkdir(parents=True,exist_ok=True)
    target=DATA/'01_Data.zip'
    if target.exists():
        if target.stat().st_size!=plan['archive_bytes']:raise RuntimeError('Existing source archive differs; refusing replacement')
        state='existing_verified'
    else:
        with tempfile.NamedTemporaryFile(dir=DATA,prefix='download_',suffix='.partial',delete=False) as tmp:
            temporary=Path(tmp.name)
            try:
                with requests.get(plan['archive_url'],stream=True,timeout=(15,120),headers={'User-Agent':'stream-temperature reference research'}) as response:
                    response.raise_for_status()
                    for block in response.iter_content(1024*1024):
                        if block:tmp.write(block)
                tmp.flush()
                if temporary.stat().st_size!=plan['archive_bytes']:raise ValueError('archive size mismatch')
            except Exception:
                temporary.unlink(missing_ok=True);raise
        temporary.replace(target);state='created_verified'
    with zipfile.ZipFile(target) as z:
        entries=[x for x in z.namelist() if '01FW013' in Path(x).name and x.lower().endswith('.csv')]
        if len(entries)!=1:raise ValueError('selected site file not unique within archive')
        with z.open(entries[0]) as f:header=f.readline().decode('utf-8-sig').strip()
    receipt={'status':state,'archive':str(target.relative_to(ROOT)),'archive_bytes':target.stat().st_size,
             'selected_member':entries[0],'selected_header':header,
             'access_scope':'archive contains all 32 sites; only selected site header inspected at acquisition',
             'license':'CC BY 4.0; Kokoszka et al. 2025, DOI 10.5281/zenodo.15053907'}
    (OUT/'acquisition.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))

def qualify_year(frame,year):
    """Check 96 unique UTC quarter-hours, finite temperatures and P/A flags per day."""
    selected=frame.loc[frame.timestamp.dt.year.eq(year)].copy()
    expected=pd.date_range(f'{year}-01-01',f'{year+1}-01-01',freq='D',inclusive='left',tz='UTC')
    if selected.empty:
        return dict(year=year,calendar_days=len(expected),source_rows=0,complete_days=0,missing_days=len(expected),
                    duplicate_rows=0,off_grid_rows=0,nonfinite_rows=0,disallowed_flag_rows=0,qualified=False),pd.DataFrame()
    ts=selected.timestamp
    grid=ts.dt.minute.mod(15).eq(0)&ts.dt.second.eq(0)&ts.dt.microsecond.eq(0)&ts.dt.nanosecond.eq(0)
    finite=np.isfinite(selected.temperature.to_numpy(float))
    flag_ok=selected.flag.isin(ALLOWED)
    selected['_day']=ts.dt.floor('D');selected['_grid']=grid.to_numpy();selected['_finite']=finite;selected['_flag_ok']=flag_ok.to_numpy()
    by_day=selected.groupby('_day').agg(rows=('timestamp','size'),unique=('timestamp','nunique'),
        grid=('_grid','sum'),finite=('_finite','sum'),allowed=('_flag_ok','sum'),mean=('temperature','mean')).reindex(expected)
    complete=by_day[['rows','unique','grid','finite','allowed']].eq(96).all(axis=1)
    dates=by_day.loc[complete,['mean']].reset_index(names='date').rename(columns={'mean':'water_c'})
    summary=dict(year=year,calendar_days=len(expected),source_rows=len(selected),complete_days=int(complete.sum()),
        missing_days=int((~complete).sum()),duplicate_rows=int(selected.timestamp.duplicated(keep=False).sum()),
        off_grid_rows=int((~grid).sum()),nonfinite_rows=int((~finite).sum()),
        disallowed_flag_rows=int((~flag_ok).sum()),qualified=bool(complete.all()))
    return summary,dates

def qualify():
    plan_path=OUT/'plan.json';receipt_path=OUT/'acquisition.json'
    if not plan_path.is_file() or not receipt_path.is_file():raise RuntimeError('Freeze and acquire the archive first')
    plan=json.loads(plan_path.read_text());receipt=json.loads(receipt_path.read_text())
    archive=ROOT/receipt['archive']
    if archive.stat().st_size!=plan['archive_bytes']:raise RuntimeError('archive differs from frozen version')
    with zipfile.ZipFile(archive) as z:
        with z.open(receipt['selected_member']) as f:
            raw=pd.read_csv(f,dtype={'station_code':str,'wtmp_flag':str})
    expected=['station_code','timestamp (UTC)','wtmp (°C)','wtmp_flag']
    if raw.columns.tolist()!=expected:raise ValueError('selected CSV schema changed')
    if not raw.station_code.eq(plan['candidate_sites'][0]).all():raise ValueError('unexpected station identity')
    timestamps=pd.to_datetime(raw['timestamp (UTC)'],utc=True,errors='coerce')
    if timestamps.isna().any():raise ValueError('unparseable source timestamp')
    frame=pd.DataFrame({'timestamp':timestamps,'temperature':pd.to_numeric(raw['wtmp (°C)'],errors='coerce'),
                        'flag':raw.wtmp_flag.fillna('').str.strip().str.upper()})
    frame['_year']=frame.timestamp.dt.year
    chosen=frame.loc[frame._year.isin(plan['years_utc'])].copy()
    chosen['_finite']=np.isfinite(chosen.temperature.to_numpy(float))
    flags=chosen.groupby(['_year','flag'],dropna=False).agg(rows=('flag','size'),finite_values=('_finite','sum')).reset_index().rename(columns={'_year':'year'})
    flags['allowed_by_frozen_rule']=flags.flag.isin(ALLOWED)
    flags.to_csv(OUT/'qualification_flags.csv',index=False)
    rows=[];daily=[]
    for year in plan['years_utc']:
        summary,days=qualify_year(frame,year);rows.append(summary)
        if len(days):days['year']=year;daily.append(days)
    table=pd.DataFrame(rows);table.to_csv(OUT/'qualification_years.csv',index=False)
    eligible=int(table.qualified.sum())>=4
    data_path=DATA/'01FW013_complete_utc_days.parquet'
    if daily:
        values=pd.concat(daily,ignore_index=True)
        # Derived values retain the source's CC BY terms; do not replace an inconsistent existing file.
        if data_path.exists():
            old=pd.read_parquet(data_path)
            try:pd.testing.assert_frame_equal(old,values,check_dtype=True,check_exact=True)
            except AssertionError as exc:raise RuntimeError('Existing derived daily values differ; preserve them') from exc
        else:values.to_parquet(data_path,index=False)
    state={'status':'qualified' if eligible else 'not_qualified','station':'01FW013',
           'years_evaluated':plan['years_utc'],'qualified_reference_years':int(table.qualified.sum()),
           'qualified_four_year_reference':bool(eligible),'qualified_dates_stored':int(sum(x['complete_days'] for x in rows)),
           'reference_rule':plan['reference_rule'],'source':'CC BY 4.0, DOI 10.5281/zenodo.15053907',
           'limitation':'author flags are recommended quality classifications, not error-free measurements; quarter-hour coverage is not continuous physical observation; same river as prior BC exploratory site 08JA017, no independent climate or natural-outage reference'}
    (OUT/'qualification_status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(table.to_string(index=False));print(json.dumps(state,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['freeze','acquire','qualify']);a=p.parse_args()
    {'freeze':freeze,'acquire':acquire,'qualify':qualify}[a.phase]()

if __name__=='__main__':main()

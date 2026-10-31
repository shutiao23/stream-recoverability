#!/usr/bin/env python3
"""Freeze Poudre candidate sites and inspect deployment logs without temperature values."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_csu_ross'
DATA=ROOT/'data/external/wrr_poudre_ross_20261026'
ID='521e317e189e498581d0aaa08c3f32bc'
BASE=f'https://www.hydroshare.org/hsapi/resource/{ID}'

def get(url):
    response=requests.get(url.replace('http://','https://',1),timeout=45,headers={'User-Agent':'stream-temperature reference research'})
    response.raise_for_status();return response

def metadata_possible_years(start,end):
    a=pd.to_datetime(start,utc=True,errors='coerce');b=pd.to_datetime(end,utc=True,errors='coerce')
    if pd.isna(a) or pd.isna(b):return []
    return [y for y in range(2020,2025) if a<=pd.Timestamp(year=y,month=1,day=1,tz='UTC') and b>=pd.Timestamp(year=y,month=12,day=31,hour=23,minute=45,tz='UTC')]

def freeze():
    OUT.mkdir(parents=True,exist_ok=True)
    catalog=get(BASE+'/files/').json()
    if catalog.get('next'):raise RuntimeError('paginated source catalog; do not assume completeness')
    files=catalog['results'];selected=[x for x in files if x['file_name']=='CSU_ROSS_sonde_location_metadata.csv']
    if len(selected)!=1:raise ValueError('site metadata file not unique')
    metadata=pd.read_csv(io.BytesIO(get(selected[0]['url']).content))
    req={'site','latitude','longitude','site_description','data_start_date','data_end_date'}
    if not req.issubset(metadata):raise ValueError('unexpected site metadata schema')
    metadata['possible_full_utc_years']=[metadata_possible_years(a,b) for a,b in zip(metadata.data_start_date,metadata.data_end_date)]
    metadata['n_possible_full_utc_years']=metadata.possible_full_utc_years.map(len)
    candidates=metadata.loc[metadata.n_possible_full_utc_years.ge(4)].copy()
    if candidates.site.duplicated().any():raise ValueError('candidate site has multiple location records')
    expected={'salyer','riverbend','cottonwood','archery'}
    if set(candidates.site)!=expected:raise ValueError('metadata-only candidate set changed; preserve the frozen plan')
    metadata['possible_full_utc_years']=metadata.possible_full_utc_years.map(lambda x:';'.join(map(str,x)))
    candidates['possible_full_utc_years']=candidates.possible_full_utc_years.map(lambda x:';'.join(map(str,x)))
    cpath=OUT/'candidate_roster.csv';mpath=OUT/'site_metadata.csv'
    if cpath.exists():
        old=pd.read_csv(cpath)
        if old.site.tolist()!=candidates.site.tolist():raise RuntimeError('frozen roster changed')
    else:metadata.to_csv(mpath,index=False);candidates.to_csv(cpath,index=False)
    notes=[x for x in files if x['file_name'].endswith('field_notes.csv') or '_field_notes_' in x['file_name']]
    source_xml=get(BASE+'/scimeta/').content
    xml=ET.fromstring(source_xml)
    ns={'hs':'https://www.hydroshare.org/terms/','rdf':'http://www.w3.org/1999/02/22-rdf-syntax-ns#'}
    licenses=[x.attrib.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource','') for x in xml.findall('.//hs:URL',ns)]
    if not any('creativecommons.org/licenses/by/4.0' in x for x in licenses):raise ValueError('source CC BY 4.0 metadata not confirmed')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'source_doi':'10.4211/hs.'+ID,'license':'CC BY 4.0',
      'published_site_location_rows':len(metadata),'candidates':sorted(candidates.site.tolist()),'candidate_count':len(candidates),
      'selection':'all individual metadata location records spanning at least four complete UTC calendar years among 2020-2024; metadata period is only an upper bound, not proof of observations',
      'preflight':'inspect author-declared site, timestamp and deployment/removal field-note columns; no sensor readings, temperatures or prediction errors are retained',
      'rule':'provider says equipment generally deployed March-November; use site-specific removal/redeployment notes only as indicative evidence, not proof of zero measurement coverage',
      'prior_contact':'previous national USGS metadata includes named Poudre stations; direct matching to these CSU sites and river networks remains unverified; all candidates share a watershed',
      'limitation':'unregistered, nonrandom, location dates may span long internal gaps; source notes 2019-2021 has no calibration data and substantial gaps; one watershed is not four independent climates'}
    if not (OUT/'plan.json').exists():(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    (OUT/'field_note_catalog.json').write_text(json.dumps([{'file_name':x['file_name'],'size':x['size'],'url':x['url'].replace('http://','https://',1)} for x in notes],indent=2)+'\n')
    print(candidates[['site','data_start_date','data_end_date','n_possible_full_utc_years']].to_string(index=False));print(json.dumps(plan,indent=2));print('field-note files',len(notes))

def logged_gaps(events):
    """Consecutive documented removal then redeployment; visit times are approximate."""
    pairs=[]
    for site,g in events.sort_values(['site','timestamp']).groupby('site'):
        changes=g.loc[g.action.notna()].copy()
        conflicts=changes.groupby('timestamp').action.nunique()
        if conflicts.gt(1).any():raise ValueError(f'ambiguous deployment status at same time for {site}')
        changes=changes.drop_duplicates(['timestamp','action'])
        states=list(changes[['timestamp','action']].itertuples(index=False,name=None))
        for (start,one),(end,two) in zip(states,states[1:]):
            if one==1 and two==0 and end-start>=pd.Timedelta(days=1):
                pairs.append({'site':site,'removed_visit':start,'redeployed_visit':end,
                              'days_between_visits':(end-start).total_seconds()/86400})
    return pd.DataFrame(pairs,columns=['site','removed_visit','redeployed_visit','days_between_visits'])

def notes():
    if not (OUT/'plan.json').exists():raise RuntimeError('Freeze metadata candidates first')
    plan=json.loads((OUT/'plan.json').read_text());catalog=json.loads((OUT/'field_note_catalog.json').read_text())
    all_events=[];receipts=[]
    for item in catalog:
        response=get(item['url']);data=pd.read_csv(io.BytesIO(response.content),usecols=['site','DateTime_UTC','sonde_employed'],dtype=str)
        selected=data.loc[data.site.isin(plan['candidates'])].copy()
        selected['timestamp']=pd.to_datetime(selected.DateTime_UTC,utc=True,errors='coerce',format='mixed')
        numeric=pd.to_numeric(selected.sonde_employed,errors='coerce')
        invalid=numeric.notna()&~numeric.isin([0,1])
        if invalid.any():raise ValueError('unexpected deployment status')
        missing_timestamp=int((selected.timestamp.isna()&numeric.notna()).sum())
        selected['action']=numeric
        receipts.append({'file_name':item['file_name'],'download_bytes':len(response.content),'candidate_notes':len(selected),
                         'nonempty_action_without_timestamp':missing_timestamp})
        all_events.append(selected[['site','timestamp','action']].dropna(subset=['timestamp']))
    events=pd.concat(all_events,ignore_index=True).drop_duplicates().sort_values(['site','timestamp'])
    gaps=logged_gaps(events)
    events.to_csv(OUT/'candidate_deployment_events.csv',index=False)
    gaps.to_csv(OUT/'candidate_logged_removal_pairs.csv',index=False)
    years=[]
    for site in plan['candidates']:
        candidate=gaps.loc[gaps.site.eq(site)]
        for year in range(2020,2025):
            start=pd.Timestamp(year=year,month=1,day=1,tz='UTC');end=pd.Timestamp(year=year+1,month=1,day=1,tz='UTC')
            overlap=(candidate.removed_visit<end)&(candidate.redeployed_visit>start)
            years.append({'site':site,'year':year,'logged_removal_pairs_overlapping_year':int(overlap.sum()),
                          'some_overlapping_removal_pair':bool(overlap.any())})
    year_table=pd.DataFrame(years);year_table.to_csv(OUT/'deployment_years.csv',index=False)
    status={'status':'metadata_preflight_complete','candidate_sites':len(plan['candidates']),
      'field_note_files':len(catalog),'candidate_event_rows':len(events),'removal_redeployment_pairs':len(gaps),
      'candidate_site_years_with_logged_gap':int(year_table.some_overlapping_removal_pair.sum()),
      'nonempty_action_missing_timestamp':sum(x['nonempty_action_without_timestamp'] for x in receipts),
      'temperature_values_retained':False,'qualified_reference_sites':0,
      'interpretation':'field notes indicate visits and possible deployment gaps, not direct proof that no temperature measurements exist; multiple sensors, unlogged actions, timestamp uncertainty and internal gaps remain unverified',
      'receipts':receipts}
    (OUT/'deployment_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(year_table.to_string(index=False));print(json.dumps(status,indent=2))

def freeze_qualification():
    if not (OUT/'deployment_status.json').exists():raise RuntimeError('Complete the metadata and deployment preflight first')
    plan=json.loads((OUT/'plan.json').read_text());listing=get(BASE+'/files/').json()
    if listing.get('next'):raise RuntimeError('source file catalog is paginated')
    wanted=[f'CSU_ROSS_{year}_raw.parquet' for year in range(2020,2025)]
    items=[]
    for name in wanted:
        found=[x for x in listing['results'] if x['file_name']==name]
        if len(found)!=1:raise ValueError(f'raw source file missing or ambiguous: {name}')
        item=found[0]
        items.append({'file_name':name,'url':item['url'].replace('http://','https://',1),
                      'size':item['size'],})
    design={'created_utc':datetime.now(timezone.utc).isoformat(),'source_doi':plan['source_doi'],
      'candidates':plan['candidates'],'years_utc':list(range(2020,2025)),
      'source_files':wanted,'parameter':'Temperature','units':'degrees C',
      'measurement_column':'value_post_drift_corr','quality_column':'qc_status','accepted_quality':['PASS'],
      'daily_reference':'exactly 96 unique quarter-hour UTC records, finite final reported value and PASS quality for every record; duplicates and off-grid readings invalidate a day',
      'annual_reference':'all UTC days in the year satisfy the daily rule; at least four such years are needed at one site',
      'sampling':'fixed four candidates from published metadata; 2019 and 2025 cannot be complete calendar years according to resource period',
      'independence':'single Poudre watershed; named nearby USGS metadata was previously encountered, connectivity and exact station matching not yet independently established',
      'caveat':'source says 2019-2021 lacked technician calibration records; even a fully PASS year is not proof of sensor calibration, independent climate or suitability for blinded confirmation',
      'precontact':'metadata, file schemas/descriptions and deployment notes examined; temperature data and prediction errors not examined before this plan'}
    qpath=OUT/'qualification_plan.json';cpath=OUT/'temperature_file_catalog.json'
    if qpath.exists():
        prior=json.loads(qpath.read_text())
        if prior['candidates']!=design['candidates'] or prior['source_files']!=design['source_files']:raise RuntimeError('existing frozen qualification changed')
    else:qpath.write_text(json.dumps(design,indent=2)+'\n');cpath.write_text(json.dumps(items,indent=2)+'\n')
    print(json.dumps(design,indent=2));print('download bytes',sum(x['size'] for x in items))

def acquire():
    if not (OUT/'qualification_plan.json').exists():raise RuntimeError('Freeze the qualification before opening temperature data')
    catalog=json.loads((OUT/'temperature_file_catalog.json').read_text());DATA.mkdir(parents=True,exist_ok=True)
    prior_path=OUT/'acquisition.json';checkpoint=OUT/'acquisition_in_progress.json'
    prior=json.loads(prior_path.read_text()) if prior_path.exists() else (json.loads(checkpoint.read_text()) if checkpoint.exists() else {})
    known={x['file_name']:x for x in prior.get('files',[])};receipts=[]
    for item in catalog:
        dest=DATA/item['file_name']
        if dest.exists() and item['file_name'] not in known:raise RuntimeError('existing source file has no local receipt; preserve it for review')
        if not dest.exists():
            with tempfile.NamedTemporaryFile(dir=DATA,prefix='source_',suffix='.partial',delete=False) as tmp:
                partial=Path(tmp.name)
                try:
                    with requests.get(item['url'],stream=True,timeout=(15,120),headers={'User-Agent':'stream-temperature reference research'}) as response:
                        response.raise_for_status()
                        for block in response.iter_content(1024*1024):
                            if block:tmp.write(block)
                    tmp.flush()
                    if partial.stat().st_size!=item['size']:raise ValueError('download size differs from frozen catalog')
                except Exception:
                    partial.unlink(missing_ok=True);raise
            partial.replace(dest)
        if dest.stat().st_size!=item['size']:raise ValueError('existing source file size differs from frozen catalog')
        receipts.append({'file_name':item['file_name'],'size':dest.stat().st_size,})
        checkpoint.write_text(json.dumps({'status':'in_progress','files':receipts},indent=2)+'\n')
        print('Acquired',item['file_name'],flush=True)
    receipt={'status':'acquired','source_doi':'10.4211/hs.'+ID,'license':'CC BY 4.0','files':receipts,
             'scope':'each source file contains multiple sites and parameters; only frozen candidates will be read for qualification',
             }
    prior_path.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))

def qualify():
    """Evaluate 15-minute completeness and provider PASS flags, never model predictions."""
    required=['qualification_plan.json','qualification_unit_mapping.json','acquisition.json']
    if any(not (OUT/x).exists() for x in required):raise RuntimeError('Frozen plan, unit clarification and source receipt are required')
    plan=json.loads((OUT/'qualification_plan.json').read_text())
    unit=json.loads((OUT/'qualification_unit_mapping.json').read_text())
    receipt=json.loads((OUT/'acquisition.json').read_text())
    if receipt['status']!='acquired' or unit['observed_raw_unit']!='C':raise RuntimeError('source acquisition or unit mapping is invalid')
    import importlib.util
    spec=importlib.util.spec_from_file_location('quarterhour_qualification',ROOT/'scripts/585_nechako_reference_qualification.py')
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    blocks=[]
    cols=['DateTime_UTC','site','parameter','units','value_post_drift_corr','qc_status']
    for item in receipt['files']:
        path=DATA/item['file_name'];
        with path.open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
        frame=pd.read_parquet(path,columns=cols,filters=[('site','in',plan['candidates']),('parameter','=',plan['parameter'])])
        unexpected=set(frame.units.dropna().astype(str))-{'C'}
        if unexpected:raise ValueError(f'unverified temperature unit labels: {unexpected}')
        timestamps=pd.to_datetime(frame.DateTime_UTC,utc=True,errors='coerce',format='mixed')
        if timestamps.isna().any():raise ValueError('unparseable candidate timestamps')
        quality=frame.qc_status.fillna('').astype(str).str.strip().str.upper()
        quality_ok=quality.eq('PASS') & frame.units.eq('C')
        blocks.append(pd.DataFrame({'site':frame.site.to_numpy(), 'timestamp':timestamps.to_numpy(),
             'temperature':pd.to_numeric(frame.value_post_drift_corr,errors='coerce').to_numpy(),
             'flag':np.where(quality_ok,'P','REJECT'),'quality':quality.to_numpy(),
             'unit_ok':frame.units.eq('C').fillna(False).to_numpy()}))
        print('Read frozen candidate columns from',item['file_name'],flush=True)
    values=pd.concat(blocks,ignore_index=True)
    values['timestamp']=pd.to_datetime(values.timestamp,utc=True)
    rows=[];flag_rows=[]
    for site in plan['candidates']:
        site_data=values.loc[values.site.eq(site)]
        for year in plan['years_utc']:
            summary,_=checker.qualify_year(site_data,year);summary['site']=site;rows.append(summary)
            selected=site_data.loc[site_data.timestamp.dt.year.eq(year)]
            ts=selected.timestamp
            on_grid=ts.dt.minute.mod(15).eq(0)&ts.dt.second.eq(0)&ts.dt.microsecond.eq(0)&ts.dt.nanosecond.eq(0)
            summary['expected_quarter_hours']=summary['calendar_days']*96
            summary['missing_quarter_hour_timestamps']=summary['expected_quarter_hours']-int(ts.loc[on_grid].nunique())
            if summary['missing_quarter_hour_timestamps']<0:raise ValueError('more unique grid timestamps than calendar permits')
            selected=selected.copy();selected['_finite']=np.isfinite(selected.temperature.to_numpy(float))
            for (label,unit_ok),group in selected.groupby(['quality','unit_ok'],dropna=False):
                flag_rows.append({'site':site,'year':year,'qc_status':str(label),'unit_ok':bool(unit_ok),
                                  'rows':len(group),'finite_values':int(group._finite.sum())})
    table=pd.DataFrame(rows);flags=pd.DataFrame(flag_rows,columns=['site','year','qc_status','unit_ok','rows','finite_values'])
    table=table[['site']+[x for x in table.columns if x!='site']]
    table.to_csv(OUT/'qualification_years.csv',index=False);flags.to_csv(OUT/'qualification_qc_counts.csv',index=False)
    grouped=table.groupby('site').agg(complete_author_pass_years=('qualified','sum'),calendar_years_checked=('year','size'),
                                     fully_pass_days=('complete_days','sum')).reset_index()
    grouped['four_complete_author_pass_years']=grouped.complete_author_pass_years.ge(4)
    grouped.to_csv(OUT/'candidate_qualification.csv',index=False)
    state={'status':'qualification_computed','sites':len(grouped),'years_per_site':len(plan['years_utc']),
           'site_years':len(table),'author_pass_complete_years':int(table.qualified.sum()),
           'site_years_with_missing_quarter_hour_timestamps':int(table.missing_quarter_hour_timestamps.gt(0).sum()),
           'minimum_missing_quarter_hour_timestamps':int(table.missing_quarter_hour_timestamps.min()),
           'sites_with_four_author_pass_complete_years':int(grouped.four_complete_author_pass_years.sum()),
           'new_independent_climate_confirmations':0,'reconstruction_accuracy_evaluated':False,
           'data_rule':plan['daily_reference'],'unit_mapping':unit['interpretation'],
           'limitation':'same watershed; source notes early years lacked technician calibration records; PASS and 15-minute coverage do not prove physical accuracy; source quality and prior-contact/network independence remain to be evaluated before calling any site an independent reference'}
    (OUT/'qualification_status.json').write_text(json.dumps(state,indent=2)+'\n')
    print(table.to_string(index=False));print(json.dumps(state,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['freeze','notes','freeze_qualification','acquire','qualify']);a=p.parse_args()
    {'freeze':freeze,'notes':notes,'freeze_qualification':freeze_qualification,'acquire':acquire,'qualify':qualify}[a.phase]()

if __name__=='__main__':main()

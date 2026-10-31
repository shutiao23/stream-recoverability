#!/usr/bin/env python3
"""Post-hoc compare USGS donor-panel daily means with current USGS daily values.

Reference retrieval is read-only and restricted to fixed public station IDs,
parameter 00010 and statistic 00003. Results are provenance evidence only;
they do not verify original data vintage, instrument accuracy or legal rights.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026/donor_provenance/usgs_daily'
META=PRIVATE.parent/'usgs_metadata';URL='https://waterservices.usgs.gov/nwis/dv/'

def freeze():
    path=OUT/'donor_usgs_daily_plan.json'
    if path.exists():raise FileExistsError('Preserve existing daily-comparison plan')
    audit=json.loads((OUT/'donor_metadata_independent_audit.json').read_text());roster=META/'unresolved_columns.csv'
    source=json.loads((OUT/'donor_usgs_metadata_plan.json').read_text())
    if audit['status']!='passed_metadata_identity_checks':raise ValueError('Metadata roster changed')
    columns=pd.read_csv(roster,dtype=str);jobs=pd.DataFrame(T.load_script('usgs_daily_plan_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source'))
    dates=[];paths=[]
    for network in sorted(columns.network_id.unique()):
        g=jobs[jobs.network_id.eq(network)&jobs.provider.eq('usgs')]
        if g.input_path.nunique()!=1:raise ValueError('Ambiguous panel')
        p=Path(g.input_path.iloc[0]);day=pd.to_datetime(pd.read_csv(p,usecols=['date']).date,errors='raise')
        if day.duplicated().any():raise ValueError('Duplicate local panel date')
        dates.extend([day.min(),day.max()]);paths.append(p)
    ids=sorted(set(columns.station_id));PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    inputs={}
    locked=PRIVATE/'inputs.json';locked.write_text(json.dumps(inputs,indent=2)+'\n');locked.chmod(0o600)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after source models, metadata results and panel date ranges were seen; before current USGS daily-value responses or differences are examined',
          'selection':'All 69 distinct USGS identifiers previously absent from three local catalogs; includes all 73 network-column occurrences, regardless of model contribution or outcome.',
          'site_count':len(ids),'panel_columns':len(columns),'panel_count':len(paths),'start_date':min(dates).strftime('%Y-%m-%d'),'end_date':max(dates).strftime('%Y-%m-%d'),
          'request':'USGS daily values, all sites in batches of 10, variable 00010 (water temperature), daily mean statistic 00003, all available approval statuses; retain qualifiers.',
          'comparison':'For each panel column compare all finite cached values with same-site, same-date finite current USGS values, only when all returned rows for a site and date agree; report missing or ambiguous source dates and overlapping absolute differences at 1e-6, 0.01 and 0.1 C. Network-column repeated days are not independent.',
          'limitations':'Current API values can differ from historical versions or local quality processing. A match does not prove the original provider, timing, sensor accuracy, calibration, derivative rights, or independent-climate performance.',
          }
    path.write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps(plan,indent=2))

def verify(plan):
    lock=PRIVATE/'inputs.json'
    d=json.loads(lock.read_text())

def retrieve():
    plan=json.loads((OUT/'donor_usgs_daily_plan.json').read_text());verify(plan)
    columns=pd.read_csv(META/'unresolved_columns.csv',dtype=str);ids=sorted(set(columns.station_id))
    receipt=PRIVATE/'acquisition.json';batches=[]
    for i,start in enumerate(range(0,len(ids),10),1):
        chunk=ids[start:start+10];dest=PRIVATE/f'batch_{i:02d}.json.gz';entry={'batch':i,'requested_sites':len(chunk),'status':'unknown'}
        params={'format':'json','sites':','.join(chunk),'parameterCd':'00010','statCd':'00003',
                'startDT':plan['start_date'],'endDT':plan['end_date'],'siteStatus':'all'}
        try:
            if dest.exists():
                with gzip.open(dest,'rb') as f:body=f.read()
                entry['from_cache']=True;entry['http_status']=200
            else:
                r=requests.get(URL,params=params,timeout=55,headers={'User-Agent':'Stream temperature research provenance audit/1.0'})
                entry['http_status']=r.status_code;entry['response_bytes']=len(r.content)
                if r.status_code!=200:
                    batches.append(entry);print('Daily batch',i,'HTTP',r.status_code,flush=True);continue
                body=r.content
            parsed=json.loads(body);series=parsed['value']['timeSeries']
            for x in series:
                site=x['sourceInfo']['siteCode'][0]['value'];var=x['variable'];parameter=var['variableCode'][0]['value'];opt=var.get('options',{}).get('option',[])
                if site not in chunk or parameter!='00010' or not any(y.get('optionCode')=='00003' for y in opt):raise ValueError('Unexpected USGS series')
            if not dest.exists():
                with gzip.open(dest,'wb',compresslevel=5) as f:f.write(body)
                dest.chmod(0o600)
            entry.update(status='completed',series=len(series),)
        except (requests.RequestException,ValueError,KeyError,json.JSONDecodeError,OSError) as exc:entry['error_type']=type(exc).__name__
        batches.append(entry);receipt.write_text(json.dumps(batches,indent=2)+'\n');receipt.chmod(0o600)
        print('Daily batch',i,entry['status'],flush=True)
    receipt.write_text(json.dumps(batches,indent=2)+'\n');receipt.chmod(0o600)
    result={'status':'completed' if len(batches)==7 and all(x['status']=='completed' for x in batches) else 'partial',
            'batch_count':len(batches),'completed_batches':sum(x['status']=='completed' for x in batches),
            'requested_identifiers':len(ids),'limitations':plan['limitations']}
    (OUT/'donor_usgs_daily_acquisition.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

def compare():
    plan=json.loads((OUT/'donor_usgs_daily_plan.json').read_text());verify(plan)
    acquisition=json.loads((OUT/'donor_usgs_daily_acquisition.json').read_text());receipt=PRIVATE/'acquisition.json'
    if acquisition['status']!='completed':raise ValueError('Incomplete acquisition; missing sites are not zero')
    rows=[]
    for entry in json.loads(receipt.read_text()):
        p=PRIVATE/f"batch_{entry['batch']:02d}.json.gz"
        with gzip.open(p,'rt') as f:payload=json.load(f)
        for ts in payload['value']['timeSeries']:
            site=ts['sourceInfo']['siteCode'][0]['value'];series=ts.get('name','')
            for v in ts['values']:
                for obs in v.get('value',[]):
                    try:value=float(obs['value'])
                    except (TypeError,ValueError):continue
                    if np.isfinite(value) and value!=-999999.0:
                        rows.append({'site':site,'date':str(obs['dateTime'])[:10],'value':value,'series':series,
                                     'qualifiers':';'.join(sorted(obs.get('qualifiers',[])))})
    raw=pd.DataFrame(rows)
    if raw.empty:raise ValueError('No numeric USGS observations returned')
    grouped=raw.groupby(['site','date']).value.agg(['min','max','size'])
    grouped['unique_value']=grouped['min'].where((grouped['max']-grouped['min']).abs()<=1e-10)
    entries=pd.read_csv(META/'unresolved_columns.csv',dtype=str);jobs=pd.DataFrame(T.load_script('usgs_daily_compare_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source'))
    summaries=[]
    for network,cols in entries.groupby('network_id'):
        path=jobs[jobs.network_id.eq(network)&jobs.provider.eq('usgs')].input_path.unique()
        if len(path)!=1:raise ValueError('Panel lookup ambiguous')
        panel=pd.read_csv(path[0],usecols=['date']+cols.station_id.tolist(),dtype={'date':str}).set_index('date')
        if panel.index.duplicated().any():raise ValueError('Duplicate local date')
        for station in cols.station_id:
            local=pd.to_numeric(panel[station],errors='coerce');local=local[np.isfinite(local)]
            if station in grouped.index.get_level_values('site'):
                reference=grouped.loc[station].reindex(local.index)
                has_source=reference['size'].notna();unique=reference.unique_value.notna();diff=(local-reference.unique_value).abs();matched=diff.notna()
                summaries.append({'station_id':station,'network_id':network,'local_finite_days':len(local),'source_days':int(has_source.sum()),
                    'ambiguous_source_days':int((has_source&~unique).sum()),'compared_days':int(matched.sum()),
                    'equal_1e_6':int((diff<=1e-6).sum()),'equal_0_01':int((diff<=.01).sum()),'different_over_0_1':int((diff>.1).sum()),
                    'absolute_error_sum':float(diff.sum()),'maximum_absolute_difference':float(diff.max()) if matched.any() else np.nan})
            else:summaries.append({'station_id':station,'network_id':network,'local_finite_days':len(local),'source_days':0,
                                   'ambiguous_source_days':0,'compared_days':0,'equal_1e_6':0,'equal_0_01':0,'different_over_0_1':0,'absolute_error_sum':0.,'maximum_absolute_difference':np.nan})
    by=pd.DataFrame(summaries);by.to_csv(PRIVATE/'column_comparisons.csv',index=False);(PRIVATE/'column_comparisons.csv').chmod(0o600)
    sums={k:int(by[k].sum()) for k in ['local_finite_days','source_days','ambiguous_source_days','compared_days','equal_1e_6','equal_0_01','different_over_0_1']}
    result={'status':'computed_posthoc','panel_columns':len(by),'unique_sites':by.station_id.nunique(),
            'columns_with_comparisons':int(by.compared_days.gt(0).sum()),'series_returned':int(raw[['site','series']].drop_duplicates().shape[0]),
            **sums,'mean_absolute_difference':float(by.absolute_error_sum.sum()/sums['compared_days']) if sums['compared_days'] else None,
            'maximum_absolute_difference':float(by.maximum_absolute_difference.max()) if by.maximum_absolute_difference.notna().any() else None,
            'source_qualifier_counts':raw.qualifiers.value_counts().to_dict(),'limitations':plan['limitations'],
            'unit':'Panel-column days; the same site/day may occur in multiple panels. Counts do not represent independent observations.'}
    (OUT/'donor_usgs_daily_comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','retrieve','compare']);a=p.parse_args()
    {'freeze':freeze,'retrieve':retrieve,'compare':compare}[a.action]()

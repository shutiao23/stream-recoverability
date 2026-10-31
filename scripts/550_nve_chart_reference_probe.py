#!/usr/bin/env python3
"""Probe fixed NVE metadata candidates through the provider's public chart service.

No service credential is used. A chart response is not assumed to carry
per-observation quality or raw subdaily completeness flags.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nve_seriekart_metadata'
URL='https://chartserver.nve.no/ShowData.aspx'


def select_unseen_basins(f, prior_station_ids):
    oldbasins={int(x.split('.')[0]) for x in prior_station_ids}
    f=f.loc[~f.stasjonnr.map(lambda x:int(x.split('.')[0]) in oldbasins)].copy()
    f['basin']=f.stasjonnr.map(lambda x:int(x.split('.')[0]))
    return f.sort_values(['basin','antallkompletteaar','stasjonnr'],ascending=[True,False,True]).drop_duplicates('basin')


def make_roster():
    f=pd.read_csv(OUT/'unmatched_metadata_candidates.csv',dtype={'stasjonnr':str})
    raw=pd.read_parquet(ROOT/'results/wrr_submission_ready/multi_agency_ingest/nve/raw_cache/observations_raw.parquet',columns=['station_id'])
    prior=set(raw.station_id.astype(str))
    old=pd.read_csv(ROOT/'results/wrr_submission_ready/nve_confirmation_batch1_stations.csv',dtype=str)
    if 'station_id' in old:prior |= set(old.station_id.dropna())
    return select_unseen_basins(f, prior)


def main():
    f=make_roster();path=OUT/'chart_candidate_roster.csv'
    if path.exists():
        old=pd.read_csv(path,dtype={'stasjonnr':str})
        if old.stasjonnr.tolist()!=f.stasjonnr.tolist():raise RuntimeError('Fixed candidate roster differs')
    else:f.to_csv(path,index=False)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'roster_selection':'all metadata candidates outside every basin present in named earlier NVE raw and confirmation files, at most one per basin chosen by largest reported complete-year field then station ID; no temperature values used',
          'n_roster':len(f),'fixed_before_request':True,'caveats':'not a formal preregistration; potential other prior records and network/climatic dependence remain unchecked; field meaning and physical subdaily completeness need verification',
          'source':'https://seriekart.nve.no/om','chart_endpoint':'provider chart service used by public Seriekart; requests use no key',
          'evaluation':'reference qualification and scoring require actual data and documented per-observation QC; a chart response alone is insufficient'}
    if not (OUT/'chart_plan.json').exists():(OUT/'chart_plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    output=[]
    for row in f.itertuples(index=False):
        site=row.stasjonnr; version=int(row.versjon); parameter=int(row.stasjonparameterkode)
        params={'req':'getchart','ver':'1.0','time':'20100101T0000;20251231T2359','lang':'no','mth':'mean',
                'chd':f'ds=htsr,da=2,id={site}.{parameter}.{version},rt=1','vfmt':'json'}
        try:
            response=requests.get(URL,params=params,timeout=60);response.raise_for_status();document=response.json()
            if not isinstance(document,list):raise ValueError('Unexpected provider schema')
            data=[item.get('SeriesPoints',[]) for item in document]
            count=sum(len(x) for x in data)
            # Store data only if supplied; empty or ambiguous responses are not zeros.
            if count:(OUT/f'chart_{site}.json').write_text(json.dumps(document)+'\n')
            output.append(dict(station_id=site,http_status=response.status_code,n_chart_points=count,
                               legend=' | '.join(str(x.get('LegendText','')) for x in document),status='points_returned' if count else 'no_points',url=response.url))
        except (requests.RequestException,ValueError,TypeError) as exc:
            output.append(dict(station_id=site,status='request_or_schema_failure',reason=str(exc)))
    results=pd.DataFrame(output);results.to_csv(OUT/'chart_probe.csv',index=False)
    status={'candidate_stations':len(f),'points_returned':int(results.status.eq('points_returned').sum()),
            'no_points':int(results.status.eq('no_points').sum()),'failures':int(results.status.eq('request_or_schema_failure').sum()),
            'strict_reference_evaluated':False,'reconstruction_scored':False,
            'interpretation':'Chart availability probe only; empty provider responses are not proof of absent data.'}
    (OUT/'chart_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(results[['station_id','status','legend']].to_string(index=False));print(json.dumps(status,indent=2))

if __name__=='__main__':main()

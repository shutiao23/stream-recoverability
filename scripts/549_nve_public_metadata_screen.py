#!/usr/bin/env python3
"""Inventory official NVE Seriekart metadata; do not acquire station values.

Named old raw caches are excluded. This is not an independence determination
and the metadata complete-year field is not a substitute for reference QC.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nve_seriekart_metadata'
URL='https://kart.nve.no/enterprise/rest/services/Mapservices/TidsserieFeltpar/MapServer/0/query'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    p={'where':"stasjonParameter = 'Vanntemperatur' AND antallKompletteAar >= 4 AND observasjonsSted LIKE 'Elv%'",
       'outFields':'stasjonNr,stasjonNavn,stasjonParameterKode,observasjonsSted,dataFraDato,dataTilDato,antallKompletteAar,vassdragsnr,vassdragsOmradeNr,versjon,compoundKey12',
       'returnGeometry':'true','outSR':'4326','f':'json','resultRecordCount':2000}
    response=requests.get(URL,params=p,timeout=60);response.raise_for_status();doc=response.json()
    if doc.get('error') or doc.get('exceededTransferLimit'):raise ValueError('NVE metadata request failed or was truncated')
    rows=[dict(x['attributes'],latitude=x['geometry']['y'],longitude=x['geometry']['x']) for x in doc['features']]
    f=pd.DataFrame(rows).sort_values('stasjonnr')
    raw=ROOT/'results/wrr_submission_ready/multi_agency_ingest/nve/raw_cache/observations_raw.parquet'
    prior=set(pd.read_parquet(raw,columns=['station_id']).station_id.astype(str))
    old=ROOT/'results/wrr_submission_ready/nve_confirmation_batch1_stations.csv'
    old_df=pd.read_csv(old,dtype=str)
    if 'station_id' in old_df.columns: prior |= set(old_df.station_id.dropna())
    # Other previously accessed NVE files may exist; this comparison is not exhaustive.
    f['seen_in_named_raw_or_confirmation']=f.stasjonnr.isin(prior)
    f.to_csv(OUT/'catalog_metadata.csv',index=False)
    f.loc[~f.seen_in_named_raw_or_confirmation].to_csv(OUT/'unmatched_metadata_candidates.csv',index=False)
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'metadata_url':response.url,
            'catalog_series':len(f),'named_prior_station_id_count':len(prior),
            'not_in_named_raw_or_confirmation':int((~f.seen_in_named_raw_or_confirmation).sum()),
            'interpretation':'Metadata-only leads; possible past contact in other caches, shared basin or climate, ambiguous metadata coverage and reference quality remain unchecked. No candidate temperatures or model errors were requested.',
            'chartserver_pilot':'Official Seriekart chart requests for three previously opened NVE sites returned station not enabled and zero points; this does not establish unavailability for every site.',
            'access_note':'Official HydAPI requests require user registration; do not extract or reuse a client credential. The Seriekart catalog is public and the agency describes its historical series as quality controlled.',
            'sources':['https://seriekart.nve.no/om','https://www.nve.no/vann-og-vassdrag/hydrologiske-data/historiske-data/','https://api.nve.no/doc/hydrologiske-data/']}
    (OUT/'status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

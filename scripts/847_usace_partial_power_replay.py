#!/usr/bin/env python3
"""Rebuild the partial-history NASA POWER table from saved API responses."""
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];REV=ROOT/'results/wrr_review_response_20261027'
DATA=ROOT/'data/external/wrr_usace_reservoir_20261027/partial_history_power'

def main():
    manifest=json.loads((DATA/'manifest.json').read_text());status=json.loads((REV/'external_usace_reservoir/partial_history_forcing_status.json').read_text())
    frames=[]
    for item in manifest['records']:
        path=(DATA/item['file']).resolve()
        if not path.is_relative_to(DATA.resolve()) or item['parameters']['time-standard']!='LST':raise ValueError('Invalid POWER response')
        with gzip.open(path,'rt') as f:data=json.load(f)
        values=data['properties']['parameter']['T2M'];dates=pd.date_range('2021-01-01','2025-12-31')
        s=pd.to_numeric(pd.Series([values.get(t.strftime('%Y%m%d'),np.nan) for t in dates]),errors='coerce').where(lambda x:x.gt(-990))
        frames.append(pd.DataFrame({'date':dates,'air_temperature_c':s,'station_id':item['resource_id'],'network_id':'usace_'+item['resource_id']}))
    actual=pd.concat(frames,ignore_index=True).sort_values(['station_id','date']).reset_index(drop=True)
    expected=pd.read_parquet(DATA/'daily_air.parquet').sort_values(['station_id','date']).reset_index(drop=True)
    pd.testing.assert_frame_equal(actual,expected,check_dtype=False,rtol=0,atol=1e-10)
    result={'status':'passed','resources':len(frames),'daily_rows':len(actual),'finite_air_values':int(np.isfinite(actual.air_temperature_c).sum()),
       'scope':'Rebuild daily air forcing from attributed saved NASA POWER JSON responses.',
       'limitations':'The replay does not establish meteorological accuracy, water-day alignment or model prediction reproducibility.'}
    path=REV/'audit/usace_partial_power_open_replay.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()

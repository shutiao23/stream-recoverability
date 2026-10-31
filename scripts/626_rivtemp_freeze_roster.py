#!/usr/bin/env python3
"""Freeze all RivTemp location metadata without reading values or dates."""
import json
import os
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_rivtemp_metadata';PRIVATE=ROOT/'private/wrr_rivtemp_reference_20261026'
COLS=['MonitoringLocationID','MonitoringLocationName','MonitoringLocationLatitude','MonitoringLocationLongitude','MonitoringLocationHorizontalCoordinateReferenceSystem','MonitoringLocationHorizontalAccuracyMeasure','MonitoringLocationHorizontalAccuracyUnit','MonitoringLocationType']

def main():
    acquisition=json.loads((OUT/'acquisition.json').read_text());source=PRIVATE/'rivtemp_mffp_v1.csv'
    if not str(acquisition['status']).startswith('downloaded'):raise ValueError('source acquisition not verified')
    with source.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    target=PRIVATE/'all_locations_before_qualification.csv';status_path=OUT/'roster_freeze.json'
    if target.exists() or status_path.exists():raise RuntimeError('existing frozen roster and state preserved')
    unique=[];rows=0
    for chunk in pd.read_csv(source,usecols=COLS,dtype=str,keep_default_na=False,chunksize=100_000):
        rows+=len(chunk);unique.append(chunk.drop_duplicates())
    values=pd.concat(unique,ignore_index=True).drop_duplicates().sort_values(COLS,kind='stable')
    if values.MonitoringLocationID.eq('').any():raise ValueError('source rows without location identity')
    # Retain inconsistent metadata rows rather than silently choosing a location.
    count=values.groupby('MonitoringLocationID').size();ids=count.index
    conflicts=int(count.gt(1).sum())
    coords=values.assign(_lat=pd.to_numeric(values.MonitoringLocationLatitude,errors='coerce'),_lon=pd.to_numeric(values.MonitoringLocationLongitude,errors='coerce'))
    valid=np.isfinite(coords._lat)&np.isfinite(coords._lon)&coords._lat.between(-90,90)&coords._lon.between(-180,180)
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    values.to_csv(target,index=False);target.chmod(0o600)
    status={'status':'all_location_metadata_frozen_before_qualification','created_utc':datetime.now(timezone.utc).isoformat(),
      'source_rows_read_metadata_only':rows,'unique_location_ids':len(ids),'distinct_location_metadata_rows':len(values),
      'ids_with_multiple_metadata_rows':conflicts,'metadata_rows_with_valid_coordinates':int(valid.sum()),
      'all_location_types':values.MonitoringLocationType.value_counts(dropna=False).to_dict(),
      'columns_read':COLS,'excluded_from_read':['ResultValue','ActivityStartDate','ActivityEndDate','result quality and flags'],
      'local_roster':'private/wrr_rivtemp_reference_20261026/all_locations_before_qualification.csv',
      'selection':'all published location IDs; no filter on year coverage, water temperature, data status or model predictions',
      'next_step':'resolve duplicate station metadata and independently audit geographic/network and previous-contact overlap before selecting a candidate for the fixed 2010-2020 year-qualification plan',
      'limitation':'a frozen metadata roster neither establishes unique physical station identity, usable complete years, subdaily quality, nor independence'}
    status_path.write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
if __name__=='__main__':main()

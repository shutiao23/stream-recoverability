#!/usr/bin/env python3
"""Freeze NJDEP station metadata and evaluate a coarse QA-span upper bound.

No temperature data are requested. A station spanning multiple calendar years
may nevertheless have seasonal deployment, gaps, estimated values or other
quality issues. Freshwater type alone does not establish a river location.
"""
from __future__ import annotations
import io
import json
import os
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata';PRIVATE=ROOT/'private/wrr_njdep_reference_20261026'
PAGE='https://njdep.rutgers.edu/continuous/download/';COORD='https://njdep.rutgers.edu/continuous/api/latest/station/coordinates/'

def covered_years(start,end,years=range(2010,2025)):
    if pd.isna(start) or pd.isna(end):return None
    if end<start:raise ValueError('QA end precedes start')
    return sum(start<=pd.Timestamp(y,1,1) and end>=pd.Timestamp(y,12,31) for y in years)

def metadata_options(html):
    soup=BeautifulSoup(html,'html.parser');select=soup.find(id='select-stations')
    if select is None:raise ValueError('station select absent')
    rows=[]
    for op in select.find_all('option'):
        ident=op.get('value','')
        if not ident:continue
        rows.append({'station_id':ident,'label':op.get_text(' ',strip=True),'water_type':op.get('data-water-type',''),
          'station_type':op.get('data-station-type',''),'qa_start':op.get('data-qa-start',''),'qa_end':op.get('data-qa-end',''),
          'affiliation':op.get('data-aff',''),'project':op.get('data-proj',''),'huc14':op.get('data-huc14','')})
    x=pd.DataFrame(rows)
    if x.empty or x.duplicated(['station_id','label']).any():raise ValueError('station options empty or duplicate labeled entries')
    for name in ['qa_start','qa_end']:
        parsed=pd.to_datetime(x[name],format='%m/%d/%Y',errors='coerce')
        if (x[name].ne('')&parsed.isna()).any():raise ValueError('unparseable provider QA date')
        x[name+'_parsed']=parsed
    x['possible_calendar_years_2010_2024']=[covered_years(a,b) for a,b in zip(x.qa_start_parsed,x.qa_end_parsed)]
    return x

def attach_coordinates(options,coordinates):
    """Keep duplicate station IDs as distinct entries, match description if needed."""
    required={'Buoy_ID','Station','Latitude','Longitude','Description','Waterbody_Type'}
    if not required.issubset(coordinates.columns) or coordinates.duplicated(['Buoy_ID','Description']).any():
        raise ValueError('coordinate schema or descriptive keys ambiguous')
    parts=[]
    for row in options.to_dict('records'):
        candidates=coordinates.loc[coordinates.Buoy_ID.eq(row['station_id'])]
        if len(candidates)>1:
            candidates=candidates.loc[candidates.Description.map(lambda v: row['label'].startswith(v+': '))]
        hit=candidates.iloc[0].to_dict() if len(candidates)==1 else {}
        parts.append(row|{key:hit.get(key,'') for key in coordinates.columns}|{'coordinate_matched':len(candidates)==1})
    return pd.DataFrame(parts)

def main():
    p=json.loads((OUT/'plan.json').read_text())
    if p['status']!='metadata_plan_frozen_before_location_roster':raise ValueError('metadata plan not frozen')
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);PRIVATE.chmod(0o700)
    savepage=PRIVATE/'download_page.html';savecoord=PRIVATE/'station_coordinates.csv';roster=PRIVATE/'station_metadata_roster.csv';statefile=OUT/'metadata_status.json'
    if roster.exists() or statefile.exists():raise RuntimeError('existing metadata roster and status preserved')
    if savepage.exists() != savecoord.exists():raise RuntimeError('incomplete downloaded metadata preserved for inspection')
    if not savepage.exists():
        try:
            page=requests.get(PAGE,timeout=45);coord=requests.get(COORD,timeout=45)
        except requests.RequestException as e:raise RuntimeError('provider metadata endpoint unavailable: '+type(e).__name__) from None
        if page.status_code!=200 or coord.status_code!=200:raise RuntimeError('provider returned HTTP '+str(page.status_code)+' / '+str(coord.status_code))
        savepage.write_bytes(page.content);savepage.chmod(0o600);savecoord.write_bytes(coord.content);savecoord.chmod(0o600)
    page_bytes=savepage.read_bytes();coord_bytes=savecoord.read_bytes()
    options=metadata_options(page_bytes);coordinates=pd.read_csv(io.BytesIO(coord_bytes),dtype=str,keep_default_na=False)
    data=attach_coordinates(options,coordinates)
    data['latitude']=pd.to_numeric(data.Latitude,errors='coerce');data['longitude']=pd.to_numeric(data.Longitude,errors='coerce')
    valid=data.latitude.between(-90,90)&data.longitude.between(-180,180)
    fresh=data.water_type.eq('fresh-water');known=data.possible_calendar_years_2010_2024.notna();span=data.possible_calendar_years_2010_2024.ge(4)
    data['metadata_freshwater_span_candidate']=fresh&known&span
    data.to_csv(roster,index=False);roster.chmod(0o600)
    result={'status':'metadata_only_span_screen','retrieved_utc':datetime.now(timezone.utc).isoformat(),
      'station_options':len(data),'unique_station_ids':int(data.station_id.nunique()),'duplicate_station_ids':int(data.loc[data.station_id.duplicated(keep=False),'station_id'].nunique()),'coordinate_matches':int(data.coordinate_matched.sum()),'valid_coordinate_rows':int(valid.sum()),
      'water_type_counts':data.water_type.value_counts(dropna=False).to_dict(),'station_type_code_counts':data.station_type.value_counts(dropna=False).to_dict(),
      'qa_span_dates_missing':int((~known).sum()),'freshwater_options':int(fresh.sum()),
      'freshwater_with_missing_dates':int((fresh&~known).sum()),'freshwater_with_four_possible_calendar_years':int((fresh&known&span).sum()),
      'freshwater_four_year_candidates_with_coordinates':int((fresh&known&span&valid).sum()),'freshwater_four_year_candidate_unique_ids':int(data.loc[fresh&known&span,'station_id'].nunique()),
      'no_temperature_values_requested':True,'no_predictions_scored':True,
      'interpretation':'first/last QA dates bound possible complete years only; duplicate station IDs remain separate labeled records; freshwater label can include lakes and does not prove lotic status; blank or inconsistent fields remain unresolved',
      'limitations':'site location, exact series parameter, QA definitions, real annual completeness, subdaily uniqueness, timezone, estimated values, prior-site identity and river-network independence are not established'}
    statefile.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

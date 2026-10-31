#!/usr/bin/env python3
"""Post-hoc audit of all NJDEP QA-span candidates despite inconsistent types."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Geod

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata';PRIVATE=ROOT/'private/wrr_njdep_reference_20261026'


def main():
    plan=json.loads((OUT/'water_type_amendment.json').read_text());status=json.loads((OUT/'metadata_status.json').read_text())
    if plan['status']!='posthoc_all_water_types_metadata_audit' or status['status']!='metadata_only_span_screen':raise ValueError('metadata amendment and roster required')
    data=pd.read_csv(PRIVATE/'station_metadata_roster.csv',dtype={'station_id':str,'huc14':str},keep_default_na=False)
    data['possible']=pd.to_numeric(data.possible_calendar_years_2010_2024,errors='coerce')
    candidate=data.loc[data.possible.ge(4)].copy();candidate['huc8']=candidate.huc14.str[:8]
    source=pd.read_csv(ROOT/'results/wrr_target_recovery_20261021/e1_archive/usgs_site_metadata.csv',dtype={'site_no':str,'huc_cd':str})
    source['huc8']=source.huc_cd.str.zfill(8)
    candidate['same_huc8_as_source']=candidate.huc8.isin(source.huc8)&candidate.huc8.str.fullmatch(r'\d{8}')
    candidate['exact_source_site_id']=candidate.station_id.isin(source.site_no)
    # River-like wording is only a triage indicator and can include tidal, reservoir or false matches.
    candidate['river_like_label']=candidate.label.str.contains(r'\b(?:river|creek|ck|brook|bk|stream|branch|br|run)\b',case=False,regex=True)
    geod=Geod(ellps='WGS84');q=source.dropna(subset=['dec_lat_va','dec_long_va']).copy();q['dec_lat_va']=pd.to_numeric(q.dec_lat_va);q['dec_long_va']=pd.to_numeric(q.dec_long_va)
    distances=[]
    for row in candidate.itertuples(index=False):
        lat=float(row.latitude);lon=float(row.longitude)
        _,_,d=geod.inv(np.full(len(q),lon),np.full(len(q),lat),q.dec_long_va.to_numpy(),q.dec_lat_va.to_numpy());distances.append(float(np.min(d)/1000))
    candidate['nearest_source_station_km']=distances
    target=PRIVATE/'all_water_types_span_candidates.csv'
    if target.exists():raise RuntimeError('existing candidate metadata preserved')
    candidate.to_csv(target,index=False);target.chmod(0o600)
    result={'status':'posthoc_metadata_candidates_not_reference_qualified','options_with_four_year_qa_span':len(candidate),'unique_station_ids':int(candidate.station_id.nunique()),
      'water_type_counts':candidate.water_type.value_counts(dropna=False).to_dict(),'river_like_label_options':int(candidate.river_like_label.sum()),
      'same_huc8_as_source_options':int(candidate.same_huc8_as_source.sum()),'exact_source_site_ids':int(candidate.exact_source_site_id.sum()),
      'within_10km_source_options':int(candidate.nearest_source_station_km.le(10).sum()),
      'original_freshwater_options_with_missing_span':status['freshwater_with_missing_dates'],
      'no_temperature_values_requested':True,'no_predictions_scored':True,
      'limitation':'river-like names and 4-year bounding spans do not establish freshwater type, uninterrupted deployment, 24-hour completeness, quality, no prior overlap or independent catchments; all candidate station identities require follow-up'}
    (OUT/'all_water_types_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

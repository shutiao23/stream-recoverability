#!/usr/bin/env python3
"""Inspect field dataset site/time/method metadata without reading values."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_field_checks'
PRIVATE=ROOT/'private/wrr_nova_scotia_field_checks_20261027'
DATA=PRIVATE/'nova_scotia_field_v6.csv'
COLUMNS=['MonitoringLocationID','MonitoringLocationName','MonitoringLocationLatitude','MonitoringLocationLongitude',
         'MonitoringLocationHorizontalCoordinateReferenceSystem','MonitoringLocationHorizontalAccuracyMeasure',
         'MonitoringLocationHorizontalAccuracyUnit','MonitoringLocationType','ActivityType','ActivityMediaName',
         'ActivityStartDate','ActivityStartTime','ActivityStartTimeZone','ActivityEndDate','ActivityEndTime',
         'ActivityEndTimeZone','SampleCollectionEquipmentName','CharacteristicName','ResultUnit','ResultValueType',
         'ResultDetectionCondition','ResultStatusID','ResultAnalyticalMethodID','ResultAnalyticalMethodContext','ResultAnalyticalMethodName']

def main():
    acquisition=json.loads((OUT/'acquisition.json').read_text());plan=json.loads((OUT/'plan.json').read_text())
    if not str(acquisition['status']).startswith('downloaded'):raise ValueError('Field-source acquisition incomplete')
    parts=[];total=0
    for chunk in pd.read_csv(DATA,usecols=COLUMNS,dtype=str,keep_default_na=False,chunksize=50000):
        total+=len(chunk);parts.append(chunk)
    f=pd.concat(parts,ignore_index=True)
    locations=f[['MonitoringLocationID','MonitoringLocationName','MonitoringLocationLatitude','MonitoringLocationLongitude',
                 'MonitoringLocationHorizontalCoordinateReferenceSystem','MonitoringLocationHorizontalAccuracyMeasure',
                 'MonitoringLocationHorizontalAccuracyUnit','MonitoringLocationType']].drop_duplicates()
    if locations.MonitoringLocationID.eq('').any():raise ValueError('Field data contain unidentified locations')
    destination=PRIVATE/'site_metadata.csv'
    locations.sort_values(['MonitoringLocationID','MonitoringLocationName']).to_csv(destination,index=False);destination.chmod(0o600)
    matched=locations[locations.MonitoringLocationName.str.contains('kelley|margaree',case=False,regex=True)]
    ids=set(matched.MonitoringLocationID);subset=f[f.MonitoringLocationID.isin(ids)].copy()
    subset['year']=pd.to_datetime(subset.ActivityStartDate,errors='coerce').dt.year
    subset=subset[subset.year.between(2009,2017)]
    def counts(column):return subset[column].replace('', '<missing>').value_counts().head(30).to_dict()
    state={'status':'metadata_screen_complete','total_dataset_rows':total,'location_metadata_rows':len(locations),
           'locations_with_kelley_or_margaree_name':len(matched),'candidate_location_ids':len(ids),
           'candidate_period_metadata_rows':len(subset),'candidate_characteristics':counts('CharacteristicName'),
           'timezones':counts('ActivityStartTimeZone'),'collection_equipment':counts('SampleCollectionEquipmentName'),
           'result_status':counts('ResultStatusID'),'result_units':counts('ResultUnit'),
           'candidate_time_labels_present':int(subset.ActivityStartTime.ne('').sum()),
           'candidate_time_labels_absent':int(subset.ActivityStartTime.eq('').sum()),
           'columns_read':COLUMNS,'result_values_read':False,
           'limitations':'Name and coordinate metadata are candidate matches, not proof of same sensor, sample identity, clock alignment or independent data quality. Counts include non-temperature fields and repeated attributes.'}
    (OUT/'metadata_status.json').write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n')
    print(matched[['MonitoringLocationID','MonitoringLocationName','MonitoringLocationLatitude','MonitoringLocationLongitude']].to_string(index=False))
    print(json.dumps(state,indent=2,ensure_ascii=False))

if __name__=='__main__':main()

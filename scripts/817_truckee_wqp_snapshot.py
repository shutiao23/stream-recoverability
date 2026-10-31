#!/usr/bin/env python3
"""Stage a minimal same-agency WQP field snapshot for local review."""
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';WQP=PRIVATE/'wqp_same_site';SNAP=ROOT/'data/external/wrr_truckee_dwr_20261027/wqp_field_snapshot'
FIELDS=['OrganizationIdentifier','MonitoringLocationIdentifier','ActivityIdentifier','ActivityStartDate','ActivityStartTime/Time',
        'ActivityStartTime/TimeZoneCode','ActivityTypeCode','CharacteristicName','ResultMeasureValue','ResultMeasure/MeasureUnitCode',
        'ResultStatusIdentifier','ResultValueTypeName','MeasureQualifierCode','ResultAnalyticalMethod/MethodIdentifier',
        'ResultAnalyticalMethod/MethodIdentifierContext','ResultAnalyticalMethod/MethodName']

def main():
    audit=json.loads((OUT/'wqp_field_independent_audit.json').read_text());status=json.loads((OUT/'wqp_field_comparison_status.json').read_text())
    plan=json.loads((OUT/'wqp_same_site_plan.json').read_text());receipt=WQP/'acquisition.json'
    if audit['status']!='passed' or status['status']!='computed_posthoc' or audit['comparable_rows_recomputed']!=status['comparable_rows']:
        raise ValueError('Field comparison audit incomplete')
    acquisition=json.loads((OUT/'wqp_same_site_acquisition.json').read_text())
    frames=[];sources=[]
    for item in json.loads(receipt.read_text()):
        if item['status']=='completed_empty':sources.append({'year':item['year'],'rows':0,'http_status':item['http_status']});continue
        if item['status']!='completed':raise ValueError('WQP acquisition incomplete')
        path=WQP/f"{item['year']}.csv.gz"
        with gzip.open(path,'rb') as f:raw=f.read()
        frame=pd.read_csv(path,compression='gzip',dtype=str,usecols=FIELDS).fillna('')
        if len(frame)!=item['rows'] or not frame.MonitoringLocationIdentifier.eq(plan['wqp_site_id']).all():raise ValueError('WQP source identity differs')
        frames.append(frame[FIELDS]);sources.append({'year':item['year'],'rows':len(frame),'http_status':item['http_status'],
            'retrieved_utc_file_mtime':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()})
    f=pd.concat(frames,ignore_index=True)
    if len(f)!=status['wqp_rows']:raise ValueError('WQP row count differs')
    SNAP.mkdir(parents=True,exist_ok=True);file=SNAP/'field_results_minimal.csv'
    if file.exists():raise FileExistsError('Preserve existing WQP field snapshot')
    f.to_csv(file,index=False)
    station=pd.read_csv(PRIVATE/'wqp_station_metadata.csv',dtype=str).fillna('')
    station=station[station.MonitoringLocationIdentifier.eq(plan['wqp_site_id'])]
    fields=['OrganizationIdentifier','OrganizationFormalName','MonitoringLocationIdentifier','MonitoringLocationName','MonitoringLocationTypeName',
            'LatitudeMeasure','LongitudeMeasure','HorizontalCoordinateReferenceSystemDatumName','HUCEightDigitCode','ProviderName']
    if len(station)!=1 or not set(fields).issubset(station.columns):raise ValueError('WQP station metadata ambiguous')
    sf=SNAP/'station_metadata_minimal.csv';station[fields].to_csv(sf,index=False)
    manifest={'created_utc':datetime.now(timezone.utc).isoformat(),
        'endpoint':'https://www.waterqualitydata.us/data/Result/search','station_page':'https://www.waterqualitydata.us/provider/STORET/CALWR_WQX/CALWR_WQX-G7166310/',
        'query':{'siteid':plan['wqp_site_id'],'characteristicName':'Temperature, water','years':plan['years'],'mimeType':'csv','sorted':'no'},
        'sources':sources,'field_results':{'file':file.name,'rows':len(f),'columns':FIELDS},
        'station_metadata':{'file':sf.name,},
        'content_note':'Selected 16 fields copied without numerical transformation from all returned field rows; original full WQP responses remain local. The 2020 response had no rows.',
        'rights_note':'WQP labels the source California DWR. The California catalog describes its DWR-collected discrete water-quality dataset as public domain; an exact record-level crosswalk from this WQP feed to that catalog was not independently established. This is a local candidate; confirm source terms before permanent public deposit.',
        'limitations':'Same station and provider as the logger; instrument identity, field protocol, sensor clock, spatial offset and data-processing overlap are not verified.'}
    (SNAP/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (SNAP/'ATTRIBUTION.txt').write_text('Source: California Department of Water Resources (CALWR_WQX), Truckee River @ Bridge 8/SquawCr, via the Water Quality Portal (WQP), accessed 2026-10-27: https://www.waterqualitydata.us/provider/STORET/CALWR_WQX/CALWR_WQX-G7166310/\nCalifornia DWR describes its separate discrete water-quality dataset as public domain: https://publish.data.ca.gov/dataset/water-quality-data. The record-level crosswalk to this WQP feed has not been independently established; confirm terms before permanent deposit.\nThis reduced snapshot preserves only fields needed for the same-agency field comparison and omits the full source response.\n')
    print('Staged 60 minimal WQP field rows and source attribution for local review')

if __name__=='__main__':main()

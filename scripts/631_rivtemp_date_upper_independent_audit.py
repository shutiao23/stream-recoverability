#!/usr/bin/env python3
"""Independently recount all date-label bounds with Arrow rather than pandas."""
from __future__ import annotations
import calendar
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.csv as acsv

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_rivtemp_metadata';PRIVATE=ROOT/'private/wrr_rivtemp_reference_20261026'

def audit_dataset(source,roster,scopes):
    ids=set(pd.read_csv(roster,usecols=['MonitoringLocationID'],dtype=str).MonitoringLocationID)
    opts=acsv.ConvertOptions(include_columns=['MonitoringLocationID','ActivityStartDate'],column_types={'MonitoringLocationID':pa.string(),'ActivityStartDate':pa.string()})
    reader=acsv.open_csv(source,read_options=acsv.ReadOptions(block_size=4*1024*1024),convert_options=opts)
    labels=defaultdict(set);n=0
    for batch in reader:
        sites=batch.column(0).to_pylist();dates=batch.column(1).to_pylist();n+=len(sites)
        for site,raw in zip(sites,dates):
            if site not in ids:raise ValueError('source identity outside frozen roster')
            try:d=date.fromisoformat(raw)
            except (ValueError,TypeError):raise ValueError('invalid source date label') from None
            labels[(site,d.year)].add(d)
    checked=0
    for name,years,table_path in scopes:
        saved=pd.read_csv(table_path,dtype={'MonitoringLocationID':str})
        if len(saved)!=len(ids)*len(years) or saved.duplicated(['MonitoringLocationID','year']).any():raise ValueError('saved date roster shape differs')
        if set(saved.MonitoringLocationID)!=ids or set(saved.year)!=set(years):raise ValueError('saved location or years differ')
        for r in saved.itertuples(index=False):
            nlabels=len(labels[(r.MonitoringLocationID,r.year)]);days=366 if calendar.isleap(r.year) else 365
            if nlabels!=r.distinct_labels or days!=r.calendar_days or (nlabels==days)!=bool(r.could_be_complete_by_label):raise ValueError('independent date-label recount mismatch')
            checked+=1
    return {'source_rows':n,'location_ids':len(ids),'station_year_rows_independently_verified':checked,'scopes':len(scopes)}

def main():
    acquisition=json.loads((OUT/'acquisition.json').read_text());plan=json.loads((OUT/'partner_screen_plan.json').read_text());report=[]
    source=PRIVATE/'rivtemp_mffp_v1.csv'
    report.append({'dataset':'MFFP'}|audit_dataset(source,PRIVATE/'all_locations_before_qualification.csv',[
      ('2010-2020',range(2010,2021),PRIVATE/'possible_label_years.csv'),('1985-2021',range(1985,2022),PRIVATE/'expanded_possible_label_years.csv')]))
    for ds in plan['datasets']:
        source=PRIVATE/(ds['id']+'_'+ds['version']+'.csv');roster=PRIVATE/(ds['id']+'_all_locations.csv')
        scopes=[('2010-2020',range(2010,2021),PRIVATE/(ds['id']+'_fixed_forward_2010_2020_possible_years.csv')),
          ('full_published_period',range(ds['metadata_years'][0],ds['metadata_years'][1]+1),PRIVATE/(ds['id']+'_published_period_possible_years.csv'))]
        report.append({'dataset':ds['name']}|audit_dataset(source,roster,scopes))
    status={'status':'passed_independent_arrow_date_recount','datasets':report,'fields_parsed':['MonitoringLocationID','ActivityStartDate'],
      'limitation':'recount checks date labels and frozen identifiers only; does not assess temperatures, quality, complete 24-hour observations, time-zone alignment or hydrologic independence'}
    (OUT/'independent_date_audit.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Find an optimistic upper bound on complete-year reference availability.

Uses only frozen station IDs and activity date labels. A label is not proof of a
finite or approved temperature, an observed 24-hour day or correct time basis.
The strict sample must be a subset of this optimistic upper bound.
"""
import calendar
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_rivtemp_metadata';PRIVATE=ROOT/'private/wrr_rivtemp_reference_20261026'
YEARS=list(range(2010,2021))

def upper_bound(dates,roster,years=YEARS):
    frame=dates.copy();frame['date']=pd.to_datetime(frame.ActivityStartDate,errors='coerce',format='%Y-%m-%d')
    if frame.date.isna().any():raise ValueError('unparseable activity date needs explicit audit')
    if not frame.MonitoringLocationID.isin(roster.MonitoringLocationID).all():raise ValueError('date rows contain station outside frozen roster')
    frame['year']=frame.date.dt.year;frame=frame.loc[frame.year.isin(years)]
    counts=frame.groupby(['MonitoringLocationID','year']).date.nunique().rename('distinct_labels').reset_index()
    grid=pd.MultiIndex.from_product([roster.MonitoringLocationID,years],names=['MonitoringLocationID','year']).to_frame(index=False)
    table=grid.merge(counts,on=['MonitoringLocationID','year'],how='left',validate='one_to_one');table['distinct_labels']=table.distinct_labels.fillna(0).astype(int)
    table['calendar_days']=table.year.map(lambda y:366 if calendar.isleap(y) else 365)
    if (table.distinct_labels>table.calendar_days).any():raise ValueError('date count exceeds calendar year')
    table['could_be_complete_by_label']=table.distinct_labels.eq(table.calendar_days)
    station=table.groupby('MonitoringLocationID',as_index=False).could_be_complete_by_label.sum().rename(columns={'could_be_complete_by_label':'possible_complete_label_years'})
    station['at_least_four_possible_years']=station.possible_complete_label_years.ge(4)
    station=station.merge(roster[['MonitoringLocationID','MonitoringLocationLatitude','MonitoringLocationLongitude']],on='MonitoringLocationID',validate='one_to_one')
    return table,station

def main():
    roster_state=json.loads((OUT/'roster_freeze.json').read_text());prior=json.loads((OUT/'prior_contact_status.json').read_text())
    if roster_state['status']!='all_location_metadata_frozen_before_qualification' or prior['status']!='metadata_screen_completed_not_network_qualified':raise ValueError('freeze and prior-contact audit required')
    target=PRIVATE/'possible_label_years.csv';sitefile=PRIVATE/'possible_label_years_by_location.csv';statusfile=OUT/'date_label_upper_bound.json'
    if target.exists() or sitefile.exists() or statusfile.exists():raise RuntimeError('existing screening output preserved')
    source=PRIVATE/'rivtemp_mffp_v1.csv';
    with source.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    roster=pd.read_csv(PRIVATE/'all_locations_before_qualification.csv',dtype=str,keep_default_na=False)
    if roster.MonitoringLocationID.duplicated().any():raise ValueError('unresolved location metadata changes')
    dates=pd.read_csv(source,usecols=['MonitoringLocationID','ActivityStartDate'],dtype=str,keep_default_na=False)
    table,site=upper_bound(dates,roster);table.to_csv(target,index=False);target.chmod(0o600);site.to_csv(sitefile,index=False);sitefile.chmod(0o600)
    selected=site.loc[site.at_least_four_possible_years]
    state={'status':'date_label_upper_bound_only','calendar_years':YEARS,'n_roster_ids':len(roster),
      'n_station_years_possible_by_label':int(table.could_be_complete_by_label.sum()),
      'n_station_ids_four_possible_years':int(len(selected)),
      'n_distinct_coordinate_pairs_four_possible_years':int(len(selected[['MonitoringLocationLatitude','MonitoringLocationLongitude']].drop_duplicates())),
      'date_parse_errors':0,'source_columns_read':['MonitoringLocationID','ActivityStartDate'],
      'scope':'upper bound based on complete sets of calendar-date labels, before examining water values, result status, timestamps or interval counts; activity dates are not guaranteed 24-hour days',
      'quality':'does not establish finite or approved temperatures, subdaily completeness, no estimated values, day boundary, upstream catchment independence or model accuracy',
      'local_only_case_tables':['private/wrr_rivtemp_reference_20261026/possible_label_years.csv','private/wrr_rivtemp_reference_20261026/possible_label_years_by_location.csv']}
    statusfile.write_text(json.dumps(state,indent=2)+'\n');print(json.dumps(state,indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Post-hoc full published-period date-label availability upper bound."""
import json
from pathlib import Path
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_rivtemp_metadata';PRIVATE=ROOT/'private/wrr_rivtemp_reference_20261026'


def main():
    prior=json.loads((OUT/'date_label_upper_bound.json').read_text());plan=json.loads((OUT/'expanded_year_amendment.json').read_text())
    if prior['n_station_ids_four_possible_years']!=0 or plan['status']!='posthoc_year_range_amendment_before_model_scoring':raise ValueError('original screening and amendment required')
    source=PRIVATE/'rivtemp_mffp_v1.csv';out=OUT/'expanded_date_label_upper_bound.json'
    local1=PRIVATE/'expanded_possible_label_years.csv';local2=PRIVATE/'expanded_possible_label_years_by_location.csv'
    if out.exists() or local1.exists() or local2.exists():raise ValueError('existing amended screen preserved')
    roster=pd.read_csv(PRIVATE/'all_locations_before_qualification.csv',dtype=str,keep_default_na=False)
    dates=pd.read_csv(source,usecols=['MonitoringLocationID','ActivityStartDate'],dtype=str,keep_default_na=False)
    mod=T.load_script('rivtemp_year_upper_bound',ROOT/'scripts/628_rivtemp_metadata_year_upper_bound.py')
    table,site=mod.upper_bound(dates,roster,years=list(range(1985,2022)))
    table.to_csv(local1,index=False);local1.chmod(0o600);site.to_csv(local2,index=False);local2.chmod(0o600)
    selected=site.loc[site.at_least_four_possible_years]
    report={'status':'posthoc_date_label_upper_bound_only','years':'1985-2021 inclusive','n_roster_ids':len(roster),
      'n_station_years_possible_by_label':int(table.could_be_complete_by_label.sum()),'n_station_ids_four_possible_years':len(selected),
      'n_distinct_coordinate_pairs_four_possible_years':len(selected[['MonitoringLocationLatitude','MonitoringLocationLongitude']].drop_duplicates()),
      'no_source_temperature_values_or_model_predictions_read':True,
      'limitation':'post-hoc response to the original 2010-2020 zero; labels do not prove full observed days, approved values, sensor quality, 24-hour boundaries or independent catchments'}
    out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()

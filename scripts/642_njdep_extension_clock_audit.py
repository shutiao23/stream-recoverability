#!/usr/bin/env python3
"""Timestamp-only screen and independent recount for the NJDEP extension."""
from pathlib import Path
import json
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_njdep_metadata';PRIVATE=ROOT/'private/wrr_njdep_reference_20261026';DATA=PRIVATE/'station_year_csv'

def main():
 plan=json.loads((OUT/'subdaily_extension_plan.json').read_text());acq=json.loads((OUT/'subdaily_extension_acquisition.json').read_text());status=OUT/'subdaily_extension_clock_status.json';local=PRIVATE/'timestamp_extension_year_summary.csv'
 if acq['status']!='posthoc_extension_files_acquired' or status.exists() or local.exists():raise ValueError('extension acquisition required; previous screen preserved')
 primary=T.load_script('njdep_extension_clock_primary',ROOT/'scripts/639_njdep_timestamp_qualification.py');independent=T.load_script('njdep_extension_clock_independent',ROOT/'scripts/640_njdep_independent_clock_audit.py')
 rows=[];zones=set();fields=['Station','Date_Time','Date_Time_TZ','Submission ID']
 for site in plan['stations']:
  for year in plan['years']:
   path=DATA/f'{site}_{year}.csv';receipt=json.loads((DATA/f'{site}_{year}.json').read_text())
   frame=pd.read_csv(path,usecols=fields,dtype=str,keep_default_na=False)
   if len(frame) and not frame.Station.eq(site).all():raise ValueError('extension station identity differs')
   zones.update(frame.Date_Time_TZ.unique());result=primary.screen_clock(frame,year);check=independent.independent_clock(path,site,year)
   for k,v in check.items():
    if int(result[k])!=v:raise ValueError('independent extension recount differs: '+k)
   rows.append({'site':site,'year':year}|result)
 table=pd.DataFrame(rows);table.to_csv(local,index=False);local.chmod(0o600)
 groups=table.groupby('site').date_label_complete_possible.apply(lambda x:int(x.eq(True).sum()))
 result={'status':'posthoc_extension_clock_independently_recounted','station_year_files':len(table),'stations':len(groups),
   'station_years_missing_reported_dates':int(table.status.eq('reported_date_labels_incomplete').sum()),
   'station_years_unparseable_clock':int(table.status.eq('unparseable_time_unknown').sum()),
   'station_years_requiring_further_quality_review':int(table.status.eq('requires_subdaily_and_quality_review').sum()),
   'stations_with_four_possible_label_years':int(groups.ge(4).sum()),
   'minimum_missing_date_labels':int(table.days_with_no_reported_time.min()),'maximum_missing_date_labels':int(table.days_with_no_reported_time.max()),
   'provider_time_zone_labels':sorted(map(str,zones)),'independent_arrow_recount_passed':True,
   'temperature_values_or_model_errors_examined':False,
   'limitation':'post-hoc two-site selection; reported-clock dates do not prove physical time basis, full subdaily measurement, nonestimated values, quality flags, sensor equivalence or independent watersheds'}
 status.write_text(json.dumps(result,indent=2)+'\n');print(table[['site','year','days_with_any_reported_time','days_with_no_reported_time','status']].to_string(index=False));print(json.dumps(result,indent=2))
if __name__=='__main__':main()

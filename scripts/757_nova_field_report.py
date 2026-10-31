#!/usr/bin/env python3
"""Render the explicitly nonconfirmatory field-versus-hourly diagnostic."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_nova_field_checks';PAPER=ROOT/'paper/wrr_tr'


def one(frame,**where):
    for col,val in where.items():frame=frame[frame[col].eq(val)]
    if len(frame)!=1:raise ValueError('Missing field diagnostic row: '+str(where))
    return frame.iloc[0]


def main():
    status=json.loads((OUT/'status.json').read_text());audit=json.loads((OUT/'independent_audit.json').read_text())
    near=json.loads((OUT/'hour_membership_status.json').read_text())
    if (status['status']!='computed_exploratory' or near['status']!='computed_posthoc' or audit['status']!='passed'
            or audit['reported_day_range_rows_rechecked']!=18 or audit['hour_proximity_rows_rechecked']!=18
            or status['site_date_multiplicity']!={'2':status['distinct_site_dates']}
            or status['site_dates_with_multiple_distinct_numeric_values']!=0
            or status['field_status_counts']!={'Preliminary':status['field_rows']} or status['time_label_present']!=0
            or not audit.get('all_nonvalue_metadata_equal_within_each_site_date')):
        raise ValueError('Field comparison or independent arithmetic audit incomplete')
    all_range=pd.read_csv(OUT/'range_summary.csv');selected=pd.read_csv(OUT/'selected_year_range_summary.csv')
    proximity=pd.read_csv(OUT/'hour_membership_summary.csv')
    a=one(all_range,scope='all_2009_2017',site='both_sites',window='same_day')
    b=one(selected,scope='modeled_years',site='both_sites',window='same_day')
    ap=one(proximity,scope='all',site='both_sites',window='single')
    bp=one(proximity,scope='modeled_years',site='both_sites',window='single')
    if a.compared_site_dates!=ap.compared_site_dates or b.compared_site_dates!=bp.compared_site_dates:
        raise ValueError('Range and proximity event denominators differ')
    vals={'NSFieldRows':str(status['field_rows']),'NSFieldDates':str(status['distinct_site_dates']),
          'NSFieldAllCompared':str(int(a.compared_site_dates)),
          'NSFieldAllWithin':str(int(a.compared_site_dates-a.site_dates_any_outside)),
          'NSFieldSelectedCompared':str(int(b.compared_site_dates)),
          'NSFieldSelectedWithin':str(int(b.compared_site_dates-b.site_dates_any_outside)),
          'NSFieldSelectedExact':str(int(bp.site_dates_within_1e_6_c)),
          'NSFieldMaxExcess':f'{b.maximum_range_excess_c:.2f}'}
    (PAPER/'nova_field_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    text=r'''\section{Nova Scotia field values and reported hourly ranges}
After the portal comparisons and model errors were inspected, we obtained a public field-sample dataset from the same provincial monitoring programme (\url{https://doi.org/10.25976/sfmj-kf56}). For the same two rivers and 2009--2017 there are \NSFieldRows{} water-temperature rows on \NSFieldDates{} reported station-dates: each date has two rows with identical metadata and numerical values. We do not know whether they represent duplicate records or separate sampling events. All are labelled preliminary and have no recorded sample time or time zone. Dataset metadata describes co-location with automated probes, but does not establish separate instruments, physical clock alignment or point-level quality.

We compare each field value with the minimum and maximum of the 24 distinct finite portal hours bearing the same reported date, without filling incomplete hours. On \NSFieldAllCompared{} station-dates with an available range, values lie inside it on \NSFieldAllWithin{}. In the previously selected eight model-evaluation station-years, all \NSFieldSelectedCompared{} field dates have a 24-hour reported-label range and \NSFieldSelectedWithin{} lie inside; the largest excess is \NSFieldMaxExcess{} $^{\circ}$C. This is not a synchronous comparison: an untimed field value can fall outside the sampled hourly extrema, and an unknown day boundary can change date matching. Pooling the preceding, same and following reported dates gives a much wider, three-day range, not a physical-day uncertainty interval.

After viewing the range result, we also searched all hourly values on each reported date: on \NSFieldSelectedExact{} of the \NSFieldSelectedCompared{} selected station-dates the field value equals at least one hourly value within $10^{-6}$ $^{\circ}$C. Searching 24 values gives many opportunities for accidental agreement and does not show simultaneous sampling or common/separate sensors. A separate CSV/datetime implementation reproduces all 18 range-summary and 18 proximity-summary cells using the same source files. The field records' preliminary status, absent clock, possible equipment dependence and provider quality procedures remain unresolved. None of these counts upgrades the two sites to strict independent references, establishes physical sensor accuracy, or validates H30 recovery.
'''
    (PAPER/'nova_field_supporting.tex').write_text(text)
    print('Rendered reported-day field diagnostic')


if __name__=='__main__':main()

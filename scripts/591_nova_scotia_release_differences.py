#!/usr/bin/env python3
"""Post-hoc magnitude and year diagnostics for two provincial data releases."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified'
WORKBOOKS=ROOT/'private/wrr_nova_scotia_verified_20261026'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def profile(workbook,portal,thresholds):
    w=workbook.dropna(subset=['timestamp']).copy();p=portal.dropna(subset=['timestamp']).copy()
    w=w.loc[~w.timestamp.duplicated(keep=False)];p=p.loc[~p.timestamp.duplicated(keep=False)]
    m=w.merge(p,on='timestamp',how='outer',suffixes=('_workbook','_portal'),indicator=True,validate='one_to_one')
    m['year']=m.timestamp.dt.year
    rows=[]
    for year,g in m.groupby('year',sort=True):
        both=g.loc[g._merge.eq('both')];a=both.value_workbook.to_numpy(float);b=both.value_portal.to_numpy(float)
        good=np.isfinite(a)&np.isfinite(b);delta=np.abs(a[good]-b[good])
        row={'year':int(year),'shared_unique_labels':len(both),'both_numeric':int(good.sum()),
             'workbook_only_unique_labels':int(g._merge.eq('left_only').sum()),'portal_only_unique_labels':int(g._merge.eq('right_only').sum()),
             'one_numeric_other_missing':int((np.isfinite(a)^np.isfinite(b)).sum()),
             'maximum_abs_difference_c':float(delta.max()) if len(delta) else np.nan}
        for threshold in thresholds:row['difference_gt_'+str(threshold).replace('.','p')]=int((delta>threshold).sum())
        rows.append(row)
    return pd.DataFrame(rows)

def main():
    plan=json.loads((OUT/'portal_difference_diagnostic_plan.json').read_text())
    portal=json.loads((OUT/'portal_acquisition.json').read_text());workbooks=json.loads((OUT/'acquisition.json').read_text())
    old=pd.read_csv(OUT/'portal_workbook_comparison.csv');m=load('portal_comparison',ROOT/'scripts/590_nova_scotia_portal_audit.py')
    rows=[]
    for item in workbooks['files']:
        p=WORKBOOKS/item['workbook']
        w,n=m.workbook_records(p);v,n2=m.portal_records(item['station_id'],portal['pages'])
        if n or n2:raise ValueError('unparsed time labels prevent cross-check')
        table=profile(w,v,plan['thresholds_c']);table['station_id']=item['station_id'];rows.append(table)
    result=pd.concat(rows,ignore_index=True)
    for station,g in result.groupby('station_id'):
        reference=old.loc[old.station_id.eq(station)]
        if len(reference)!=1:raise ValueError('missing station comparison')
        row=reference.iloc[0]
        for field in ['shared_unique_labels','both_numeric','workbook_only_unique_labels','portal_only_unique_labels','one_numeric_other_missing']:
            if int(g[field].sum())!=int(row[field]):raise ValueError(f'year profiles disagree with initial comparison: {station}/{field}')
        if int(g['difference_gt_1e-06'].sum())!=int(row.numeric_different):raise ValueError('initial tolerance mismatch')
    result.to_csv(OUT/'portal_difference_by_year.csv',index=False)
    fields=[x for x in result.columns if x.startswith('difference_gt_')]
    station=result.groupby('station_id')[['shared_unique_labels','both_numeric','workbook_only_unique_labels','portal_only_unique_labels']+fields].sum().reset_index()
    station.to_csv(OUT/'portal_difference_by_station.csv',index=False)
    w=pd.read_csv(OUT/'reported_label_completeness.csv');p=pd.read_csv(OUT/'portal_label_completeness.csv')
    c=w[['station_id','year','complete_label_year']].merge(p[['station_id','year','complete_label_year']],on=['station_id','year'],suffixes=('_workbook','_portal'),validate='one_to_one')
    c.to_csv(OUT/'complete_label_year_overlap.csv',index=False)
    report={'status':'passed','stations':len(station),'site_years':len(result),'both_numeric':int(result.both_numeric.sum()),
       'difference_gt_1e-06':int(result['difference_gt_1e-06'].sum()),'difference_gt_0p01':int(result['difference_gt_0p01'].sum()),
       'difference_gt_0p1':int(result['difference_gt_0p1'].sum()),'difference_gt_0p5':int(result['difference_gt_0p5'].sum()),
       'maximum_abs_difference_c':float(result.maximum_abs_difference_c.max()),
       'year_pairs_both_complete_labels':int((c.complete_label_year_workbook&c.complete_label_year_portal).sum()),
       'year_pairs_only_workbook_complete_labels':int((c.complete_label_year_workbook&~c.complete_label_year_portal).sum()),
       'year_pairs_only_portal_complete_labels':int((~c.complete_label_year_workbook&c.complete_label_year_portal).sum()),
       'limitation':'post-hoc descriptive thresholds, different releases of one programme, no independent sensor comparison, unverified timezone and per-observation QA; duplicate labels excluded, not averaged'}
    (OUT/'portal_difference_status.json').write_text(json.dumps(report,indent=2)+'\n')
    print(station.to_string(index=False));print(json.dumps(report,indent=2))

if __name__=='__main__':main()

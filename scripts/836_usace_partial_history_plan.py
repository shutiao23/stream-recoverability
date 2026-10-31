#!/usr/bin/env python3
"""Freeze a post-hoc partial-history evaluation before new model predictions."""
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir'
PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027';DATA=ROOT/'data/external/wrr_usace_reservoir_20261027'
SOURCE=ROOT/'results/wrr_review_completion_20261024'

def main():
    dest=OUT/'partial_history_evaluation_plan.json'
    if dest.exists():raise FileExistsError('Preserve existing evaluation plan')
    for name in ['partial_year_bounds_independent_audit.json','partial_year_record_screen_independent_audit.json']:
        if json.loads((OUT/name).read_text())['status']!='passed':raise ValueError('Prior bound audit missing')
    engine=T.load_script('usace_partial_history_plan_engine',ROOT/'scripts/835_usace_partial_history_engine.py')
    daily=pd.read_parquet(DATA/'finite_daily.parquet');daily['day']=pd.to_datetime(daily.day)
    meta=pd.read_csv(PRIVATE/'roster.csv').set_index('resource_id')
    annual=pd.read_csv(OUT/'finite_reference_years.csv')
    if annual.loc[annual.year.between(2021,2025),'finite_reference_year'].any():
        raise ValueError('Expected no complete target or history year')
    manifest=json.loads((DATA/'manifest.json').read_text());rows=[]
    for item in manifest['records']:
        rid=item['resource_id'];obs=daily[daily.resource_id.eq(rid)].set_index('day').mean_c
        good=[]
        for year in range(2021,2026):
            s=obs.reindex(pd.date_range(f'{year}-01-01',f'{year}-12-31'))
            if engine.history_qualifies(s):good.append(year)
        for target in range(2021,2026):
            s=obs.reindex(pd.date_range(f'{target}-01-01',f'{target}-12-31'))
            histories=[y for y in good if y!=target]
            if len(histories)>=3 and s.notna().sum()>=30:
                rows.append({'resource_id':rid,'year':target,'history_years':';'.join(map(str,histories)),
                  'reported_target_complete_days':int(s.notna().sum()),'actual_complete_history_years':0,
                  'latitude':float(meta.loc[rid,'latitude']),'longitude':float(meta.loc[rid,'longitude']),
                  'gage_ids':meta.loc[rid,'gage_ids']})
    cohort=pd.DataFrame(rows);cohort=cohort.sort_values(['resource_id','year']).reset_index(drop=True)
    path=PRIVATE/'partial_history_roster.csv';cohort.to_csv(path,index=False);path.chmod(0o600)
    files=[DATA/'finite_daily.parquet',DATA/'partial_year_h30_bounds.csv',DATA/'manifest.json',OUT/'finite_reference_years.csv',
      SOURCE/'deployment/global_source_candidate.joblib',SOURCE/'independent_study/source_case_settings.json',
      SOURCE/'independent_study/source_missingness_generator.json',ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json',
      ROOT/'scripts/431_tr_cases.py',ROOT/'scripts/495_review_completion_independent_analysis.py',ROOT/'scripts/wrr_tr_features.py',
      ROOT/'scripts/835_usace_partial_history_engine.py',ROOT/'scripts/837_usace_partial_history_forcing.py',
      ROOT/'scripts/838_usace_partial_history_predict.py',Path(__file__)]
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
      'status':'posthoc cohort and evaluation design fixed after target availability and conditional H30 bounds were inspected; before this model prediction or model-error evaluation',
      'cohort':'All ten previously screened resources and 2021-2025 target years; retain any target with at least 30 observed complete days and at least three other history years meeting the rule. Do not select by target H30 value, interval width, model output or model errors.',
      'history_rule':'Other calendar years have >=75% fully observed days, no missing endpoint, and longest missing run <=45 days. Within each selected history year linearly interpolate missing daily values using only that year. Original complete-year counts remain 0 and are not recoded as observed. Rule and data are posthoc, the 45-day limit is a sensitivity choice, not a quality guarantee.',
      'target_mask':'Leave evaluated calendar year out of all local training. Natural missing daily values and every additional synthetic mask day are both hidden; missing target-day placeholders are never used as observations or truth. Generate existing controlled 30/60/90-day masks with existing seed streams, no donor stations. No target interpolation is used as reference.',
      'source':'Previously fixed global annual source model and source-only calibration; annual model is not refitted on target. Actual complete history count supplied as 0, outside the original >=4 complete-year input regime. This is an adaptation, not the original complete-history protocol.',
      'weather':'NASA POWER daily T2M at source coordinates rounded to 0.01 degrees, 2021-2025 local solar time. Alignment with fixed-MST water days is an assumption and must remain disclosed.',
      'scoring':'Retain all cohort cases and all bounded references. For each point prediction p and H30 reference interval [L,U], score absolute error within [max(L-p,0,p-U), max(abs(p-L),abs(p-U))]; coverage of predicted interval is definitely true if it contains [L,U], possibly true if intervals intersect. Report both limits and availability; no midpoint truth. Separately describe the already-seen width<=0.1 C subset as posthoc and use paired available cases.',
      'dependencies':'Water quality/corrections, missing-slot range assumption, source overlap and independent climates unresolved. Upstream and downstream sites are dependent. The target-derived bounds and source-visible history have been examined in prior work, so this is not a prospective, independent confirmation.',
      'no_trend_or_risk_guarantee':True,'cohort_station_years':len(cohort),'cohort_resources':int(cohort.resource_id.nunique()),
      }
    dest.write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps({'cohort_station_years':len(cohort),'cohort_resources':int(cohort.resource_id.nunique()),'status':plan['status']},indent=2))

if __name__=='__main__':main()

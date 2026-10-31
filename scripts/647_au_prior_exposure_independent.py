#!/usr/bin/env python3
"""Independent Arrow/Python recount of earlier Australian target overlap."""
import csv
from collections import defaultdict
from datetime import datetime,date
import json
import math
from pathlib import Path
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/audit';FOLLOW=ROOT/'results/wrr_submission_ready/followup_20261021/au_confirmation'
R1=ROOT/'results/wrr_target_recovery_20261021/e7_sealed/cases.parquet';R2=ROOT/'results/wrr_target_recovery_20261022/e7_au_development/cases.parquet'


def eligible(row):
 def present(x):return x is not None and not (isinstance(x,float) and math.isnan(x))
 return row['policy_choice']!='unavailable' and present(row['state_h30_q50']) and present(row['eval_truth_h30'])


def main():
 refs=[]
 with (FOLLOW/'observed_reference_release.csv').open(newline='',encoding='utf8') as f:
  for r in csv.DictReader(f):
   if r['observed_sampling_reference_eligible']=='True':refs.append((r['station_id'],int(r['year']),r['role']))
 if len(set((s,y) for s,y,_ in refs))!=len(refs):raise ValueError('duplicate reference station/year')
 cols=['station_id','year','hot_year_start','hemisphere_shift_days','policy_choice','state_h30_q50','eval_truth_h30']
 calendar=defaultdict(lambda:[0,0]);hot=defaultdict(dict);total1=total2=0
 for row in pq.read_table(R1,columns=cols).to_pylist():
  if row['hemisphere_shift_days']!=0:raise ValueError('round 1 time convention changed')
  key=(str(row['station_id']),int(row['year']));calendar[key][0]+=1;calendar[key][1]+=int(eligible(row));total1+=int(eligible(row))
 for row in pq.read_table(R2,columns=cols).to_pylist():
  if row['hemisphere_shift_days']!=184:raise ValueError('round 2 time convention changed')
  start=datetime.strptime(row['hot_year_start'],'%Y-%m-%d').date();end=start.replace(year=start.year+1)
  key=(start,end);v=hot[str(row['station_id'])].setdefault(key,[0,0]);v[0]+=1;v[1]+=int(eligible(row));total2+=int(eligible(row))
 role=defaultdict(lambda:dict(reference_station_years=0,round1_calendar_case_station_years=0,round1_evaluated_station_years=0,round2_hot_window_station_years=0,round2_evaluable_hot_window_station_years=0))
 for station,year,group in refs:
  k=role[group];k['reference_station_years']+=1;n,e=calendar[(station,year)];k['round1_calendar_case_station_years']+=int(n>0);k['round1_evaluated_station_years']+=int(e>0)
  lo=date(year,1,1);hi=date(year+1,1,1);wins=[v for (start,end),v in hot[station].items() if start<hi and end>lo]
  k['round2_hot_window_station_years']+=int(len(wins)>0);k['round2_evaluable_hot_window_station_years']+=int(any(x[1]>0 for x in wins))
 with (OUT/'australia_prior_exposure_by_role.csv').open(newline='',encoding='utf8') as f:
  existing={r['role']:r for r in csv.DictReader(f)}
 for name,vals in role.items():
  if name not in existing:raise ValueError('role missing')
  for k,v in vals.items():
   if int(existing[name][k])!=v:raise ValueError('independent overlap differs: '+name+'/'+k)
 status={'status':'independent_prior_exposure_recount_passed','reference_station_years':len(refs),'roles_checked':len(role),
  'round1_evaluation_case_count':total1,'round2_development_case_count':total2,
  'scope':'independent Arrow/Python identity, eligibility-presence and overlapping time-window recount; no model inference or error comparison',
  'limitation':'does not prove identical masks, source-training leakage, physical independence or 24-hour completeness'}
 (OUT/'australia_prior_exposure_independent.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))
if __name__=='__main__':main()

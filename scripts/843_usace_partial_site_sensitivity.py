#!/usr/bin/env python3
"""Post-hoc site and network-proxy sensitivity for bounded scores."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/external_usace_reservoir';PRIVATE=ROOT/'private/wrr_usace_reservoir_reference_20261027'

def inputs():
    runner=T.load_script('usace_site_sensitivity_runner',ROOT/'scripts/838_usace_partial_history_predict.py')
    status=json.loads((OUT/'partial_history_score_status.json').read_text());audit=json.loads((OUT/'partial_history_score_independent_audit.json').read_text());path=PRIVATE/'partial_history_scored_cases.parquet'
    if audit['status']!='passed':raise ValueError('Score inputs not audited')
    return runner,path

def freeze():
    path=OUT/'partial_history_site_sensitivity_plan.json'
    if path.exists():raise FileExistsError('Preserve site sensitivity plan')
    runner,cases=inputs();roster=PRIVATE/'partial_history_roster.csv';meta=PRIVATE/'roster.csv';net=PRIVATE/'nldi_metadata/gage_summary.csv'
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc after target H30 bounds and aggregate model scores were inspected; before generating per-site results',
       'cohort':'All four fixed resources and all available cases, and the already defined width<=0.1 C posthoc subset. Report every resource, including those with zero subset cases.',
       'metrics':'Number of target years/cases, interpolation burden in history, equal-case means of each method lower/upper absolute-error bounds, and D2-minus-comparator paired difference bounds. Compare known gage-proxy 200-km prior hits as descriptive subsets only.',
       'limitations':'No-hit is not proof of independence: sensor and gage can differ, search is truncated, networks and climate can overlap. Mask cases repeat years, and no site or uncertainty inference is claimed. Results depend on assumed missing-value bounds, quality, training interpolation and out-of-support model inputs.',
       }
    path.write_text(json.dumps(plan,indent=2)+'\n');print('Frozen all-site posthoc sensitivity')

def run():
    runner,path=inputs();p=json.loads((OUT/'partial_history_site_sensitivity_plan.json').read_text())
    scorer=T.load_script('usace_site_sensitivity_score',ROOT/'scripts/839_usace_partial_history_score.py')
    cases=pd.read_parquet(path);roster=pd.read_csv(PRIVATE/'partial_history_roster.csv');meta=pd.read_csv(PRIVATE/'roster.csv').set_index('resource_id');network=pd.read_csv(PRIVATE/'nldi_metadata/gage_summary.csv',dtype={'site':str}).set_index('site')
    rows=[];sensitivity=[]
    for rid in sorted(roster.resource_id.unique()):
        m=meta.loc[rid];gages=m.gage_ids.split(';')
        if any(g not in network.index for g in gages):raise ValueError('Gage proxy missing')
        prior=any(int(network.loc[g,'prior_gage_hits'])>0 for g in gages);source=any(int(network.loc[g,'source_panel_gage_hits'])>0 for g in gages)
        interp=[]
        for y in roster.loc[roster.resource_id.eq(rid),'year']:
            receipt=json.loads((PRIVATE/'partial_history_predictions'/rid/str(y)/'receipt.json').read_text());interp.extend(x['interpolated_days'] for x in receipt['history'])
        for name,sub in [('all',cases[cases.resource_id.eq(rid)]),('reference_width_at_most_0.1_posthoc',cases[cases.resource_id.eq(rid)&cases.h30_interval_width_c.le(.1+1e-12)])]:
            t=sub[sub.common];row={'resource_id':rid,'title':m.title,'cohort':name,'prior_network_proxy_hit':prior,'source_panel_proxy_hit':source,
              'station_years':len(t[['resource_id','year']].drop_duplicates()),'cases':len(t),'max_history_interpolated_days':max(interp) if interp else None}
            for label in ['plug_in','D2','stochastic']:
                row[label+'_mae_lower_c']=t[label+'_err_low'].mean();row[label+'_mae_upper_c']=t[label+'_err_high'].mean()
            if len(t):
                for label,col in [('plug_in','h30__policy'),('stochastic','stochastic_cal_q50')]:
                    a,b=scorer.pair_bounds(t.D2.to_numpy(float),t[col].to_numpy(float),t.h30_lower_c.to_numpy(float),t.h30_upper_c.to_numpy(float))
                    row['D2_minus_'+label+'_lower_c']=a.mean();row['D2_minus_'+label+'_upper_c']=b.mean()
            rows.append(row)
    table=pd.DataFrame(rows);table.to_csv(OUT/'partial_history_site_sensitivity.csv',index=False)
    for name in ['all','reference_width_at_most_0.1_posthoc']:
        for state in [False,True]:
            ids=set(table.loc[table.cohort.eq(name)&table.prior_network_proxy_hit.eq(state),'resource_id'])
            sub=cases[cases.resource_id.isin(ids)&cases.common]
            if name!='all':sub=sub[sub.h30_interval_width_c.le(.1+1e-12)]
            if not len(sub):continue
            row={'cohort':name,'prior_network_proxy_hit':state,'sites':sub.resource_id.nunique(),
                 'station_years':len(sub[['resource_id','year']].drop_duplicates()),'cases':len(sub)}
            for label in ['plug_in','D2','stochastic']:
                row[label+'_mae_lower_c']=sub[label+'_err_low'].mean();row[label+'_mae_upper_c']=sub[label+'_err_high'].mean()
            sensitivity.append(row)
    groups=pd.DataFrame(sensitivity);groups.to_csv(OUT/'partial_history_network_sensitivity.csv',index=False)
    status={'status':'completed','resources':len(roster.resource_id.unique()),'site_summary_rows':len(table),'network_summary_rows':len(groups),
       'limitations':p['limitations']}
    (OUT/'partial_history_site_sensitivity_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(table.to_string(index=False));print(groups.to_string(index=False));print(json.dumps(status,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);x=a.parse_args();freeze() if x.action=='freeze' else run()

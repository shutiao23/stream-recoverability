#!/usr/bin/env python3
"""Post-hoc paired summaries by gap length and station, not independent trials."""
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory'
PRIVATE=ROOT/'private/wrr_nova_scotia_exploratory_20261026'


def main():
    integrity=json.loads((OUT/'integrity_status.json').read_text());probe=json.loads((OUT/'hidden_value_probe.json').read_text())
    if integrity['status']!='passed' or probe['status']!='passed':raise RuntimeError('case arithmetic or hidden probes did not pass')
    data=pd.read_parquet(PRIVATE/'predictions.parquet')
    spec=importlib.util.spec_from_file_location('ns_scoring_tables',ROOT/'scripts/598_nova_scotia_exploratory_score.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    scorer=T.load_script('ns_diagnostic_quantiles',ROOT/'scripts/528_review_response_annual.py')
    base,pair,_=m.score_tables(data,scorer.quantile_samples)
    saved=pd.read_csv(OUT/'paired_summary.csv')
    merged=pair.merge(saved,on='stratum',suffixes=('_new','_saved'),validate='one_to_one')
    for col in ['n_eligible','n_common','D2_mae','stochastic_mae','D2_coverage90','stochastic_coverage90','D2_width90','stochastic_width90','D2_interval_score90','stochastic_interval_score90','D2_crps','stochastic_crps']:
        if not np.allclose(merged[col+'_new'],merged[col+'_saved'],atol=1e-8,rtol=0,equal_nan=True):raise ValueError('overall paired values disagree')
    rows=[]
    for axis in ['gap_length','station_id']:
        for value,block in data.groupby(axis,sort=True):
            s,p,_=m.score_tables(block,scorer.quantile_samples);r=p.loc[p.stratum.eq('all')].iloc[0].to_dict()
            r.update(axis=axis,level=str(value));rows.append(r)
    diagnostics=pd.DataFrame(rows);diagnostics.to_csv(OUT/'paired_posthoc_diagnostics.csv',index=False)
    state={'status':'passed','cases':len(data),'group_rows':len(diagnostics),
       'scope':'after-score descriptive breakdown by site and gap length; both methods share the same cases in each row',
       'limitation':'two sites and repeated masks, no population inference; reported-clock reference and physical sensor quality remain uncertain'}
    (OUT/'diagnostic_status.json').write_text(json.dumps(state,indent=2)+'\n');print(diagnostics.to_string(index=False));print(json.dumps(state,indent=2))

if __name__=='__main__':main()

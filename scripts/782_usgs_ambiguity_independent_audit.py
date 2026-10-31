#!/usr/bin/env python3
"""Independently recompute the post-hoc multiple-USGS-values diagnostic."""
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity';P=ROOT/'private/wrr_open_source_sensitivity_20261026/donor_provenance';D=P/'usgs_daily'

def main():
    plan=json.loads((OUT/'donor_usgs_ambiguous_plan.json').read_text());summary=json.loads((OUT/'donor_usgs_ambiguous_summary.json').read_text())
    records=[]
    for batch in json.loads((D/'acquisition.json').read_text()):
        path=D/f"batch_{batch['batch']:02d}.json.gz"
        with gzip.open(path,'rt') as f:payload=json.load(f)
        for series in payload['value']['timeSeries']:
            site=series['sourceInfo']['siteCode'][0]['value']
            for block in series['values']:
                method=json.dumps(block.get('method',[]),sort_keys=True,separators=(',',':'))
                for v in block.get('value',[]):
                    records.append((site,str(v['dateTime'])[:10],v['value'],';'.join(sorted(v.get('qualifiers',[]))),method))
    raw=pd.DataFrame(records,columns=['site','date','value','qualifiers','method']);raw['value']=pd.to_numeric(raw.value,errors='coerce')
    raw=raw[np.isfinite(raw.value)&raw.value.ne(-999999.)].copy()
    groups=raw.groupby(['site','date']).agg(low=('value','min'),high=('value','max'),n_values=('value','nunique'),n_methods=('method','nunique'),n_qualifiers=('qualifiers','nunique'))
    ambiguous=groups[groups.high-groups.low>1e-10];values=raw.merge(ambiguous.reset_index()[['site','date']],on=['site','date'],how='inner')
    roster=pd.read_csv(P/'usgs_metadata/unresolved_columns.csv',dtype=str);jobs=pd.DataFrame(T.load_script('ambiguity_independent_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source'))
    local=[]
    for network,cols in roster.groupby('network_id'):
        paths=jobs[jobs.network_id.eq(network)&jobs.provider.eq('usgs')].input_path.unique()
        if len(paths)!=1:raise ValueError('Ambiguous panel path')
        selected=pd.read_csv(paths[0],usecols=['date']+cols.station_id.tolist(),dtype={'date':str})
        melted=selected.melt(id_vars='date',var_name='site',value_name='local');melted['local']=pd.to_numeric(melted['local'],errors='coerce')
        local.append(melted[np.isfinite(melted.local)])
    local=pd.concat(local,ignore_index=True);merged=local.merge(groups.reset_index(),on=['site','date'],how='left');amb=merged[(merged.high-merged.low)>1e-10].copy()
    expanded=amb.reset_index().merge(values,on=['site','date'],how='left');expanded['hit']=(expanded.local-expanded.value).abs()<=1e-6
    matches=expanded.groupby('index').hit.any();no_source=int(merged.low.isna().sum());checks={
        'ambiguous_panel_column_days':len(amb),'matches_at_least_one':int(matches.sum()),'matches_none':int((~matches).sum()),
        'at_least_two_recorded_methods':int((amb.n_methods>1).sum()),'multiple_qualifier_sets':int((amb.n_qualifiers>1).sum()),'no_finite_source_days':no_source}
    for key,value in checks.items():
        if int(summary[key])!=value:raise AssertionError('Mismatch '+key)
    counts=amb.n_values.value_counts().to_dict()
    if {str(int(k)):int(v) for k,v in counts.items()}!=summary['distinct_value_counts']:raise AssertionError('Distinct-value count mismatch')
    spread=amb.high-amb.low
    if not np.isclose(spread.max(),summary['max_range_c'],atol=1e-10) or not np.isclose(spread.median(),summary['median_range_c'],atol=1e-10):raise AssertionError('Ambiguous-value spread differs')
    result={'status':'passed','panel_column_days_recomputed':len(amb),'all_candidate_values_recomputed':True,
            'implementation':'Independent pandas joins and group aggregates over all saved source responses and local panels.',
            'limitations':'Uses the same responses and cached panels. Any-match analysis is post-hoc and does not identify a correct method, historical source, sensor quality, or permission.'}
    (OUT/'donor_usgs_ambiguous_independent_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()

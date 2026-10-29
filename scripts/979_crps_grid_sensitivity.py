#!/usr/bin/env python3
"""Check integration-grid precision of the saved annual-quantile comparison.

The annual quantiles, source offsets, targets and tail assumption are fixed.
This checks quadrature of that assumed distribution, not its correctness.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from stream_recoverability.experiments.tr_revision.archive import marginal_draws

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_process_experiments_20261029/source_calibration'
LEVELS = [5, 10, 25, 50, 75, 90, 95]


def main():
    paths = [OUT/'full/target_three_layer_cases.csv', OUT/'full/target_historical_reference.csv']
    scored = pd.read_csv(paths[0], float_precision='round_trip').rename(columns={'layer':'method'})
    baseline = pd.read_csv(paths[1], float_precision='round_trip').assign(seed=-1, count=-1)
    keep = ['station_key','year','region','method','seed','count','truth','bound','crps256_normal'] + [f'q{x:02d}' for x in LEVELS]
    cases = pd.concat([scored[keep], baseline[keep]], ignore_index=True)
    q = cases[[f'q{x:02d}' for x in LEVELS]].to_numpy(float)
    results = []
    max_reproduction = 0.
    for grid in [256, 1024, 4096]:
        samples = marginal_draws(q, draws=grid, tails='normal', lower_bounds=cases.bound.to_numpy(float))
        weights = (2*np.arange(1, grid+1)-grid-1)[:,None]
        crps = np.abs(samples-cases.truth.to_numpy(float)).mean(axis=0) - (weights*np.sort(samples,axis=0)).sum(axis=0)/(grid*grid)
        if grid == 256:
            max_reproduction = float(np.max(abs(crps-cases.crps256_normal.to_numpy(float))))
            if max_reproduction > 1e-10:
                raise ValueError('Independent order-statistic CRPS does not reproduce saved 256-grid scores')
        results.append(cases[['station_key','year','region','method','seed','count']].assign(grid=grid, crps=crps))
    values = pd.concat(results, ignore_index=True)
    values.to_csv(OUT/'target_crps_grid_cases.csv', index=False)
    summary = values.groupby(['method','seed','count','grid','region'], dropna=False).agg(n=('crps','size'),crps=('crps','mean')).reset_index()
    pooled = values.groupby(['method','seed','count','grid'], dropna=False).agg(n=('crps','size'),crps=('crps','mean')).reset_index().assign(region='pooled_27')
    summary = pd.concat([summary, pooled], ignore_index=True)
    summary.to_csv(OUT/'target_crps_grid_summary.csv', index=False)
    delta = values.pivot(index=['station_key','year','region','method','seed','count'],columns='grid',values='crps')
    crossing = []
    for grid in [256, 1024, 4096]:
        part = pooled.loc[pooled.grid.eq(grid)]
        fixed = float(part.loc[part.method.eq('fixed_D2'),'crps'].iloc[0])
        classical = part.loc[part.method.eq('reestimated_source_offset') & part.seed.eq(0)].set_index('count').crps
        crossing.append({'grid':grid,'fixed_D2':fixed,'nested20_updated':float(classical.loc[20]),'nested500_updated':float(classical.loc[500]),'same_seed_order_crossing':bool(classical.loc[20]>fixed>classical.loc[500])})
    report = {'status':'passed','scope':'Precision of CRPS integration for the same fixed seven-quantile, bounded normal-tail approximation; no offset/model refit or convergence claim for the underlying distribution.',
              'comparison_cases':len(cases),'grid_sizes':[256,1024,4096], 'score_rows':len(values),
              'saved256_reproduction_max_error':max_reproduction,
              'max_casewise_change_256_to4096':float((delta[4096]-delta[256]).abs().max()),
              'seed_zero_same_stream_ordering':crossing,
              'all_three_grids_preserve_reported_seed0_order_crossing':all(x['same_seed_order_crossing'] for x in crossing),
              'baseline_seed_and_budget_sentinel':-1,
              'input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT/'crps_grid_sensitivity.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()

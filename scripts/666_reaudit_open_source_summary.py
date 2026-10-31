#!/usr/bin/env python3
"""Independently recount the candidate-source paired trend and factorial results."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_review_response_20261027/open_source_sensitivity'
BASE = ROOT / 'results/wrr_review_response_20261027/whole_archive'
PRIVATE = ROOT / 'private/wrr_open_source_sensitivity_20261026/whole_archive'
INDEX = ['family', 'mode', 'station_key', 'replicate']


def main():
    old = pd.read_csv(BASE / 'trends.csv')
    paths = sorted(PRIVATE.glob('*/?*/replicate_*/*/trends.csv'))
    if len(paths) != 3320:
        raise ValueError('Expected all 3,320 archive settings')
    new = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    for frame in [old, new]:
        point = frame.loc[frame.dependence.eq('point') & frame.available.fillna(False)]
        if not np.allclose(point.squared_error, point.error**2, atol=1e-12, rtol=1e-10):
            raise ValueError('Saved squared errors disagree with signed errors')
    def pivot(frame):
        x = frame.loc[frame.dependence.eq('point') & frame.estimator.isin(['plug_in', 'D2', 'stochastic_calibrated'])]
        if x.duplicated(INDEX+['retention', 'estimator']).any():
            raise ValueError('Duplicate point-case identity')
        return x.pivot(index=INDEX, columns=['retention', 'estimator'], values='squared_error')
    a, b = pivot(old), pivot(new)
    if not a.index.equals(b.index):
        raise ValueError('Target identities differ')
    ref = pd.read_csv(OUT / 'archive_four_way_comparison.csv').set_index(['family', 'mode'])
    factor = pd.read_csv(OUT / 'archive_factorial_paired.csv').set_index(['family', 'mode', 'estimator'])
    mapping = old.loc[old.dependence.eq('point') & old.retention.eq('all') & old.estimator.eq('D2'), INDEX+['independence_group']]
    if mapping.duplicated(INDEX).any():
        raise ValueError('Duplicate connected-group mapping')
    mapping = mapping.set_index(INDEX).independence_group
    count = 0
    for offset, (family, mode) in enumerate(ref.index):
        selector = (a.index.get_level_values('family') == family) & (a.index.get_level_values('mode') == mode)
        x, y = a.loc[selector], b.loc[selector]
        d = np.column_stack([x[('all','D2')], x[('all','stochastic_calibrated')], y[('all','D2')], y[('all','stochastic_calibrated')]])
        valid = np.isfinite(d).all(axis=1)
        d = d[valid]
        saved = ref.loc[(family, mode)]
        if len(d) != int(saved.common_four_way_cases):
            raise ValueError('Common comparator denominator differs')
        labels = ['D2_original_rmse', 'stochastic_calibrated_original_rmse', 'D2_candidate_rmse', 'stochastic_calibrated_candidate_rmse']
        for j, col in enumerate(labels):
            if not np.isclose(np.sqrt(d[:,j].mean()), saved[col], atol=1e-10, rtol=0):
                raise ValueError('Common comparator RMSE differs: '+col)
        group = mapping.reindex(x.index)[valid].to_numpy()
        if pd.isna(group).any() or len(set(group)) != int(saved.common_groups):
            raise ValueError('Common connected-group denominator differs')
        groups = sorted(set(group))
        old_gaps = d[:,0]-d[:,1]
        candidate_gaps = d[:,2]-d[:,3]
        sums_old = np.array([old_gaps[group == g].sum() for g in groups])
        sums_new = np.array([candidate_gaps[group == g].sum() for g in groups])
        sizes = np.array([(group == g).sum() for g in groups])
        rng = np.random.default_rng(661 + offset)
        changes = []
        for _ in range(4000):
            picked = rng.integers(len(groups), size=len(groups))
            changes.append((sums_new[picked].sum()-sums_old[picked].sum())/sizes[picked].sum())
        bounds = np.quantile(changes, [.025, .975])
        if not np.allclose(bounds, [saved.gap_change_bootstrap_low, saved.gap_change_bootstrap_high], atol=1e-12, rtol=0):
            raise ValueError('Connected-group paired bootstrap differs')
        for estimator in ['D2', 'stochastic_calibrated']:
            # Baseline warm/all and each estimator warm/all in both versions.
            vals = np.column_stack([x[('warm90','plug_in')], x[('all','plug_in')],
                                    x[('warm90',estimator)], x[('all',estimator)],
                                    y[('warm90','plug_in')], y[('all','plug_in')],
                                    y[('warm90',estimator)], y[('all',estimator)]])
            vals = vals[np.isfinite(vals).all(axis=1)]
            saved_factor = factor.loc[(family, mode, estimator)]
            if len(vals) != int(saved_factor.n_common):
                raise ValueError('Factorial common denominator differs')
            for label, start in [('original', 0), ('candidate', 4)]:
                q, r, s, t = (vals[:,start+i] for i in range(4))
                retention = np.mean(((q-r)+(s-t))/2)
                estimator_gain = np.mean(((q-s)+(r-t))/2)
                total = np.mean(q-t)
                for name, value in [('symmetric_retention',retention), ('symmetric_estimator',estimator_gain), ('total_gain',total)]:
                    if not np.isclose(value, saved_factor[label+'_'+name], atol=1e-10, rtol=0):
                        raise ValueError('Factorial mean differs: '+label+' '+name)
                if not np.isclose(retention+estimator_gain, total, atol=1e-10, rtol=0):
                    raise ValueError('Factorial decomposition does not add up')
        count += 1
    report = {'status': 'passed', 'archive_settings': len(paths), 'four_way_cells_checked': count,
              'factorial_cells_checked': len(factor), 'squared_errors_recomputed': True,
              'group_bootstrap_cells_checked': count,
              'limitation': 'Independent arithmetic on saved target outcomes and predictions; not a rerun of the refit, raw source QC, provider permissions, or a climate-transfer test.'}
    (OUT / 'independent_summary_audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Audit restricted-provider dependence of original whole-archive models.

Counts positive-weight source rows, never publishes observation values. This is
provenance evidence, not a legal determination about whether predictions are
redistributable. Original model roles and weights are checked against bundles.
"""
from __future__ import annotations
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed

ROOT = T.ROOT
REV = ROOT / 'results/wrr_review_response_20261027'
OUT = REV / 'audit'
SOURCE = ROOT / 'results/wrr_review_completion_20261024'


def main():
    trends = pd.read_csv(REV / 'whole_archive/trends.csv')
    expected = trends.groupby(['mode', 'region']).station_key.nunique()
    refit = T.load_script('source_rights_roles', ROOT / 'scripts/466_review_completion_refit.py')
    roster = T.roster().drop_duplicates('station_key').set_index('station_key')
    targets = set(trends.station_key)
    if not targets.issubset(roster.index):
        raise ValueError('Target station missing from rights roster')
    target_rights = roster.loc[sorted(targets)]
    if not target_rights.data_rights_redistribution_allowed.astype(str).str.lower().eq('true').all():
        raise ValueError('Target sources have unresolved recorded redistribution rights')
    rows = []
    for mode, split in [('offline', 'leave_one_year_out'), ('forward', 'before_2010')]:
        path = SOURCE / 'cases' / split / 'seed_00.parquet'
        schema = pq.ParquetFile(path).schema.names
        cols = ['region', 'station_key', 'provider', 'network_id', 'independence_group', 'policy_choice', 'eval_truth_h30']
        if 'training_partition' in schema:
            cols.append('training_partition')
        c = pd.read_parquet(path, columns=cols)
        c = c.loc[c.policy_choice.ne('unavailable') & c.eval_truth_h30.notna()].reset_index(drop=True)
        if not c.station_key.str.split('|').str[0].eq(c.provider).all():
            raise ValueError('Provider and station prefix disagree')
        if c.groupby('network_id').provider.nunique().gt(1).any() or c.groupby('independence_group').provider.nunique().gt(1).any():
            raise ValueError('Mixed-provider network or group requires separate lineage audit')
        regions = sorted(c.region.unique())
        for region in sorted(expected.loc[mode].index):
            bundle = joblib.load(SOURCE / 'refits' / split / 'seed_00' / (region + '.joblib'))
            _, roles, weights = refit.roles(c, region, plain_seed(7, 0, regions.index(region)))
            if roles != bundle['roles']:
                raise ValueError('Source roles differ from saved model')
            restricted = c.provider.eq('lubw').to_numpy()
            for role in ['estimator', 'interval_calibration', 'risk_learning', 'rule_calibration']:
                pos = (np.asarray(weights[role]) > 0) & restricted
                rows.append({'mode': mode, 'region': region, 'role': role, 'target_stations': int(expected.loc[(mode, region)]),
                             'lubw_positive_weight_case_rows': int(pos.sum()),
                             'lubw_positive_weight_groups': int(c.loc[pos, 'independence_group'].nunique()),
                             'lubw_bootstrap_weighted_case_rows': int(np.asarray(weights[role])[pos].sum())})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / 'archive_restricted_source_roles.csv', index=False)
    est = out.loc[out.role.eq('estimator')]
    status = {'status': 'passed_with_dependency_found', 'target_stations': len(targets),
              'target_provider_counts': target_rights.provider.value_counts().to_dict(),
              'model_mode_region_combinations': len(est),
              'estimator_combinations_with_lubw_positive_weight': int(est.lubw_positive_weight_case_rows.gt(0).sum()),
              'interval_calibration_combinations_with_lubw_positive_weight': int(out.loc[out.role.eq('interval_calibration'), 'lubw_positive_weight_case_rows'].gt(0).sum()),
              'source_role_assignments_match_saved_models': True,
              'limitations': 'Rows are repeated masked cases, not independent stations or climate samples. Positive training weights establish source dependence, not the legal status of a particular prediction. Other provider, air-forcing, source-case, mask, model and downstream provenance still require review.'}
    (OUT / 'archive_restricted_source_roles.json').write_text(json.dumps(status, indent=2) + '\n')
    print(out.loc[out.role.isin(['estimator', 'interval_calibration'])].to_string(index=False))
    print(json.dumps(status, indent=2))


if __name__ == '__main__':
    main()

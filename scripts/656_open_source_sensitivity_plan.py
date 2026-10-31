#!/usr/bin/env python3
"""Freeze the post-hoc source-rights and strict-region sensitivity design.

Only provider and case identities/metadata are screened here. No new model or
held-out performance is calculated. Subsequent refits remain local until all
source and derivative permissions are individually established.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
import wrr_tr_common as T

ROOT = T.ROOT
OUT = ROOT / 'results/wrr_review_response_20261027/open_source_sensitivity'
SOURCE = ROOT / 'results/wrr_review_completion_20261024'
REV = ROOT / 'results/wrr_review_response_20261027'
ALLOWED = ['chmi', 'foen', 'gkd_bayern', 'nve_hydapi', 'rws_waterwebservices', 'syke', 'usgs']

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan_path = OUT / 'plan.json'
    if plan_path.exists():
        raise RuntimeError('Preserve existing frozen plan')
    audit = json.loads((REV / 'audit/archive_restricted_source_roles.json').read_text())
    if audit['estimator_combinations_with_lubw_positive_weight'] != audit['model_mode_region_combinations']:
        raise ValueError('Original source dependency changed; reassess plan')
    targets = pd.read_csv(REV / 'whole_archive/trends.csv', usecols=['mode', 'region', 'station_key']).drop_duplicates()
    roster = T.roster().drop_duplicates('station_key').set_index('station_key')
    if not set(targets.station_key).issubset(roster.index) or not set(roster.loc[targets.station_key, 'provider']).issubset(ALLOWED):
        raise ValueError('Target source is missing or not in the candidate allowable providers')
    before = {}
    hashes = {}
    for split in ['leave_one_year_out', 'before_2010']:
        path = SOURCE / 'cases' / split / 'seed_00.parquet'
        cols = ['station_key', 'provider', 'network_id', 'independence_group', 'region', 'design_family', 'calendar_source', 'policy_choice', 'eval_truth_h30']
        if 'training_partition' in pq.ParquetFile(path).schema.names:
            cols.append('training_partition')
        c = pd.read_parquet(path, columns=cols)
        eligible = c.loc[c.policy_choice.ne('unavailable') & c.eval_truth_h30.notna()].copy()
        if eligible.groupby('network_id').provider.nunique().gt(1).any() or eligible.groupby('independence_group').provider.nunique().gt(1).any():
            raise ValueError('Mixed-source network or group requires further review')
        c = eligible.loc[eligible.provider.isin(ALLOWED)]
        calendar = c.loc[c.design_family.eq('calendar')]
        origin = calendar.calendar_source.fillna('').str.split('|').str[0]
        if origin.eq('').any() or not origin.eq(calendar.provider).all():
            raise ValueError('Calendar source not identifiable within target provider')
        if not set(c.station_key).issubset(roster.index):
            raise ValueError('Unmapped source stations')
        r = roster.loc[sorted(set(c.station_key))]
        if not r.data_rights_redistribution_allowed.astype(str).str.lower().eq('true').all() or not r.derived_output_allowed.astype(str).str.lower().eq('true').all():
            raise ValueError('Candidate source rights require further review')
        before[split] = {'eligible_case_rows_before_filter': len(eligible), 'candidate_case_rows_after_filter': len(c),
                         'removed_case_rows': len(eligible)-len(c), 'candidate_stations': c.station_key.nunique(),
                         'candidate_groups': c.independence_group.nunique(), 'providers_removed': sorted(set(eligible.provider)-set(ALLOWED)),
                         'checked_same_provider_calendars': len(calendar)}
    plan = {'created_utc': datetime.now(timezone.utc).isoformat(), 'status': 'posthoc_design_frozen_before_new_predictions',
            'analysis': 'Refit source models and classical offsets on candidate permitted provider cases only, with strictly excluded target-region groups and new role assignments using the unchanged seed algorithm. Reuse the original archive masks and already fitted daily features; compare with original model and classical outputs on their common target cases.',
            'allowed_providers': ALLOWED, 'splits': before, 'target_mode_region_stations': targets.groupby(['mode', 'region']).station_key.nunique().to_dict(),
            'role_rule': 'Recompute role assignments and bootstrap weights using only retained source cases; remove every connected group that occurs in the target region from every source role, without replacement. Require at least two role groups and positive usable estimation and calibration observations.',
            'limitations': 'Post-hoc sensitivity after original results and source-rights audit; all original target masks and daily refits are reused. The source role assignment and sample size change as well as strict regional exclusion, so differences are not attributable to a single cause. Candidate provider permissions, prior-QC, air and mask provenance, and individual derivative publication rights require further review. Not a preregistered or independent-climate test.'}
    plan['target_mode_region_stations'] = [{'mode': k[0], 'region': k[1], 'stations': int(v)} for k, v in plan['target_mode_region_stations'].items()]
    plan_path.write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps(plan, indent=2))

if __name__ == '__main__':
    main()

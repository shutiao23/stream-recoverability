#!/usr/bin/env python3
"""Freeze an exploratory late-start metadata roster before count preflight."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_review_response_20261027/external_usgs_late_start'
SCOPE = ROOT / 'results/wrr_submission_ready/followup_20261021/usgs_metadata_extension/effective_candidate_scope.csv'
CATALOG = ROOT / 'data/external/wrr_usgs_new_reference_20261021/metadata/combined_daily_mean_temperature_metadata.json'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'plan.json').exists() or (OUT / 'candidate_roster.csv').exists():
        raise RuntimeError('Roster or plan already exists; preserve the existing freeze')
    scope = pd.read_csv(SCOPE, dtype=str)
    begin = pd.to_datetime(scope.begin, utc=True, errors='coerce')
    end = pd.to_datetime(scope.end, utc=True, errors='coerce')
    mask = (scope.not_yet_excluded_metadata_candidate.eq('True')
            & scope.same_HUC8_as_prior_record.eq('False') & begin.dt.year.between(2017, 2021)
            & end.dt.year.ge(2025)
            & ~scope.station_name.str.contains('LAKE|RESERVOIR|CANAL|TAILRACE|DIVERSION|POWERPLANT|REGULATING', case=False, na=False))
    f = scope.loc[mask].copy()
    before = len(f)
    prior = set()
    sources = [
        ('results/additional_usgs_observed/cohort_metadata.csv', 'station_id'),
        ('results/wrr_target_recovery_20261022/e10_sealed_usgs/sealed_roster.csv', 'station_id'),
        ('results/wrr_target_recovery_20261021/e1_archive/usgs_site_metadata.csv', 'site_no'),
        ('results/wrr_review_response_20261027/external_usgs/cohort.csv', 'station_id'),
        ('results/wrr_review_response_20261027/external_usgs_fresh/cohort.csv', 'station_id'),
        ('results/wrr_submission_ready/followup_20261021/usgs_prior_cache_audit/expanded_prior_station_inventory.csv', 'station_id'),
    ]
    for name, col in sources:
        prior.update(pd.read_csv(ROOT / name, dtype=str)[col].dropna())
    prior.add('02450250')
    for p in (ROOT / 'results/wrr_review_completion_20261024/national_meaning/site_results').glob('*.json'):
        try:
            if json.loads(p.read_text()).get('status') == 'processed':
                prior.add(p.stem)
        except (OSError, json.JSONDecodeError):
            raise RuntimeError(f'Cannot audit processed status: {p}')
    raw = ROOT / 'data/external/wrr_target_recovery_20261022/usgs_new/values_raw'
    contacted = f.station_id.isin(prior) | f.series_id.map(lambda x: (raw / (x + '.json')).exists())
    f = f.loc[~contacted].copy()
    if f.station_id.duplicated().any():
        raise RuntimeError('Multiple candidate series per site; require explicit series selection')
    catalog = {x['id']: x['properties'] for x in json.loads(CATALOG.read_text())['features']}
    spec = importlib.util.spec_from_file_location('national_timezones', ROOT / 'scripts/490_review_completion_national_availability.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    f['native_zone'] = [module.native_zone(catalog[x]) for x in f.series_id]
    f = f.sort_values(['HUC2_region_proxy', 'station_id', 'series_id'])
    path = OUT / 'candidate_roster.csv'
    f.to_csv(path, index=False)
    plan = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'initial_candidates': before, 'known_prior_contacts_excluded': int(contacted.sum()), 'frozen_candidates': len(f),
        'selection': 'Current-vintage metadata candidates flagged not yet excluded, no known prior HUC8, begin during 2017-2021, end in or after 2025, and no obvious non-river term in name. Existing source/E10/fresh/cache contacts are also excluded. Missing timezone or unresolved network status is retained and must be resolved before any reference claim.',
        'count_preflight': 'Query 2017-2025 annual approved daily sample counts for matching daily mean series. Keep only count and interval metadata, no annual temperature statistics or prediction errors. Four full calendar years of 365/366 approved daily observations are necessary but not sufficient. Absent records are unknown.',
        'caveat': 'Post hoc exploratory availability screening after earlier negative screens, not a prospective or random reference cohort. River suitability, separation from prior analyses, local-day support, point-level quality and rights remain to be checked before use.'}
    (OUT / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps({'initial': before, 'prior_contact_excluded': int(contacted.sum()), 'frozen': len(f), 'network_status': f.network_status.value_counts().to_dict(), 'missing_timezone': int(f.native_zone.isna().sum())}, indent=2))

if __name__ == '__main__':
    main()

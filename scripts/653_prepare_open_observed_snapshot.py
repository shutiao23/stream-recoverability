#!/usr/bin/env python3
"""Prepare a shareable subset of the main observation-only record evidence.

Extracts only temperature/date fields for previously eligible stations with
recorded permitted source and derivative reuse. Does not recreate source QC,
license omitted providers, or release restricted source/model data.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
import pandas as pd
import wrr_tr_common as T

ROOT = T.ROOT
OUT = ROOT / 'results/wrr_review_response_20261027/open_observed_record_snapshot'
SOURCE = ROOT / 'results/wrr_review_completion_20261024/observed_records'
RULES = ROOT / 'results/wrr_review_response_20261027/rules'
PERMITTED = {
    'usgs': 'USGS confirmatory hydrology',
    'gkd_bayern': 'v11 GKD Bayern confirmation temperature',
    'chmi': 'v11 CHMI confirmation temperature',
    'foen': 'v11 FOEN confirmation temperature',
}

def main():
    if OUT.exists():
        raise RuntimeError('Preserve the existing snapshot; use a new path for a revised vintage')
    years = pd.read_parquet(T.E1 / 'station_years.parquet')
    years = years.loc[~years.edge_year & years.fully_active & years.year.between(1981, 2025)].copy()
    counts = years.loc[years.complete_year & years.truth_h30.notna()].groupby('station_key').size()
    eligible = set(counts.index[counts.ge(15)])
    roster = T.roster().drop_duplicates('station_key')
    roster = roster.loc[roster.station_key.isin(eligible)].copy()
    if len(roster) != len(eligible) or set(roster.station_key) != eligible:
        raise ValueError('Eligible roster missing or duplicated')
    allowed = roster.loc[roster.provider.isin(PERMITTED)].copy()
    for row in allowed.itertuples():
        if (row.data_rights_artifact != PERMITTED[row.provider] or
            str(row.data_rights_redistribution_allowed).lower() != 'true' or
            str(row.derived_output_allowed).lower() != 'true'):
            raise ValueError('Source reuse or derivative permission is not documented: ' + row.station_key)
    excluded = roster.loc[~roster.station_key.isin(allowed.station_key)]
    if set(excluded.provider) != {'lubw'}:
        raise ValueError('A previously unreviewed source would be excluded; assess it explicitly')
    keys = set(allowed.station_key)
    daily = pd.read_parquet(T.SCRATCH / 'archive_daily.parquet', columns=['station_key', 'date', 'water_c'],
                            filters=[('station_key', 'in', sorted(keys))])
    if daily.duplicated(['station_key', 'date']).any() or set(daily.station_key) != keys:
        raise ValueError('Daily source identity or date problem')
    selected_years = years.loc[years.station_key.isin(keys), ['station_key', 'year', 'edge_year', 'fully_active', 'complete_year', 'truth_h30']]
    witnesses = pd.read_csv(SOURCE / 'observed_record_certificates.csv')
    if not set(witnesses.station_key).issubset(keys):
        raise ValueError('Not all original witness stations have permitted source data')
    bounds = pd.read_csv(SOURCE / 'all_incomplete_year_bounds.csv')
    bounds = bounds.loc[bounds.station_key.isin(keys)]
    rule_years = pd.read_csv(RULES / 'eligible_station_years.csv', dtype={'train_warm_months': str})
    keep_cols = ['station_key', 'year', 'observed_fraction', 'warm_observed_fraction', 'julaug_complete', 'complete_year', 'longest_run', 'reported_window', 'train_warm_fraction', 'train_warm_months']
    rule_years = rule_years.loc[rule_years.station_key.isin(keys), keep_cols]
    decisions = pd.read_csv(RULES / 'witness_rules.csv')
    decisions = decisions.loc[:, ['station_key', 'incomplete_year', 'rule', 'passes_rule', 'excluded_exceeds_accepted_observed_record']]
    rule_summary = pd.read_csv(RULES / 'rule_summary.csv')
    OUT.mkdir(parents=True)
    daily.sort_values(['station_key', 'date']).to_parquet(OUT / 'daily_temperature.parquet', index=False)
    selected_years.sort_values(['station_key', 'year']).to_parquet(OUT / 'station_years.parquet', index=False)
    allowed[['station_key', 'provider', 'network_id', 'statistic_class', 'data_rights_artifact', 'data_rights_license', 'data_rights_required_citation', 'acquisition_route']].sort_values('station_key').to_csv(OUT / 'source_roster.csv', index=False)
    bounds.to_csv(OUT / 'all_incomplete_year_bounds.csv', index=False)
    witnesses.to_csv(OUT / 'observed_record_certificates.csv', index=False)
    rule_years.to_csv(OUT / 'eligible_station_years.csv', index=False)
    decisions.to_csv(OUT / 'witness_rules.csv', index=False)
    rule_summary.to_csv(OUT / 'rule_summary.csv', index=False)
    (OUT / 'ATTRIBUTION.txt').write_text('''Selected daily-temperature archive for observation-only witness verification\n\nThis is a project-processed, float32, quality-filtered subset of provider data,\nnot the original provider-native measurements or a statement of sensor accuracy.\nData and derived outputs are limited to previously selected eligible stations\nwith documented source/derivative reuse. The study's one LUBW eligible station\nis excluded pending permission. Selection, aggregation, quality filtering,\nfloat32 conversion, and the derived station-year/window calculations are\nproject changes; dates, available values, and station identities are retained.\n\nUSGS: U.S. Geological Survey, Water Data for the Nation, daily water temperature,\nhttps://api.waterdata.usgs.gov/; acknowledge the U.S. Geological Survey.\n\nGKD Bayern: Datenquelle: Bayerisches Landesamt fuer Umwelt, www.lfu.bayern.de;\nwater temperature, https://www.gkd.bayern.de/de/fluesse/wassertemperatur/tabellen;\nCC BY 4.0 https://creativecommons.org/licenses/by/4.0/ .\n\nCHMI: Czech Hydrometeorological Institute, historical measured water temperature,\nhttps://opendata.chmi.cz/hydrology/historical/data/measured_temperature/ ;\nCC BY 4.0 https://creativecommons.org/licenses/by/4.0/ .\n\nFOEN: Federal Office for the Environment (FOEN), Hydrological observations,\nhttps://api.data-platform.cloud.bafu.admin.ch/en/dataproduct-water-observations ;\nOpen use. Must provide the source; https://api.data-platform.cloud.bafu.admin.ch/en/lizenz-und-quelle .\n\nThe candidate is a local review artifact, not a permanent public archive.\n''')
    files = sorted(p for p in OUT.iterdir() if p.is_file())
    manifest = {'scope': 'Previously eligible open-provider station subset; project-processed float32 daily series, not provider-native raw values or the entire study population',
                'total_original_eligible_stations': len(eligible), 'included_eligible_stations': len(keys),
                'included_by_provider': allowed.provider.value_counts().to_dict(),
                'excluded_by_provider': excluded.provider.value_counts().to_dict(),
                'original_witnesses_included': len(witnesses),
                'files': [{'path': p.name, 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'files'}, indent=2))

if __name__ == '__main__':
    main()

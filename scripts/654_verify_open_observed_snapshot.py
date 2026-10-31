#!/usr/bin/env python3
"""Independently re-audit main observation witnesses from the open subset.

Recomputes reported-year bounds, complete-year references, witness windows,
and rule decisions on the supplied canonical daily series. It verifies neither
all eligible stations nor upstream measurements, raw quality control, models,
or data rights. Included stations were already selected before this snapshot.
"""
from __future__ import annotations
import argparse
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'results/wrr_review_response_20261027/open_observed_record_snapshot'
NEEDED = {'daily_temperature.parquet', 'station_years.parquet', 'source_roster.csv',
          'all_incomplete_year_bounds.csv', 'observed_record_certificates.csv',
          'eligible_station_years.csv', 'witness_rules.csv', 'rule_summary.csv', 'ATTRIBUTION.txt'}

def verify_snapshot(manifest_path=None):
    manifest_path=Path(manifest_path) if manifest_path is not None else SNAPSHOT/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    names = [entry['path'] for entry in manifest['files']]
    if len(names) != len(set(names)) or set(names) != NEEDED:
        raise ValueError('Unexpected, duplicate or missing snapshot files')
    for entry in manifest['files']:
        p = (SNAPSHOT / entry['path']).resolve()
        if (not p.is_relative_to(SNAPSHOT.resolve()) or not p.is_file()
                or (SNAPSHOT / entry['path']).is_symlink() or not entry.get('sha256')
                or hashlib.sha256(p.read_bytes()).hexdigest()!=entry['sha256']):
            raise ValueError('Snapshot input missing or changed: ' + entry['path'])
    roster = pd.read_csv(SNAPSHOT / 'source_roster.csv')
    if roster.station_key.duplicated().any() or len(roster) != manifest['included_eligible_stations']:
        raise ValueError('Station roster identity mismatch')
    if roster.provider.value_counts().to_dict() != manifest['included_by_provider'] or set(roster.provider) != {'usgs', 'gkd_bayern', 'chmi', 'foen'}:
        raise ValueError('Unexpected source roster')
    witnesses = pd.read_csv(SNAPSHOT / 'observed_record_certificates.csv')
    if len(witnesses) != manifest['original_witnesses_included'] or not set(witnesses.station_key).issubset(set(roster.station_key)):
        raise ValueError('Witness roster mismatch')
    return manifest

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,help='Use an explicit snapshot manifest; historical default remains unchanged')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/wrr_review_response_20261027/audit/open_observed_reproduction.json')
    args = parser.parse_args()
    result = {'scope': 'independent record arithmetic and screening-rule audit on previously selected open-provider processed daily series',
              'limitations': 'one of the original 96 stations is omitted due to unresolved reuse; cannot independently establish eligibility of unprovided stations, reconstruct provider-native data or prior QC, or validate sensor accuracy, the main models, or independent climate transfer'}
    try:
        manifest = verify_snapshot(args.manifest)
        with tempfile.TemporaryDirectory(prefix='open_observed_replay_') as tmp:
            root = Path(tmp)
            for folder in ['scripts', 'configs', 'src', 'scratch/wrr_target_recovery_20261021',
                           'results/wrr_target_recovery_20261021/e1_archive',
                           'results/wrr_review_completion_20261024/observed_records',
                           'results/wrr_review_response_20261027/rules']:
                (root / folder).mkdir(parents=True, exist_ok=True)
            for name in ['570_reaudit_observed_records.py', '571_reaudit_screening_rules.py', 'wrr_tr_common.py', 'wrr_r3_common.py']:
                shutil.copy2(ROOT / 'scripts' / name, root / 'scripts' / name)
            shutil.copy2(ROOT / 'configs/wrr_target_recovery_20261022.json', root / 'configs')
            shutil.copytree(ROOT / 'src/stream_recoverability', root / 'src/stream_recoverability', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            shutil.copy2(SNAPSHOT / 'daily_temperature.parquet', root / 'scratch/wrr_target_recovery_20261021/archive_daily.parquet')
            shutil.copy2(SNAPSHOT / 'station_years.parquet', root / 'results/wrr_target_recovery_20261021/e1_archive/station_years.parquet')
            for name in ['all_incomplete_year_bounds.csv', 'observed_record_certificates.csv']:
                shutil.copy2(SNAPSHOT / name, root / 'results/wrr_review_completion_20261024/observed_records' / name)
            for name in ['eligible_station_years.csv', 'witness_rules.csv', 'rule_summary.csv']:
                shutil.copy2(SNAPSHOT / name, root / 'results/wrr_review_response_20261027/rules' / name)
            for name in ['570_reaudit_observed_records.py', '571_reaudit_screening_rules.py']:
                proc = subprocess.run([sys.executable, str(root / 'scripts' / name)], cwd=root, capture_output=True, text=True)
                if proc.returncode:
                    raise RuntimeError(name + ' failed: ' + (proc.stdout + proc.stderr)[-2500:])
            audit = root / 'results/wrr_review_response_20261027/audit'
            observed = json.loads((audit / 'observed_record_independent_reaudit.json').read_text())
            rules = json.loads((audit / 'screening_rule_reaudit.json').read_text())
            if (not observed['passed'] or
                not rules['passed'] or
                observed['eligible_stations'] != manifest['included_eligible_stations'] or
                observed['certificate_station_years'] != manifest['original_witnesses_included'] or
                rules['witnesses_checked'] != manifest['original_witnesses_included']):
                raise ValueError('Recomputed observation or rule audit does not match snapshot scope')
            result.update({'status': 'passed', 'included_stations': observed['eligible_stations'],
                           'original_stations': manifest['total_original_eligible_stations'],
                           'excluded_by_provider': manifest['excluded_by_provider'],
                           'reference_station_years_recomputed': observed['reference_station_years_recomputed'],
                           'incomplete_station_years_recomputed': observed['incomplete_station_years_recomputed'],
                           'witness_station_years': observed['certificate_station_years'],
                           'rule_decisions_checked': rules['witness_rule_decisions_checked'],
                           'target_year_perturbation_probes': rules['target_year_perturbation_probes'],
                           'fixed_original_warm_fraction_source': 'saved station-year metadata, not independently recomputed',
                           'source_sensor_and_prior_qc_verified': False})
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        result.update({'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if result['status'] != 'passed':
        raise SystemExit(1)

if __name__ == '__main__':
    main()

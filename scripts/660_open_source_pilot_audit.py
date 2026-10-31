#!/usr/bin/env python3
"""Verify the first candidate-source archive pilot without interpreting scores."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import wrr_tr_common as T

ROOT = T.ROOT
REV = ROOT / 'results/wrr_review_response_20261027'
OUT = REV / 'open_source_sensitivity'
PRIVATE = ROOT / 'private/wrr_open_source_sensitivity_20261026'
BASE = REV / 'whole_archive'

def main():
    plan = json.loads((OUT / 'plan.json').read_text())
    model_receipts = json.loads((PRIVATE / 'refit_receipts.json').read_text())
    model = model_receipts['offline|foen']
    helper = T.load_script('open_pilot_verify', ROOT / 'scripts/658_open_source_archive_sensitivity.py')
    stage = PRIVATE / 'whole_archive_pilot_1'
    files = sorted(stage.glob('*/offline/replicate_00/*/open_source_receipt.json'))
    if len(files) != 20:
        raise ValueError('Pilot should contain two families for ten stations')
    stations, families = set(), set()
    model_path = PRIVATE / 'refits/leave_one_year_out/seed_00/foen.joblib'
    calpath = PRIVATE / 'calibrations/offline/foen.json'
    for path in files:
        target = path.parent
        family = path.relative_to(stage).parts[0]
        original = BASE / family / 'offline' / 'replicate_00' / target.name
        design = json.loads((target / 'design.json').read_text())
        old = json.loads((original / 'design.json').read_text())
        receipt = json.loads(path.read_text())
        if (design['masks'] != old['masks'] or
            design['station_key'] != old['station_key'] or
            design['hidden_values_present_in_visible_archive'] != 0):
            raise ValueError('Pilot cache, inputs, masks or model mismatch')
        helper.verify_plugin(original, target)
        stations.add(design['station_key']);families.add(family)
    if len(stations) != 10 or families != {'calendar', 'crossed'}:
        raise ValueError('Pilot target roster is incomplete')
    result = {'status': 'pilot_passed_no_accuracy_claim', 'mode': 'offline', 'region': 'foen',
              'stations': len(stations), 'families': sorted(families), 'replicates': 1,
              'archive_settings': len(files), 'same_masks': True, 'hidden_target_values_present': 0,
              'unchanged_plugin_and_target_slope': True,
              'model_source_roles_strict_region_verified': model['strict_target_region_positive_rows'] == 0,
              'models_completed_when_audited': len(model_receipts), 'models_planned': len(plan['target_mode_region_stations']),
              'limitation': 'Pilot checks implementation and fixed input identities on one replicate, not model accuracy or the full planned comparison. Case/model outputs remain local pending rights and provenance review.'}
    (OUT / 'pilot_status.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()

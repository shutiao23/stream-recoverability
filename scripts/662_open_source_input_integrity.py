#!/usr/bin/env python3
"""Independently compare the filtered local source cases with original Arrow data.

The allowed provider filter is applied independently to every column, not only
the model features. A passing check says nothing about provider permissions or
upstream case generation and does not expose values in the aggregate report.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_review_response_20261027/open_source_sensitivity'
SOURCE = ROOT / 'results/wrr_review_completion_20261024/cases'
PRIVATE = ROOT / 'private/wrr_open_source_sensitivity_20261026/candidate_cases'

def main():
    plan = json.loads((OUT / 'plan.json').read_text())
    allowed = pa.array(plan['allowed_providers'])
    rows = []
    for split in ['leave_one_year_out', 'before_2010']:
        path = PRIVATE / split / 'seed_00.parquet'
        if not path.exists():
            rows.append({'split': split, 'status': 'not_yet_created'})
            continue
        source_path = SOURCE / split / 'seed_00.parquet'
        original = pq.read_table(source_path)
        candidate = pq.read_table(path)
        expected = original.filter(pc.is_in(original['provider'], value_set=allowed))
        if not expected.schema.equals(candidate.schema, check_metadata=False) or not expected.equals(candidate, check_metadata=False):
            raise ValueError('Filtered candidate differs from exact provider-filtered original: ' + split)
        rows.append({'split': split, 'status': 'passed', 'original_rows': len(original),
                     'candidate_rows': len(candidate), 'columns': len(candidate.schema),
                     'all_columns_equal_after_provider_filter': True})
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(),
              'status': 'passed' if all(x['status']=='passed' for x in rows) else 'partial_in_progress',
              'splits': rows,
              'limitation': 'Exact identity of processed source cases only; not raw instrument data, source QC, legal reuse permission, role assignments, independent climate validation, or proof of all upstream dependencies.'}
    (OUT / 'candidate_input_integrity.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()

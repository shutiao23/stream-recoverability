#!/usr/bin/env python3
"""Record a post-hoc paired annual-interval sensitivity before computing it."""
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_review_response_20261027/open_source_sensitivity'
STAGE = ROOT / 'private/wrr_open_source_sensitivity_20261026/whole_archive'

def main():
    path = OUT / 'annual_sensitivity_plan.json'
    if path.exists():
        raise RuntimeError('Preserve existing plan')
    summary = json.loads((OUT / 'archive_summary_status.json').read_text())
    role = json.loads((OUT / 'candidate_source_role_audit.json').read_text())
    if summary['status'] != 'passed_complete_posthoc_sensitivity' or role['status'] != 'passed':
        raise ValueError('The source-filter and archive audits must be complete')
    receipts = sorted(STAGE.glob('*/?*/replicate_*/*/open_source_receipt.json'))
    if len(receipts) != 3320:
        raise ValueError('Incomplete archive receipts')
    for receipt in receipts:
        signature.update(str(receipt.relative_to(STAGE)).encode() + b'\0' + receipt.read_bytes())
    files = [ROOT / 'scripts/578_peak_visibility_diagnostics.py', ROOT / 'scripts/576_verify_private_annual_predictions.py',
             ROOT / 'results/wrr_review_response_20261027/whole_archive/peak_visibility_annual.csv']
    plan = {'created_utc': datetime.now(timezone.utc).isoformat(), 'status': 'posthoc_frozen_before_candidate_annual_scores',
            'receipt_count': len(receipts),
            'design': 'Compare both versions, both estimators, and all seven quantiles on the exact same incomplete-year cases. Report original availability and the four-way common cohort, bias, MAE, 90% coverage, width, interval score, assumed-tail CRPS and zero-width rates; separately stratify on complete-reference H30 relative to the observed lower bound.',
            'resampling': 'Resample connected groups jointly for the original and candidate score differences; report case-weighted and equal-group contrasts, plus descriptive leave-one-region-out results without model refitting.',
            'limitations': 'This study is after original and candidate trend results were inspected. It reuses target records, masks and daily refits; source providers, source role assignment and region exclusion changed together. The peak-visibility stratum depends on the hidden complete reference and is unavailable for deployment. Bootstrap groups are not necessarily independent climates; results do not establish coverage or legal redistribution rights.'}
    path.write_text(json.dumps(plan, indent=2)+'\n')
    print(json.dumps(plan, indent=2))

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Render selected matched-retention statistics without retuning a model."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/release_outputs'


def main():
    f=pd.read_csv(OUT/'matched_numerical_retention.csv')
    select=lambda c,k:f.loc[f.condition.eq(c)&f.family.eq(k)].iloc[0]
    clean=select('clean','calendar');future=select('future_years','crossed');air=select('air_exposure','calendar')
    source=pd.read_csv(OUT/'source_calibrated_release_summary.csv')
    source_audit=json.loads((OUT/'source_calibrated_audit.json').read_text())
    if not source_audit['passed']:raise RuntimeError('Source-calibrated target audit failed')
    src=lambda family,method:source.loc[source.family.eq(family)&source.method.eq(method)].iloc[0]
    st=src('calendar','three_outputs');ss=src('calendar','score_only')
    ct=src('crossed','three_outputs');cs=src('crossed','score_only')
    values={'MRCount':f'{int(clean.n_equal_numerical):,}','MRThreeBad':str(int(clean.three_output_bad)),
            'MRScoreBad':str(int(clean.score_only_bad)), 'MRThreeRisk':f'{100*clean.three_output_risk:.3f}',
            'MRScoreRisk':f'{100*clean.score_only_risk:.3f}',
            'MRFutureCount':f'{int(future.n_equal_numerical):,}',
            'MRFutureThree':f'{100*future.three_output_risk:.2f}',
            'MRFutureScore':f'{100*future.score_only_risk:.2f}',
            'MRAirCount':str(int(air.n_equal_numerical)),
            'MRAirThreeBad':str(int(air.three_output_bad)), 'MRAirScoreBad':str(int(air.score_only_bad)),
            'SRCThreeRetention':f'{100*st.retention:.1f}', 'SRCScoreRetention':f'{100*ss.retention:.1f}',
            'SRCThreeRisk':f'{100*st.risk:.3f}', 'SRCScoreRisk':f'{100*ss.risk:.3f}',
            'SRCGapThreeRetention':f'{100*ct.retention:.1f}', 'SRCGapScoreRetention':f'{100*cs.retention:.1f}',
            'SRCGapThreeRisk':f'{100*ct.risk:.2f}', 'SRCGapScoreRisk':f'{100*cs.risk:.2f}'}
    (ROOT/'paper/wrr_tr/release_matched_values.tex').write_text(''.join(
        '\\newcommand{\\'+name+'}{'+value+'}\n' for name,value in values.items()))
    status={'scope':'same numerical count on opened evaluation feature distributions; no label use in matching',
            'n_scenarios':len(f),'valid_matched_scenarios':int(f.n_equal_numerical.gt(0).sum()),
            'source_rule_audit_passed':source_audit['passed'],
            'zero_output_scenarios':int(f.n_equal_numerical.eq(0).sum()),
            'equal_count_all':bool((f.three_only==f.score_only).all()),
            'limitations':'transductive feature/count matching; different bounds and unknown states mean total information is not held equal; no prospective or group-safety guarantee'}
    (OUT/'matched_retention_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps(status,indent=2))
    if not status['equal_count_all']:raise SystemExit(1)

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Render the source-only projected-risk experiment and its limitations."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/projected_risk_sensitivity'
PAPER=ROOT/'paper/wrr_tr'


def only(frame,**filters):
    for key,value in filters.items():frame=frame[frame[key].eq(value)]
    if len(frame)!=1:raise ValueError('Unexpected projected-risk summary cell')
    return frame.iloc[0]


def main():
    audit=json.loads((OUT/'independent_audit.json').read_text())
    ref=json.loads((OUT/'reference_score_status.json').read_text())
    if audit['status']!='passed' or audit['summary_cells_checked']!=4 or ref['masked_cases']!=7583:
        raise ValueError('Projected-risk audit or reference verification incomplete')
    summary=pd.read_csv(OUT/'summary.csv')
    a=only(summary,family='crossed',comparison='source_threshold')
    b=only(summary,family='crossed',comparison='matched_target_count')
    vals={'PRCases':f'{int(a.n_masked):,}','PRGroups':str(int(a.n_groups)),
          'PROldCount':f'{int(a.old_selected):,}','PRNewCount':f'{int(a.new_selected):,}',
          'PROldRetention':f'{100*a.old_retention:.1f}','PRNewRetention':f'{100*a.new_retention:.1f}',
          'PROldFailure':f'{100*a.old_failure:.2f}','PRNewFailure':f'{100*a.new_failure:.2f}',
          'PRMatchedCount':f'{int(b.old_selected):,}','PRMatchedOldBad':str(int(b.old_bad)),
          'PRMatchedNewBad':str(int(b.new_bad)),'PRMatchedOldFailure':f'{100*b.old_failure:.2f}',
          'PRMatchedNewFailure':f'{100*b.new_failure:.2f}',
          'PRMatchedLow':f'{100*b.risk_difference_low:.2f}','PRMatchedHigh':f'{100*b.risk_difference_high:.2f}'}
    (PAPER/'projected_risk_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in vals.items()))
    lines=[]
    for family,flabel in [('calendar','Calendar'),('crossed','Controlled')]:
        for comparison,label in [('source_threshold','Source threshold'),('matched_target_count','Target count match')]:
            r=only(summary,family=family,comparison=comparison)
            lines.append(f"{flabel} & {label} & {int(r.n_masked):,} & {int(r.old_selected):,} / {int(r.new_selected):,} & {int(r.old_bad)} / {int(r.new_bad)} & {100*r.old_failure:.2f} / {100*r.new_failure:.2f} \\\\")
    text=r'''\section{Exploratory projected-point failure score}
After inspecting prior projection and risk results, we fitted six region-specific binary classifiers to identify absolute D2 point error above 0.5 $^{\circ}$C after the observed-bound projection. For each target region, the source estimator, interval-calibration, risk-learning and rule-calibration connected-group roles are disjoint, all groups appearing in the target region are excluded, and forward source cases precede 2010. Training uses the assigned risk-learning source groups, weighted equally by connected group. The new classifier uses the existing decision-time feature matrix, the projected 90\% interval width and the projected point's distance above the visible bound; neither the old risk score nor the held reference is a predictor. Each model uses 120 low-leaf-count boosted trees with the fixed settings documented in the analysis plan. Six to eight source training groups contribute per model.

For each region and mask family, separate source rule-calibration groups select an old-score and a new-score cutoff to approximate 80\% group-equal-weight numerical retention on valid source cases, without using failure labels to choose the cutoff. Both cutoffs are fixed before target scoring. Target numerical retention can differ. A second, transductive comparison ranks the new target scores and matches the old-score numerical count separately within each target region and family; ties are broken deterministically without target outcomes. It is not a prospective cutoff, and equal counts need not retain the same years or bound values.

The candidate annual caches contained no reference H30 values. Therefore source models, source cutoffs, target scores and selections were saved first; the target reference was then joined by station, masked year, family and replicate from the separately saved complete-archive record. A second comparison against the original source station--year--family H30 verified all 7,583 reference values, and the saved selections did not change. These target archives and source data had nevertheless been inspected in earlier analyses; this is not an unopened reference experiment.

Table~\ref{tab:projected-risk} gives pooled forward results. Source thresholds in the controlled-gap family give old/new numerical retention \PROldRetention\% / \PRNewRetention\% and selected failure \PROldFailure\% / \PRNewFailure\%. At the matched \PRMatchedCount{} outputs, the original and projected-risk scores have \PRMatchedOldBad{} and \PRMatchedNewBad{} failures, respectively; the connected-group bootstrap interval for the difference in selected failure rates (new minus old) is [\PRMatchedLow, \PRMatchedHigh] percentage points. Group resampling is descriptive and repeated masks are not independent climates. The old classifier targeted an unprojected point; the new classifier targets the projected point, but a better-aligned training label does not itself imply better deployment decisions. The source masks degrade one year at a time, while target archives are jointly degraded across years. These results do not establish calibrated probabilities, group-level risk control, natural-outage performance or independent-climate transfer.

\begin{table}[ht]
\caption{Forward annual failure comparison, old raw score / projected-point score. An error exceeds 0.5 $^{\circ}$C. Source-threshold counts can differ; the target count match is transductive and uses no target outcomes.}
\label{tab:projected-risk}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{llrrrr}\toprule
Mask & Selection & Cases & Numerical & Failures & Failure (\%) \\
\midrule
'''+'\n'.join(lines)+r'''
\bottomrule\end{tabular}}\end{table}

The independent audit refits the six classifiers using the same source records and feature implementation, rechecks the disjoint roles, reproduces the twelve family-specific source threshold pairs, reconstructs all target scores and label-free selections, and recomputes group bootstrap and region-deletion summaries. It also checks reference attachment against both saved reference sources. It does not independently reconstruct physical observations, establish source permissions or verify the classifier's prospective reliability.
'''
    (PAPER/'projected_risk_supporting.tex').write_text(text)
    print('Rendered projection-aware risk sensitivity')


if __name__=='__main__':main()

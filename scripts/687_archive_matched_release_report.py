#!/usr/bin/env python3
"""Render the post-hoc equal-numerical-count archive comparison."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/wrr_review_response_20261027/archive_matched_release_trend'
PAPER = ROOT/'paper/wrr_tr'


def main():
    audit = json.loads((OUT/'independent_audit.json').read_text())
    if audit['status'] != 'passed' or audit['archive_settings_checked'] != 3320:
        raise ValueError('Independent archive audit is incomplete')
    likelihood = json.loads((OUT/'independent_likelihood_audit.json').read_text())
    if likelihood['working_fits_checked'] != 6640 or likelihood['common_difference_above_1e_5']:
        raise ValueError('Independent likelihood replay is incomplete or differs by more than tolerance')
    table = pd.read_csv(OUT/'summary.csv')
    if len(table) != 8 or not table.n_archives.eq(table.n_matched_archives).all():
        raise ValueError('Unexpected matched summary')
    f = table[(table.family == 'crossed') & (table['mode'] == 'forward') & (table.method == 'values_and_bounds')].iloc[0]
    values = {'AMCases':f'{int(f.n_common):,}', 'AMGroups':str(int(f.n_common_groups)),
              'AMNumerical':f'{int(f.n_numeric):,}', 'AMBadOriginal':str(int(f.n_original_bad)), 'AMBadScore':str(int(f.n_score_bad)),
              'AMBounds':str(int(f.n_original_bound)), 'AMOriginalRMSE':f'{f.rmse_original:.4f}', 'AMScoreRMSE':f'{f.rmse_score:.4f}',
              'AMBootstrapLow':f'{f.bootstrap_low:.4f}', 'AMBootstrapHigh':f'{f.bootstrap_high:.4f}'}
    (PAPER/'archive_matched_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in values.items()))
    descriptions = {('calendar','offline'):'Calendar, offline', ('calendar','forward'):'Calendar, forward',
                    ('crossed','offline'):'Controlled, offline', ('crossed','forward'):'Controlled, forward'}
    lines = []
    for key in descriptions:
        row = table[(table.family == key[0]) & (table['mode'] == key[1]) & (table.method == 'values_and_bounds')].iloc[0]
        lines.append(f"{descriptions[key]} & {int(row.n_numeric):,} & {int(row.n_original_bad)} / {int(row.n_score_bad)} & {int(row.n_original_bound)} / {int(row.n_score_bound)} & {int(row.n_common)} & {row.rmse_original:.4f} / {row.rmse_score:.4f} \\\\")
    content = r'''\section{Matched numerical release within each archive}
After the original release and trend results were inspected, we fixed a further descriptive comparison on the same 3,320 archive settings. In each archive the three-output rule's number of numerical releases was matched exactly by choosing the lowest available raw classifier scores; equal scores were broken by year, and the existing detected-quality exclusion was applied to both rules. The choice uses the target archive's score distribution and its original release count, but no reference outcomes. It is therefore transductive and not a prospective release threshold. The same observed years and D2 estimates are used, while the selected years can differ. Nonselected years retain a visible lower bound if allowed by the same quality flag, and otherwise remain unknown. An unassessed quality diagnostic does not count as a detected flag in this analysis, as in the original pipeline.

Table~\ref{tab:archive-matched-release} gives annual errors and working-likelihood trend RMSE; lower-bound counts are not an assertion that the same years or bound values were retained. The number of numerical outputs is matched within each archive, but equal counts do not establish equal total information or comparable prospective risks. Repeated masks are not independent climates. A connected-group bootstrap of paired squared-error differences for forward controlled gaps gives [\AMBootstrapLow, \AMBootstrapHigh] $({}^{\circ}\mathrm{C}/\mathrm{decade})^2$; this is descriptive and spans zero. The likelihood treats released predictions as exact, censoring may be informative, and its intervals are not calibrated missingness-only uncertainty. No model was refitted for this comparison.

\begin{table}[ht]
\caption{Per-archive matched numerical output. Annual errors exceed 0.5 $^{\circ}$C. Counts and RMSE are original three-output rule / score-only comparator; RMSE uses common converged release-plus-bound working-likelihood fits and units $^{\circ}$C per decade.}
\label{tab:archive-matched-release}
\centering\small
\begin{tabular}{lrrrrr}\toprule
Scenario & Numeric & Errors & Bounds & Fits & RMSE \\
\midrule
''' + '\n'.join(lines) + r'''
\bottomrule\end{tabular}\end{table}

The audit separately reconstructed the selection masks for all 3,320 archives using Python ordering, recomputed 3,319 available score-comparator numerical-only OLS slopes and checked all eight summary cells. A second implementation refitted all 6,640 rule-by-archive censored likelihoods using normal log-density and survival functions. Convergence status agreed for every fit; 6,638 converged in both implementations, and their largest slope difference was approximately $1.2\times10^{-6}$ $^{\circ}$C per decade. This numerical check used the same observations, selected cases and working likelihood; it did not independently reconstruct source sensors or models, establish likelihood validity or verify interval standard errors.
'''
    (PAPER/'archive_matched_supporting.tex').write_text(content)
    print('Rendered matched archive values and supporting text')


if __name__ == '__main__':
    main()

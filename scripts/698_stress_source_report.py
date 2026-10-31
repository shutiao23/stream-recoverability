#!/usr/bin/env python3
"""Render six-way common source-model stress comparison for the paper."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/expanded_stress_source_sensitivity'
PAPER=ROOT/'paper/wrr_tr'


def only(frame,**filters):
    for col,val in filters.items():frame=frame[frame[col].eq(val)]
    if len(frame)!=1:raise ValueError(f'Expected one comparison: {filters}')
    return frame.iloc[0]


def main():
    audit=json.loads((OUT/'independent_audit.json').read_text())
    if audit['status']!='passed' or audit['summary_cells_checked']!=24:
        raise ValueError('Six-way independent summary audit incomplete')
    baseline=json.loads((OUT/'baseline_audit.json').read_text())
    if baseline['status']!='passed' or baseline['candidate_baseline_receipts_verified']!=205 or baseline['strict_huc17_baselines_replayed']!=15:
        raise ValueError('Source baseline replay is incomplete')
    data=pd.read_csv(OUT/'six_way_summary.csv')
    donor={v:only(data,scenario='synchronized_donors',estimator='D2',dependence='point',version=v)
           for v in ['strict_original','candidate']}
    values={'SDSCases':str(int(donor['candidate'].n_common_six_way)),
            'SDSStrictBase':f"{donor['strict_original'].baseline_rmse:.4f}",
            'SDSStrictDonor':f"{donor['strict_original'].stress_rmse:.4f}",
            'SDSCandidateBase':f"{donor['candidate'].baseline_rmse:.4f}",
            'SDSCandidateDonor':f"{donor['candidate'].stress_rmse:.4f}"}
    (PAPER/'stress_source_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in values.items()))
    lines=[]
    for scenario,short in [('synchronized_donors','Donor gaps'),('heat_associated_matched','Heat, fixed years')]:
        for estimator,label in [('D2','D2'),('stochastic_calibrated','Stochastic')]:
            for version,name in [('original','Original'),('strict_original','Strict'),('candidate','Candidate')]:
                a=only(data,scenario=scenario,estimator=estimator,dependence='independent',version=version)
                lines.append(f"{short} & {label} & {name} & {int(a.n_common_six_way)} & {a.baseline_rmse:.4f} / {a.stress_rmse:.4f} & {100*a.baseline_missing_coverage95:.1f} / {100*a.stress_missing_coverage95:.1f} & {a.baseline_width95:.3f} / {a.stress_width95:.3f} & {a.baseline_interval_score95:.3f} / {a.stress_interval_score95:.3f} \\\\")
    text=r'''\section{Source-model sensitivity of expanded stresses}
Following inspection of the original source-role audit and expanded stress results, we replayed the stressed daily features and masks through two already fitted alternative source-model sets. The strict-original version replaces only the forward HUC17 model, the sole affected target region in this cohort, with the model refitted after excluding every HUC17 connected group from its source roles; other source assignments remain as before. This removes source cases and changes source sample size. The candidate version replaces the models for all six forward target regions with the separately refitted candidate-provider models, which exclude all target-region groups but also change source providers, source sample size and role assignments. Source-model outputs and calibration offsets are recalculated; the previously fitted local daily features and target masks remain fixed. Neither comparison is prospective or a clean causal experiment for a single change.

Table~\ref{tab:stress-source-sensitivity} uses, separately for each estimator and stress, only archives available under both baseline and stress in all three source versions. The independent annual-rank intervals use the same six-way common interval cohort, with the same normal-spacing tail assumptions. D2 has 205 common archives; the stochastic method has 190 for donor gaps and 187 for the fixed-count heat stress. Repeated masks are not independent climates. Descriptive connected-group bootstrap and fixed-prediction region deletion results accompany the aggregate files. In the heat scenario the number of masked years is fixed within archive, but the number and placement of hidden days can change; in the donor scenario target masks are identical. These simulations do not verify a natural outage mechanism or transfer to new climates.

\begin{table}[ht]
\caption{Source-model sensitivity on six-way common archives, baseline / stress. RMSE, width and score use $^{\circ}$C per decade; coverage is the nominal 95\% trend interval percentage. Strict changes only the affected HUC17 source model; candidate changes source providers and assignments across all regions.}
\label{tab:stress-source-sensitivity}\centering\small
\resizebox{\linewidth}{!}{\begin{tabular}{lllrrrrr}\toprule
Scenario & Estimator & Source & Cases & RMSE & Coverage & Width & Score \\
\midrule
'''+'\n'.join(lines)+r'''
\bottomrule\end{tabular}}\end{table}

The source-role audit checked the positive-weight roles of the original and alternative models. All 440 alternative stress reanalyses preserved the target masks, hidden-value checks, plug-in values and observed lower bounds. The audit checked all 205 candidate baseline receipts against their source models, calibration, original features and saved outputs, and replayed the 15 affected strict-original baselines, including 60 annual predictions and 180 trend rows. A second implementation independently recomputed the six-way common cohorts, 24 aggregate cells, 144 region-deletion cells and 4,000 group bootstrap draws per cell from 9,840 saved case rows. These checks did not independently refit source models, check sensor accuracy or validate climate transfer.
'''
    (PAPER/'stress_source_supporting.tex').write_text(text)
    print('Rendered stress source-model sensitivity')


if __name__=='__main__':main()

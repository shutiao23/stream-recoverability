#!/usr/bin/env python3
"""Recreate manuscript figures 2--5 from supplied aggregate CSV tables.

No daily inputs, model fitting, case-level verification, or independent
validation is performed by this script; see the package README.
"""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from stream_recoverability.experiments.tr_revision.review_figures import (
    plot_aggregate_figures, set_review_style,
)

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=ROOT/'results/wrr_review_response_20261027')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/reviewer_recreated_figures')
    args=parser.parse_args(); results=args.results
    score=pd.read_csv(results/'annual/source_scorecard_summary.csv')
    trend=pd.read_csv(results/'whole_archive/trend_summary.csv')
    trend_cases=pd.read_csv(results/'whole_archive/trends.csv')
    uncertainty=pd.read_csv(results/'whole_archive/uncertainty_paired_summary.csv')
    uncertainty_cases=pd.read_csv(results/'whole_archive/uncertainty_common_cases.csv')
    ci_path=results/'whole_archive/figure_uncertainty_bootstrap.csv'
    if not ci_path.is_file():
        raise FileNotFoundError('Required group-interval table is missing: '+str(ci_path))
    uncertainty_ci=pd.read_csv(ci_path)
    factor=pd.read_csv(results/'whole_archive/factorial_paired_summary.csv')
    annual=pd.read_csv(results/'whole_archive/annual_summary.csv')
    states=pd.read_csv(results/'release_outputs/output_states.csv')
    releases=pd.read_csv(results/'release_outputs/release_metrics.csv')
    args.output.mkdir(parents=True,exist_ok=True)
    set_review_style()
    def save(fig,name):
        fig.tight_layout()
        fig.savefig(args.output/(name+'.pdf'),bbox_inches='tight')
        fig.savefig(args.output/(name+'.png'),dpi=170,bbox_inches='tight')
        plt.close(fig)
    plot_aggregate_figures(score,trend,factor,annual,states,releases,save,
        trend_cases=trend_cases,uncertainty=uncertainty,uncertainty_ci=uncertainty_ci,
        uncertainty_cases=uncertainty_cases)
    print(f'Four figures generated in {args.output}. Input summaries are assumed, not independently re-evaluated.')

if __name__=='__main__':main()

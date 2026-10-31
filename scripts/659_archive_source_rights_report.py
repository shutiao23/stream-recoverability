#!/usr/bin/env python3
"""Render checked aggregate source-rights dependencies for the paper."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'results/wrr_review_response_20261027/audit'
PAPER = ROOT / 'paper/wrr_tr'


def main():
    status = json.loads((AUDIT / 'archive_restricted_source_roles.json').read_text())
    x = pd.read_csv(AUDIT / 'archive_restricted_source_roles.csv')
    if status['status'] != 'passed_with_dependency_found' or x.duplicated(['mode', 'region', 'role']).any():
        raise ValueError('Source dependency audit is incomplete or duplicated')
    est = x.loc[x.role.eq('estimator')]
    cal = x.loc[x.role.eq('interval_calibration')]
    if (len(est) != status['model_mode_region_combinations'] or
        int(est.lubw_positive_weight_case_rows.gt(0).sum()) != status['estimator_combinations_with_lubw_positive_weight'] or
        int(cal.lubw_positive_weight_case_rows.gt(0).sum()) != status['interval_calibration_combinations_with_lubw_positive_weight']):
        raise ValueError('Source dependency audit counts differ')
    values = {'RightsModelCombinations': len(est), 'RightsEstimatorLUBW': int(est.lubw_positive_weight_case_rows.gt(0).sum()),
              'RightsCalibrationLUBW': int(cal.lubw_positive_weight_case_rows.gt(0).sum())}
    candidate = ROOT / 'results/wrr_review_response_20261027/open_source_sensitivity'
    donor = json.loads((candidate / 'donor_provenance_status.json').read_text())
    donor_independent = json.loads((candidate / 'donor_provenance_independent_audit.json').read_text())
    metadata = json.loads((candidate / 'donor_metadata_independent_audit.json').read_text())
    daily = json.loads((candidate / 'donor_usgs_daily_comparison.json').read_text())
    daily_audit = json.loads((candidate / 'donor_usgs_daily_independent_audit.json').read_text())
    ambiguity = json.loads((candidate / 'donor_usgs_ambiguous_summary.json').read_text())
    ambiguity_audit = json.loads((candidate / 'donor_usgs_ambiguous_independent_audit.json').read_text())
    roles = pd.read_csv(candidate / 'donor_provenance_roles.csv')
    if (not donor['donor_visibility_counts_match_saved_cases'] or donor_independent['status'] != 'passed'
            or metadata['status'] != 'passed_metadata_identity_checks' or daily_audit['status'] != 'passed'
            or ambiguity_audit['status'] != 'passed' or len(roles) != 52):
        raise ValueError('Candidate donor provenance audit is incomplete')
    exposed = int(roles.finite_donor_estimate_outside_all_catalogs.gt(0).sum())
    (PAPER / 'source_rights_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+str(v)+'}\n' for k, v in values.items()))
    lines = [r'\section{Source-provider dependence of whole-archive models}',
       ('The 42 whole-archive target stations belong to providers with recorded reuse paths, '
        'but source-model training has additional provenance. Recomputing the source role assignments '
        'and checking them against all ' + str(len(est)) + ' saved seed-zero model bundles shows that '
        + str(values['RightsEstimatorLUBW']) + ' estimator roles and ' + str(values['RightsCalibrationLUBW']) +
        ' interval-calibration roles have positive-weight LUBW source cases. Source cases are repeated '
        'masks; their counts are not independent observations. Positive source weights establish model '
        'dependence but do not resolve the legal status of any particular derivative. Individual source, '
        'model, target, mask and reviewer-access rights still require confirmation. A post-hoc '
        'candidate-provider strict-region refit is reported separately and does not replace the main results.'),
       ('A subsequent post-hoc audit reconstructed donor visibility for all 194,370 eligible candidate source-case '
        'rows using the saved masks and processed panels, and checked the counts against the stored cases. '
        'In ' + str(exposed) + ' of 52 mode--region--role cells, some positive-weight rows had a finite '
        'donor-regression estimate while a visible donor was absent from the original three local catalogs. '
        'These are repeated rows, not independent sites or evidence of unauthorized use. The 73 such '
        'USGS panel-column occurrences correspond to 69 identifiers, all returned by the USGS site metadata '
        'service; one GKD column has a matching project-generated network-QC record. The independent '
        'check re-evaluated 156 selected source cases and all 52 role cells. Site-number existence and '
        'project QC metadata do not establish the original provenance of cached temperature values, '
        'complete processing lineage, or permission to redistribute derived models. The public site '
        'metadata snapshot can be replayed separately; source panel mappings remain local.'),
       ('After the metadata audit, we retrieved current USGS daily-mean water temperatures for those '
        '69 sites. Of ' + f"{daily['local_finite_days']:,}" + ' finite local panel-column days, '
        + f"{daily['compared_days']:,}" + ' had a single distinct finite USGS value and all agreed within '
        '$10^{-6}$ $^{\\circ}$C. Another ' + f"{ambiguity['ambiguous_panel_column_days']:,}" +
        ' had multiple distinct USGS values; every local value matched at least one alternative, but '
        'that post-hoc match does not determine which series was used historically. Their median '
        'within-day range was ' + f"{ambiguity['median_range_c']:.1f}" + ' $^{\\circ}$C; '
        + str(ambiguity['no_finite_source_days']) + ' local days had no finite returned value. '
        'These are repeated panel-column days, not independent site-days. A separate implementation '
        'recomputed all comparisons. The current public responses are included for source-only replay; '
        'they do not establish historic data vintage, sensor quality or derivative permissions.'),
       r'\begin{table}[p]\centering\small',
       r'\caption{LUBW cases with positive source-role weights, not independent station counts. Groups with bootstrap multiplicity zero do not contribute.}\label{tab:rights-roles}',
       r'\begin{tabular}{llrr}\toprule',
       r'Mode & Region & Estimator case rows & Interval calibration case rows\\\midrule']
    for _, r in est.sort_values(['mode','region']).iterrows():
        c = cal.loc[cal['mode'].eq(r['mode']) & cal.region.eq(r.region)]
        if len(c) != 1:
            raise ValueError('Estimator/calibration role pair missing')
        region = r.region.replace('_', r'\_')
        lines.append(f"{r['mode']} & {region} & {int(r.lubw_positive_weight_case_rows)} & {int(c.iloc[0].lubw_positive_weight_case_rows)}" + r'\\')
    lines += [r'\bottomrule\end{tabular}', r'\end{table}']
    (PAPER / 'source_rights_supporting.tex').write_text('\n'.join(lines) + '\n')
    print(json.dumps(values, indent=2))


if __name__ == '__main__':
    main()

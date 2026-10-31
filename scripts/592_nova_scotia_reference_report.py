#!/usr/bin/env python3
"""Audit and report the Nova Scotia reported-label and release comparison."""
import calendar
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified'
PAPER=ROOT/'paper/wrr_tr'


def main():
    workbook=json.loads((OUT/'reported_label_status.json').read_text());portal=json.loads((OUT/'portal_label_status.json').read_text())
    comp=json.loads((OUT/'portal_workbook_status.json').read_text());diag=json.loads((OUT/'portal_difference_status.json').read_text())
    prior=json.loads((OUT/'prior_contact_audit.json').read_text())
    if workbook['status']!='label_completeness_computed' or portal['status']!='portal_label_completeness_computed' or comp['status']!='comparison_computed' or diag['status']!='passed':
        raise RuntimeError('one or more Nova Scotia evidence steps are incomplete')
    if prior['status']!='checked' or prior['candidates']!=4:raise RuntimeError('prior identifier check is incomplete')
    overlap=pd.read_csv(OUT/'complete_label_year_overlap.csv');diff=pd.read_csv(OUT/'portal_difference_by_year.csv')
    if overlap.duplicated(['station_id','year']).any() or diff.duplicated(['station_id','year']).any():raise ValueError('duplicate station-year in comparison')
    common=overlap.loc[overlap.complete_label_year_workbook & overlap.complete_label_year_portal].merge(diff,on=['station_id','year'],how='left',validate='one_to_one')
    if len(common)!=diag['year_pairs_both_complete_labels'] or common.both_numeric.isna().any():raise ValueError('common complete-label denominator mismatch')
    expected=common.year.map(lambda y:(366 if calendar.isleap(y) else 365)*24)
    common['identical_all_numeric_1e6']=common.both_numeric.eq(expected)&common['difference_gt_1e-06'].eq(0)&common.workbook_only_unique_labels.eq(0)&common.portal_only_unique_labels.eq(0)
    common['within_0p01_all_numeric']=common.both_numeric.eq(expected)&common['difference_gt_0p01'].eq(0)&common.workbook_only_unique_labels.eq(0)&common.portal_only_unique_labels.eq(0)
    common.to_csv(OUT/'common_complete_label_years.csv',index=False)
    w=pd.read_csv(OUT/'reported_label_site_summary.csv');p=pd.read_csv(OUT/'portal_label_site_summary.csv')
    summary=w[['station_id','possible_complete_label_years']].merge(p[['station_id','possible_complete_label_years']],on='station_id',suffixes=('_workbook','_portal'),validate='one_to_one')
    grouped=common.groupby('station_id').agg(common_complete_labels=('year','size'),fully_equal_1e6=('identical_all_numeric_1e6','sum'),within_0p01=('within_0p01_all_numeric','sum')).reset_index()
    summary=summary.merge(grouped,on='station_id',how='left',validate='one_to_one').fillna({'common_complete_labels':0,'fully_equal_1e6':0,'within_0p01':0})
    summary['four_or_more_equal_complete_label_years']=summary.fully_equal_1e6.ge(4)
    summary.to_csv(OUT/'common_complete_label_site_summary.csv',index=False)
    if int(common.identical_all_numeric_1e6.sum())>len(common) or diag['both_numeric']!=comp['both_numeric']:
        raise ValueError('shared release arithmetic inconsistent')
    report={'status':'passed','stations_screened':len(summary),'workbook_complete_label_years':workbook['complete_reported_label_years'],
        'portal_complete_label_years':portal['complete_reported_label_years'],'common_complete_label_years':len(common),
        'common_complete_label_years_equal_1e6':int(common.identical_all_numeric_1e6.sum()),
        'stations_with_four_equal_complete_label_years':int(summary.four_or_more_equal_complete_label_years.sum()),
        'shared_unique_both_numeric_labels':diag['both_numeric'],'numeric_different_at_1e6':diag['difference_gt_1e-06'],
        'numeric_different_over_0p01_c':diag['difference_gt_0p01'],'numeric_different_over_0p5_c':diag['difference_gt_0p5'],
        'maximum_abs_difference_c':diag['maximum_abs_difference_c'],
        'named_inventory_exact_id_matches':sum(len(x['exact_candidate_matches']) for x in prior['inventories']),
        'strict_reference_qualification':'not established','reconstruction_scored_in_original_reference_screen':False,
        'separate_exploratory_score_exists':(ROOT/'results/wrr_review_response_20261027/external_nova_scotia_exploratory/score_status.json').exists(),
        'limitation':'two releases of one provincial programme; reported labels are not validated physical hours; point-level QA, estimated values, local timezone and station independence remain unresolved; 0.01 and 0.5 C thresholds were chosen after inspecting the first comparison'}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=[r'\section{Nova Scotia verified workbooks and open-portal comparison}',
      ('Four river locations were fixed from the provider’s historical workbook list before opening their temperature sequences. '
       'The workbooks are labelled verified, but their inspected headers do not identify per-hour temperature quality or estimated-value flags; '
       'one header states UTC--04:00 and the remaining headers do not establish a time basis. '
       'We count complete reported clock-label years, requiring 24 unique hourly labels with finite numeric cells per calendar day, '
       'without claiming these labels correspond to 24 independent physical hours or nonestimated values. '
       'The openly licensed portal was accessed only after the workbook completeness screen; it is another release of the same monitoring programme, not an independent sensor. '
       'Of '+str(len(common))+' station-years with complete labels in both releases, '+str(int(common.identical_all_numeric_1e6.sum()))+
       ' have every numeric value equal within the originally specified $10^{-6}$ $^{\circ}$C tolerance. '
       'These include at least four such years at '+str(int(summary.four_or_more_equal_complete_label_years.sum()))+' stations. '
       'Across '+format(diag['both_numeric'],',')+' shared unique numeric labels, '+format(diag['difference_gt_1e-06'],',')+
       ' differ at that tolerance; '+format(diag['difference_gt_0p5'],',')+' exceed 0.5 $^{\circ}$C in a post-hoc diagnostic, '
       'with a maximum '+f"{diag['maximum_abs_difference_c']:.3f}"+' $^{\circ}$C. '
       'These comparisons do not identify which version is correct, and clock-label matching does not resolve physical time. '
       'The original reference screen did not score a reconstruction method; a later, explicitly exploratory amendment is reported separately. The portal source is Government of Nova Scotia, dataset bkfi-mjgw, '
       'Open Government Licence -- Nova Scotia; legacy workbook reuse remains unresolved.'),
      r'\begin{table}[p]\centering\small',
      r'\caption{Retrospective 2009--2017 reported-label completeness and release concordance. Equal means that every hourly numeric value in the common complete-label year matches to $10^{-6}$ $^{\circ}$C at the same reported clock label. Quality, estimated-value status, time basis and climate independence are not established.}\label{tab:nova-scotia-reference}',
      r'\begin{tabular}{lrrrr}\toprule',
      r'Station & Workbook & Portal & Both & Fully equal\\\midrule']
    for r in summary.sort_values('station_id').itertuples(index=False):
        lines.append(' & '.join(map(str,[r.station_id,int(r.possible_complete_label_years_workbook),int(r.possible_complete_label_years_portal),int(r.common_complete_labels),int(r.fully_equal_1e6)]))+r'\\')
    lines.extend([r'\bottomrule\end{tabular}',r'\end{table}'])
    (PAPER/'nova_scotia_reference_supporting.tex').write_text('\n'.join(lines)+'\n')
    print(summary.to_string(index=False));print(json.dumps(report,indent=2))

if __name__=='__main__':main()

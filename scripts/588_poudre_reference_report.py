#!/usr/bin/env python3
"""Cross-check and report the frozen Poudre raw-archive qualification."""
import calendar
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_csu_ross'
DATA=ROOT/'data/external/wrr_poudre_ross_20261026'
PAPER=ROOT/'paper/wrr_tr'

def main():
    plan=json.loads((OUT/'qualification_plan.json').read_text());status=json.loads((OUT/'qualification_status.json').read_text())
    receipt=json.loads((OUT/'acquisition.json').read_text());unit=json.loads((OUT/'qualification_unit_mapping.json').read_text())
    years=pd.read_csv(OUT/'qualification_years.csv');flags=pd.read_csv(OUT/'qualification_qc_counts.csv',keep_default_na=False)
    candidates=pd.read_csv(OUT/'candidate_qualification.csv');roster=pd.read_csv(OUT/'candidate_roster.csv')
    if status['status']!='qualification_computed' or receipt['status']!='acquired':raise ValueError('source intake not complete')
    if set(roster.site)!=set(plan['candidates']) or set(candidates.site)!=set(plan['candidates']) or len(years)!=len(plan['candidates'])*len(plan['years_utc']):
        raise ValueError('candidate or year denominator differs')
    if years.duplicated(['site','year']).any() or set(years.year)!=set(plan['years_utc']):raise ValueError('duplicate or unexpected years')
    for r in years.itertuples(index=False):
        days=366 if calendar.isleap(r.year) else 365
        if r.calendar_days!=days or r.expected_quarter_hours!=96*days or r.complete_days+r.missing_days!=days:
            raise ValueError('calendar denominator differs')
        group=flags.loc[flags.site.eq(r.site)&flags.year.eq(r.year)]
        if int(group.rows.sum())!=r.source_rows or int((group.rows-group.finite_values).sum())!=r.nonfinite_rows:
            raise ValueError('quality counts differ from source-row totals')
        rejected=~group.qc_status.eq('PASS')|~group.unit_ok
        if int(group.loc[rejected,'rows'].sum())!=r.disallowed_flag_rows:raise ValueError('rejected quality/unit counts differ')
        if r.duplicate_rows==0 and r.off_grid_rows==0 and r.missing_quarter_hour_timestamps!=r.expected_quarter_hours-r.source_rows:
            raise ValueError('timestamp counts inconsistent')
    if int(years.qualified.sum())!=status['author_pass_complete_years'] or int(years.missing_quarter_hour_timestamps.gt(0).sum())!=status['site_years_with_missing_quarter_hour_timestamps']:
        raise ValueError('qualification status differs')
    for item in receipt['files']:
        with (DATA/item['file_name']).open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
    report={'status':'passed','sites':len(candidates),'site_years':len(years),
       'complete_author_pass_years':int(years.qualified.sum()),
       'site_years_missing_quarter_hour_timestamps':int(years.missing_quarter_hour_timestamps.gt(0).sum()),
       'minimum_missing_quarter_hour_timestamps':int(years.missing_quarter_hour_timestamps.min()),
       'sites_with_four_complete_author_pass_years':int(candidates.four_complete_author_pass_years.sum()),
       'scored_reconstruction':False,'source_files':len(receipt['files']),'unit_mapping':unit['interpretation'],
       'limitation':'only four metadata-selected locations, one watershed, no independent-climate conclusion; raw files contain additional unexamined sites and parameters; 2019-2021 technician calibration records were not collected'}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    text=[r'\section{Poudre Water Quality Network reference qualification}',
      ('A metadata-only screen selected four locations whose source periods span at least four UTC years in 2020--2024. '
       'The selected sites share one watershed; older USGS station metadata from the same river had already been encountered, '
       'and exact prior-network connections remain unresolved. Before opening temperatures, we fixed a criterion of '
       '96 unique quarter-hour UTC observations per day, finite post-processing values in degrees Celsius and author PASS status. '
       'The author metadata describes the unit as degrees C, while the source file uses C; that notation mapping was recorded '
       'after inspecting unit labels and before calculating completeness. None of the 20 site-years qualifies; each lacks '
       'at least '+str(report['minimum_missing_quarter_hour_timestamps'])+' distinct quarter-hour timestamps even before '
       'the value and quality filters. Thus no recovery model was scored. Source files contain other sites and parameters that '
       'were not qualified here. The authors note that technician calibration records were not collected for 2019--2021; '
       'PASS flags do not prove error-free sensors or independent climates. Source: Struthers et al. (2026), '
       'DOI 10.4211/hs.521e317e189e498581d0aaa08c3f32bc, CC BY 4.0.'),
      r'\begin{table}[p]\centering\scriptsize',
      r'\caption{Author PASS, finite-value and 96-quarter-hour qualification for the four metadata-selected Poudre sites. Missing timestamps are counted independently of quality flags; incomplete days can also contain nonfinite or non-PASS records. These are four sites within one watershed.}\label{tab:poudre-reference}',
      r'\begin{tabular}{lrrrrrr}\toprule',
      r'Site & Year & Calendar days & Complete days & Missing timestamps & Nonfinite & Not PASS\\\midrule']
    for r in years.sort_values(['site','year']).itertuples(index=False):
        text.append(' & '.join(map(str,[r.site,r.year,r.calendar_days,r.complete_days,r.missing_quarter_hour_timestamps,r.nonfinite_rows,r.disallowed_flag_rows]))+r'\\')
    text.extend([r'\bottomrule\end{tabular}',r'\end{table}'])
    (PAPER/'poudre_reference_supporting.tex').write_text('\n'.join(text)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

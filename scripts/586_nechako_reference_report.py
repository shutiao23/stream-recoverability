#!/usr/bin/env python3
"""Cross-check and report the frozen Nechako candidate qualification."""
import calendar
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nechako_nhg'
PAPER=ROOT/'paper/wrr_tr'

def main():
    plan=json.loads((OUT/'plan.json').read_text());receipt=json.loads((OUT/'acquisition.json').read_text());state=json.loads((OUT/'qualification_status.json').read_text())
    roster=pd.read_csv(OUT/'metadata_roster.csv');candidate=pd.read_csv(OUT/'candidate_roster.csv')
    years=pd.read_csv(OUT/'qualification_years.csv');flags=pd.read_csv(OUT/'qualification_flags.csv')
    if len(roster)!=plan['published_site_count'] or len(candidate)!=plan['candidate_count'] or candidate.site_code.tolist()!=plan['candidate_sites']:
        raise ValueError('frozen metadata roster differs')
    if years.year.tolist()!=plan['years_utc'] or int(years.qualified.sum())!=state['qualified_reference_years']:
        raise ValueError('qualification years differ')
    for r in years.itertuples(index=False):
        days=366 if calendar.isleap(r.year) else 365
        if r.calendar_days!=days or r.complete_days+r.missing_days!=days:raise ValueError('year denominator inconsistent')
        group=flags.loc[flags.year.eq(r.year)]
        if int(group.rows.sum())!=r.source_rows or int((group.rows-group.finite_values).sum())!=r.nonfinite_rows:
            raise ValueError('flag and nonfinite counts differ')
        if int(group.loc[~group.allowed_by_frozen_rule,'rows'].sum())!=r.disallowed_flag_rows:
            raise ValueError('disallowed flag count differs')
    if state['qualified_four_year_reference'] != (int(years.qualified.sum())>=4):raise ValueError('qualification decision differs')
    archive=ROOT/receipt['archive'];
    with archive.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    report={'status':'passed','published_sites':len(roster),'metadata_candidates':len(candidate),
        'reference_years_checked':len(years),'qualified_reference_years':int(years.qualified.sum()),
        'qualified_four_year_sites':int(state['qualified_four_year_reference']),
        'all_years_contain_nonfinite_values':bool(years.nonfinite_rows.gt(0).all()),
        'same_river_as_previous_bc_case':True,'temperature_scoring_performed':False,
        'limitation':'one preselected site only; metadata covers 32 sites but only the selected sequence was opened; recommended flags and finite quarter-hour values do not guarantee error-free sensors; same river and climate as a previous BC exploratory case'}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    text=[r'\section{Additional Nechako subdaily reference qualification}',
        ('The 2019--2024 author archive supersedes its 2019--2021 version. Before opening temperature sequences, '
         'published site dates were used to select the only river or creek candidate whose metadata could span all four UTC years '
         '2020--2023; named lakes and a spillway were excluded. The frozen criterion requires exactly 96 unique quarter-hour '
         'timestamps per UTC day, finite values, and author flags P or A. The download contains 32 sites; only the selected '
         'candidate sequence was opened. No year meets this criterion, so no recovery model was scored. Each year also contains '
         'at least one nonfinite value independently of whether other flagged readings are admitted. This site is on the same '
         'Nechako River as an earlier BC exploratory case and is not an independent climatic confirmation. The source is '
         'Kokoszka et al. (2025), DOI 10.5281/zenodo.15053907, CC BY 4.0.'),
         r'\begin{table}[p]\centering\small',
         r'\caption{Frozen P/A flag and 96-quarter-hour qualification of the selected Nechako site. Incomplete days include missing or nonfinite measurements, rejected author flags, duplicates or off-grid timestamps. Author flags are recommended classifications rather than proof of error-free measurements.}\label{tab:nechako-reference}',
         r'\begin{tabular}{lrrrrr}\toprule',
         r'Year & Days & Complete & Incomplete & Nonfinite records & Rejected flags\\\midrule']
    for r in years.itertuples(index=False):
        text.append(' & '.join(map(str,[r.year,r.calendar_days,r.complete_days,r.missing_days,r.nonfinite_rows,r.disallowed_flag_rows]))+r'\\')
    text.extend([r'\bottomrule\end{tabular}',r'\end{table}'])
    (PAPER/'nechako_reference_supporting.tex').write_text('\n'.join(text)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

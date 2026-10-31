#!/usr/bin/env python3
"""Render the unregistered, count-only USGS candidate screen."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_usgs_unresolved_network'
PAPER=ROOT/'paper/wrr_tr'


def main():
    initial=json.loads((OUT/'status.json').read_text());extension=json.loads((OUT/'extension_2025_status.json').read_text())
    metadata=json.loads((OUT/'unresolved_2025_metadata_status.json').read_text())
    if initial['status']!='completed_count_screen' or extension['status']!='completed_posthoc_2025_count_screen' or metadata['status']!='metadata_checked':
        raise RuntimeError('candidate intake is not fully documented')
    f=pd.read_csv(OUT/'candidate_counts_2010_2025.csv',dtype={'station_id':str})
    if f.station_id.duplicated().any() or len(f)!=initial['metadata_candidates'] or len(f)!=extension['metadata_candidates']:
        raise ValueError('candidate roster or denominator mismatch')
    for name in ['approved_counts.csv','approved_counts_2025.csv']:
        c=pd.read_csv(OUT/name,dtype={'station_id':str})
        if set(c.columns)!={'station_id','year','approved_daily_count','expected_days','interval_full_year','count_complete'}:
            raise ValueError('count receipt contains unexpected fields or lacks count fields')
    if int(f.extended_count_pass.fillna(False).sum())!=extension['extended_count_pass'] or int(f.extended_count_pass.isna().sum())!=extension['extended_count_unknown']:
        raise ValueError('extended selection count mismatch')
    lines=[r'\section{Additional USGS count-only candidate screen}',
      ('An additional metadata-only roster of '+str(len(f))+' stations was fixed before requesting 2010--2024 approved daily-mean counts. '
       'All retained unresolved river-network identities; no temperatures or reconstruction errors were saved. '
       'No station had at least four full years in the initial screen. After that result, the same entire roster was checked for 2025; '
       'this extension is post hoc and unregistered. No station is confirmed to pass the four-year count requirement, '
       'and '+str(extension['extended_count_unknown'])+' remains undetermined because the 2025 statistic was not returned. '
       'Three other missing 2025 statistics cannot change eligibility because their original counts are at most two. '
       'For the undetermined candidate, the current metadata end precedes 2025, but metadata may lag observations and alternative series were not screened. '
       'Count completeness does not establish nonestimated daily observations, complete subdaily coverage, sensor accuracy, river-network independence or climate independence. No candidate was scored.'),
      r'\begin{table}[p]\centering\small',
      r'\caption{USGS count-only preflight for the additional fixed metadata roster. The 2025 extension was decided after the 2010--2024 results. A missing count is shown as --; eligibility is unknown when a missing 2025 count could change the four-year decision. No temperature values are shown.}\label{tab:usgs-unresolved-counts}',
      r'\begin{tabular}{lrrl}\toprule',
      r'Station & 2010--2024 complete years & 2025 approved days & Extended count decision\\\midrule']
    for _,r in f.sort_values('station_id').iterrows():
        count='--' if pd.isna(r.approved_daily_count_2025) else str(int(r.approved_daily_count_2025))
        decision='Unknown' if pd.isna(r.extended_count_pass) else ('Pass' if bool(r.extended_count_pass) else 'Does not pass')
        years='--' if pd.isna(r.n_count_complete_years) else str(int(r.n_count_complete_years))
        lines.append(' & '.join([r.station_id,years,count,decision])+r'\\')
    lines.extend([r'\bottomrule\end{tabular}',r'\end{table}'])
    (PAPER/'usgs_unresolved_count_supporting.tex').write_text('\n'.join(lines)+'\n')
    report={'status':'passed','initial_candidates':len(f),'initial_count_pass':initial['count_preflight_pass'],
       'extension_count_pass':extension['extended_count_pass'],'extension_count_unknown':extension['extended_count_unknown'],
       '2025_statistics_missing':extension['2025_count_not_returned'],
       'unknown_selected_series_metadata_ended_before_2025':metadata['metadata_end_before_2025'],
       'new_reference_qualified':0,'temperature_values_saved':False,
       'limitation':'post-hoc availability extension; a missing 2025 count remains unknown, metadata may lag, and all candidates retain unresolved river-network and quality status'}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

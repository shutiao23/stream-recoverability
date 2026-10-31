#!/usr/bin/env python3
"""Render the source-role audit without treating same-region groups as target leakage."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'results/wrr_review_response_20261027/audit'
PAPER=ROOT/'paper/wrr_tr'


def main():
    status=json.loads((AUDIT/'region_holdout_role_status.json').read_text())
    table=pd.read_csv(AUDIT/'region_holdout_role_audit.csv')
    if status['status']!='passed_audit_with_finding' or status['held_test_group_overlap'] or status['held_test_station_overlap']:
        raise ValueError('source role audit is incomplete or has unaccounted target overlap')
    affected=table.loc[table.same_region_groups_with_positive_weight.gt(0)].copy()
    if len(affected)!=status['same_region_positive_weight_role_rows']:raise ValueError('affected role count differs')
    def one(region,role):
        x=affected.loc[affected['split'].eq('before_2010')&affected.region.eq(region)&affected.role.eq(role)]
        if len(x)!=1:raise ValueError('affected role not unique')
        return x.iloc[0]
    h=one('usgs_huc17','estimator');n=one('nve_hydapi','interval_calibration')
    v={'RHModels':str(status['models_checked']),'RHRoleRows':str(status['role_rows_checked']),
       'RHHucGroups':str(int(h.same_region_groups_with_positive_weight)),'RHHucStations':str(int(h.same_region_stations_with_positive_weight)),
       'RHHucCases':str(int(h.same_region_cases_with_positive_weight)),'RHHucWeighted':str(int(h.same_region_bootstrap_weighted_cases)),
       'RHNveGroups':str(int(n.same_region_groups_with_positive_weight)),'RHNveStations':str(int(n.same_region_stations_with_positive_weight)),
       'RHNveCases':str(int(n.same_region_cases_with_positive_weight)),
       'RHArchiveCases':str(int(status['forward_usgs_huc17_archive_station_repetitions'])),
       'RHArchiveStations':str(int(status['forward_usgs_huc17_archive_stations'])),
       'RHFutureCases':f"{int(status['future_release_target_cases_in_affected_regions']):,}"}
    (PAPER/'region_holdout_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+x+'}\n' for k,x in v.items()))
    lines=[r'\section{Source role audit for partitioned forward models}',
       ('We re-derived the seed-zero bootstrap weights and checked them against the roles saved in '+str(status['models_checked'])+' model bundles for the four evaluated source splits. '
        'The selected held test stations and their recorded connected groups did not enter any source role. '
        'However, in the before-2010 split, the role function defines held groups from test-period cases; '
        'training-only groups in the same named region may therefore remain in the source. '
        'The table reports positive-weight same-region source cases, not held-target observations. '
        'This is not a uniformly held-region design; the distinction affects the interpretation of forward transfer. '
        'It does not establish leakage of target-station hidden values or physical independence across groups.'),
       r'\begin{table}[p]\centering\small',
       r'\caption{Seed-zero before-2010 model roles with positive-weight source cases in the named target region. Bootstrap-weighted counts include repeated role draws and do not represent independent samples.}\label{tab:forward-region-role-audit}',
       r'\begin{tabular}{llrrrr}\toprule',
       r'Region & Role & Groups & Stations & Cases & Weighted cases\\\midrule']
    for _,r in affected.sort_values(['split','region','role']).iterrows():
        lines.append(' & '.join([str(r.region).replace('_',r'\_'),str(r.role).replace('_',r'\_'),
          str(int(r.same_region_groups_with_positive_weight)),str(int(r.same_region_stations_with_positive_weight)),
          str(int(r.same_region_cases_with_positive_weight)),str(int(r.same_region_bootstrap_weighted_cases))])+r'\\')
    lines.extend([r'\bottomrule\end{tabular}',r'\end{table}'])
    (PAPER/'region_holdout_supporting.tex').write_text('\n'.join(lines)+'\n')
    report={'status':'passed','models_checked':status['models_checked'],'held_target_group_overlap':0,'held_target_station_overlap':0,
       'huc17_same_region_groups':int(h.same_region_groups_with_positive_weight),'huc17_same_region_stations':int(h.same_region_stations_with_positive_weight),
       'huc17_same_region_cases':int(h.same_region_cases_with_positive_weight),'huc17_same_region_weighted_cases':int(h.same_region_bootstrap_weighted_cases),
       'nve_same_region_interval_groups':int(n.same_region_groups_with_positive_weight),'nve_same_region_interval_cases':int(n.same_region_cases_with_positive_weight),
       'affected_forward_archive_cases':int(status['forward_usgs_huc17_archive_station_repetitions']),
       'affected_forward_archive_stations':int(status['forward_usgs_huc17_archive_stations']),
       'affected_future_output_region_rows':int(status['future_release_target_cases_in_affected_regions']),
       'limitation':status['limitation']}
    (AUDIT/'region_holdout_role_report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()

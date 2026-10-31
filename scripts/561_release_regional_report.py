#!/usr/bin/env python3
"""Render selected fixed-rule regional sensitivity results for manuscript use."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/release_outputs'


def main():
    directions=pd.read_csv(OUT/'source_release_region_directions.csv').set_index('design_family')
    groups=pd.read_csv(OUT/'source_release_equal_group.csv').set_index('design_family')
    region=pd.read_csv(OUT/'source_release_by_region.csv')
    syke=region.loc[region.design_family.eq('crossed') & region.region.eq('syke')].iloc[0]
    drop=pd.read_csv(OUT/'source_release_leave_one_region_out.csv')
    c=drop.loc[drop.design_family.eq('calendar'),'conditional_error_difference']
    x=drop.loc[drop.design_family.eq('crossed'),'conditional_error_difference']
    values={'RGGapPositive':str(int(directions.loc['crossed','n_three_higher'])),
            'RGGapNegative':str(int(directions.loc['crossed','n_three_lower'])),
            'RGGapDefined':str(int(directions.loc['crossed','n_both_defined'])),
            'RGGapUndefined':str(int(directions.loc['crossed','n_undefined'])),
            'RGSykeThreeRetention':f'{100*syke.three_retention:.1f}',
            'RGSykeScoreRetention':f'{100*syke.score_retention:.1f}',
            'RGSykeThreeRisk':f'{100*syke.three_error:.2f}',
            'RGSykeScoreRisk':f'{100*syke.score_error:.2f}',
            'RGCommonGroups':str(int(groups.loc['calendar','n_both_defined'])),
            'RGAllGroups':str(int(groups.loc['calendar','n_groups'])),
            'RGThreeGroupRisk':f"{100*groups.loc['calendar','three_mean_group_error']:.3f}",
            'RGScoreGroupRisk':f"{100*groups.loc['calendar','score_mean_group_error']:.3f}"}
    (ROOT/'paper/wrr_tr/release_regional_values.tex').write_text(''.join(
        '\\newcommand{\\'+name+'}{'+value+'}\n' for name,value in values.items()))
    status={'source':'held-region clean cases and source-calibrated thresholds fixed before evaluation',
            'regions_crossed':directions.loc['crossed'].to_dict(),
            'common_group_means_calendar':groups.loc['calendar'].to_dict(),
            'drop_one_evaluation_region_calendar_error_gap_range':[float(c.min()),float(c.max())],
            'drop_one_evaluation_region_crossed_error_gap_range':[float(x.min()),float(x.max())],
            'limitations':'zero-release conditional risk undefined; case retention differs; exclusions do not refit models or thresholds; region signs are descriptive, not independent tests'}
    (OUT/'source_release_regional_report.json').write_text(json.dumps(status,indent=2,default=str)+'\n')
    print(json.dumps(status,indent=2,default=str))

if __name__=='__main__':main()

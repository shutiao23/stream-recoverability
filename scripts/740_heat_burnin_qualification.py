#!/usr/bin/env python3
"""Count evaluation-period years in the first-seven-year heat-mask baseline.

This audits year labels only, after the masked results were observed. Detailed
station labels stay local. It does not access or evaluate temperature values.
"""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/heat_gap_matched'
PRIVATE=ROOT/'private/wrr_heat_gap_matched_20261027'
ROSTER=ROOT/'private/wrr_expanded_stress_20261027/roster.csv'
CASES=ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet'


def main():
    roster=pd.read_csv(ROSTER)
    f=pd.read_parquet(CASES,columns=['station_key','year','design_family'])
    f=f[f.design_family.eq('crossed')&f.station_key.isin(roster.station_key)]
    rows=[]
    for site in roster.itertuples(index=False):
        years=sorted(f.loc[f.station_key.eq(site.station_key),'year'].unique())
        if len(years)<7:raise ValueError('Incomplete burn-in year metadata')
        first=years[:7];late=[int(y) for y in first if y>=2010]
        rows.append({'station_key':site.station_key,'region':site.region,'first_seven_years':','.join(map(str,first)),
                     'at_or_after_2010':len(late),'latest_in_burnin':max(first)})
    data=pd.DataFrame(rows)
    if len(data)!=41 or data.station_key.duplicated().any():raise ValueError('Unexpected station roster')
    private=PRIVATE/'burnin_year_metadata.parquet';data.to_parquet(private,index=False);private.chmod(0o600)
    counts=data.at_or_after_2010.value_counts().sort_index()
    report={'status':'passed','posthoc_clarification':True,'stations':len(data),'stations_with_any_2010_or_later_burnin':int(data.at_or_after_2010.gt(0).sum()),
            'station_count_by_number_of_2010_or_later_burnin_years':{str(int(k)):int(v) for k,v in counts.items()},
            'latest_burnin_year':int(data.latest_in_burnin.max()),
            'clarification':'The frozen matched-gap plan incorrectly described the first-seven-year air baseline as pre-2010. The implementation uses the first seven complete reference-year labels; some extend into the evaluation period. The original expanded-stress plan correctly said first seven years. No scenario masks or predictions were changed.',
            'interpretation':'The air values construct a synthetic test mask, not an input fitted using held water outcomes. This is not a strictly prior-vintage or prospective outage-generation experiment; year and air information from the evaluation period is used to design the retrospective mask.',
            'scope':'Year metadata only; no temperature values, measurement-quality evaluation or independent climate evidence.'}
    (OUT/'plan_clarification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()

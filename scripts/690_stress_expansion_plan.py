#!/usr/bin/env python3
"""Freeze a post-hoc expansion of whole-archive mechanism sensitivities."""
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd
import wrr_tr_common as T

ROOT = T.ROOT
REV = ROOT/'results/wrr_review_response_20261027'
OUT = REV/'expanded_stress'
PRIVATE = ROOT/'private/wrr_expanded_stress_20261027'

def main():
    if (OUT/'plan.json').exists():raise FileExistsError('Existing scenario plan is preserved')
    trends=pd.read_csv(REV/'whole_archive/trends.csv')
    base=trends[(trends.family=='crossed') & (trends['mode']=='forward') & (trends.replicate<5)
                & (trends.estimator=='D2') & (trends.retention=='all') & (trends.dependence=='point')]
    keys=['station_key','replicate']
    if base.duplicated(keys).any() or len(base)!=205:raise ValueError('Expected 41 stations and 205 baseline settings')
    core=T.load_script('stress_expansion_jobs', ROOT/'scripts/431_tr_cases.py')
    jobs={j['station_key']:j for j in core.jobs_for('source')}
    if not set(base.station_key).issubset(jobs):raise ValueError('Missing original station job')
    roster=base[['station_key','region','independence_group']].drop_duplicates().sort_values('station_key')
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700); OUT.mkdir(parents=True,exist_ok=True)
    roster.to_csv(PRIVATE/'roster.csv',index=False)
    files=[ROOT/'scripts/689_fixed_count_heat_stress.py',ROOT/'scripts/521_whole_archive.py',ROOT/'scripts/431_tr_cases.py',
           ROOT/'scripts/495_review_completion_independent_analysis.py',ROOT/'scripts/466_review_completion_refit.py',
           ROOT/'scripts/467_review_completion_analysis.py',T.CONFIG,T.E1_MISSINGNESS/'mnar_generator.json',
           ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet',
           ROOT/'results/wrr_review_completion_20261024/cases/before_2010/seed_00.parquet',REV/'whole_archive/trends.csv']
    for region in sorted(roster.region.unique()):
        files.append(ROOT/'results/wrr_review_completion_20261024/refits/before_2010/seed_00'/f'{region}.joblib')
    for station in roster.station_key:
        for name in ['input_path','air_input_path']:
            p=Path(jobs[station][name])
            if p.exists():files.append(p)
        for rep in range(5):
            files.append(REV/'whole_archive/crossed/forward'/f'replicate_{rep:02d}'/station.replace('|','_')/'design.json')
    files=list(dict.fromkeys(files))
    missing=[str(x) for x in files if not x.is_file()]
    if missing:raise FileNotFoundError(f'Frozen source or baseline missing: {missing[:5]}')
    records=[{'path':str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p),} for p in files]
    manifest=PRIVATE/'input_manifest.json';manifest.write_text(json.dumps(records,indent=2)+'\n')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc sensitivity, after inspecting original results; not a preregistered or independent-climate study',
          'scope':'all 41 forward-eligible original whole-archive stations, first five existing replicates, controlled long-gap family; 205 expected station-replicate settings per scenario',
          'roster_count':len(roster),'connected_groups':int(roster.independence_group.nunique()),'regions':int(roster.region.nunique()),
          'replicates':[0,1,2,3,4],'family':'crossed','mode':'forward','draws':256,
          'synchronized_donors':'reuse each target gap mask exactly; mask those same days in all donor columns before local fitting',
          'heat_associated_matched':'baseline 35% seeded number of masked years held exactly fixed per archive; for eligible years select that number without replacement by exponential-race weights 5 for annual air H30 above the first-seven-years 80th percentile and 1 otherwise; separate fixed random stream',
          'heat_limits':'air is used to construct an experimental mask, not to select source cases by evaluation outcome; hot-year identity, gap shapes, total hidden days and positions can change; missing air yields unavailable, not zero error',
          'measurement':'paired case availability, D2 and calibrated stochastic trend RMSE and nominal 95% interval summaries, 4,000 connected-group paired bootstraps and leave-one-region-out without refitting; primary comparison is fixed-model descriptive sensitivity',
          'limitations':'source and original results already viewed; five repeated masks are not independent climates; model seed zero; source model may include other groups in named target region; fixed temporal cutoff and currently available forcing; no causal isolation of changing year position or gap length, natural-outage validation or group safety',
          'privacy':'station roster, per-case predictions, baseline input manifest and per-case scores stay local private; aggregate output only in candidate package',
          }
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print('Frozen 205 settings for each stress across',len(roster),'stations and',plan['connected_groups'],'groups',flush=True)

if __name__=='__main__':main()

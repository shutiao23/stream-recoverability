#!/usr/bin/env python3
"""Check both source models and both stress adapters on one frozen archive."""
import json
from pathlib import Path
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT
module=T.load_script('stress_source_pilot',ROOT/'scripts/694_stress_source_sensitivity.py')


def main():
    module.verify_plan()
    roster=pd.read_csv(module.EXP/'roster.csv')
    station=roster[roster.region.eq('usgs_huc17')].sort_values('station_key').iloc[0].station_key
    jobs={j['station_key']:j for j in T.load_script('stress_pilot_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source')}
    reference=pd.read_parquet(module.SOURCE/'cases/leave_one_year_out/seed_00.parquet',columns=['station_key','region','independence_group','year','design_family','mask_runs','h30__policy','eval_truth_h30'])
    reference=reference[reference.station_key.eq(station)&reference.design_family.eq('crossed')]
    for scenario in module.SCENARIOS:
        for version,base in [('strict_original',module.STRICT),('candidate',module.CAND)]:
            calibration=base/'strict_archive_calibration.json' if version=='strict_original' else base/'calibrations/forward/usgs_huc17.json'
            model=base/'refits/before_2010/seed_00/usgs_huc17.joblib'
            module.work(scenario,version,jobs[station],reference,0,json.loads(calibration.read_text()),model,calibration)
    result={'status':'pilot_passed_no_accuracy_claim','source_versions':2,'scenarios':2,'archive_reanalyses':4,
            'checks':'same target masks, hidden target and donor checks, plug-in, annual policy and observed bound',
            'limitation':'One station and one replicate; no accuracy or source-effect interpretation.'}
    (module.OUT/'pilot.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()

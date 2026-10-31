#!/usr/bin/env python3
"""Fix the single-station exploratory comparison before target scoring."""
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr'
PRIVATE=ROOT/'private/wrr_truckee_reference_20261027';SOURCE=ROOT/'results/wrr_review_completion_20261024'

def main():
    dest=OUT/'exploratory_score_plan.json'
    if dest.exists():raise FileExistsError('Preserve exploratory scoring plan')
    finite=json.loads((OUT/'finite_reference_status.json').read_text());audit=json.loads((OUT/'finite_reference_independent_audit.json').read_text())
    if finite['status']!='finite_published_reference_screened' or audit['status']!='passed':raise ValueError('Published daily reference not checked')
    stations=pd.read_csv(PRIVATE/'finite_reference_stations.csv');years=pd.read_csv(PRIVATE/'finite_reference_years.csv')
    selected=stations.loc[stations.at_least_four_finite_reference_years,'station_code'];chosen=years.loc[years.station_code.isin(selected)&years.finite_reference_year,['station_code','year']].sort_values(['station_code','year'])
    if len(selected)!=1 or len(chosen)!=4 or chosen.station_code.nunique()!=1:raise ValueError('Fixed qualifying cohort changed')
    coordinates=pd.read_csv(OUT/'station_metadata_03.csv').set_index('Station_Code',verify_integrity=True)
    chosen=chosen.copy();chosen['latitude']=[float(coordinates.loc[s,'Latitude']) for s in chosen.station_code];chosen['longitude']=[float(coordinates.loc[s,'Longitude']) for s in chosen.station_code]
    roster=PRIVATE/'exploratory_roster.csv';chosen.to_csv(roster,index=False);roster.chmod(0o600)
    files=[PRIVATE/'finite_reported_daily.parquet',PRIVATE/'finite_reference_years.csv',PRIVATE/'finite_reference_stations.csv',
           SOURCE/'deployment/global_source_candidate.joblib',SOURCE/'independent_study/source_case_settings.json',
           SOURCE/'independent_study/source_missingness_generator.json',ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/source_calibration.json',
           ROOT/'scripts/431_tr_cases.py',ROOT/'scripts/495_review_completion_independent_analysis.py',ROOT/'scripts/598_nova_scotia_exploratory_score.py',
           ROOT/'scripts/528_review_response_annual.py',ROOT/'scripts/wrr_tr_features.py',Path(__file__)]
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'posthoc fixed exploratory evaluation after source metadata, downloaded values and finite-day qualification were inspected; no Truckee model predictions, H30 values or prediction errors examined',
        'selection':'All sites with at least four complete finite published-reference years; exactly one site and all four qualifying years. Selection uses temporal and value availability, not annual H30 or prediction error.',
        'reference':'Daily arithmetic means of 96 distinct finite reported 15-minute values. Provider describes QA/QC and uses PST; per-value estimated/corrected flags and physical day alignment remain unresolved.',
        'method':'Single-year leave-one-year-out: three other complete selected years at that site form local history, with target gaps hidden and no donor stations. Reuse the fixed global annual source model and source-only calibration; compare plug-in, D2, and calibrated stochastic on the same controlled 30/60/90-day masks.',
        'metrics':'Annual point MAE, bias, absolute error over 0.5 C; availability; nominal 90% coverage, interval width, score and CRPS on common cases. Also retain reported outcomes by year; no trend inference from four years and no cluster or climate generalization.',
        'forcing':'One NASA POWER T2M request for 2011–2020 at the station metadata coordinates rounded to 0.01 degree, daily local-solar time. POWER local solar day need not align with the water provider PST day; weather quality is not validated.',
        'limitations':'One station, four years and one managed watershed with previous Truckee-basin data contact. Source model and calibration are fixed but the full river-network separation from every source dependency is not established. Nonestimated measurements, independent climate, natural outage, source permissions and physical measurement uncertainty remain unresolved. Repeated masks are not independent stations or climates.',
        }
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded four-year single-station exploratory comparison')

if __name__=='__main__':main()

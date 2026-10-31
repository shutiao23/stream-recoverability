#!/usr/bin/env python3
"""Write only the fixed-cohort ECCC qualification summary for the manuscript."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_eccc_red'


def main():
    s=json.loads((OUT/'status.json').read_text())
    p=json.loads((OUT/'prior_eccc_cache_status.json').read_text())
    counts=pd.read_csv(OUT/'status_grade_counts.csv')
    validated=int(counts.loc[counts.status.eq('VALIDATED') & counts.grade.isna(),'n_hourly_rows'].sum())
    macros={'ECCCFiles':str(s['n_files']), 'ECCCUnresolvedIdentity':f"{s['n_identity_unresolved_rows']:,}",
            'ECCCValidatedMissingGrade':f'{validated:,}', 'ECCCLiteralStrictRows':f"{s['n_literal_v_grade_numeric12_rows']:,}",
            'ECCCCompleteYears':str(s['complete_local_wallclock_years']), 'ECCCPriorStations':str(p['opened_stations']),
            'ECCCPriorMaxYears':str(p['max_possible_full_years'])}
    (ROOT/'paper/wrr_tr/eccc_red_values.tex').write_text(''.join(
        '\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in macros.items()))
    report={'strict_hourly_reference_eligible':s['strict_physical_reference_eligible'],
            'files_acquired':s['n_files'],'unresolved_station_identity_rows':s['n_identity_unresolved_rows'],
            'validated_word_rows_with_missing_grade':validated,
            'literal_v_numeric_grade12_rows':s['n_literal_v_grade_numeric12_rows'],
            'complete_provider_wallclock_years':s['complete_local_wallclock_years'],
            'previous_opened_stations_upper_bound':p['opened_stations'],'max_possible_years_prior_cache':p['max_possible_full_years'],
            'same_river_as_source':s['prior_same_river_source'],
            'limitations':'station identifier, status and grade vocabulary, and daylight-saving convention require provider clarification; no new independent basin or reconstruction score'}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

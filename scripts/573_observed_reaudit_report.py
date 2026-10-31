#!/usr/bin/env python3
"""Render scope and counts of independent observed-record arithmetic checks."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'results/wrr_review_response_20261027/audit'


def main():
    source=json.loads((A/'observed_record_independent_reaudit.json').read_text())
    precision=json.loads((A/'input_panel_precision_audit.json').read_text())
    rules=json.loads((A/'screening_rule_reaudit.json').read_text())
    usgs=json.loads((A/'usgs_observed_independent_reaudit.json').read_text())
    replay=json.loads((A/'usgs_observed_reproduction.json').read_text())
    shareable=json.loads((A/'open_observed_reproduction.json').read_text())
    if not all(x['passed'] for x in [source,rules,usgs,precision]):raise RuntimeError('Observed-record re-audit failed')
    if replay['status']!='passed' or shareable['status']!='passed':raise RuntimeError('Included observation replays failed')
    lines=[r'\section{Independent observed-record arithmetic re-audits}',
      f"Using the same local canonical float32 daily archive and an independent convolution implementation, we recomputed {source['reference_station_years_recomputed']:,} complete reference station-years and {source['incomplete_station_years_recomputed']:,} incomplete station-years at {source['eligible_stations']} eligible stations. All {source['certificate_station_years']} witness identities, saved 30-day values and complete-year reference maxima agreed within the stated numerical tolerance. This is an arithmetic re-audit of the same processed archive, not an independent check of provider-native records or sensor error.",
      f"Comparing {precision['finite_daily_values_compared']:,} finite values from {precision['input_panel_files']} selected project input panels with the canonical archive yielded no missingness or float32-cast discrepancies. The largest absolute rounding difference is {precision['maximum_float32_rounding_c']:.8f} degrees C; {precision['witness_identity_changes']} witness identities and {precision['half_c_margin_classification_changes']} classifications at the 0.5-degree excess threshold changed. The input panels are processed project files, not provider-native instrument records.",
      f"Across {rules['station_years_checked']:,} eligible station-years, independently recalculated annual coverage, available 30-day maxima, July--August completeness and longest missing runs reproduced {rules['witness_rule_decisions_checked']} witness--rule decisions. For each of {rules['target_year_perturbation_probes']} witness years, increasing its observed values by 5 degrees C did not change the leave-target-year-out warm-season climatology. The old fixed-season fraction remains sourced from saved metadata; these probes do not cover every year or other pipelines.",
      f"For the ten additional USGS sites, independent parsing of the saved daily API responses reproduced {usgs['complete_approved_station_years']} approved-complete reference station-years and the {usgs['witness_station_years_checked']} certified observed windows. The original quality-screened window selection also replays from the saved payloads, but the separate arithmetic audit does not independently implement that selection. Approved estimated values remain in complete-year references, but the certified windows contain no estimated days. These records do not establish subdaily completeness, physical measurement accuracy or independent recovery performance.",
      f"A separate candidate review subset contains processed daily values for {shareable['included_stations']} of {shareable['original_stations']} previously eligible source stations, including all {shareable['witness_station_years']} witnesses. One LUBW station is omitted pending permission. The subset verifies the included reported-series arithmetic and rule decisions, but cannot independently confirm the omitted station or the original full eligible-station denominator."]
    macros={'IPDays':f"{precision['finite_daily_values_compared']:,}", 'IPPanels':str(precision['input_panel_files']),
            'IPRounding':f"{precision['maximum_float32_rounding_c']:.8f}", 'IPWitnessChanges':str(precision['witness_identity_changes']),
            'IPHalfDegreeChanges':str(precision['half_c_margin_classification_changes'])}
    (ROOT/'paper/wrr_tr/input_precision_values.tex').write_text(''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in macros.items()))
    (ROOT/'paper/wrr_tr/record_reaudit_supporting.tex').write_text('\n\n'.join(lines)+'\n')
    print('Observed-record arithmetic re-audits prepared; provider-native source and sensor accuracy remain unverified.')

if __name__=='__main__':main()

#!/usr/bin/env python3
"""A necessary-size screen for the current retained pools, before new errors."""
from __future__ import annotations

import importlib
import json

import yaml

import wrr_r3_common as C

N = importlib.import_module("399_wrr_neon_recruitment_feasibility")
OUT = C.READY / "followup_20261021/reference_pool_feasibility"


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    base = OUT.parent
    spec_path = C.ROOT / "configs/wrr_next_confirmation_20261021.yaml"
    usgs_path = base / "usgs_intake_evidence/summary.json"
    au_path = base / "au_dependence_audit/summary.json"
    spec = yaml.safe_load(spec_path.read_text())
    usgs, au = (json.loads(path.read_text()) for path in [usgs_path, au_path])
    allocation = spec["joint_error_allocation"]
    risk = spec["selected_risk_cap"]
    cal_floor = N.ideal_group_floor(risk, allocation["formal_calibration_per_method"])
    test_floor = N.ideal_group_floor(risk, allocation["evaluation_risk_per_method"])
    # These are generous maxima, not actual independent or quality-qualified
    # units: every retained USGS station and every unresolved AU station counts.
    us_max = int(usgs["not_yet_excluded_after_current_connection_and_coordinate_screens"])
    au_max = int(au["conservative_qualified_hydrologic_blocks_total"] + au["qualified_reference_stations_pending_topology"])
    maximum, necessary = us_max + au_max, cal_floor + test_floor
    C.write_json(OUT / "summary.json", {
        "status": "necessary_size_screen_under_existing_rosters_and_conservative_grouping_only",
        "USGS_retained_station_upper_bound_before_reference_QC": us_max,
        "AU_quality_candidate_block_upper_bound_including_unmapped_station": au_max,
        "optimistic_pooled_unit_upper_bound": maximum,
        "ideal_one_threshold_zero_failure_full_admission_calibration_floor": cal_floor,
        "ideal_one_threshold_zero_failure_full_admission_test_floor": test_floor,
        "necessary_disjoint_calibration_plus_test_floor_ignoring_training": necessary,
        "current_pools_can_meet_even_this_necessary_floor": maximum >= necessary,
        "all_upper_bound_units_assumed_independent_and_quality_eligible_only_for_this_screen": True,
        "scope_excludes_984_unverified_AU_candidates_and_other_unrecruited_sources": True,
        "original_AU_roles_not_reshuffled": True, "no_new_temperature_or_prediction_errors_opened": True,
        "sample_size_recommendation": None,
        "not_a_joint_power_calculation_or_proof_about_all_public_data": True,
        "conclusion": "Current retained pools cannot support the declared formal joint endpoint even under idealized assumptions; additional verified units and target-population planning are required." if maximum < necessary else "Passing a necessary count does not establish independence, reference quality or joint power."})
    print(f"[422] current-pool optimistic bound {maximum}; necessary ideal disjoint calibration/test floor {necessary}; no new-target N recommended", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create a current delivery receipt from produced files; never marks a goal done."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import wrr_tr_common as T

OUT=T.ROOT/"results/wrr_review_completion_20261024"
DOC=T.ROOT/"docs/reviews/wrr_review_completion_20261024"


def read(path):return json.loads(path.read_text()) if path.exists() else {}


def digest(path):
    sha=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1<<20),b""):sha.update(block)
    return sha.hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument("--verify",action="store_true");a=p.parse_args()
    target=OUT/"evidence/delivery_receipt.json"
    if a.verify:
        d=read(target)
        if not d:raise RuntimeError("No delivery receipt exists")
        for name,meta in d["artifacts"].items():
            path=T.ROOT/name
            assert path.stat().st_size==meta["bytes"] and digest(path)==meta["sha256"],name
        print("Delivery artifact checksums verified",flush=True);return 0
    root=ET.parse(OUT/"evidence/extended_unit_tests.xml").getroot()
    suites=[root] if root.tag=="testsuite" else list(root.iter("testsuite"))
    counts={key:sum(int(s.attrib.get(key,0)) for s in suites) for key in ["tests","failures","errors","skipped"]}
    if counts["failures"] or counts["errors"]:raise RuntimeError("Current test record contains failures")
    status=read(OUT/"evidence/completion_status.json");validation=read(OUT/"evidence/validation.json")
    study=OUT/"independent_study";registration=read(study/"public_registration_status.json")
    manifest=read(study/"file_sha256.json")
    changed=[name for name,sha in manifest.items() if not (T.ROOT/name).is_file() or digest(T.ROOT/name)!=sha]
    window=read(OUT/"target_windows/h7/full/completion.json")
    paths=[T.ROOT/"paper/wrr_tr"/name for name in ["review_completion_article.pdf","review_completion_supporting.pdf","review_completion_cover_letter.txt"]]
    paths += [DOC/name for name in ["EXECUTION_REPORT_ZH.md","EXPERIMENT_CHECKLIST_ZH.md","INDEPENDENT_EXECUTION_ZH.md",
        "SUBMISSION_CHECKLIST_ZH.md","FORCING_EXECUTION_ZH.md","WINDOW_EXECUTION_ZH.md","NATIONAL_EXECUTION_ZH.md","FLOW_EXECUTION_ZH.md","FOCUSED_DIAGNOSTICS_ZH.md","ZERO_FLOW_MISSINGNESS_ZH.md"]]
    paths += [study/"registration_code_and_protocol.tar.gz",OUT/"evidence/extended_unit_tests.xml",OUT/"evidence/validation.json"]
    paths.append(OUT/"evidence/archive_execution_smoke.json")
    paths += [OUT/name for name in ["inputs/source_coordinate_supplement.csv","inputs/source_coordinate_supplement_audit.json",
        "failure_map/status.json","failure_map/failure_map.pdf","inputs/forcing_recovery/usgs/status.json",
        "inputs/forcing_recovery/usgs/numerical_audit.json","inputs/forcing_recovery/usgs/summary.csv"]]
    paths += [OUT/"flow_comparators"/name for name in ["status.json","design.json","historical_control_audit.json",
        "scorecard.csv","paired_effects.csv","rules.csv"]]
    paths += [OUT/"national_meaning"/name for name in ["status.json","acquisition.json","forcing_status.json",
        "application/status.json","application/meaning/network_and_regional_summary.csv",
        "application/meaning/spatial_coverage.csv","application/meaning/field_significance.csv",
        "application/meaning/hot_year_frequency_network_region.csv","application/meaning/observed_record_certificates.csv"]]
    paths += [OUT/"focused_diagnostics"/name for name in ["status.json","hot_year_examples_per_seed.csv",
        "prespecified_station_profiles.csv","prespecified_station_trends_per_seed.csv"]]
    paths += [OUT/"zero_flow_missingness"/name for name in ["status.json","conditional_logit_summary.csv","cohort_counts.csv"]]
    artifacts={str(path.relative_to(T.ROOT)):{"bytes":path.stat().st_size,"sha256":digest(path)} for path in paths if path.exists()}
    d={"created_utc":datetime.now(timezone.utc).isoformat(),"unit_tests":counts,"unit_tests_passed":counts["tests"]-counts["skipped"],
        "source_seeds":status.get("full_seed_analyses"),"source_region_refits":540,
        "full_H7_target_refits_complete":bool(window.get("complete")),"H7_source_region_refits":window.get("outer_fits"),
        "H7_daily_input_audit":read(OUT/"target_windows/h7/full/daily_input_audit.json").get("passed",False),
        "default_H30_parity":read(OUT/"target_windows/h30_default_parity.json"),
        "full_USGS_forcing":read(OUT/"inputs/forcing_full_source_exact/analysis_summary.json"),
        "full_USGS_forcing_original_control":read(OUT/"inputs/forcing_full_source_exact/original_core_control_audit.json"),
        "source_coordinates":read(OUT/"failure_map/status.json"),
        "driver_recovery_models":{region:read(OUT/f"inputs/forcing_recovery/{region}/status.json") for region in ["usgs","europe"]},
        "European_weather_progress":read(OUT/"europe_full_source_exact/acquisition_progress.json"),
        "European_analysis_status":read(OUT/"europe_full_source_exact/analysis_summary.json"),
        "national_source_progress":read(OUT/"national_meaning/progress.json"),"national_h30_analysis_complete":bool(validation.get("national_h30_analysis_complete")),
        "national_retrieved_panel_execution_complete":bool(validation.get("national_retrieved_panel_execution_complete")),
        "national_qualification_and_result_bounds":read(OUT/"national_meaning/status.json"),
        "NZ_independent_values_requested":bool(registration.get("water_temperature_values_requested",False)),"public_registration_status":registration.get("status"),
        "draft_registration_bundle_matches_current_manifest_files":bool(manifest) and not changed,
        "draft_manifest_files_changed_since_packaging":changed,"author_and_platform_fields":"user-owned",
        "source_core_verified":bool(validation.get("source_core_complete",validation.get("source_core_and_local_extensions_complete",False))),
        "all_user_requirements_complete":False,"artifacts":artifacts}
    T.write_json(target,d)
    print(json.dumps({"unit_tests_passed":d["unit_tests_passed"],"full_H7_target_refits_complete":d["full_H7_target_refits_complete"],
        "draft_bundle_matches_current_manifest_files":d["draft_registration_bundle_matches_current_manifest_files"],"all_user_requirements_complete":False},indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())

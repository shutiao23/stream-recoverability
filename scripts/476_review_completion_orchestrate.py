#!/usr/bin/env python3
"""Resume dependent analysis stages after running generators finish.

Run each stage with its own log and retain the first failure. This does not
mark a running process complete, make a public registration, or acquire new
confirmation outcomes. Completed expensive refits are resumable by region.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=ROOT/CONFIG["out"]
SCRATCH=ROOT/"scratch"
_resume_label=None
_resume_reached=True


def wait_for(paths,label):
    while not all(p.exists() for p in paths):
        print(f"waiting: {label}",flush=True)
        time.sleep(30)


def run(label,args):
    global _resume_reached
    if not _resume_reached:
        if label!=_resume_label:
            print(f"retaining completed stage {label}",flush=True)
            return
        _resume_reached=True
    print(f"starting {label}",flush=True)
    with (SCRATCH/f"review_completion_{label}.log").open("w") as log:
        result=subprocess.run([sys.executable,*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=os.environ|{"OPENBLAS_NUM_THREADS":"1","OMP_NUM_THREADS":"1"})
    if result.returncode:
        raise RuntimeError(f"{label} failed ({result.returncode}); see scratch/review_completion_{label}.log")
    print(f"completed {label}",flush=True)


def main():
    global _resume_label,_resume_reached
    parser=argparse.ArgumentParser()
    parser.add_argument("--start-at",choices=["source_refits","opened_transfer_refit","opened_transfer_analysis","cold_to_hot_refits","before_2010_refits","non_air_refit_refits","bridge_repair","source_analysis","cold_to_hot_analysis","before_2010_analysis","non_air_refit_analysis","air_exposure_cases","air_exposure_analysis","adaptation","meaning","failure_map","group_robustness","formal_semi_rcps","formal_conditional","regional_rankings","observed_records","probability_ablation","deep_matched_annual","nonlinear_inputs","local_nonlinear_controls","nearby_observed_air","flow_comparators","focused_diagnostics","zero_flow_missingness","full_USGS_forcing","source_coordinates","full_Europe_forcing","USGS_forcing_recovery","Europe_forcing_recovery","H7_target_refits","H7_target_evidence","national_forcing","national_application","national_meaning","deployment_candidate","independent_metadata_horizons","independent_metadata_wellington","source_registration_inputs","independent_roster","final_evidence","prereg_final_bundle","archive_execution","final_validation"])
    args=parser.parse_args();_resume_label=args.start_at;_resume_reached=args.start_at is None
    wait_for([OUT/"cases/leave_one_year_out/summary.json"],"20-seed source generation")
    run("source_refits",["scripts/466_review_completion_refit.py","--workers","48"])
    run("opened_transfer_refit",["scripts/479_review_completion_opened_transfer.py"])
    run("opened_transfer_analysis",["scripts/467_review_completion_analysis.py","--split","opened_transfer","--seeds","0","--workers","1","--skip-trends"])
    for split in ["cold_to_hot","before_2010","non_air_refit"]:
        wait_for([OUT/"cases"/split/"summary.json"],f"{split} generation")
        run(split+"_refits",["scripts/466_review_completion_refit.py","--split",split,"--seeds","0","1","2","--workers","32"])
    run("bridge_repair",["scripts/483_review_completion_bridge_repair.py","--workers","24"])
    run("source_analysis",["scripts/467_review_completion_analysis.py","--workers","16"])
    for split in ["cold_to_hot","before_2010"]:
        run(split+"_analysis",["scripts/467_review_completion_analysis.py","--split",split,"--seeds","0","1","2","--workers","3","--skip-trends"])
    run("non_air_refit_analysis",["scripts/467_review_completion_analysis.py","--split","non_air_refit","--seeds","0","1","2","--workers","3"])
    run("air_exposure_cases",["scripts/465_review_completion_cases.py","--split","air_exposure","--seeds","0","1","2","--workers","48","--resume"])
    run("air_exposure_analysis",["scripts/499_review_completion_air_exposure.py","--workers","3"])
    run("adaptation",["scripts/470_review_completion_adaptation.py","--workers","16"])
    run("meaning",["scripts/471_review_completion_meaning.py"])
    run("failure_map",["scripts/482_review_completion_failure_map.py"])
    run("group_robustness",["scripts/486_review_completion_group_robustness.py","--workers","8"])
    run("formal_semi_rcps",["scripts/487_review_completion_semi_rcps.py","--workers","8"])
    run("formal_conditional",["scripts/488_review_completion_conditional_conformal.py","--workers","8"])
    run("regional_rankings",["scripts/489_review_completion_regional_rankings.py"])
    run("observed_records",["scripts/491_review_completion_observed_record_bounds.py"])
    run("probability_ablation",["scripts/492_review_completion_probability_ablation.py"])
    wait_for([OUT/f"deep/seed_{seed:02d}/csdi_cases.parquet" for seed in [0,1,2]],"three CSDI comparator fits and sampled predictions")
    run("deep_matched_annual",["scripts/481_review_completion_deep_match.py"])
    run("nonlinear_inputs",["scripts/484_review_completion_nonlinear_inputs.py"])
    run("local_nonlinear_controls",["scripts/493_review_completion_local_boosting.py"])
    run("nearby_observed_air",["scripts/505_review_completion_observed_air.py","--all-source","--exact-source-ridge"])
    run("flow_comparators",["scripts/517_review_completion_flow_comparators.py","--workers","24"])
    run("focused_diagnostics",["scripts/518_review_completion_focused_diagnostics.py"])
    run("zero_flow_missingness",["scripts/519_review_completion_zero_flow_missingness.py","--workers","24","--draws","400"])
    run("full_USGS_forcing",["scripts/507_review_completion_full_forcing.py","--workers","2","--analysis-workers","16"])
    run("source_coordinates",["scripts/513_review_completion_source_coordinates.py"])
    run("full_Europe_forcing",["scripts/510_review_completion_europe_full.py","--workers","2","--analysis-workers","16"])
    run("USGS_forcing_recovery",["scripts/515_review_completion_forcing_recovery.py","--region","usgs","--workers","16"])
    run("Europe_forcing_recovery",["scripts/515_review_completion_forcing_recovery.py","--region","europe","--workers","16"])
    run("H7_target_refits",["scripts/506_review_completion_window_refits.py","--workers","48","--resume","--with-trends"])
    run("H7_target_evidence",["scripts/509_review_completion_window_evidence.py"])
    run("deployment_candidate",["scripts/485_review_completion_deployment.py"])
    national_acquisition=OUT/"national_meaning/acquisition.json"
    if national_acquisition.exists() and json.loads(national_acquisition.read_text()).get("all_planned_attempted"):
        run("national_forcing",["scripts/501_review_completion_national_forcing.py","--workers","2"])
        run("national_application",["scripts/502_review_completion_national_application.py","--workers","24","--resume"])
        run("national_meaning",["scripts/503_review_completion_national_meaning.py","--bootstrap","2000"])
    run("independent_metadata_horizons",["scripts/494_review_completion_independent_metadata.py"])
    run("independent_metadata_wellington",["scripts/494_review_completion_independent_metadata.py","--agency","greater_wellington"])
    run("source_registration_inputs",["scripts/472_review_completion_prereg.py"])
    run("independent_roster",["scripts/498_review_completion_freeze_independent_roster.py"])
    run("final_evidence",["scripts/473_review_completion_evidence.py"])
    run("prereg_final_bundle",["scripts/472_review_completion_prereg.py"])
    run("archive_execution",["scripts/516_review_completion_archive_smoke.py"])
    run("final_validation",["scripts/474_review_completion_validate.py"])
    if not _resume_reached:
        raise RuntimeError("Resume stage was not reached")
    print("All local evidence stages finished. Public registration and independent evaluation remain external.",flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())

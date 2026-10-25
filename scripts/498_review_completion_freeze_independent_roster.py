#!/usr/bin/env python3
"""Freeze the outcome-free small failure-detection cohort before OSF submission."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.independent import fetch_metadata,sha256
from stream_recoverability.seeds import plain_seed

STUDY=T.ROOT/"results/wrr_review_completion_20261024/independent_study"


def main():
    status=json.loads((STUDY/"public_registration_status.json").read_text())
    if status.get("status")!="not_publicly_registered":raise RuntimeError("Preserve the public registration snapshot; do not refreeze its roster")
    meta=json.loads((STUDY/"greater_wellington/qualification_summary.json").read_text())
    if not meta["all_sites_resolved"] or meta["errors"]:raise RuntimeError("Finish outcome-free metadata screening first")
    roster=pd.read_csv(STUDY/"greater_wellington/potential_roster.csv")
    if roster.empty:raise RuntimeError("No metadata-eligible candidate")
    source=T.load_script("r4_registered_source_roles",T.ROOT/"scripts/466_review_completion_refit.py")
    water=T.load_script("r4_registered_native_qc",T.ROOT/"scripts/496_review_completion_independent_acquisition.py")
    forcing=T.load_script("r4_registered_native_forcing",T.ROOT/"scripts/497_review_completion_independent_cases.py")
    # Search only old data directories. Newly downloaded catalogs under results
    # are not evidence of prior access to river-temperature outcomes.
    patterns=["Greater Wellington","New Zealand",'"NZ"',*roster.site.tolist()]
    command=["rg","-i","-F","-l","--no-messages","--glob","*metadata*.csv","--glob","*manifest*.json","--glob","*catalog*.json","--glob","*roster*.csv"]
    for pattern in patterns:command += ["-e",pattern]
    command += [str(T.ROOT/"data"),str(T.ROOT/"data_versions")]
    scan=subprocess.run(command,capture_output=True,text=True)
    if scan.returncode not in [0,1]:raise RuntimeError("Prior metadata scan did not finish")
    matches=scan.stdout.splitlines()
    audit={"scope":"local data/data_versions metadata, manifests, rosters and catalogs; not proof about unrelated accounts or all past human knowledge",
           "searched_patterns":patterns,"matched_paths":matches,"temperature_values_read":False,
           "prior_access_exclusion":"no candidate/agency evidence in this workspace's prior source metadata" if not matches else "unresolved matches; do not freeze"}
    T.write_json(STUDY/"prior_access_audit.json",audit)
    if matches:raise RuntimeError("Review prior metadata matches before freezing a new cohort")
    ranges=[]
    for row in roster.itertuples(index=False):
        response=fetch_metadata(water.ENDPOINT,STUDY/"greater_wellington/requests","TimeRange",Site=row.site,Measurement=row.measurement)
        for tag in ["From","To"]:
            stamp=pd.Timestamp(response.findtext(tag))
            if stamp.tzinfo is None or stamp.utcoffset().total_seconds()!=43200:
                raise RuntimeError("Provider TimeRange does not confirm the frozen NZST offset")
        ranges.append({"site":row.site,"from":response.findtext("From"),"to":response.findtext("To")})
    roster["station_id"]=roster.site.map(lambda s:"gw_"+hashlib.sha256(s.encode()).hexdigest()[:10])
    roster["station_key"]="nz_gw|"+roster.station_id
    roster["independence_group"]=roster.conservative_group.map(lambda s:"nz_gw_zone_"+hashlib.sha256(s.encode()).hexdigest()[:10])
    roster["network_id"]=roster.independence_group
    roster["provider"]="nz_gw"
    roster=roster.sort_values("station_key")
    path=STUDY/"greater_wellington/registration_roster.csv";roster.to_csv(path,index=False)
    c=pd.read_parquet(source.OUT/"cases/leave_one_year_out/seed_00.parquet",columns=["region","independence_group","policy_choice","eval_truth_h30","air_warm_z_mean"])
    c=c.loc[c.policy_choice.ne("unavailable")&c.eval_truth_h30.notna()].reset_index(drop=True)
    number=sorted(set(c.region.unique())|{"global_source_candidate"}).index("global_source_candidate")
    _,roles,weights=source.roles(c,"global_source_candidate",plain_seed(7,0,number))
    candidate=json.loads((source.OUT/"deployment/candidate.json").read_text())
    if roles!=candidate["roles"]:raise RuntimeError("Source role reconstruction differs from the fixed model")
    plan={"status":"metadata_roster_frozen","provider":"greater_wellington","endpoint":water.ENDPOINT,
          "metadata_roster_file":str(path.relative_to(STUDY)),"metadata_roster_sha256":sha256(path),
          "qc_specification":water.QC_SPEC,"native_time_zone":"NZST fixed UTC+12, confirmed by all candidate TimeRange metadata",
          "provider_time_ranges":ranges,"observation_end_exclusive":"2026-07-01T00:00:00",
          "source_model_sha256":sha256(source.OUT/"deployment/global_source_candidate.joblib"),
          "classical_calibration_sha256":sha256(source.OUT/"deployment/classical_calibration.json"),
          "source_case_settings_sha256":sha256(STUDY/"source_case_settings.json"),
          "source_generator_sha256":sha256(STUDY/"source_missingness_generator.json"),
          "source_decision_hot_cutoff":float(c.loc[weights["estimator"]>0,"air_warm_z_mean"].quantile(.9)),
          "air_forcing":forcing.AIR_SPEC,"independence_groups_verified":True,"prior_temperature_access_excluded":True,
          "grouping_evidence":"Agency SurfaceWaterZone conservatively merges connected Hutt tributaries and Wainuiomata, all Ruamahanga tributaries, and the selected Kapiti coastal catchments. Predictors share water donors only within these merged groups. Management grouping is structural; independent/exchangeable weather and errors across zones remain assumptions.",
          "n_prospective_stations":len(roster),"n_conservative_groups":roster.independence_group.nunique(),
          "domain":"Continuous river records with at least four strict QC complete hot years after acquisition. No dry-bed physical temperature claim. All metadata-eligible candidates included; distance-based domain flags diagnostic only, never tuned on target errors.",
          "study_interpretation":"Small prospective failure-detection/descriptive study; no budget reached 80 percent source planning power. Three conservative zones cannot implement E5 at ten labeled groups. No confirmation of universal transfer or individual conditional risk.",
          "temperature_values_requested":False,"public_registration_required_before_acquisition":True}
    T.write_json(STUDY/"acquisition_plan.json",plan)
    print(f"Metadata roster fixed: {len(roster)} prospective stations, {roster.independence_group.nunique()} conservative zones; no river values requested.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())

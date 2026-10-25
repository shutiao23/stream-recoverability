#!/usr/bin/env python3
"""Metadata-only independent-study preparation and public-registration gate.

No method in this file downloads river-temperature values. A local protocol
file is never called a public registration. Verification reads OSF's public
record and checks the attached protocol name before changing the status.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import platform
from datetime import datetime,timezone
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import requests
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed
from stream_recoverability.experiments.tr_revision.independent import (
    accepted_public_registration, registration_identifier, verify_registration_attachments,require_acquisition_plan,
)

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]/"independent_study"
DOC=T.ROOT/"docs/reviews/wrr_review_completion_20261024"


def metadata_only():
    OUT.mkdir(parents=True,exist_ok=True)
    endpoint="https://envirodata.horizons.govt.nz/api/hilltop/data"
    request={"Service":"Hilltop","Request":"SiteList","Location":"Yes"}
    response=requests.get(endpoint,params=request,timeout=60)
    response.raise_for_status()
    root=ET.fromstring(response.content)
    if any(e.tag.rsplit("}",1)[-1] in ["Data","E","V","Value"] for e in root.iter()):
        raise RuntimeError("Metadata response unexpectedly contains observations; do not ingest")
    (OUT/"horizons_site_list.xml").write_bytes(response.content)
    sites=[]
    for site in root.iter("Site"):
        sites.append({"site":site.attrib.get("Name"),**{child.tag:child.text for child in site}})
    pd.DataFrame(sites).to_csv(OUT/"metadata_site_catalog.csv",index=False)
    T.write_json(OUT/"metadata_request.json",{"url":response.url,"retrieved_utc":datetime.now(timezone.utc).isoformat(),"water_temperature_values_requested":False,"role":"catalog only; no series availability or river-connectivity qualification inferred","n_sites":len(sites)})


def verify_osf(identifier, attachments=False):
    # Only a public accepted registration has a usable registration timestamp.
    identifier=registration_identifier(identifier)
    if attachments:
        paths=[OUT/"registration_code_and_protocol.tar.gz",OUT/"protocol_draft.json",OUT/"file_sha256.json"]
        status=verify_registration_attachments(identifier,paths)
        try:
            require_acquisition_plan(OUT,status)
            status["acquisition_ready"]=True
        except (RuntimeError,FileNotFoundError,KeyError) as error:
            status["acquisition_ready"]=False
            status["remaining_requirement"]=str(error)
        T.write_json(OUT/"public_registration_status.json",status)
        return
    response=requests.get(f"https://api.osf.io/v2/registrations/{identifier}/?version=2.20",timeout=30)
    response.raise_for_status()
    document=response.json();attributes=document["data"]["attributes"]
    accepted_public_registration(document,identifier)
    T.write_json(OUT/"osf_public_record.json",document)
    T.write_json(OUT/"public_registration_status.json",{"status":"public_record_found_requires_protocol_attachment_check","url":f"https://osf.io/{identifier}/","registered_utc":attributes.get("date_registered"),"water_temperature_values_requested":False,"attachment_verification":"Confirm protocol and exact model/code archive attachments before acquisition. A different registration is not sufficient."})


def power():
    rows=[]
    for seed in CONFIG["seeds"]:
        files=sorted((OUT.parent/f"refits/leave_one_year_out/seed_{seed:02d}").glob("*.parquet"))
        if not files:return None
        c=pd.concat([pd.read_parquet(p,columns=["independence_group","design_family","D2","eval_truth_h30","risk_score"]) for p in files])
        c=c.loc[c.design_family.eq("crossed")].copy();c["admitted"]=c.risk_score.le(.1)
        c["bad"]=c.admitted&(c.D2-c.eval_truth_h30).abs().gt(.5)
        g=c.groupby("independence_group").agg(a=("admitted","sum"),b=("bad","sum"))
        a,b=g.a.to_numpy(float),g.b.to_numpy(float)
        for n in [20,30,40,60,80,100,150,200]:
            rng=np.random.default_rng(plain_seed(72,seed,n));index=rng.integers(0,len(g),(2000,n))
            admitted=a[index];bad=b[index];total=admitted.sum(axis=1)
            risk=np.divide(bad.sum(axis=1),total,out=np.full(2000,np.nan),where=total>0)
            evaluable=admitted>=20;ratios=np.divide(bad,admitted,out=np.full_like(bad,np.nan),where=admitted>0)
            excess=np.divide(((ratios>.1)&evaluable).sum(axis=1),evaluable.sum(axis=1),out=np.full(2000,np.nan),where=evaluable.sum(axis=1)>0)
            influence=(bad-risk[:,None]*admitted)/np.maximum(admitted.mean(axis=1)[:,None],1e-12)
            upper=risk+1.645*influence.std(axis=1,ddof=1)/np.sqrt(n)
            success=np.isfinite(risk+excess)&(risk<=.06)&(upper<=.08)&(excess<=.1)
            rows.append(dict(seed=seed,independent_groups=n,simulation_repetitions=2000,joint_E1_E2_probability=float(success.mean())))
    per_seed=pd.DataFrame(rows);per_seed.to_csv(OUT/"sample_size_planning_by_seed.csv",index=False)
    combined=[]
    for n,b in per_seed.groupby("independent_groups"):
        p=b.joint_E1_E2_probability
        combined.append(dict(independent_groups=n,n_source_seeds=b.seed.nunique(),simulation_repetitions_per_seed=2000,total_simulations=2000*len(b),joint_E1_E2_probability=float(p.mean()),source_seed_lower=float(p.quantile(.025)),source_seed_upper=float(p.quantile(.975))))
    result=pd.DataFrame(combined);result.to_csv(OUT/"sample_size_planning.csv",index=False)
    T.write_json(OUT/"planning_design.json",{"source_seeds":CONFIG["seeds"],"mixing":"equal mixture of seed-specific independent-group empirical resampling; 2000 simulations per seed and group budget","interpretation":"algorithm and source-group composition sensitivity on the same opened archive, not independent climates or confirmed new-region power","E1_interval":"delta-method planning approximation; registered evaluation uses group bootstrap","joint":"E1 and E2 must both pass; zero admission or no evaluable group fails"})
    return result


def prepare():
    OUT.mkdir(parents=True,exist_ok=True);DOC.mkdir(parents=True,exist_ok=True)
    status_path=OUT/"public_registration_status.json"
    if status_path.exists() and str(json.loads(status_path.read_text()).get("status","")).startswith("public_"):
        raise RuntimeError("A public registration record has been recorded. Preserve the existing code/model archive and checksum; use a separately versioned study directory for any later draft.")
    if not (OUT/"public_registration_status.json").exists():
        T.write_json(OUT/"public_registration_status.json",{"status":"not_publicly_registered","water_temperature_values_requested":False,"blocker":"OSF account/project, verified investigators and publicly accepted registration required; no authenticated OSF connector available","local_file_is_registration":False})
    registration=json.loads((OUT/"public_registration_status.json").read_text())
    if registration.get("status")=="not_publicly_registered":
        registration.pop("blocker",None)
        registration["next_requirement"]="user-managed public OSF registration and matching protocol/model attachments before any new observation access"
        registration["author_and_platform_fields"]="user will fill these fields"
        T.write_json(OUT/"public_registration_status.json",registration)
    protocol={"status":"ready_for_author_review_then_OSF_submission; not registered","population":"New Zealand regional-council continuous river temperature, Horizons first, followed by independent councils only if the fixed metadata eligibility fails; no temperature values before public registration","metadata_source":"https://envirodata.horizons.govt.nz/api/hilltop/data","eligibility":{"minimum_complete_hot_years":4,"daily_mean":"agency daily mean, or verified complete subdaily aggregation with QC; no monthly WQ samples","hot_year":"July-June using actual calendar boundaries","river_only":True,"exclude_existing_stations_and_connected_networks":True,"network":"connected catchments, conservative joins across shared rivers and donors","minimum_group_evaluable_admissions":20,"sampling_stop":"metadata roster fixed before observations; no performance-based substitutions"},"method":{"estimators":["source-developed functional debias point","distribution regression with group-disjoint interval calibration","MOVE1 warm and annual","stochastic AR1 bridge"],"decision":"source-fixed individual risk score <= 0.1; batch policy adds maximum individual score 0.3","tolerance_c":.5,"source_model_selection":"select from case-level proper scores and group diagnostics before signing; do not select on target outcomes","local_calibration_secondary":[2,4,8,10,16]},"endpoints":{"E1":{"role":"primary","population":"controlled 30/60/90-day gaps","risk_max":.06,"one_sided_95_group_bootstrap_upper_max":.08,"nonempty_required":True},"E2":{"role":"co_primary","group_failure_risk_threshold":.1,"max_fraction_exceeding":.1,"minimum_admitted_per_group":20,"empty_groups":"report unavailable, do not count as passes"},"E3":{"role":"secondary","stratum":"decision-time peak_overlap >= 0.5","coverage90_range":[.85,.95],"interval_score":True},"E4":{"role":"secondary","stratum":"same decision-time danger stratum","mae_reduction_vs_plugin_min":.2},"E5":{"role":"descriptive","label_budget_groups":10,"report":"bounded-group certified retention, certificate status and worst-group risk"}},"inference":{"unit":"independent connected-catchment group","bootstrap_draws":2000,"E1_E2_joint_success":"intersection, with E1 confidence bound and point-estimate E2; no claim of simultaneous confidence for every group","handling_unavailable":"retain denominator and reason; do not impute success","multiplicity":"E1 and E2 must both pass; E3/E4 secondary, Holm adjustment for inferential superiority tests"},"acquisition":"only after OSF public timestamp, attached model/code archive, metadata roster and eligibility signed; a local timestamp or an unrelated registration cannot authorize it","failure_text":"Unchanged source calibration did not control both overall and group risks; local labeled groups are needed. Report required labels only if the prespecified curve supports a budget.","success_text":"The preregistered overall and group endpoints were met in this sampled region; individual conditional risk and other climates remain unproven.","authorship":"requires verified investigator names, affiliations, contact and funding","implementation_files":["scripts/465_review_completion_cases.py","scripts/466_review_completion_refit.py","scripts/467_review_completion_analysis.py","scripts/470_review_completion_adaptation.py"]}
    protocol["status"]="draft_for_failure_detection_design_review; not publicly registered; qualified metadata roster incomplete"
    protocol["authorship"]="user-owned: the user will fill author, affiliation, funding and platform/deposit fields"
    protocol["method"]["primary_release_value"]="calibrated D2 median; this is the source failure classifier's target"
    protocol["method"]["source_model_selection"]="source-only global candidate already fitted with seed zero and four disjoint group roles; candidate.json records the choice; no target outcomes used"
    protocol["method"]["candidate_file"]="results/wrr_review_completion_20261024/deployment/global_source_candidate.joblib"
    protocol["method"]["decision"]="primary single-value release: source-fixed D2 failure score <= 0.1; any separately reported batch policy must also cap individual scores at 0.3"
    protocol["method"]["scope"]="classical estimation is a comparator; it does not inherit the classifier trained for D2 errors"
    protocol["method"]["target_history_use"]="Offline reconstruction: daily regression, climatology and residual models use the target station's other historical years under the fixed recipe; the evaluated whole year is excluded. Later historical years may be used. Annual distribution-regression/P2 weights, failure classifier, interval offsets and decision-hot cutoff remain source-only. This is not a real-time forecast or absence of all target-history fitting."
    protocol["method"]["local_comparators"]=["bounded-group selected-risk certificate","labeled-only WSR RCPS","general-loss semi-supervised RCPS with WSR, distinct unlabeled calibration groups and untouched test groups"]
    protocol["method"]["conditional_conformal_scope"]="auxiliary conservative and independently randomized binary-LAC prediction sets; coverage/false-admission frequency reported separately from selected risk; no substitution for the E2 group-risk endpoint"
    protocol["method"]["batch_policy_scope"]="not a primary endpoint; any additional batch method must have its full source calibration and individual cap fixed in the public protocol before values, not selected after target outcomes"
    protocol["metadata_screening"]={"observation_access":False,"fixed_fallback_order":["Horizons public continuous archive","Greater Wellington public continuous archive"],"fallback_trigger":"fewer than four calendar-supported July-June years or no qualified continuous river series, determined exclusively from metadata","horizons_result":"58 collection sites screened; zero potentially eligible sites in the current public archive; no predictive test performed","qualification_files":["horizons_metadata/qualification_summary.json","greater_wellington/qualification_summary.json"],"grouping":"Horizons catchment; Greater Wellington conservatively merged surface-water management zones, with any shared donors/connectivity merged before freezing; zone counts are not automatically independent catchment counts"}
    protocol["implementation_files"] += ["scripts/494_review_completion_independent_metadata.py","scripts/495_review_completion_independent_analysis.py","scripts/496_review_completion_independent_acquisition.py","scripts/497_review_completion_independent_cases.py","scripts/498_review_completion_freeze_independent_roster.py","src/stream_recoverability/experiments/tr_revision/independent.py","src/stream_recoverability/experiments/tr_revision/native_temperature.py"]
    plan_template={"status":"draft_not_qualified_not_acquisition_authorization","provider":"greater_wellington_metadata_fallback","metadata_roster_file":None,"metadata_roster_sha256":None,"source_model_sha256":hashlib.sha256((OUT.parent/"deployment/global_source_candidate.joblib").read_bytes()).hexdigest(),"qc_specification":None,"native_time_zone":"NZST, fixed UTC+12, subject to explicit provider time metadata verification","independence_groups_verified":False,"prior_temperature_access_excluded":False,"required_before_registration":"Freeze a nonempty eligible roster with station_key and independence_group, provider-specific quality/cadence/daily aggregation, shared-donor network joins, full prior-access exclusion and acquisition endpoints. This template cannot authorize any value access."}
    T.write_json(OUT/"acquisition_plan.template.json",plan_template)
    T.write_json(OUT/"source_case_settings.json",T.settings()|{"classical_baselines":True,"trajectory_targets":["h30"],"replication_seeds":[0],"training_split":"leave_one_year_out"})
    T.write_json(OUT/"source_missingness_generator.json",json.loads((T.E1_MISSINGNESS/"mnar_generator.json").read_text()))
    if (OUT/"acquisition_plan.json").exists():
        plan=json.loads((OUT/"acquisition_plan.json").read_text())
        for name,field in [("source_case_settings.json","source_case_settings_sha256"),("source_missingness_generator.json","source_generator_sha256")]:
            if hashlib.sha256((OUT/name).read_bytes()).hexdigest()!=plan[field]:raise RuntimeError("Frozen generation inputs changed; review a separately versioned plan before registration")
        protocol["status"]="metadata-roster-frozen failure-detection draft; user platform fields and public registration still pending"
        protocol["prospective_cohort"]={"provider":plan["provider"],"stations":plan["n_prospective_stations"],"conservative_groups":plan["n_conservative_groups"],"roster":"greater_wellington/registration_roster.csv","acquisition_plan":"acquisition_plan.json","water_values_opened":False,"qualification":"metadata only; strict quality-complete years are checked once after registration"}
        protocol["measurement"]={"qc":plan["qc_specification"],"native_clock":plan["native_time_zone"],"air":plan["air_forcing"],"observation_end_exclusive":plan["observation_end_exclusive"]}
        protocol["endpoints"]["E5"]["feasibility"]="Not implementable in the fixed three-zone cohort; report unavailable, not zero-risk certified retention"
        protocol["success_text"]="This small prospective cohort met the prespecified descriptive sample criteria. Three conservative management zones do not establish population-level 95 percent risk control, general climate transfer, or any individual conditional guarantee."
        protocol["failure_text"]="Unchanged source calibration did not meet the prespecified descriptive criteria. With three zones the ten-labeled-group comparison is unavailable; no sufficient local-label budget has been established. Report the observed failures and all qualification/availability limits."
    planning=power()
    protocol["planning"]={"joint_E1_E2_target_probability":.8,"n_source_seeds":20,"simulations_per_group_budget":40000,"budget_reaching_target":None if planning is None or not planning.joint_E1_E2_probability.ge(.8).any() else int(planning.loc[planning.joint_E1_E2_probability.ge(.8),"independent_groups"].min()),"interpretation":"No tested equal-seed source planning mixture reaches 80%; algorithm and group-composition variation is substantial. Source-seed quantiles are not new-climate uncertainty or verified transfer power. This is failure-detection design material until publicly registered with a qualified roster."}
    T.write_json(OUT/"protocol_draft.json",protocol)
    versions={"python":platform.python_version()}
    for package in ["numpy","pandas","scipy","scikit-learn","lightgbm","torch","pypots","pyarrow","statsmodels","conditionalconformal","cvxpy"]:
        try:
            versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package]=None
    T.write_json(OUT/"environment_versions.json",versions)
    bundle=OUT/"registration_code_and_protocol.tar.gz"
    paths=[OUT/"protocol_draft.json",OUT/"environment_versions.json",OUT/"acquisition_plan.template.json",OUT/"source_case_settings.json",OUT/"source_missingness_generator.json",T.ROOT/"configs/wrr_review_completion_20261024.json",T.ROOT/"configs/wrr_target_recovery_20261022.json",T.ROOT/"pyproject.toml",T.ROOT/"Makefile"]
    for name in ["acquisition_plan.json"]:
        if (OUT/name).exists():
            paths.append(OUT/name)
            frozen=json.loads((OUT/name).read_text())
            if frozen.get("metadata_roster_file"):
                roster=OUT/frozen["metadata_roster_file"]
                if not roster.resolve().is_relative_to(OUT.resolve()):raise RuntimeError("Roster must be within the study directory")
                paths.append(roster)
    if (OUT/"prior_access_audit.json").exists():paths.append(OUT/"prior_access_audit.json")
    for name in ["source_interface_smoke.json","air_interface_check.json"]:
        if (OUT/name).exists():paths.append(OUT/name)
    # Include transitive local source dependencies, not just entry points.
    paths+=sorted((T.ROOT/"src").rglob("*.py"))
    paths+=sorted((T.ROOT/"scripts").rglob("*.py"))
    paths+=sorted((T.ROOT/"tests").rglob("*.py"))
    supplement=T.ROOT/"configs/wrr_review_national_supplement_20261024.json"
    if supplement.exists():paths.append(supplement)
    paths+=sorted((T.ROOT/"docs/reviews/wrr_review_completion_20261024").glob("*.md"))
    paths+=sorted((OUT.parent/"refits/leave_one_year_out/seed_00").glob("*.joblib"))
    paths+=sorted((OUT.parent/"deployment").glob("*.joblib"))+sorted((OUT.parent/"deployment").glob("*.json"))+sorted((OUT.parent/"deployment").glob("*.parquet"))
    for name in ["claim_stability.csv","rules_summary.csv","scorecard_summary.csv"]:
        path=OUT.parent/"evidence"/name
        if path.exists():
            paths.append(path)
    for metadata_path in [OUT/"metadata_site_catalog.csv",OUT/"metadata_request.json",OUT/"sample_size_planning.csv",OUT/"sample_size_planning_by_seed.csv",OUT/"planning_design.json"]:
        if metadata_path.exists():
            paths.append(metadata_path)
    for folder in ["horizons_metadata","greater_wellington","horizons_lawa"]:
        paths+=sorted(p for p in (OUT/folder).rglob("*") if p.is_file())
    paths=sorted(set(paths))
    manifest={str(p.relative_to(T.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    T.write_json(OUT/"file_sha256.json",manifest)
    paths.append(OUT/"file_sha256.json")
    with tarfile.open(bundle,"w:gz") as tar:
        for path in paths:
            tar.add(path,arcname=str(path.relative_to(T.ROOT)))
    T.write_json(OUT/"bundle_inventory.json",{"files":[str(p.relative_to(T.ROOT)) for p in paths],"bytes":bundle.stat().st_size,"sha256":hashlib.sha256(bundle.read_bytes()).hexdigest(),"registered":False,"all_final_models_included":(OUT.parent/"deployment/global_source_candidate.joblib").exists(),"sample_size_planning_available":planning is not None,"author_and_platform_fields":"user will fill these fields; they are not invented"})
    return protocol


def main():
    p=argparse.ArgumentParser();p.add_argument("--metadata",action="store_true");p.add_argument("--osf-registration");p.add_argument("--verify-attachments",action="store_true");p.add_argument("--planning-only",action="store_true");a=p.parse_args()
    if a.verify_attachments and not a.osf_registration:
        p.error("--verify-attachments requires --osf-registration")
    if a.planning_only:
        OUT.mkdir(parents=True,exist_ok=True);power();return 0
    if a.osf_registration:
        # Public-record verification must not silently rebuild the uploaded
        # archive: gzip timestamps alone would change its frozen checksum.
        OUT.mkdir(parents=True,exist_ok=True)
        if a.verify_attachments:verify_osf(a.osf_registration,attachments=True)
        else:verify_osf(a.osf_registration)
        return 0
    prepare()
    if a.metadata:
        try:
            metadata_only()
        except Exception as error:
            T.write_json(OUT/"metadata_unavailable.json",{"error":str(error),"water_temperature_values_requested":False})
    return 0


if __name__=="__main__":
    raise SystemExit(main())

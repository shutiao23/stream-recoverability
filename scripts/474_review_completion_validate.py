#!/usr/bin/env python3
"""Validate produced evidence without conflating external dependencies with runs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import wrr_tr_common as T

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]


def sha256_stream(stream):
    digest=hashlib.sha256()
    for block in iter(lambda:stream.read(1<<20),b""):
        digest.update(block)
    return digest.hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument("--partial",action="store_true");a=p.parse_args()
    checks=[]
    required_seeds=CONFIG["seeds"]
    seen=[]
    for seed in required_seeds:
        path=OUT/f"analyses/leave_one_year_out/seed_{seed:02d}/summary.json"
        if not path.exists():
            if not a.partial:
                raise AssertionError(f"Missing seed {seed}")
            continue
        summary=json.loads(path.read_text());assert summary["complete"]
        assert summary.get("analysis_version")==CONFIG["analysis_version"],f"Stale analysis: {path}"
        assert summary["trend_replicates"]==CONFIG["trend_replicates"]
        seen.append(seed)
        for meta_path in sorted((OUT/f"refits/leave_one_year_out/seed_{seed:02d}").glob("*.json")):
            meta=json.loads(meta_path.read_text())
            if "roles" not in meta:
                continue
            roles=[set(v) for v in meta["roles"].values()]
            held=set(meta["held_groups"])
            for i,role in enumerate(roles):
                assert not role.intersection(held),f"Held-group leakage: {meta_path}"
                for other in roles[:i]:
                    assert not role.intersection(other),f"Role leakage: {meta_path}"
            frame=pd.read_parquet(meta_path.with_suffix(".parquet"),columns=["risk_score","D2_q05","D2_q50","D2_q95"])
            assert frame.risk_score.between(0,1).all()
            assert (frame.D2_q05<=frame.D2_q50).all() and (frame.D2_q50<=frame.D2_q95).all()
        rules=pd.read_csv(path.parent/"rules.csv")
        assert rules.retention.between(0,1).all()
        empty=rules.n_admitted.eq(0)
        assert rules.loc[empty,"risk"].isna().all(),"Empty admissions cannot be zero-risk successes"
        individual=rules.rule.eq("individual_0.1")&~empty
        assert rules.loc[individual,"max_admitted_probability"].le(.1+1e-12).all()
    checks.append({"check":"full_seed_analyses","observed":len(seen),"required":20,"passed":len(seen)==20})
    status_path=OUT/"independent_study/public_registration_status.json"
    status={}
    if status_path.exists():
        status=json.loads(status_path.read_text())
        if status["water_temperature_values_requested"]:
            assert status["status"]=="public_registration_and_attachments_verified"
            receipt=json.loads((OUT/"independent_study/acquisition_receipt.json").read_text())
            assert pd.Timestamp(receipt["first_temperature_request_utc"])>pd.Timestamp(status["registered_utc"])
        checks.append({"check":"new_values_not_requested_before_registration","passed":True})
    if not a.partial:
        for split in ["cold_to_hot","before_2010","non_air_refit"]:
            for seed in [0,1,2]:
                summary_path=OUT/f"analyses/{split}/seed_{seed:02d}/summary.json"
                assert summary_path.exists(),f"Missing differential split {split}/{seed}"
                assert json.loads(summary_path.read_text()).get("analysis_version")==CONFIG["analysis_version"],f"Stale differential analysis {summary_path}"
        for seed in [0,1,2]:
            for model in ["boosting","lstm","saits","csdi"]:
                path=OUT/f"deep/seed_{seed:02d}/{model}_cases.parquet"
                assert path.exists(),f"Missing deep comparator {path}"
            csdi=pd.read_parquet(OUT/f"deep/seed_{seed:02d}/csdi_cases.parquet")
            assert csdi.n_draws.eq(20).all()
            flow=pd.read_parquet(OUT/f"deep/seed_{seed:02d}/boosting_with_flow_cases.parquet")
            assert flow.loc[~flow.available,"h30_estimate"].isna().all(),"Unsupported flow input is unavailable, not an easy successful case"
            for name in ["boosting_local_air","boosting_local_flow"]:
                local=pd.read_parquet(OUT/f"deep/seed_{seed:02d}/{name}_cases.parquet")
                assert len(local)==len(csdi)
                assert local.loc[~local.available,"h30_estimate"].isna().all()
        deep=pd.read_csv(OUT/"evidence/deep_scorecard_per_seed.csv")
        assert (deep.n_valid<=deep.n_eligible).all()
        assert deep.loc[deep.n_valid.eq(0),"failure_rate"].isna().all()
        for name in ["forcing_ablation_cases.parquet","natural_gap_sample_size.csv","station_characteristics.csv"]:
            assert (OUT/"inputs"/name).exists()
        assert (OUT/"daily_max/status.json").exists()
        flow_folder=OUT/"flow_comparators"
        flow_status=json.loads((flow_folder/"status.json").read_text())
        flow_control=json.loads((flow_folder/"historical_control_audit.json").read_text())
        assert flow_status["complete"] and flow_control["passed"]
        for name,digest in flow_status["source_inputs_sha256"].items():
            assert hashlib.sha256((T.ROOT/name).read_bytes()).hexdigest()==digest,name
        flow_cases=pd.read_parquet(flow_folder/"case_predictions.parquet")
        assert len(flow_cases)==flow_status["n_cases"]==flow_control["n_cases"]==134925
        assert flow_cases.site.nunique()==flow_status["n_sites"]==255
        for column in ["single_donor_ridge_log7q","move1_log7q","stochastic_log7q"]:
            paired=flow_cases[column].notna()&flow_cases.recorded_log7q.notna()
            assert flow_cases.loc[paired,column].le(flow_cases.loc[paired,"recorded_log7q"]+1e-10).all()
        assert flow_cases.loc[flow_cases.layer_donor.eq(1),"stochastic_log7q_draws"].map(len).eq(20).all()
        checks.append({"check":"matched low-flow classical comparisons, historical controls and observed-window bounds","passed":True})
        focused_folder=OUT/"focused_diagnostics"
        focused=json.loads((focused_folder/"status.json").read_text())
        assert focused["complete"] and focused["source_seeds"]==list(range(20))
        examples=pd.read_csv(focused_folder/"hot_year_examples_per_seed.csv")
        assert examples.seed.nunique()==20 and len(examples)==focused["n_example_score_rows"]
        assert examples[["hits","misses","false_alarms","correct_negatives"]].sum(axis=1).eq(examples.n_common).all()
        assert examples.groupby(["seed","illustration","family"]).n_common.nunique().eq(1).all()
        assert examples.n_common.le(examples.n_eligible).all()
        for denominator,rate,numerator in [(examples.hits+examples.misses,"hit_rate",examples.hits),
                                          (examples.false_alarms+examples.correct_negatives,"false_alarm_rate",examples.false_alarms)]:
            np.testing.assert_allclose(examples[rate],numerator/denominator.replace(0,np.nan),atol=1e-12,equal_nan=True)
        no_class=(examples.hits+examples.misses).eq(0)|(examples.false_alarms+examples.correct_negatives).eq(0)
        assert examples.loc[no_class,"sedi"].isna().all()
        station_trends=pd.read_csv(focused_folder/"prespecified_station_trends_per_seed.csv")
        assert len(station_trends)==120 and station_trends.seed.nunique()==20
        qualification=pd.read_csv(focused_folder/"US_year_qualification.csv")
        assert len(qualification)==focused["n_US_source_regions"]
        assert qualification.qualified.sum()==focused["n_US_regions_with_qualified_warm_year"]
        assert qualification.loc[qualification.qualified,"median_air_anomaly"].gt(0).all()
        checks.append({"check":"planned station profiles and twenty-seed common-case named-year event diagnostics","passed":True})
        zero_folder=OUT/"zero_flow_missingness"
        zero_status=json.loads((zero_folder/"status.json").read_text())
        assert zero_status["complete"] and zero_status["bootstrap_draws"]==400
        for name,digest in zero_status["source_sha256"].items():
            assert hashlib.sha256((T.ROOT/name).read_bytes()).hexdigest()==digest,name
        zero_sample=pd.read_parquet(zero_folder/"station_year_sample.parquet")
        assert zero_sample.station_key.nunique()==zero_status["n_USGS_physical_stations"]==336
        assert len(zero_sample)==zero_status["n_USGS_station_year_rows"]==6479
        assert zero_sample.loc[zero_sample.proxy_class.eq("recorded_zero_flow"),"station_key"].nunique()==21
        assert zero_sample.loc[zero_sample.proxy_class.eq("no_approved_flow"),"zero_days"].isna().all()
        zero_summary=pd.read_csv(zero_folder/"conditional_logit_summary.csv")
        np.testing.assert_allclose(zero_summary.odds_ratio,np.exp(zero_summary.log_odds),atol=1e-12)
        for (label,analysis),block in zero_summary.groupby(["proxy_class","analysis"]):
            bootstrap=pd.read_csv(zero_folder/f"bootstrap_{label}_{analysis}.csv")
            assert len(bootstrap)==400
            for row in block.itertuples(index=False):
                values=bootstrap["beta__"+row.covariate].dropna()
                assert len(values)==row.n_bootstrap
                if len(values)>20:
                    np.testing.assert_allclose([row.odds_ratio_lower95,row.odds_ratio_upper95],
                        np.exp(np.quantile(values,[.025,.975])),atol=1e-10)
        checks.append({"check":"C1 zero-flow proxy strata, unknown flow and group-bootstrap odds intervals","passed":True})
        assert (OUT/"meaning/field_significance.csv").exists()
        assert json.loads((OUT/"meaning/summary.json").read_text())["historical_models_only"] is False
        deletion=pd.read_csv(OUT/"robustness/group_deletions_all_seeds.csv")
        assert deletion.seed.nunique()==20 and not deletion.status.eq("optimality_unproven").any()
        historical=pd.read_csv(OUT/"robustness/historical_N1_deletions.csv")
        assert set(historical.population)=={"deploy","mech"}
        assert historical.minimum_groups.eq(10).all()
        formal=json.loads((OUT/"conditional_conformal/design.json").read_text())
        assert formal["implementation_version"]=="group-units-v4-binary-LAC" and len(formal["seeds"])==20
        conditional=pd.read_csv(OUT/"conditional_conformal/rules_all_seeds.csv")
        assert conditional.seed.nunique()==20
        assert conditional.loc[conditional.n_admitted.eq(0),"risk_case_weighted"].isna().all()
        assert {"coarse_overlapping_groups_randomized","held_region_group_randomized"}.issubset(conditional.method.unique())
        ss=json.loads((OUT/"semi_rcps/design.json").read_text())
        assert len(ss["seeds"])==20 and ss["repeats"]==100
        ablation=pd.read_csv(OUT/"probability_ablation/per_seed.csv")
        assert ablation.seed.nunique()==20
        for seed in CONFIG["seeds"]:
            rule=pd.read_csv(OUT/f"analyses/leave_one_year_out/seed_{seed:02d}/rules.csv")
            for method,name in [("raw_classifier","individual_0.1"),("Platt_plus_empirical_groups","individual_group_adjusted")]:
                left=ablation.loc[ablation.seed.eq(seed)&ablation.method.eq(method)].set_index("family")
                right=rule.loc[rule.rule.eq(name)&rule.delivery.eq("distribution_regression")].set_index("family")
                for metric in ["retention","risk","fraction_groups_above_10"]:
                    np.testing.assert_allclose(left[metric].sort_index(),right[metric].sort_index(),equal_nan=True)
        witnesses=pd.read_csv(OUT/"observed_records/observed_record_certificates.csv")
        assert witnesses.station_key.nunique()==20 and len(witnesses)==35
        assert witnesses.n_complete_years.ge(15).all() and witnesses.n_missing_days.gt(0).all()
        for row in witnesses.itertuples():
            values=np.fromstring(row.verified_daily_values,sep=";")
            assert len(values)==30 and np.isfinite(values).all()
            assert abs(values.mean()-row.observed_window_mean)<5e-6
            assert row.observed_window_mean>row.maximum_complete_year_H30+5e-6
            assert (pd.Timestamp(row.observed_window_end)-pd.Timestamp(row.observed_window_start)).days==29
        regional=pd.read_csv(OUT/"regional_rankings/same_roster_same_span_summary.csv")
        assert regional.status.eq("computed").sum()>=3
        planning=pd.read_csv(OUT/"independent_study/sample_size_planning_by_seed.csv")
        assert planning.seed.nunique()==20 and len(planning)==160
        assert planning.simulation_repetitions.eq(2000).all()
        p4=pd.read_csv(OUT/"evidence/P4_analogue_per_seed.csv")
        assert p4.seed.nunique()==20 and len(p4)==60
        assert p4.missing_component_coverage.between(0,1).all()
        assert p4.total_interval_coverage.between(0,1).all()
        checks.append({"check":"group deletion, formal calibration and observed record witnesses","passed":True})
        candidate=json.loads((OUT/"deployment/candidate.json").read_text())
        assert candidate["target_water_temperature_read"] is False
        candidate_roles=[set(x) for x in candidate["roles"].values()]
        for i,role in enumerate(candidate_roles):
            assert all(not role.intersection(other) for other in candidate_roles[:i])
        assert (OUT/"deployment/global_source_candidate.joblib").exists()
        study=OUT/"independent_study"
        plan=json.loads((study/"acquisition_plan.json").read_text())
        assert plan["n_prospective_stations"]==9 and plan["n_conservative_groups"]==3
        assert plan["qc_specification"]["accepted_quality_codes"]==[600]
        assert plan["qc_specification"]["daily_completeness"]==1
        assert hashlib.sha256((study/plan["metadata_roster_file"]).read_bytes()).hexdigest()==plan["metadata_roster_sha256"]
        for name,field in [("source_case_settings.json","source_case_settings_sha256"),("source_missingness_generator.json","source_generator_sha256")]:
            assert hashlib.sha256((study/name).read_bytes()).hexdigest()==plan[field]
        for folder in ["horizons_metadata","greater_wellington"]:
            for path in (study/folder).rglob("*.xml"):
                root=ET.parse(path).getroot()
                assert not any(e.tag.rsplit("}",1)[-1] in {"Data","E","V","Value","MeasurementTimeseries"} for e in root.iter()),path
        if status.get("status")!="public_registration_and_attachments_verified":
            assert not (study/"acquired").exists(),"New-cohort river observations are not yet authorized by public registration"
        assert json.loads((study/"source_interface_smoke.json").read_text())["fixed_model_unchanged"]
        checks.append({"check":"outcome-free metadata roster, native measurement plan and source inference interface","passed":True})
        exposure=json.loads((OUT/"air_exposure/design.json").read_text())
        assert exposure["seeds"]==[0,1,2] and exposure["source_fit_seed"]==0
        release=pd.read_csv(OUT/"air_exposure/release_metrics_all_seeds.csv")
        assert release.seed.nunique()==3 and len(release)==12
        assert release.retention.between(0,1).all() and release.risk.between(0,1).all()
        audit=json.loads((OUT/"air_exposure/paired_case_audit.json").read_text())
        assert all(row["case_mask_and_truth_match"] for row in audit["rows"])
        control=json.loads((OUT/"air_exposure/source_control_parity.json").read_text())
        assert control["matched_scorecard_rows"]==552
        assert all(value==0 for value in control["maximum_absolute_differences"].values())
        checks.append({"check":"paired unflagged exposure and unchanged clean-source scorecard","passed":True})
        observed=json.loads((OUT/"inputs/observed_air_full_source_exact/original_core_control_audit.json").read_text())
        assert observed["exact_source_verified"] and observed["case_rows"]==67316
        assert observed["availability_disagreements"]==0 and observed["maximum_point_difference"]==0
        lag=json.loads((OUT/"inputs/calendar_lag_correction_audit.json").read_text())
        assert lag["POWER_controls_equal"] and all(n==6239 for n in lag["new_rows_per_arm"].values())
        checks.append({"check":"nearby observed-air original-input controls and calendar-day driver lags","passed":True})
        full_forcing=OUT/"inputs/forcing_full_source_exact"
        if (full_forcing/"analysis_summary.json").exists():
            forcing_audit=json.loads((full_forcing/"original_core_control_audit.json").read_text())
            assert forcing_audit["exact_source_verified"] and forcing_audit["case_rows"]==67316
            assert forcing_audit["availability_disagreements"]==0 and forcing_audit["maximum_point_difference"]==0
            forcing=pd.read_parquet(full_forcing/"cases.parquet",columns=["arm","available","point","error"])
            assert forcing.groupby("arm").size().eq(67316).all() and len(forcing)==201948
            assert forcing.loc[~forcing.available,["point","error"]].isna().all().all()
            checks.append({"check":"full-source USGS forcing exact controls and unavailable-case denominators","passed":True})
        from wrr_review_forcing_reporting import europe_evidence
        european=europe_evidence(OUT)
        if european["full_source"]:
            folder=european["folder"]
            cases=pd.read_parquet(folder/"cases.parquet")
            keys=["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice"]
            assert not cases.duplicated(keys+["arm"]).any()
            expected=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet",columns=keys+["provider","h30__air_ridge"])
            expected=expected.loc[expected.provider.ne("usgs")&expected.year.between(1981,2025)]
            control=cases.loc[cases.arm.eq("POWER")].merge(expected,on=keys,validate="one_to_one")
            assert len(control)==len(expected) and cases.groupby("arm").size().eq(len(expected)).all()
            assert (control.point.notna()==control.h30__air_ridge.notna()).all()
            np.testing.assert_allclose(control.point,control.h30__air_ridge,rtol=1e-11,atol=1e-11,equal_nan=True)
            assert cases.loc[~cases.available,["point","error"]].isna().all().all()
            assert np.isfinite(cases.loc[cases.available,["point","error"]]).all().all()
            checks.append({"check":"full European source roster, exact POWER predictions and both arm denominators","passed":True})
        for region in ["usgs","europe"]:
            folder=OUT/"inputs/forcing_recovery"/region
            if not (folder/"status.json").exists() or json.loads((folder/"status.json").read_text()).get("partial",True):continue
            modeled=pd.read_parquet(folder/"cases.parquet")
            reference=pd.read_parquet(OUT/("inputs/forcing_full_source_exact/cases.parquet" if region=="usgs" else "europe_full_source_exact/cases.parquet"))
            if region=="usgs":
                extra=pd.read_parquet(OUT/"inputs/observed_air_full_source_exact/cases.parquet")
                reference=pd.concat([reference,extra.loc[extra.arm.eq("observed_TAVG")]],ignore_index=True)
            keys=["network_id","station_key","year","design_family","realization_id","peak_overlap","policy_choice","arm"]
            compared=modeled.merge(reference[keys+["point","error"]],on=keys,suffixes=("","_reference"),validate="one_to_one")
            assert len(compared)==len(modeled)==len(reference)
            for name in ["point","error"]:
                np.testing.assert_allclose(compared[name],compared[name+"_reference"],rtol=1e-9,atol=1e-9,equal_nan=True)
            assert modeled.loc[~modeled.point_available,"recovery_probability"].isna().all()
            probability=modeled.recovery_probability.dropna();assert probability.between(-1e-12,1+1e-12).all()
            audit=json.loads((folder/"numerical_audit.json").read_text())
            assert audit["passed"] and audit["residual_target_year_excluded"]
            assert all(v["maximum_prediction_difference"]<=1e-7 for v in audit["independent_sklearn_OOF_checks"])
            checks.append({"check":f"{region} driver-specific recovery residual exclusion, point controls and probability support","passed":True})
        coordinate_audit=OUT/"inputs/source_coordinate_supplement_audit.json"
        if coordinate_audit.exists():
            coordinate=json.loads(coordinate_audit.read_text())
            assert coordinate["passed"] and coordinate["n_source_stations"]==9
            assert coordinate["maximum_catalog_coordinate_difference"]<=1e-9
            mapping=json.loads((OUT/"failure_map/status.json").read_text())
            assert mapping["n_stations"]==581 and mapping["n_with_coordinates"]==581
            checks.append({"check":"exact official French station coordinates and complete source-map coverage","passed":True})
        outlet_path=OUT/"inputs/lake_outlet_metadata/verified_designations.json"
        if outlet_path.exists():
            designations=json.loads(outlet_path.read_text())
            assert designations["n_verified"]==1
            for row in designations["records"]:
                page=OUT/"inputs/lake_outlet_metadata"/("USGS-"+row["station_id"]+".html")
                assert hashlib.sha256(page.read_bytes()).hexdigest()==row["official_page_sha256"]
                assert "AT OUTLET OF CLEAR LAKE" in page.read_text().upper()
            failures=pd.read_csv(OUT/"failure_map/station_failures_and_metadata.csv")
            positives=set(failures.loc[failures.lake_outlet_status.eq("agency_designated_lake_outlet"),"station_key"])
            assert positives=={row["station_key"] for row in designations["records"]}
            assert failures.loc[~failures.station_key.isin(positives),"lake_outlet_status"].eq("not independently established").all()
            checks.append({"check":"explicit agency lake-outlet designation without inferred negative river classes","passed":True})
        h7=OUT/"target_windows/h7/full"
        if (h7/"completion.json").exists():
            window=json.loads((h7/"completion.json").read_text())
            assert window["complete"] and window["seeds"]==list(range(20)) and window["outer_fits"]==540
            assert json.loads((h7/"daily_input_audit.json").read_text())["passed"]
            identities=json.loads((h7/"outer_prediction_identity_audit.json").read_text())
            assert identities["passed"] and len(identities["rows"])==20
            assert all(row["native_target_and_point_match"] for row in identities["rows"])
            assert json.loads((OUT/"target_windows/h30_default_parity.json").read_text())["passed"]
            checks.append({"check":"native H7 targets,540 disjoint outer fits and unchanged default H30","passed":True})
        inventory=json.loads((OUT/"independent_study/bundle_inventory.json").read_text())
        bundle=OUT/"independent_study/registration_code_and_protocol.tar.gz"
        assert inventory["all_final_models_included"]
        with bundle.open("rb") as stream:
            assert sha256_stream(stream)==inventory["sha256"]
        # Check the archive itself, not today's mutable working tree. Public
        # registration must preserve these exact bytes even after later edits.
        with tarfile.open(bundle) as archive:
            manifest_name=str((OUT/"independent_study/file_sha256.json").relative_to(T.ROOT))
            manifest=json.load(archive.extractfile(manifest_name))
            for name,digest in manifest.items():
                with archive.extractfile(name) as stream:
                    assert sha256_stream(stream)==digest,name
        checks.append({"check":"draft bundle checksums and frozen source candidate","passed":True})
        execution=json.loads((OUT/"evidence/archive_execution_smoke.json").read_text())
        assert execution["passed"] and execution["returncode"]==0 and execution["archive_sha256"]==inventory["sha256"]
        assert execution["network_disabled"] and not execution["working_tree_code_imported"]
        assert execution["source_feature_cases"]>0 and execution["synthetic_generated_cases"]>0 and execution["synthetic_numeric_columns_compared"]>0
        checks.append({"check":"isolated registered-archive inference and synthetic generator parity without network","passed":True})
    national_path=OUT/"national_availability/summary.json"
    national=json.loads(national_path.read_text()) if national_path.exists() else {}
    national_complete=bool(national.get("all_metadata_possible_sites_resolved",False))
    national_h30_path=OUT/"national_meaning/status.json"
    national_h30_complete=bool(national_h30_path.exists() and json.loads(national_h30_path.read_text()).get("complete"))
    from wrr_review_national_reporting import national_evidence
    national_panel=national_evidence(OUT)
    if national_panel is not None:
        checks.append({"check":"national retrieved-panel artifacts and unresolved-eligibility bounds","passed":True})
    core_complete=not a.partial and len(seen)==20
    window_path=OUT/"target_windows/h7/full/completion.json"
    window_complete=bool(window_path.exists() and json.loads(window_path.read_text()).get("complete"))
    forcing_path=OUT/"inputs/forcing_full_source_exact/analysis_summary.json"
    forcing_complete=bool(forcing_path.exists() and not json.loads(forcing_path.read_text()).get("partial",True))
    from wrr_review_forcing_reporting import europe_evidence
    europe_complete=bool(europe_evidence(OUT)["full_source"])
    recovery_complete={region:bool((OUT/f"inputs/forcing_recovery/{region}/status.json").exists() and not json.loads((OUT/f"inputs/forcing_recovery/{region}/status.json").read_text()).get("partial",True)) for region in ["usgs","europe"]}
    extensions_complete=core_complete and window_complete and forcing_complete and europe_complete and all(recovery_complete.values())
    report={"checks":checks,"completed_seed_analyses":seen,"source_core_complete":core_complete,
        "source_core_and_local_extensions_complete":extensions_complete,"full_H7_target_refits_complete":window_complete,
        "full_USGS_forcing_complete":forcing_complete,"full_Europe_available_coordinate_forcing_complete":europe_complete,
        "driver_recovery_models_complete":recovery_complete,
        "national_availability_complete":national_complete,"national_h30_analysis_complete":national_h30_complete,
        "national_retrieved_panel_execution_complete":national_panel is not None,
        "local_evidence_complete":extensions_complete and national_h30_complete,"independent_transfer_completed":False,
        "qualified_natural_gap_accuracy_completed":False,"overall_user_goal_complete":False}
    T.write_json(OUT/"evidence/validation.json",report)
    print(json.dumps(report,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())

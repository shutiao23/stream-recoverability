"""W7 T2 weasel tests. Production code and manifests are imported read-only.

A flag-only "T2 done" PR must fail these tests. Scratch pack does not edit
production files, download the USGS 98-list, open sealed/Loire/Swiss
temperatures, retarget design_freeze_v4, or retune Twin E / φ.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

W7 = Path(__file__).resolve().parent
REPO = W7.parents[2]
SRC = REPO / "src"
if str(W7) not in sys.path:
    sys.path.insert(0, str(W7))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.analysis.hierarchical_confirmation import (  # noqa: E402
    evaluate_success,
    simulate_confirmation_panel,
)
from stream_recoverability.experiments.contracts import (  # noqa: E402
    DEFAULT_DESIGN_PATH,
    EXECUTABLE_DESIGN_VERSION,
    SUPPORTED_EXECUTABLE_DESIGN_VERSIONS,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (  # noqa: E402
    BASE_INFORMATION_CONDITIONS,
    EXTENDED_INFORMATION_CONDITIONS,
)
from w7_contract import (  # noqa: E402
    CODE4_LIVE_SITES,
    GO_NO_GO,
    INCREMENTAL_R2_W8_FLOOR,
    INFERENCE_WITHHELD,
    MH_BLOCKED,
    MIN_CONCURRENT_DAYS,
    MIN_STATIONS,
    NA_OPEN_6YR_DEVELOPMENT,
    NA_OPEN_6YR_FAILURE_CLOSURE,
    NA_OPEN_6YR_VALIDATION,
    NA_OPEN_8YR,
    NA_OPEN_8YR_DEVELOPMENT,
    NA_OPEN_8YR_VALIDATION,
    NEVER_SEALED_TOKENS,
    N_EXECUTABLE_BD,
    N_MH_AUXILIARY_EXPECTED,
    N_MH_AUXILIARY_TERMINAL,
    N_MH_STRUCTURAL_NOT_APPLICABLE,
    N_NETWORKS_MIN_T2,
    OVERLAPPING_DAILY_YEARS_MIN,
    REQUIRED_MANIFEST_KEYS,
    SANDRE_CORRECTE,
    SANDRE_NON_QUALIFIE,
    SEALED_HUC8_PAD_EXAMPLE,
    UK_EA_BEST_OVERLAP_CONCURRENT_DAYS,
    UK_EA_BEST_OVERLAP_NETWORK,
    UK_EA_BEST_OVERLAP_N_STATIONS,
    UK_EA_BEST_OVERLAP_YEARS,
    UK_EA_HYDROMETRIC_CLUSTERS_50KM,
    UK_EA_N_COMPLETE_ENOUGH,
    UK_EA_SPATIAL_CATALOG_CLUSTERS_50KM,
    W7_FIRST_LAYER,
    WORKLOAD_SHA256,
    assert_w7_not_t2_contract,
    europe_does_not_increment_t2,
    executable_count_after_mh_relabel,
    flag_only_w7_t2_done_holes,
    mh_cell_is_blocked,
    n_cannot_reach_floor_by_padding,
    naive_relabel_code4_as_correcte,
    naive_relabel_mh_as_executable,
    network_ci_status,
    operator_or_phi_retune_licensed,
    sandre_code_is_t8_eligible,
    t2_confirmatory_eligible,
    t8_countable,
    w7_information_is_first_layer,
    w8_failure_closure_action,
)

CONTRACT = W7 / "manifest_contract.json"
FLAG_ONLY = W7 / "demo" / "flag_only_t2_done.json"
WORKLOAD = REPO / "results/framework/t2_recovery_benchmark_v1/workload_manifest.json"
GEOMETRY = REPO / "results/framework/t2_outage_geometry_v1/geometry_binding_manifest.json"
V4_READY = REPO / "results/framework/t2_recovery_benchmark_v4/readiness_manifest.json"
W6_MANIFEST = REPO / "results/framework/public_catalog/w6_europe_source_audit_manifest.json"
HUBEAU_SITES = REPO / "results/framework/public_catalog/w6_hubeau_correct_station_audit.csv"
UK_HYDRO = (
    REPO / "results/framework/public_rivers_europe/uk_ea_hydrometric_spatial_daily_manifest.json"
)
UK_OVERLAP = (
    REPO / "results/framework/public_rivers_europe/uk_ea_hydrometric_spatial_overlap.csv"
)
FOEN_AUDIT = REPO / "results/framework/public_catalog/w6_foen_public_api_audit.json"
FREEZE_V9 = REPO / "configs/design_freeze_v9.yaml"
SPLIT = REPO / "configs/network_catalog_v3_split.yaml"
QC_DEV = (
    REPO
    / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6/development/qc_manifest.json"
)
QC_VAL = (
    REPO
    / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6/validation/qc_manifest.json"
)
W7_SLICE = REPO / "results/framework/t2_recovery_benchmark_v1/w7_open_role_bd_slice"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _production_evidence(*, evaluate_live_passed: bool = False) -> dict:
    w6 = json.loads(W6_MANIFEST.read_text(encoding="utf-8"))
    uk = json.loads(UK_HYDRO.read_text(encoding="utf-8"))
    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    v4 = json.loads(V4_READY.read_text(encoding="utf-8"))
    return {
        "n_open": int(workload.get("n_networks") or 0),
        "n_europe_complete_enough": int(w6.get("n_europe_complete_enough_added") or 0),
        "hubeau_n_sites_with_sandre_correcte_observations": int(
            w6.get("hubeau_n_sites_with_sandre_correcte_observations") or 0
        ),
        "uk_ea_n_complete_enough": int(uk.get("n_complete_enough") or 0),
        "evaluate_success_live_passed": evaluate_live_passed,
        "meteorology_M": bool((workload.get("dependency_audit") or {}).get("meteorology_M")),
        "hydraulics_H": bool((workload.get("dependency_audit") or {}).get("hydraulics_H")),
        "n_mh_auxiliary_terminal": int(
            (v4.get("auxiliary") or {}).get("n_networks_terminal") or 0
        ),
    }


def _live_evaluate_success(n_networks: int) -> dict:
    return evaluate_success(simulate_confirmation_panel(n_networks=n_networks, seed=7))


def test_manifest_contract_required_keys() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for key in REQUIRED_MANIFEST_KEYS:
        assert key in contract
    assert contract["passed"] is False
    assert contract["n_networks"] == NA_OPEN_6YR_FAILURE_CLOSURE
    assert contract["n_networks_8yr"] == NA_OPEN_8YR
    assert contract["n_networks_min_t2"] == N_NETWORKS_MIN_T2
    assert contract["go_no_go"] == GO_NO_GO
    assert contract["confirmatory_eligible"] is False
    assert contract["evaluate_success"]["passed"] is False
    assert contract["evaluate_success"]["n_networks_min"] == N_NETWORKS_MIN_T2
    assert contract["network_interval"]["inference_status"] == INFERENCE_WITHHELD
    assert contract["europe_complete_enough_used"] is False
    assert contract["hubeau_correcte_t8_usable"] is False
    assert contract["sealed_outcomes_opened"] is False
    assert contract["mh_blocked_cells_relabeled_executable"] is False
    assert contract["operator_retuned_because_incremental_r2_lt_005"] is False
    assert_w7_not_t2_contract(contract)


def test_flag_only_t2_done_pr_is_rejected() -> None:
    lying = json.loads(FLAG_ONLY.read_text(encoding="utf-8"))
    live = _live_evaluate_success(NA_OPEN_6YR_FAILURE_CLOSURE)
    assert live["passed"] is False
    evidence = _production_evidence(evaluate_live_passed=bool(live["passed"]))
    holes = flag_only_w7_t2_done_holes(lying, evidence)
    assert "n_lt_100_sold_as_confirmatory_t2" in holes
    assert "network_ci_tested_at_n_lt_100" in holes
    assert "n_padded_above_open_role_stock" in holes
    assert "europe_catalog_or_5_91_counted_as_t8_or_t2" in holes
    assert "hubeau_code4_counted_as_correcte_t8" in holes
    assert "passed_true_while_evaluate_success_fails" in holes
    assert "sealed_huc8_foen_loire_opened_to_pad_n" in holes
    assert "mh_blocked_relabeled_executable" in holes
    assert "operator_or_phi_retuned_for_incremental_r2" in holes
    assert "w8_failure_closure_was_retune_not_retitle" in holes
    with pytest.raises(AssertionError, match="passed|tested|evaluate_success"):
        assert_w7_not_t2_contract(lying)


def test_passed_true_while_evaluate_success_still_fails() -> None:
    live = _live_evaluate_success(NA_OPEN_6YR_FAILURE_CLOSURE)
    assert live["passed"] is False
    assert live["confirmatory_eligible"] is False
    assert live["n_networks_min"] == N_NETWORKS_MIN_T2
    spearman = live["spearman"]
    assert spearman["inference_status"] == INFERENCE_WITHHELD
    flag_only = {
        "passed": True,
        "n_networks": NA_OPEN_6YR_FAILURE_CLOSURE,
        "purpose": "development_slice_not_evidence",
        "formal_evidence": False,
        "confirmatory_eligible": False,
        "go_no_go": GO_NO_GO,
        "evaluate_success": {
            "passed": False,
            "n_networks_min": N_NETWORKS_MIN_T2,
            "spearman_inference_status": INFERENCE_WITHHELD,
        },
        "network_interval": {"inference_status": INFERENCE_WITHHELD},
        "sealed_outcomes_opened": False,
        "europe_complete_enough_used": False,
        "mh_blocked_cells_relabeled_executable": False,
        "operator_retuned_because_incremental_r2_lt_005": False,
    }
    holes = flag_only_w7_t2_done_holes(
        flag_only, _production_evidence(evaluate_live_passed=False)
    )
    assert "passed_true_while_evaluate_success_fails" in holes
    with pytest.raises(AssertionError, match="passed"):
        assert_w7_not_t2_contract(flag_only)


def test_n_67_and_n_59_cannot_be_confirmatory_t2() -> None:
    for n in (NA_OPEN_8YR, NA_OPEN_6YR_FAILURE_CLOSURE, N_NETWORKS_MIN_T2 - 1):
        assert t2_confirmatory_eligible(n) is False
        assert network_ci_status(n) == INFERENCE_WITHHELD
        live = _live_evaluate_success(n)
        assert live["passed"] is False
        assert live["confirmatory_eligible"] is False
        assert live["spearman"]["inference_status"] != "tested"
    qc = json.loads(QC_DEV.read_text(encoding="utf-8"))
    val = json.loads(QC_VAL.read_text(encoding="utf-8"))
    assert qc["primary_8yr_counts"]["open_complete_enough_total"] == NA_OPEN_8YR
    assert qc["primary_8yr_counts"]["by_role"]["development"]["complete_enough"] == (
        NA_OPEN_8YR_DEVELOPMENT
    )
    assert qc["primary_8yr_counts"]["by_role"]["validation"]["complete_enough"] == (
        NA_OPEN_8YR_VALIDATION
    )
    assert int(qc["n_networks_complete_enough"]) == NA_OPEN_6YR_DEVELOPMENT
    assert int(val["n_networks_complete_enough"]) == NA_OPEN_6YR_VALIDATION
    assert (
        int(qc["n_networks_complete_enough"]) + int(val["n_networks_complete_enough"])
        == NA_OPEN_6YR_FAILURE_CLOSURE
    )
    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    assert workload["n_networks"] == NA_OPEN_6YR_FAILURE_CLOSURE
    assert workload["roles"]["development"] == NA_OPEN_6YR_DEVELOPMENT
    assert workload["roles"]["validation"] == NA_OPEN_6YR_VALIDATION
    assert workload["go_no_go"] == GO_NO_GO
    assert workload["network_inference_status"] == INFERENCE_WITHHELD
    assert _sha256(WORKLOAD) == WORKLOAD_SHA256


def test_tested_ci_at_n_lt_100_fails_contract() -> None:
    base = json.loads(CONTRACT.read_text(encoding="utf-8"))
    tested = dict(base)
    tested["network_interval"] = dict(base["network_interval"])
    tested["network_interval"]["inference_status"] = "tested"
    with pytest.raises(AssertionError, match="tested"):
        assert_w7_not_t2_contract(tested)
    sold = dict(base)
    sold["passed"] = True
    with pytest.raises(AssertionError, match="passed"):
        assert_w7_not_t2_contract(sold)
    freeze = yaml.safe_load(FREEZE_V9.read_text(encoding="utf-8"))
    inference = freeze["locked_success_criterion"]["inference"]
    t2 = freeze["locked_success_criterion"]["t2_large_sample_primary"]
    assert inference["n_networks_min"] == N_NETWORKS_MIN_T2
    assert t2["withhold_network_ci_if_n_lt_100"] is True


def test_europe_catalog_clusters_and_5_91_overlap_are_not_t8_or_t2() -> None:
    uk = json.loads(UK_HYDRO.read_text(encoding="utf-8"))
    assert uk["n_complete_enough"] == UK_EA_N_COMPLETE_ENOUGH
    assert uk["n_spatial_clusters_3plus_50km"] == UK_EA_SPATIAL_CATALOG_CLUSTERS_50KM
    assert (
        uk["n_hydrometric_spatial_clusters_3plus_50km"]
        == UK_EA_HYDROMETRIC_CLUSTERS_50KM
    )
    assert uk["countable_toward_t8"] is False
    overlap = pd.read_csv(UK_OVERLAP)
    best = overlap.loc[overlap["network_id"].astype(str).eq(UK_EA_BEST_OVERLAP_NETWORK)]
    assert not best.empty
    years = float(best["overlap_years"].iloc[0])
    assert years == pytest.approx(UK_EA_BEST_OVERLAP_YEARS, abs=1e-6)
    assert years == pytest.approx(5.91, abs=0.01)
    assert years < OVERLAPPING_DAILY_YEARS_MIN
    assert int(best["n_stations"].iloc[0]) == UK_EA_BEST_OVERLAP_N_STATIONS
    assert int(best["days_with_min_stations"].iloc[0]) == UK_EA_BEST_OVERLAP_CONCURRENT_DAYS
    assert bool(best["complete_enough"].iloc[0]) is False
    assert bool(best["countable_toward_t8"].iloc[0]) is False
    assert int(best["days_with_min_stations"].iloc[0]) >= MIN_CONCURRENT_DAYS
    assert (
        t8_countable(
            n_stations=UK_EA_BEST_OVERLAP_N_STATIONS,
            overlapping_daily_years=years,
            days_with_min_stations=UK_EA_BEST_OVERLAP_CONCURRENT_DAYS,
            quality_ok=True,
        )
        is False
    )
    assert (
        t8_countable(
            n_stations=3,
            overlapping_daily_years=8.0,
            days_with_min_stations=MIN_CONCURRENT_DAYS,
            quality_ok=True,
            catalog_cluster_only=True,
        )
        is False
    )
    padded = europe_does_not_increment_t2(
        n_catalog_clusters=UK_EA_SPATIAL_CATALOG_CLUSTERS_50KM,
        overlap_years=years,
        n_europe_complete_enough=0,
    )
    assert padded["t8_or_t2_n_increment"] == 0
    assert padded["n_after"] == NA_OPEN_6YR_FAILURE_CLOSURE
    assert padded["t2_passed"] is False
    assert padded["n_after"] < N_NETWORKS_MIN_T2
    w6 = json.loads(W6_MANIFEST.read_text(encoding="utf-8"))
    assert w6["n_europe_complete_enough_added"] == 0
    assert w6["countable_toward_t8"] is False


def test_hubeau_code4_is_not_correcte_or_t8() -> None:
    sites = pd.read_csv(HUBEAU_SITES, dtype={"site_id": str})
    positive = (
        pd.to_numeric(sites["n_correct_instantaneous"], errors="coerce").fillna(0).gt(0).sum()
    )
    assert int(positive) == 0
    for site_id in CODE4_LIVE_SITES:
        row = sites.loc[sites["site_id"].astype(str).eq(site_id)]
        assert not row.empty, site_id
        assert int(row["n_correct_instantaneous"].iloc[0] or 0) == 0
        assert str(row["quality_code_required"].iloc[0]) == SANDRE_CORRECTE
    assert sandre_code_is_t8_eligible(SANDRE_NON_QUALIFIE) is False
    assert sandre_code_is_t8_eligible(SANDRE_CORRECTE) is True
    assert naive_relabel_code4_as_correcte(SANDRE_NON_QUALIFIE) == SANDRE_CORRECTE
    assert (
        t8_countable(
            n_stations=MIN_STATIONS,
            overlapping_daily_years=8.0,
            days_with_min_stations=MIN_CONCURRENT_DAYS,
            quality_ok=True,
            code_qualification=SANDRE_NON_QUALIFIE,
        )
        is False
    )
    w6 = json.loads(W6_MANIFEST.read_text(encoding="utf-8"))
    assert w6["hubeau_n_sites_with_sandre_correcte_observations"] == 0
    assert w6["hubeau_unqualified_code_4_accepted"] is False
    usable = json.loads(CONTRACT.read_text(encoding="utf-8"))
    usable["hubeau_correcte_t8_usable"] = True
    with pytest.raises(AssertionError, match="hubeau_correcte"):
        assert_w7_not_t2_contract(usable)


def test_sealed_huc8_foen_loire_cannot_pad_n() -> None:
    freeze = yaml.safe_load(FREEZE_V9.read_text(encoding="utf-8"))
    assert freeze["split_rule"]["loire_swiss_still_not_countable_for_t8"] is True
    assert freeze["clustering_rule"]["do_not_download_name_huc2_98_list"] is True
    never = tuple(freeze["split_rule"]["never_sealed_networks"])
    assert never == NEVER_SEALED_TOKENS
    assert len(never) == 14
    catalog = yaml.safe_load(SPLIT.read_text(encoding="utf-8"))
    sealed_ids = {
        str(row["network_id"])
        for row in catalog["networks"]
        if str(row.get("role")) == "sealed"
    }
    assert SEALED_HUC8_PAD_EXAMPLE in sealed_ids
    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    open_ids = set(workload["network_ids"])
    assert SEALED_HUC8_PAD_EXAMPLE not in open_ids
    assert open_ids.isdisjoint(sealed_ids)
    assert open_ids.isdisjoint(set(NEVER_SEALED_TOKENS))
    assert "suwannee_river_huc31" not in open_ids
    assert workload["sealed_temperature_records_read"] is False
    assert workload["sealed_input_roots_allowed"] == []
    foen = json.loads(FOEN_AUDIT.read_text(encoding="utf-8"))
    assert foen["public_graphql_reachable"] is True
    assert foen["temperature_values_requested"] is False
    assert foen["swiss_countable_toward_t8"] is False
    w6 = json.loads(W6_MANIFEST.read_text(encoding="utf-8"))
    assert w6["loire_downloaded"] is False
    assert w6["swiss_countable_toward_t8"] is False
    padded = n_cannot_reach_floor_by_padding(
        sealed_huc8=40,
        loire=1,
        swiss=1,
        europe_clusters=UK_EA_SPATIAL_CATALOG_CLUSTERS_50KM,
        uk_ea_overlap_years=UK_EA_BEST_OVERLAP_YEARS,
        code4_sites=4,
    )
    assert padded["padding_increment"] == 0
    assert padded["n_honest"] == NA_OPEN_6YR_FAILURE_CLOSURE
    assert padded["clears_floor"] is False
    assert (
        t8_countable(
            n_stations=3,
            overlapping_daily_years=8.0,
            days_with_min_stations=MIN_CONCURRENT_DAYS,
            quality_ok=True,
            sealed_huc8=True,
        )
        is False
    )
    assert (
        t8_countable(
            n_stations=3,
            overlapping_daily_years=8.0,
            days_with_min_stations=MIN_CONCURRENT_DAYS,
            quality_ok=True,
            loire=True,
        )
        is False
    )
    assert (
        t8_countable(
            n_stations=3,
            overlapping_daily_years=8.0,
            days_with_min_stations=MIN_CONCURRENT_DAYS,
            quality_ok=True,
            swiss=True,
            foen_values=True,
        )
        is False
    )
    opened = json.loads(CONTRACT.read_text(encoding="utf-8"))
    opened["sealed_outcomes_opened"] = True
    with pytest.raises(AssertionError, match="sealed"):
        assert_w7_not_t2_contract(opened)


def test_mh_blocked_cells_cannot_be_relabeled_executable() -> None:
    assert BASE_INFORMATION_CONDITIONS == W7_FIRST_LAYER
    assert EXTENDED_INFORMATION_CONDITIONS == MH_BLOCKED
    for condition in W7_FIRST_LAYER:
        assert w7_information_is_first_layer(condition) is True
        assert mh_cell_is_blocked(condition) is False
    for condition in MH_BLOCKED:
        assert w7_information_is_first_layer(condition) is False
        assert mh_cell_is_blocked(condition) is True
        assert (
            naive_relabel_mh_as_executable("structural_not_applicable", condition)
            == "executable"
        )
    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    tier = workload["tier_1"]
    assert tier["n_executable"] == N_EXECUTABLE_BD
    assert (
        tier["reason_counts"][
            "structural_not_applicable|structural_unimplemented_no_meteorology_or_hydraulics_adapter"
        ]
        == N_MH_STRUCTURAL_NOT_APPLICABLE
    )
    assert workload["dependency_audit"]["meteorology_M"] is False
    assert workload["dependency_audit"]["hydraulics_H"] is False
    semantics = tier["information_semantics"]
    assert semantics["B_union_D_union_M"] == "blocked_until_meteorology_M_is_bound"
    assert semantics["B_union_D_union_M_union_H"] == "blocked_until_M_and_hydraulics_H_are_bound"
    contract_map = tier["model_information_contract"]
    assert (
        contract_map["donor_regression|B_union_D_union_M"]["workload_category"]
        == "structural_not_applicable"
    )
    assert (
        contract_map["xgboost|B_union_D_union_M_union_H"]["workload_category"]
        == "structural_not_applicable"
    )
    geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    blocked = set(geometry["blocked_cells"])
    assert "meteorology_M_information_cells_unbound" in blocked
    assert "hydraulics_H_information_cells_unbound" in blocked
    v4 = json.loads(V4_READY.read_text(encoding="utf-8"))
    assert v4["auxiliary"]["n_networks_terminal"] == N_MH_AUXILIARY_TERMINAL
    assert v4["auxiliary"]["n_networks_expected"] == N_MH_AUXILIARY_EXPECTED
    assert v4["network_inference_status"] == INFERENCE_WITHHELD
    inflated = executable_count_after_mh_relabel(relabel=True)
    honest = executable_count_after_mh_relabel(relabel=False)
    assert honest == N_EXECUTABLE_BD
    assert inflated == N_EXECUTABLE_BD + N_MH_STRUCTURAL_NOT_APPLICABLE
    relabeled = json.loads(CONTRACT.read_text(encoding="utf-8"))
    relabeled["mh_blocked_cells_relabeled_executable"] = True
    relabeled["n_executable"] = inflated
    with pytest.raises(AssertionError, match="M/H"):
        assert_w7_not_t2_contract(relabeled)
    holes = flag_only_w7_t2_done_holes(
        relabeled, _production_evidence(evaluate_live_passed=False)
    )
    assert "mh_blocked_relabeled_executable" in holes


def test_incremental_r2_below_0_05_is_w8_retitle_not_retune() -> None:
    assert w8_failure_closure_action(0.02) == "retitle_to_predictability"
    assert w8_failure_closure_action(0.049) == "retitle_to_predictability"
    assert w8_failure_closure_action(INCREMENTAL_R2_W8_FLOOR) == (
        "keep_operator_title_still_not_t2"
    )
    assert operator_or_phi_retune_licensed(0.02) is False
    assert operator_or_phi_retune_licensed(0.20) is False
    freeze = yaml.safe_load(FREEZE_V9.read_text(encoding="utf-8"))
    assert "retitle to predictability" in freeze["failure_closure"]
    assert "do not retune" in freeze["failure_closure"]
    twin = freeze["t5_confound_control"]["synthetic_twin_design"]
    assert twin["do_not_retune_phi_or_isolation_to_save_gate"] is True
    retuned = json.loads(CONTRACT.read_text(encoding="utf-8"))
    retuned["operator_retuned_because_incremental_r2_lt_005"] = True
    retuned["incremental_r2_vs_donor_r2"] = 0.02
    retuned["w8_failure_closure_action"] = "retune_operator_and_phi"
    with pytest.raises(AssertionError, match="retitle|retune"):
        assert_w7_not_t2_contract(retuned)
    twin_flag = dict(retuned)
    twin_flag["operator_retuned_because_incremental_r2_lt_005"] = False
    twin_flag["twin_e_retuned"] = True
    with pytest.raises(AssertionError, match="Twin E"):
        assert_w7_not_t2_contract(twin_flag)


def test_design_freeze_v4_was_not_retargeted() -> None:
    assert EXECUTABLE_DESIGN_VERSION == "design_freeze_v4"
    assert DEFAULT_DESIGN_PATH == Path("configs/design_freeze_v4.yaml")
    assert "design_freeze_v9" not in SUPPORTED_EXECUTABLE_DESIGN_VERSIONS
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["design_freeze_v4_retargeted"] is False
    assert contract["catalog_98_name_huc2_downloaded"] is False
    assert contract["twin_e_retuned"] is False
    freeze = yaml.safe_load(FREEZE_V9.read_text(encoding="utf-8"))
    assert freeze["historical_case_study_freeze"] == "design_freeze_v4"
    assert freeze["not_an_executable_design"] is True
    assert freeze["sealed_outcomes_opened"] is False


def test_honest_production_workload_is_not_a_t2_pass() -> None:
    workload = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    holes = flag_only_w7_t2_done_holes(
        workload, _production_evidence(evaluate_live_passed=False)
    )
    assert "n_lt_100_sold_as_confirmatory_t2" not in holes
    assert "network_ci_tested_at_n_lt_100" not in holes
    assert "passed_true_while_evaluate_success_fails" not in holes
    assert_w7_not_t2_contract(workload, require_keys=False)
    patched = dict(workload)
    patched["passed"] = True
    patched["inference_status"] = "tested"
    with pytest.raises(AssertionError, match="passed|tested"):
        assert_w7_not_t2_contract(patched, require_keys=False)


def test_production_w7_slice_if_present_cannot_claim_t2() -> None:
    if not W7_SLICE.exists():
        return
    manifests = list(W7_SLICE.rglob("*manifest*.json"))
    assert manifests, "W7 slice directory exists but has no manifest"
    live = _live_evaluate_success(NA_OPEN_6YR_FAILURE_CLOSURE)
    evidence = _production_evidence(evaluate_live_passed=bool(live["passed"]))
    for path in manifests:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        holes = flag_only_w7_t2_done_holes(payload, evidence)
        assert "passed_true_while_evaluate_success_fails" not in holes, path
        assert "network_ci_tested_at_n_lt_100" not in holes, path
        assert "n_lt_100_sold_as_confirmatory_t2" not in holes, path
        assert payload.get("passed") is not True, path
        status = str(
            (payload.get("network_interval") or {}).get("inference_status")
            or payload.get("network_inference_status")
            or payload.get("inference_status")
            or INFERENCE_WITHHELD
        )
        assert status != "tested", path
        n_networks = int(payload.get("n_networks") or 0)
        if n_networks:
            assert n_networks <= NA_OPEN_6YR_FAILURE_CLOSURE
            assert n_networks < N_NETWORKS_MIN_T2
        assert_w7_not_t2_contract(payload, require_keys=False)

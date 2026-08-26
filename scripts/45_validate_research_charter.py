#!/usr/bin/env python3
"""Fail closed if the next-paper charter, freeze, or catalog drift."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.analysis.study_freeze import (
    load_study_freeze,
    study_is_confirmatory,
)
from stream_recoverability.data.network_catalog import (
    load_network_catalog,
    validate_catalog,
)
from stream_recoverability.experiments.contracts import (
    DEFAULT_DESIGN_PATH,
    EXECUTABLE_DESIGN_VERSION,
)


def main() -> None:
    charter = (ROOT / "docs/research_charter_v1.md").read_text(encoding="utf-8")
    for marker in (
        "人话",
        "到底要算什么",
        "怎样算过关",
        "怎样算失败",
        "现在做到哪",
    ):
        assert marker in charter, marker
    protocol_v9 = ROOT / "docs/protocol_change_v8_to_v9.md"
    assert protocol_v9.is_file(), (
        "v9 freeze requires docs/protocol_change_v8_to_v9.md; "
        "refusing to invent a protocol here"
    )
    protocol_v91 = ROOT / "docs/protocol_change_v9_to_v9.1.md"
    assert protocol_v91.is_file(), (
        "v9.1 amendment requires docs/protocol_change_v9_to_v9.1.md; "
        "refusing to invent a protocol here"
    )
    freeze = load_study_freeze()
    assert (
        freeze.get("design_id") == "design_freeze_v9"
        or freeze.get("design_version") == "design_freeze_v9"
    ), "default study freeze must be design_freeze_v9"
    assert freeze["formal_evidence"] is False
    assert freeze["sealed_outcomes_opened"] is False
    assert freeze["headline_claim_licensed"] is False
    assert freeze["reservoir_mechanism_in_headline"] is False
    assert freeze["hard_type_labels_are_primary"] is False
    assert freeze["eventwise_best_envelope_is_primary"] is False
    assert freeze["national_dam_auc_is_recoverability_evidence"] is False
    assert study_is_confirmatory(freeze) is False
    historical = freeze["split_rule"]["historical_seen_networks"]
    assert "jinsha_upper" in historical
    assert "chattahoochee_upper_middle" in historical
    assert freeze.get("jinsha_outcomes_reusable_as_confirmation") is False
    assert freeze.get("chattahoochee_outcomes_reusable_as_confirmation") is False
    never_sealed = set(freeze["split_rule"].get("never_sealed_networks") or [])
    required_never_sealed = {
        "jinsha_upper",
        "chattahoochee_upper_middle",
        "delaware_river_huc20",
        "willamette_river_huc17",
        "suwannee_river_huc31",
        "yellowstone_river_huc10",
        "rio_grande_huc13",
        "madison_river_huc10",
        "cahaba_river_huc31",
        "mckenzie_river_huc17",
        "mahoning_river_huc50",
        "roanoke_river_huc30",
        "santa_fe_river_huc31",
        "clearwater_river_huc17",
    }
    assert required_never_sealed.issubset(never_sealed)
    assert "delaware_river_huc20" in never_sealed
    assert "suwannee_river_huc31" in never_sealed
    assert "mahoning_river_huc50" in never_sealed
    assert DEFAULT_DESIGN_PATH.as_posix().endswith("design_freeze_v4.yaml")
    assert EXECUTABLE_DESIGN_VERSION == "design_freeze_v4"
    not_public_daily = set(
        freeze["split_rule"].get(
            "not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public"
        )
        or []
    )
    assert {"loire_mainstem", "swiss_aar_rhine"}.issubset(not_public_daily)
    assert freeze.get("not_an_executable_design") is True
    assert freeze.get("executable") is False
    t2 = freeze["locked_success_criterion"]["t2_large_sample_primary"]
    assert float(t2["out_of_network_spearman_min"]) >= 0.60
    assert float(t2["network_bootstrap_lower_bound_min"]) >= 0.40
    assert freeze.get("protocol_amendment") == "v9.1"
    assert freeze.get("protocol_change_path") == "docs/protocol_change_v9_to_v9.1.md"
    e5 = freeze["experiments"]["E5"]
    assert e5["estimand"]["forbidden_metric"] == "classification_auc"
    assert float(e5["gate"]["operator_spearman_min"]) >= 0.90
    assert float(e5["gate"]["univariate_spearman_max"]) <= 0.70
    assert float(e5["gate"]["operator_calibration_slope_min"]) >= 0.90
    assert float(e5["gate"]["operator_calibration_slope_max"]) <= 1.10
    assert e5["twin_e"]["required"] is True
    assert e5["gate"]["twin_e_must_pass_as_own_cell"] is True
    assert e5["gate"]["holdout_family_locked_before_scoring"] is True
    assert e5["twin_e"]["must_pass_as_own_cell"] is True
    assert e5["holdout_family_locked_before_scoring"] is True
    assert e5["gate"]["stricter_than_superseded_auc_gate"] is True
    assert e5["superseded_gate"]["recorded_gate_pass"] is False
    clustering = freeze["clustering_rule"]
    assert clustering["grouping"] == "huc8_plus_nldi_covariate"
    assert clustering["do_not_download_name_huc2_98_list"] is True
    assert clustering["catalog_level_count_is_not_t2"] is True
    assert clustering["catalog_level_count_is_approximate"] is False
    assert int(clustering["catalog_level_count"]) == 166
    assert clustering["reviewer_161_equals_naive_zfill"] is True
    assert clustering["reviewer_161_used_truncated_search"] is False
    assert clustering["w1a_huc8_166_is_catalog_unit_not_t2"] is True
    interval_rule = str(freeze.get("interval_rule") or "")
    assert "12-river" in interval_rule
    assert "6-river" in interval_rule
    assert "n<100" in interval_rule
    assert freeze["t5_confound_control"]["synthetic_twin_design"]["twin_e"]
    budget = freeze["recovery_benchmark"]["two_tier_compute_budget"]
    assert budget["locked_before_download"] is True
    assert budget["not_posthoc_shrinkage"] is True
    tier2 = budget["tier_2_stratified_subsample"]
    assert list(tier2["n_allowed_range"]) == [28, 32]
    assert list(tier2["gaps_all_required"]) == [30, 90, 180]
    assert tier2["sample_locked_before_download"] is True
    forbids = freeze["recovery_benchmark"]["primary_evidence_forbids"]
    assert "selecting_the_better_of_90_and_180_days" in forbids
    assert "posthoc_roster_shrink_after_download" in forbids
    assert freeze["ingest_qc"]["any_nwis_sentinel_in_values"] == "rejected_sentinel"
    ledger = (ROOT / "paper/boundary_ledger.md").read_text(encoding="utf-8")
    assert "## BL-015" in ledger
    assert "forced_donor_dominated" in ledger
    assert "## BL-016" in ledger
    assert "## BL-017" in ledger
    catalog = load_network_catalog()
    violations = validate_catalog(catalog)
    assert not violations, violations
    historical = [
        network
        for network in catalog["networks"]
        if network.get("historical_seen")
    ]
    assert {item["network_id"] for item in historical} == {
        "jinsha_upper",
        "chattahoochee_upper_middle",
    }
    assert all(item["split_role"] != "sealed" for item in historical)
    sealed = [network for network in catalog["networks"] if network["split_role"] == "sealed"]
    assert all(item.get("sealed_outcomes_opened") is False for item in sealed)
    assert all(item.get("temperature_record_unverified") is True for item in sealed)
    print("research charter, freeze, and catalog contracts hold")


if __name__ == "__main__":
    main()

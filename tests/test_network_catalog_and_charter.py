from __future__ import annotations

from pathlib import Path

from stream_recoverability.analysis.study_freeze import (
    LEGACY_STUDY_FREEZE_V1,
    load_study_freeze,
    study_is_confirmatory,
)
from stream_recoverability.data.network_catalog import (
    catalog_frame,
    load_network_catalog,
    validate_catalog,
)
from stream_recoverability.experiments.topology_falsification import (
    geometry_label,
    run_topology_suite,
)

ROOT = Path(__file__).resolve().parents[1]


def test_v9_locks_floors_and_never_sealed_rivers() -> None:
    freeze = load_study_freeze()
    t2 = freeze["locked_success_criterion"]["t2_large_sample_primary"]
    assert t2["out_of_network_spearman_min"] == 0.60
    assert t2["network_bootstrap_lower_bound_min"] == 0.40
    assert t2["gates_are_confirmatory_floors"] is True
    from stream_recoverability.analysis.hierarchical_confirmation import (
        evaluate_success,
        simulate_confirmation_panel,
    )

    small = evaluate_success(simulate_confirmation_panel(n_networks=8, seed=2))
    assert small["thresholds_locked"] is True
    assert small["confirmatory_eligible"] is False
    assert small["passed"] is False
    assert small["spearman"]["inference_status"] != "tested"
    never_sealed = set(freeze["split_rule"]["never_sealed_networks"])
    assert {
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
    }.issubset(never_sealed)
    assert "delaware_river_huc20" in never_sealed
    assert "loire_mainstem" in set(
        freeze["split_rule"][
            "not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public"
        ]
    )
    e5 = freeze["experiments"]["E5"]
    assert freeze["protocol_amendment"] == "v9.1"
    assert e5["gate"]["operator_spearman_min"] == 0.90
    assert e5["gate"]["univariate_spearman_max"] == 0.70
    assert e5["twin_e"]["required"] is True
    assert e5["gate"]["twin_e_must_pass_as_own_cell"] is True
    assert e5["gate"]["holdout_family_locked_before_scoring"] is True
    assert e5["holdout_family_locked_before_scoring"] is True
    assert e5["superseded_gate"]["recorded_gate_pass"] is False
    clustering = freeze["clustering_rule"]
    assert clustering["grouping"] == "huc8_plus_nldi_covariate"
    assert clustering["catalog_level_count_is_approximate"] is False
    assert int(clustering["catalog_level_count"]) == 166
    assert clustering["catalog_level_count_is_not_t2"] is True
    assert clustering["reviewer_161_equals_naive_zfill"] is True
    assert clustering["reviewer_161_used_truncated_search"] is False
    assert clustering["reviewer_161_is_truncated_lower_bound"] is False
    assert clustering["w1a_huc8_166_is_catalog_unit_not_t2"] is True
    interval_rule = str(freeze["interval_rule"])
    assert "6-river" in interval_rule
    assert "n<100" in interval_rule
    tier2 = freeze["recovery_benchmark"]["two_tier_compute_budget"][
        "tier_2_stratified_subsample"
    ]
    assert list(tier2["n_allowed_range"]) == [28, 32]
    assert list(tier2["gaps_all_required"]) == [30, 90, 180]
    assert tier2["sample_locked_before_download"] is True
    forbids = freeze["recovery_benchmark"]["primary_evidence_forbids"]
    assert "selecting_the_better_of_90_and_180_days" in forbids
    assert "posthoc_roster_shrink_after_download" in forbids


def test_evaluate_success_cannot_confirmatory_pass_below_100_networks() -> None:
    from stream_recoverability.analysis.hierarchical_confirmation import (
        evaluate_success,
        simulate_confirmation_panel,
    )

    for n_networks in (4, 6, 12, 99):
        result = evaluate_success(
            simulate_confirmation_panel(n_networks=n_networks, seed=3, noise=0.02)
        )
        assert result["passed"] is False
        assert result["confirmatory_eligible"] is False
        assert result["n_networks_min"] == 100
        assert result["spearman"]["inference_status"] != "tested"
        assert result["passed_numeric_floors"] is False
        ci_lower = result["spearman"]["ci_lower"]
        ci_upper = result["spearman"]["ci_upper"]
        assert ci_lower != ci_lower
        assert ci_upper != ci_upper

    large = evaluate_success(
        simulate_confirmation_panel(n_networks=120, seed=1, noise=0.02)
    )
    assert large["confirmatory_eligible"] is True
    assert large["n_networks_min"] == 100
    assert large["spearman"]["n_networks"] == 120


def test_study_freeze_does_not_license_confirmation() -> None:
    freeze = load_study_freeze()
    assert freeze["formal_evidence"] is False
    assert study_is_confirmatory(freeze) is False
    assert freeze["jinsha_outcomes_reusable_as_confirmation"] is False
    assert freeze["chattahoochee_outcomes_reusable_as_confirmation"] is False
    legacy = load_study_freeze(LEGACY_STUDY_FREEZE_V1)
    assert legacy["design_id"] == "recoverability_study_freeze_v1"
    assert study_is_confirmatory(legacy) is False


def test_catalog_is_metadata_only_and_covers_regimes() -> None:
    document = load_network_catalog()
    assert validate_catalog(document) == []
    frame = catalog_frame(document)
    assert frame["sealed_outcomes_opened"].eq(False).all()
    sealed = frame.loc[frame["split_role"].eq("sealed")]
    assert sealed["temperature_record_unverified"].all()
    assert {"regulated", "groundwater_dominated", "atmospheric", "large_river"}.issubset(
        set(frame["regime"])
    )
    historical = set(frame.loc[frame["split_role"].eq("historical"), "network_id"])
    assert historical == {"jinsha_upper", "chattahoochee_upper_middle"}


def test_charter_and_protocol_exist() -> None:
    charter = (ROOT / "docs/research_charter_v1.md").read_text(encoding="utf-8")
    current_protocol = ROOT / "docs/protocol_change_v8_to_v9.md"
    amendment = ROOT / "docs/protocol_change_v9_to_v9.1.md"
    historical_protocol = ROOT / "docs/protocol_change_v7_to_v8.md"
    assert "怎样算失败" in charter
    assert current_protocol.is_file()
    assert amendment.is_file()
    amendment_text = amendment.read_text(encoding="utf-8")
    assert "Twin E" in amendment_text
    assert "stricter" in amendment_text.lower() or "更严" in amendment_text
    assert "独立格子" in amendment_text
    assert "hold-out" in amendment_text.lower() or "Hold-out" in amendment_text
    assert "n<100" in amendment_text
    assert "一律拒绝" in amendment_text or "禁止" in amendment_text
    assert "161 条已在手" not in amendment_text
    assert "T2 is met" not in amendment_text
    assert "univariate ceiling raised 0.65" not in amendment_text
    ledger = (ROOT / "paper/boundary_ledger.md").read_text(encoding="utf-8")
    assert "## BL-016" in ledger
    assert "## BL-017" in ledger
    assert "## BL-015" in ledger
    assert "Twin E passes as its own cell" in ledger
    assert "naive" in ledger.lower() and "zfill" in ledger.lower()
    assert "truncated combo" in ledger.lower() or "truncated search" in ledger.lower()
    assert "Does it suggest a redesign of the historical freeze?** NO" in ledger
    assert "W1-A" in ledger or "166" in ledger
    if historical_protocol.is_file():
        assert "design_freeze_v4" in historical_protocol.read_text(encoding="utf-8")
    assert (ROOT / "paper/next/manuscript_skeleton.md").is_file()


def test_topology_suite_labels_one_sided_endpoints() -> None:
    assert geometry_label(0, (1, 2)) == "downstream_only"
    assert geometry_label(2, (0, 1)) == "upstream_only"
    result = run_topology_suite()
    audit = result["endpoint_audit"].set_index("river")
    assert bool(audit.loc["endpoint_upstream_origin", "network_endpoint"])
    assert audit.loc["endpoint_upstream_origin", "geometry"] == "downstream_only"

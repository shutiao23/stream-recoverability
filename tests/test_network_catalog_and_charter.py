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
    never_sealed = set(freeze["split_rule"]["never_sealed_networks"])
    assert "delaware_river_huc20" in never_sealed
    assert "loire_mainstem" in set(
        freeze["split_rule"][
            "not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public"
        ]
    )


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
    historical_protocol = ROOT / "docs/protocol_change_v7_to_v8.md"
    assert "怎样算失败" in charter
    assert current_protocol.is_file()
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

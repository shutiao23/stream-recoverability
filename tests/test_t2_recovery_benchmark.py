from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.frozen_outage_geometry import (
    load_frozen_geometry_bindings,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    build_workload_manifest,
    discover_failure_closure_networks,
    discover_open_networks,
    execute_item,
    iter_frozen_geometry_work_items,
    iter_work_items,
    load_t2_geometry_workload,
    load_v91_budget,
    lock_tier2_sample,
    run_items,
    tier2_timing_exception_ledger,
)

ROOT = Path(__file__).resolve().parents[1]


def _fixture_repo(
    tmp_path: Path,
    *,
    role: str = "development",
    catalog_role: str | None = None,
    opened: bool = False,
    manifest_split_sha: str | None = None,
) -> Path:
    split_sha = "a" * 64
    config = tmp_path / "configs"
    config.mkdir(parents=True)
    (config / "network_catalog_v3_split.yaml").write_text(
        "status: locked_before_download\n"
        f"sha256: {split_sha}\n"
        "networks:\n"
        "- network_id: huc8_test0001\n"
        f"  role: {catalog_role or role}\n"
    )
    directory = (
        tmp_path
        / "data_versions/global_network_corpus_v1/w3_development_pilot/networks/huc8_test0001"
    )
    directory.mkdir(parents=True)
    index = pd.date_range("2018-01-01", periods=365 * 4, freq="D")
    phase = np.arange(len(index), dtype=float)
    frame = pd.DataFrame(
        {
            "date": index,
            "site_a": 10.0 + np.sin(phase / 30.0),
            "site_b": 9.0 + np.cos(phase / 27.0),
        }
    )
    frame.to_csv(directory / "daily_wide_qc.csv", index=False)
    manifest = {
        "network_id": "huc8_test0001",
        "role": role,
        "status": "complete",
        "split_sha256": manifest_split_sha or split_sha,
        "sealed_temperature_records_read": opened,
        "overlap": {
            "role": role,
            "complete_enough": True,
            "n_days": len(frame),
        },
    }
    (directory / "network_manifest.json").write_text(json.dumps(manifest) + "\n")
    return tmp_path


def test_v91_budget_is_exact() -> None:
    budget = load_v91_budget(ROOT)
    assert budget["protocol_amendment"] == "v9.1"
    assert budget["placements"] == 20
    assert budget["tier_1_models"] == (
        "climatology",
        "pchip_or_linear",
        "kalman",
        "donor_regression",
        "xgboost",
    )
    assert budget["gaps"] == (7, 14, 30, 60, 90, 180, 365)


def test_discovery_accepts_only_open_qualified_manifest(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    networks, audit = discover_open_networks(repo)
    assert [item.network_id for item in networks] == ["huc8_test0001"]
    assert audit["sealed_input_roots_allowed"] == []

    sealed_repo = _fixture_repo(tmp_path / "sealed_role", role="sealed")
    sealed, sealed_audit = discover_open_networks(sealed_repo)
    assert sealed == []
    assert sealed_audit["rejected"]["role_mismatch_or_sealed"] == 1

    opened_repo = _fixture_repo(tmp_path / "opened", opened=True)
    opened, opened_audit = discover_open_networks(opened_repo)
    assert opened == []
    assert opened_audit["rejected"]["sealed_or_opened_input"] == 1


def test_discovery_rejects_catalog_role_or_split_sha_mismatch(tmp_path: Path) -> None:
    role_repo = _fixture_repo(tmp_path / "role", catalog_role="validation")
    role_networks, role_audit = discover_open_networks(role_repo)
    assert role_networks == []
    assert role_audit["rejected"]["catalog_role_mismatch_or_network_absent"] == 1

    sha_repo = _fixture_repo(tmp_path / "sha", manifest_split_sha="b" * 64)
    sha_networks, sha_audit = discover_open_networks(sha_repo)
    assert sha_networks == []
    assert sha_audit["rejected"]["catalog_split_sha_mismatch"] == 1


def test_full_grid_keeps_all_placement_slots_and_blocks_extended_inputs(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path)
    networks, _ = discover_open_networks(repo)
    budget = load_v91_budget(ROOT)
    # Reuse the project freeze hash while pointing only at the synthetic open root.
    items = list(iter_work_items(repo, networks, budget))
    assert len(items) == 2 * 7 * 5 * 20 * 5
    assert {item.placement for item in items} == set(range(20))
    shared = {}
    for item in items:
        key = (item.target_station, item.gap_length, item.placement)
        shared.setdefault(key, set()).add(item.start_index)
    assert all(len(starts) == 1 for starts in shared.values())
    extended = next(
        item
        for item in items
        if item.model == "donor_regression"
        and item.information_condition == "B_union_D_union_M"
        and item.start_index >= 0
    )
    result = execute_item(repo, networks[0], extended)
    assert result["status"] == "structural_not_applicable"
    assert result["sealed_temperature_records_read"] is False
    assert result["formal_evidence"] is False
    assert result["reason"] == "structural_unimplemented_no_meteorology_or_hydraulics_adapter"
    _, inventory = discover_open_networks(repo)
    manifest = build_workload_manifest(
        repo, networks, inventory, budget, include_frozen_geometry=False
    )
    category_total = sum(
        manifest["tier_1"][key]
        for key in (
            "n_executable",
            "n_reference",
            "n_not_applicable",
            "n_data_ineligible",
            "n_external_dependency",
        )
    )
    assert category_total == manifest["tier_1"]["n_work_items"]
    assert manifest["tier_1"]["n_reference"] > 0
    assert manifest["tier_1"]["n_external_dependency"] == 0


def test_b_d_and_b_union_d_information_semantics(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    networks, _ = discover_open_networks(repo)
    budget = load_v91_budget(ROOT)
    items = list(
        iter_work_items(
            repo,
            networks,
            budget,
            models=["pchip_or_linear", "donor_regression"],
            gaps=[7],
            information_conditions=["B", "D", "B_union_D"],
        )
    )
    first = {
        (item.model, item.information_condition): item
        for item in items
        if item.placement == 0 and item.start_index >= 0
    }
    b = execute_item(repo, networks[0], first[("pchip_or_linear", "B")])
    d = execute_item(repo, networks[0], first[("donor_regression", "D")])
    bd = execute_item(repo, networks[0], first[("donor_regression", "B_union_D")])
    fake_joint = execute_item(
        repo, networks[0], first[("pchip_or_linear", "B_union_D")]
    )
    assert b["consumed_information"] == ["B"]
    assert d["consumed_information"] == ["D"]
    assert bd["consumed_information"] == ["B", "D"]
    assert all(row["information_condition_result"] for row in (b, d, bd))
    assert fake_joint["status"] == "structural_not_applicable"
    assert fake_joint["reason"] == "model_does_not_implement_full_information_condition"


def test_climatology_is_a_complete_reference_not_an_information_result(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path)
    networks, _ = discover_open_networks(repo)
    budget = load_v91_budget(ROOT)
    item = next(
        item
        for item in iter_work_items(
            repo,
            networks,
            budget,
            models=["climatology"],
            gaps=[7],
            information_conditions=["B_union_D"],
        )
        if item.start_index >= 0
    )
    result = execute_item(repo, networks[0], item)
    assert result["status"] == "reference_complete"
    assert result["workload_category"] == "reference"
    assert result["consumed_information"] == []
    assert result["information_condition_result"] is False
    assert result["reference_ignores_available_information"] is True
    assert result["mae_deg_c"] == result["climatology_mae_deg_c"]
    assert result["achieved_skill"] == 0.0
    assert len(result["prediction_sha256"]) == 64


def test_hidden_truth_does_not_change_bd_prediction_but_boundary_does(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path)
    networks, _ = discover_open_networks(repo)
    budget = load_v91_budget(ROOT)
    original_items = list(
        iter_work_items(
            repo,
            networks,
            budget,
            models=["pchip_or_linear", "donor_regression"],
            gaps=[7],
            information_conditions=["B", "B_union_D"],
        )
    )
    items = {
        (item.model, item.information_condition): item
        for item in original_items
        if item.start_index >= 0 and item.placement == 0 and item.target_station == "site_a"
    }
    b_item = items[("pchip_or_linear", "B")]
    bd_item = items[("donor_regression", "B_union_D")]
    original_b = execute_item(repo, networks[0], b_item)
    original_bd = execute_item(repo, networks[0], bd_item)
    path = repo / networks[0].wide_path
    frame = pd.read_csv(path)
    gap_rows = range(bd_item.start_index, bd_item.start_index + bd_item.gap_length)
    frame.loc[list(gap_rows), "site_a"] += 1000.0
    frame.to_csv(path, index=False)
    hidden_networks, _ = discover_open_networks(repo)
    hidden_b = execute_item(repo, hidden_networks[0], b_item)
    hidden_bd = execute_item(repo, hidden_networks[0], bd_item)
    assert hidden_b["prediction_sha256"] == original_b["prediction_sha256"]
    assert hidden_bd["prediction_sha256"] == original_bd["prediction_sha256"]

    frame.loc[bd_item.start_index - 1, "site_a"] += 25.0
    frame.to_csv(path, index=False)
    boundary_networks, _ = discover_open_networks(repo)
    boundary_b = execute_item(repo, boundary_networks[0], b_item)
    assert boundary_b["prediction_sha256"] != hidden_b["prediction_sha256"]


def test_bounded_run_checkpoints_and_resumes(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    networks, _ = discover_open_networks(repo)
    budget = load_v91_budget(ROOT)
    items = iter_work_items(
        repo,
        networks,
        budget,
        models=["pchip_or_linear"],
        gaps=[7],
        information_conditions=["B"],
    )
    output = tmp_path / "output"
    first = run_items(repo, networks, items, output, max_items=1)
    assert first["executed"] == 1
    assert first["statuses"] == {"complete": 1}

    items_again = iter_work_items(
        repo,
        networks,
        budget,
        models=["pchip_or_linear"],
        gaps=[7],
        information_conditions=["B"],
    )
    second = run_items(repo, networks, items_again, output, max_items=1)
    assert second["executed"] == 0
    assert second["resumed"] == 1


def test_tier2_lock_is_metadata_only_and_deterministic() -> None:
    first = lock_tier2_sample(ROOT)
    second = lock_tier2_sample(ROOT)
    assert first["sample_sha256"] == second["sample_sha256"]
    assert first["n_networks"] == 30
    assert first["data_availability_inspected"] is False
    assert first["deep_models_run"] is False
    assert first["preregistered"] is False
    allowed = {
        "network_id",
        "role",
        "climate_band",
        "regulation_stratum",
        "size_tertile",
    }
    assert all(set(row) == allowed for row in first["sample"])
    canonical = json.dumps(
        first["sample"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == first["sample_sha256"]
    ledger = tier2_timing_exception_ledger(first)
    assert ledger["sample_preregistered"] is False
    assert ledger["sealed_entries_are_metadata_only"] is True


def test_frozen_geometry_identity_truth_and_donor_mask_are_shared() -> None:
    networks, audit = discover_failure_closure_networks(ROOT)
    assert len(networks) == 67
    assert audit["qualification_mode"] == "failure_closure6"
    budget = load_v91_budget(ROOT)
    binding = ROOT / "results/framework/t2_outage_geometry_v1"
    natural, adversarial, manifest = load_frozen_geometry_bindings(binding)
    natural_row = natural.iloc[[0]]
    synchronous = adversarial.loc[
        adversarial["stress_id"].eq("synchronous_network_outage")
    ].iloc[[0]]
    items = list(
        iter_frozen_geometry_work_items(
            ROOT,
            networks,
            budget,
            natural_row,
            synchronous,
            manifest,
            models=["climatology", "pchip_or_linear", "donor_regression"],
            information_conditions=["B", "D", "B_union_D"],
        )
    )
    by_geometry = {}
    for item in items:
        by_geometry.setdefault(item.geometry_id, []).append(item)
    assert {len(group) for group in by_geometry.values()} == {9}
    assert all(len({item.geometry_row_sha256 for item in group}) == 1 for group in by_geometry.values())

    natural_items = [item for item in items if item.geometry == "natural_outage"]
    frozen_natural = natural_row.iloc[0]
    assert {item.truth_start_date for item in natural_items} == {
        frozen_natural["benchmark_start_date"]
    }
    assert {item.observed_missing_start_date for item in natural_items} == {
        frozen_natural["start_date"]
    }
    assert frozen_natural["actual_missing_truth_available"] in (False, np.bool_(False))

    synchronous_items = [
        item for item in items if item.geometry == "adversarial_stress"
    ]
    assert {item.donor_mask_rule for item in synchronous_items} == {
        "mask_all_network_stations_during_gap"
    }
    donor_d = next(
        item
        for item in synchronous_items
        if item.model == "donor_regression" and item.information_condition == "D"
    )
    result = execute_item(
        ROOT,
        next(network for network in networks if network.network_id == donor_d.network_id),
        donor_d,
    )
    assert result["status"] == "structural_not_applicable"
    assert result["reason"] == "donor_information_masked_by_frozen_geometry"


def test_t2_geometry_workload_rejects_catalog_byte_drift(tmp_path: Path) -> None:
    source = ROOT / "results/framework/t2_outage_geometry_v1"
    for name in (
        "natural_outage_catalog.csv",
        "adversarial_stress_catalog.csv",
        "geometry_binding_manifest.json",
    ):
        shutil.copy2(source / name, tmp_path / name)
    networks, _ = discover_failure_closure_networks(ROOT)
    budget = load_v91_budget(ROOT)
    workload, manifest = load_t2_geometry_workload(
        ROOT, networks, budget, directory=tmp_path
    )
    first = next(iter(workload))
    assert first.geometry_id.startswith("natural_")
    assert manifest["natural_outage"]["n_benchmark_eligible"] == 2355

    with (tmp_path / "natural_outage_catalog.csv").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    try:
        load_t2_geometry_workload(ROOT, networks, budget, directory=tmp_path)
    except ValueError as error:
        assert "byte drift" in str(error)
    else:
        raise AssertionError("T2 workload must reject frozen geometry byte drift")

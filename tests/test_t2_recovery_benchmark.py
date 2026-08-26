from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.t2_recovery_benchmark import (
    build_workload_manifest,
    discover_open_networks,
    execute_item,
    iter_work_items,
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
    assert result["reason"] == "structural_unimplemented_no_meteorology_or_hydraulics_adapter"
    _, inventory = discover_open_networks(repo)
    manifest = build_workload_manifest(repo, networks, inventory, budget)
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

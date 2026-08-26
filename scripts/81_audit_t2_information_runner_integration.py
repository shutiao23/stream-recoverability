#!/usr/bin/env python3
"""Audit one bounded open-role M/H consumer without computing performance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stream_recoverability.experiments.t2_information_runner_integration import (
    INTEGRATION_CONTRACT_VERSION,
    METEOROLOGY_LAG_ROSTER,
    load_materialized_auxiliary,
    prepare_materialized_information_item,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    RUNNER_CONTRACT_VERSION,
    discover_failure_closure_networks,
    iter_work_items,
    load_v91_budget,
    read_panel,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "results/framework/t2_information_runner_integration_v1/readiness_manifest.json"
)
V3_WORKLOAD = ROOT / "results/framework/t2_recovery_benchmark_v1/workload_manifest.json"
SMOKE_NETWORK = "huc8_02040103"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _readiness_row(item, prepared) -> dict[str, object]:
    return {
        "source_v3_item_id": item.item_id,
        "network_id": item.network_id,
        "role": item.role,
        "target_station": item.target_station,
        "model": item.model,
        "gap_length": item.gap_length,
        "placement": item.placement,
        "start_index": item.start_index,
        "information_condition": item.information_condition,
        "supported": prepared.supported,
        "category": prepared.category,
        "reason": prepared.reason,
        "requested_information_groups": prepared.audit.get(
            "requested_information_groups", []
        ),
        "n_requested_auxiliary_features": prepared.audit.get(
            "n_requested_auxiliary_features", 0
        ),
        "insufficient_train_features": prepared.audit.get(
            "insufficient_train_features", []
        ),
        "incomplete_gap_features": prepared.audit.get(
            "incomplete_gap_features", []
        ),
        "temperature_performance_metric_computed": False,
        "sealed_temperature_records_read": False,
    }


def main() -> None:
    before = _sha256(V3_WORKLOAD)
    v3 = json.loads(V3_WORKLOAD.read_text(encoding="utf-8"))
    if v3.get("runner_contract_version") != RUNNER_CONTRACT_VERSION:
        raise ValueError("frozen v3 workload/runner contract mismatch")
    networks, inventory = discover_failure_closure_networks(ROOT)
    lookup = {network.network_id: network for network in networks}
    network = lookup[SMOKE_NETWORK]
    budget = load_v91_budget(ROOT)
    items = list(
        iter_work_items(
            ROOT,
            [network],
            budget,
            models=["donor_regression"],
            gaps=[7],
            information_conditions=[
                "B_union_D_union_M",
                "B_union_D_union_M_union_H",
            ],
        )
    )
    pairs: dict[tuple[str, int, int], dict[str, object]] = {}
    for item in items:
        if item.start_index < 0:
            continue
        key = (item.target_station, item.placement, item.start_index)
        pairs.setdefault(key, {})[item.information_condition] = item
    pair = next(
        value
        for value in pairs.values()
        if {
            "B_union_D_union_M",
            "B_union_D_union_M_union_H",
        }.issubset(value)
    )

    # Network-scoped validation/load occurs once.  A future chunk executor can
    # reuse this same cache boundary for every item in the network.
    panel = read_panel(ROOT, network)
    auxiliary = load_materialized_auxiliary(ROOT, network)
    adapter_cache = {}
    rows = []
    for condition in (
        "B_union_D_union_M",
        "B_union_D_union_M_union_H",
    ):
        item = pair[condition]
        for lag in METEOROLOGY_LAG_ROSTER:
            prepared = prepare_materialized_information_item(
                ROOT,
                network,
                item,
                meteorology_lag_days=lag,
                panel=panel,
                auxiliary=auxiliary,
                adapter_cache=adapter_cache,
            )
            row = _readiness_row(item, prepared)
            row["meteorology_lag_days"] = lag
            rows.append(row)

    after = _sha256(V3_WORKLOAD)
    v3_contracts = v3["tier_1"]["model_information_contract"]
    v3_counts = v3["tier_1"]["counts_by_role_model_information"]
    extended_conditions = {
        "B_union_D_union_M",
        "B_union_D_union_M_union_H",
    }
    n_v3_extended_items = sum(
        int(count)
        for key, count in v3_counts.items()
        if key.rsplit("|", 1)[-1] in extended_conditions
    )
    n_v3_items = int(v3["tier_1"]["n_work_items"])
    projected_v4_items = (
        n_v3_items
        - n_v3_extended_items
        + n_v3_extended_items * len(METEOROLOGY_LAG_ROSTER)
    )
    classification_change = any(
        row["supported"]
        and v3_contracts[
            f"{row['model']}|{row['information_condition']}"
        ]["workload_category"]
        == "structural_not_applicable"
        for row in rows
    )
    result = {
        "manifest_schema": "t2_v91_information_runner_readiness_v1",
        "status": "candidate_consumer_ready_new_workload_freeze_required",
        "integration_contract_version": INTEGRATION_CONTRACT_VERSION,
        "source_v3_runner_contract_version": RUNNER_CONTRACT_VERSION,
        "source_v3_workload_path": str(V3_WORKLOAD.relative_to(ROOT)),
        "source_v3_workload_sha256_before": before,
        "source_v3_workload_sha256_after": after,
        "source_v3_workload_bytes_unchanged": before == after,
        "source_v3_extended_cells_remain_frozen_structural_not_applicable": True,
        "candidate_changes_v3_classification": classification_change,
        "v4_or_later_new_workload_freeze_required": classification_change,
        "v3_item_ids_reusable_as_formal_candidate_ids": False,
        "future_item_identity_must_bind": [
            "integration_contract_version",
            "materialized_auxiliary_daily_long_sha256",
            "meteorology_lag_days",
            "strict_requested_feature_coverage_semantics",
        ],
        "future_v4_meteorology_lag_roster": list(METEOROLOGY_LAG_ROSTER),
        "future_v4_extended_item_count_multiplier_per_source_item": len(
            METEOROLOGY_LAG_ROSTER
        ),
        "future_v4_extended_item_count_must_expand_lag_dimension": True,
        "source_v3_work_item_count": n_v3_items,
        "source_v3_extended_work_item_count": n_v3_extended_items,
        "future_v4_projected_work_item_count_with_lag_dimension": projected_v4_items,
        "future_v4_projected_count_is_not_a_frozen_workload": True,
        "heldout_skill_used_to_select_meteorology_lag": False,
        "all_meteorology_lag_sensitivity_cells_required": True,
        "cache_contract": (
            "load_and_hash_panel_and_auxiliary_once_per_network_and_reuse_adapter_"
            "by_train_mask_condition_lag"
        ),
        "smoke_network": SMOKE_NETWORK,
        "n_networks_discovered": len(networks),
        "catalog_split_sha256": inventory["catalog_split_sha256"],
        "cells": rows,
        "coverage_semantics": {
            "requested_roster": (
                "all_station_by_frozen_group_variables_required_no_channel_substitution"
            ),
            "train_min_days_per_feature": 365,
            "gap": "every_requested_feature_finite_on_every_gap_day",
            "missing_channel": "cell_data_ineligible_no_fill_no_drop",
            "adapter_standardization": "mean_population_sd_train_days_only",
            "meteorology_lag_roster": list(METEOROLOGY_LAG_ROSTER),
            "meteorology_lag_cell_semantics": (
                "all_three_reported_separately_no_heldout_selection"
            ),
            "downstream_missing_training_values": (
                "declared_train_only_column_median_in_baseline"
            ),
        },
        "performance_metrics_computed": False,
        "network_interval_reported": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "purpose": "pipeline_verification_not_evidence",
        "passed": False,
    }
    if not result["source_v3_workload_bytes_unchanged"]:
        raise AssertionError("readiness audit mutated the frozen v3 workload")
    if not classification_change:
        raise AssertionError("bounded M smoke did not demonstrate the required v4 split")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

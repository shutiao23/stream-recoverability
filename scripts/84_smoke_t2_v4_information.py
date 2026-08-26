#!/usr/bin/env python3
"""Run a bounded v2 M/H preparation smoke without scoring temperature."""

from __future__ import annotations

import json
from pathlib import Path

from stream_recoverability.experiments.t2_information_runner_integration import (
    load_materialized_auxiliary_v2,
    prepare_materialized_information_item,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    discover_failure_closure_networks,
    iter_work_items,
    load_v91_budget,
    read_panel,
)
from stream_recoverability.experiments.t2_workload_v4 import (
    V4_RUNNER_CONTRACT_VERSION,
    audit_v4_prerequisites,
    iter_v4_work_items,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/framework/t2_recovery_benchmark_v4/pilot_smoke_manifest.json"
PREFERRED_PILOT_NETWORK = "huc8_02040103"
CONDITIONS = ("B_union_D_union_M", "B_union_D_union_M_union_H")


def main() -> None:
    networks, _ = discover_failure_closure_networks(ROOT)
    lookup = {network.network_id: network for network in networks}
    prerequisites = audit_v4_prerequisites(
        ROOT, networks, allow_legacy_pipeline_smoke=True
    )
    if not prerequisites.bindings:
        manifest = {
            "manifest_schema": "t2_v91_open_role_workload_v4_pilot_smoke_v1",
            "status": "blocked_no_current_plan_terminal_auxiliary",
            "purpose": "pipeline_verification_not_evidence",
            "passed": False,
            "formal_evidence": False,
            "formal_workload_generated": False,
            "formal_result_generated": False,
            "n_cells": 0,
            "cells": [],
            "v2_networks_terminal_at_smoke": 0,
            "v2_networks_expected": prerequisites.n_networks_expected,
            "all_67_terminal": False,
            "temperature_columns_read_for_performance": [],
            "performance_metrics_computed": False,
            "network_interval_reported": False,
            "sealed_paths_traversed": False,
            "sealed_temperature_records_read": False,
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"output": str(OUTPUT), "n_cells": 0}, indent=2))
        return
    pilot_network = (
        PREFERRED_PILOT_NETWORK
        if PREFERRED_PILOT_NETWORK in prerequisites.bindings
        else min(prerequisites.bindings)
    )
    network = lookup[pilot_network]
    budget = load_v91_budget(ROOT)
    source = list(
        iter_work_items(
            ROOT,
            [network],
            budget,
            models=["donor_regression"],
            gaps=[7],
            information_conditions=CONDITIONS,
        )
    )
    pairs: dict[tuple[str, int, int], dict[str, object]] = {}
    for item in source:
        if item.start_index >= 0:
            pairs.setdefault(
                (item.target_station, item.placement, item.start_index), {}
            )[item.information_condition] = item
    pair = next(value for value in pairs.values() if set(CONDITIONS) <= set(value))
    source_pair = [pair[condition] for condition in CONDITIONS]
    items = list(
        iter_v4_work_items(
            source_pair, prerequisites, require_full_corpus=False
        )
    )
    panel = read_panel(ROOT, network)
    auxiliary = load_materialized_auxiliary_v2(
        ROOT, network, allow_legacy_pipeline_smoke=True
    )
    adapter_cache = {}
    cells = []
    for item in items:
        prepared = prepare_materialized_information_item(
            ROOT,
            network,
            item.runner_item(),
            meteorology_lag_days=int(item.meteorology_lag_days),
            panel=panel,
            auxiliary=auxiliary,
            adapter_cache=adapter_cache,
        )
        cells.append(
            {
                "ordinal": item.ordinal,
                "item_id": item.item_id,
                "source_v3_item_id": item.source_v3_item.item_id,
                "information_condition": item.source_v3_item.information_condition,
                "meteorology_lag_days": item.meteorology_lag_days,
                "model": item.source_v3_item.model,
                "category": prepared.category,
                "reason": prepared.reason,
                "supported": prepared.supported,
                "requested_information_groups": prepared.audit.get(
                    "requested_information_groups", []
                ),
                "n_requested_auxiliary_features": prepared.audit.get(
                    "n_requested_auxiliary_features", 0
                ),
                "auxiliary_daily_long_sha256": auxiliary.audit["daily_long_sha256"],
                "auxiliary_manifest_schema": auxiliary.audit["manifest_schema"],
                "temperature_performance_metric_computed": False,
                "sealed_temperature_records_read": False,
            }
        )
    manifest = {
        "manifest_schema": "t2_v91_open_role_workload_v4_pilot_smoke_v1",
        "status": "bounded_preparation_smoke_complete_not_formal",
        "purpose": "pipeline_verification_not_evidence",
        "passed": False,
        "formal_evidence": False,
        "formal_workload_generated": False,
        "formal_result_generated": False,
        "v4_runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "network_id": pilot_network,
        "n_cells": len(cells),
        "cells": cells,
        "v2_networks_terminal_at_smoke": prerequisites.n_networks_terminal,
        "v2_networks_expected": prerequisites.n_networks_expected,
        "all_67_terminal": prerequisites.ready,
        "legacy_schema_accepted_for_pipeline_smoke_only": (
            auxiliary.audit["source_contract"]
            == "legacy_nwis_v2_legacy_schema_pipeline_smoke"
        ),
        "temperature_columns_read_for_performance": [],
        "performance_metrics_computed": False,
        "network_interval_reported": False,
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(OUTPUT), "n_cells": len(cells)}, indent=2))


if __name__ == "__main__":
    main()

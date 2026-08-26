#!/usr/bin/env python3
"""Run bounded legacy/cache A/B smokes on the frozen open-role T2 stream."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from itertools import islice
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_cached_executor import (
    CACHE_CONTRACT_VERSION,
    NetworkExecutionCache,
)
from stream_recoverability.experiments.t2_chunk_executor import MAX_CHUNK_ITEMS
from stream_recoverability.experiments.t2_recovery_benchmark import (
    _cell_contract,
    discover_failure_closure_networks,
    execute_item,
    iter_all_work_items,
    json_safe,
    load_v91_budget,
)

DEFAULT_OUTPUT = (
    ROOT
    / "results/framework/t2_recovery_benchmark_v1"
    / "performance_smoke_v1/manifest.json"
)
EQUIVALENCE_FIELDS = (
    "ordinal",
    "item_id",
    "status",
    "reason",
    "implementation",
    "n_scored",
    "mae_deg_c",
    "climatology_mae_deg_c",
    "achieved_skill",
    "prediction_sha256",
    "input_sha256",
    "runner_contract_version",
    "sealed_temperature_records_read",
)


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(
        json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _view(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in EQUIVALENCE_FIELDS}


def _fit_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    computed = [
        row
        for row in rows
        if row.get("status") in {"complete", "reference_complete"}
    ]
    return {
        "climatology": len(computed),
        "kalman": sum(row.get("model") == "kalman" for row in computed),
        "donor_regression": sum(
            row.get("model") == "donor_regression" for row in computed
        ),
        "xgboost": sum(row.get("model") == "xgboost" for row in computed),
    }


def run_smoke(count: int, *, items, lookup) -> dict[str, Any]:
    selected = items[:count]
    began = perf_counter()
    legacy = [execute_item(ROOT, lookup[item.network_id], item) for item in selected]
    legacy_seconds = perf_counter() - began

    cache = NetworkExecutionCache(ROOT)
    began = perf_counter()
    optimized = [cache.execute(lookup[item.network_id], item) for item in selected]
    optimized_seconds = perf_counter() - began

    legacy_views = [_view(row) for row in legacy]
    optimized_views = [_view(row) for row in optimized]
    mismatches = [
        int(item.ordinal)
        for item, left, right in zip(selected, legacy_views, optimized_views, strict=True)
        if left != right
    ]
    fit_counts = _fit_counts(legacy)
    cache_stats = dict(cache.stats())
    return {
        "n_items": count,
        "ordinal_range": [int(selected[0].ordinal), int(selected[-1].ordinal) + 1],
        "legacy_wall_seconds": legacy_seconds,
        "optimized_wall_seconds": optimized_seconds,
        "wall_speedup": legacy_seconds / optimized_seconds,
        "legacy_semantic_sha256": _canonical_sha(legacy_views),
        "optimized_semantic_sha256": _canonical_sha(optimized_views),
        "semantic_equivalence_fields": list(EQUIVALENCE_FIELDS),
        "semantic_mismatch_ordinals": mismatches,
        "semantic_equivalent": not mismatches,
        "legacy_fit_counts": fit_counts,
        "optimized_fit_counts": {
            **fit_counts,
            "climatology": int(cache_stats["climatology_cache_misses_fits"]),
        },
        "legacy_panel_reads_and_hashes_during_execution": sum(
            row.get("status") in {"complete", "reference_complete"}
            for row in legacy
        ),
        "optimized_cache": cache_stats,
        "status_counts": {
            status: sum(str(row.get("status")) == status for row in legacy)
            for status in sorted({str(row.get("status")) for row in legacy})
        },
        "sealed_temperature_records_read": False,
    }


def analyze_fit_reuse(items, *, lookup) -> dict[str, Any]:
    """Count exact fit signatures without fitting any workload model."""

    n_items = 0
    supported = 0
    networks_used: set[str] = set()
    legacy_fits = {
        "climatology": 0,
        "kalman": 0,
        "donor_regression": 0,
        "xgboost": 0,
    }
    unique_signatures: dict[str, set[tuple[Any, ...]]] = {
        model: set() for model in legacy_fits
    }
    chunk_panel_signatures: set[tuple[int, str]] = set()
    chunk_climatology_signatures: set[tuple[Any, ...]] = set()
    for item in items:
        n_items += 1
        networks_used.add(item.network_id)
        chunk = int(item.ordinal) // MAX_CHUNK_ITEMS
        contract = _cell_contract(item)
        if not contract["supported"]:
            continue
        supported += 1
        chunk_panel_signatures.add((chunk, item.network_id))
        network = lookup[item.network_id]
        common = (
            network.wide_sha256,
            item.target_station,
            int(item.start_index),
            int(item.start_index) + int(item.gap_length),
        )
        legacy_fits["climatology"] += 1
        unique_signatures["climatology"].add(common)
        chunk_climatology_signatures.add((chunk, *common))
        if item.model in {"kalman", "donor_regression", "xgboost"}:
            legacy_fits[item.model] += 1
            # These fields fully describe the model frame/mask branch. The
            # audit reports possible exact duplicates but the v1 optimizer
            # deliberately keeps every non-climatology fit item-scoped.
            unique_signatures[item.model].add(
                (
                    *common,
                    item.information_condition,
                    item.donor_mask_rule,
                    item.target_mask_scope,
                    item.boundary_mode,
                )
            )
    unique_counts = {
        model: len(signatures) for model, signatures in unique_signatures.items()
    }
    return {
        "n_work_items_scanned": n_items,
        "n_supported_execution_calls": supported,
        "legacy_panel_reads_and_hashes_during_execution": supported,
        "global_network_cache_custody_read_lower_bound": len(networks_used),
        "production_chunk_size": MAX_CHUNK_ITEMS,
        "chunk_scoped_network_cache_custody_reads": len(chunk_panel_signatures),
        "legacy_fit_counts": legacy_fits,
        "exact_unique_fit_signature_counts": unique_counts,
        "exact_duplicate_fit_counts": {
            model: legacy_fits[model] - unique_counts[model]
            for model in legacy_fits
        },
        "chunk_scoped_climatology_fit_count": len(chunk_climatology_signatures),
        "chunk_scoped_climatology_duplicate_fits_removed": (
            legacy_fits["climatology"] - len(chunk_climatology_signatures)
        ),
        "enabled_fit_cache": ["climatology"],
        "item_scoped_fit_policy": ["kalman", "donor_regression", "xgboost"],
        "analysis_executes_models": False,
        "sealed_temperature_records_read": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts", nargs="+", type=int, default=[20, 100])
    parser.add_argument(
        "--analyze-full-workload",
        action="store_true",
        help="scan exact fit signatures without fitting models",
    )
    parser.add_argument(
        "--reuse-existing-smokes",
        action="store_true",
        help="retain prior bounded timings while refreshing signature analysis",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    counts = sorted(set(args.counts))
    if not counts or counts[0] < 1 or counts[-1] > 500:
        raise ValueError("smoke counts must lie between 1 and 500")
    if any("sealed" in part.lower() for part in args.output.resolve().parts):
        raise ValueError("refusing a sealed-path benchmark output")

    networks, inventory = discover_failure_closure_networks(ROOT)
    budget = load_v91_budget(ROOT)
    lookup = {network.network_id: network for network in networks}
    if args.reuse_existing_smokes:
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        smokes = existing["smokes"]
    else:
        items = list(islice(iter_all_work_items(ROOT, networks, budget), counts[-1]))
        smokes = [run_smoke(count, items=items, lookup=lookup) for count in counts]
    manifest = {
        "manifest_schema": "t2_execution_cache_performance_smoke_v1",
        "purpose": "pipeline_performance_equivalence_not_evidence",
        "cache_contract_version": CACHE_CONTRACT_VERSION,
        "n_networks_inventory": len(networks),
        "input_inventory_qualification_mode": inventory.get("qualification_mode"),
        "smokes": smokes,
        "all_semantically_equivalent": all(
            smoke["semantic_equivalent"] for smoke in smokes
        ),
        "passed": False,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "sealed_temperature_records_read": False,
    }
    if args.analyze_full_workload:
        manifest["full_workload_fit_reuse_analysis"] = analyze_fit_reuse(
            iter_all_work_items(ROOT, networks, budget), lookup=lookup
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(manifest), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

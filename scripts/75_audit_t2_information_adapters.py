#!/usr/bin/env python3
"""Audit v9.1 T2 M/H feasibility without downloads or sealed-data access."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.t2_information_adapters import (
    ADAPTER_CONTRACT_VERSION,
    fit_t2_information_adapter,
)

DEFAULT_OUTPUT = (
    ROOT / "results/framework/t2_information_adapters_v1/feasibility_manifest.json"
)
OPEN_ROLE_ROOTS = (
    "open_role_qc/development",
    "open_role_qc/validation",
)
BURNED_SMOKE_VERSION = "external_upper_middle_chattahoochee_v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_role_inventory() -> dict[str, object]:
    corpus = ROOT / "data_versions/global_network_corpus_v1"
    roots = []
    total = 0
    auxiliary_files = []
    for relative in OPEN_ROLE_ROOTS:
        root = corpus / relative / "networks"
        networks = sorted(path for path in root.glob("huc8_*") if path.is_dir())
        total += len(networks)
        schemas: set[tuple[str, ...]] = set()
        for network in networks:
            long_path = network / "daily_long_qc.csv"
            if long_path.is_file():
                schemas.add(tuple(pd.read_csv(long_path, nrows=0).columns))
            for pattern in ("*meteor*", "*hydraulic*", "*discharge*", "*flow*"):
                auxiliary_files.extend(
                    str(path.relative_to(ROOT)) for path in network.glob(pattern)
                )
        roots.append(
            {
                "relative_root": relative,
                "n_networks": len(networks),
                "daily_long_schemas": [list(value) for value in sorted(schemas)],
            }
        )
    catalog = pd.read_csv(
        ROOT / "results/framework/public_catalog/usgs_daily_temperature_series.csv",
        usecols=["site_id", "latitude", "longitude"],
    )
    coordinate_complete = np.isfinite(catalog[["latitude", "longitude"]]).all(axis=1)
    return {
        "roots": roots,
        "n_unique_role_directories": total,
        "auxiliary_files_found": sorted(set(auxiliary_files)),
        "open_role_meteorology_materialized": False,
        "open_role_hydraulics_materialized": False,
        "catalog_station_rows": len(catalog),
        "catalog_station_rows_with_coordinates": int(coordinate_complete.sum()),
        "coordinate_interpretation": (
            "sufficient_to_plan_station-specific NASA POWER point requests; "
            "not evidence that M has been acquired or provider-screened"
        ),
    }


def _burned_smoke_grid() -> dict[str, object]:
    path = ROOT / "data_versions" / BURNED_SMOKE_VERSION / "daily_long.parquet"
    # Read only the historical fitting partition.  This network is already on
    # never_sealed; no v3 sealed path is traversed or opened.
    daily = pd.read_parquet(path, filters=[("split", "==", "train")])
    index = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    site_ids = tuple(sorted(daily["site_id"].astype(str).unique()))
    fitting = pd.Series(index.year <= 2018, index=index)
    cells = []
    for condition in ("B_union_D_union_M", "B_union_D_union_M_union_H"):
        for lag in (-1, 0, 1):
            adapter = fit_t2_information_adapter(
                daily,
                target_index=index,
                train_mask=fitting,
                site_ids=site_ids,
                condition=condition,
                meteorology_lag_days=lag,
            )
            transformed = adapter.transform(daily)
            coverage = transformed.features.notna().mean()
            cells.append(
                {
                    "condition": condition,
                    "meteorology_lag_days": lag,
                    "n_days": len(transformed.features),
                    "n_features": int(transformed.features.shape[1]),
                    "min_feature_coverage": float(coverage.min()),
                    "all_features_have_train_values": all(
                        count > 0 for count in adapter.train_counts.values()
                    ),
                    "adapter_manifest_sha256": hashlib.sha256(
                        json.dumps(
                            adapter.manifest(),
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                }
            )
    return {
        "status": "passed_adapter_smoke_not_t2_evidence",
        "data_version": BURNED_SMOKE_VERSION,
        "data_role": "historical_burned_never_sealed_external_model_fitting_only",
        "input_path": str(path.relative_to(ROOT)),
        "input_sha256": _sha256_file(path),
        "parquet_filter": "split == train",
        "fit_period": "2012-01-01/2018-12-31",
        "transform_period": f"{index.min().date()}/{index.max().date()}",
        "n_sites": len(site_ids),
        "n_cells": len(cells),
        "cells": cells,
        "performance_metric_computed": False,
        "formal_evidence": False,
    }


def build_manifest() -> dict[str, object]:
    inventory = _open_role_inventory()
    smoke = _burned_smoke_grid()
    return {
        "manifest_schema": "t2_v91_information_feasibility_v1",
        "status": "blocked_for_production_t2_mh",
        "adapter_contract_version": ADAPTER_CONTRACT_VERSION,
        "design_id": "design_freeze_v9",
        "protocol_amendment": "v9.1",
        "production_ready": False,
        "reason": (
            "The HUC8 open-role corpus has temperature/QC panels but no "
            "provider-audited daily M or H artifacts."
        ),
        "open_role_inventory": inventory,
        "local_smoke_grid": smoke,
        "information_contract": {
            "M": ["Ta", "P", "W", "RH", "Rs"],
            "M_provider": "NASA POWER daily point at each USGS site coordinate",
            "H": ["F", "L"],
            "H_provider": "USGS OGC approved daily discharge and gage height",
            "station_metadata_is_hydraulics": False,
            "nested_conditions": [
                "B_union_D_union_M",
                "B_union_D_union_M_union_H",
            ],
        },
        "date_alignment": {
            "base_join": "exact timezone-naive provider calendar-day label",
            "meteorology_sensitivity_lags_days": [-1, 0, 1],
            "lag_semantics": "source_date_equals_target_date_plus_lag_days",
            "hydraulics_lag_days": 0,
            "lag_selection_using_heldout_skill": False,
            "hydraulic_travel_time_inferred_from_calendar_lag": False,
        },
        "provider_qc": {
            "M": "finite NASA POWER non-fill provider_value; not called approved",
            "H": (
                "USGS approval_status Approved and qc_status approved or "
                "approved_estimated; provisional excluded"
            ),
            "missing_policy": "NA retained; no interpolation, ffill, or bfill",
        },
        "leakage_boundary": {
            "adapter_fit_statistics": "training days only",
            "target_temperature_read_by_adapter": False,
            "auxiliary_values_inside_gap": (
                "available only in the declared M/H information condition"
            ),
            "heldout_skill_used_to_select_meteorology_lag": False,
            "sealed_paths_traversed": False,
            "sealed_temperature_records_read": False,
        },
        "downloads_performed": False,
        "required_unblock_actions": [
            "materialize station-specific NASA POWER daily M for open roles with raw-response hashes",
            "query and materialize USGS 00060/00065 daily availability for open roles",
            "apply the frozen provider QC contract and record per-feature coverage",
            "wire adapter bundles into model-specific B+D+M and B+D+M+H consumers",
            "run feasibility before any T2 performance metric",
        ],
        "passed": False,
        "formal_evidence": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()

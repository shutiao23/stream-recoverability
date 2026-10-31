"""Locked development-only download policy for the HUC8 catalog-v3 pilot.

This module deliberately has no dependency on the retired name-by-HUC2 v2
download plan.  It checks the locked split declaration before it selects any
network, and joins station-specific dates from the local public series catalog
rather than inventing a common download window.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from stream_recoverability.seeds import plain_seed


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_V3_CATALOG = REPOSITORY_ROOT / "configs/network_catalog_v3_huc8.yaml"
DEFAULT_V3_SPLIT = REPOSITORY_ROOT / "configs/network_catalog_v3_split.yaml"
DEFAULT_SERIES_METADATA = (
    REPOSITORY_ROOT
    / "results/framework/public_catalog/usgs_daily_temperature_series.csv"
)

PILOT_SEED = 20260826
PILOT_SIZE = 20
STRATIFICATION_COLUMNS = (
    "climate_band",
    "regulation_stratum",
    "size_tertile",
)


def _load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError(f"expected a YAML mapping: {path}")
    return document


def verify_split_lock(
    *,
    split_path: str | Path = DEFAULT_V3_SPLIT,
) -> dict[str, Any]:
    """Check the frozen split declaration and return it.

    The split must still be declared as locked before any download, with no
    temperatures downloaded and no sealed outcome opened.
    """

    split = _load_yaml_mapping(split_path)
    if split.get("status") != "locked_before_download":
        raise ValueError("catalog-v3 split is not locked_before_download")
    if bool(split.get("temperatures_downloaded")):
        raise ValueError("pre-download split metadata was unexpectedly mutated")
    if bool(split.get("sealed_outcomes_opened")):
        raise ValueError("split metadata says sealed outcomes were opened")
    return split


def _hamilton_quotas(
    group_sizes: Mapping[tuple[str, ...], int], n: int
) -> dict[tuple[str, ...], int]:
    """Proportional integer allocation with deterministic largest remainders."""

    total = int(sum(group_sizes.values()))
    if n < 1 or n > total:
        raise ValueError(f"pilot size must be in [1, {total}], got {n}")
    exact = {key: n * size / total for key, size in group_sizes.items()}
    quotas = {key: int(value) for key, value in exact.items()}
    remaining = n - sum(quotas.values())
    order = sorted(
        group_sizes,
        key=lambda key: (-(exact[key] - quotas[key]), key),
    )
    for key in order[:remaining]:
        quotas[key] += 1
    return quotas


def deterministic_stratified_sample(
    rows: Sequence[Mapping[str, Any]],
    *,
    n: int = PILOT_SIZE,
    seed: int = PILOT_SEED,
) -> list[dict[str, Any]]:
    """Select a reproducible proportional sample across all locked strata."""

    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for source in rows:
        row = dict(source)
        network_id = str(row.get("network_id") or "")
        if not network_id or network_id in seen:
            raise ValueError("split rows need unique non-empty network_id values")
        seen.add(network_id)
        if str(row.get("role")) != "development":
            raise ValueError(f"non-development row offered to pilot: {network_id}")
        if bool(row.get("never_sealed")):
            raise ValueError(
                f"never_sealed row offered to development pilot: {network_id}"
            )
        key = tuple(str(row.get(column) or "") for column in STRATIFICATION_COLUMNS)
        grouped[key].append(row)

    quotas = _hamilton_quotas({key: len(value) for key, value in grouped.items()}, n)
    selected: list[dict[str, Any]] = []
    for stratum_index, key in enumerate(sorted(grouped)):
        members = sorted(grouped[key], key=lambda row: str(row["network_id"]))
        order = np.random.default_rng(plain_seed(seed, stratum_index)).permutation(
            len(members)
        )
        selected.extend(members[int(index)] for index in order[: quotas[key]])
    return sorted(selected, key=lambda row: str(row["network_id"]))


def _load_series_metadata(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"site_id": str})
    required = {"site_id", "daily_begin", "daily_end"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"series metadata missing columns: {sorted(missing)}")
    frame = frame.copy()
    frame["site_id"] = frame["site_id"].astype(str)
    if frame["site_id"].duplicated().any():
        raise ValueError("series metadata has duplicate site_id rows")
    return frame.set_index("site_id", drop=False)


def plan_v3_development_pilot(
    *,
    catalog_path: str | Path = DEFAULT_V3_CATALOG,
    split_path: str | Path = DEFAULT_V3_SPLIT,
    series_metadata_path: str | Path = DEFAULT_SERIES_METADATA,
    pilot_size: int = PILOT_SIZE,
    pilot_seed: int = PILOT_SEED,
) -> dict[str, Any]:
    """Build the only permitted W3 USGS pilot plan: 20 development HUC8 units."""

    split = verify_split_lock(split_path=split_path)
    catalog = _load_yaml_mapping(catalog_path)
    if catalog.get("catalog_id") != "network_catalog_v3_huc8":
        raise ValueError("refusing a non-v3-HUC8 candidate catalog")
    if bool(catalog.get("sealed_outcomes_opened")):
        raise ValueError("candidate catalog says sealed outcomes were opened")

    candidates = {
        str(row.get("network_id")): dict(row) for row in catalog.get("networks") or []
    }
    development = [
        dict(row)
        for row in split.get("networks") or []
        if str(row.get("role")) == "development"
    ]
    selected = deterministic_stratified_sample(
        development, n=pilot_size, seed=pilot_seed
    )
    metadata = _load_series_metadata(series_metadata_path)

    networks: list[dict[str, Any]] = []
    for split_row in selected:
        network_id = str(split_row["network_id"])
        candidate = candidates.get(network_id)
        if candidate is None:
            raise ValueError(f"split network absent from HUC8 catalog: {network_id}")
        site_ids = [str(item) for item in candidate.get("candidate_station_ids") or []]
        if len(site_ids) < 3 or len(site_ids) != len(set(site_ids)):
            raise ValueError(f"invalid HUC8 candidate station list: {network_id}")
        stations = []
        for site_id in site_ids:
            if site_id not in metadata.index:
                raise ValueError(
                    f"candidate {network_id} site {site_id} absent from local series metadata"
                )
            source = metadata.loc[site_id]
            start = pd.to_datetime(source["daily_begin"], errors="coerce")
            end = pd.to_datetime(source["daily_end"], errors="coerce")
            if pd.isna(start) or pd.isna(end) or start > end:
                raise ValueError(f"invalid local series dates for station {site_id}")
            stations.append(
                {
                    "site_id": site_id,
                    "start": pd.Timestamp(start).date().isoformat(),
                    "end": pd.Timestamp(end).date().isoformat(),
                }
            )
        networks.append(
            {
                "network_id": network_id,
                "role": "development",
                "climate_band": str(split_row.get("climate_band") or ""),
                "regulation_stratum": str(split_row.get("regulation_stratum") or ""),
                "size_tertile": str(split_row.get("size_tertile") or ""),
                "flow_connected": candidate.get("flow_connected"),
                "stations": stations,
            }
        )

    return {
        "policy": "catalog_v3_huc8_development_only",
        "pilot_seed": int(pilot_seed),
        "pilot_size": int(pilot_size),
        "stratification_columns": list(STRATIFICATION_COLUMNS),
        "n_development_available": len(development),
        "n_validation_selected": 0,
        "n_sealed_selected": 0,
        "sealed_temperature_records_read": False,
        "retired_name_huc2_plan_used": False,
        "networks": networks,
    }


__all__ = [
    "PILOT_SEED",
    "PILOT_SIZE",
    "STRATIFICATION_COLUMNS",
    "deterministic_stratified_sample",
    "plan_v3_development_pilot",
    "verify_split_lock",
]

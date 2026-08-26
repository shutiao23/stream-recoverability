"""Bounded open-role acquisition pilot for the v9.1 T2 M/H adapters.

This module deliberately supports one development network only.  It reads the
open-role panel's station/date columns to bind request windows, but never reads
water-temperature values and never traverses a sealed role.  Provider failures
and genuinely absent USGS series are recorded per source instead of widening
the requested corpus.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import confirmatory as provider
from .t2_information_adapters import (
    ADAPTER_CONTRACT_VERSION,
    HYDRAULICS_VARIABLES,
    METEOROLOGY_VARIABLES,
)

PILOT_NETWORK_ID = "huc8_01070004"
PILOT_ROLE = "development"
PILOT_SCHEMA_VERSION = "t2_v91_open_role_mh_acquisition_pilot_v1"
SPLIT_SHA256 = "2405169325fecaeb24bea9a5c9fc5ea66e303c14e41def1e3d32f6853679c1f1"


@dataclass(frozen=True)
class PilotSite:
    site_id: str
    start: str
    end: str
    longitude: float
    latitude: float


@dataclass(frozen=True)
class PilotPlan:
    network_id: str
    role: str
    sites: tuple[PilotSite, ...]
    split_sha256: str = SPLIT_SHA256


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def load_bounded_pilot_plan(repository_root: str | Path) -> PilotPlan:
    """Resolve and verify the deterministic first complete development network."""

    root = Path(repository_root)
    split_path = root / "results/framework/public_catalog/catalog_v3_split_table.csv"
    split = pd.read_csv(split_path, dtype={"network_id": "string", "role": "string"})
    development = split.loc[split["role"].eq(PILOT_ROLE)].sort_values("network_id")
    if development.empty or str(development.iloc[0]["network_id"]) != PILOT_NETWORK_ID:
        raise ValueError("bounded pilot is not the deterministic first development network")

    network_root = (
        root
        / "data_versions/global_network_corpus_v1/open_role_qc/development/networks"
        / PILOT_NETWORK_ID
    )
    qc_path = network_root / "network_qc_manifest.json"
    qc = json.loads(qc_path.read_text(encoding="utf-8"))
    expected_qc = {
        "network_id": PILOT_NETWORK_ID,
        "role": PILOT_ROLE,
        "status": "complete",
    }
    for key, expected in expected_qc.items():
        if qc.get(key) != expected:
            raise ValueError(f"pilot network QC {key} is not {expected!r}")
    if not bool(qc.get("overlap", {}).get("complete_enough")):
        raise ValueError("pilot network is not complete_enough")
    if qc.get("split_sha256") != SPLIT_SHA256:
        raise ValueError("pilot network split hash differs from locked catalog v3")

    # Explicitly request only identifiers and dates.  The temperature outcome
    # column is not loaded even for this open development role.
    dates = pd.read_csv(
        network_root / "daily_long_qc.csv",
        usecols=["site_id", "date"],
        dtype={"site_id": "string", "date": "string"},
    )
    windows = dates.groupby("site_id", sort=True)["date"].agg(["min", "max"])

    locations = pd.read_csv(
        root / "results/framework/public_catalog/usgs_long_temperature_locations.csv",
        usecols=["site_id", "latitude", "longitude", "found"],
        dtype={"site_id": "string"},
    ).set_index("site_id")
    sites: list[PilotSite] = []
    for site_id in sorted(qc["stations"]):
        if site_id not in windows.index or site_id not in locations.index:
            raise ValueError(f"pilot site lacks date window or coordinates: {site_id}")
        location = locations.loc[site_id]
        longitude = float(location["longitude"])
        latitude = float(location["latitude"])
        if not bool(location["found"]) or not np.isfinite([longitude, latitude]).all():
            raise ValueError(f"pilot site lacks finite provider coordinates: {site_id}")
        sites.append(
            PilotSite(
                site_id=site_id,
                start=str(windows.loc[site_id, "min"]),
                end=str(windows.loc[site_id, "max"]),
                longitude=longitude,
                latitude=latitude,
            )
        )
    if tuple(site.site_id for site in sites) != (
        "01095220",
        "01095375",
        "01095434",
    ):
        raise ValueError("bounded pilot station set changed")
    return PilotPlan(PILOT_NETWORK_ID, PILOT_ROLE, tuple(sites))


def _protocol(site: PilotSite) -> provider.ConfirmatoryProtocol:
    return provider.ConfirmatoryProtocol(
        design_path="configs/design_freeze_v9.yaml",
        design_sha256="not_used_by_bounded_acquisition_pilot",
        design_version="design_freeze_v9.1_information_acquisition_pilot",
        network=PILOT_NETWORK_ID,
        site_ids=(site.site_id,),
        periods=(provider.SplitPeriod("open_role_request_window", site.start, site.end),),
        quality_rule=(
            "POWER finite non-fill; USGS Approved only; provisional excluded"
        ),
        nasa_community="AG",
        nasa_time_standard="UTC",
        nasa_spatial_rule="nearest_POWER_grid_cell_to_each_USGS_site_coordinate",
        rs_interpretation=provider.RS_INTERPRETATION,
        network_huc8=(PILOT_NETWORK_ID.removeprefix("huc8_"),),
    )


def build_request_plan(plan: PilotPlan) -> dict[str, Any]:
    requests: list[dict[str, Any]] = []
    for site in plan.sites:
        protocol = _protocol(site)
        for spec in provider.HYDROLOGY_SPECS[1:]:
            requests.extend(
                [
                    {
                        "provider": "usgs_ogc_daily",
                        "request_kind": "time_series_metadata",
                        "site_id": site.site_id,
                        "variable": spec.variable,
                        "start": site.start,
                        "end": site.end,
                        "url": provider._usgs_time_series_url(site.site_id, spec),
                    },
                    {
                        "provider": "usgs_ogc_daily",
                        "request_kind": "daily_values",
                        "site_id": site.site_id,
                        "variable": spec.variable,
                        "start": site.start,
                        "end": site.end,
                        "url": provider._usgs_daily_url(site.site_id, spec, protocol),
                    },
                ]
            )
        requests.append(
            {
                "provider": "nasa_power_daily_point",
                "request_kind": "daily_point_meteorology",
                "site_id": site.site_id,
                "variable": None,
                "start": site.start,
                "end": site.end,
                "longitude": site.longitude,
                "latitude": site.latitude,
                "url": provider._nasa_power_url(
                    site.longitude, site.latitude, protocol
                ),
            }
        )
    result = {
        "manifest_schema": "t2_v91_open_role_mh_request_plan_v1",
        "bounded_network_id": plan.network_id,
        "role": plan.role,
        "split_sha256": plan.split_sha256,
        "n_networks": 1,
        "n_sites": len(plan.sites),
        "requests": requests,
        "n_initial_requests": len(requests),
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "performance_metrics_computed": False,
    }
    result["plan_sha256"] = hashlib.sha256(_canonical_json(result).encode()).hexdigest()
    return result


def _empty_daily() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "date",
            "site_id",
            "station_id",
            "variable",
            "value",
            "source",
            "natural_observed",
            "qc_status",
            "approval_status",
            "quality_approved",
        ]
    )


def _coverage(
    plan: PilotPlan,
    daily: pd.DataFrame,
    failures: list[dict[str, Any]],
) -> pd.DataFrame:
    failed = {(row["site_id"], row["variable"]) for row in failures}
    rows: list[dict[str, Any]] = []
    for site in plan.sites:
        expected_days = len(pd.date_range(site.start, site.end, freq="D"))
        for variable in (*METEOROLOGY_VARIABLES, *HYDRAULICS_VARIABLES):
            subset = daily.loc[
                daily.get("site_id", pd.Series(dtype=str)).astype(str).eq(site.site_id)
                & daily.get("variable", pd.Series(dtype=str)).astype(str).eq(variable)
            ]
            eligible = subset.get("natural_observed", pd.Series(False, index=subset.index))
            if variable in HYDRAULICS_VARIABLES:
                eligible = eligible.astype(bool) & subset.get(
                    "quality_approved", pd.Series(False, index=subset.index)
                ).astype(bool)
            rows.append(
                {
                    "network_id": plan.network_id,
                    "role": plan.role,
                    "site_id": site.site_id,
                    "variable": variable,
                    "information_group": "M"
                    if variable in METEOROLOGY_VARIABLES
                    else "H",
                    "request_start": site.start,
                    "request_end": site.end,
                    "n_expected_calendar_days": expected_days,
                    "n_provider_rows": len(subset),
                    "n_provider_eligible_rows": int(eligible.sum()),
                    "provider_row_coverage": len(subset) / expected_days,
                    "eligible_coverage": int(eligible.sum()) / expected_days,
                    "source_status": (
                        "failed_or_unavailable"
                        if (site.site_id, variable) in failed
                        else "materialized"
                    ),
                }
            )
    return pd.DataFrame(rows)


def _artifact_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": _relative(path, root),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }


def run_bounded_pilot(
    repository_root: str | Path,
    output_dir: str | Path,
    *,
    execute: bool = False,
    fetcher: provider.HTTPFetcher = provider.urlopen_fetcher,
    usgs_api_key: str | None = None,
) -> dict[str, Any]:
    """Plan or execute the single-network M/H acquisition pilot."""

    root = Path(repository_root)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    plan = load_bounded_pilot_plan(root)
    request_plan = build_request_plan(plan)
    request_plan_path = output / "request_plan.json"
    request_plan_path.write_text(
        json.dumps(request_plan, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    if not execute:
        manifest = {
            "manifest_schema": PILOT_SCHEMA_VERSION,
            "status": "dry_run",
            "dry_run": True,
            "execute": False,
            "network_id": plan.network_id,
            "role": plan.role,
            "n_networks": 1,
            "n_sites": len(plan.sites),
            "site_ids": [site.site_id for site in plan.sites],
            "request_plan": _artifact_record(request_plan_path, root),
            "provider_responses_opened": False,
            "temperature_columns_read": [],
            "sealed_paths_traversed": False,
            "sealed_temperature_records_read": False,
            "performance_metrics_computed": False,
            "formal_evidence": False,
            "purpose": "pipeline_verification_not_evidence",
            "passed": False,
        }
        manifest_path = output / "pilot_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return manifest

    raw_root = output / "raw"
    daily_frames: list[pd.DataFrame] = []
    series_frames: list[pd.DataFrame] = []
    power_metadata_frames: list[pd.DataFrame] = []
    request_records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for site in plan.sites:
        protocol = _protocol(site)
        for spec in provider.HYDROLOGY_SPECS[1:]:
            try:
                series_result = provider.fetch_ogc_feature_collection(
                    provider._usgs_time_series_url(site.site_id, spec),
                    request_kind="time_series_metadata",
                    site_id=site.site_id,
                    variable=spec.variable,
                    raw_root=raw_root,
                    artifact_prefix=(
                        Path("usgs")
                        / "time_series_metadata"
                        / site.site_id
                        / spec.variable
                    ),
                    fetcher=fetcher,
                    api_key=usgs_api_key,
                )
                request_records.extend(series_result.request_records)
                series = provider.parse_time_series_metadata(
                    site.site_id, spec, series_result
                )
                series_frames.append(series)
                allowed = set(
                    series.loc[
                        series["metadata_available"].fillna(False), "id"
                    ].astype(str)
                )
                if not allowed:
                    failures.append(
                        {
                            "site_id": site.site_id,
                            "variable": spec.variable,
                            "provider": "usgs_ogc_daily",
                            "status": "source_unavailable_no_daily_mean_series",
                            "error_type": None,
                            "error": None,
                        }
                    )
                    continue
                daily_result = provider.fetch_ogc_feature_collection(
                    provider._usgs_daily_url(site.site_id, spec, protocol),
                    request_kind="daily_values",
                    site_id=site.site_id,
                    variable=spec.variable,
                    raw_root=raw_root,
                    artifact_prefix=(
                        Path("usgs") / "daily" / site.site_id / spec.variable
                    ),
                    fetcher=fetcher,
                    api_key=usgs_api_key,
                )
                request_records.extend(daily_result.request_records)
                daily_frames.append(
                    provider.parse_usgs_daily_values(
                        site.site_id,
                        spec,
                        daily_result,
                        allowed_time_series_ids=allowed,
                        start=site.start,
                        end=site.end,
                    )
                )
            # Provider and parser failures are retained per source in the audit.
            except Exception as error:  # noqa: BLE001
                failures.append(
                    {
                        "site_id": site.site_id,
                        "variable": spec.variable,
                        "provider": "usgs_ogc_daily",
                        "status": "source_fetch_or_parse_failed",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )

        try:
            meteorology, point_metadata, record = provider._fetch_power_document(
                site_id=site.site_id,
                longitude=site.longitude,
                latitude=site.latitude,
                protocol=protocol,
                raw_root=raw_root,
                fetcher=fetcher,
            )
            daily_frames.append(meteorology)
            power_metadata_frames.append(point_metadata)
            request_records.append(record)
        # One arbitrary POWER transport/parser failure represents all M fields.
        except Exception as error:  # noqa: BLE001
            for variable in METEOROLOGY_VARIABLES:
                failures.append(
                    {
                        "site_id": site.site_id,
                        "variable": variable,
                        "provider": "nasa_power_daily_point",
                        "status": "source_fetch_or_parse_failed",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )

    daily = (
        pd.concat(daily_frames, ignore_index=True)
        if daily_frames
        else _empty_daily()
    )
    if not daily.empty:
        daily = daily.sort_values(["site_id", "date", "variable"]).reset_index(drop=True)
    coverage = _coverage(plan, daily, failures)
    series = pd.concat(series_frames, ignore_index=True) if series_frames else pd.DataFrame()
    power_metadata = (
        pd.concat(power_metadata_frames, ignore_index=True)
        if power_metadata_frames
        else pd.DataFrame()
    )

    daily_path = output / "daily_long_auxiliary.parquet"
    coverage_path = output / "coverage.csv"
    series_path = output / "usgs_time_series_metadata.csv"
    power_path = output / "power_point_metadata.csv"
    records_path = output / "raw_request_log.json"
    failures_path = output / "source_failures.json"
    schema_path = output / "adapter_schema.json"
    daily.to_parquet(daily_path, index=False)
    coverage.to_csv(coverage_path, index=False)
    series.to_csv(series_path, index=False)
    power_metadata.to_csv(power_path, index=False)
    records_path.write_text(
        json.dumps(request_records, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    failures_path.write_text(
        json.dumps(failures, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    adapter_schema = {
        "adapter_contract_version": ADAPTER_CONTRACT_VERSION,
        "table": "daily_long_auxiliary.parquet",
        "required_columns": [
            "date",
            "site_id",
            "variable",
            "value",
            "source",
            "natural_observed",
            "qc_status",
            "approval_status",
            "quality_approved",
        ],
        "variables": {
            "M": list(METEOROLOGY_VARIABLES),
            "H": list(HYDRAULICS_VARIABLES),
        },
        "value_role": "M_or_H_covariate_only_never_temperature_target",
        "power_fill_policy": "natural_observed_false_value_NA_qc_provider_fill_value",
        "usgs_provisional_policy": (
            "quality_approved_false_value_NA_qc_excluded_provisional"
        ),
        "missing_source_policy": "record_failure_and_leave_absent_no_fill",
    }
    schema_path.write_text(
        json.dumps(adapter_schema, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    artifacts = {
        name: _artifact_record(path, root)
        for name, path in {
            "request_plan": request_plan_path,
            "daily_long_auxiliary": daily_path,
            "coverage": coverage_path,
            "usgs_time_series_metadata": series_path,
            "power_point_metadata": power_path,
            "raw_request_log": records_path,
            "source_failures": failures_path,
            "adapter_schema": schema_path,
        }.items()
    }
    raw_hashes = [
        str(record["response_sha256"])
        for record in request_records
        if record.get("response_sha256")
    ]
    manifest = {
        "manifest_schema": PILOT_SCHEMA_VERSION,
        "status": "materialized_complete" if not failures else "materialized_partial",
        "dry_run": False,
        "execute": True,
        "network_id": plan.network_id,
        "role": plan.role,
        "split_sha256": plan.split_sha256,
        "n_networks": 1,
        "n_sites": len(plan.sites),
        "site_ids": [site.site_id for site in plan.sites],
        "station_request_windows": [site.__dict__ for site in plan.sites],
        "n_auxiliary_rows": len(daily),
        "n_source_failures_or_unavailable": len(failures),
        "n_raw_responses": len(request_records),
        "raw_response_sha256": raw_hashes,
        "raw_response_hashes_complete_for_logged_responses": (
            len(raw_hashes) == len(request_records)
        ),
        "artifacts": artifacts,
        "provider_qc": {
            "POWER": "finite and not provider fill_value; fill retained as rejected row",
            "USGS": "Approved only; Provisional retained as rejected row with NA value",
        },
        "value_role": "M_and_H_covariates_only_not_target",
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "performance_metrics_computed": False,
        "network_interval_reported": False,
        "formal_evidence": False,
        "purpose": "pipeline_verification_not_evidence",
        "passed": not failures and len(daily) > 0,
    }
    manifest_path = output / "pilot_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest


__all__ = [
    "PILOT_NETWORK_ID",
    "PILOT_ROLE",
    "PilotPlan",
    "PilotSite",
    "build_request_plan",
    "load_bounded_pilot_plan",
    "run_bounded_pilot",
]

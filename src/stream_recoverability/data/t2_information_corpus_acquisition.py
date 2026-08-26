"""Recoverable, sequential M/H acquisition for the open T2 corpus.

The acquisition roster is exactly the 67 overlap-qualified development and
validation networks in the frozen six-year failure closure.  Planning reads
only station identifiers and dates from open-role QC tables.  It rejects
sealed roles and never loads the water-temperature outcome column.

Execution is deliberately network-scoped and sequential.  A terminal network
manifest is an integrity-checked resume boundary; interrupted networks can be
retried without touching completed peers.  This module materializes auxiliary
covariates and their provider-QC audit only.  It computes no recovery score or
performance statistic.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.experiments.t2_recovery_benchmark import (
    discover_failure_closure_networks,
)

from . import confirmatory as provider
from .t2_information_adapters import (
    ADAPTER_CONTRACT_VERSION,
    HYDRAULICS_VARIABLES,
    METEOROLOGY_VARIABLES,
)

CORPUS_SCHEMA_VERSION = "t2_v91_open_role_mh_corpus_acquisition_v1"
NETWORK_SCHEMA_VERSION = "t2_v91_open_role_mh_network_acquisition_v1"
PLAN_SCHEMA_VERSION = "t2_v91_open_role_mh_corpus_request_plan_v1"
SPLIT_SHA256 = "2405169325fecaeb24bea9a5c9fc5ea66e303c14e41def1e3d32f6853679c1f1"
EXPECTED_NETWORKS = 67
POWER_DAILY_START = "1981-01-01"
ALLOWED_ROLES = ("development", "validation")
TERMINAL_STATUSES = ("materialized_complete", "materialized_partial")
RETRY_STATUS = "acquisition_retry_required"


@dataclass(frozen=True)
class CorpusSitePlan:
    site_id: str
    target_start: str
    target_end: str
    power_start: str
    longitude: float
    latitude: float


@dataclass(frozen=True)
class CorpusNetworkPlan:
    network_id: str
    role: str
    source_key: str
    sites: tuple[CorpusSitePlan, ...]
    source_network_manifest_sha256: str
    source_date_projection_sha256: str
    split_sha256: str
    network_plan_sha256: str


@dataclass(frozen=True)
class CorpusAcquisitionPlan:
    networks: tuple[CorpusNetworkPlan, ...]
    split_sha256: str
    plan_sha256: str


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _artifact_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": _relative(path, root),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _normalize_site_id(value: Any) -> str:
    site = str(value).strip()
    if not site or not site.isdigit():
        raise ValueError(f"USGS site id must contain digits only: {value!r}")
    return site.zfill(8)


def _network_plan_payload(
    *,
    network_id: str,
    role: str,
    source_key: str,
    sites: Sequence[CorpusSitePlan],
    source_network_manifest_sha256: str,
    source_date_projection_sha256: str,
) -> dict[str, Any]:
    return {
        "network_id": network_id,
        "role": role,
        "source_key": source_key,
        "sites": [asdict(site) for site in sites],
        "source_network_manifest_sha256": source_network_manifest_sha256,
        "source_date_projection_sha256": source_date_projection_sha256,
        "split_sha256": SPLIT_SHA256,
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "performance_metrics_computed": False,
    }


def load_corpus_plan(repository_root: str | Path) -> CorpusAcquisitionPlan:
    """Bind a deterministic plan to the exact failure-closure T2 roster."""

    root = Path(repository_root).resolve()
    networks, discovery = discover_failure_closure_networks(root)
    if discovery.get("catalog_split_sha256") != SPLIT_SHA256:
        raise ValueError("failure-closure discovery differs from the locked split SHA")
    if len(networks) != EXPECTED_NETWORKS:
        raise ValueError(
            f"production M/H roster must contain exactly {EXPECTED_NETWORKS} networks, "
            f"found {len(networks)}"
        )
    if set(discovery.get("roles", {})) != set(ALLOWED_ROLES):
        raise ValueError("production M/H roster must contain both open roles only")

    locations_path = root / "results/framework/public_catalog/usgs_long_temperature_locations.csv"
    locations = pd.read_csv(
        locations_path,
        usecols=["site_id", "latitude", "longitude", "found"],
        dtype={"site_id": "string"},
    )
    locations["site_id"] = locations["site_id"].map(_normalize_site_id)
    if locations["site_id"].duplicated().any():
        raise ValueError("USGS location catalog contains duplicate station identifiers")
    locations = locations.set_index("site_id")

    plans: list[CorpusNetworkPlan] = []
    for network in networks:
        if network.role not in ALLOWED_ROLES or "sealed" in network.source_key.lower():
            raise ValueError(f"non-open network reached M/H planning: {network.network_id}")
        network_dir = (root / network.wide_path).parent
        allowed_root = (
            root
            / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
            / network.role
        )
        if not _inside(network_dir, allowed_root):
            raise ValueError(f"network escaped the open failure closure: {network.network_id}")
        manifest_path = root / network.manifest_path
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        overlap = manifest.get("overlap") or {}
        if (
            manifest.get("status") != "complete"
            or overlap.get("complete_enough") is not True
            or manifest.get("qualification_mode") != "failure_closure6"
            or manifest.get("split_sha256") != SPLIT_SHA256
            or manifest.get("sealed_temperature_records_read") is not False
        ):
            raise ValueError(f"network is not eligible open failure-closure input: {network.network_id}")

        wide_columns = pd.read_csv(network_dir / "daily_wide_qc.csv", nrows=0).columns
        station_ids = tuple(sorted(_normalize_site_id(value) for value in wide_columns[1:]))
        if len(station_ids) < 3 or len(set(station_ids)) != len(station_ids):
            raise ValueError(f"invalid T2 station roster for {network.network_id}")

        # This is the only row-bearing source read.  The outcome column is not
        # requested from pandas and therefore never enters the process.
        date_path = network_dir / "daily_long_qc.csv"
        dates = pd.read_csv(
            date_path,
            usecols=["site_id", "date"],
            dtype={"site_id": "string", "date": "string"},
        )
        dates["site_id"] = dates["site_id"].map(_normalize_site_id)
        if set(dates["site_id"].unique()) != set(station_ids):
            raise ValueError(f"date projection differs from T2 station roster: {network.network_id}")
        windows = dates.groupby("site_id", sort=True)["date"].agg(["min", "max"])

        site_plans: list[CorpusSitePlan] = []
        for site_id in station_ids:
            if site_id not in locations.index:
                raise ValueError(f"site lacks public coordinates: {site_id}")
            location = locations.loc[site_id]
            longitude = float(location["longitude"])
            latitude = float(location["latitude"])
            if not bool(location["found"]) or not np.isfinite([longitude, latitude]).all():
                raise ValueError(f"site lacks finite public coordinates: {site_id}")
            target_start = str(windows.loc[site_id, "min"])
            target_end = str(windows.loc[site_id, "max"])
            if pd.Timestamp(target_end) < pd.Timestamp(target_start):
                raise ValueError(f"reversed request window for {site_id}")
            power_start = max(target_start, POWER_DAILY_START)
            if pd.Timestamp(power_start) > pd.Timestamp(target_end):
                raise ValueError(f"site predates the entire POWER daily archive: {site_id}")
            site_plans.append(
                CorpusSitePlan(
                    site_id=site_id,
                    target_start=target_start,
                    target_end=target_end,
                    power_start=power_start,
                    longitude=longitude,
                    latitude=latitude,
                )
            )

        payload = _network_plan_payload(
            network_id=network.network_id,
            role=network.role,
            source_key=network.source_key,
            sites=site_plans,
            source_network_manifest_sha256=_sha256_file(manifest_path),
            source_date_projection_sha256=_sha256_bytes(
                dates.sort_values(["site_id", "date"])
                .to_csv(index=False)
                .encode("utf-8")
            ),
        )
        network_plan_sha256 = _sha256_bytes(_canonical_json(payload).encode())
        plans.append(
            CorpusNetworkPlan(
                network_id=network.network_id,
                role=network.role,
                source_key=network.source_key,
                sites=tuple(site_plans),
                source_network_manifest_sha256=payload[
                    "source_network_manifest_sha256"
                ],
                source_date_projection_sha256=payload[
                    "source_date_projection_sha256"
                ],
                split_sha256=SPLIT_SHA256,
                network_plan_sha256=network_plan_sha256,
            )
        )

    plans.sort(key=lambda value: (value.role, value.network_id))
    corpus_payload = {
        "manifest_schema": PLAN_SCHEMA_VERSION,
        "split_sha256": SPLIT_SHA256,
        "qualification_mode": "failure_closure6",
        "n_networks": len(plans),
        "n_sites": sum(len(network.sites) for network in plans),
        "networks": [asdict(network) for network in plans],
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "performance_metrics_computed": False,
    }
    plan_sha256 = _sha256_bytes(_canonical_json(corpus_payload).encode())
    return CorpusAcquisitionPlan(tuple(plans), SPLIT_SHA256, plan_sha256)


def plan_as_dict(plan: CorpusAcquisitionPlan) -> dict[str, Any]:
    result = {
        "manifest_schema": PLAN_SCHEMA_VERSION,
        "split_sha256": plan.split_sha256,
        "qualification_mode": "failure_closure6",
        "n_networks": len(plan.networks),
        "n_sites": sum(len(network.sites) for network in plan.networks),
        "networks": [asdict(network) for network in plan.networks],
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "performance_metrics_computed": False,
        "plan_sha256": plan.plan_sha256,
    }
    without_hash = dict(result)
    without_hash.pop("plan_sha256")
    if _sha256_bytes(_canonical_json(without_hash).encode()) != plan.plan_sha256:
        raise AssertionError("corpus acquisition plan hash is not reproducible")
    return result


def _protocol(
    network: CorpusNetworkPlan,
    site: CorpusSitePlan,
    *,
    start: str,
    end: str,
) -> provider.ConfirmatoryProtocol:
    return provider.ConfirmatoryProtocol(
        design_path="configs/design_freeze_v9.yaml",
        design_sha256="bound_by_failure_closure_and_network_plan_sha256",
        design_version="design_freeze_v9.1_information_corpus_acquisition",
        network=network.network_id,
        site_ids=(site.site_id,),
        periods=(provider.SplitPeriod("open_role_request_window", start, end),),
        quality_rule="POWER finite non-fill; USGS Approved only; provisional excluded",
        nasa_community="AG",
        nasa_time_standard="UTC",
        nasa_spatial_rule="nearest_POWER_grid_cell_to_each_USGS_site_coordinate",
        rs_interpretation=provider.RS_INTERPRETATION,
        network_huc8=(network.network_id.removeprefix("huc8_"),),
    )


def build_network_request_plan(network: CorpusNetworkPlan) -> dict[str, Any]:
    requests: list[dict[str, Any]] = []
    for site in network.sites:
        hydro_protocol = _protocol(
            network, site, start=site.target_start, end=site.target_end
        )
        for spec in provider.HYDROLOGY_SPECS[1:]:
            requests.extend(
                [
                    {
                        "provider": "usgs_ogc_daily",
                        "request_kind": "time_series_metadata",
                        "site_id": site.site_id,
                        "variable": spec.variable,
                        "start": site.target_start,
                        "end": site.target_end,
                        "url": provider._usgs_time_series_url(site.site_id, spec),
                    },
                    {
                        "provider": "usgs_ogc_daily",
                        "request_kind": "daily_values",
                        "site_id": site.site_id,
                        "variable": spec.variable,
                        "start": site.target_start,
                        "end": site.target_end,
                        "url": provider._usgs_daily_url(
                            site.site_id, spec, hydro_protocol
                        ),
                    },
                ]
            )
        power_protocol = _protocol(
            network, site, start=site.power_start, end=site.target_end
        )
        requests.append(
            {
                "provider": "nasa_power_daily_point",
                "request_kind": "daily_point_meteorology",
                "site_id": site.site_id,
                "variable": None,
                "start": site.power_start,
                "end": site.target_end,
                "longitude": site.longitude,
                "latitude": site.latitude,
                "url": provider._nasa_power_url(
                    site.longitude, site.latitude, power_protocol
                ),
            }
        )
    result = {
        "manifest_schema": "t2_v91_open_role_mh_network_request_plan_v1",
        "network_id": network.network_id,
        "role": network.role,
        "split_sha256": network.split_sha256,
        "network_plan_sha256": network.network_plan_sha256,
        "n_sites": len(network.sites),
        "n_initial_requests": len(requests),
        "requests": requests,
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "performance_metrics_computed": False,
    }
    result["request_plan_sha256"] = _sha256_bytes(_canonical_json(result).encode())
    return result


def select_networks(
    plan: CorpusAcquisitionPlan,
    *,
    network_ids: Sequence[str] = (),
    max_networks: int | None = None,
    all_networks: bool = False,
) -> tuple[CorpusNetworkPlan, ...]:
    """Resolve one explicit, deterministic bounded/all selection."""

    modes = int(bool(network_ids)) + int(max_networks is not None) + int(all_networks)
    if modes > 1:
        raise ValueError("choose only one of network_ids, max_networks, or all_networks")
    roster = {network.network_id: network for network in plan.networks}
    if network_ids:
        requested = set(network_ids)
        missing = requested.difference(roster)
        if missing:
            raise ValueError(f"requested networks are outside the frozen roster: {sorted(missing)}")
        return tuple(network for network in plan.networks if network.network_id in requested)
    if max_networks is not None:
        if max_networks < 1 or max_networks > len(plan.networks):
            raise ValueError("max_networks must be between 1 and the frozen roster size")
        return plan.networks[: int(max_networks)]
    if all_networks:
        return plan.networks
    return plan.networks


class RateLimitedFetcher:
    """Serialize provider calls with a minimum start-to-start interval."""

    def __init__(
        self,
        fetcher: provider.HTTPFetcher,
        interval_seconds: float,
    ) -> None:
        if interval_seconds < 0:
            raise ValueError("request interval cannot be negative")
        self.fetcher = fetcher
        self.interval_seconds = float(interval_seconds)
        self._last_started: float | None = None

    def __call__(self, url: str, headers: dict[str, str]) -> provider.HTTPResponse:
        now = time.monotonic()
        if self._last_started is not None:
            delay = self.interval_seconds - (now - self._last_started)
            if delay > 0:
                time.sleep(delay)
        self._last_started = time.monotonic()
        return self.fetcher(url, headers)


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


def _validate_provider_qc(daily: pd.DataFrame) -> None:
    if daily.empty:
        return
    variables = set(daily["variable"].astype(str))
    forbidden = variables.difference((*METEOROLOGY_VARIABLES, *HYDRAULICS_VARIABLES))
    if forbidden or "T" in variables or "temperature_c" in daily.columns:
        raise ValueError(f"non-M/H variable reached auxiliary output: {sorted(forbidden)}")
    values = pd.to_numeric(daily["value"], errors="coerce")
    natural = daily["natural_observed"].astype(bool)
    approved = daily["quality_approved"].astype(bool)
    meteorology = daily["variable"].isin(METEOROLOGY_VARIABLES)
    hydraulics = daily["variable"].isin(HYDRAULICS_VARIABLES)
    power_eligible = meteorology & natural
    if values[power_eligible].isna().any() or approved[power_eligible].eq(False).any():
        raise ValueError("eligible POWER rows must be finite provider-screened values")
    if values[meteorology & ~natural].notna().any():
        raise ValueError("POWER provider fill rows must remain NA")
    usgs_eligible = hydraulics & natural & approved
    if values[usgs_eligible].isna().any():
        raise ValueError("approved USGS hydraulic rows must be finite")
    rejected_h = hydraulics & ~usgs_eligible
    if values[rejected_h].notna().any():
        raise ValueError("non-approved USGS hydraulic rows must remain NA")
    if not daily.loc[hydraulics, "approval_status"].isin(
        ["Approved", "Provisional"]
    ).all():
        raise ValueError("USGS hydraulics contain an unexpected approval status")


def _coverage(
    network: CorpusNetworkPlan,
    daily: pd.DataFrame,
    failures: Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    failed = {(str(row["site_id"]), str(row["variable"])) for row in failures}
    rows: list[dict[str, Any]] = []
    for site in network.sites:
        for variable in (*METEOROLOGY_VARIABLES, *HYDRAULICS_VARIABLES):
            request_start = (
                site.power_start if variable in METEOROLOGY_VARIABLES else site.target_start
            )
            expected_days = len(pd.date_range(request_start, site.target_end, freq="D"))
            target_days = len(pd.date_range(site.target_start, site.target_end, freq="D"))
            subset = daily.loc[
                daily.get("site_id", pd.Series(dtype=str)).astype(str).eq(site.site_id)
                & daily.get("variable", pd.Series(dtype=str)).astype(str).eq(variable)
            ]
            eligible = subset.get(
                "natural_observed", pd.Series(False, index=subset.index)
            ).astype(bool)
            if variable in HYDRAULICS_VARIABLES:
                eligible &= subset.get(
                    "quality_approved", pd.Series(False, index=subset.index)
                ).astype(bool)
            rows.append(
                {
                    "network_id": network.network_id,
                    "role": network.role,
                    "site_id": site.site_id,
                    "variable": variable,
                    "information_group": (
                        "M" if variable in METEOROLOGY_VARIABLES else "H"
                    ),
                    "target_start": site.target_start,
                    "request_start": request_start,
                    "request_end": site.target_end,
                    "n_target_calendar_days": target_days,
                    "n_expected_provider_days": expected_days,
                    "n_provider_rows": len(subset),
                    "n_provider_eligible_rows": int(eligible.sum()),
                    "provider_row_coverage": len(subset) / expected_days,
                    "eligible_coverage": int(eligible.sum()) / expected_days,
                    "pre_power_archive_days": max(0, target_days - expected_days),
                    "source_status": (
                        "failed_or_unavailable"
                        if (site.site_id, variable) in failed
                        else "materialized"
                    ),
                }
            )
    return pd.DataFrame(rows)


def _network_output(root: Path, network: CorpusNetworkPlan) -> Path:
    return root / network.role / "networks" / network.network_id


def _validate_terminal_manifest(
    repository_root: Path,
    output: Path,
    network: CorpusNetworkPlan,
) -> dict[str, Any] | None:
    manifest_path = output / "network_manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("manifest_schema") != NETWORK_SCHEMA_VERSION
        or manifest.get("network_plan_sha256") != network.network_plan_sha256
        or manifest.get("network_id") != network.network_id
        or manifest.get("role") != network.role
        or manifest.get("sealed_temperature_records_read") is not False
    ):
        raise ValueError(f"existing network manifest is not a valid resume boundary: {output}")
    if manifest.get("status") == RETRY_STATUS:
        return None
    if manifest.get("status") not in TERMINAL_STATUSES:
        raise ValueError(f"existing network manifest has an unknown status: {output}")
    for artifact in (manifest.get("artifacts") or {}).values():
        path = repository_root / str(artifact["path"])
        if not path.is_file() or _sha256_file(path) != artifact.get("sha256"):
            raise ValueError(f"resume artifact integrity failure: {path}")
    records_path = output / "raw_request_log.json"
    records = json.loads(records_path.read_text(encoding="utf-8"))
    for record in records:
        response = output / str(record["response_artifact"])
        if not response.is_file() or _sha256_file(response) != record.get(
            "response_sha256"
        ):
            raise ValueError(f"resume raw response integrity failure: {response}")
    return manifest


def acquire_network(
    repository_root: str | Path,
    corpus_output_root: str | Path,
    network: CorpusNetworkPlan,
    *,
    fetcher: provider.HTTPFetcher = provider.urlopen_fetcher,
    usgs_api_key: str | None = None,
    resume: bool = True,
) -> tuple[dict[str, Any], bool]:
    """Acquire one network; return its manifest and whether it was resumed."""

    root = Path(repository_root).resolve()
    corpus_output = Path(corpus_output_root).resolve()
    output = _network_output(corpus_output, network)
    output.mkdir(parents=True, exist_ok=True)
    existing = _validate_terminal_manifest(root, output, network)
    if existing is not None:
        if not resume:
            raise FileExistsError(f"terminal network output already exists: {output}")
        return existing, True

    request_plan = build_network_request_plan(network)
    request_plan_path = output / "request_plan.json"
    _write_json(request_plan_path, request_plan)
    raw_root = output / "raw"
    daily_frames: list[pd.DataFrame] = []
    series_frames: list[pd.DataFrame] = []
    power_metadata_frames: list[pd.DataFrame] = []
    request_records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for site in network.sites:
        hydro_protocol = _protocol(
            network, site, start=site.target_start, end=site.target_end
        )
        for spec in provider.HYDROLOGY_SPECS[1:]:
            try:
                series_result = provider.fetch_ogc_feature_collection(
                    provider._usgs_time_series_url(site.site_id, spec),
                    request_kind="time_series_metadata",
                    site_id=site.site_id,
                    variable=spec.variable,
                    raw_root=raw_root,
                    artifact_prefix=(
                        Path("usgs") / "time_series_metadata" / site.site_id / spec.variable
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
                    provider._usgs_daily_url(site.site_id, spec, hydro_protocol),
                    request_kind="daily_values",
                    site_id=site.site_id,
                    variable=spec.variable,
                    raw_root=raw_root,
                    artifact_prefix=Path("usgs") / "daily" / site.site_id / spec.variable,
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
                        start=site.target_start,
                        end=site.target_end,
                    )
                )
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

        power_protocol = _protocol(
            network, site, start=site.power_start, end=site.target_end
        )
        try:
            meteorology, point_metadata, record = provider._fetch_power_document(
                site_id=site.site_id,
                longitude=site.longitude,
                latitude=site.latitude,
                protocol=power_protocol,
                raw_root=raw_root,
                fetcher=fetcher,
            )
            daily_frames.append(meteorology)
            power_metadata_frames.append(point_metadata)
            request_records.append(record)
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

    daily = pd.concat(daily_frames, ignore_index=True) if daily_frames else _empty_daily()
    if not daily.empty:
        daily = daily.sort_values(["site_id", "date", "variable"]).reset_index(drop=True)
    _validate_provider_qc(daily)
    coverage = _coverage(network, daily, failures)
    series = pd.concat(series_frames, ignore_index=True) if series_frames else pd.DataFrame()
    power_metadata = (
        pd.concat(power_metadata_frames, ignore_index=True)
        if power_metadata_frames
        else pd.DataFrame()
    )

    paths = {
        "daily_long_auxiliary": output / "daily_long_auxiliary.parquet",
        "coverage": output / "coverage.csv",
        "usgs_time_series_metadata": output / "usgs_time_series_metadata.csv",
        "power_point_metadata": output / "power_point_metadata.csv",
        "raw_request_log": output / "raw_request_log.json",
        "source_failures": output / "source_failures.json",
        "adapter_schema": output / "adapter_schema.json",
        "request_plan": request_plan_path,
    }
    daily.to_parquet(paths["daily_long_auxiliary"], index=False)
    coverage.to_csv(paths["coverage"], index=False)
    series.to_csv(paths["usgs_time_series_metadata"], index=False)
    power_metadata.to_csv(paths["power_point_metadata"], index=False)
    _write_json(paths["raw_request_log"], request_records)
    _write_json(paths["source_failures"], failures)
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
        "variables": {"M": list(METEOROLOGY_VARIABLES), "H": list(HYDRAULICS_VARIABLES)},
        "value_role": "M_or_H_covariate_only_never_temperature_target",
        "power_archive_start": POWER_DAILY_START,
        "power_fill_policy": "natural_observed_false_value_NA_qc_provider_fill_value",
        "usgs_provisional_policy": "quality_approved_false_value_NA_qc_excluded_provisional",
        "missing_source_policy": "record_failure_and_leave_absent_no_fill",
    }
    _write_json(paths["adapter_schema"], adapter_schema)
    artifacts = {name: _artifact_record(path, root) for name, path in paths.items()}
    raw_hashes = [
        str(record["response_sha256"])
        for record in request_records
        if record.get("response_sha256")
    ]
    has_retriable_failure = any(
        row["status"] == "source_fetch_or_parse_failed" for row in failures
    )
    status = (
        RETRY_STATUS
        if has_retriable_failure
        else "materialized_complete"
        if not failures
        else "materialized_partial"
    )
    manifest = {
        "manifest_schema": NETWORK_SCHEMA_VERSION,
        "status": status,
        "acquisition_terminal": status in TERMINAL_STATUSES,
        "network_id": network.network_id,
        "role": network.role,
        "source_key": network.source_key,
        "split_sha256": network.split_sha256,
        "network_plan_sha256": network.network_plan_sha256,
        "n_sites": len(network.sites),
        "site_ids": [site.site_id for site in network.sites],
        "station_request_windows": [asdict(site) for site in network.sites],
        "n_auxiliary_rows": len(daily),
        "n_source_failures_or_unavailable": len(failures),
        "source_failure_status_counts": dict(
            sorted(Counter(str(row["status"]) for row in failures).items())
        ),
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
        "purpose": "auxiliary_corpus_materialization_not_performance_evidence",
        "passed": False,
    }
    _write_json(output / "network_manifest.json", manifest)
    # Verify terminal boundaries exactly as a future resume would.  Transport
    # or parser failures remain explicitly retriable and are never skipped.
    checked = _validate_terminal_manifest(root, output, network)
    if status in TERMINAL_STATUSES and checked is None:
        raise AssertionError("network manifest did not form a resume boundary")
    return manifest, False


def _network_attrition_row(
    repository_root: Path,
    corpus_output: Path,
    network: CorpusNetworkPlan,
) -> dict[str, Any]:
    output = _network_output(corpus_output, network)
    manifest_path = output / "network_manifest.json"
    base: dict[str, Any] = {
        "network_id": network.network_id,
        "role": network.role,
        "n_sites_planned": len(network.sites),
        "network_plan_sha256": network.network_plan_sha256,
        "materialization_status": "not_materialized",
        "n_auxiliary_rows": 0,
        "n_source_failures_or_unavailable": 0,
        "n_M_cells_materialized": 0,
        "n_H_cells_materialized": 0,
        "n_M_cells_failed_or_unavailable": 0,
        "n_H_cells_failed_or_unavailable": 0,
        "mean_M_eligible_coverage": np.nan,
        "mean_H_eligible_coverage": np.nan,
        "all_raw_response_hashes_complete": False,
    }
    if not manifest_path.is_file():
        return base
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = _validate_terminal_manifest(repository_root, output, network)
    if manifest is None:
        if raw_manifest.get("status") != RETRY_STATUS:
            return base
        manifest = raw_manifest
    coverage = pd.read_csv(output / "coverage.csv")
    base.update(
        {
            "materialization_status": manifest["status"],
            "n_auxiliary_rows": int(manifest["n_auxiliary_rows"]),
            "n_source_failures_or_unavailable": int(
                manifest["n_source_failures_or_unavailable"]
            ),
            "n_M_cells_materialized": int(
                ((coverage["information_group"] == "M") & (coverage["source_status"] == "materialized")).sum()
            ),
            "n_H_cells_materialized": int(
                ((coverage["information_group"] == "H") & (coverage["source_status"] == "materialized")).sum()
            ),
            "n_M_cells_failed_or_unavailable": int(
                ((coverage["information_group"] == "M") & (coverage["source_status"] != "materialized")).sum()
            ),
            "n_H_cells_failed_or_unavailable": int(
                ((coverage["information_group"] == "H") & (coverage["source_status"] != "materialized")).sum()
            ),
            "mean_M_eligible_coverage": float(
                coverage.loc[coverage["information_group"] == "M", "eligible_coverage"].mean()
            ),
            "mean_H_eligible_coverage": float(
                coverage.loc[coverage["information_group"] == "H", "eligible_coverage"].mean()
            ),
            "all_raw_response_hashes_complete": bool(
                manifest["raw_response_hashes_complete_for_logged_responses"]
            ),
        }
    )
    return base


def write_global_attrition(
    repository_root: str | Path,
    corpus_output_root: str | Path,
    plan: CorpusAcquisitionPlan,
) -> tuple[Path, Path, dict[str, Any]]:
    root = Path(repository_root).resolve()
    output = Path(corpus_output_root).resolve()
    rows = [_network_attrition_row(root, output, network) for network in plan.networks]
    frame = pd.DataFrame(rows)
    csv_path = output / "global_attrition.csv"
    frame.to_csv(csv_path, index=False)
    materialized = frame["materialization_status"].isin(TERMINAL_STATUSES)
    summary = {
        "manifest_schema": "t2_v91_open_role_mh_global_attrition_v1",
        "plan_sha256": plan.plan_sha256,
        "split_sha256": plan.split_sha256,
        "n_networks_planned": len(frame),
        "n_sites_planned": sum(len(network.sites) for network in plan.networks),
        "n_networks_materialized": int(materialized.sum()),
        "n_networks_remaining": int((~materialized).sum()),
        "materialization_status_counts": dict(
            sorted(frame["materialization_status"].value_counts().astype(int).items())
        ),
        "n_source_failures_or_unavailable": int(
            frame["n_source_failures_or_unavailable"].sum()
        ),
        "n_M_cells_failed_or_unavailable": int(
            frame["n_M_cells_failed_or_unavailable"].sum()
        ),
        "n_H_cells_failed_or_unavailable": int(
            frame["n_H_cells_failed_or_unavailable"].sum()
        ),
        "all_materialized_raw_response_hashes_complete": bool(
            materialized.any()
            and frame.loc[materialized, "all_raw_response_hashes_complete"].all()
        ),
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "performance_metrics_computed": False,
        "formal_evidence": False,
        "passed": False,
    }
    summary_path = output / "global_attrition_summary.json"
    _write_json(summary_path, summary)
    return csv_path, summary_path, summary


def run_corpus_acquisition(
    repository_root: str | Path,
    output_root: str | Path,
    *,
    execute: bool = False,
    network_ids: Sequence[str] = (),
    max_networks: int | None = None,
    all_networks: bool = False,
    acknowledged_network_count: int | None = None,
    acknowledge_all_network_count: int | None = None,
    resume: bool = True,
    request_interval_seconds: float = 1.0,
    fetcher: provider.HTTPFetcher = provider.urlopen_fetcher,
    usgs_api_key: str | None = None,
) -> dict[str, Any]:
    """Plan or execute an explicitly acknowledged sequential acquisition."""

    root = Path(repository_root).resolve()
    output = Path(output_root).resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan = load_corpus_plan(root)
    selected = select_networks(
        plan,
        network_ids=network_ids,
        max_networks=max_networks,
        all_networks=all_networks,
    )
    if execute:
        if all_networks:
            if acknowledge_all_network_count != len(plan.networks):
                raise ValueError(
                    f"all-network execution requires --acknowledge-all-network-count {len(plan.networks)}"
                )
            if acknowledged_network_count is not None:
                raise ValueError("bounded and all-network acknowledgements cannot be combined")
        else:
            if not network_ids and max_networks is None:
                raise ValueError("execution requires an explicit bounded selection or --all")
            if acknowledged_network_count != len(selected):
                raise ValueError(
                    f"bounded execution requires --acknowledge-network-count {len(selected)}"
                )
            if acknowledge_all_network_count is not None:
                raise ValueError("bounded and all-network acknowledgements cannot be combined")

    plan_path = output / "corpus_request_plan.json"
    _write_json(plan_path, plan_as_dict(plan))
    selected_plan = {
        "manifest_schema": "t2_v91_open_role_mh_selected_run_plan_v1",
        "corpus_plan_sha256": plan.plan_sha256,
        "execute": execute,
        "selection_mode": (
            "all"
            if all_networks
            else "network_ids"
            if network_ids
            else "max_networks"
            if max_networks is not None
            else "dry_run_full_roster"
        ),
        "selected_network_ids": [network.network_id for network in selected],
        "n_networks_selected": len(selected),
        "scope_acknowledgement": {
            "mode": "all" if all_networks else "bounded" if execute else "not_required_dry_run",
            "expected_network_count": len(selected),
            "acknowledged_network_count": (
                acknowledge_all_network_count
                if all_networks
                else acknowledged_network_count
                if execute
                else None
            ),
        },
        "sequential_execution": True,
        "request_interval_seconds": float(request_interval_seconds),
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "performance_metrics_computed": False,
    }
    selected_plan["selected_plan_sha256"] = _sha256_bytes(
        _canonical_json(selected_plan).encode()
    )
    selected_path = output / "selected_run_plan.json"
    _write_json(selected_path, selected_plan)

    results: list[dict[str, Any]] = []
    if execute:
        limited_fetcher = RateLimitedFetcher(fetcher, request_interval_seconds)
        for network in selected:
            manifest, resumed = acquire_network(
                root,
                output,
                network,
                fetcher=limited_fetcher,
                usgs_api_key=usgs_api_key,
                resume=resume,
            )
            results.append(
                {
                    "network_id": network.network_id,
                    "role": network.role,
                    "status": manifest["status"],
                    "resumed": resumed,
                    "n_source_failures_or_unavailable": manifest[
                        "n_source_failures_or_unavailable"
                    ],
                }
            )

    attrition_path, attrition_summary_path, attrition = write_global_attrition(
        root, output, plan
    )
    status = "dry_run" if not execute else "execution_complete_for_selected_scope"
    run_manifest = {
        "manifest_schema": CORPUS_SCHEMA_VERSION,
        "status": status,
        "execute": execute,
        "dry_run": not execute,
        "corpus_plan_sha256": plan.plan_sha256,
        "selected_plan_sha256": selected_plan["selected_plan_sha256"],
        "split_sha256": plan.split_sha256,
        "n_networks_in_frozen_roster": len(plan.networks),
        "n_sites_in_frozen_roster": sum(len(network.sites) for network in plan.networks),
        "n_networks_selected": len(selected),
        "selected_network_ids": [network.network_id for network in selected],
        "n_networks_executed_now": sum(not row["resumed"] for row in results),
        "n_networks_resumed": sum(row["resumed"] for row in results),
        "scope_acknowledgement": selected_plan["scope_acknowledgement"],
        "sequential_execution": True,
        "parallel_workers": 1,
        "request_interval_seconds": float(request_interval_seconds),
        "results": results,
        "global_attrition": attrition,
        "artifacts": {
            "corpus_request_plan": _artifact_record(plan_path, root),
            "selected_run_plan": _artifact_record(selected_path, root),
            "global_attrition": _artifact_record(attrition_path, root),
            "global_attrition_summary": _artifact_record(attrition_summary_path, root),
        },
        "provider_responses_opened": execute and any(not row["resumed"] for row in results),
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "performance_metrics_computed": False,
        "network_interval_reported": False,
        "formal_evidence": False,
        "purpose": "auxiliary_corpus_materialization_not_performance_evidence",
        "passed": False,
    }
    _write_json(output / "run_manifest.json", run_manifest)
    return run_manifest


__all__ = [
    "CORPUS_SCHEMA_VERSION",
    "EXPECTED_NETWORKS",
    "NETWORK_SCHEMA_VERSION",
    "CorpusAcquisitionPlan",
    "CorpusNetworkPlan",
    "CorpusSitePlan",
    "RateLimitedFetcher",
    "acquire_network",
    "build_network_request_plan",
    "load_corpus_plan",
    "plan_as_dict",
    "run_corpus_acquisition",
    "select_networks",
    "write_global_attrition",
]

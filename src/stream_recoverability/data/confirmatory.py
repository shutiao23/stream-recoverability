"""Immutable acquisition and preparation of the frozen confirmatory data.

The builder implements the external protocol in ``design_freeze_v1.yaml``.  It
uses the modern USGS OGC API and the NASA POWER daily point API, records every
non-secret request and raw response by SHA-256, and materialises no performance
metrics. Full acquisition is deliberately gated by a hash-verified finalized
model-roster manifest produced from validation-only evidence.

Official API documentation:

* https://api.waterdata.usgs.gov/docs/ogcapi/
* https://power.larc.nasa.gov/docs/services/api/temporal/daily/
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
import pandas as pd
import yaml

from stream_recoverability.experiments.contracts import build_design_contract

from .prepare import TIME_FEATURE_COLUMNS, add_time_features

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONFIRMATORY_DATA_VERSION = "external_lower_chattahoochee_v1"
CONFIRMATORY_SCHEMA_VERSION = "confirmatory_external_data_v1"
REQUEST_PLAN_SCHEMA_VERSION = "confirmatory_request_plan_v1"
REQUEST_LOG_SCHEMA_VERSION = "external_http_request_log_v1"
FINALIZED_MODEL_ROSTER_SCHEMA_VERSION = "finalized_model_roster_v1"
DEFAULT_SELECTION_DATA_VERSION = "published_v1"
FINALIST_ARTIFACT_NAMES = ("ranking", "stage2_selection", "go_no_go")
FINALIZED_MODEL_ROSTER_FIELDS = frozenset(
    {
        "schema_version",
        "finalized",
        "evaluation_split",
        "evidence_role",
        "formal_evidence",
        "selected_models",
        "best_traditional_model",
        "proposed_decision",
        "artifacts",
    }
)

USGS_OGC_BASE = "https://api.waterdata.usgs.gov/ogcapi/v0/collections"
NASA_POWER_DAILY_POINT_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
USGS_OGC_DOCUMENTATION = "https://api.waterdata.usgs.gov/docs/ogcapi/"
NASA_POWER_DOCUMENTATION = (
    "https://power.larc.nasa.gov/docs/services/api/temporal/daily/"
)
HTTP_USER_AGENT = "stream-recoverability-confirmatory-builder/1.0"
USGS_PAGE_LIMIT = 10_000
MAX_OGC_PAGES = 10_000

FROZEN_SITE_IDS = (
    "02334430",
    "02335000",
    "02335450",
    "02336000",
    "02337170",
)
FROZEN_VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "DH")
FROZEN_HYDROLOGY = (
    ("T", "00010", "00003"),
    ("F", "00060", "00003"),
    ("L", "00065", "00003"),
)
FROZEN_METEOROLOGY = (
    ("Ta", "T2M"),
    ("P", "PRECTOTCORR"),
    ("W", "WS2M"),
    ("RH", "RH2M"),
    ("DH", "ALLSKY_SFC_SW_DWN"),
)
FROZEN_PERIODS = (
    ("train", "2012-01-01", "2020-12-31"),
    ("validation", "2021-01-01", "2022-12-31"),
    ("confirmatory", "2023-01-01", "2025-12-31"),
)
FROZEN_QUALITY_RULE = "retain_approved_and_estimated_flagged_values_exclude_provisional"
DH_INTERPRETATION = "daily_shortwave_radiation_proxy_not_sunshine_duration"

FT3_S_TO_M3_S = 0.028316846592
FT_TO_M = 0.3048


@dataclass(frozen=True)
class ExternalVariableSpec:
    variable: str
    provider: str
    provider_code: str
    statistic_id: str | None
    source_unit: str
    unit: str
    conversion_factor: float
    conversion_formula: str
    interpretation: str


HYDROLOGY_SPECS = (
    ExternalVariableSpec(
        "T",
        "usgs_ogc_daily",
        "00010",
        "00003",
        "deg C",
        "degC",
        1.0,
        "identity",
        "daily_mean_water_temperature",
    ),
    ExternalVariableSpec(
        "F",
        "usgs_ogc_daily",
        "00060",
        "00003",
        "ft^3/s",
        "m3/s",
        FT3_S_TO_M3_S,
        "m3_per_s = ft3_per_s * 0.028316846592",
        "daily_mean_discharge",
    ),
    ExternalVariableSpec(
        "L",
        "usgs_ogc_daily",
        "00065",
        "00003",
        "ft",
        "m",
        FT_TO_M,
        "m = ft * 0.3048",
        "daily_mean_gage_height",
    ),
)
METEOROLOGY_SPECS = (
    ExternalVariableSpec(
        "Ta",
        "nasa_power_daily_point",
        "T2M",
        None,
        "C",
        "degC",
        1.0,
        "identity",
        "daily_air_temperature_at_2_m",
    ),
    ExternalVariableSpec(
        "P",
        "nasa_power_daily_point",
        "PRECTOTCORR",
        None,
        "mm/day",
        "mm/day",
        1.0,
        "identity",
        "daily_corrected_precipitation",
    ),
    ExternalVariableSpec(
        "W",
        "nasa_power_daily_point",
        "WS2M",
        None,
        "m/s",
        "m/s",
        1.0,
        "identity",
        "daily_wind_speed_at_2_m",
    ),
    ExternalVariableSpec(
        "RH",
        "nasa_power_daily_point",
        "RH2M",
        None,
        "%",
        "%",
        1.0,
        "identity",
        "daily_relative_humidity_at_2_m",
    ),
    ExternalVariableSpec(
        "DH",
        "nasa_power_daily_point",
        "ALLSKY_SFC_SW_DWN",
        None,
        "MJ/m^2/day",
        "MJ/m^2/day",
        1.0,
        "identity",
        DH_INTERPRETATION,
    ),
)
VARIABLE_SPECS = HYDROLOGY_SPECS + METEOROLOGY_SPECS
VARIABLE_SPEC_BY_NAME = {spec.variable: spec for spec in VARIABLE_SPECS}


@dataclass(frozen=True)
class SplitPeriod:
    label: str
    start: str
    end: str


@dataclass(frozen=True)
class ConfirmatoryProtocol:
    design_path: str
    design_sha256: str
    design_version: str
    network: str
    site_ids: tuple[str, ...]
    periods: tuple[SplitPeriod, ...]
    quality_rule: str
    nasa_community: str
    nasa_time_standard: str
    nasa_spatial_rule: str
    dh_interpretation: str

    @property
    def start(self) -> str:
        return self.periods[0].start

    @property
    def end(self) -> str:
        return self.periods[-1].end

    def metadata(self) -> dict[str, Any]:
        result = asdict(self)
        result["hydrology"] = [asdict(spec) for spec in HYDROLOGY_SPECS]
        result["meteorology"] = [asdict(spec) for spec in METEOROLOGY_SPECS]
        result["variables"] = list(FROZEN_VARIABLES)
        result["data_version"] = CONFIRMATORY_DATA_VERSION
        return result


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_json_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _expect_equal(actual: Any, expected: Any, path: str) -> None:
    if actual != expected:
        raise ValueError(
            f"design freeze mismatch at {path}: expected {expected!r}, found {actual!r}"
        )


def _portable_path(path: Path) -> str:
    """Use a clone-stable repository path when the design is in this checkout."""

    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPOSITORY_ROOT.resolve()))
    except ValueError:
        return str(resolved)


def load_confirmatory_protocol(
    design_path: str | Path = "configs/design_freeze_v1.yaml",
) -> ConfirmatoryProtocol:
    """Load and strictly validate the frozen external-data protocol."""

    path = Path(design_path)
    if not path.is_file():
        raise FileNotFoundError(f"design freeze not found: {path}")
    raw = path.read_bytes()
    document = yaml.safe_load(raw)
    if not isinstance(document, Mapping):
        raise TypeError("design freeze must contain a mapping")
    _expect_equal(document.get("design_version"), "design_freeze_v1", "design_version")
    dataset = document.get("confirmatory_dataset")
    if not isinstance(dataset, Mapping):
        raise TypeError("design freeze must contain confirmatory_dataset")
    _expect_equal(dataset.get("status"), "pending", "confirmatory_dataset.status")
    _expect_equal(
        dataset.get("access_rule"),
        "evaluate_once_after_protocol_and_finalists_are_frozen",
        "confirmatory_dataset.access_rule",
    )
    protocol = dataset.get("frozen_external_protocol")
    if not isinstance(protocol, Mapping):
        raise TypeError("confirmatory_dataset must contain frozen_external_protocol")
    _expect_equal(
        protocol.get("provider"),
        "usgs_water_services",
        "frozen_external_protocol.provider",
    )
    _expect_equal(
        protocol.get("network"),
        "lower_chattahoochee_mainstem_case_study",
        "frozen_external_protocol.network",
    )
    _expect_equal(
        tuple(str(value) for value in protocol.get("site_ids", ())),
        FROZEN_SITE_IDS,
        "frozen_external_protocol.site_ids",
    )
    _expect_equal(
        dict(protocol.get("daily_statistics", {})),
        {
            "temperature": "00010:00003",
            "discharge": "00060:00003",
            "level": "00065:00003",
        },
        "frozen_external_protocol.daily_statistics",
    )
    meteorology = protocol.get("meteorology")
    if not isinstance(meteorology, Mapping):
        raise TypeError("frozen external protocol meteorology must be a mapping")
    _expect_equal(
        meteorology.get("provider"),
        "nasa_power_daily_point",
        "frozen_external_protocol.meteorology.provider",
    )
    _expect_equal(
        meteorology.get("community"),
        "AG",
        "frozen_external_protocol.meteorology.community",
    )
    _expect_equal(
        meteorology.get("time_standard"),
        "UTC",
        "frozen_external_protocol.meteorology.time_standard",
    )
    _expect_equal(
        dict(meteorology.get("variables", {})),
        dict(FROZEN_METEOROLOGY),
        "frozen_external_protocol.meteorology.variables",
    )
    _expect_equal(
        meteorology.get("DH_interpretation"),
        DH_INTERPRETATION,
        "frozen_external_protocol.meteorology.DH_interpretation",
    )
    _expect_equal(
        meteorology.get("spatial_rule"),
        "nearest_POWER_grid_cell_to_each_USGS_site_coordinate",
        "frozen_external_protocol.meteorology.spatial_rule",
    )
    for label, start, end in FROZEN_PERIODS:
        _expect_equal(
            dict(protocol.get(label, {})),
            {"start": start, "end": end},
            f"frozen_external_protocol.{label}",
        )
    _expect_equal(
        protocol.get("quality_rule"),
        FROZEN_QUALITY_RULE,
        "frozen_external_protocol.quality_rule",
    )
    return ConfirmatoryProtocol(
        design_path=_portable_path(path),
        design_sha256=_sha256_bytes(raw),
        design_version="design_freeze_v1",
        network="lower_chattahoochee_mainstem_case_study",
        site_ids=FROZEN_SITE_IDS,
        periods=tuple(SplitPeriod(*value) for value in FROZEN_PERIODS),
        quality_rule=FROZEN_QUALITY_RULE,
        nasa_community="AG",
        nasa_time_standard="UTC",
        nasa_spatial_rule="nearest_POWER_grid_cell_to_each_USGS_site_coordinate",
        dh_interpretation=DH_INTERPRETATION,
    )


def _build_url(base: str, query: Sequence[tuple[str, str]]) -> str:
    return f"{base}?{urllib.parse.urlencode(query, safe=',/')}"


def _usgs_monitoring_location_url(site_id: str) -> str:
    return _build_url(
        f"{USGS_OGC_BASE}/monitoring-locations/items",
        (("f", "json"), ("limit", str(USGS_PAGE_LIMIT)), ("id", f"USGS-{site_id}")),
    )


def _usgs_time_series_url(site_id: str, spec: ExternalVariableSpec) -> str:
    return _build_url(
        f"{USGS_OGC_BASE}/time-series-metadata/items",
        (
            ("f", "json"),
            ("limit", str(USGS_PAGE_LIMIT)),
            ("monitoring_location_id", f"USGS-{site_id}"),
            ("parameter_code", spec.provider_code),
            ("statistic_id", cast(str, spec.statistic_id)),
        ),
    )


def _usgs_daily_url(
    site_id: str, spec: ExternalVariableSpec, protocol: ConfirmatoryProtocol
) -> str:
    return _build_url(
        f"{USGS_OGC_BASE}/daily/items",
        (
            ("f", "json"),
            ("limit", str(USGS_PAGE_LIMIT)),
            ("monitoring_location_id", f"USGS-{site_id}"),
            ("parameter_code", spec.provider_code),
            ("statistic_id", cast(str, spec.statistic_id)),
            ("datetime", f"{protocol.start}/{protocol.end}"),
        ),
    )


def _coordinate_string(value: float) -> str:
    if not math.isfinite(float(value)):
        raise ValueError("site coordinates must be finite")
    return repr(float(value))


def _nasa_power_url(
    longitude: float, latitude: float, protocol: ConfirmatoryProtocol
) -> str:
    return _build_url(
        NASA_POWER_DAILY_POINT_URL,
        (
            ("parameters", ",".join(spec.provider_code for spec in METEOROLOGY_SPECS)),
            ("community", protocol.nasa_community),
            ("longitude", _coordinate_string(longitude)),
            ("latitude", _coordinate_string(latitude)),
            ("start", protocol.start.replace("-", "")),
            ("end", protocol.end.replace("-", "")),
            ("format", "JSON"),
            ("time-standard", protocol.nasa_time_standard),
        ),
    )


def _request_identity(url: str, accept: str) -> dict[str, Any]:
    return {
        "method": "GET",
        "url": url,
        "headers": {"Accept": accept, "User-Agent": HTTP_USER_AGENT},
        "secret_fields_excluded": ["X-Api-Key"],
    }


def _planned_request(
    *,
    provider: str,
    request_kind: str,
    site_id: str,
    variable: str | None,
    url: str,
    accept: str,
) -> dict[str, Any]:
    identity = _request_identity(url, accept)
    return {
        "provider": provider,
        "request_kind": request_kind,
        "site_id": site_id,
        "variable": variable,
        "url": url,
        "request_sha256": _canonical_json_sha256(identity),
        "pagination": (
            "follow_server_rel_next_until_absent"
            if provider == "usgs"
            else "not_applicable"
        ),
    }


def build_confirmatory_request_plan(
    protocol: ConfirmatoryProtocol,
) -> dict[str, Any]:
    """Return the frozen initial requests without making network calls."""

    initial: list[dict[str, Any]] = []
    for site_id in protocol.site_ids:
        initial.append(
            _planned_request(
                provider="usgs",
                request_kind="monitoring_location_metadata",
                site_id=site_id,
                variable=None,
                url=_usgs_monitoring_location_url(site_id),
                accept="application/geo+json",
            )
        )
        for spec in HYDROLOGY_SPECS:
            initial.append(
                _planned_request(
                    provider="usgs",
                    request_kind="time_series_metadata",
                    site_id=site_id,
                    variable=spec.variable,
                    url=_usgs_time_series_url(site_id, spec),
                    accept="application/geo+json",
                )
            )
            initial.append(
                _planned_request(
                    provider="usgs",
                    request_kind="daily_values",
                    site_id=site_id,
                    variable=spec.variable,
                    url=_usgs_daily_url(site_id, spec, protocol),
                    accept="application/geo+json",
                )
            )
        nasa_template = _nasa_power_url(0.0, 0.0, protocol).replace(
            "longitude=0.0&latitude=0.0",
            "longitude={USGS_LONGITUDE}&latitude={USGS_LATITUDE}",
        )
        initial.append(
            _planned_request(
                provider="nasa_power",
                request_kind="daily_point_meteorology",
                site_id=site_id,
                variable=None,
                url=nasa_template,
                accept="application/json",
            )
        )
    plan: dict[str, Any] = {
        "schema_version": REQUEST_PLAN_SCHEMA_VERSION,
        "design_version": protocol.design_version,
        "design_sha256": protocol.design_sha256,
        "data_version": CONFIRMATORY_DATA_VERSION,
        "network": protocol.network,
        "period": {"start": protocol.start, "end": protocol.end},
        "site_ids": list(protocol.site_ids),
        "variables": list(FROZEN_VARIABLES),
        "initial_requests": initial,
        "initial_request_count": len(initial),
        "usgs_paging_rule": (
            "follow the response link whose rel is exactly 'next'; never construct offsets"
        ),
        "credential_rule": (
            "optional USGS key is sent only in X-Api-Key and is never hashed or persisted"
        ),
        "execution_gate": ("hash-verified finalized_model_roster_v1 manifest required"),
        "performance_metrics": "prohibited",
    }
    plan["plan_sha256"] = _canonical_json_sha256(plan)
    return plan


@dataclass(frozen=True)
class HTTPResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes


class HTTPFetcher(Protocol):
    def __call__(self, url: str, headers: Mapping[str, str]) -> HTTPResponse: ...


def urlopen_fetcher(url: str, headers: Mapping[str, str]) -> HTTPResponse:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return HTTPResponse(
                url=response.geturl(),
                status=int(response.status),
                headers={
                    str(key): str(value) for key, value in response.headers.items()
                },
                body=response.read(),
            )
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code} while fetching {url}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"network failure while fetching {url}: {error.reason}"
        ) from error


class _DuplicateJSONKey(ValueError):
    pass


def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(f"raw JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def strict_json_loads(raw: bytes) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_pairs
        )
    except UnicodeDecodeError as error:
        raise ValueError("provider response is not UTF-8 JSON") from error
    except json.JSONDecodeError as error:
        raise ValueError("provider response is not valid JSON") from error


@dataclass(frozen=True)
class FinalizedModelRoster:
    """Validated, immutable authorization to open confirmatory source values."""

    manifest_path: str
    manifest_sha256: str
    selected_models: tuple[str, ...]
    best_traditional_model: str
    proposed_decision: str
    selection_data_version: str
    selection_design_hash: str
    selection_contract: dict[str, Any]
    selection_code_provenance: dict[str, Any] | None
    selection_data_version_manifest: dict[str, Any]
    artifacts: dict[str, dict[str, Any]]

    def metadata(self) -> dict[str, Any]:
        result = asdict(self)
        result["selected_models"] = list(self.selected_models)
        return result


def _resolve_roster_artifact_path(value: str, roster_path: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    repository_candidate = REPOSITORY_ROOT / candidate
    manifest_candidate = roster_path.parent / candidate
    existing = [
        path for path in (repository_candidate, manifest_candidate) if path.is_file()
    ]
    if len(existing) > 1 and existing[0].resolve() != existing[1].resolve():
        raise ValueError(f"ambiguous finalized-roster artifact path: {value}")
    return existing[0] if existing else repository_candidate


def _validated_roster_artifacts(
    value: object, roster_path: Path
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise TypeError("finalized model roster artifacts must be a mapping")
    missing = sorted(set(FINALIST_ARTIFACT_NAMES).difference(value))
    unexpected = sorted(set(value).difference(FINALIST_ARTIFACT_NAMES))
    if missing or unexpected:
        raise ValueError(
            "finalized model roster artifact set is not frozen: "
            f"missing={missing}, unexpected={unexpected}"
        )
    validated: dict[str, dict[str, Any]] = {}
    resolved_paths: set[Path] = set()
    for name in FINALIST_ARTIFACT_NAMES:
        identity = value[name]
        if not isinstance(identity, Mapping):
            raise TypeError(f"finalized roster artifact {name} must be a mapping")
        if set(identity) != {"path", "sha256"}:
            raise ValueError(
                f"finalized roster artifact {name} identity requires only path/sha256"
            )
        raw_path = identity.get("path")
        expected_sha256 = identity.get("sha256")
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError(f"finalized roster artifact {name} requires path")
        if (
            not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_sha256)
        ):
            raise ValueError(
                f"finalized roster artifact {name} requires lowercase SHA-256"
            )
        path = _resolve_roster_artifact_path(raw_path, roster_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"finalized roster artifact {name} does not exist: {path}"
            )
        resolved = path.resolve()
        if resolved in resolved_paths:
            raise ValueError("finalized roster artifacts must be distinct files")
        resolved_paths.add(resolved)
        observed_sha256 = file_sha256(resolved)
        if observed_sha256 != expected_sha256:
            raise ValueError(f"finalized roster artifact {name} SHA-256 does not match")
        validated[name] = {
            "path": _portable_path(resolved),
            "sha256": observed_sha256,
            "bytes": resolved.stat().st_size,
        }
    return validated


def load_finalized_model_roster(
    roster_manifest_path: str | Path,
    *,
    design_path: str | Path = REPOSITORY_ROOT / "configs/design_freeze_v1.yaml",
    study_manifest_path: str | Path = REPOSITORY_ROOT / "study_manifest.yaml",
    experiment_config_path: str | Path = REPOSITORY_ROOT / "configs/experiments.yaml",
    selection_data_version: str = DEFAULT_SELECTION_DATA_VERSION,
    selection_data_version_manifest_path: str | Path | None = None,
) -> FinalizedModelRoster:
    """Validate the validation-only roster before any confirmatory I/O begins."""

    roster_path = Path(roster_manifest_path)
    if not roster_path.is_file():
        raise FileNotFoundError(f"finalized model roster not found: {roster_path}")
    if selection_data_version != DEFAULT_SELECTION_DATA_VERSION:
        raise ValueError("confirmatory selection must be frozen against published_v1")
    version_manifest = (
        Path(selection_data_version_manifest_path)
        if selection_data_version_manifest_path is not None
        else REPOSITORY_ROOT
        / "data_versions"
        / selection_data_version
        / "version_manifest.json"
    )
    if not version_manifest.is_file():
        raise FileNotFoundError(
            "selection data-version manifest is required before confirmatory access: "
            f"{version_manifest}"
        )
    expected_contract = build_design_contract(
        design_path=design_path,
        manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        data_version=selection_data_version,
        evaluation_split="validation",
        data_version_manifest_path=version_manifest,
    )
    raw = roster_path.read_bytes()
    document = strict_json_loads(raw)
    if not isinstance(document, Mapping):
        raise TypeError("finalized model roster must contain a JSON mapping")
    if document.get("schema_version") != FINALIZED_MODEL_ROSTER_SCHEMA_VERSION:
        raise ValueError(
            "finalized model roster schema_version must be "
            f"{FINALIZED_MODEL_ROSTER_SCHEMA_VERSION}"
        )
    canonical_contract = {
        field: value
        for field, value in expected_contract.items()
        if field != "code_provenance"
    }
    frozen_fields = FINALIZED_MODEL_ROSTER_FIELDS | set(canonical_contract)
    allowed_fields = frozen_fields | {"code_provenance"}
    missing_fields = sorted(frozen_fields.difference(document))
    unexpected_fields = sorted(set(document).difference(allowed_fields))
    if missing_fields or unexpected_fields:
        raise ValueError(
            "finalized model roster fields differ from the frozen schema: "
            f"missing={missing_fields}, unexpected={unexpected_fields}"
        )
    if document.get("finalized") is not True:
        raise ValueError("finalized model roster requires finalized=true")
    if document.get("evaluation_split") != "validation":
        raise ValueError("finalized model roster must use evaluation_split=validation")
    if document.get("formal_evidence") is not False:
        raise ValueError("finalized model roster must declare formal_evidence=false")
    if document.get("evidence_role") != "model_selection_only":
        raise ValueError(
            "finalized model roster evidence_role must be model_selection_only"
        )
    mismatches = {
        field: (document.get(field), canonical_contract[field])
        for field in canonical_contract
        if document.get(field) != canonical_contract[field]
    }
    if mismatches:
        raise ValueError(
            f"finalized model roster design/data contract mismatch: {mismatches}"
        )
    selected = document.get("selected_models")
    if not isinstance(selected, list) or not selected:
        raise ValueError("finalized model roster requires non-empty selected_models")
    if not all(
        isinstance(model, str) and model and model.strip() == model
        for model in selected
    ):
        raise TypeError("selected_models must contain normalized non-empty strings")
    if len(set(selected)) != len(selected):
        raise ValueError("selected_models contains duplicates")
    best_traditional = document.get("best_traditional_model")
    if (
        not isinstance(best_traditional, str)
        or not best_traditional
        or best_traditional.strip() != best_traditional
    ):
        raise ValueError("finalized model roster requires best_traditional_model")
    if best_traditional not in selected:
        raise ValueError("best_traditional_model must be included in selected_models")
    decision = document.get("proposed_decision")
    if decision not in {"include_proposed_formally", "framework_only"}:
        raise ValueError("finalized model roster has invalid proposed_decision")
    proposed_selected = "proposed" in selected
    if proposed_selected != (decision == "include_proposed_formally"):
        raise ValueError("selected_models and proposed_decision are inconsistent")
    artifacts = _validated_roster_artifacts(document.get("artifacts"), roster_path)
    raw_provenance = document.get("code_provenance")
    if raw_provenance is not None and not isinstance(raw_provenance, Mapping):
        raise TypeError("finalized model roster code_provenance must be a mapping")
    return FinalizedModelRoster(
        manifest_path=_portable_path(roster_path),
        manifest_sha256=_sha256_bytes(raw),
        selected_models=tuple(selected),
        best_traditional_model=best_traditional,
        proposed_decision=decision,
        selection_data_version=selection_data_version,
        selection_design_hash=expected_contract["design_hash"],
        selection_contract=json.loads(json.dumps(canonical_contract)),
        selection_code_provenance=(
            json.loads(json.dumps(raw_provenance))
            if raw_provenance is not None
            else None
        ),
        selection_data_version_manifest={
            "path": _portable_path(version_manifest),
            "sha256": file_sha256(version_manifest),
            "bytes": version_manifest.stat().st_size,
        },
        artifacts=artifacts,
    )


@dataclass(frozen=True)
class OGCCollectionResult:
    features: tuple[dict[str, Any], ...]
    feature_provenance: tuple[dict[str, Any], ...]
    request_records: tuple[dict[str, Any], ...]


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    normalized = name.lower()
    for key, value in headers.items():
        if str(key).lower() == normalized:
            return str(value)
    return None


def _validate_provider_response(
    response: HTTPResponse, *, expected_host: str, content_types: tuple[str, ...]
) -> None:
    if response.status != 200:
        raise RuntimeError(
            f"provider returned unexpected HTTP status {response.status}"
        )
    parsed = urllib.parse.urlsplit(response.url)
    if parsed.scheme != "https" or parsed.netloc != expected_host:
        raise ValueError(f"provider redirected to unexpected URL {response.url!r}")
    content_type = (_header_value(response.headers, "Content-Type") or "").lower()
    if not any(value in content_type for value in content_types):
        raise ValueError(f"provider returned unexpected content type {content_type!r}")


def _store_http_exchange(
    *,
    url: str,
    accept: str,
    provider: str,
    request_kind: str,
    site_id: str,
    variable: str | None,
    page_number: int,
    raw_root: Path,
    artifact_prefix: Path,
    fetcher: HTTPFetcher,
    api_key: str | None,
) -> tuple[Any, dict[str, Any]]:
    identity = _request_identity(url, accept)
    request_bytes = _canonical_json_bytes(identity)
    request_sha256 = _sha256_bytes(request_bytes)
    stem = f"page_{page_number:04d}"
    request_path = raw_root / artifact_prefix / f"{stem}.request.json"
    response_path = raw_root / artifact_prefix / f"{stem}.response.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_bytes(request_bytes)
    headers = dict(identity["headers"])
    if api_key is not None:
        if not api_key.strip():
            raise ValueError("USGS API key cannot be blank")
        headers["X-Api-Key"] = api_key
    response = fetcher(url, headers)
    expected_host = (
        "api.waterdata.usgs.gov" if provider == "usgs" else "power.larc.nasa.gov"
    )
    expected_types = (
        ("application/geo+json", "application/json")
        if provider == "usgs"
        else ("application/json",)
    )
    _validate_provider_response(
        response, expected_host=expected_host, content_types=expected_types
    )
    response_path.write_bytes(response.body)
    response_sha256 = _sha256_bytes(response.body)
    parsed = strict_json_loads(response.body)
    record = {
        "provider": provider,
        "request_kind": request_kind,
        "site_id": site_id,
        "variable": variable,
        "page_number": page_number,
        "request_url": url,
        "response_url": response.url,
        "request_sha256": request_sha256,
        "response_sha256": response_sha256,
        "request_artifact": str(request_path.relative_to(raw_root.parent)),
        "response_artifact": str(response_path.relative_to(raw_root.parent)),
        "http_status": response.status,
        "content_type": _header_value(response.headers, "Content-Type"),
        "etag": _header_value(response.headers, "ETag"),
        "last_modified": _header_value(response.headers, "Last-Modified"),
        "api_key_header_used": api_key is not None,
    }
    if file_sha256(request_path) != request_sha256:
        raise AssertionError("stored request identity hash changed")
    if file_sha256(response_path) != response_sha256:
        raise AssertionError("stored raw response hash changed")
    return parsed, record


def _validate_next_url(initial_url: str, next_url: str) -> None:
    initial = urllib.parse.urlsplit(initial_url)
    following = urllib.parse.urlsplit(next_url)
    if (
        following.scheme != "https"
        or following.netloc != "api.waterdata.usgs.gov"
        or following.path != initial.path
    ):
        raise ValueError(f"USGS next link escaped the frozen endpoint: {next_url!r}")
    initial_query = urllib.parse.parse_qs(initial.query, keep_blank_values=True)
    next_query = urllib.parse.parse_qs(following.query, keep_blank_values=True)
    for key, expected in initial_query.items():
        if key in {"f", "limit", "offset", "cursor"}:
            continue
        if next_query.get(key) != expected:
            raise ValueError(
                f"USGS next link changed frozen query field {key!r}: {next_url!r}"
            )


def fetch_ogc_feature_collection(
    initial_url: str,
    *,
    request_kind: str,
    site_id: str,
    variable: str | None,
    raw_root: str | Path,
    artifact_prefix: str | Path,
    fetcher: HTTPFetcher = urlopen_fetcher,
    api_key: str | None = None,
) -> OGCCollectionResult:
    """Fetch every page by following the exact server-provided ``rel=next`` URL."""

    raw_root = Path(raw_root)
    prefix = Path(artifact_prefix)
    current_url = initial_url
    visited: set[str] = set()
    features: list[dict[str, Any]] = []
    feature_provenance: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    seen_feature_ids: set[str] = set()

    for page_number in range(1, MAX_OGC_PAGES + 1):
        if current_url in visited:
            raise ValueError("USGS pagination contains a cycle")
        visited.add(current_url)
        payload, record = _store_http_exchange(
            url=current_url,
            accept="application/geo+json",
            provider="usgs",
            request_kind=request_kind,
            site_id=site_id,
            variable=variable,
            page_number=page_number,
            raw_root=raw_root,
            artifact_prefix=prefix,
            fetcher=fetcher,
            api_key=api_key,
        )
        if (
            not isinstance(payload, Mapping)
            or payload.get("type") != "FeatureCollection"
        ):
            raise TypeError("USGS OGC response must be a GeoJSON FeatureCollection")
        page_features = payload.get("features")
        links = payload.get("links", [])
        if not isinstance(page_features, list) or not isinstance(links, list):
            raise TypeError("USGS OGC response features and links must be lists")
        returned = payload.get("numberReturned")
        if returned is not None and (
            isinstance(returned, bool)
            or not isinstance(returned, int)
            or returned != len(page_features)
        ):
            raise ValueError("USGS numberReturned does not match the feature page")
        for feature in page_features:
            if not isinstance(feature, Mapping):
                raise TypeError("USGS features must be mappings")
            feature_id = str(feature.get("id", ""))
            if not feature_id:
                raise ValueError("USGS feature is missing its id")
            if feature_id in seen_feature_ids:
                raise ValueError(
                    f"duplicate USGS feature id across pages: {feature_id}"
                )
            seen_feature_ids.add(feature_id)
            features.append(copy_mapping(feature))
            feature_provenance.append(
                {
                    "request_sha256": record["request_sha256"],
                    "response_sha256": record["response_sha256"],
                    "response_artifact": record["response_artifact"],
                    "page_number": page_number,
                }
            )
        next_links = [
            link
            for link in links
            if isinstance(link, Mapping) and str(link.get("rel")) == "next"
        ]
        if len(next_links) > 1:
            raise ValueError("USGS response contains multiple rel=next links")
        records.append(record)
        if not next_links or not page_features:
            return OGCCollectionResult(
                tuple(features), tuple(feature_provenance), tuple(records)
            )
        href = next_links[0].get("href")
        if not isinstance(href, str) or not href:
            raise ValueError("USGS rel=next link has no href")
        current_url = urllib.parse.urljoin(current_url, href)
        _validate_next_url(initial_url, current_url)
    raise RuntimeError(f"USGS pagination exceeded {MAX_OGC_PAGES} pages")


def copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-copy a JSON-compatible mapping through canonical serialization."""

    return cast(dict[str, Any], json.loads(_canonical_json_bytes(value)))


def _feature_parts(feature: Mapping[str, Any]) -> tuple[dict[str, Any], float, float]:
    properties = feature.get("properties")
    geometry = feature.get("geometry")
    if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
        raise TypeError("provider feature requires properties and geometry mappings")
    if geometry.get("type") != "Point":
        raise ValueError("provider feature geometry must be Point")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("provider Point geometry requires longitude and latitude")
    try:
        longitude, latitude = float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError) as error:
        raise ValueError("provider coordinates must be numeric") from error
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise ValueError("provider coordinates must be finite")
    return copy_mapping(properties), longitude, latitude


def _metadata_scalar(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return _canonical_json_bytes(value).decode("utf-8")
    return value


def parse_site_metadata(site_id: str, result: OGCCollectionResult) -> pd.DataFrame:
    expected_id = f"USGS-{site_id}"
    if len(result.features) != 1:
        raise ValueError(
            f"expected exactly one monitoring-location feature for {expected_id}; "
            f"found {len(result.features)}"
        )
    feature = result.features[0]
    properties, longitude, latitude = _feature_parts(feature)
    if properties.get("id") != expected_id or feature.get("id") != expected_id:
        raise ValueError(f"monitoring-location metadata does not match {expected_id}")
    if properties.get("agency_code") != "USGS":
        raise ValueError("frozen monitoring location is not a USGS site")
    if str(properties.get("monitoring_location_number")) != site_id:
        raise ValueError("monitoring-location number differs from frozen site id")
    row = {key: _metadata_scalar(value) for key, value in properties.items()}
    row.update(
        {
            "site_id": site_id,
            "feature_id": str(feature["id"]),
            "longitude": longitude,
            "latitude": latitude,
            "provider_properties_json": _canonical_json_bytes(properties).decode(
                "utf-8"
            ),
            **result.feature_provenance[0],
        }
    )
    return pd.DataFrame([row])


def parse_time_series_metadata(
    site_id: str,
    spec: ExternalVariableSpec,
    result: OGCCollectionResult,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for feature, provenance in zip(
        result.features, result.feature_provenance, strict=True
    ):
        properties, longitude, latitude = _feature_parts(feature)
        expected = {
            "monitoring_location_id": f"USGS-{site_id}",
            "parameter_code": spec.provider_code,
            "statistic_id": spec.statistic_id,
            "unit_of_measure": spec.source_unit,
        }
        for key, value in expected.items():
            if properties.get(key) != value:
                raise ValueError(
                    f"time-series metadata {key} mismatch for {site_id}/{spec.variable}"
                )
        if properties.get("id") != feature.get("id"):
            raise ValueError("time-series feature and property ids differ")
        row = {key: _metadata_scalar(value) for key, value in properties.items()}
        row.update(
            {
                "site_id": site_id,
                "variable": spec.variable,
                "feature_id": str(feature["id"]),
                "longitude": longitude,
                "latitude": latitude,
                "metadata_available": True,
                "provider_properties_json": _canonical_json_bytes(properties).decode(
                    "utf-8"
                ),
                **provenance,
            }
        )
        rows.append(row)
    if not rows:
        rows.append(
            {
                "site_id": site_id,
                "variable": spec.variable,
                "monitoring_location_id": f"USGS-{site_id}",
                "parameter_code": spec.provider_code,
                "statistic_id": spec.statistic_id,
                "unit_of_measure": spec.source_unit,
                "id": None,
                "metadata_available": False,
            }
        )
    return pd.DataFrame(rows)


def _qualifier_tokens(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise TypeError("USGS qualifier must be null, a string, or a string list")


def _is_estimated(tokens: Sequence[str]) -> bool:
    normalized = {value.strip().upper() for value in tokens}
    return "E" in normalized or any("ESTIMAT" in value for value in normalized)


def parse_usgs_daily_values(
    site_id: str,
    spec: ExternalVariableSpec,
    result: OGCCollectionResult,
    *,
    allowed_time_series_ids: set[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """Parse Approved/Provisional daily values while retaining raw evidence."""

    rows: list[dict[str, Any]] = []
    for feature, provenance in zip(
        result.features, result.feature_provenance, strict=True
    ):
        properties, longitude, latitude = _feature_parts(feature)
        expected = {
            "monitoring_location_id": f"USGS-{site_id}",
            "parameter_code": spec.provider_code,
            "statistic_id": spec.statistic_id,
            "unit_of_measure": spec.source_unit,
        }
        for key, value in expected.items():
            if properties.get(key) != value:
                raise ValueError(
                    f"USGS daily {key} mismatch for {site_id}/{spec.variable}"
                )
        series_id = str(properties.get("time_series_id", ""))
        if not series_id or series_id not in allowed_time_series_ids:
            raise ValueError(
                f"USGS daily value references unknown time series {series_id!r}"
            )
        date = pd.to_datetime(properties.get("time"), errors="coerce")
        if pd.isna(date):
            raise ValueError("USGS daily value has an invalid date")
        date = pd.Timestamp(date).normalize()
        if not pd.Timestamp(start) <= date <= pd.Timestamp(end):
            raise ValueError("USGS returned a daily value outside the frozen period")
        raw_value = pd.to_numeric(properties.get("value"), errors="coerce")
        if not np.isfinite(raw_value):
            raise ValueError("USGS daily value is not finite numeric text")
        approval = properties.get("approval_status")
        if approval not in {"Approved", "Provisional"}:
            raise ValueError(f"unexpected USGS approval_status {approval!r}")
        tokens = _qualifier_tokens(properties.get("qualifier"))
        estimated = _is_estimated(tokens)
        approved = approval == "Approved"
        converted = float(raw_value) * spec.conversion_factor if approved else np.nan
        rows.append(
            {
                "date": date,
                "site_id": site_id,
                "station_id": site_id,
                "variable": spec.variable,
                "raw_name": spec.provider_code,
                "source": spec.provider,
                "source_value_original": float(raw_value),
                "raw_value": float(raw_value),
                "value": converted,
                "raw_unit": spec.source_unit,
                "unit": spec.unit,
                "conversion_factor": spec.conversion_factor,
                "unit_conversion": spec.conversion_formula,
                "natural_observed": True,
                "quality_approved": approved,
                "approval_status": approval,
                "qualifier_json": _canonical_json_bytes(list(tokens)).decode("utf-8"),
                "estimated_qualifier": estimated,
                "qc_status": (
                    "approved_estimated"
                    if approved and estimated
                    else "approved"
                    if approved
                    else "excluded_provisional"
                ),
                "time_series_id": series_id,
                "source_feature_id": str(feature["id"]),
                "source_last_modified": properties.get("last_modified"),
                "source_longitude": longitude,
                "source_latitude": latitude,
                "interpretation": spec.interpretation,
                "quality_basis": "USGS approval_status Approved only",
                **provenance,
            }
        )
    frame = pd.DataFrame(rows)
    _reject_duplicate_observations(frame, context="USGS daily values")
    return frame


def _reject_duplicate_observations(frame: pd.DataFrame, *, context: str) -> None:
    if frame.empty:
        return
    keys = ["date", "site_id", "variable"]
    duplicated = frame.duplicated(keys, keep=False)
    if not duplicated.any():
        return
    conflicts = []
    for key, group in frame.loc[duplicated].groupby(keys, sort=False, dropna=False):
        comparison = group.drop(columns=keys).astype(str).drop_duplicates()
        conflicts.append(
            {"key": tuple(map(str, key)), "conflicting": len(comparison) > 1}
        )
    if any(value["conflicting"] for value in conflicts):
        raise ValueError(
            f"{context} contains conflicting duplicate observations: {conflicts[:3]}"
        )
    raise ValueError(f"{context} contains duplicate observations: {conflicts[:3]}")


def _parse_power_response(
    site_id: str,
    longitude: float,
    latitude: float,
    payload: Any,
    provenance: Mapping[str, Any],
    protocol: ConfirmatoryProtocol,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not isinstance(payload, Mapping) or payload.get("type") != "Feature":
        raise TypeError("NASA POWER response must be a Feature")
    header = payload.get("header")
    parameters = payload.get("parameters")
    properties = payload.get("properties")
    geometry = payload.get("geometry")
    if not all(
        isinstance(value, Mapping)
        for value in (header, parameters, properties, geometry)
    ):
        raise TypeError("NASA POWER response metadata fields must be mappings")
    header = cast(Mapping[str, Any], header)
    parameters = cast(Mapping[str, Any], parameters)
    properties = cast(Mapping[str, Any], properties)
    geometry = cast(Mapping[str, Any], geometry)
    expected_header = {
        "time_standard": protocol.nasa_time_standard,
        "start": protocol.start.replace("-", ""),
        "end": protocol.end.replace("-", ""),
    }
    for key, expected in expected_header.items():
        if header.get(key) != expected:
            raise ValueError(f"NASA POWER header {key} mismatch")
    fill_value = header.get("fill_value")
    if not isinstance(fill_value, (int, float)) or not math.isfinite(float(fill_value)):
        raise ValueError("NASA POWER header has no finite fill_value")
    if geometry.get("type") != "Point":
        raise ValueError("NASA POWER geometry must be Point")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("NASA POWER geometry has no point coordinates")
    response_longitude, response_latitude = float(coordinates[0]), float(coordinates[1])
    if not math.isfinite(response_longitude) or not math.isfinite(response_latitude):
        raise ValueError("NASA POWER response coordinates must be finite")
    parameter_values = properties.get("parameter")
    if not isinstance(parameter_values, Mapping):
        raise TypeError("NASA POWER properties.parameter must be a mapping")
    expected_codes = tuple(spec.provider_code for spec in METEOROLOGY_SPECS)
    if set(parameters) != set(expected_codes) or set(parameter_values) != set(
        expected_codes
    ):
        raise ValueError(
            "NASA POWER response parameter set differs from the frozen request"
        )
    rows: list[dict[str, Any]] = []
    for spec in METEOROLOGY_SPECS:
        parameter_metadata = parameters.get(spec.provider_code)
        values = parameter_values.get(spec.provider_code)
        if not isinstance(parameter_metadata, Mapping) or not isinstance(
            values, Mapping
        ):
            raise TypeError("NASA POWER parameter metadata and values must be mappings")
        if parameter_metadata.get("units") != spec.source_unit:
            raise ValueError(
                f"NASA POWER unit mismatch for {spec.provider_code}: "
                f"{parameter_metadata.get('units')!r}"
            )
        for date_text, raw_value in values.items():
            try:
                date = pd.to_datetime(str(date_text), format="%Y%m%d").normalize()
            except (TypeError, ValueError) as error:
                raise ValueError("NASA POWER returned an invalid daily date") from error
            if not pd.Timestamp(protocol.start) <= date <= pd.Timestamp(protocol.end):
                raise ValueError("NASA POWER returned a date outside the frozen period")
            numeric = pd.to_numeric(raw_value, errors="coerce")
            if not np.isfinite(numeric):
                raise ValueError("NASA POWER daily value is non-numeric")
            available = not math.isclose(
                float(numeric), float(fill_value), rel_tol=0.0, abs_tol=0.0
            )
            rows.append(
                {
                    "date": date,
                    "site_id": site_id,
                    "station_id": site_id,
                    "variable": spec.variable,
                    "raw_name": spec.provider_code,
                    "source": spec.provider,
                    "source_value_original": float(numeric),
                    "raw_value": float(numeric),
                    "value": float(numeric) if available else np.nan,
                    "raw_unit": spec.source_unit,
                    "unit": spec.unit,
                    "conversion_factor": spec.conversion_factor,
                    "unit_conversion": spec.conversion_formula,
                    "natural_observed": available,
                    "quality_approved": available,
                    "approval_status": "NotApplicable",
                    "qualifier_json": "[]",
                    "estimated_qualifier": False,
                    "qc_status": "provider_value"
                    if available
                    else "provider_fill_value",
                    "time_series_id": None,
                    "source_feature_id": None,
                    "source_last_modified": None,
                    "source_longitude": response_longitude,
                    "source_latitude": response_latitude,
                    "interpretation": spec.interpretation,
                    "quality_basis": "NASA POWER finite non-fill-value screen",
                    **provenance,
                }
            )
    observations = pd.DataFrame(rows)
    _reject_duplicate_observations(observations, context="NASA POWER daily values")
    point_metadata = pd.DataFrame(
        [
            {
                "site_id": site_id,
                "requested_usgs_longitude": longitude,
                "requested_usgs_latitude": latitude,
                "response_longitude": response_longitude,
                "response_latitude": response_latitude,
                "response_elevation": coordinates[2] if len(coordinates) > 2 else None,
                "spatial_rule": protocol.nasa_spatial_rule,
                "spatial_implementation": (
                    "POWER daily point API provider-side source-native nearest-grid selection; "
                    "the builder performs no interpolation"
                ),
                "time_standard": header.get("time_standard"),
                "api_name": (
                    header.get("api", {}).get("name")
                    if isinstance(header.get("api"), Mapping)
                    else None
                ),
                "api_version": (
                    header.get("api", {}).get("version")
                    if isinstance(header.get("api"), Mapping)
                    else None
                ),
                "sources_json": _canonical_json_bytes(header.get("sources", [])).decode(
                    "utf-8"
                ),
                "fill_value": float(fill_value),
                "parameters_json": _canonical_json_bytes(parameters).decode("utf-8"),
                "messages_json": _canonical_json_bytes(
                    payload.get("messages", [])
                ).decode("utf-8"),
                **provenance,
            }
        ]
    )
    return observations, point_metadata


@dataclass(frozen=True)
class ConfirmatorySourceBundle:
    hydrology: pd.DataFrame
    meteorology: pd.DataFrame
    site_metadata: pd.DataFrame
    time_series_metadata: pd.DataFrame
    power_point_metadata: pd.DataFrame
    request_records: tuple[dict[str, Any], ...]


def _fetch_power_document(
    *,
    site_id: str,
    longitude: float,
    latitude: float,
    protocol: ConfirmatoryProtocol,
    raw_root: Path,
    fetcher: HTTPFetcher,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    url = _nasa_power_url(longitude, latitude, protocol)
    payload, record = _store_http_exchange(
        url=url,
        accept="application/json",
        provider="nasa_power",
        request_kind="daily_point_meteorology",
        site_id=site_id,
        variable=None,
        page_number=1,
        raw_root=raw_root,
        artifact_prefix=Path("nasa_power") / site_id,
        fetcher=fetcher,
        api_key=None,
    )
    observations, metadata = _parse_power_response(
        site_id,
        longitude,
        latitude,
        payload,
        {
            "request_sha256": record["request_sha256"],
            "response_sha256": record["response_sha256"],
            "response_artifact": record["response_artifact"],
            "page_number": 1,
        },
        protocol,
    )
    return observations, metadata, record


def fetch_confirmatory_sources(
    protocol: ConfirmatoryProtocol,
    raw_root: str | Path,
    *,
    fetcher: HTTPFetcher = urlopen_fetcher,
    usgs_api_key: str | None = None,
) -> ConfirmatorySourceBundle:
    """Fetch frozen raw sources. Call only after the finalists are frozen."""

    raw_root = Path(raw_root)
    site_frames: list[pd.DataFrame] = []
    series_frames: list[pd.DataFrame] = []
    hydro_frames: list[pd.DataFrame] = []
    meteorology_frames: list[pd.DataFrame] = []
    power_metadata_frames: list[pd.DataFrame] = []
    request_records: list[dict[str, Any]] = []

    for site_id in protocol.site_ids:
        site_result = fetch_ogc_feature_collection(
            _usgs_monitoring_location_url(site_id),
            request_kind="monitoring_location_metadata",
            site_id=site_id,
            variable=None,
            raw_root=raw_root,
            artifact_prefix=Path("usgs") / "monitoring_locations" / site_id,
            fetcher=fetcher,
            api_key=usgs_api_key,
        )
        site_frame = parse_site_metadata(site_id, site_result)
        site_frames.append(site_frame)
        request_records.extend(site_result.request_records)

        for spec in HYDROLOGY_SPECS:
            series_result = fetch_ogc_feature_collection(
                _usgs_time_series_url(site_id, spec),
                request_kind="time_series_metadata",
                site_id=site_id,
                variable=spec.variable,
                raw_root=raw_root,
                artifact_prefix=(
                    Path("usgs") / "time_series_metadata" / site_id / spec.variable
                ),
                fetcher=fetcher,
                api_key=usgs_api_key,
            )
            series_frame = parse_time_series_metadata(site_id, spec, series_result)
            series_frames.append(series_frame)
            request_records.extend(series_result.request_records)
            allowed_series = set(
                series_frame.loc[
                    series_frame["metadata_available"].fillna(False), "id"
                ].astype(str)
            )
            daily_result = fetch_ogc_feature_collection(
                _usgs_daily_url(site_id, spec, protocol),
                request_kind="daily_values",
                site_id=site_id,
                variable=spec.variable,
                raw_root=raw_root,
                artifact_prefix=Path("usgs") / "daily" / site_id / spec.variable,
                fetcher=fetcher,
                api_key=usgs_api_key,
            )
            hydro_frames.append(
                parse_usgs_daily_values(
                    site_id,
                    spec,
                    daily_result,
                    allowed_time_series_ids=allowed_series,
                    start=protocol.start,
                    end=protocol.end,
                )
            )
            request_records.extend(daily_result.request_records)

        longitude = float(site_frame.iloc[0]["longitude"])
        latitude = float(site_frame.iloc[0]["latitude"])
        met_frame, power_metadata, power_record = _fetch_power_document(
            site_id=site_id,
            longitude=longitude,
            latitude=latitude,
            protocol=protocol,
            raw_root=raw_root,
            fetcher=fetcher,
        )
        meteorology_frames.append(met_frame)
        power_metadata_frames.append(power_metadata)
        request_records.append(power_record)

    return ConfirmatorySourceBundle(
        hydrology=pd.concat(hydro_frames, ignore_index=True),
        meteorology=pd.concat(meteorology_frames, ignore_index=True),
        site_metadata=pd.concat(site_frames, ignore_index=True),
        time_series_metadata=pd.concat(series_frames, ignore_index=True),
        power_point_metadata=pd.concat(power_metadata_frames, ignore_index=True),
        request_records=tuple(request_records),
    )


def _split_labels(dates: pd.Series, protocol: ConfirmatoryProtocol) -> np.ndarray:
    labels = np.full(len(dates), "unassigned", dtype=object)
    normalized = pd.to_datetime(dates).dt.normalize()
    for period in protocol.periods:
        selected = normalized.between(period.start, period.end, inclusive="both")
        labels[selected.to_numpy()] = period.label
    if np.any(labels == "unassigned"):
        raise ValueError(
            "external calendar contains dates outside frozen split periods"
        )
    return labels


def assemble_confirmatory_frames(
    hydrology: pd.DataFrame,
    meteorology: pd.DataFrame,
    protocol: ConfirmatoryProtocol,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Align all eight variables to the complete frozen calendar."""

    observations = pd.concat([hydrology, meteorology], ignore_index=True, sort=False)
    if not observations.empty:
        _reject_duplicate_observations(
            observations, context="combined external observations"
        )
        unexpected_sites = sorted(set(observations["site_id"]) - set(protocol.site_ids))
        unexpected_variables = sorted(
            set(observations["variable"]) - set(FROZEN_VARIABLES)
        )
        if unexpected_sites or unexpected_variables:
            raise ValueError(
                f"external observations escaped frozen axes: sites={unexpected_sites}, "
                f"variables={unexpected_variables}"
            )
    calendar = pd.date_range(protocol.start, protocol.end, freq="D")
    index = pd.MultiIndex.from_product(
        [calendar, protocol.site_ids, FROZEN_VARIABLES],
        names=["date", "site_id", "variable"],
    )
    if observations.empty:
        aligned = pd.DataFrame(index=index).reset_index()
    else:
        observations = observations.copy()
        observations["date"] = pd.to_datetime(observations["date"]).dt.normalize()
        aligned = observations.set_index(["date", "site_id", "variable"]).reindex(index)
        aligned = aligned.reset_index()
    aligned["station_id"] = aligned["site_id"]
    static_columns = {
        "raw_name": {spec.variable: spec.provider_code for spec in VARIABLE_SPECS},
        "source": {spec.variable: spec.provider for spec in VARIABLE_SPECS},
        "raw_unit": {spec.variable: spec.source_unit for spec in VARIABLE_SPECS},
        "unit": {spec.variable: spec.unit for spec in VARIABLE_SPECS},
        "conversion_factor": {
            spec.variable: spec.conversion_factor for spec in VARIABLE_SPECS
        },
        "unit_conversion": {
            spec.variable: spec.conversion_formula for spec in VARIABLE_SPECS
        },
        "interpretation": {
            spec.variable: spec.interpretation for spec in VARIABLE_SPECS
        },
    }
    for column, lookup in static_columns.items():
        expected = aligned["variable"].map(lookup)
        if column in aligned:
            present = aligned[column].notna()
            if (
                not aligned.loc[present, column]
                .astype(str)
                .equals(expected.loc[present].astype(str))
            ):
                raise ValueError(f"external observation {column} metadata conflict")
            aligned[column] = aligned[column].where(present, expected)
        else:
            aligned[column] = expected
    for column in ("raw_value", "source_value_original", "value"):
        aligned[column] = pd.to_numeric(aligned.get(column), errors="coerce")

    def column_or_default(name: str, default: Any) -> pd.Series:
        if name in aligned:
            return aligned[name]
        return pd.Series(default, index=aligned.index)

    aligned["natural_observed"] = (
        column_or_default("natural_observed", False).fillna(False).astype(bool)
    )
    aligned["quality_approved"] = (
        column_or_default("quality_approved", False).fillna(False).astype(bool)
    )
    aligned["estimated_qualifier"] = (
        column_or_default("estimated_qualifier", False).fillna(False).astype(bool)
    )
    if (
        aligned["quality_approved"]
        & (~np.isfinite(aligned["value"]) | ~aligned["natural_observed"])
    ).any():
        raise ValueError("quality-approved external rows must be finite and observed")
    aligned["approval_status"] = column_or_default("approval_status", "Missing").fillna(
        "Missing"
    )
    aligned["qualifier_json"] = column_or_default("qualifier_json", "[]").fillna("[]")
    aligned["qc_status"] = column_or_default("qc_status", "source_missing").fillna(
        "source_missing"
    )
    aligned["quality_basis"] = column_or_default(
        "quality_basis", "source record absent"
    ).fillna("source record absent")
    aligned["split"] = _split_labels(aligned["date"], protocol)
    aligned["data_version"] = CONFIRMATORY_DATA_VERSION
    aligned["is_external_validation"] = True
    aligned["external_evidence_role"] = aligned["split"].map(
        {
            "train": "external_model_fitting_only",
            "validation": "external_early_stopping_only",
            "confirmatory": "locked_confirmatory_evaluation_only",
        }
    )
    aligned["quality_rule"] = protocol.quality_rule
    variable_order = {value: index for index, value in enumerate(FROZEN_VARIABLES)}
    site_order = {value: index for index, value in enumerate(protocol.site_ids)}
    aligned["_site_order"] = aligned["site_id"].map(site_order)
    aligned["_variable_order"] = aligned["variable"].map(variable_order)
    aligned = aligned.sort_values(
        ["date", "_site_order", "_variable_order"], kind="stable"
    ).drop(columns=["_site_order", "_variable_order"])
    aligned = aligned.reset_index(drop=True)

    value_wide = aligned.pivot(
        index="date", columns=["site_id", "variable"], values="value"
    ).reindex(columns=pd.MultiIndex.from_product([protocol.site_ids, FROZEN_VARIABLES]))
    value_wide.columns = [
        f"{site_id}_{variable}" for site_id, variable in value_wide.columns
    ]
    wide = value_wide.reset_index()
    wide["split"] = _split_labels(wide["date"], protocol)
    wide["data_version"] = CONFIRMATORY_DATA_VERSION
    wide["is_external_validation"] = True
    wide = add_time_features(wide, origin_year=2012)
    measurements = [
        f"{site_id}_{variable}"
        for site_id in protocol.site_ids
        for variable in FROZEN_VARIABLES
    ]
    leading = [
        "date",
        "split",
        "data_version",
        "is_external_validation",
        *TIME_FEATURE_COLUMNS,
    ]
    wide = wide[[*leading, *measurements]]
    return aligned, wide


def build_availability_report(
    long_data: pd.DataFrame, protocol: ConfirmatoryProtocol
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = long_data.groupby(["split", "site_id", "variable"], sort=False)
    for period in protocol.periods:
        for site_id in protocol.site_ids:
            for variable in FROZEN_VARIABLES:
                group = grouped.get_group((period.label, site_id, variable))
                total = len(group)
                usable = group["quality_approved"] & np.isfinite(group["value"])
                rows.append(
                    {
                        "split": period.label,
                        "site_id": site_id,
                        "variable": variable,
                        "expected_days": total,
                        "natural_observed_days": int(group["natural_observed"].sum()),
                        "quality_approved_days": int(group["quality_approved"].sum()),
                        "usable_days": int(usable.sum()),
                        "estimated_approved_days": int(
                            (usable & group["estimated_qualifier"]).sum()
                        ),
                        "provisional_excluded_days": int(
                            group["qc_status"].eq("excluded_provisional").sum()
                        ),
                        "source_missing_days": int(
                            group["qc_status"].eq("source_missing").sum()
                        ),
                        "usable_fraction": float(usable.sum() / total),
                        "data_version": CONFIRMATORY_DATA_VERSION,
                    }
                )
    return pd.DataFrame(rows)


def build_quality_report(
    long_data: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    grouped = (
        long_data.groupby(
            [
                "source",
                "site_id",
                "variable",
                "approval_status",
                "qc_status",
                "estimated_qualifier",
            ],
            dropna=False,
            sort=False,
        )
        .size()
        .rename("row_count")
        .reset_index()
    )
    summary = {
        "schema_version": CONFIRMATORY_SCHEMA_VERSION,
        "data_version": CONFIRMATORY_DATA_VERSION,
        "quality_rule": FROZEN_QUALITY_RULE,
        "total_rows": len(long_data),
        "natural_observed_rows": int(long_data["natural_observed"].sum()),
        "quality_approved_rows": int(long_data["quality_approved"].sum()),
        "estimated_approved_rows": int(
            (long_data["quality_approved"] & long_data["estimated_qualifier"]).sum()
        ),
        "provisional_excluded_rows": int(
            long_data["qc_status"].eq("excluded_provisional").sum()
        ),
        "provider_fill_value_rows": int(
            long_data["qc_status"].eq("provider_fill_value").sum()
        ),
        "source_missing_rows": int(long_data["qc_status"].eq("source_missing").sum()),
        "duplicate_observations": 0,
        "conflicting_observations": 0,
        "dh_interpretation": DH_INTERPRETATION,
        "performance_metrics_computed": False,
    }
    return grouped, summary


def _write_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_immutable_request_plan(plan: Mapping[str, Any], path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable request plan: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            json.dump(
                dict(plan),
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            handle.write("\n")
        try:
            # A same-directory hard link gives us atomic no-clobber semantics;
            # unlike rename(), it cannot replace even an empty existing target.
            os.link(temporary_name, output)
        except FileExistsError as error:
            raise FileExistsError(
                f"refusing to overwrite immutable request plan: {output}"
            ) from error
        Path(temporary_name).unlink()
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    return output


def _artifact_manifest(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        relative = str(path.relative_to(root))
        if relative in {"provenance_manifest.json", "provenance_manifest.json.sha256"}:
            continue
        result[relative] = {"sha256": file_sha256(path), "bytes": path.stat().st_size}
    return result


def _build_into_staging(
    protocol: ConfirmatoryProtocol,
    finalized_roster: FinalizedModelRoster,
    staging: Path,
    *,
    fetcher: HTTPFetcher,
    usgs_api_key: str | None,
) -> dict[str, Any]:
    raw_root = staging / "raw"
    bundle = fetch_confirmatory_sources(
        protocol,
        raw_root,
        fetcher=fetcher,
        usgs_api_key=usgs_api_key,
    )
    long_data, wide_data = assemble_confirmatory_frames(
        bundle.hydrology, bundle.meteorology, protocol
    )
    availability = build_availability_report(long_data, protocol)
    quality_details, quality_summary = build_quality_report(long_data)

    long_data.to_parquet(staging / "daily_long.parquet", index=False)
    wide_data.to_parquet(staging / "daily_wide.parquet", index=False)
    metadata_root = staging / "metadata"
    metadata_root.mkdir(parents=True, exist_ok=False)
    bundle.site_metadata.to_parquet(
        metadata_root / "site_metadata.parquet", index=False
    )
    bundle.time_series_metadata.to_parquet(
        metadata_root / "time_series_metadata.parquet", index=False
    )
    bundle.power_point_metadata.to_parquet(
        metadata_root / "power_point_metadata.parquet", index=False
    )
    availability.to_parquet(metadata_root / "availability_report.parquet", index=False)
    quality_details.to_parquet(metadata_root / "quality_detail.parquet", index=False)
    _write_json(
        availability.to_dict(orient="records"),
        metadata_root / "availability_report.json",
    )
    _write_json(quality_summary, metadata_root / "quality_report.json")
    request_log = {
        "schema_version": REQUEST_LOG_SCHEMA_VERSION,
        "request_count": len(bundle.request_records),
        "api_key_values_persisted": False,
        "requests": list(bundle.request_records),
    }
    _write_json(request_log, metadata_root / "request_log.json")
    _write_json(
        build_confirmatory_request_plan(protocol), metadata_root / "request_plan.json"
    )
    split_root = staging / "splits"
    split_root.mkdir(parents=True, exist_ok=False)
    for period in protocol.periods:
        wide_data.loc[wide_data["split"] == period.label].to_parquet(
            split_root / f"{period.label}.parquet", index=False
        )

    artifacts = _artifact_manifest(staging)
    manifest: dict[str, Any] = {
        "schema_version": CONFIRMATORY_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_version": CONFIRMATORY_DATA_VERSION,
        "immutable": True,
        "design_version": protocol.design_version,
        "design_path": protocol.design_path,
        "design_sha256": protocol.design_sha256,
        "confirmatory_access_gate": finalized_roster.metadata(),
        "protocol": protocol.metadata(),
        "official_documentation": {
            "usgs_ogc": USGS_OGC_DOCUMENTATION,
            "nasa_power_daily": NASA_POWER_DOCUMENTATION,
        },
        "request_count": len(bundle.request_records),
        "requests_sha256": _canonical_json_sha256(list(bundle.request_records)),
        "raw_response_count": sum(
            1 for value in artifacts if value.endswith(".response.json")
        ),
        "output_counts": {
            "long_rows": len(long_data),
            "wide_rows": len(wide_data),
            "site_metadata_rows": len(bundle.site_metadata),
            "time_series_metadata_rows": len(bundle.time_series_metadata),
            "power_point_metadata_rows": len(bundle.power_point_metadata),
            "availability_report_rows": len(availability),
            "split_wide_rows": {
                period.label: int((wide_data["split"] == period.label).sum())
                for period in protocol.periods
            },
        },
        "quality_summary": quality_summary,
        "unit_conversions": [asdict(spec) for spec in VARIABLE_SPECS],
        "dh_interpretation": DH_INTERPRETATION,
        "confirmatory_evaluation_executed": False,
        "performance_metrics_computed": False,
        "artifacts": artifacts,
    }
    _write_json(manifest, staging / "provenance_manifest.json")
    manifest_hash = file_sha256(staging / "provenance_manifest.json")
    (staging / "provenance_manifest.json.sha256").write_text(
        manifest_hash + "\n", encoding="ascii"
    )
    return manifest


def build_confirmatory_data(
    design_path: str | Path,
    output_dir: str | Path,
    *,
    finalized_model_roster_path: str | Path,
    study_manifest_path: str | Path = REPOSITORY_ROOT / "study_manifest.yaml",
    experiment_config_path: str | Path = REPOSITORY_ROOT / "configs/experiments.yaml",
    selection_data_version: str = DEFAULT_SELECTION_DATA_VERSION,
    selection_data_version_manifest_path: str | Path | None = None,
    fetcher: HTTPFetcher = urlopen_fetcher,
    usgs_api_key: str | None = None,
) -> dict[str, Any]:
    """Atomically materialise the external data without computing performance.

    The finalized validation roster and each artifact it attests are checked
    before creating output paths or performing any HTTP request.
    """

    protocol = load_confirmatory_protocol(design_path)
    finalized_roster = load_finalized_model_roster(
        finalized_model_roster_path,
        design_path=design_path,
        study_manifest_path=study_manifest_path,
        experiment_config_path=experiment_config_path,
        selection_data_version=selection_data_version,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.parent / f".{output.name}.build.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise FileExistsError(
            f"confirmatory build lock already exists: {lock}"
        ) from error
    os.close(descriptor)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.staging.", dir=output.parent)
    )
    try:
        if output.exists():
            raise FileExistsError(f"refusing to overwrite immutable output: {output}")
        manifest = _build_into_staging(
            protocol,
            finalized_roster,
            staging,
            fetcher=fetcher,
            usgs_api_key=usgs_api_key,
        )
        if output.exists():
            raise FileExistsError(f"refusing to overwrite immutable output: {output}")
        os.rename(staging, output)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        lock.unlink(missing_ok=True)


__all__ = [
    "CONFIRMATORY_DATA_VERSION",
    "CONFIRMATORY_SCHEMA_VERSION",
    "DEFAULT_SELECTION_DATA_VERSION",
    "DH_INTERPRETATION",
    "FINALIZED_MODEL_ROSTER_SCHEMA_VERSION",
    "FROZEN_HYDROLOGY",
    "FROZEN_METEOROLOGY",
    "FROZEN_PERIODS",
    "FROZEN_SITE_IDS",
    "FROZEN_VARIABLES",
    "FT3_S_TO_M3_S",
    "FT_TO_M",
    "HYDROLOGY_SPECS",
    "METEOROLOGY_SPECS",
    "REQUEST_PLAN_SCHEMA_VERSION",
    "ConfirmatoryProtocol",
    "ConfirmatorySourceBundle",
    "ExternalVariableSpec",
    "FinalizedModelRoster",
    "HTTPResponse",
    "OGCCollectionResult",
    "SplitPeriod",
    "assemble_confirmatory_frames",
    "build_availability_report",
    "build_confirmatory_data",
    "build_confirmatory_request_plan",
    "build_quality_report",
    "fetch_confirmatory_sources",
    "fetch_ogc_feature_collection",
    "file_sha256",
    "load_confirmatory_protocol",
    "load_finalized_model_roster",
    "parse_site_metadata",
    "parse_time_series_metadata",
    "parse_usgs_daily_values",
    "strict_json_loads",
    "urlopen_fetcher",
    "write_immutable_request_plan",
]

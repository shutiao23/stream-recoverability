"""Fail-closed byte custody for the prospective FOEN sealed split.

This module verifies the pre-value catalog, split, and GraphQL-template hashes,
expands the fixed station-by-calendar-year request grid, and writes successful
provider response bodies as opaque bytes. It deliberately has no response JSON
decoder and no sealed read/unseal method.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG = REPOSITORY_ROOT / "configs/foen_prospective_catalog_v1.yaml"
DEFAULT_SPLIT = REPOSITORY_ROOT / "configs/foen_prospective_split_v1.yaml"
DEFAULT_CANONICAL_SPLIT = (
    REPOSITORY_ROOT / "results/framework/public_catalog/foen_prospective_split_v1.csv"
)
DEFAULT_QUERY_TEMPLATE = REPOSITORY_ROOT / "configs/foen_daily_value_query_v1.graphql"
DEFAULT_SEALED_VAULT = REPOSITORY_ROOT / "data/sealed_public_rivers_foen_v1/vault"
DEFAULT_REGISTRY = (
    REPOSITORY_ROOT / "results/framework/public_catalog/foen_sealed_byte_registry_v1"
)

LOCKED_SPLIT_SHA256 = "4405cf690ccf9d9b62a8dfa76d2d1d74806e662835bff0043ee9fe1e5619ae59"
LOCKED_CATALOG_SHA256 = (
    "2e348f571a6e19025d8f6d6aca2dfe55997927b94a608a78baedd89819a78727"
)
LOCKED_QUERY_TEMPLATE_SHA256 = (
    "978247efe815a79863e0383a3ae1e8c293642ec245d7205bd13a46b2ec3a446d"
)
FOEN_ENDPOINT = "https://data.bafu.admin.ch/api"
SEALED_ROLE = "sealed"
PROVIDER = "foen"
REGISTRY_SCHEMA = "foen_sealed_byte_registry_v1"
REQUEST_START = "1974-01-01T00:00:00Z"
REQUEST_END_EXCLUSIVE = "2026-01-01T00:00:00Z"
EXPECTED_SEALED_NETWORKS = 10
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REGISTRY_FIELDS = frozenset(
    {
        "registry_schema",
        "provider",
        "network_id",
        "role",
        "site_id",
        "request_year",
        "request_start",
        "request_end_exclusive",
        "split_sha256",
        "catalog_sha256",
        "query_template_sha256",
        "storage_class",
        "response_sha256",
        "byte_count",
        "content_parsed",
        "json_decoded",
        "value_fields_inspected",
        "sealed_outcomes_opened",
        "qc_permitted",
        "reused_registry",
    }
)


class FoenCustodyError(RuntimeError):
    """Raised when a lock or byte-registry invariant fails closed."""


class FoenSealedAccessError(PermissionError):
    """Raised for any attempted development-time access to sealed bytes."""


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _yaml_mapping(path: str | Path) -> dict[str, Any]:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError(f"expected YAML mapping: {path}")
    return document


def _safe(value: str, label: str) -> str:
    text = str(value)
    if not text or not _SAFE_COMPONENT.fullmatch(text):
        raise ValueError(f"unsafe {label}: {text!r}")
    return text


def _utc_year(value: str) -> int:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"request bound is not UTC: {value}")
    if (parsed.month, parsed.day, parsed.hour, parsed.minute, parsed.second) != (
        1,
        1,
        0,
        0,
        0,
    ):
        raise ValueError(f"request bound is not a calendar-year boundary: {value}")
    return int(parsed.year)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class FoenYearRequest:
    network_id: str
    role: str
    site_id: str
    year: int
    start: str
    end_exclusive: str

    def metadata(self) -> dict[str, Any]:
        return {
            "network_id": self.network_id,
            "role": self.role,
            "site_id": self.site_id,
            "request_year": self.year,
            "request_start": self.start,
            "request_end_exclusive": self.end_exclusive,
        }


@dataclass(frozen=True)
class LockedFoenCatalog:
    """Hash-verified prospective split and its fixed annual request grid."""

    roles: Mapping[str, str]
    stations: Mapping[str, tuple[str, ...]]
    split_sha256: str
    catalog_sha256: str
    query_template_sha256: str
    endpoint: str
    query_template: str
    start_year: int
    end_year_exclusive: int

    @classmethod
    def load(
        cls,
        *,
        catalog_path: str | Path = DEFAULT_CATALOG,
        split_path: str | Path = DEFAULT_SPLIT,
        canonical_path: str | Path = DEFAULT_CANONICAL_SPLIT,
        query_template_path: str | Path = DEFAULT_QUERY_TEMPLATE,
        expected_split_sha256: str = LOCKED_SPLIT_SHA256,
        expected_catalog_sha256: str = LOCKED_CATALOG_SHA256,
        expected_query_template_sha256: str = LOCKED_QUERY_TEMPLATE_SHA256,
    ) -> LockedFoenCatalog:
        split_digest = _sha256(canonical_path)
        catalog_digest = _sha256(catalog_path)
        query_digest = _sha256(query_template_path)
        if split_digest != expected_split_sha256:
            raise ValueError("FOEN canonical split SHA-256 mismatch")
        if catalog_digest != expected_catalog_sha256:
            raise ValueError("FOEN catalog SHA-256 mismatch")
        if query_digest != expected_query_template_sha256:
            raise ValueError("FOEN query-template SHA-256 mismatch")

        split = _yaml_mapping(split_path)
        if split.get("split_id") != "foen_prospective_split_v1":
            raise ValueError("refusing a non-FOEN-v1 split")
        if split.get("status") != "locked_before_temperature_value_query":
            raise ValueError("FOEN split is not locked before value query")
        if str(split.get("sha256")) != split_digest:
            raise ValueError("FOEN split YAML differs from canonical split hash")
        if str(split.get("catalog_sha256")) != catalog_digest:
            raise ValueError("FOEN split YAML differs from catalog hash")
        if split.get("temperature_values_queried") is not False:
            raise ValueError("FOEN split does not affirm unopened values")
        if split.get("sealed_outcomes_opened") is not False:
            raise ValueError("FOEN split does not affirm unopened sealed outcomes")
        if split.get("coverage_fields_used_for_eligibility") is not False:
            raise ValueError("FOEN split used coverage fields as eligibility")
        if int(split.get("qualified_networks_claimed") or 0) != 0:
            raise ValueError("FOEN metadata lock claims qualified networks")

        contract = split.get("future_request_contract") or {}
        expected_contract = {
            "status": "template_locked_not_executed",
            "query_template_sha256": query_digest,
            "endpoint": FOEN_ENDPOINT,
            "aggregation": "data_1day_mean",
            "parameter": "WT",
            "release_states": ["2", "3"],
            "request_start": REQUEST_START,
            "request_end_exclusive": REQUEST_END_EXCLUSIVE,
            "partition": "disjoint_calendar_year_windows",
            "response_handling_for_sealed": "stream_raw_http_response_bytes_without_json_decode",
            "template_executed": False,
        }
        drift = {
            key
            for key, expected in expected_contract.items()
            if contract.get(key) != expected
        }
        if drift:
            raise ValueError(f"FOEN future request contract drift: {sorted(drift)}")

        canonical_rows = list(
            csv.DictReader(
                Path(canonical_path).read_text(encoding="utf-8").splitlines()
            )
        )
        roles: dict[str, str] = {}
        canonical_stations: dict[str, tuple[str, ...]] = {}
        for row in canonical_rows:
            network_id = _safe(str(row.get("network_id") or ""), "network_id")
            role = str(row.get("role") or "")
            if network_id in roles:
                raise ValueError(f"duplicate FOEN split network: {network_id}")
            site_ids = tuple(
                _safe(item, "site_id")
                for item in str(row.get("station_ids") or "").split(",")
                if item
            )
            if len(site_ids) < 3 or len(site_ids) != len(set(site_ids)):
                raise ValueError(f"invalid FOEN station membership: {network_id}")
            if row.get("temperature_values_queried") != "false":
                raise ValueError("canonical FOEN split does not affirm unopened values")
            if row.get("qualified_8yr_status") != "unknown_until_post_download_qc":
                raise ValueError("canonical FOEN split claims daily-year eligibility")
            roles[network_id] = role
            canonical_stations[network_id] = site_ids

        yaml_rows = {
            str(row.get("network_id")): row for row in split.get("networks") or []
        }
        if set(yaml_rows) != set(roles):
            raise ValueError("FOEN split YAML membership differs from canonical table")
        for network_id, role in roles.items():
            row = yaml_rows[network_id]
            if str(row.get("role")) != role:
                raise ValueError("FOEN split YAML role differs from canonical table")
            if (
                tuple(str(item) for item in row.get("station_ids") or [])
                != canonical_stations[network_id]
            ):
                raise ValueError(
                    "FOEN split YAML station IDs differ from canonical table"
                )
            if role == SEALED_ROLE and (
                bool(row.get("never_sealed")) or bool(row.get("development_burned"))
            ):
                raise ValueError("burned FOEN network assigned sealed")

        sealed_ids = {
            network_id for network_id, role in roles.items() if role == SEALED_ROLE
        }
        if len(sealed_ids) != EXPECTED_SEALED_NETWORKS:
            raise ValueError("FOEN split must contain exactly ten sealed networks")
        if any("2016" in canonical_stations[network_id] for network_id in sealed_ids):
            raise ValueError("timestamp-probed FOEN station 2016 assigned sealed")

        catalog = _yaml_mapping(catalog_path)
        if catalog.get("catalog_id") != "foen_prospective_catalog_v1":
            raise ValueError("refusing a non-FOEN-v1 catalog")
        if (
            catalog.get("status")
            != "metadata_only_locked_before_temperature_value_query"
        ):
            raise ValueError("FOEN catalog is not a pre-value metadata lock")
        if catalog.get("temperature_values_queried") is not False:
            raise ValueError("FOEN catalog does not affirm unopened values")
        if catalog.get("coverage_fields_used_for_eligibility") is not False:
            raise ValueError("FOEN catalog used coverage fields as eligibility")
        catalog_rows = {
            str(row.get("network_id")): row for row in catalog.get("networks") or []
        }
        if set(catalog_rows) != set(roles):
            raise ValueError("FOEN catalog membership differs from split")
        for network_id, site_ids in canonical_stations.items():
            row = catalog_rows[network_id]
            if (
                tuple(str(item) for item in row.get("candidate_station_ids") or [])
                != site_ids
            ):
                raise ValueError("FOEN catalog station IDs differ from canonical split")
            if str(row.get("role")) != roles[network_id]:
                raise ValueError("FOEN catalog role differs from canonical split")
            if row.get("temperature_values_queried") is not False:
                raise ValueError("FOEN candidate claims queried values")

        start_year = _utc_year(str(contract.get("request_start")))
        end_year_exclusive = _utc_year(str(contract.get("request_end_exclusive")))
        if end_year_exclusive <= start_year:
            raise ValueError("FOEN request grid is empty")
        return cls(
            roles=roles,
            stations=canonical_stations,
            split_sha256=split_digest,
            catalog_sha256=catalog_digest,
            query_template_sha256=query_digest,
            endpoint=str(contract.get("endpoint")),
            query_template=Path(query_template_path).read_text(encoding="utf-8"),
            start_year=start_year,
            end_year_exclusive=end_year_exclusive,
        )

    def role(self, network_id: str) -> str:
        try:
            return self.roles[str(network_id)]
        except KeyError as error:
            raise ValueError(
                f"network is absent from locked FOEN split: {network_id}"
            ) from error

    def requests(self, role: str = SEALED_ROLE) -> list[FoenYearRequest]:
        if role != SEALED_ROLE:
            raise ValueError("FOEN prospective custody exposes sealed requests only")
        rows: list[FoenYearRequest] = []
        for network_id in sorted(self.roles):
            if self.roles[network_id] != role:
                continue
            for site_id in self.stations[network_id]:
                for year in range(self.start_year, self.end_year_exclusive):
                    rows.append(
                        FoenYearRequest(
                            network_id=network_id,
                            role=role,
                            site_id=site_id,
                            year=year,
                            start=f"{year:04d}-01-01T00:00:00Z",
                            end_exclusive=f"{year + 1:04d}-01-01T00:00:00Z",
                        )
                    )
        return rows

    def exact_request(
        self, network_id: str, site_id: str, year: int
    ) -> FoenYearRequest:
        if self.role(network_id) != SEALED_ROLE:
            raise FoenSealedAccessError(
                "non-sealed FOEN network has no custody request"
            )
        if str(site_id) not in self.stations.get(str(network_id), ()):
            raise ValueError("station is not a member of the locked FOEN network")
        if int(year) not in range(self.start_year, self.end_year_exclusive):
            raise ValueError("year is outside the locked FOEN request grid")
        return FoenYearRequest(
            network_id=str(network_id),
            role=SEALED_ROLE,
            site_id=str(site_id),
            year=int(year),
            start=f"{int(year):04d}-01-01T00:00:00Z",
            end_exclusive=f"{int(year) + 1:04d}-01-01T00:00:00Z",
        )


class FoenSealedCorpusGate:
    """Write-only FOEN response custody with no sealed read method."""

    def __init__(
        self,
        catalog: LockedFoenCatalog,
        *,
        sealed_vault: str | Path = DEFAULT_SEALED_VAULT,
        registry_dir: str | Path = DEFAULT_REGISTRY,
    ) -> None:
        self.catalog = catalog
        self.sealed_vault = Path(sealed_vault)
        self.registry_dir = Path(registry_dir)
        if _inside(self.registry_dir, self.sealed_vault) or _inside(
            self.sealed_vault, self.registry_dir
        ):
            raise ValueError("FOEN sealed vault and registry must be disjoint")

    def assert_qc_allowed(self, network_id: str) -> None:
        role = self.catalog.role(network_id)
        raise FoenSealedAccessError(
            f"FOEN role {role!r} has no development-time byte access: {network_id}"
        )

    def _locations(self, request: FoenYearRequest) -> tuple[Path, Path]:
        stem = f"{request.site_id}_{request.year:04d}"
        object_path = self.sealed_vault / request.network_id / f"{stem}.sealed"
        registry_path = self.registry_dir / request.network_id / f"{stem}.json"
        return object_path, registry_path

    def _base_record(self, request: FoenYearRequest) -> dict[str, Any]:
        return {
            "registry_schema": REGISTRY_SCHEMA,
            "provider": PROVIDER,
            **request.metadata(),
            "split_sha256": self.catalog.split_sha256,
            "catalog_sha256": self.catalog.catalog_sha256,
            "query_template_sha256": self.catalog.query_template_sha256,
            "storage_class": "foen_sealed_write_only_provider_vault",
            "content_parsed": False,
            "json_decoded": False,
            "value_fields_inspected": False,
            "sealed_outcomes_opened": False,
            "qc_permitted": False,
            "reused_registry": False,
        }

    def cache_stream(
        self,
        network_id: str,
        site_id: str,
        year: int,
        chunks: Iterable[bytes],
    ) -> dict[str, Any]:
        """Stream one response body to mode-000 storage without decoding it."""

        request = self.catalog.exact_request(network_id, site_id, year)
        object_path, registry_path = self._locations(request)
        if object_path.exists() or registry_path.exists():
            raise FileExistsError("immutable FOEN custody object already exists")
        self.sealed_vault.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.sealed_vault, 0o700)
        object_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(object_path.parent, 0o700)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = object_path.with_name(
            f".{object_path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
        )
        digest = hashlib.sha256()
        byte_count = 0
        try:
            with temporary.open("xb") as handle:
                os.chmod(temporary, 0o600)
                for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise TypeError("FOEN response stream must yield bytes")
                    if not chunk:
                        continue
                    handle.write(chunk)
                    digest.update(chunk)
                    byte_count += len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if byte_count < 1:
                raise ValueError("refusing to register an empty FOEN response")
            os.chmod(temporary, 0o000)
            os.replace(temporary, object_path)
        except BaseException:
            if temporary.exists():
                temporary.unlink()
            raise

        record = {
            **self._base_record(request),
            "response_sha256": digest.hexdigest(),
            "byte_count": byte_count,
        }
        temporary_registry = registry_path.with_suffix(".json.tmp")
        temporary_registry.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary_registry, registry_path)
        return record

    def resume_record(
        self, network_id: str, site_id: str, year: int
    ) -> dict[str, Any] | None:
        """Resume from strict registry and file metadata without opening bytes."""

        request = self.catalog.exact_request(network_id, site_id, year)
        object_path, registry_path = self._locations(request)
        object_exists = object_path.exists()
        registry_exists = registry_path.exists()
        if not object_exists and not registry_exists:
            return None
        if object_exists != registry_exists:
            raise FoenCustodyError(
                "FOEN object and registry must both exist or both be absent"
            )
        if object_path.is_symlink() or registry_path.is_symlink():
            raise FoenCustodyError("FOEN custody paths cannot be symlinks")
        if not object_path.is_file() or not registry_path.is_file():
            raise FoenCustodyError("FOEN custody paths must be regular files")
        try:
            record = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise FoenCustodyError(f"FOEN registry is unreadable: {error}") from error
        if not isinstance(record, dict) or set(record) != _REGISTRY_FIELDS:
            raise FoenCustodyError("FOEN registry differs from strict schema")
        expected = self._base_record(request)
        mismatched = {
            key
            for key, expected_value in expected.items()
            if record.get(key) != expected_value
        }
        if mismatched:
            raise FoenCustodyError(
                f"FOEN registry metadata mismatch: {sorted(mismatched)}"
            )
        response_sha = record.get("response_sha256")
        if not isinstance(response_sha, str) or not _SHA256.fullmatch(response_sha):
            raise FoenCustodyError("FOEN registry has invalid response SHA-256")
        byte_count = record.get("byte_count")
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 1
        ):
            raise FoenCustodyError("FOEN registry has invalid byte count")
        stat_result = object_path.stat()
        if stat_result.st_size != byte_count:
            raise FoenCustodyError("FOEN object size differs from registry")
        if stat_result.st_mode & 0o777:
            raise FoenCustodyError("FOEN sealed object is not mode 000")
        resumed = dict(record)
        resumed["reused_registry"] = True
        return resumed


def registry_manifest(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(row) for row in records]
    for row in rows:
        if set(row) != _REGISTRY_FIELDS:
            raise ValueError("FOEN registry row differs from strict custody schema")
    return {
        "manifest_schema": "foen_sealed_custody_manifest_v1",
        "provider": PROVIDER,
        "n_objects": len(rows),
        "n_reused": sum(row.get("reused_registry") is True for row in rows),
        "content_parsed": False,
        "json_decoded": False,
        "value_fields_inspected": False,
        "sealed_outcomes_opened": False,
        "contains_outcome_values": False,
        "formal_evidence": False,
        "objects": rows,
    }


__all__ = [
    "DEFAULT_CANONICAL_SPLIT",
    "DEFAULT_CATALOG",
    "DEFAULT_QUERY_TEMPLATE",
    "DEFAULT_REGISTRY",
    "DEFAULT_SEALED_VAULT",
    "DEFAULT_SPLIT",
    "EXPECTED_SEALED_NETWORKS",
    "FOEN_ENDPOINT",
    "LOCKED_CATALOG_SHA256",
    "LOCKED_QUERY_TEMPLATE_SHA256",
    "LOCKED_SPLIT_SHA256",
    "FoenCustodyError",
    "FoenSealedAccessError",
    "FoenSealedCorpusGate",
    "FoenYearRequest",
    "LockedFoenCatalog",
    "registry_manifest",
]

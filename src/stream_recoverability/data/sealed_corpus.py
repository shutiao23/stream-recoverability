"""Fail-closed byte custody for the locked catalog-v3 HUC8 split.

Development and validation objects may be opened by QC code.  Sealed objects
may only be streamed into a write-only vault.  This module intentionally
contains no dataframe, JSON-response, or temperature parser and exposes no
sealed read/unseal function.

Filesystem permissions are defense in depth, not a replacement for process
isolation.  A confirmatory evaluation must be run later under a separately
authorized unseal procedure that does not exist in this module.
"""

from __future__ import annotations

import csv
import json
import os
import re
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG = REPOSITORY_ROOT / "configs/network_catalog_v3_huc8.yaml"
DEFAULT_SPLIT = REPOSITORY_ROOT / "configs/network_catalog_v3_split.yaml"
DEFAULT_CANONICAL_SPLIT = (
    REPOSITORY_ROOT / "results/framework/public_catalog/catalog_v3_split_table.csv"
)
DEFAULT_SERIES_METADATA = (
    REPOSITORY_ROOT
    / "results/framework/public_catalog/usgs_daily_temperature_series.csv"
)
DEFAULT_READABLE_CACHE = REPOSITORY_ROOT / "data/public_rivers_v3/governed"
DEFAULT_SEALED_VAULT = REPOSITORY_ROOT / "data/sealed_public_rivers_v3/vault"
DEFAULT_REGISTRY = (
    REPOSITORY_ROOT / "results/framework/public_catalog/sealed_byte_registry_v1"
)
QC_ROLES = frozenset({"development", "validation"})
SEALED_ROLE = "sealed"
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
_REGISTRY_FIELDS = frozenset(
    {
        "registry_schema",
        "network_id",
        "role",
        "site_id",
        "request_start",
        "request_end",
        "storage_class",
        "byte_count",
        "content_parsed",
        "sealed_outcomes_opened",
        "qc_permitted",
        "reused_registry",
    }
)


class SealedOutcomeAccessError(PermissionError):
    """Raised before any sealed outcome path is opened or parsed."""


class CorpusCustodyError(RuntimeError):
    """Raised when cached bytes and their immutable registry fail closed."""


def _mapping_yaml(path: str | Path) -> dict[str, Any]:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError(f"expected YAML mapping: {path}")
    return document


def _safe_component(value: str, label: str) -> str:
    text = str(value)
    if not text or not _SAFE_COMPONENT.fullmatch(text):
        raise ValueError(f"unsafe {label}: {text!r}")
    return text


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class StationRequest:
    network_id: str
    role: str
    site_id: str
    start: str
    end: str

    def metadata(self) -> dict[str, str]:
        return {
            "network_id": self.network_id,
            "role": self.role,
            "site_id": self.site_id,
            "request_start": self.start,
            "request_end": self.end,
        }


@dataclass(frozen=True)
class LockedV3Catalog:
    """Metadata-only view of the locked v3 split and station catalog."""

    roles: Mapping[str, str]
    stations: Mapping[str, tuple[str, ...]]
    dates: Mapping[str, tuple[str, str]]

    @classmethod
    def load(
        cls,
        *,
        catalog_path: str | Path = DEFAULT_CATALOG,
        split_path: str | Path = DEFAULT_SPLIT,
        canonical_path: str | Path = DEFAULT_CANONICAL_SPLIT,
        series_metadata_path: str | Path = DEFAULT_SERIES_METADATA,
    ) -> LockedV3Catalog:
        canonical_text = Path(canonical_path).read_text(encoding="utf-8")
        split = _mapping_yaml(split_path)
        if split.get("status") != "locked_before_download":
            raise ValueError("catalog-v3 split is not locked_before_download")
        if split.get("sealed_outcomes_opened") is not False:
            raise ValueError(
                "catalog-v3 split does not affirm unopened sealed outcomes"
            )

        canonical_rows = list(csv.DictReader(canonical_text.splitlines()))
        roles: dict[str, str] = {}
        for row in canonical_rows:
            network_id = _safe_component(str(row.get("network_id") or ""), "network_id")
            role = str(row.get("role") or "")
            if network_id in roles:
                raise ValueError(f"duplicate split network: {network_id}")
            roles[network_id] = role
        yaml_roles = {
            str(row.get("network_id")): str(row.get("role"))
            for row in split.get("networks") or []
        }
        if roles != yaml_roles:
            raise ValueError("catalog-v3 YAML roles differ from canonical split table")

        catalog = _mapping_yaml(catalog_path)
        if catalog.get("catalog_id") != "network_catalog_v3_huc8":
            raise ValueError("refusing a non-v3-HUC8 catalog")
        if catalog.get("sealed_outcomes_opened") is not False:
            raise ValueError("catalog does not affirm unopened sealed outcomes")
        stations: dict[str, tuple[str, ...]] = {}
        for row in catalog.get("networks") or []:
            network_id = str(row.get("network_id") or "")
            if network_id not in roles:
                continue
            site_ids = tuple(
                _safe_component(str(value), "site_id")
                for value in row.get("candidate_station_ids") or []
            )
            if len(site_ids) < 3 or len(site_ids) != len(set(site_ids)):
                raise ValueError(f"invalid station membership for {network_id}")
            if roles[network_id] == SEALED_ROLE and bool(row.get("never_sealed")):
                raise ValueError(f"never_sealed network assigned sealed: {network_id}")
            stations[network_id] = site_ids
        missing = set(roles).difference(stations)
        # Historical/never-sealed catalog rows need no expansion route.  Every
        # executable split role must resolve to an exact HUC8 station set.
        executable_missing = {
            network_id
            for network_id in missing
            if roles[network_id] in QC_ROLES | {SEALED_ROLE}
        }
        if executable_missing:
            raise ValueError(
                "split networks absent from HUC8 station catalog: "
                f"{sorted(executable_missing)[:5]}"
            )

        dates: dict[str, tuple[str, str]] = {}
        with Path(series_metadata_path).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                site_id = str(row.get("site_id") or "")
                if site_id in dates:
                    raise ValueError(f"duplicate station metadata: {site_id}")
                dates[site_id] = (
                    str(row.get("daily_begin") or ""),
                    str(row.get("daily_end") or ""),
                )
        requested_sites = {
            site_id
            for network_id, site_ids in stations.items()
            if roles[network_id] in QC_ROLES | {SEALED_ROLE}
            for site_id in site_ids
        }
        missing_dates = requested_sites.difference(dates)
        if missing_dates:
            raise ValueError(
                f"stations missing exact request dates: {sorted(missing_dates)[:5]}"
            )
        return cls(
            roles=roles,
            stations=stations,
            dates=dates,
        )

    def role(self, network_id: str) -> str:
        try:
            return self.roles[str(network_id)]
        except KeyError as error:
            raise ValueError(
                f"network is absent from locked v3 split: {network_id}"
            ) from error

    def requests(self, role: str) -> list[StationRequest]:
        if role not in QC_ROLES | {SEALED_ROLE}:
            raise ValueError(f"role is not expandable: {role}")
        rows: list[StationRequest] = []
        for network_id in sorted(self.roles):
            if self.roles[network_id] != role:
                continue
            for site_id in self.stations[network_id]:
                start, end = self.dates[site_id]
                rows.append(StationRequest(network_id, role, site_id, start, end))
        return rows

    def exact_request(self, network_id: str, site_id: str) -> StationRequest:
        role = self.role(network_id)
        if role not in QC_ROLES | {SEALED_ROLE}:
            raise ValueError(f"network role is not expandable: {role}")
        if str(site_id) not in self.stations.get(str(network_id), ()):
            raise ValueError("station is not a member of the locked HUC8 network")
        start, end = self.dates[str(site_id)]
        return StationRequest(str(network_id), role, str(site_id), start, end)


class HUC8CorpusGate:
    """Route raw response bytes according to the immutable HUC8 split role."""

    def __init__(
        self,
        catalog: LockedV3Catalog,
        *,
        readable_cache: str | Path = DEFAULT_READABLE_CACHE,
        sealed_vault: str | Path = DEFAULT_SEALED_VAULT,
        registry_dir: str | Path = DEFAULT_REGISTRY,
    ) -> None:
        self.catalog = catalog
        self.readable_cache = Path(readable_cache)
        self.sealed_vault = Path(sealed_vault)
        self.registry_dir = Path(registry_dir)
        if _inside(self.sealed_vault, self.readable_cache) or _inside(
            self.readable_cache, self.sealed_vault
        ):
            raise ValueError("sealed vault and QC-readable cache must be disjoint")

    def assert_qc_allowed(self, network_id: str) -> str:
        role = self.catalog.role(network_id)
        if role == SEALED_ROLE:
            raise SealedOutcomeAccessError(
                f"sealed HUC8 outcomes cannot be opened during development: {network_id}"
            )
        if role not in QC_ROLES:
            raise PermissionError(f"QC is not authorized for split role {role!r}")
        return role

    def open_for_qc(self, network_id: str, path: str | Path) -> BinaryIO:
        """Open a development/validation object after role and path checks."""

        role = self.assert_qc_allowed(network_id)
        source = Path(path)
        authorized_root = self.readable_cache / role / str(network_id)
        if not _inside(source, authorized_root):
            raise PermissionError("QC path is outside its role-scoped readable cache")
        return source.open("rb")

    def open_registered_for_qc(
        self, network_id: str, site_id: str
    ) -> tuple[dict[str, Any], BinaryIO] | None:
        """Resume custody and open one registered open-role object for QC.

        Role authorization happens before registry inspection or path opening,
        so a sealed network is rejected at the first line of the access path.
        """

        self.assert_qc_allowed(network_id)
        record = self.resume_record(network_id, site_id)
        if record is None:
            return None
        request = self.catalog.exact_request(network_id, site_id)
        object_path, _ = self._locations(request)
        return record, self.open_for_qc(network_id, object_path)

    def _locations(self, request: StationRequest) -> tuple[Path, Path]:
        stem = f"{request.site_id}_{request.start}_{request.end}"
        if request.role == SEALED_ROLE:
            object_path = self.sealed_vault / request.network_id / f"{stem}.sealed"
        else:
            object_path = (
                self.readable_cache / request.role / request.network_id / f"{stem}.raw"
            )
        registry_path = (
            self.registry_dir / request.role / request.network_id / f"{stem}.json"
        )
        return object_path, registry_path

    def cache_stream(
        self, network_id: str, site_id: str, chunks: Iterable[bytes]
    ) -> dict[str, Any]:
        """Stream one provider response to an ordinary readable cache file."""
        request = self.catalog.exact_request(network_id, site_id)
        object_path, registry_path = self._locations(request)
        if object_path.exists():
            return self.resume_record(network_id, site_id)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = object_path.with_suffix(object_path.suffix + ".tmp")
        with temporary.open("wb") as handle:
            for chunk in chunks:
                handle.write(chunk)
        temporary.replace(object_path)
        record = {
            "registry_schema": "huc8_corpus_byte_registry_v1",
            **request.metadata(),
            "storage_class": "provider_cache",
            "byte_count": object_path.stat().st_size,
            "content_parsed": False,
            "sealed_outcomes_opened": False,
            "qc_permitted": request.role in QC_ROLES,
            "reused_registry": False,
        }
        registry_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record

    def resume_record(self, network_id: str, site_id: str) -> dict[str, Any] | None:
        """Reuse an existing provider response; its sidecar is optional metadata."""
        request = self.catalog.exact_request(network_id, site_id)
        object_path, registry_path = self._locations(request)
        if not object_path.exists():
            return None
        object_path.chmod(object_path.stat().st_mode | 0o600)
        record = (
            json.loads(registry_path.read_text())
            if registry_path.exists()
            else {
                "registry_schema": "huc8_corpus_byte_registry_v1",
                **request.metadata(),
                "content_parsed": False,
                "sealed_outcomes_opened": False,
                "qc_permitted": request.role in QC_ROLES,
            }
        )
        return {
            **record,
            "storage_class": "provider_cache",
            "byte_count": object_path.stat().st_size,
            "reused_registry": True,
        }


def registry_manifest(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize custody metadata without copying provider outcomes."""

    rows = [dict(row) for row in records]
    for row in rows:
        unexpected = set(row).difference(_REGISTRY_FIELDS)
        if unexpected:
            raise ValueError(
                f"registry row contains non-custody fields: {sorted(unexpected)}"
            )
    roles = {
        role: sum(row.get("role") == role for row in rows)
        for role in sorted(QC_ROLES | {SEALED_ROLE})
    }
    return {
        "manifest_schema": "huc8_corpus_custody_manifest_v1",
        "n_objects": len(rows),
        "n_reused": sum(row.get("reused_registry") is True for row in rows),
        "n_objects_by_role": roles,
        "content_parsed": False,
        "sealed_outcomes_opened": False,
        "contains_outcome_values": False,
        "formal_evidence": False,
        "objects": rows,
    }


__all__ = [
    "DEFAULT_READABLE_CACHE",
    "DEFAULT_REGISTRY",
    "DEFAULT_SEALED_VAULT",
    "QC_ROLES",
    "SEALED_ROLE",
    "CorpusCustodyError",
    "HUC8CorpusGate",
    "LockedV3Catalog",
    "SealedOutcomeAccessError",
    "StationRequest",
    "registry_manifest",
]

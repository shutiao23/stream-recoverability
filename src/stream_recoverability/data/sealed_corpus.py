"""Fail-closed byte custody for the locked catalog-v3 HUC8 split.

Development and validation objects may be opened by QC code.  Sealed objects
may only be streamed into a write-only vault while a SHA-256 digest is
calculated.  This module intentionally contains no dataframe, JSON-response,
or temperature parser and exposes no sealed read/unseal function.

Filesystem permissions are defense in depth, not a replacement for process
isolation.  A confirmatory evaluation must be run later under a separately
authorized unseal procedure that does not exist in this module.
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
    REPOSITORY_ROOT
    / "results/framework/public_catalog/sealed_byte_registry_v1"
)
LOCKED_SPLIT_SHA256 = (
    "2405169325fecaeb24bea9a5c9fc5ea66e303c14e41def1e3d32f6853679c1f1"
)
QC_ROLES = frozenset({"development", "validation"})
SEALED_ROLE = "sealed"
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REGISTRY_FIELDS = frozenset(
    {
        "registry_schema",
        "network_id",
        "role",
        "site_id",
        "request_start",
        "request_end",
        "split_sha256",
        "storage_class",
        "sha256",
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
    """Metadata-only view of the byte-verified v3 split and station catalog."""

    roles: Mapping[str, str]
    stations: Mapping[str, tuple[str, ...]]
    dates: Mapping[str, tuple[str, str]]
    split_sha256: str

    @classmethod
    def load(
        cls,
        *,
        catalog_path: str | Path = DEFAULT_CATALOG,
        split_path: str | Path = DEFAULT_SPLIT,
        canonical_path: str | Path = DEFAULT_CANONICAL_SPLIT,
        series_metadata_path: str | Path = DEFAULT_SERIES_METADATA,
        expected_sha256: str = LOCKED_SPLIT_SHA256,
    ) -> LockedV3Catalog:
        canonical_bytes = Path(canonical_path).read_bytes()
        observed = hashlib.sha256(canonical_bytes).hexdigest()
        split = _mapping_yaml(split_path)
        if observed != expected_sha256 or str(split.get("sha256")) != expected_sha256:
            raise ValueError("catalog-v3 canonical split SHA-256 mismatch")
        if split.get("status") != "locked_before_download":
            raise ValueError("catalog-v3 split is not locked_before_download")
        if split.get("sealed_outcomes_opened") is not False:
            raise ValueError("catalog-v3 split does not affirm unopened sealed outcomes")

        canonical_rows = list(
            csv.DictReader(canonical_bytes.decode("utf-8").splitlines())
        )
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
            raise ValueError(f"stations missing exact request dates: {sorted(missing_dates)[:5]}")
        return cls(
            roles=roles,
            stations=stations,
            dates=dates,
            split_sha256=observed,
        )

    def role(self, network_id: str) -> str:
        try:
            return self.roles[str(network_id)]
        except KeyError as error:
            raise ValueError(f"network is absent from locked v3 split: {network_id}") from error

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
                self.readable_cache
                / request.role
                / request.network_id
                / f"{stem}.raw"
            )
        registry_path = (
            self.registry_dir / request.role / request.network_id / f"{stem}.json"
        )
        return object_path, registry_path

    def cache_stream(
        self,
        network_id: str,
        site_id: str,
        chunks: Iterable[bytes],
    ) -> dict[str, Any]:
        """Cache an exact catalog request without parsing response bytes.

        The role is derived from the locked split, never supplied by a caller.
        Sealed bytes are hashed during the write and changed to mode ``000``
        before this method returns.  The returned registry record is a strict
        metadata whitelist and cannot contain temperature observations.
        """

        request = self.catalog.exact_request(network_id, site_id)
        object_path, registry_path = self._locations(request)
        if object_path.exists() or registry_path.exists():
            raise FileExistsError(f"immutable corpus object already exists: {site_id}")
        if request.role == SEALED_ROLE:
            self.sealed_vault.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.sealed_vault, 0o700)
        object_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if request.role == SEALED_ROLE:
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
                        raise TypeError("download stream must yield bytes")
                    if not chunk:
                        continue
                    handle.write(chunk)
                    digest.update(chunk)
                    byte_count += len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if byte_count == 0:
                raise ValueError("refusing to register an empty provider response")
            if request.role == SEALED_ROLE:
                os.chmod(temporary, 0o000)
            else:
                os.chmod(temporary, 0o600)
            os.replace(temporary, object_path)
        except BaseException:
            if temporary.exists():
                temporary.unlink()
            raise

        record: dict[str, Any] = {
            "registry_schema": "huc8_corpus_byte_registry_v1",
            **request.metadata(),
            "split_sha256": self.catalog.split_sha256,
            "storage_class": (
                "sealed_write_only_vault"
                if request.role == SEALED_ROLE
                else "role_scoped_qc_readable_cache"
            ),
            "sha256": digest.hexdigest(),
            "byte_count": byte_count,
            "content_parsed": False,
            "sealed_outcomes_opened": False,
            "qc_permitted": request.role in QC_ROLES,
            "reused_registry": False,
        }
        temporary_registry = registry_path.with_suffix(".json.tmp")
        temporary_registry.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary_registry, registry_path)
        return record

    def resume_record(
        self, network_id: str, site_id: str
    ) -> dict[str, Any] | None:
        """Reuse a valid registry without opening the cached provider object.

        The object is inspected only through filesystem metadata.  In
        particular, sealed bytes are never opened to recompute their digest;
        the append-only registry is the digest authority.  A missing half of
        the object/registry pair or any registry drift fails closed before a
        caller can issue another provider request.
        """

        request = self.catalog.exact_request(network_id, site_id)
        object_path, registry_path = self._locations(request)
        object_exists = object_path.exists()
        registry_exists = registry_path.exists()
        if not object_exists and not registry_exists:
            return None
        if object_exists != registry_exists:
            raise CorpusCustodyError(
                "cached object and registry must either both exist or both be absent"
            )
        if object_path.is_symlink() or registry_path.is_symlink():
            raise CorpusCustodyError("custody object and registry cannot be symlinks")
        if not object_path.is_file() or not registry_path.is_file():
            raise CorpusCustodyError("custody object and registry must be regular files")
        try:
            value = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CorpusCustodyError(f"custody registry is unreadable: {error}") from error
        if not isinstance(value, dict):
            raise CorpusCustodyError("custody registry must be a JSON mapping")
        if set(value) != _REGISTRY_FIELDS:
            raise CorpusCustodyError("custody registry fields differ from strict schema")

        expected = {
            "registry_schema": "huc8_corpus_byte_registry_v1",
            **request.metadata(),
            "split_sha256": self.catalog.split_sha256,
            "storage_class": (
                "sealed_write_only_vault"
                if request.role == SEALED_ROLE
                else "role_scoped_qc_readable_cache"
            ),
            "content_parsed": False,
            "sealed_outcomes_opened": False,
            "qc_permitted": request.role in QC_ROLES,
            "reused_registry": False,
        }
        mismatched = {
            key
            for key, expected_value in expected.items()
            if value.get(key) != expected_value
        }
        if mismatched:
            raise CorpusCustodyError(
                f"custody registry metadata mismatch: {sorted(mismatched)}"
            )
        digest = value.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise CorpusCustodyError("custody registry has invalid SHA-256")
        byte_count = value.get("byte_count")
        if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 1:
            raise CorpusCustodyError("custody registry has invalid byte_count")
        if object_path.stat().st_size != byte_count:
            raise CorpusCustodyError("cached object size differs from registry byte_count")
        if request.role == SEALED_ROLE:
            mode = object_path.stat().st_mode & 0o777
            if mode != 0:
                raise CorpusCustodyError("sealed cached object is not mode 000")
        resumed = dict(value)
        resumed["reused_registry"] = True
        return resumed


def registry_manifest(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize custody metadata without copying provider outcomes."""

    rows = [dict(row) for row in records]
    for row in rows:
        unexpected = set(row).difference(_REGISTRY_FIELDS)
        if unexpected:
            raise ValueError(f"registry row contains non-custody fields: {sorted(unexpected)}")
    roles = {role: sum(row.get("role") == role for row in rows) for role in sorted(QC_ROLES | {SEALED_ROLE})}
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
    "LOCKED_SPLIT_SHA256",
    "QC_ROLES",
    "SEALED_ROLE",
    "CorpusCustodyError",
    "HUC8CorpusGate",
    "LockedV3Catalog",
    "SealedOutcomeAccessError",
    "StationRequest",
    "registry_manifest",
]

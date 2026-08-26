"""Legacy-NWIS v2 M/H acquisition for the frozen open T2 corpus.

Version 1 used the modern USGS OGC daily API once per station and variable.
That transport is retained as an immutable audit, but cannot support this run
without an API key.  Version 2 uses one legacy NWIS daily-values RDB request per
network for both F and L, followed by exact station-specific frozen-window
filtering.  NASA POWER remains station-specific.

The v2 root, schemas, hashes, manifests, and attempts are independent of v1.
No v1 response or manifest is overwritten or promoted into v2.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import socket
import time
import urllib.parse
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Self

import numpy as np
import pandas as pd

from . import confirmatory as provider
from . import t2_information_corpus_acquisition as v1
from .t2_information_adapters import (
    ADAPTER_CONTRACT_VERSION,
    HYDRAULICS_VARIABLES,
    METEOROLOGY_VARIABLES,
)

CORPUS_SCHEMA_VERSION = "t2_v91_open_role_mh_corpus_acquisition_v2_5"
NETWORK_SCHEMA_VERSION = "t2_v91_open_role_mh_network_acquisition_v2_5"
LEGACY_NETWORK_SCHEMA_VERSION = "t2_v91_open_role_mh_network_acquisition_v2"
V2_1_NETWORK_SCHEMA_VERSION = "t2_v91_open_role_mh_network_acquisition_v2_1"
V2_2_NETWORK_SCHEMA_VERSION = "t2_v91_open_role_mh_network_acquisition_v2_2"
V2_3_NETWORK_SCHEMA_VERSION = "t2_v91_open_role_mh_network_acquisition_v2_3"
V2_4_NETWORK_SCHEMA_VERSION = "t2_v91_open_role_mh_network_acquisition_v2_4"
STALE_NETWORK_SCHEMA_VERSIONS = (
    LEGACY_NETWORK_SCHEMA_VERSION,
    V2_1_NETWORK_SCHEMA_VERSION,
    V2_2_NETWORK_SCHEMA_VERSION,
    V2_3_NETWORK_SCHEMA_VERSION,
    V2_4_NETWORK_SCHEMA_VERSION,
)
PLAN_SCHEMA_VERSION = "t2_v91_open_role_mh_corpus_request_plan_v2_5"
PARSER_CONTRACT_VERSION = "legacy_nwis_rdb_hydraulics_parser_v2_5"
LEGACY_PROVIDER = "usgs_legacy_nwis_dv_rdb"
LEGACY_DV_ENDPOINT = "https://waterservices.usgs.gov/nwis/dv/"
LEGACY_PARAMETERS = ("00060", "00065")
LEGACY_STATISTIC = "00003"
TERMINAL_STATUSES = ("materialized_complete", "materialized_partial")
RETRYABLE_HTTP_STATUSES = (429, 500, 502, 503, 504)
DEFAULT_REQUEST_INTERVAL_SECONDS = 3.0
DEFAULT_MAX_TRANSIENT_RETRIES = 4
DEFAULT_RETRY_BACKOFF_INITIAL_SECONDS = 15.0
DEFAULT_RETRY_BACKOFF_MAX_SECONDS = 240.0
DEFAULT_HTTP_429_COOLDOWN_SECONDS = 120.0
MAX_NETWORK_SITE_DAYS_PER_LEGACY_REQUEST = 200_000
LOCKED_PROVIDER_NONNUMERIC_CODES = ("Ice", "Eqp", "***", "Bkw", "Rat")


class ProviderCircuitOpen(RuntimeError):
    """Raised after one provider request exhausts its transient retry budget."""

    def __init__(self, message: str, *, audit: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.audit = dict(audit)


class RootExecutionLock:
    """Process-scoped advisory lock preventing concurrent writers to one v2 root."""

    def __init__(self, output: Path) -> None:
        self.path = output / ".acquisition.lock"
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.handle.seek(0)
            owner = self.handle.read().strip()
            self.handle.close()
            raise RuntimeError(
                f"another v2 acquisition writer holds {self.path}: {owner}"
            ) from error
        owner = {
            "manifest_schema": "t2_v91_open_role_mh_root_writer_lock_v1",
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(json.dumps(owner, sort_keys=True) + "\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.released = False

    def release(self) -> None:
        if self.released:
            return
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()
        self.released = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.release()

    def __del__(self) -> None:
        if hasattr(self, "released") and not self.released:
            self.release()


class _RetryableProviderFailure(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        status: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(reason)
        self.status = status
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class LegacyNetworkRequest:
    request_id: str
    network_id: str
    role: str
    site_ids: tuple[str, ...]
    start: str
    end: str
    parameter_codes: tuple[str, ...]
    statistic_code: str
    url: str
    estimated_site_days: int


@dataclass(frozen=True)
class V2NetworkPlan:
    base: v1.CorpusNetworkPlan
    legacy_requests: tuple[LegacyNetworkRequest, ...]
    network_plan_sha256: str

    @property
    def network_id(self) -> str:
        return self.base.network_id

    @property
    def role(self) -> str:
        return self.base.role

    @property
    def sites(self) -> tuple[v1.CorpusSitePlan, ...]:
        return self.base.sites


@dataclass(frozen=True)
class V2CorpusPlan:
    networks: tuple[V2NetworkPlan, ...]
    split_sha256: str
    v1_roster_plan_sha256: str
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


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": _relative(path, root),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _legacy_url(site_ids: Sequence[str], start: str, end: str) -> str:
    query = urllib.parse.urlencode(
        {
            "format": "rdb",
            "sites": ",".join(site_ids),
            "startDT": start,
            "endDT": end,
            "parameterCd": ",".join(LEGACY_PARAMETERS),
            "statCd": LEGACY_STATISTIC,
            "siteStatus": "all",
        }
    )
    return f"{LEGACY_DV_ENDPOINT}?{query}"


def _legacy_requests(network: v1.CorpusNetworkPlan) -> tuple[LegacyNetworkRequest, ...]:
    start = min(site.target_start for site in network.sites)
    end = max(site.target_end for site in network.sites)
    days = len(pd.date_range(start, end, freq="D"))
    estimated = days * len(network.sites)
    if estimated > MAX_NETWORK_SITE_DAYS_PER_LEGACY_REQUEST:
        raise ValueError(
            f"{network.network_id} exceeds the locked one-request site-day bound: {estimated}"
        )
    sites = tuple(site.site_id for site in network.sites)
    identity = {
        "network_id": network.network_id,
        "role": network.role,
        "site_ids": list(sites),
        "start": start,
        "end": end,
        "parameter_codes": list(LEGACY_PARAMETERS),
        "statistic_code": LEGACY_STATISTIC,
    }
    return (
        LegacyNetworkRequest(
            request_id=f"legacy_dv_{_sha256_bytes(_canonical_json(identity).encode())[:20]}",
            network_id=network.network_id,
            role=network.role,
            site_ids=sites,
            start=start,
            end=end,
            parameter_codes=LEGACY_PARAMETERS,
            statistic_code=LEGACY_STATISTIC,
            url=_legacy_url(sites, start, end),
            estimated_site_days=estimated,
        ),
    )


def load_v2_corpus_plan(repository_root: str | Path) -> V2CorpusPlan:
    base = v1.load_corpus_plan(repository_root)
    networks: list[V2NetworkPlan] = []
    for network in base.networks:
        requests = _legacy_requests(network)
        payload = {
            "transport_version": "legacy_nwis_dv_rdb_network_batch_v2",
            "parser_contract_version": PARSER_CONTRACT_VERSION,
            "locked_provider_nonnumeric_codes": list(
                LOCKED_PROVIDER_NONNUMERIC_CODES
            ),
            "base_network_plan_sha256": network.network_plan_sha256,
            "legacy_requests": [asdict(request) for request in requests],
            "power_transport": "nasa_power_daily_point_station_specific",
            "temperature_columns_read": [],
            "sealed_paths_traversed": False,
            "performance_metrics_computed": False,
        }
        networks.append(
            V2NetworkPlan(
                base=network,
                legacy_requests=requests,
                network_plan_sha256=_sha256_bytes(_canonical_json(payload).encode()),
            )
        )
    payload = {
        "manifest_schema": PLAN_SCHEMA_VERSION,
        "v1_roster_plan_sha256": base.plan_sha256,
        "split_sha256": base.split_sha256,
        "n_networks": len(networks),
        "n_sites": sum(len(network.sites) for network in networks),
        "n_legacy_usgs_requests": sum(
            len(network.legacy_requests) for network in networks
        ),
        "n_power_requests": sum(len(network.sites) for network in networks),
        "networks": [
            {
                "network_id": network.network_id,
                "role": network.role,
                "base_network_plan_sha256": network.base.network_plan_sha256,
                "network_plan_sha256": network.network_plan_sha256,
                "legacy_requests": [
                    asdict(request) for request in network.legacy_requests
                ],
            }
            for network in networks
        ],
        "usgs_transport": LEGACY_PROVIDER,
        "parser_contract_version": PARSER_CONTRACT_VERSION,
        "locked_provider_nonnumeric_codes": list(LOCKED_PROVIDER_NONNUMERIC_CODES),
        "legacy_batching_rule": (
            "one_request_per_network_for_00060_and_00065_when_estimated_site_days_le_200000"
        ),
        "v1_ogc_root_read_or_mutated": False,
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "performance_metrics_computed": False,
    }
    return V2CorpusPlan(
        networks=tuple(networks),
        split_sha256=base.split_sha256,
        v1_roster_plan_sha256=base.plan_sha256,
        plan_sha256=_sha256_bytes(_canonical_json(payload).encode()),
    )


def plan_as_dict(plan: V2CorpusPlan) -> dict[str, Any]:
    result = {
        "manifest_schema": PLAN_SCHEMA_VERSION,
        "v1_roster_plan_sha256": plan.v1_roster_plan_sha256,
        "split_sha256": plan.split_sha256,
        "n_networks": len(plan.networks),
        "n_sites": sum(len(network.sites) for network in plan.networks),
        "n_legacy_usgs_requests": sum(
            len(network.legacy_requests) for network in plan.networks
        ),
        "n_power_requests": sum(len(network.sites) for network in plan.networks),
        "networks": [
            {
                "network_id": network.network_id,
                "role": network.role,
                "base_network_plan_sha256": network.base.network_plan_sha256,
                "network_plan_sha256": network.network_plan_sha256,
                "legacy_requests": [
                    asdict(request) for request in network.legacy_requests
                ],
            }
            for network in plan.networks
        ],
        "usgs_transport": LEGACY_PROVIDER,
        "parser_contract_version": PARSER_CONTRACT_VERSION,
        "locked_provider_nonnumeric_codes": list(LOCKED_PROVIDER_NONNUMERIC_CODES),
        "legacy_batching_rule": (
            "one_request_per_network_for_00060_and_00065_when_estimated_site_days_le_200000"
        ),
        "v1_ogc_root_read_or_mutated": False,
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "performance_metrics_computed": False,
        "plan_sha256": plan.plan_sha256,
    }
    check = dict(result)
    check.pop("plan_sha256")
    if _sha256_bytes(_canonical_json(check).encode()) != plan.plan_sha256:
        raise AssertionError("v2 corpus plan SHA is not reproducible")
    return result


def select_networks(
    plan: V2CorpusPlan,
    *,
    network_ids: Sequence[str] = (),
    max_networks: int | None = None,
    all_networks: bool = False,
) -> tuple[V2NetworkPlan, ...]:
    modes = int(bool(network_ids)) + int(max_networks is not None) + int(all_networks)
    if modes > 1:
        raise ValueError("choose only one of network_ids, max_networks, or all_networks")
    roster = {network.network_id: network for network in plan.networks}
    if network_ids:
        requested = set(network_ids)
        missing = requested.difference(roster)
        if missing:
            raise ValueError(f"requested networks are outside the v2 plan: {sorted(missing)}")
        return tuple(network for network in plan.networks if network.network_id in requested)
    if max_networks is not None:
        if not 1 <= max_networks <= len(plan.networks):
            raise ValueError("max_networks must be inside the frozen v2 roster")
        return plan.networks[:max_networks]
    return plan.networks


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if str(key).lower() == name.lower():
            return str(value)
    return None


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = _header_value(headers, "Retry-After")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _runtime_transient(error: BaseException) -> tuple[int | None, str] | None:
    message = str(error)
    match = re.search(r"\bHTTP\s+(\d{3})\b", message, flags=re.IGNORECASE)
    if match and int(match.group(1)) in RETRYABLE_HTTP_STATUSES:
        return int(match.group(1)), message
    normalized = message.lower()
    if (
        "network failure" in normalized
        or "timed out" in normalized
        or "timeout" in normalized
        or "connection reset" in normalized
        or "temporarily unavailable" in normalized
    ):
        return None, message
    if isinstance(error, (TimeoutError, ConnectionError)):
        return None, message or type(error).__name__
    return None


class AuditedRateLimitedFetcher:
    """Global sequential rate limiter with deterministic retry and circuit break."""

    def __init__(
        self,
        fetcher: provider.HTTPFetcher,
        *,
        interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
        max_transient_retries: int = DEFAULT_MAX_TRANSIENT_RETRIES,
        backoff_initial_seconds: float = DEFAULT_RETRY_BACKOFF_INITIAL_SECONDS,
        backoff_max_seconds: float = DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
        http_429_cooldown_seconds: float = DEFAULT_HTTP_429_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if interval_seconds < 0:
            raise ValueError("request interval cannot be negative")
        if max_transient_retries < 0:
            raise ValueError("max_transient_retries cannot be negative")
        if backoff_initial_seconds < 0 or backoff_max_seconds < backoff_initial_seconds:
            raise ValueError("invalid retry backoff bounds")
        if http_429_cooldown_seconds < 0:
            raise ValueError("HTTP 429 cooldown cannot be negative")
        self.fetcher = fetcher
        self.interval_seconds = float(interval_seconds)
        self.max_transient_retries = int(max_transient_retries)
        self.backoff_initial_seconds = float(backoff_initial_seconds)
        self.backoff_max_seconds = float(backoff_max_seconds)
        self.http_429_cooldown_seconds = float(http_429_cooldown_seconds)
        self.clock = clock
        self.sleeper = sleeper
        self._last_started: float | None = None
        self._cooldown_until = 0.0
        self._circuit_audit: dict[str, Any] | None = None
        self.events: list[dict[str, Any]] = []
        self.n_base_calls = 0

    @property
    def circuit_open(self) -> bool:
        return self._circuit_audit is not None

    def _wait(self) -> None:
        now = self.clock()
        interval_ready = (
            now
            if self._last_started is None
            else self._last_started + self.interval_seconds
        )
        ready = max(interval_ready, self._cooldown_until)
        delay = ready - now
        if delay > 0:
            self.sleeper(delay)

    def _failure(
        self, response_or_error: provider.HTTPResponse | BaseException
    ) -> _RetryableProviderFailure | None:
        if isinstance(response_or_error, provider.HTTPResponse):
            if response_or_error.status not in RETRYABLE_HTTP_STATUSES:
                return None
            return _RetryableProviderFailure(
                f"HTTP {response_or_error.status}",
                status=response_or_error.status,
                retry_after_seconds=_retry_after(response_or_error.headers),
            )
        parsed = _runtime_transient(response_or_error)
        if parsed is None:
            return None
        status, reason = parsed
        return _RetryableProviderFailure(reason, status=status)

    def __call__(
        self, url: str, headers: Mapping[str, str]
    ) -> provider.HTTPResponse:
        if self._circuit_audit is not None:
            raise ProviderCircuitOpen(
                "provider circuit is already open; refusing another request",
                audit=self._circuit_audit,
            )
        for retry_index in range(self.max_transient_retries + 1):
            self._wait()
            self._last_started = self.clock()
            self.n_base_calls += 1
            try:
                response = self.fetcher(url, headers)
                failure = self._failure(response)
                if failure is None:
                    return response
            except BaseException as error:
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                failure = self._failure(error)
                if failure is None:
                    raise
            assert failure is not None
            exhausted = retry_index >= self.max_transient_retries
            exponential = min(
                self.backoff_max_seconds,
                self.backoff_initial_seconds * (2**retry_index),
            )
            cooldown = exponential
            if failure.status == 429:
                cooldown = max(cooldown, self.http_429_cooldown_seconds)
            if failure.retry_after_seconds is not None:
                cooldown = max(cooldown, failure.retry_after_seconds)
            event = {
                "event": "transient_provider_failure",
                "url": url,
                "status": failure.status,
                "reason": str(failure),
                "retry_index": retry_index,
                "attempt_number": retry_index + 1,
                "retry_budget": self.max_transient_retries,
                "cooldown_seconds": cooldown,
                "jitter_seconds": 0.0,
                "exhausted": exhausted,
            }
            self.events.append(event)
            if exhausted:
                self._circuit_audit = {
                    "state": "open",
                    "reason": "transient_retry_budget_exhausted",
                    "trigger": event,
                    "n_base_calls": self.n_base_calls,
                    "n_retry_events": len(self.events),
                }
                raise ProviderCircuitOpen(
                    "transient provider retry budget exhausted; global circuit opened",
                    audit=self._circuit_audit,
                ) from failure
            self._cooldown_until = max(self._cooldown_until, self.clock() + cooldown)
        raise AssertionError("unreachable retry loop")

    def audit(self) -> dict[str, Any]:
        return {
            "request_interval_seconds": self.interval_seconds,
            "max_transient_retries": self.max_transient_retries,
            "backoff_initial_seconds": self.backoff_initial_seconds,
            "backoff_max_seconds": self.backoff_max_seconds,
            "http_429_cooldown_seconds": self.http_429_cooldown_seconds,
            "jitter_policy": "none_deterministic",
            "n_base_calls": self.n_base_calls,
            "n_retry_events": len(self.events),
            "circuit_open": self.circuit_open,
            "circuit": self._circuit_audit,
            "events": list(self.events),
        }


def _qualifier_approved(value: str) -> bool:
    return bool(re.match(r"^A(?:$|:)", value.strip(), flags=re.IGNORECASE))


def scan_legacy_rdb_nonnumeric_codes(
    paths: Sequence[str | Path],
) -> Counter[str]:
    """Inventory every nonempty nonnumeric F/L value in raw Legacy RDB files."""

    counts: Counter[str] = Counter()
    for raw_path in sorted(Path(path) for path in paths):
        lines = raw_path.read_bytes().decode("utf-8", errors="strict").splitlines()
        index = 0
        while index < len(lines):
            if not lines[index].startswith("agency_cd\tsite_no\tdatetime"):
                index += 1
                continue
            columns = lines[index].split("\t")
            value_indices = [
                ordinal
                for ordinal, column in enumerate(columns)
                if re.fullmatch(r"[^\t]+_(00060|00065)_00003", column)
            ]
            index += 2
            while index < len(lines) and not lines[index].startswith(
                "agency_cd\tsite_no\tdatetime"
            ):
                line = lines[index]
                index += 1
                if not line or line.startswith("#"):
                    continue
                values = line.split("\t")
                if len(values) != len(columns):
                    raise ValueError(f"raw RDB row width mismatch during scan: {raw_path}")
                for ordinal in value_indices:
                    raw_text = values[ordinal].strip()
                    if not raw_text:
                        continue
                    numeric = pd.to_numeric(raw_text, errors="coerce")
                    if not np.isfinite(numeric):
                        counts[raw_text] += 1
    return counts


def parse_legacy_hydraulics_rdb(
    payload: bytes,
    request: LegacyNetworkRequest,
    *,
    response_sha256: str,
    response_artifact: str,
) -> pd.DataFrame:
    """Parse network-batched 00060/00065 daily means with strict A-only QC."""

    lines = payload.decode("utf-8", errors="strict").splitlines()
    requested = set(request.site_ids)
    specs = {spec.provider_code: spec for spec in provider.HYDROLOGY_SPECS[1:]}
    rows: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("agency_cd\tsite_no\tdatetime"):
            index += 1
            continue
        columns = lines[index].split("\t")
        value_columns: list[tuple[str, str]] = []
        for column in columns:
            match = re.fullmatch(r"([^\t]+)_(00060|00065)_00003", column)
            if match:
                qualifier = f"{column}_cd"
                if qualifier not in columns:
                    raise ValueError(f"legacy RDB value lacks qualifier column: {column}")
                value_columns.append((column, match.group(2)))
        if not value_columns:
            raise ValueError("legacy RDB data table has no requested daily-mean F/L column")
        index += 2
        while index < len(lines) and not lines[index].startswith(
            "agency_cd\tsite_no\tdatetime"
        ):
            line = lines[index]
            index += 1
            if not line or line.startswith("#"):
                continue
            values = line.split("\t")
            if len(values) != len(columns):
                raise ValueError("legacy RDB row width differs from its table header")
            record = dict(zip(columns, values, strict=True))
            site_id = str(record["site_no"]).zfill(8)
            if site_id not in requested:
                raise ValueError(f"legacy response contained unrequested site {site_id}")
            date = pd.to_datetime(record["datetime"], errors="coerce")
            if pd.isna(date):
                raise ValueError("legacy RDB contained an invalid daily date")
            date = pd.Timestamp(date).normalize()
            if not pd.Timestamp(request.start) <= date <= pd.Timestamp(request.end):
                raise ValueError("legacy RDB returned a date outside the batch request")
            for value_column, code in value_columns:
                text = record.get(value_column, "").strip()
                if not text:
                    continue
                qualifier = record.get(f"{value_column}_cd", "").strip()
                spec = specs[code]
                provider_nonnumeric = text in LOCKED_PROVIDER_NONNUMERIC_CODES
                if provider_nonnumeric:
                    raw_value = np.nan
                    approved = False
                    estimated = False
                    converted = np.nan
                    approval_status = "Provisional"
                    qc_status = "excluded_non_numeric_provider_code"
                    natural_observed = False
                else:
                    raw_value = pd.to_numeric(text, errors="coerce")
                    if not np.isfinite(raw_value):
                        raise ValueError(
                            f"legacy RDB contained unknown non-numeric provider text {text!r}"
                        )
                    approved = _qualifier_approved(qualifier)
                    natural_observed = True
                    estimated = bool(
                        re.search(
                            r"(?:^|:)E(?:$|:)", qualifier, flags=re.IGNORECASE
                        )
                    )
                    converted = (
                        float(raw_value) * spec.conversion_factor
                        if approved
                        else np.nan
                    )
                    approval_status = "Approved" if approved else "Provisional"
                    qc_status = (
                        "approved_estimated"
                        if approved and estimated
                        else "approved"
                        if approved
                        else "excluded_provisional"
                    )
                rows.append(
                    {
                        "date": date,
                        "site_id": site_id,
                        "station_id": site_id,
                        "variable": spec.variable,
                        "raw_name": code,
                        "source": LEGACY_PROVIDER,
                        "raw_text": text,
                        "source_value_original": (
                            float(raw_value) if np.isfinite(raw_value) else np.nan
                        ),
                        "raw_value": (
                            float(raw_value) if np.isfinite(raw_value) else np.nan
                        ),
                        "value": converted,
                        "raw_unit": spec.source_unit,
                        "unit": spec.unit,
                        "conversion_factor": spec.conversion_factor,
                        "unit_conversion": spec.conversion_formula,
                        "natural_observed": natural_observed,
                        "quality_approved": approved,
                        "approval_status": approval_status,
                        "qualifier_json": _canonical_json([qualifier]),
                        "estimated_qualifier": estimated,
                        "qc_status": qc_status,
                        "time_series_id": value_column.rsplit("_", maxsplit=2)[0],
                        "source_feature_id": None,
                        "source_last_modified": None,
                        "source_longitude": np.nan,
                        "source_latitude": np.nan,
                        "interpretation": spec.interpretation,
                        "quality_basis": "legacy NWIS RDB qualifier prefix A only",
                        "response_sha256": response_sha256,
                        "response_artifact": response_artifact,
                    }
                )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    duplicated = frame.duplicated(["date", "site_id", "variable"], keep=False)
    if duplicated.any():
        keys = frame.loc[duplicated, ["date", "site_id", "variable"]]
        raise ValueError(
            f"legacy RDB has ambiguous overlapping series for {len(keys)} rows"
        )
    return frame.sort_values(["site_id", "date", "variable"]).reset_index(drop=True)


def parse_legacy_network_response(
    payload: bytes,
    network: V2NetworkPlan,
    request: LegacyNetworkRequest,
    *,
    response_sha256: str,
    response_artifact: str,
) -> pd.DataFrame:
    frame = parse_legacy_hydraulics_rdb(
        payload,
        request,
        response_sha256=response_sha256,
        response_artifact=response_artifact,
    )
    if frame.empty:
        return frame
    windows = {
        site.site_id: (pd.Timestamp(site.target_start), pd.Timestamp(site.target_end))
        for site in network.sites
    }
    keep = pd.Series(False, index=frame.index)
    for site_id, (start, end) in windows.items():
        keep |= frame["site_id"].eq(site_id) & frame["date"].between(start, end)
    return frame.loc[keep].reset_index(drop=True)


def _request_identity(url: str, accept: str) -> bytes:
    return (
        _canonical_json(
            {
                "method": "GET",
                "url": url,
                "headers": {
                    "Accept": accept,
                    "User-Agent": "stream-recoverability/0.1 legacy-nwis-v2",
                },
            }
        )
        + "\n"
    ).encode()


def _fetch_legacy_request(
    output: Path,
    network: V2NetworkPlan,
    request: LegacyNetworkRequest,
    fetcher: AuditedRateLimitedFetcher,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = output / "raw/usgs_legacy" / request.request_id
    raw.mkdir(parents=True, exist_ok=True)
    request_path = raw / "request.json"
    response_path = raw / "response.rdb"
    request_bytes = _request_identity(request.url, "text/plain")
    request_path.write_bytes(request_bytes)
    headers = {
        "Accept": "text/plain",
        "User-Agent": "stream-recoverability/0.1 legacy-nwis-v2",
    }
    response = fetcher(request.url, headers)
    parsed = urllib.parse.urlsplit(response.url)
    if response.status != 200:
        raise RuntimeError(f"legacy NWIS returned non-success HTTP {response.status}")
    if parsed.scheme != "https" or parsed.netloc not in {
        "waterservices.usgs.gov",
        "nwis.waterservices.usgs.gov",
    }:
        raise ValueError(f"legacy NWIS redirected outside its official host: {response.url}")
    content_type = (_header_value(response.headers, "Content-Type") or "").lower()
    if not any(value in content_type for value in ("text/plain", "tab-separated")):
        raise ValueError(f"legacy NWIS returned unexpected content type {content_type!r}")
    response_path.write_bytes(response.body)
    response_sha = _sha256_bytes(response.body)
    response_artifact = str(response_path.relative_to(output))
    frame = parse_legacy_network_response(
        response.body,
        network,
        request,
        response_sha256=response_sha,
        response_artifact=response_artifact,
    )
    record = {
        "provider": LEGACY_PROVIDER,
        "request_kind": "network_batch_daily_values_rdb",
        "network_id": network.network_id,
        "site_ids": list(request.site_ids),
        "variables": list(HYDRAULICS_VARIABLES),
        "request_url": request.url,
        "response_url": response.url,
        "request_artifact": str(request_path.relative_to(output)),
        "response_artifact": response_artifact,
        "request_sha256": _sha256_bytes(request_bytes),
        "response_sha256": response_sha,
        "http_status": response.status,
        "content_type": _header_value(response.headers, "Content-Type"),
        "rows_after_station_window_filter": len(frame),
    }
    if _sha256_file(request_path) != record["request_sha256"]:
        raise AssertionError("legacy request identity hash changed")
    if _sha256_file(response_path) != response_sha:
        raise AssertionError("legacy raw response hash changed")
    return frame, record


def _protocol(
    network: V2NetworkPlan,
    site: v1.CorpusSitePlan,
) -> provider.ConfirmatoryProtocol:
    return provider.ConfirmatoryProtocol(
        design_path="configs/design_freeze_v9.yaml",
        design_sha256="bound_by_failure_closure_and_v2_network_plan_sha256",
        design_version="design_freeze_v9.1_information_corpus_acquisition_v2",
        network=network.network_id,
        site_ids=(site.site_id,),
        periods=(
            provider.SplitPeriod(
                "open_role_power_window", site.power_start, site.target_end
            ),
        ),
        quality_rule="POWER finite non-fill; legacy NWIS qualifier A only",
        nasa_community="AG",
        nasa_time_standard="UTC",
        nasa_spatial_rule="nearest_POWER_grid_cell_to_each_USGS_site_coordinate",
        rs_interpretation=provider.RS_INTERPRETATION,
        network_huc8=(network.network_id.removeprefix("huc8_"),),
    )


def _network_output(root: Path, network: V2NetworkPlan) -> Path:
    return root / network.role / "networks" / network.network_id


def _current_children(output: Path) -> list[Path]:
    return sorted(path for path in output.iterdir() if path.name != "attempts")


def _archive_inventory(path: Path) -> list[dict[str, Any]]:
    rows = []
    for file in sorted(value for value in path.rglob("*") if value.is_file()):
        if file.name in {"attempt_archive_manifest.json", ".archive_intent.json"}:
            continue
        rows.append(
            {
                "path": str(file.relative_to(path)),
                "bytes": file.stat().st_size,
                "sha256": _sha256_file(file),
            }
        )
    return rows


def _archive_reason(output: Path) -> str:
    manifest_path = output / "network_manifest.json"
    if not manifest_path.is_file():
        return "interrupted_missing_manifest"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") in TERMINAL_STATUSES:
        if manifest.get("manifest_schema") in STALE_NETWORK_SCHEMA_VERSIONS:
            return "terminal_rebuild_parser_contract_v2_5"
        raise ValueError("current-contract terminal output must be resumed, never archived")
    return f"nonterminal_manifest_{manifest.get('status', 'unknown')}"


def _complete_attempt_archive(
    output: Path,
    network: V2NetworkPlan,
    staging: Path,
    final: Path,
    *,
    number: int,
    reason: str,
    recovering_staging: bool = False,
) -> Path:
    intent_path = staging / ".archive_intent.json"
    if intent_path.is_file():
        intent = json.loads(intent_path.read_text(encoding="utf-8"))
        if (
            intent.get("network_id") != network.network_id
            or intent.get("role") != network.role
            or int(intent.get("attempt_number", -1)) != number
        ):
            raise ValueError(f"attempt staging intent does not match {network.network_id}")
        reason = str(intent.get("archive_reason") or reason)
        started_at = str(intent.get("archive_started_at_utc"))
    else:
        started_at = datetime.now(timezone.utc).isoformat()
        intent = {
            "manifest_schema": "t2_v91_open_role_mh_attempt_archive_intent_v2_5",
            "attempt_number": number,
            "network_id": network.network_id,
            "role": network.role,
            "network_plan_sha256": network.network_plan_sha256,
            "archive_reason": reason,
            "archive_started_at_utc": started_at,
        }
        _write_json_atomic(intent_path, intent)
    for child in _current_children(output):
        destination = staging / child.name
        if destination.exists():
            raise ValueError(
                f"attempt staging collision is retained for manual recovery: {destination}"
            )
        child.rename(destination)
    inventory = _archive_inventory(staging)
    archive_manifest = {
        "manifest_schema": "t2_v91_open_role_mh_attempt_archive_v2_5",
        "attempt_number": number,
        "network_id": network.network_id,
        "role": network.role,
        "network_plan_sha256": network.network_plan_sha256,
        "archive_reason": reason,
        "archive_started_at_utc": started_at,
        "archive_completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "recovered_from_in_progress_staging": recovering_staging,
        "n_files": len(inventory),
        "total_bytes": sum(row["bytes"] for row in inventory),
        "inventory": inventory,
        "v1_ogc_root_read_or_mutated": False,
    }
    _write_json_atomic(staging / "attempt_archive_manifest.json", archive_manifest)
    if final.exists():
        raise FileExistsError(f"completed attempt archive already exists: {final}")
    staging.rename(final)
    return final


def archive_nonterminal_attempt(output: Path, network: V2NetworkPlan) -> Path | None:
    """Complete stale staging or atomically archive every current v2 artifact."""

    output.mkdir(parents=True, exist_ok=True)
    attempts = output / "attempts"
    attempts.mkdir(exist_ok=True)
    completed_numbers = [
        int(match.group(1))
        for path in attempts.iterdir()
        if (match := re.fullmatch(r"attempt_(\d{4})", path.name))
    ]
    staging_matches = [
        (path, int(match.group(1)))
        for path in attempts.iterdir()
        if (match := re.fullmatch(r"\.attempt_(\d{4})\.in_progress", path.name))
    ]
    if len(staging_matches) > 1:
        raise ValueError("multiple in-progress attempt archives require manual audit")
    if staging_matches:
        staging, number = staging_matches[0]
        final = attempts / f"attempt_{number:04d}"
        if final.exists():
            raise ValueError("both staging and completed attempt directories exist")
        intent_path = staging / ".archive_intent.json"
        reason = (
            str(json.loads(intent_path.read_text())["archive_reason"])
            if intent_path.is_file()
            else "recovered_incomplete_attempt_archive"
        )
        return _complete_attempt_archive(
            output,
            network,
            staging,
            final,
            number=number,
            reason=reason,
            recovering_staging=True,
        )
    if not _current_children(output):
        return None
    reason = _archive_reason(output)
    number = max(completed_numbers, default=0) + 1
    final = attempts / f"attempt_{number:04d}"
    staging = attempts / f".attempt_{number:04d}.in_progress"
    if final.exists() or staging.exists():
        raise FileExistsError(f"attempt archive target already exists: {final}")
    staging.mkdir()
    return _complete_attempt_archive(
        output,
        network,
        staging,
        final,
        number=number,
        reason=reason,
    )


def _validate_terminal(
    repository_root: Path, output: Path, network: V2NetworkPlan
) -> dict[str, Any] | None:
    path = output / "network_manifest.json"
    if not path.is_file():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("manifest_schema") in STALE_NETWORK_SCHEMA_VERSIONS
        and manifest.get("status") in TERMINAL_STATUSES
    ):
        if (
            manifest.get("network_id") != network.network_id
            or manifest.get("role") != network.role
            or manifest.get("v1_ogc_root_read_or_mutated") is not False
            or manifest.get("sealed_temperature_records_read") is not False
        ):
            raise ValueError("stale v2 terminal cannot be safely bound to this network")
        return None
    if (
        manifest.get("manifest_schema") != NETWORK_SCHEMA_VERSION
        or manifest.get("network_id") != network.network_id
        or manifest.get("role") != network.role
        or manifest.get("network_plan_sha256") != network.network_plan_sha256
        or manifest.get("parser_contract_version") != PARSER_CONTRACT_VERSION
        or manifest.get("v1_ogc_root_read_or_mutated") is not False
        or manifest.get("sealed_temperature_records_read") is not False
    ):
        raise ValueError("existing v2 manifest does not match the frozen v2 plan")
    if manifest.get("status") not in TERMINAL_STATUSES:
        return None
    for artifact in manifest.get("artifacts", {}).values():
        target = repository_root / artifact["path"]
        if not target.is_file() or _sha256_file(target) != artifact["sha256"]:
            raise ValueError(f"v2 resume artifact integrity failure: {target}")
    records = json.loads((output / "raw_request_log.json").read_text())
    for record in records:
        request = output / record["request_artifact"]
        if not request.is_file() or _sha256_file(request) != record["request_sha256"]:
            raise ValueError(f"v2 resume raw request integrity failure: {request}")
        target = output / record["response_artifact"]
        if not target.is_file() or _sha256_file(target) != record["response_sha256"]:
            raise ValueError(f"v2 resume raw response integrity failure: {target}")
    return manifest


def _missing_sources(
    network: V2NetworkPlan, daily: pd.DataFrame
) -> list[dict[str, Any]]:
    present = set(
        zip(daily.get("site_id", []), daily.get("variable", []), strict=False)
    )
    rows = []
    for site in network.sites:
        for variable in (*METEOROLOGY_VARIABLES, *HYDRAULICS_VARIABLES):
            if (site.site_id, variable) not in present:
                rows.append(
                    {
                        "site_id": site.site_id,
                        "variable": variable,
                        "provider": (
                            "nasa_power_daily_point"
                            if variable in METEOROLOGY_VARIABLES
                            else LEGACY_PROVIDER
                        ),
                        "status": "source_unavailable_no_rows_in_successful_response",
                        "error_type": None,
                        "error": None,
                    }
                )
    return rows


def acquire_network(
    repository_root: str | Path,
    output_root: str | Path,
    network: V2NetworkPlan,
    *,
    fetcher: AuditedRateLimitedFetcher,
    resume: bool = True,
) -> tuple[dict[str, Any], bool]:
    root = Path(repository_root).resolve()
    output = _network_output(Path(output_root).resolve(), network)
    output.mkdir(parents=True, exist_ok=True)
    terminal = _validate_terminal(root, output, network)
    if terminal is not None:
        if not resume:
            raise FileExistsError(f"terminal v2 network exists: {output}")
        return terminal, True
    archive = archive_nonterminal_attempt(output, network)
    retry_event_start = len(fetcher.events)

    request_plan = {
        "manifest_schema": "t2_v91_open_role_mh_network_request_plan_v2",
        "network_id": network.network_id,
        "role": network.role,
        "network_plan_sha256": network.network_plan_sha256,
        "legacy_requests": [asdict(request) for request in network.legacy_requests],
        "power_requests": [
            {
                "site_id": site.site_id,
                "start": site.power_start,
                "end": site.target_end,
                "url": provider._nasa_power_url(
                    site.longitude, site.latitude, _protocol(network, site)
                ),
            }
            for site in network.sites
        ],
        "n_provider_requests": len(network.legacy_requests) + len(network.sites),
        "previous_attempt_archive": (
            str(archive.relative_to(output)) if archive is not None else None
        ),
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "performance_metrics_computed": False,
    }
    request_plan["request_plan_sha256"] = _sha256_bytes(
        _canonical_json(request_plan).encode()
    )
    request_plan_path = output / "request_plan.json"
    _write_json(request_plan_path, request_plan)

    daily_frames: list[pd.DataFrame] = []
    records: list[dict[str, Any]] = []
    power_metadata_frames: list[pd.DataFrame] = []
    for request in network.legacy_requests:
        frame, record = _fetch_legacy_request(output, network, request, fetcher)
        daily_frames.append(frame)
        records.append(record)
    for site in network.sites:
        meteorology, metadata, record = provider._fetch_power_document(
            site_id=site.site_id,
            longitude=site.longitude,
            latitude=site.latitude,
            protocol=_protocol(network, site),
            raw_root=output / "raw",
            fetcher=fetcher,
        )
        daily_frames.append(meteorology)
        power_metadata_frames.append(metadata)
        records.append(record)
    daily = pd.concat(daily_frames, ignore_index=True, sort=False)
    if not daily.empty:
        daily = daily.sort_values(["site_id", "date", "variable"]).reset_index(drop=True)
        if "raw_text" not in daily.columns:
            daily["raw_text"] = pd.NA
        missing_raw_text = daily["raw_text"].isna()
        daily.loc[missing_raw_text, "raw_text"] = daily.loc[
            missing_raw_text, "source_value_original"
        ].map(lambda value: None if pd.isna(value) else format(float(value), ".17g"))
        daily["raw_text"] = daily["raw_text"].astype("string")
    v1._validate_provider_qc(daily)
    failures = _missing_sources(network, daily)
    coverage = v1._coverage(network.base, daily, failures)
    power_metadata = pd.concat(power_metadata_frames, ignore_index=True)

    paths = {
        "daily_long_auxiliary": output / "daily_long_auxiliary.parquet",
        "coverage": output / "coverage.csv",
        "power_point_metadata": output / "power_point_metadata.csv",
        "raw_request_log": output / "raw_request_log.json",
        "source_failures": output / "source_failures.json",
        "adapter_schema": output / "adapter_schema.json",
        "request_plan": request_plan_path,
    }
    daily.to_parquet(paths["daily_long_auxiliary"], index=False)
    coverage.to_csv(paths["coverage"], index=False)
    power_metadata.to_csv(paths["power_point_metadata"], index=False)
    _write_json(paths["raw_request_log"], records)
    _write_json(paths["source_failures"], failures)
    _write_json(
        paths["adapter_schema"],
        {
            "adapter_contract_version": ADAPTER_CONTRACT_VERSION,
            "acquisition_schema": NETWORK_SCHEMA_VERSION,
            "parser_contract_version": PARSER_CONTRACT_VERSION,
            "table": "daily_long_auxiliary.parquet",
            "variables": {
                "M": list(METEOROLOGY_VARIABLES),
                "H": list(HYDRAULICS_VARIABLES),
            },
            "providers": {"M": "nasa_power_daily_point", "H": LEGACY_PROVIDER},
            "legacy_approval_policy": "qualifier prefix A only; all other finite rows retained with value NA",
            "legacy_nonnumeric_policy": {
                "locked_codes": list(LOCKED_PROVIDER_NONNUMERIC_CODES),
                "raw_text_column": "raw_text",
                "value_policy": "value_and_raw_value_NA_quality_not_approved",
                "qc_status": "excluded_non_numeric_provider_code",
                "unknown_nonempty_text": "fail_closed",
            },
            "legacy_unit_conversion": {
                "F": "ft3_per_s * 0.028316846592",
                "L": "ft * 0.3048",
            },
            "missing_source_policy": "record_failure_and_leave_absent_no_fill",
            "v1_ogc_root_read_or_mutated": False,
        },
    )
    artifacts = {name: _artifact(path, root) for name, path in paths.items()}
    status = "materialized_complete" if not failures else "materialized_partial"
    manifest = {
        "manifest_schema": NETWORK_SCHEMA_VERSION,
        "status": status,
        "acquisition_terminal": True,
        "network_id": network.network_id,
        "role": network.role,
        "split_sha256": network.base.split_sha256,
        "network_plan_sha256": network.network_plan_sha256,
        "base_v1_roster_network_plan_sha256": network.base.network_plan_sha256,
        "parser_contract_version": PARSER_CONTRACT_VERSION,
        "locked_provider_nonnumeric_codes": list(LOCKED_PROVIDER_NONNUMERIC_CODES),
        "n_sites": len(network.sites),
        "site_ids": [site.site_id for site in network.sites],
        "n_auxiliary_rows": len(daily),
        "n_source_failures_or_unavailable": len(failures),
        "source_failure_status_counts": dict(
            sorted(Counter(row["status"] for row in failures).items())
        ),
        "n_raw_responses": len(records),
        "raw_response_sha256": [record["response_sha256"] for record in records],
        "raw_response_hashes_complete_for_logged_responses": all(
            bool(record.get("response_sha256")) for record in records
        ),
        "provider_request_counts": {
            LEGACY_PROVIDER: len(network.legacy_requests),
            "nasa_power_daily_point": len(network.sites),
        },
        "provider_qc": {
            "POWER": "finite and not provider fill_value",
            "USGS_LEGACY": "RDB qualifier prefix A only; P/other retained as NA",
        },
        "retry_audit": fetcher.events[retry_event_start:],
        "previous_attempt_archive": request_plan["previous_attempt_archive"],
        "artifacts": artifacts,
        "v1_ogc_root_read_or_mutated": False,
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "performance_metrics_computed": False,
        "network_interval_reported": False,
        "formal_evidence": False,
        "purpose": "legacy_transport_auxiliary_materialization_not_performance_evidence",
        "passed": False,
    }
    _write_json(output / "network_manifest.json", manifest)
    if _validate_terminal(root, output, network) is None:
        raise AssertionError("v2 network failed to form a terminal resume boundary")
    return manifest, False


def _global_attrition(
    repository_root: Path, output_root: Path, plan: V2CorpusPlan
) -> tuple[Path, Path, dict[str, Any]]:
    rows = []
    for network in plan.networks:
        output = _network_output(output_root, network)
        terminal = _validate_terminal(repository_root, output, network)
        row = {
            "network_id": network.network_id,
            "role": network.role,
            "n_sites_planned": len(network.sites),
            "network_plan_sha256": network.network_plan_sha256,
            "materialization_status": "not_materialized",
            "n_auxiliary_rows": 0,
            "n_source_failures_or_unavailable": 0,
            "n_attempt_archives": len(list((output / "attempts").glob("attempt_*"))),
        }
        if terminal is not None:
            row.update(
                {
                    "materialization_status": terminal["status"],
                    "n_auxiliary_rows": terminal["n_auxiliary_rows"],
                    "n_source_failures_or_unavailable": terminal[
                        "n_source_failures_or_unavailable"
                    ],
                }
            )
        elif output.is_dir() and _current_children(output):
            manifest_path = output / "network_manifest.json"
            existing_manifest = (
                json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
            )
            if (
                existing_manifest.get("manifest_schema")
                in STALE_NETWORK_SCHEMA_VERSIONS
                and existing_manifest.get("status") in TERMINAL_STATUSES
            ):
                row["materialization_status"] = "stale_terminal_rebuild_required"
            else:
                row["materialization_status"] = "interrupted_nonterminal"
        rows.append(row)
    frame = pd.DataFrame(rows)
    csv_path = output_root / "global_attrition.csv"
    frame.to_csv(csv_path, index=False)
    terminal = frame["materialization_status"].isin(TERMINAL_STATUSES)
    summary = {
        "manifest_schema": "t2_v91_open_role_mh_global_attrition_v2",
        "plan_sha256": plan.plan_sha256,
        "n_networks_planned": len(frame),
        "n_networks_materialized": int(terminal.sum()),
        "n_networks_remaining": int((~terminal).sum()),
        "n_attempt_archives": int(frame["n_attempt_archives"].sum()),
        "materialization_status_counts": dict(
            sorted(frame["materialization_status"].value_counts().astype(int).items())
        ),
        "n_source_failures_or_unavailable": int(
            frame["n_source_failures_or_unavailable"].sum()
        ),
        "v1_ogc_root_read_or_mutated": False,
        "temperature_columns_read": [],
        "sealed_temperature_records_read": False,
        "performance_metrics_computed": False,
        "passed": False,
    }
    summary_path = output_root / "global_attrition_summary.json"
    _write_json(summary_path, summary)
    return csv_path, summary_path, summary


def _archive_previous_root_state(output: Path) -> dict[str, Any] | None:
    state_path = output / "root_execution_manifest.json"
    if not state_path.is_file():
        return None
    payload = state_path.read_bytes()
    history = output / "root_run_history"
    history.mkdir(exist_ok=True)
    existing = [
        int(match.group(1))
        for path in history.iterdir()
        if (match := re.fullmatch(r"run_(\d{4})\.json", path.name))
    ]
    number = max(existing, default=0) + 1
    destination = history / f"run_{number:04d}.json"
    temporary = history / f".run_{number:04d}.json.partial"
    temporary.write_bytes(payload)
    temporary.replace(destination)
    return {
        "path": str(destination.relative_to(output)),
        "sha256": _sha256_bytes(payload),
        "bytes": len(payload),
    }


def run_v2_corpus_acquisition(
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
    request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
    max_transient_retries: int = DEFAULT_MAX_TRANSIENT_RETRIES,
    retry_backoff_initial_seconds: float = DEFAULT_RETRY_BACKOFF_INITIAL_SECONDS,
    retry_backoff_max_seconds: float = DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
    http_429_cooldown_seconds: float = DEFAULT_HTTP_429_COOLDOWN_SECONDS,
    fetcher: provider.HTTPFetcher = provider.urlopen_fetcher,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    output = Path(output_root).resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan = load_v2_corpus_plan(root)
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
                    f"all-network execution requires acknowledgement {len(plan.networks)}"
                )
        else:
            if not network_ids and max_networks is None:
                raise ValueError("execution requires explicit bounded selection or --all")
            if acknowledged_network_count != len(selected):
                raise ValueError(
                    f"bounded execution requires acknowledgement {len(selected)}"
                )
    root_lock = RootExecutionLock(output) if execute else None
    plan_path = output / "corpus_request_plan.json"
    _write_json(plan_path, plan_as_dict(plan))
    selected_plan = {
        "manifest_schema": "t2_v91_open_role_mh_selected_run_plan_v2",
        "corpus_plan_sha256": plan.plan_sha256,
        "selected_network_ids": [network.network_id for network in selected],
        "n_networks_selected": len(selected),
        "execute": execute,
        "sequential_execution": True,
        "parallel_workers": 1,
        "retry_policy": {
            "request_interval_seconds": request_interval_seconds,
            "max_transient_retries": max_transient_retries,
            "backoff_initial_seconds": retry_backoff_initial_seconds,
            "backoff_max_seconds": retry_backoff_max_seconds,
            "http_429_cooldown_seconds": http_429_cooldown_seconds,
            "jitter": "none",
            "exhaustion": "global_circuit_break_and_stop_run",
        },
        "scope_acknowledgement": {
            "mode": "all" if all_networks else "bounded" if execute else "not_required",
            "expected": len(selected),
            "provided": (
                acknowledge_all_network_count
                if all_networks
                else acknowledged_network_count
                if execute
                else None
            ),
        },
        "v1_ogc_root_read_or_mutated": False,
    }
    selected_plan["selected_plan_sha256"] = _sha256_bytes(
        _canonical_json(selected_plan).encode()
    )
    selected_path = output / "selected_run_plan.json"
    _write_json(selected_path, selected_plan)
    root_state_path = output / "root_execution_manifest.json"
    root_started_at: str | None = None
    previous_root_state: dict[str, Any] | None = None
    if execute:
        previous_root_state = _archive_previous_root_state(output)
        root_started_at = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(
            root_state_path,
            {
                "manifest_schema": "t2_v91_open_role_mh_root_execution_state_v2_5",
                "status": "in_progress",
                "started_at_utc": root_started_at,
                "corpus_plan_sha256": plan.plan_sha256,
                "selected_plan_sha256": selected_plan["selected_plan_sha256"],
                "selected_network_ids": [
                    network.network_id for network in selected
                ],
                "n_networks_selected": len(selected),
                "previous_root_state": previous_root_state,
                "v1_ogc_root_read_or_mutated": False,
                "sealed_temperature_records_read": False,
                "performance_metrics_computed": False,
            },
        )
    limited = AuditedRateLimitedFetcher(
        fetcher,
        interval_seconds=request_interval_seconds,
        max_transient_retries=max_transient_retries,
        backoff_initial_seconds=retry_backoff_initial_seconds,
        backoff_max_seconds=retry_backoff_max_seconds,
        http_429_cooldown_seconds=http_429_cooldown_seconds,
        clock=clock,
        sleeper=sleeper,
    )
    results: list[dict[str, Any]] = []
    stop: dict[str, Any] | None = None
    if execute:
        for network in selected:
            try:
                manifest, resumed = acquire_network(
                    root, output, network, fetcher=limited, resume=resume
                )
            except ProviderCircuitOpen as error:
                stop = {
                    "reason": "provider_circuit_open",
                    "network_id": network.network_id,
                    "error": str(error),
                    "circuit": error.audit,
                }
                break
            except Exception as error:  # noqa: BLE001
                stop = {
                    "reason": "network_acquisition_error",
                    "network_id": network.network_id,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
                break
            results.append(
                {
                    "network_id": network.network_id,
                    "status": manifest["status"],
                    "resumed": resumed,
                }
            )
    attrition_path, attrition_summary_path, attrition = _global_attrition(
        root, output, plan
    )
    status = (
        "dry_run"
        if not execute
        else "execution_stopped_fail_closed"
        if stop is not None
        else "execution_complete_for_selected_scope"
    )
    manifest = {
        "manifest_schema": CORPUS_SCHEMA_VERSION,
        "status": status,
        "execute": execute,
        "dry_run": not execute,
        "corpus_plan_sha256": plan.plan_sha256,
        "selected_plan_sha256": selected_plan["selected_plan_sha256"],
        "n_networks_in_frozen_roster": len(plan.networks),
        "n_sites_in_frozen_roster": sum(len(network.sites) for network in plan.networks),
        "n_networks_selected": len(selected),
        "n_networks_executed_or_resumed": len(results),
        "n_networks_executed_now": sum(not row["resumed"] for row in results),
        "n_networks_resumed": sum(row["resumed"] for row in results),
        "stop": stop,
        "results": results,
        "provider_transport_audit": limited.audit(),
        "global_attrition": attrition,
        "artifacts": {
            "corpus_request_plan": _artifact(plan_path, root),
            "selected_run_plan": _artifact(selected_path, root),
            "global_attrition": _artifact(attrition_path, root),
            "global_attrition_summary": _artifact(attrition_summary_path, root),
        },
        "v1_ogc_root_read_or_mutated": False,
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "performance_metrics_computed": False,
        "network_interval_reported": False,
        "formal_evidence": False,
        "passed": False,
    }
    _write_json(output / "run_manifest.json", manifest)
    if execute:
        _write_json_atomic(
            root_state_path,
            {
                "manifest_schema": "t2_v91_open_role_mh_root_execution_state_v2_5",
                "status": status,
                "started_at_utc": root_started_at,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "corpus_plan_sha256": plan.plan_sha256,
                "selected_plan_sha256": selected_plan["selected_plan_sha256"],
                "n_networks_selected": len(selected),
                "n_networks_executed_now": manifest["n_networks_executed_now"],
                "n_networks_resumed": manifest["n_networks_resumed"],
                "stop": stop,
                "provider_transport_audit": limited.audit(),
                "previous_root_state": previous_root_state,
                "run_manifest": _artifact(output / "run_manifest.json", root),
                "v1_ogc_root_read_or_mutated": False,
                "sealed_temperature_records_read": False,
                "performance_metrics_computed": False,
            },
        )
        assert root_lock is not None
        root_lock.release()
    return manifest


def compare_v2_to_v1_ogc(
    repository_root: str | Path,
    v2_output_root: str | Path,
    network_id: str,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Compare approved v2 legacy H against an already successful v1 OGC network."""

    root = Path(repository_root).resolve()
    plan = load_v2_corpus_plan(root)
    matches = [network for network in plan.networks if network.network_id == network_id]
    if len(matches) != 1:
        raise ValueError(f"network is not in the v2 roster: {network_id}")
    network = matches[0]
    v1_path = (
        root
        / "data_versions/global_network_corpus_v1/open_role_auxiliary/failure_closure6"
        / network.role
        / "networks"
        / network_id
        / "daily_long_auxiliary.parquet"
    )
    v2_path = _network_output(Path(v2_output_root).resolve(), network) / "daily_long_auxiliary.parquet"
    if not v1_path.is_file() or not v2_path.is_file():
        raise FileNotFoundError("both v1 OGC and v2 legacy network products are required")

    def eligible(path: Path, source: str) -> pd.DataFrame:
        frame = pd.read_parquet(
            path,
            columns=[
                "date",
                "site_id",
                "variable",
                "value",
                "source",
                "approval_status",
                "quality_approved",
            ],
        )
        frame = frame.loc[
            frame["source"].eq(source)
            & frame["variable"].isin(HYDRAULICS_VARIABLES)
            & frame["approval_status"].eq("Approved")
            & frame["quality_approved"].astype(bool)
            & pd.to_numeric(frame["value"], errors="coerce").notna()
        ].copy()
        frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
        return frame[["date", "site_id", "variable", "value"]]

    ogc = eligible(v1_path, "usgs_ogc_daily").rename(columns={"value": "ogc_value"})
    legacy = eligible(v2_path, LEGACY_PROVIDER).rename(columns={"value": "legacy_value"})
    comparison = ogc.merge(
        legacy,
        on=["date", "site_id", "variable"],
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    both = comparison["_merge"].eq("both")
    comparison["absolute_difference"] = (
        comparison["ogc_value"] - comparison["legacy_value"]
    ).abs()
    comparison["exact_match"] = both & np.isclose(
        comparison["ogc_value"], comparison["legacy_value"], rtol=0.0, atol=1e-12
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "legacy_vs_ogc_daily_hydraulics.csv"
    comparison.to_csv(csv_path, index=False)
    n_ogc = len(ogc)
    n_ogc_missing = int(comparison["_merge"].eq("left_only").sum())
    n_overlap = int(both.sum())
    n_exact = int(comparison.loc[both, "exact_match"].sum())
    result = {
        "manifest_schema": "t2_v91_legacy_vs_ogc_transport_regression_v1",
        "network_id": network_id,
        "n_ogc_approved_rows": n_ogc,
        "n_legacy_approved_rows": len(legacy),
        "n_overlap_rows": n_overlap,
        "n_exact_value_matches": n_exact,
        "n_ogc_rows_missing_from_legacy": n_ogc_missing,
        "n_legacy_rows_not_in_ogc": int(comparison["_merge"].eq("right_only").sum()),
        "max_absolute_difference": (
            float(comparison.loc[both, "absolute_difference"].max())
            if n_overlap
            else None
        ),
        "passed": bool(n_ogc > 0 and n_ogc_missing == 0 and n_exact == n_overlap),
        "comparison": _artifact(csv_path, root),
        "v1_read_for_transport_regression_only": True,
        "v1_mutated": False,
        "temperature_columns_read": [],
        "sealed_temperature_records_read": False,
        "performance_metrics_computed": False,
    }
    _write_json(output / "transport_regression_manifest.json", result)
    return result


__all__ = [
    "CORPUS_SCHEMA_VERSION",
    "LEGACY_PROVIDER",
    "NETWORK_SCHEMA_VERSION",
    "AuditedRateLimitedFetcher",
    "ProviderCircuitOpen",
    "RootExecutionLock",
    "V2CorpusPlan",
    "V2NetworkPlan",
    "acquire_network",
    "archive_nonterminal_attempt",
    "compare_v2_to_v1_ogc",
    "load_v2_corpus_plan",
    "parse_legacy_hydraulics_rdb",
    "parse_legacy_network_response",
    "plan_as_dict",
    "run_v2_corpus_acquisition",
    "scan_legacy_rdb_nonnumeric_codes",
]

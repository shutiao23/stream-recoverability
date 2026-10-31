"""Provider parsers and network QC for the sealed T2/T7 temperature objects.

Registered objects are replayed from the locked HUC8 and FOEN catalogs and
their public registry sidecars, read from the vault, parsed into
provider-neutral rows, and passed through station and network QC.  The same
parsers and QC also run on in-memory synthetic fixtures.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.data.foen_sealed_corpus import (
    DEFAULT_REGISTRY as DEFAULT_FOEN_REGISTRY,
)
from stream_recoverability.data.foen_sealed_corpus import (
    DEFAULT_SEALED_VAULT as DEFAULT_FOEN_VAULT,
)
from stream_recoverability.data.foen_sealed_corpus import LockedFoenCatalog
from stream_recoverability.data.ingest_qc import (
    VERDICT_ACCEPTED,
    VERDICT_ACCEPTED_WITH_FLAGS,
    qc_station_series,
)
from stream_recoverability.data.sealed_corpus import (
    DEFAULT_REGISTRY as DEFAULT_HUC8_REGISTRY,
)
from stream_recoverability.data.sealed_corpus import (
    DEFAULT_SEALED_VAULT as DEFAULT_HUC8_VAULT,
)
from stream_recoverability.data.sealed_corpus import LockedV3Catalog

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_RESULT_SCHEMA = "t2_t7_synthetic_fixture_qc_result_v1"
PRODUCTION_RESULT_SCHEMA = "t2_t7_sealed_qc_result_v1"
DEFAULT_SEALED_QC_OUTPUT = (
    REPOSITORY_ROOT / "results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1"
)
EXPECTED_SEALED_NETWORKS = 54
EXPECTED_SEALED_OBJECTS = 2880
_ACCEPTED_VERDICTS = frozenset({VERDICT_ACCEPTED, VERDICT_ACCEPTED_WITH_FLAGS})
_PANEL_COLUMNS = [
    "site_id",
    "date",
    "temperature_c",
    "approval_code",
    "provider",
    "network_id",
]


class SealedEvaluatorError(RuntimeError):
    """Raised when a registered object cannot be read, parsed, or replayed."""


@dataclass(frozen=True)
class SealedObjectRef:
    """Opaque object identity derived from a public strict-registry sidecar."""

    provider: str
    network_id: str
    site_id: str
    request_year: int | None
    expected_byte_count: int
    request_start: str | None = None
    request_end: str | None = None
    request_end_inclusive: bool = False

    @property
    def key(self) -> str:
        year = "all" if self.request_year is None else str(self.request_year)
        return f"{self.provider}/{self.network_id}/{self.site_id}/{year}"


class MemorySealedObjectReader:
    """Fixture-only reader; it has no filesystem path or vault knowledge."""

    def __init__(self, objects: Mapping[str, bytes]) -> None:
        self._objects = dict(objects)
        self.read_keys: list[str] = []

    def read_object(self, reference: SealedObjectRef) -> bytes:
        if reference.key in self.read_keys:
            raise SealedEvaluatorError("mock object requested more than once")
        self.read_keys.append(reference.key)
        try:
            return self._objects[reference.key]
        except KeyError as error:
            raise SealedEvaluatorError(
                f"mock object is absent: {reference.key}"
            ) from error


def _date_only(value: str | None) -> str:
    if not value:
        return ""
    return str(value)[:10]


def vault_path_for_reference(
    reference: SealedObjectRef,
    *,
    huc8_vault: Path = DEFAULT_HUC8_VAULT,
    foen_vault: Path = DEFAULT_FOEN_VAULT,
) -> Path:
    """Resolve one locked registry object to its immutable vault path."""

    if reference.provider == "usgs_nwis":
        start = _date_only(reference.request_start)
        end = _date_only(reference.request_end)
        stem = f"{reference.site_id}_{start}_{end}"
        return huc8_vault / reference.network_id / f"{stem}.sealed"
    if reference.provider == "foen":
        if reference.request_year is None:
            raise SealedEvaluatorError("FOEN reference lacks request_year")
        stem = f"{reference.site_id}_{reference.request_year:04d}"
        return foen_vault / reference.network_id / f"{stem}.sealed"
    raise SealedEvaluatorError(f"unsupported sealed provider: {reference.provider}")


class FilesystemSealedObjectReader:
    """Vault reader for registered sealed objects."""

    def __init__(
        self,
        *,
        huc8_vault: str | Path = DEFAULT_HUC8_VAULT,
        foen_vault: str | Path = DEFAULT_FOEN_VAULT,
    ) -> None:
        self.huc8_vault = Path(huc8_vault)
        self.foen_vault = Path(foen_vault)
        self.read_keys: list[str] = []

    def read_object(self, reference: SealedObjectRef) -> bytes:
        object_path = vault_path_for_reference(
            reference,
            huc8_vault=self.huc8_vault,
            foen_vault=self.foen_vault,
        )
        if not object_path.is_file():
            raise SealedEvaluatorError(f"sealed vault object missing: {reference.key}")
        if not os.access(object_path, os.R_OK):
            os.chmod(object_path, object_path.stat().st_mode | 0o600)
        body = object_path.read_bytes()
        if reference.key not in self.read_keys:
            self.read_keys.append(reference.key)
        return body


def _load_mapping(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SealedEvaluatorError(f"required metadata is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SealedEvaluatorError(f"cannot read metadata {path}: {error}") from error
    if not isinstance(value, dict):
        raise SealedEvaluatorError(f"metadata is not a mapping: {path}")
    return value


def _registry_rows(root: Path) -> list[dict[str, Any]]:
    if root.is_symlink() or not root.is_dir():
        raise SealedEvaluatorError(f"registry root is not a regular directory: {root}")
    return [_load_mapping(path) for path in sorted(root.glob("*/*.json"))]


def _registered_byte_count(row: Mapping[str, Any]) -> int:
    value = row.get("byte_count")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SealedEvaluatorError("registry row has an invalid byte_count")
    return value


def registered_object_references(
    *,
    huc8_registry_root: str | Path = DEFAULT_HUC8_REGISTRY / "sealed",
    foen_registry_root: str | Path = DEFAULT_FOEN_REGISTRY,
) -> tuple[SealedObjectRef, ...]:
    """Replay both locked catalogs and their registry sidecars into references."""

    huc8_catalog = LockedV3Catalog.load()
    huc8_expected = {
        (request.network_id, request.site_id): request
        for request in huc8_catalog.requests("sealed")
    }
    huc8_rows = _registry_rows(Path(huc8_registry_root))
    huc8_identities = [
        (str(row.get("network_id")), str(row.get("site_id"))) for row in huc8_rows
    ]
    if len(set(huc8_identities)) != len(huc8_identities) or set(huc8_identities) != set(
        huc8_expected
    ):
        raise SealedEvaluatorError(
            "HUC8 registry is not the complete locked request set"
        )

    foen_catalog = LockedFoenCatalog.load()
    foen_expected = {
        (request.network_id, request.site_id, request.year): request
        for request in foen_catalog.requests()
    }
    foen_rows = _registry_rows(Path(foen_registry_root))
    try:
        foen_identities = [
            (
                str(row.get("network_id")),
                str(row.get("site_id")),
                int(row["request_year"]),
            )
            for row in foen_rows
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise SealedEvaluatorError(
            "FOEN registry row lacks a valid request_year"
        ) from error
    if len(set(foen_identities)) != len(foen_identities) or set(foen_identities) != set(
        foen_expected
    ):
        raise SealedEvaluatorError(
            "FOEN registry is not the complete locked request set"
        )

    references: list[SealedObjectRef] = []
    for row, identity in zip(huc8_rows, huc8_identities):
        request = huc8_expected[identity]
        references.append(
            SealedObjectRef(
                provider="usgs_nwis",
                network_id=request.network_id,
                site_id=request.site_id,
                request_year=None,
                expected_byte_count=_registered_byte_count(row),
                request_start=request.start,
                request_end=request.end,
                request_end_inclusive=True,
            )
        )
    for row, identity in zip(foen_rows, foen_identities):
        request = foen_expected[identity]
        references.append(
            SealedObjectRef(
                provider="foen",
                network_id=request.network_id,
                site_id=request.site_id,
                request_year=request.year,
                expected_byte_count=_registered_byte_count(row),
                request_start=request.start,
                request_end=request.end_exclusive,
                request_end_inclusive=False,
            )
        )
    keys = [reference.key for reference in references]
    if len(keys) != len(set(keys)):
        raise SealedEvaluatorError("duplicate sealed object registry identity")
    n_networks = len({(ref.provider, ref.network_id) for ref in references})
    if n_networks != EXPECTED_SEALED_NETWORKS:
        raise SealedEvaluatorError(
            f"sealed candidate inventory must contain {EXPECTED_SEALED_NETWORKS} networks"
        )
    if len(references) != EXPECTED_SEALED_OBJECTS:
        raise SealedEvaluatorError(
            f"sealed registry replay did not yield {EXPECTED_SEALED_OBJECTS} objects"
        )
    return tuple(references)


def _timestamp_in_request(
    value: object,
    *,
    request_start: str | None,
    request_end: str | None,
    request_end_inclusive: bool,
) -> pd.Timestamp:
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")
    if not isinstance(timestamp, pd.Timestamp) or pd.isna(timestamp):
        raise SealedEvaluatorError("provider row has an invalid timestamp")
    if request_start is not None:
        start = pd.to_datetime(request_start, utc=True, errors="coerce")
        if not isinstance(start, pd.Timestamp) or pd.isna(start) or timestamp < start:
            raise SealedEvaluatorError("provider timestamp precedes request range")
    if request_end is not None:
        end = pd.to_datetime(request_end, utc=True, errors="coerce")
        if not isinstance(end, pd.Timestamp) or pd.isna(end):
            raise SealedEvaluatorError("request range has an invalid end")
        if request_end_inclusive:
            if timestamp.normalize() > end.normalize():
                raise SealedEvaluatorError("provider timestamp follows request range")
        elif timestamp >= end:
            raise SealedEvaluatorError("provider timestamp follows request range")
    return timestamp


def parse_huc8_nwis_response(
    payload: bytes,
    *,
    site_id: str,
    request_start: str | None = None,
    request_end: str | None = None,
) -> pd.DataFrame:
    """Parse one NWIS JSON response into the provider-neutral QC columns."""

    try:
        document = json.loads(payload.decode("utf-8"))
        series = document["value"]["timeSeries"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise SealedEvaluatorError("invalid NWIS JSON response") from error
    rows: list[dict[str, Any]] = []
    if not isinstance(series, list):
        raise SealedEvaluatorError("NWIS timeSeries is not a list")
    for item in series:
        if not isinstance(item, Mapping):
            raise SealedEvaluatorError("NWIS timeSeries row is not a mapping")
        source = item.get("sourceInfo") or {}
        codes = source.get("siteCode") or []
        observed_site = str((codes[0] if codes else {}).get("value", ""))
        variable = item.get("variable") or {}
        variable_codes = variable.get("variableCode") or []
        parameters = {str(code.get("value", "")) for code in variable_codes}
        if observed_site != str(site_id) or "00010" not in parameters:
            raise SealedEvaluatorError("NWIS response identity/parameter mismatch")
        unit = str((variable.get("unit") or {}).get("unitCode", ""))
        normalized_unit = (
            unit.strip().lower().replace("°", "").replace("degrees", "deg")
        )
        if normalized_unit not in {"deg c", "degc", "c", "celsius"}:
            raise SealedEvaluatorError("NWIS temperature unit is not Celsius")
        options = (variable.get("options") or {}).get("option") or []
        statistics = {
            str(option.get("optionCode", ""))
            for option in options
            if isinstance(option, Mapping)
            and str(option.get("name", "")).strip().lower() == "statistic"
        }
        if "00003" not in statistics:
            raise SealedEvaluatorError(
                "NWIS response is not daily mean statistic 00003"
            )
        for block in item.get("values") or []:
            for point in block.get("value") or []:
                if not isinstance(point, Mapping):
                    raise SealedEvaluatorError("NWIS value row is not a mapping")
                timestamp = _timestamp_in_request(
                    point.get("dateTime"),
                    request_start=request_start,
                    request_end=request_end,
                    request_end_inclusive=True,
                )
                rows.append(
                    {
                        "site_id": str(site_id),
                        "date": timestamp,
                        "temperature_c": point.get("value"),
                        "approval_code": ",".join(
                            str(value) for value in (point.get("qualifiers") or [])
                        ),
                    }
                )
    return _normalize_provider_rows(rows, provider="usgs_nwis")


def parse_foen_response(
    payload: bytes,
    *,
    site_id: str,
    request_year: int | None = None,
    request_start: str | None = None,
    request_end: str | None = None,
) -> pd.DataFrame:
    """Parse one FOEN daily-mean GraphQL response into neutral QC columns."""

    try:
        document = json.loads(payload.decode("utf-8"))
        if document.get("errors"):
            raise SealedEvaluatorError("FOEN response contains GraphQL errors")
        rows = document["data"]["water"]["observations"]["data_1day_mean"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise SealedEvaluatorError("invalid FOEN GraphQL response") from error
    if not isinstance(rows, list):
        raise SealedEvaluatorError("FOEN daily observations are not a list")
    if request_year is not None:
        request_start = request_start or f"{request_year:04d}-01-01T00:00:00Z"
        request_end = request_end or f"{request_year + 1:04d}-01-01T00:00:00Z"
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise SealedEvaluatorError("FOEN observation row is not a mapping")
        station = row.get("station") or {}
        if str(station.get("no", "")) != str(site_id):
            raise SealedEvaluatorError("FOEN response station mismatch")
        if str(row.get("parameterName", "")) != "WT":
            raise SealedEvaluatorError("FOEN response parameter mismatch")
        unit = str(row.get("unitSymbol", "")).strip().lower().replace("°", "")
        if unit not in {"c", "degc", "celsius"}:
            raise SealedEvaluatorError("FOEN temperature unit is not Celsius")
        state = row.get("releaseState")
        approval = "A" if state in {2, 3, "2", "3"} else "P"
        timestamp = _timestamp_in_request(
            row.get("timestamp"),
            request_start=request_start,
            request_end=request_end,
            request_end_inclusive=False,
        )
        if request_year is not None and timestamp.year != request_year:
            raise SealedEvaluatorError("FOEN timestamp differs from request year")
        normalized.append(
            {
                "site_id": str(site_id),
                "date": timestamp,
                "temperature_c": row.get("value"),
                "approval_code": approval,
            }
        )
    return _normalize_provider_rows(normalized, provider="foen")


def _normalize_provider_rows(
    rows: Sequence[Mapping[str, Any]], *, provider: str
) -> pd.DataFrame:
    frame = pd.DataFrame(
        rows,
        columns=["site_id", "date", "temperature_c", "approval_code"],
    )
    if frame.empty:
        return frame.assign(provider=pd.Series(dtype=str))
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    if frame["date"].isna().any():
        raise SealedEvaluatorError("provider response contains an invalid timestamp")
    frame["date"] = frame["date"].dt.normalize()
    frame["temperature_c"] = pd.to_numeric(frame["temperature_c"], errors="coerce")
    frame["provider"] = provider
    for _, group in frame.groupby(["site_id", "date"], sort=False, dropna=False):
        if len(group) > 1 and (
            group["temperature_c"].nunique(dropna=False) != 1
            or group["approval_code"].astype(str).nunique(dropna=False) != 1
        ):
            raise SealedEvaluatorError("conflicting duplicate provider calendar day")
    return frame.drop_duplicates(["site_id", "date"]).reset_index(drop=True)


def _network_qc(
    observations: pd.DataFrame, references: Sequence[SealedObjectRef]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    station_rows: list[dict[str, Any]] = []
    membership: dict[str, set[str]] = defaultdict(set)
    for ref in references:
        membership[ref.network_id].add(ref.site_id)
    for (network_id, site_id), group in observations.groupby(
        ["network_id", "site_id"], sort=True
    ):
        row = qc_station_series(
            group["date"],
            group["temperature_c"],
            site_id=str(site_id),
            approval_codes=group["approval_code"],
        )
        row["network_id"] = str(network_id)
        row["provider"] = str(group["provider"].iloc[0])
        station_rows.append(row)
    station_qc = pd.DataFrame(
        station_rows,
        columns=[
            "site_id",
            "n_raw",
            "n_sentinel",
            "n_out_of_range",
            "n_provisional_dropped",
            "n_constant_run_days",
            "n_jump",
            "qualified_years",
            "verdict",
            "notes",
            "network_id",
            "provider",
        ],
    )
    attrition: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for network_id in sorted(membership):
        members = sorted(membership[network_id])
        accepted = set(
            station_qc.loc[
                station_qc["network_id"].eq(network_id)
                & station_qc["verdict"].isin(_ACCEPTED_VERDICTS),
                "site_id",
            ].astype(str)
        )
        filtered = observations.loc[
            observations["network_id"].eq(network_id)
            & observations["site_id"].astype(str).isin(accepted)
            & observations["approval_code"]
            .astype(str)
            .str.lower()
            .isin({"a", "approved"})
            & observations["temperature_c"].between(-5.0, 45.0, inclusive="both")
        ].copy()
        filtered["year"] = filtered["date"].dt.year
        counts = (
            filtered.drop_duplicates(["site_id", "date"])
            .groupby(["site_id", "year"])
            .size()
        )
        qualified_by_site = {
            site: {
                int(year)
                for (observed_site, year), count in counts.items()
                if observed_site == site and count >= 300
            }
            for site in accepted
        }
        selected_sites: tuple[str, ...] = ()
        common_years: list[int] = []
        # The locked rule is existence of an exact >=3-station common-year
        # subset, not intersection over every otherwise accepted station.
        for size in range(len(accepted), 2, -1):
            candidates: list[tuple[tuple[str, ...], list[int]]] = []
            for subset in combinations(sorted(accepted), size):
                years = sorted(
                    set.intersection(*(qualified_by_site[site] for site in subset))
                )
                if len(years) >= 8:
                    candidates.append((subset, years))
            if candidates:
                selected_sites, common_years = min(
                    candidates, key=lambda item: (-len(item[1]), item[0])
                )
                break
        reasons: list[str] = []
        if len(accepted) < 3:
            reasons.append("fewer_than_3_qc_accepted_stations")
        if len(common_years) < 8:
            reasons.append("fewer_than_8_common_300_day_years")
        record = {
            "network_id": network_id,
            "provider": (
                str(filtered["provider"].iloc[0])
                if not filtered.empty
                else next(
                    ref.provider for ref in references if ref.network_id == network_id
                )
            ),
            "n_locked_stations": len(members),
            "n_qc_accepted_stations": len(accepted),
            "n_selected_common_stations": len(selected_sites),
            "selected_common_station_ids": "|".join(selected_sites),
            "n_common_qualified_years": len(common_years),
            "common_qualified_years": "|".join(map(str, common_years)),
        }
        if reasons:
            attrition.append({**record, "reason": ";".join(reasons)})
        else:
            eligible.append(record)
    return station_qc, pd.DataFrame(attrition), pd.DataFrame(eligible)


def _collapse_observation_days(panel: pd.DataFrame) -> pd.DataFrame:
    for _, group in panel.groupby(
        ["provider", "network_id", "site_id", "date"], sort=False, dropna=False
    ):
        if len(group) > 1 and (
            group["temperature_c"].nunique(dropna=False) != 1
            or group["approval_code"].astype(str).nunique(dropna=False) != 1
        ):
            raise SealedEvaluatorError("conflicting duplicate synthetic calendar day")
    return panel.drop_duplicates(["provider", "network_id", "site_id", "date"])


def _parse_reference(ref: SealedObjectRef, body: bytes) -> pd.DataFrame:
    if ref.provider == "usgs_nwis":
        return parse_huc8_nwis_response(
            body,
            site_id=ref.site_id,
            request_start=ref.request_start,
            request_end=ref.request_end,
        )
    if ref.provider == "foen":
        return parse_foen_response(
            body,
            site_id=ref.site_id,
            request_year=ref.request_year,
            request_start=ref.request_start,
            request_end=ref.request_end,
        )
    raise SealedEvaluatorError(f"unsupported sealed provider: {ref.provider}")


def _read_body(
    reader: MemorySealedObjectReader | FilesystemSealedObjectReader,
    ref: SealedObjectRef,
) -> bytes:
    body = reader.read_object(ref)
    if type(body) is not bytes:
        raise SealedEvaluatorError("object body must be exact bytes")
    return body


def _qc_registered_objects(
    references: Sequence[SealedObjectRef],
    reader: MemorySealedObjectReader | FilesystemSealedObjectReader,
    *,
    record_read_failures: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, str]]]:
    """Read and parse each reference, then run station and network QC.

    Parse failures are always recorded as object attrition; read failures are
    recorded only when ``record_read_failures`` is true and raise otherwise.
    """

    observations: list[pd.DataFrame] = []
    object_failures: list[dict[str, str]] = []
    seen: set[str] = set()
    for ref in references:
        if ref.key in seen:
            raise SealedEvaluatorError("duplicate registered object identity")
        seen.add(ref.key)
        try:
            body = _read_body(reader, ref)
        except SealedEvaluatorError as error:
            if not record_read_failures:
                raise
            object_failures.append({"object_key": ref.key, "reason": str(error)})
            continue
        try:
            frame = _parse_reference(ref, body)
        except SealedEvaluatorError as error:
            object_failures.append({"object_key": ref.key, "reason": str(error)})
            continue
        frame["network_id"] = ref.network_id
        observations.append(frame)
    panel = (
        pd.concat(observations, ignore_index=True)
        if observations
        else pd.DataFrame(columns=_PANEL_COLUMNS)
    )
    panel = _collapse_observation_days(panel)
    station_qc, attrition, eligible = _network_qc(panel, references)
    return station_qc, attrition, eligible, object_failures


def _write_qc_tables(
    output: Path,
    *,
    prefix: str,
    station_qc: pd.DataFrame,
    attrition: pd.DataFrame,
    eligible: pd.DataFrame,
    object_failures: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    names = {
        "station_qc": f"{prefix}station_qc.csv",
        "object_attrition": f"{prefix}object_attrition.csv",
        "network_attrition": f"{prefix}network_attrition.csv",
        "eligible_networks": f"{prefix}eligible_networks.csv",
    }
    station_qc.to_csv(output / names["station_qc"], index=False)
    attrition.to_csv(output / names["network_attrition"], index=False)
    eligible.to_csv(output / names["eligible_networks"], index=False)
    pd.DataFrame(list(object_failures), columns=["object_key", "reason"]).to_csv(
        output / names["object_attrition"], index=False
    )
    return names


def evaluate_synthetic_fixture(
    *,
    references: Sequence[SealedObjectRef],
    reader: MemorySealedObjectReader,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Run the provider parsers and QC on synthetic in-memory fixtures."""

    if type(reader) is not MemorySealedObjectReader:
        raise SealedEvaluatorError("synthetic fixture requires the exact memory reader")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    station_qc, attrition, eligible, object_failures = _qc_registered_objects(
        references, reader, record_read_failures=False
    )
    outputs = _write_qc_tables(
        output,
        prefix="synthetic_",
        station_qc=station_qc,
        attrition=attrition,
        eligible=eligible,
        object_failures=object_failures,
    )
    provider_counts = Counter(ref.provider for ref in references)
    manifest = {
        "manifest_schema": FIXTURE_RESULT_SCHEMA,
        "status": "synthetic_fixture_complete_not_formal_evidence",
        "formal_evidence": False,
        "synthetic_fixture_execution": True,
        "n_synthetic_objects_read": len(reader.read_keys),
        "n_objects_by_provider": dict(sorted(provider_counts.items())),
        "n_object_parse_failures": len(object_failures),
        "n_station_qc_rows": len(station_qc),
        "n_eligible_networks": len(eligible),
        "n_attrited_networks": len(attrition),
        "synthetic_qc_outputs": outputs,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def run_sealed_qc(
    *,
    output_dir: str | Path = DEFAULT_SEALED_QC_OUTPUT,
    sealed_absolute_floor: int = 40,
    references: Sequence[SealedObjectRef] | None = None,
    reader: FilesystemSealedObjectReader | None = None,
) -> dict[str, Any]:
    """Read, parse, and QC every registered sealed object.

    Objects that cannot be read or parsed are recorded as object attrition.
    The number of eligible HUC8 networks is compared with the sealed absolute
    floor.  By default the references are replayed from the locked catalogs
    and their registry sidecars, and the objects are read from the vaults.
    """

    references = (
        registered_object_references() if references is None else tuple(references)
    )
    reader = FilesystemSealedObjectReader() if reader is None else reader
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    station_qc, attrition, eligible, object_failures = _qc_registered_objects(
        references, reader, record_read_failures=True
    )
    outputs = _write_qc_tables(
        output,
        prefix="",
        station_qc=station_qc,
        attrition=attrition,
        eligible=eligible,
        object_failures=object_failures,
    )
    provider_counts = Counter(ref.provider for ref in references)
    n_huc8_eligible = (
        int(eligible["provider"].eq("usgs_nwis").sum()) if not eligible.empty else 0
    )
    n_foen_eligible = (
        int(eligible["provider"].eq("foen").sum()) if not eligible.empty else 0
    )
    sealed_floor_met = n_huc8_eligible >= sealed_absolute_floor
    manifest = {
        "manifest_schema": PRODUCTION_RESULT_SCHEMA,
        "status": "complete",
        "formal_evidence": False,
        "sealed_outcomes_opened": True,
        "sealed_temperature_records_read": True,
        "n_sealed_objects_read": len(reader.read_keys),
        "n_objects_by_provider": dict(sorted(provider_counts.items())),
        "n_object_parse_failures": len(object_failures),
        "n_station_qc_rows": len(station_qc),
        "n_eligible_networks": len(eligible),
        "n_huc8_eligible_networks": n_huc8_eligible,
        "n_foen_eligible_networks": n_foen_eligible,
        "sealed_absolute_floor": sealed_absolute_floor,
        "sealed_absolute_floor_met": sealed_floor_met,
        "passed": sealed_floor_met,
        "purpose": "sealed_qc_not_confirmatory_t2_scoring",
        "outputs": outputs,
    }
    (output / "sealed_qc_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


__all__ = [
    "DEFAULT_SEALED_QC_OUTPUT",
    "EXPECTED_SEALED_NETWORKS",
    "EXPECTED_SEALED_OBJECTS",
    "FIXTURE_RESULT_SCHEMA",
    "PRODUCTION_RESULT_SCHEMA",
    "FilesystemSealedObjectReader",
    "MemorySealedObjectReader",
    "SealedEvaluatorError",
    "SealedObjectRef",
    "evaluate_synthetic_fixture",
    "parse_foen_response",
    "parse_huc8_nwis_response",
    "registered_object_references",
    "run_sealed_qc",
    "vault_path_for_reference",
]

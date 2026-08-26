"""Deterministic, resumable NLDI metadata acquisition for open T5 targets."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.data.http_json import JsonHttpError, get_json
from stream_recoverability.data.nldi_connectivity import (
    NLDI_BASE,
    normalize_nwis_site_id,
)
from stream_recoverability.experiments.t5_matching_contract import (
    OPEN_ROLES,
    collapse_predictor_rosters,
)

DIRECTIONS = ("UM", "DM")
DISTANCE_KM = 200
PROVIDER_UNAVAILABLE_HTTP_STATUSES = frozenset({400, 404, 405, 410, 422})


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_open_target_plan(
    predictors: pd.DataFrame,
    *,
    cache_dir: Path,
    unavailable_dir: Path | None = None,
    distance_km: int = DISTANCE_KM,
) -> pd.DataFrame:
    """Return the immutable target/direction request universe."""

    rosters = collapse_predictor_rosters(predictors)
    roles = set(rosters["role"].astype(str))
    if not roles.issubset(OPEN_ROLES):
        raise ValueError(f"NLDI plan contains non-open roles: {sorted(roles)}")
    targets = sorted(set(rosters["station_id"].map(normalize_nwis_site_id)))
    registry_dir = (
        Path(unavailable_dir)
        if unavailable_dir is not None
        else Path(cache_dir) / "provider_unavailable_registry"
    )
    rows: list[dict[str, Any]] = []
    for target in targets:
        for direction in DIRECTIONS:
            filename = f"{target}_{direction}_{int(distance_km)}.json"
            unavailable_path = registry_dir / filename
            rows.append(
                {
                    "request_ordinal": len(rows),
                    "target_station_id": target,
                    "direction": direction,
                    "distance_km": int(distance_km),
                    "endpoint": (
                        f"{NLDI_BASE}/USGS-{target}/navigation/{direction}/nwissite"
                        f"?distance={int(distance_km)}"
                    ),
                    "cache_path": (Path(cache_dir) / filename).as_posix(),
                    "unavailable_path": unavailable_path.as_posix(),
                }
            )
    return pd.DataFrame(rows)


def _unavailable_sidecar_status(
    path: Path,
    *,
    target_station_id: str,
    direction: str,
    distance_km: int,
    endpoint: str,
) -> str:
    if not path.is_file():
        return "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "invalid_existing_unavailable_sidecar"
    valid = bool(
        isinstance(payload, dict)
        and payload.get("schema_version") == "t5_nldi_provider_unavailable_v1"
        and payload.get("classification") == "provider_confirmed_unavailable"
        and payload.get("http_status") in PROVIDER_UNAVAILABLE_HTTP_STATUSES
        and payload.get("target_station_id")
        == normalize_nwis_site_id(target_station_id)
        and payload.get("direction") == str(direction).upper()
        and payload.get("distance_km") == int(distance_km)
        and payload.get("endpoint") == str(endpoint)
    )
    return (
        "provider_confirmed_unavailable"
        if valid
        else "invalid_existing_unavailable_sidecar"
    )


def cache_status(
    path: Path,
    unavailable_path: Path | None = None,
    *,
    target_station_id: str = "",
    direction: str = "",
    distance_km: int = DISTANCE_KM,
    endpoint: str = "",
) -> str:
    if not path.is_file():
        return (
            _unavailable_sidecar_status(
                unavailable_path,
                target_station_id=target_station_id,
                direction=direction,
                distance_km=distance_km,
                endpoint=endpoint,
            )
            if unavailable_path is not None
            else "missing"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "invalid_existing_cache"
    if (
        not isinstance(payload, dict)
        or payload.get("type") != "FeatureCollection"
        or not isinstance(payload.get("features"), list)
    ):
        return "invalid_existing_cache"
    return "complete"


def _resolved(path: str, root: Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else Path(root) / candidate


def audit_plan_cache(plan: pd.DataFrame, *, root: Path = Path()) -> pd.DataFrame:
    """Attach current cache state without changing the immutable plan."""

    audit = plan[["request_ordinal", "target_station_id", "direction"]].copy()
    audit["cache_path"] = plan["cache_path"].astype(str)
    audit["unavailable_path"] = plan.get("unavailable_path", "").astype(str)
    audit["status"] = [
        cache_status(
            _resolved(cache_path, root),
            _resolved(unavailable_path, root) if unavailable_path else None,
            target_station_id=target_station_id,
            direction=direction,
            distance_km=int(distance_km),
            endpoint=endpoint,
        )
        for cache_path, unavailable_path, target_station_id, direction, distance_km, endpoint in zip(
            audit["cache_path"],
            audit["unavailable_path"],
            plan["target_station_id"],
            plan["direction"],
            plan["distance_km"],
            plan["endpoint"],
            strict=True,
        )
    ]
    audit["response_sha256"] = [
        (
            file_sha256(_resolved(cache_path, root))
            if status == "complete"
            else ""
        )
        for cache_path, status in zip(
            audit["cache_path"], audit["status"], strict=True
        )
    ]
    return audit


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def fetch_nldi_slot(
    *,
    target_station_id: str,
    direction: str,
    distance_km: int,
    cache_path: Path,
    unavailable_path: Path,
    request_interval_seconds: float,
    timeout: int = 90,
) -> dict[str, Any]:
    """Fetch one slot while retaining deterministic HTTP status semantics."""

    endpoint = (
        f"{NLDI_BASE}/USGS-{normalize_nwis_site_id(target_station_id)}/navigation/"
        f"{str(direction).upper()}/nwissite?distance={int(distance_km)}"
    )
    existing = cache_status(
        cache_path,
        unavailable_path,
        target_station_id=target_station_id,
        direction=direction,
        distance_km=distance_km,
        endpoint=endpoint,
    )
    if existing in {"complete", "provider_confirmed_unavailable"}:
        return {"status": existing, "http_status": None}
    if existing.startswith("invalid_existing_"):
        raise RuntimeError(f"fail-closed existing NLDI artifact: {existing}")
    try:
        document = get_json(endpoint, timeout=timeout)
    except JsonHttpError as error:
        http_status = error.status_code
        if http_status in PROVIDER_UNAVAILABLE_HTTP_STATUSES:
            _atomic_json(
                unavailable_path,
                {
                    "schema_version": "t5_nldi_provider_unavailable_v1",
                    "classification": "provider_confirmed_unavailable",
                    "target_station_id": normalize_nwis_site_id(target_station_id),
                    "direction": str(direction).upper(),
                    "distance_km": int(distance_km),
                    "http_status": http_status,
                    "endpoint": endpoint,
                },
            )
            time.sleep(max(float(request_interval_seconds), 0.0))
            return {
                "status": "provider_confirmed_unavailable",
                "http_status": http_status,
            }
        time.sleep(max(float(request_interval_seconds), 0.0))
        return {"status": "transient_failure", "http_status": http_status}
    except RuntimeError:
        time.sleep(max(float(request_interval_seconds), 0.0))
        return {"status": "transient_failure", "http_status": None}
    if (
        not isinstance(document, dict)
        or document.get("type") != "FeatureCollection"
        or not isinstance(document.get("features"), list)
    ):
        time.sleep(max(float(request_interval_seconds), 0.0))
        return {"status": "invalid_response", "http_status": None}
    _atomic_json(cache_path, document)
    time.sleep(max(float(request_interval_seconds), 0.0))
    return {"status": "complete", "http_status": 200}


def execute_missing_requests(
    plan: pd.DataFrame,
    *,
    cache_dir: Path,
    max_new_requests: int,
    request_interval_seconds: float = 0.3,
    plan_root: Path = Path(),
) -> pd.DataFrame:
    """Serially fill at most ``max_new_requests`` missing cache entries."""

    if max_new_requests < 1:
        raise ValueError("max_new_requests must be positive")
    before = audit_plan_cache(plan, root=plan_root)
    invalid = before.loc[before["status"].str.startswith("invalid_existing_")]
    if not invalid.empty:
        details = invalid[
            ["request_ordinal", "target_station_id", "direction", "status"]
        ].to_dict(orient="records")
        raise RuntimeError(f"fail-closed invalid NLDI artifacts: {details[:5]}")
    missing_ordinals = before.loc[before["status"].eq("missing"), "request_ordinal"]
    selected_order = list(missing_ordinals.head(max_new_requests).astype(int))
    selected = set(selected_order)
    logs: list[dict[str, Any]] = []
    halted_early = False
    halt_reason: str | None = None
    for row in plan.itertuples(index=False):
        if int(row.request_ordinal) not in selected:
            continue
        cache_path = _resolved(str(row.cache_path), plan_root)
        unavailable_path = _resolved(str(row.unavailable_path), plan_root)
        fetch_result = fetch_nldi_slot(
            target_station_id=str(row.target_station_id),
            direction=str(row.direction),
            distance_km=int(row.distance_km),
            cache_path=cache_path,
            unavailable_path=unavailable_path,
            request_interval_seconds=request_interval_seconds,
        )
        status = str(fetch_result["status"])
        logs.append(
            {
                "request_ordinal": int(row.request_ordinal),
                "target_station_id": str(row.target_station_id),
                "direction": str(row.direction),
                "status": status,
                "http_status": fetch_result.get("http_status"),
                "response_sha256": (
                    file_sha256(cache_path) if status == "complete" else ""
                ),
            }
        )
        if status in {"transient_failure", "invalid_response"}:
            halted_early = True
            halt_reason = status
            break
    result = pd.DataFrame(
        logs,
        columns=[
            "request_ordinal",
            "target_station_id",
            "direction",
            "status",
            "http_status",
            "response_sha256",
        ],
    )
    result.attrs.update(
        {
            "halted_early": halted_early,
            "halt_reason": halt_reason,
            "n_selected_requests": len(selected_order),
            "n_selected_requests_remaining_after_halt": (
                len(selected_order) - len(logs) if halted_early else 0
            ),
        }
    )
    return result


__all__ = [
    "DIRECTIONS",
    "DISTANCE_KM",
    "audit_plan_cache",
    "build_open_target_plan",
    "cache_status",
    "execute_missing_requests",
    "fetch_nldi_slot",
    "file_sha256",
]

"""Deterministic, resumable NLDI metadata acquisition for open T5 targets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.data.nldi_connectivity import (
    NLDI_BASE,
    fetch_nldi_navigation,
    normalize_nwis_site_id,
)
from stream_recoverability.experiments.t5_matching_contract import (
    OPEN_ROLES,
    collapse_predictor_rosters,
)

DIRECTIONS = ("UM", "DM")
DISTANCE_KM = 200


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
    distance_km: int = DISTANCE_KM,
) -> pd.DataFrame:
    """Return the immutable target/direction request universe."""

    rosters = collapse_predictor_rosters(predictors)
    roles = set(rosters["role"].astype(str))
    if not roles.issubset(OPEN_ROLES):
        raise ValueError(f"NLDI plan contains non-open roles: {sorted(roles)}")
    targets = sorted(set(rosters["station_id"].map(normalize_nwis_site_id)))
    rows: list[dict[str, Any]] = []
    for target in targets:
        for direction in DIRECTIONS:
            filename = f"{target}_{direction}_{int(distance_km)}.json"
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
                }
            )
    return pd.DataFrame(rows)


def cache_status(path: Path) -> str:
    if not path.is_file():
        return "missing"
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
    audit["status"] = audit["cache_path"].map(
        lambda item: cache_status(_resolved(item, root))
    )
    audit["response_sha256"] = audit["cache_path"].map(
        lambda item: (
            file_sha256(_resolved(item, root))
            if cache_status(_resolved(item, root)) == "complete"
            else ""
        )
    )
    return audit


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
    missing_ordinals = before.loc[before["status"].eq("missing"), "request_ordinal"]
    selected_order = list(missing_ordinals.head(max_new_requests).astype(int))
    selected = set(selected_order)
    logs: list[dict[str, Any]] = []
    halted_early = False
    halt_reason: str | None = None
    for row in plan.itertuples(index=False):
        if int(row.request_ordinal) not in selected:
            continue
        document = fetch_nldi_navigation(
            str(row.target_station_id),
            str(row.direction),
            distance_km=float(row.distance_km),
            cache_dir=cache_dir,
            pause_s=request_interval_seconds,
        )
        path = _resolved(str(row.cache_path), plan_root)
        status = cache_status(path)
        if document is not None and status == "invalid_existing_cache":
            digest = file_sha256(path)
            quarantine = path.with_name(f"{path.stem}.invalid-{digest[:12]}.json")
            suffix = 1
            while quarantine.exists():
                quarantine = path.with_name(
                    f"{path.stem}.invalid-{digest[:12]}-{suffix}.json"
                )
                suffix += 1
            path.replace(quarantine)
            status = "invalid_response_quarantined"
        logs.append(
            {
                "request_ordinal": int(row.request_ordinal),
                "target_station_id": str(row.target_station_id),
                "direction": str(row.direction),
                "status": status if document is not None else "request_failed",
                "response_sha256": file_sha256(path) if status == "complete" else "",
            }
        )
        if document is None:
            halted_early = True
            halt_reason = "request_failed_after_internal_retries"
            break
        if status != "complete":
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
    "file_sha256",
]

"""T7 once-lock for public-river confirmation. Does not open temperatures.

The lock records network IDs only. Last-check and burned rivers cannot be
sealed. The lock is refused until 40 eligible networks exist, including 10
outside North America with public daily concurrency. Floors cannot be lowered.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from stream_recoverability.analysis.study_freeze import load_study_freeze
from stream_recoverability.data.v2_download_policy import (
    BURNED_NAME_TOKENS,
    HISTORICAL_TOKENS,
    LAST_CHECK_NAME_TOKENS,
    last_check_network_ids,
)

DEFAULT_LOCK = Path("results/framework/public_rivers_v2/confirmatory_once.lock.json")
NORTH_AMERICA = frozenset({"north_america", "na", "north america"})
NON_NORTH_AMERICA = frozenset(
    {"europe", "asia", "africa", "south_america", "oceania", "australia", "antarctica"}
)
FLOOR_MIN = 40
NON_NA_FLOOR_MIN = 10


def _haystack(network_id: str) -> str:
    return str(network_id).lower().replace("-", "_")


def _explicit_true(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, (int, float)) and value == 1:
        return True
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    return False


def is_forbidden_sealed(network_id: str, freeze: Mapping[str, Any] | None = None) -> bool:
    document = freeze if freeze is not None else load_study_freeze()
    split = document.get("split_rule") or {}
    never = {str(item) for item in split.get("never_sealed_networks") or []}
    uncountable = {
        str(item)
        for item in split.get("not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public")
        or []
    }
    if str(network_id) in never or str(network_id) in uncountable:
        return True
    text = _haystack(network_id)
    if any(token in text for token in LAST_CHECK_NAME_TOKENS):
        return True
    if any(token in text for token in HISTORICAL_TOKENS):
        return True
    if any(token.split()[0] in text for token in BURNED_NAME_TOKENS if token.split()):
        return True
    if any(_haystack(item).split("_")[0] and _haystack(item).split("_")[0] in text for item in never):
        return True
    if str(network_id) in last_check_network_ids():
        return True
    return False


def propose_sealed_networks(
    candidates: Sequence[Mapping[str, Any]],
    *,
    freeze: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assign sealed IDs from metadata. Does not read temperature values."""

    document = freeze if freeze is not None else load_study_freeze()
    split = document.get("split_rule") or {}
    floor = max(int(split.get("sealed_min_networks") or split.get("sealed_absolute_floor") or FLOOR_MIN), FLOOR_MIN)
    non_na_floor = max(int(split.get("sealed_min_outside_north_america") or NON_NA_FLOOR_MIN), NON_NA_FLOOR_MIN)
    eligible = []
    rejected = []
    for row in candidates:
        network_id = str(row.get("network_id") or "")
        continent = str(row.get("continent") or "unknown").strip().lower().replace(" ", "_")
        complete = _explicit_true(row.get("complete_enough"))
        if not network_id or not complete:
            rejected.append({"network_id": network_id, "reason": "not_complete_enough"})
            continue
        if is_forbidden_sealed(network_id, freeze=document):
            rejected.append({"network_id": network_id, "reason": "never_sealed_or_last_check"})
            continue
        eligible.append({"network_id": network_id, "continent": continent})
    non_na = [item for item in eligible if item["continent"] in NON_NORTH_AMERICA]
    north = [item for item in eligible if item["continent"] in NORTH_AMERICA]
    enough = len(eligible) >= floor and len(non_na) >= non_na_floor
    sealed: list[str] = []
    if enough:
        sealed_non_na = [item["network_id"] for item in non_na[:non_na_floor]]
        remaining = floor - len(sealed_non_na)
        sealed_na = [item["network_id"] for item in north[:remaining]]
        sealed = sealed_non_na + sealed_na
        extra = [item["network_id"] for item in non_na[non_na_floor:] + north[remaining:]]
        if len(sealed) < floor:
            sealed.extend(extra[: floor - len(sealed)])
        sealed_continents = {
            item["continent"]
            for item in eligible
            if item["network_id"] in set(sealed)
        }
        if len(sealed) < floor or sum(1 for item in eligible if item["network_id"] in set(sealed) and item["continent"] in NON_NORTH_AMERICA) < non_na_floor:
            sealed = []
            enough = False
        del sealed_continents
    return {
        "what_this_is": "Metadata-only T7 sealed assignment. Temperatures were not opened.",
        "what_this_is_not": "Not confirmatory evaluation. Not a license to read sealed values.",
        "sealed_outcomes_opened": False,
        "lock_created": False,
        "eligible_n": len(eligible),
        "non_north_america_n": len(non_na),
        "sealed_min_networks": floor,
        "sealed_min_outside_north_america": non_na_floor,
        "enough_to_lock": enough and len(sealed) >= floor,
        "sealed_network_ids": sealed if enough and len(sealed) >= floor else [],
        "rejected": rejected[:50],
        "temperatures_opened": False,
        "last_check_temperatures_opened": False,
        "formal_evidence": False,
    }


def write_lock_or_refuse(
    proposal: Mapping[str, Any],
    path: str | Path = DEFAULT_LOCK,
) -> dict[str, Any]:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(proposal)
    if dest.is_file():
        payload["lock_created"] = False
        payload["reason"] = "lock_already_exists"
        return payload
    if not payload.get("enough_to_lock"):
        payload["lock_created"] = False
        payload["reason"] = "insufficient_eligible_networks_including_non_na"
        refusal = dest.with_name(dest.stem + ".refusal.json") if dest.suffix else dest.with_suffix(".refusal.json")
        if dest.name.endswith(".lock.json"):
            refusal = dest.with_name("confirmatory_once.lock.refusal.json")
        refusal.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        payload["refusal_path"] = str(refusal)
        return payload
    payload["lock_created"] = True
    payload["reason"] = "ids_locked_temperatures_unopened"
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return payload


__all__ = [
    "DEFAULT_LOCK",
    "is_forbidden_sealed",
    "propose_sealed_networks",
    "write_lock_or_refuse",
]

"""Who may be downloaded from catalog v2. Last-check temperatures stay closed.

Catalog overlap is not download concurrency. This module does not remap
``network_catalog_v1.yaml`` and does not assign sealed roles.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from stream_recoverability.data.network_catalog import load_network_catalog

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_V1_CATALOG = REPOSITORY_ROOT / "configs/network_catalog_v1.yaml"
DEFAULT_V2_CANDIDATES = REPOSITORY_ROOT / "configs/network_catalog_v2_candidates.yaml"

LAST_CHECK_NAME_TOKENS = (
    "colorado",
    "columbia",
    "ohio_mainstem",
    "ohio river",
    "deschutes",
    "loire",
    "swiss",
    "aar_rhine",
    "aare",
)
HISTORICAL_TOKENS = ("chattahoochee", "jinsha")
BURNED_NAME_TOKENS = (
    "delaware river",
    "willamette river",
    "suwannee river",
    "yellowstone river",
    "rio grande",
    "madison river",
    "cahaba river",
    "mckenzie river",
    "mahoning river",
    "roanoke river",
    "santa fe river",
    "clearwater river",
)
LAST_CHECK_USES = {"last_check"}
LAST_CHECK_ROLES = {"sealed"}


def last_check_site_ids(catalog: Mapping[str, Any] | None = None) -> set[str]:
    """Site IDs named on v1 last-check / sealed rivers. Never download these."""

    document = catalog if catalog is not None else load_network_catalog()
    blocked: set[str] = set()
    for network in document.get("networks") or []:
        use = str(network.get("use") or "")
        role = str(network.get("split_role") or "")
        if use not in LAST_CHECK_USES and role not in LAST_CHECK_ROLES:
            continue
        for site_id in network.get("candidate_station_ids") or []:
            blocked.add(str(site_id))
    return blocked


def last_check_network_ids(catalog: Mapping[str, Any] | None = None) -> set[str]:
    document = catalog if catalog is not None else load_network_catalog()
    blocked: set[str] = set()
    for network in document.get("networks") or []:
        use = str(network.get("use") or "")
        role = str(network.get("split_role") or "")
        if use in LAST_CHECK_USES or role in LAST_CHECK_ROLES:
            blocked.add(str(network.get("network_id") or ""))
    return blocked


def _haystack(network: Mapping[str, Any]) -> str:
    return " ".join(
        [
            str(network.get("network_id") or ""),
            str(network.get("display_name") or ""),
        ]
    ).lower()


def block_reason(
    network: Mapping[str, Any],
    *,
    last_check_sites: Iterable[str],
) -> str | None:
    """Return why this v2 row must not be newly downloaded, or None if allowed."""

    text = _haystack(network)
    if network.get("historical_seen") or any(token in text for token in HISTORICAL_TOKENS):
        return "historical"
    if any(token in text for token in LAST_CHECK_NAME_TOKENS):
        return "last_check_name"
    sites = [str(item) for item in network.get("candidate_station_ids") or []]
    blocked_sites = set(str(item) for item in last_check_sites)
    if any(site in blocked_sites for site in sites):
        return "last_check_site"
    if any(token in text for token in BURNED_NAME_TOKENS):
        return "already_downloaded_burned"
    return None


def load_v2_candidates(path: str | Path = DEFAULT_V2_CANDIDATES) -> dict[str, Any]:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError("v2 candidates must be a mapping")
    return document


def assign_unique_sites(
    networks: Sequence[Mapping[str, Any]],
    *,
    blocked_sites: Iterable[str],
) -> list[dict[str, Any]]:
    """One station, one download network. Larger clusters keep a contested ID."""

    blocked = set(str(item) for item in blocked_sites)
    ranked = sorted(
        networks,
        key=lambda row: (
            -len(row.get("candidate_station_ids") or []),
            str(row.get("network_id") or ""),
        ),
    )
    claimed: set[str] = set()
    assigned: list[dict[str, Any]] = []
    for network in ranked:
        kept: list[str] = []
        dropped_blocked: list[str] = []
        dropped_claimed: list[str] = []
        for site_id in (str(item) for item in network.get("candidate_station_ids") or []):
            if site_id in blocked:
                dropped_blocked.append(site_id)
                continue
            if site_id in claimed:
                dropped_claimed.append(site_id)
                continue
            kept.append(site_id)
            claimed.add(site_id)
        assigned.append(
            {
                **dict(network),
                "download_site_ids": kept,
                "dropped_last_check_site_ids": dropped_blocked,
                "dropped_duplicate_site_ids": dropped_claimed,
            }
        )
    return assigned


def site_set_nested(inner: Sequence[str], outer: Sequence[str]) -> bool:
    left = set(inner)
    right = set(outer)
    return bool(left) and left.issubset(right) and left != right


def independent_unit_flags(rows: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    """False when a network's download IDs are a proper subset of another."""

    site_map = {
        str(row.get("network_id")): [str(item) for item in row.get("download_site_ids") or []]
        for row in rows
    }
    flags: dict[str, bool] = {}
    for network_id, sites in site_map.items():
        nested = any(
            other_id != network_id and site_set_nested(sites, other_sites)
            for other_id, other_sites in site_map.items()
        )
        flags[network_id] = not nested
    return flags


def plan_v2_downloads(
    *,
    v1_catalog: Mapping[str, Any] | None = None,
    v2_document: Mapping[str, Any] | None = None,
    min_download_stations: int = 3,
) -> dict[str, Any]:
    """Return blocked vs downloadable v2 rows. Does not touch temperatures."""

    v1 = v1_catalog if v1_catalog is not None else load_network_catalog()
    v2 = v2_document if v2_document is not None else load_v2_candidates()
    blocked_sites = last_check_site_ids(v1)
    classified: list[dict[str, Any]] = []
    for network in v2.get("networks") or []:
        reason = block_reason(network, last_check_sites=blocked_sites)
        classified.append({**dict(network), "block_reason": reason})
    downloadable = [row for row in classified if row["block_reason"] is None]
    assigned = assign_unique_sites(downloadable, blocked_sites=blocked_sites)
    too_small = []
    keep = []
    for row in assigned:
        if len(row.get("download_site_ids") or []) < int(min_download_stations):
            too_small.append(
                {
                    **row,
                    "block_reason": "fewer_than_min_download_stations_after_unique_sites",
                }
            )
        else:
            keep.append(row)
    flags = independent_unit_flags(keep)
    for row in keep:
        row["independent_unit"] = bool(flags.get(str(row.get("network_id")), True))
    return {
        "last_check_site_ids": sorted(blocked_sites),
        "last_check_network_ids": sorted(last_check_network_ids(v1)),
        "n_v2_candidates": int(len(classified)),
        "blocked": [row for row in classified if row["block_reason"] is not None] + too_small,
        "downloadable": keep,
        "n_downloadable": int(len(keep)),
        "n_independent_downloadable": int(sum(1 for row in keep if row.get("independent_unit"))),
        "n_download_sites": int(sum(len(row.get("download_site_ids") or []) for row in keep)),
        "network_catalog_v1_rewritten": False,
        "sealed_outcomes_opened": False,
        "last_check_temperatures_opened": False,
    }


__all__ = [
    "BURNED_NAME_TOKENS",
    "DEFAULT_V1_CATALOG",
    "DEFAULT_V2_CANDIDATES",
    "HISTORICAL_TOKENS",
    "LAST_CHECK_NAME_TOKENS",
    "assign_unique_sites",
    "block_reason",
    "independent_unit_flags",
    "last_check_network_ids",
    "last_check_site_ids",
    "load_v2_candidates",
    "plan_v2_downloads",
    "site_set_nested",
]

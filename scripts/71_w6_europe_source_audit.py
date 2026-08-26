#!/usr/bin/env python3
"""W6 public-Europe audit without opening Loire or Swiss temperature values.

Hub'Eau is preflighted at every station in every non-Loire 3+ name cluster.
Only Sandre qualification 1 (``Correcte``) can enter the strict daily path.
If a station has no such observations, a bulk temperature download is neither
useful nor attempted.

FOEN is audited as metadata/timestamps only.  The 2026 public GraphQL endpoint
supersedes the old assumption that historical daily data always require a
manual order, but the locked protocol still forbids counting Swiss networks.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.http_json import USER_AGENT, get_json
from stream_recoverability.data.hubeau_temperature import (
    HUBEAU_CHRONIQUE,
    HUBEAU_CORRECT_QUALIFICATION,
)

CATALOG = ROOT / "results/framework/public_catalog"
CLUSTERS = CATALOG / "hubeau_non_loire_clusters.csv"
HUBEAU_SITE_AUDIT = CATALOG / "w6_hubeau_correct_station_audit.csv"
HUBEAU_NETWORK_AUDIT = CATALOG / "w6_hubeau_strict_network_audit.csv"
FOEN_AUDIT = CATALOG / "w6_foen_public_api_audit.json"
MANIFEST = CATALOG / "w6_europe_source_audit_manifest.json"
FOEN_GRAPHQL = "https://data.bafu.admin.ch/api"
FOEN_DOCS = (
    "https://api.data-platform.cloud.bafu.admin.ch/en/dataproduct-water-observations"
)
FOEN_ORDER_PAGE = (
    "https://www.bafu.admin.ch/en/hydrological-data-service-for-watercourses-and-lakes"
)


def _hubeau_query(site_id: str, sort: str) -> str:
    return (
        HUBEAU_CHRONIQUE
        + "?"
        + urllib.parse.urlencode(
            {
                "code_station": str(site_id),
                "code_qualification": HUBEAU_CORRECT_QUALIFICATION,
                "size": "1",
                "page": "1",
                "sort": sort,
            }
        )
    )


def hubeau_correct_span(
    site_id: str,
    *,
    fetch_json: Callable[..., dict[str, Any]] = get_json,
) -> dict[str, Any]:
    """Return count and dated span for validated observations, never values."""

    first = fetch_json(
        _hubeau_query(site_id, "asc"), timeout=45, retries=3, base_pause_s=0.5
    )
    count = int(first.get("count") or 0)
    first_rows = first.get("data") or []
    begin = first_rows[0].get("date_mesure_temp") if first_rows else None
    end = None
    if count:
        last = fetch_json(
            _hubeau_query(site_id, "desc"), timeout=45, retries=3, base_pause_s=0.5
        )
        last_rows = last.get("data") or []
        end = last_rows[0].get("date_mesure_temp") if last_rows else None
    years = float("nan")
    if begin and end:
        years = float((pd.Timestamp(end) - pd.Timestamp(begin)).days / 365.25)
    return {
        "site_id": str(site_id),
        "n_correct_instantaneous": count,
        "correct_begin": begin,
        "correct_end": end,
        "correct_span_years": years,
        "quality_code_required": HUBEAU_CORRECT_QUALIFICATION,
        "quality_label_required": "Correcte",
        "daily_download_started": False,
        "error": None,
    }


def summarize_hubeau_networks(
    clusters: pd.DataFrame, station_audit: pd.DataFrame
) -> pd.DataFrame:
    """Strict preflight: fewer than three validated stations means hard zero."""

    lookup = (
        station_audit.set_index("site_id")
        if not station_audit.empty
        else pd.DataFrame()
    )
    rows: list[dict[str, Any]] = []
    for row in clusters.itertuples(index=False):
        site_ids = [item for item in str(row.site_ids).split(",") if item]
        member = lookup.reindex(site_ids) if not lookup.empty else pd.DataFrame()
        counts = pd.to_numeric(
            member.get("n_correct_instantaneous", pd.Series(dtype=float)),
            errors="coerce",
        ).fillna(0)
        errors = member.get("error", pd.Series(dtype=object)).notna().sum()
        positive = int(counts.gt(0).sum())
        reason = (
            "preflight_error"
            if errors
            else "fewer_than_3_stations_with_correct_observations"
            if positive < 3
            else "requires_strict_daily_density_and_concurrency_download"
        )
        rows.append(
            {
                "river": str(row.river),
                "n_candidate_stations": len(site_ids),
                "n_sites_preflighted": len(member),
                "n_sites_with_correct_observations": positive,
                "n_preflight_errors": int(errors),
                "strict_daily_download_started": False,
                "strict_8yr_concurrent_complete": False,
                "countable_toward_t8": False,
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)


def run_hubeau_audit(*, max_workers: int = 4) -> tuple[pd.DataFrame, pd.DataFrame]:
    clusters = pd.read_csv(CLUSTERS, dtype={"site_ids": str})
    membership: dict[str, str] = {}
    for row in clusters.itertuples(index=False):
        for site_id in str(row.site_ids).split(","):
            if site_id:
                membership[site_id] = str(row.river)

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as executor:
        futures = {
            executor.submit(hubeau_correct_span, site_id): site_id
            for site_id in sorted(membership)
        }
        for future in as_completed(futures):
            site_id = futures[future]
            try:
                result = future.result()
            except Exception as error:  # noqa: BLE001
                result = {
                    "site_id": site_id,
                    "n_correct_instantaneous": None,
                    "correct_begin": None,
                    "correct_end": None,
                    "correct_span_years": None,
                    "quality_code_required": HUBEAU_CORRECT_QUALIFICATION,
                    "quality_label_required": "Correcte",
                    "daily_download_started": False,
                    "error": str(error),
                }
            rows.append({"river": membership[site_id], **result})
    station_audit = pd.DataFrame(rows).sort_values(["river", "site_id"])
    network_audit = summarize_hubeau_networks(clusters, station_audit)
    station_audit.to_csv(HUBEAU_SITE_AUDIT, index=False)
    network_audit.to_csv(HUBEAU_NETWORK_AUDIT, index=False)
    return station_audit, network_audit


def _post_graphql(
    query: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    request = urllib.request.Request(
        FOEN_GRAPHQL,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(str(payload["errors"]))
    return payload


def run_foen_metadata_audit() -> dict[str, Any]:
    """Verify public daily-WT capability without requesting measurement values."""

    station_query = """
    { water { observations { stations(limit: 10000) {
      no name riverName status coverageFrom coverageTo latitude longitude
    } } } }
    """
    stations_payload = _post_graphql(station_query)
    stations = stations_payload["data"]["water"]["observations"]["stations"]
    frame = pd.DataFrame(stations)
    named = frame.loc[frame["riverName"].fillna("").astype(str).str.strip().ne("")]
    clusters = named.groupby("riverName")["no"].nunique()

    # Timestamp, parameter, unit, and release state prove the public daily table
    # is live.  Deliberately omit `value`: Swiss temperature outcomes stay closed.
    daily_query = """
    query Audit($station: String!) {
      water { observations { data_1day_mean(
        where: {
          station: { no: { _eq: $station } }
          parameterName: { _eq: "WT" }
          timestamp: { _gte: "2025-01-01T00:00:00Z", _lt: "2025-01-08T00:00:00Z" }
        }, limit: 7
      ) { timestamp parameterName unitSymbol releaseState station { no name } } } }
    }
    """
    daily_payload = _post_graphql(daily_query, {"station": "2016"})
    rows = daily_payload["data"]["water"]["observations"]["data_1day_mean"]
    audit = {
        "as_of": "2026-08-26",
        "endpoint": FOEN_GRAPHQL,
        "official_documentation": FOEN_DOCS,
        "manual_order_page_still_available": FOEN_ORDER_PAGE,
        "authentication_required": False,
        "public_graphql_reachable": True,
        "public_daily_mean_water_temperature_table": "data_1day_mean",
        "water_temperature_parameter": "WT",
        "release_states_documented": {
            "1": "provisional",
            "2": "validated",
            "3": "final_or_replaced",
        },
        "n_station_metadata_rows": len(frame),
        "n_named_river_clusters_3plus_metadata_only": int(clusters.ge(3).sum()),
        "metadata_timestamp_probe_station": "2016",
        "metadata_timestamp_probe_rows": len(rows),
        "metadata_timestamp_probe_release_states": sorted(
            {str(item.get("releaseState")) for item in rows}
        ),
        "temperature_values_requested": False,
        "historical_daily_requires_manual_order": False,
        "manual_order_only_for": "legacy_or_special_products_not_required_by_the_public_GraphQL_daily_path",
        "swiss_countable_toward_t8": False,
        "swiss_exclusion_reason": "locked_protocol_loire_swiss_still_not_countable_for_t8",
        "recommended_when_governance_changes": (
            "Query data_1day_mean in disjoint yearly windows; parameterName=WT; "
            "retain releaseState 2 or 3; require >=300 distinct days in each of "
            "eight common calendar years; never use coverageFrom/coverageTo as eligibility."
        ),
    }
    FOEN_AUDIT.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()
    CATALOG.mkdir(parents=True, exist_ok=True)
    sites, networks = run_hubeau_audit(max_workers=args.max_workers)
    foen = run_foen_metadata_audit()
    errors = int(sites["error"].notna().sum())
    n_positive = int(
        pd.to_numeric(sites["n_correct_instantaneous"], errors="coerce")
        .fillna(0)
        .gt(0)
        .sum()
    )
    manifest = {
        "what_this_is": "W6 Europe source feasibility and strict-QC preflight.",
        "what_this_is_not": (
            "Not T8 evidence; not a claim from raw spans; no Loire or Swiss "
            "temperature outcomes were opened."
        ),
        "hubeau_n_non_loire_clusters_attempted": len(networks),
        "hubeau_n_non_loire_sites_preflighted": len(sites),
        "hubeau_n_preflight_errors": errors,
        "hubeau_n_sites_with_sandre_correcte_observations": n_positive,
        "hubeau_n_strict_8yr_concurrent_complete": int(
            networks["strict_8yr_concurrent_complete"].fillna(False).sum()
        ),
        "hubeau_bulk_daily_downloads_started": int(
            sites["daily_download_started"].fillna(False).sum()
        ),
        "hubeau_unqualified_code_4_accepted": False,
        "foen_public_graphql_reachable": bool(foen["public_graphql_reachable"]),
        "foen_historical_daily_requires_manual_order": bool(
            foen["historical_daily_requires_manual_order"]
        ),
        "foen_temperature_values_requested": False,
        "loire_downloaded": False,
        "swiss_countable_toward_t8": False,
        "n_europe_complete_enough_added": 0,
        "countable_toward_t8": False,
        "passed": False,
        "formal_evidence": False,
    }
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

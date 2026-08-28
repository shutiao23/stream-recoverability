"""Ordinary download and QC functions for new confirmation candidates."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.data.http_json import get_json
from stream_recoverability.data.ingest_qc import clean_long_frame, qc_long_frame
from stream_recoverability.data.public_temperature import overlap_report, river_wide_panel


NWIS_DAILY_VALUES = "https://waterservices.usgs.gov/nwis/dv/"
HUBEAU_CHRONICLE = "https://hubeau.eaufrance.fr/api/v1/temperature/chronique"
HUBEAU_PAGE_SIZE = 20000
FOEN_GRAPHQL = "https://data.bafu.admin.ch/api"
FOEN_DAILY_QUERY = """
query DailyWaterTemperature(
  $station: String!
  $from: AWSDateTime!
  $to: AWSDateTime!
) {
  water {
    observations {
      data_1day_mean(
        where: {
          station: { no: { _eq: $station } }
          parameterName: { _eq: "WT" }
          timestamp: { _gte: $from, _lt: $to }
        }
        limit: 10000
      ) {
        timestamp parameterName value unitSymbol releaseState station { no }
      }
    }
  }
}
"""
MIN_STATIONS = 3
MIN_QUALIFIED_YEARS = 8
MIN_CONCURRENT_DAYS = 5 * 365


def site_ids(value: str) -> tuple[str, ...]:
    """Parse the candidate table's pipe-separated station roster."""

    return tuple(item for item in str(value).split("|") if item)


def usgs_network_url(stations: Sequence[str], start: str, end: str) -> str:
    """One NWIS daily-mean water-temperature request for a network roster."""

    return NWIS_DAILY_VALUES + "?" + urllib.parse.urlencode(
        {
            "format": "json",
            "sites": ",".join(str(item) for item in stations),
            "parameterCd": "00010",
            "statCd": "00003",
            "startDT": str(start),
            "endDT": str(end),
        }
    )


def parse_usgs_network(document: dict[str, Any]) -> pd.DataFrame:
    """Parse all station series in one NWIS response to a daily long table."""

    rows = []
    for series in (document.get("value") or {}).get("timeSeries") or []:
        source = series.get("sourceInfo") or {}
        codes = source.get("siteCode") or []
        station = str(codes[0]["value"])
        for values_group in series.get("values") or []:
            for point in values_group.get("value") or []:
                qualifier = point.get("qualifiers") or []
                rows.append(
                    {
                        "site_id": station,
                        "date": point.get("dateTime"),
                        "temperature_c": point.get("value"),
                        "qualifier": ",".join(str(item) for item in qualifier),
                    }
                )
    frame = pd.DataFrame(
        rows, columns=["site_id", "date", "temperature_c", "qualifier"]
    )
    frame["date"] = (
        pd.to_datetime(frame["date"], utc=True).dt.tz_localize(None).dt.normalize()
    )
    frame["temperature_c"] = pd.to_numeric(frame["temperature_c"])
    return frame.sort_values(["site_id", "date"], kind="mergesort").reset_index(
        drop=True
    )


def download_usgs_network(
    stations: Sequence[str], start: str, end: str
) -> pd.DataFrame:
    """Download one candidate network directly from NWIS."""

    document = get_json(
        usgs_network_url(stations, start, end),
        timeout=180,
        retries=6,
        base_pause_s=1.0,
    )
    return parse_usgs_network(document)


def hubeau_window_url(station: str, start: str, end: str) -> str:
    """Hub'Eau chronicle request including the provider quality field."""

    return HUBEAU_CHRONICLE + "?" + urllib.parse.urlencode(
        {
            "code_station": str(station),
            "date_debut_mesure": str(start),
            "date_fin_mesure": str(end),
            "code_qualification": "1",
            "size": str(HUBEAU_PAGE_SIZE),
            "page": "1",
            "sort": "asc",
        }
    )


def _hubeau_rows(document: dict[str, Any], station: str) -> list[dict[str, Any]]:
    rows = []
    for item in document.get("data") or []:
        quality = str(item.get("code_qualification") or "")
        rows.append(
            {
                "site_id": str(station),
                "date": item.get("date_mesure_temp"),
                "temperature_c": item.get("resultat"),
                "qualifier": "A" if quality == "1" else "P",
                "provider_quality_code": quality,
            }
        )
    return rows


def download_hubeau_window(
    station: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict[str, Any]]:
    """Download a date window, bisecting responses larger than one API page."""

    document = get_json(
        hubeau_window_url(
            station, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        ),
        timeout=120,
        retries=6,
        base_pause_s=0.8,
    )
    count = int(document.get("count") or 0)
    has_next = bool(document.get("next") or document.get("api_next"))
    if (count > HUBEAU_PAGE_SIZE or has_next) and start < end:
        midpoint = start + (end - start) // 2
        return download_hubeau_window(
            station, start, midpoint
        ) + download_hubeau_window(station, midpoint + pd.Timedelta(days=1), end)
    return _hubeau_rows(document, station)


def download_hubeau_station(station: str, start: str, end: str) -> pd.DataFrame:
    """Download one Hub'Eau station and retain quality codes for QC."""

    rows = download_hubeau_window(station, pd.Timestamp(start), pd.Timestamp(end))
    frame = pd.DataFrame(
        rows,
        columns=[
            "site_id",
            "date",
            "temperature_c",
            "qualifier",
            "provider_quality_code",
        ],
    )
    frame["date"] = pd.to_datetime(frame["date"])
    frame["temperature_c"] = pd.to_numeric(frame["temperature_c"])
    return frame.sort_values("date", kind="mergesort").reset_index(drop=True)


def foen_request(station: str, start: str, end: str) -> urllib.request.Request:
    """Build one ordinary FOEN GraphQL request for a new candidate station."""

    body = json.dumps(
        {
            "query": FOEN_DAILY_QUERY,
            "variables": {
                "station": str(station),
                "from": f"{start}T00:00:00Z",
                "to": f"{end}T00:00:00Z",
            },
        }
    ).encode("utf-8")
    return urllib.request.Request(
        FOEN_GRAPHQL,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "stream-recoverability/0.1 open-confirmation-qc",
        },
    )


def parse_foen_daily(document: dict[str, Any], station: str) -> pd.DataFrame:
    """Retain validated/final FOEN daily water temperature in Celsius."""

    rows = []
    observations = document["data"]["water"]["observations"]["data_1day_mean"]
    for item in observations:
        if str(item["station"]["no"]) == str(station) and str(
            item["parameterName"]
        ) == "WT" and item["releaseState"] in (2, 3, "2", "3"):
            rows.append(
                {
                    "site_id": str(station),
                    "date": item["timestamp"],
                    "temperature_c": item["value"],
                    "qualifier": "A",
                }
            )
    frame = pd.DataFrame(
        rows, columns=["site_id", "date", "temperature_c", "qualifier"]
    )
    frame["date"] = (
        pd.to_datetime(frame["date"], utc=True).dt.tz_localize(None).dt.normalize()
    )
    frame["temperature_c"] = pd.to_numeric(frame["temperature_c"])
    return frame.sort_values("date", kind="mergesort").reset_index(drop=True)


def download_foen_station(station: str, start: str, end: str) -> pd.DataFrame:
    """Download one new FOEN station without consulting prior temperature files."""

    with urllib.request.urlopen(foen_request(station, start, end), timeout=120) as response:
        document = json.loads(response.read().decode("utf-8"))
    return parse_foen_daily(document, station)


def _daily_mean(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby(["site_id", "date"], as_index=False)
        .agg(temperature_c=("temperature_c", "mean"), qualifier=("qualifier", "first"))
        .sort_values(["site_id", "date"], kind="mergesort")
    )


def qc_candidate_network(
    candidate: dict[str, Any] | pd.Series,
    raw_long: pd.DataFrame,
    output_root: str | Path,
    *,
    min_qualified_years: int = MIN_QUALIFIED_YEARS,
) -> dict[str, Any]:
    """Apply station and concurrent-network QC and overwrite ordinary tables."""

    candidate_row = dict(candidate)
    network_id = str(candidate_row["network_id"])
    requested = site_ids(str(candidate_row["site_ids"]))
    report = qc_long_frame(raw_long)
    missing = [station for station in requested if station not in set(report["site_id"])]
    if missing:
        report = pd.concat(
            [
                report,
                pd.DataFrame(
                    {
                        "site_id": missing,
                        "n_raw": 0,
                        "n_sentinel": 0,
                        "n_out_of_range": 0,
                        "n_provisional_dropped": 0,
                        "n_constant_run_days": 0,
                        "n_jump": 0,
                        "qualified_years": 0,
                        "verdict": "no_observations",
                        "notes": "",
                    }
                ),
            ],
            ignore_index=True,
        )
    report["network_id"] = network_id
    report["provider"] = str(candidate_row["provider"])
    report["eligible_for_network"] = (
        report["verdict"].astype(str).str.startswith("accepted")
        & report["qualified_years"].ge(int(min_qualified_years))
    )
    clean = clean_long_frame(
        raw_long,
        report=report,
        min_qualified_years=min_qualified_years,
    )
    daily = _daily_mean(clean)
    wide = river_wide_panel(
        [group.copy() for _, group in daily.groupby("site_id", sort=False)]
    )
    overlap = overlap_report(wide, min_stations=MIN_STATIONS)
    complete = bool(
        int(overlap["n_stations"]) >= MIN_STATIONS
        and float(overlap["overlap_years"]) >= min_qualified_years
        and int(overlap["days_with_min_stations"]) >= MIN_CONCURRENT_DAYS
    )
    directory = Path(output_root) / "networks" / network_id
    directory.mkdir(parents=True, exist_ok=True)
    wide.to_csv(directory / "daily_wide_temperature.csv", index_label="date")
    report.to_csv(directory / "network_qc.csv", index=False)
    finite = pd.to_numeric(raw_long["temperature_c"]).replace(
        [np.inf, -np.inf], np.nan
    ).notna()
    result = {
        "network_id": network_id,
        "provider": str(candidate_row["provider"]),
        "river_group": str(candidate_row["river_group"]),
        "n_requested_stations": len(requested),
        "n_stations_with_values": int(raw_long.loc[finite, "site_id"].nunique()),
        "n_eligible_stations": int(report["eligible_for_network"].sum()),
        "n_daily_rows": int(len(wide)),
        "n_concurrent_days": int(overlap["days_with_min_stations"]),
        "overlap_start": overlap["overlap_start"],
        "overlap_end": overlap["overlap_end"],
        "overlap_years": float(overlap["overlap_years"]),
        "complete_enough": complete,
        "qc_status": "qualified" if complete else "daily_qc_not_qualified",
    }
    pd.DataFrame([result]).to_csv(directory / "network_qc_summary.csv", index=False)
    return result


__all__ = [
    "download_hubeau_station",
    "download_hubeau_window",
    "download_foen_station",
    "download_usgs_network",
    "foen_request",
    "hubeau_window_url",
    "parse_usgs_network",
    "parse_foen_daily",
    "qc_candidate_network",
    "site_ids",
    "usgs_network_url",
]

#!/usr/bin/env python3
"""TR2-M4b: inputs of the test on new USGS stations.

``--design`` (before the round-2 models are fitted) fixes the design from availability
metadata alone: every HUC8 network that contains at least one eligible station
(four or more complete years of approved daily means), all candidates of those
networks as members (targets and potential donors), the independence groups,
the HUC2 regions and the missingness strata. It also fetches NASA POWER T2M for
the target stations with the same request as the source and Australian
forcing. No water-temperature value is requested.

``--values`` (after the round-2 models are fixed) requests the approved daily
mean water temperature of every member of the design roster, reusing cached
responses, applies the repository's ingest QC (``qc_long_frame`` /
``clean_long_frame``), writes one wide panel per network and the roster
that the case builder reads.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_tr_common as T

OUT = T.OUT / "e10_sealed_usgs"
DATA = T.ROOT / "data/external/wrr_target_recovery_20261022/usgs_new"
AVAILABILITY = OUT / "availability_roster.csv"
DESIGN = OUT / "sealed_design_roster.csv"
API = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items"
POWER = (
    "https://power.larc.nasa.gov/api/temporal/daily/point"
    "?parameters=T2M&community=AG&longitude={lon}&latitude={lat}"
    "&start={start}&end={end}&format=JSON"
)
START, END, FILL = "19810101", "20260831", -999.0
AGENT = {"User-Agent": "stream-recoverability target-recovery test (research use)"}


def request_json(url: str, attempts: int = 8) -> dict:
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=240) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            wait = int(error.headers.get("Retry-After", 30)) if error.code == 429 else 10 * (attempt + 1)
            time.sleep(min(wait, 600))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Request failed: {url}")


def fetch_power(row: dict) -> Path:
    path = DATA / "power_raw" / f"{row['station_id']}.json"
    if path.exists() and path.stat().st_size:
        return path
    url = POWER.format(lat=row["latitude"], lon=row["longitude"], start=START, end=END)
    payload = request_json(url, attempts=4)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    path.with_suffix(".url").write_text(url + "\n")
    return path


def power_frame(path: Path, station: str, network: str) -> pd.DataFrame:
    values = json.loads(path.read_text())["properties"]["parameter"]["T2M"]
    frame = pd.DataFrame({"date": pd.to_datetime(list(values), format="%Y%m%d"), "air_temperature_c": list(values.values())})
    frame.loc[frame.air_temperature_c <= FILL + 1e-6, "air_temperature_c"] = np.nan
    frame["station_id"], frame["network_id"] = station, network
    return frame


def design(workers: int) -> int:
    roster = pd.read_csv(AVAILABILITY, dtype={"station_id": str, "HUC8": str, "huc2": str, "series_id": str})
    roster["eligible"] = roster.eligible.astype(str).eq("True")
    networks = sorted(roster.loc[roster.eligible, "network_id"].unique())
    members = roster.loc[roster.network_id.isin(networks) & roster.n_approved.fillna(0).gt(0)].copy()
    members["role"] = np.where(members.eligible, "target", "donor_only")
    members = members.rename(columns={"group_all": "independence_group"})
    columns = [
        "network_id", "station_id", "series_id", "role", "independence_group", "huc2", "HUC8", "latitude", "longitude", "state_name",
        "n_complete_years", "complete_years", "n_incomplete_active_years", "incomplete_share_active", "missing_fraction_active",
        "missingness_stratum", "same_HUC8_as_prior_record", "first_approved", "last_approved",
    ]
    members = members[columns].sort_values(["network_id", "station_id"]).reset_index(drop=True)
    targets = members.loc[members.role.eq("target")]
    jobs = targets[["station_id", "latitude", "longitude"]].to_dict("records")
    with ThreadPoolExecutor(min(workers, 6)) as pool:
        paths = list(pool.map(fetch_power, jobs))
    air = pd.concat([power_frame(path, row.station_id, row.network_id) for path, row in zip(paths, targets.itertuples(index=False))], ignore_index=True)
    air["air_temperature_c"] = air.air_temperature_c.astype("float32")
    air["station_id"] = air.station_id.astype("category")
    air["network_id"] = air.network_id.astype("category")
    air_path = DATA / "air_forcing.parquet"
    air.to_parquet(air_path, index=False)
    with_air = set(air.dropna(subset=["air_temperature_c"]).station_id.astype(str))
    members["has_air_forcing"] = members.station_id.isin(with_air)
    OUT.mkdir(parents=True, exist_ok=True)
    members.to_csv(DESIGN, index=False)
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "values_requested": False,
        "role": "TR2 test on new USGS stations; the design uses availability metadata only",
        "n_networks": len(networks), "n_members": len(members), "n_targets": len(targets), "n_donor_only": int(members.role.eq("donor_only").sum()),
        "n_target_complete_years": int(targets.n_complete_years.sum()), "n_independence_groups": int(targets.independence_group.nunique()),
        "n_huc2": int(targets.huc2.nunique()), "huc2_targets": targets.huc2.value_counts().sort_index().to_dict(),
        "targets_by_stratum": targets.missingness_stratum.value_counts().to_dict(),
        "groups_by_stratum": targets.groupby("missingness_stratum").independence_group.nunique().to_dict(),
        "targets_sharing_huc8_with_prior_record": int(targets.same_HUC8_as_prior_record.astype(str).eq("True").sum()),
        "networks_with_a_second_member": int((members.groupby("network_id").size() > 1).sum()),
        "n_targets_with_air_forcing": int(members.loc[members.role.eq("target"), "has_air_forcing"].sum()),
        "design_roster": str(DESIGN.relative_to(T.ROOT)),
        "air_forcing": {"path": str(air_path.relative_to(T.ROOT)), "source": "NASA POWER T2M daily, same request as scripts/428_tr_au_sealed_prep.py"},
    }
    T.write_json(OUT / "sealed_design.json", summary)
    print({key: value for key, value in summary.items() if not isinstance(value, dict) or key in ("huc2_targets", "targets_by_stratum", "groups_by_stratum")}, flush=True)
    return 0


def fetch_values(series_id: str) -> Path:
    path = DATA / "values_raw" / f"{series_id}.json"
    if path.exists():
        return path
    url = f"{API}?f=json&time_series_id={series_id}&properties=time,value,approval_status,qualifier&skipGeometry=true&limit=10000"
    features, pages = [], []
    while url:
        document = request_json(url)
        page = [{"time": item["properties"]["time"], "value": item["properties"].get("value"), "approval_status": item["properties"].get("approval_status"), "qualifier": item["properties"].get("qualifier")} for item in document.get("features", [])]
        features += page
        pages.append(url)
        url = next((link["href"] for link in document.get("links", []) if link.get("rel") == "next"), None)
        if not page or len(page) < 10000 or len(pages) >= 30:
            url = None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"series_id": series_id, "requests": pages, "features": features}) + "\n")
    return path


def values(workers: int) -> int:
    from stream_recoverability.data.ingest_qc import clean_long_frame, qc_long_frame

    members = pd.read_csv(DESIGN, dtype={"station_id": str, "series_id": str, "huc2": str, "HUC8": str})
    with ThreadPoolExecutor(workers) as pool:
        raw = dict(zip(members.series_id, pool.map(fetch_values, members.series_id)))
    pieces = []
    for row in members.itertuples(index=False):
        features = json.loads(raw[row.series_id].read_text())["features"]
        frame = pd.DataFrame(features)
        if frame.empty:
            continue
        frame["site_id"] = row.station_id
        frame["date"] = pd.to_datetime(frame.time.str[:10])
        frame["qualifier"] = frame.qualifier.map(lambda q: ";".join(q) if isinstance(q, list) else (q or ""))
        pieces.append(frame[["site_id", "date", "value", "approval_status", "qualifier"]])
    long = pd.concat(pieces, ignore_index=True)
    long["value"] = pd.to_numeric(long.value, errors="coerce")
    report = qc_long_frame(long)
    clean = clean_long_frame(long, report=report, min_qualified_years=0)
    report.to_csv(OUT / "ingest_qc_report.csv", index=False)
    rows = []
    for network, block in members.groupby("network_id"):
        stations = block.station_id.tolist()
        subset = clean.loc[clean.site_id.isin(stations)]
        panel = subset.pivot_table(index="date", columns="site_id", values="temperature_c", aggfunc="first").reindex(columns=stations)
        if panel.dropna(how="all").empty:
            continue
        panel = panel.asfreq("D")
        panel.index.name = "date"
        path = DATA / "networks" / network / "daily_wide_temperature.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        panel.reset_index().to_csv(path, index=False, date_format="%Y-%m-%d", float_format="%.4g")
        for member in block.itertuples(index=False):
            series = panel[member.station_id] if member.station_id in panel else pd.Series(dtype=float)
            years = series.groupby(series.index.year).apply(lambda s: bool(s.notna().all() and len(s) == (366 if pd.Timestamp(int(s.index[0].year), 12, 31).is_leap_year else 365))) if len(series) else pd.Series(dtype=bool)
            rows.append({**member._asdict(), "input_path": str(path.relative_to(T.ROOT)), "n_complete_years_values": int(years.sum()), "n_values": int(series.notna().sum())})
    roster = pd.DataFrame(rows)
    sealed = roster.loc[roster.role.eq("target")]
    sealed.to_csv(OUT / "sealed_roster.csv", index=False)
    roster.to_csv(OUT / "sealed_members_with_values.csv", index=False)
    raw_files = [str(path.relative_to(T.ROOT)) for path in sorted((DATA / "values_raw").glob("*.json"))]
    summary = {
        "read_utc": datetime.now(timezone.utc).isoformat(),
        "n_members_with_values": int((roster.n_values > 0).sum()), "n_targets": len(sealed),
        "n_targets_whose_complete_years_changed": int((sealed.n_complete_years_values != sealed.n_complete_years).sum()),
        "qc_verdicts": report.verdict.astype(str).value_counts().to_dict(), "raw_files": raw_files,
    }
    T.write_json(OUT / "sealed_values.json", summary)
    print({key: value for key, value in summary.items() if key != "raw_files"}, flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--design", action="store_true")
    group.add_argument("--values", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    return design(args.workers) if args.design else values(args.workers)


if __name__ == "__main__":
    raise SystemExit(main())

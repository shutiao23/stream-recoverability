#!/usr/bin/env python3
"""E5a — coordinates for every station in the panel.

The v17 air-driven estimator is supported on 2.3% of development cases and
0.85% of reserved cases, and the supplement explains why: air temperature was
joined only "where it was already available in the archive". That is the most
exposed part of the study for a water-resources audience, because
air-temperature regression is the standard way this field fills a stream
temperature record, and 36 of the 110 development networks have no synchronous
donor at all -- for those stations the estimator library collapses to
climatology and interpolation.

The obstacle was never data availability. It is that station coordinates were
never carried into the pipeline. This script assembles them from the catalogues
already in the repository and, for the two providers those do not cover, from
the agencies' own public endpoints. Every row records where its coordinate came
from, because a coordinate with no provenance is not evidence.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.panel import station_roster  # noqa: E402
from stream_recoverability.experiments.v18_closure.paths import (  # noqa: E402
    E5_AIR,
    STATION_COORDINATES,
)

TIMEOUT = 120
USGS_BATCH = 60
ARSO_XML = "http://www.arso.gov.si/xml/vode/hidro_podatki_zadnji.xml"
NWIS = "https://waterservices.usgs.gov/nwis/site/?format=rdb&siteOutput=expanded&sites="

LOCAL_CATALOGUES = {
    "foen": ("results/framework/public_catalog/foen_temperature_station_metadata_20260826.csv", "site_id", "latitude", "longitude"),
    "chmi": ("results/development_v11/chmi_temperature/official_station_catalog.csv", "site_id", "latitude", "longitude"),
    "syke": ("results/development_v11/syke_surface_temperature/official_station_catalog.csv", "site_id", "latitude", "longitude"),
    "lubw": ("results/development_v11/lubw_temperature/official_station_catalog.csv", "site_id", "latitude", "longitude"),
    "gkd_bayern": ("results/development_v11/gkd_bayern_temperature/station_catalog.csv", "site_id", "latitude", "longitude"),
    "nve_hydapi": ("results/development_v11/second_confirmation/nve/series_catalog.csv", "site_id", "latitude", "longitude"),
    "rws_waterwebservices": ("results/framework/public_catalog/rws_temperature_locations.csv", "Code", "Lat", "Lon"),
    "usgs": ("results/framework/public_catalog/usgs_station_catalog.csv", "site_id", "latitude", "longitude"),
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "stream-recoverability/1.0"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def from_local() -> pd.DataFrame:
    rows = []
    for provider, (path, id_column, lat, lon) in LOCAL_CATALOGUES.items():
        full = ROOT / path
        if not full.exists():
            continue
        frame = pd.read_csv(full, dtype={id_column: str}, low_memory=False)
        frame = frame.loc[frame[lat].notna() & frame[lon].notna()]
        for row in frame.itertuples():
            rows.append(
                {
                    "provider": provider,
                    "station_id": str(getattr(row, id_column)).strip(),
                    "latitude": float(getattr(row, lat)),
                    "longitude": float(getattr(row, lon)),
                    "coordinate_source": f"repository catalogue: {path}",
                }
            )
    return pd.DataFrame(rows).drop_duplicates(subset=["provider", "station_id"])


def from_nwis(site_ids: list[str]) -> pd.DataFrame:
    rows = []
    for start in range(0, len(site_ids), USGS_BATCH):
        batch = site_ids[start : start + USGS_BATCH]
        try:
            payload = fetch(NWIS + ",".join(batch)).decode("utf-8", errors="replace")
        except Exception as error:  # noqa: BLE001 - provenance matters more than the class
            print(f"  NWIS batch {start // USGS_BATCH}: {error}", file=sys.stderr)
            continue
        lines = [line for line in payload.splitlines() if line and not line.startswith("#")]
        if len(lines) < 3:
            continue
        frame = pd.read_csv(io.StringIO("\n".join([lines[0]] + lines[2:])), sep="\t", dtype=str)
        for row in frame.itertuples():
            latitude = getattr(row, "dec_lat_va", None)
            longitude = getattr(row, "dec_long_va", None)
            if not latitude or not longitude or pd.isna(latitude) or pd.isna(longitude):
                continue
            rows.append(
                {
                    "provider": "usgs",
                    "station_id": str(row.site_no).strip(),
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "coordinate_source": "USGS NWIS site service",
                }
            )
    return pd.DataFrame(rows)


def from_arso() -> pd.DataFrame:
    try:
        payload = fetch(ARSO_XML)
    except Exception as error:  # noqa: BLE001
        print(f"  ARSO: {error}", file=sys.stderr)
        return pd.DataFrame()
    root = ET.fromstring(payload)
    rows = []
    for station in root.iter("postaja"):
        code = station.get("sifra")
        latitude = station.get("wgs84_sirina")
        longitude = station.get("wgs84_dolzina")
        if not code or not latitude or not longitude:
            continue
        rows.append(
            {
                "provider": "arso",
                "station_id": str(code).strip(),
                "latitude": float(latitude),
                "longitude": float(longitude),
                "coordinate_source": "ARSO hidro_podatki_zadnji.xml",
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    E5_AIR.mkdir(parents=True, exist_ok=True)
    STATION_COORDINATES.parent.mkdir(parents=True, exist_ok=True)

    roster = station_roster()
    roster = roster.loc[roster["eligible_station"]].copy()
    roster["station_id"] = roster["station_id"].astype(str).str.strip()
    wanted = roster[["network_id", "station_id", "provider"]].drop_duplicates()

    print("assembling from repository catalogues")
    coordinates = from_local()

    merged = wanted.merge(coordinates, on=["provider", "station_id"], how="left")
    missing_usgs = sorted(
        merged.loc[merged["latitude"].isna() & merged["provider"].eq("usgs"), "station_id"].unique()
    )
    if missing_usgs:
        print(f"querying NWIS for {len(missing_usgs)} USGS sites")
        extra = from_nwis(missing_usgs)
        if not extra.empty:
            coordinates = pd.concat([coordinates, extra], ignore_index=True)

    if merged.loc[merged["latitude"].isna() & merged["provider"].eq("arso")].shape[0]:
        print("querying ARSO")
        extra = from_arso()
        if not extra.empty:
            coordinates = pd.concat([coordinates, extra], ignore_index=True)

    coordinates = coordinates.drop_duplicates(subset=["provider", "station_id"], keep="first")
    final = wanted.merge(coordinates, on=["provider", "station_id"], how="left")
    final = final.loc[final["latitude"].between(-90, 90) | final["latitude"].isna()]
    final.to_csv(STATION_COORDINATES, index=False)

    coverage = (
        final.assign(has_coordinate=final["latitude"].notna())
        .groupby("provider")
        .agg(stations=("station_id", "size"), with_coordinate=("has_coordinate", "sum"))
        .reset_index()
    )
    coverage["coverage_pct"] = coverage["with_coordinate"] / coverage["stations"] * 100
    coverage.to_csv(E5_AIR / "coordinate_coverage.csv", index=False)

    summary = {
        "n_stations": int(len(final)),
        "n_with_coordinates": int(final["latitude"].notna().sum()),
        "coverage_pct": float(final["latitude"].notna().mean() * 100),
        "by_source": final["coordinate_source"].value_counts(dropna=False).to_dict(),
        "still_missing": final.loc[final["latitude"].isna(), ["provider", "station_id"]].to_dict(
            orient="records"
        )[:40],
    }
    (E5_AIR / "coordinate_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(coverage.to_string(index=False))
    print(f"\ntotal coverage {summary['coverage_pct']:.1f}% ({summary['n_with_coordinates']}/{summary['n_stations']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

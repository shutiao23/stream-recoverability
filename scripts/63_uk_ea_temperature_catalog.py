#!/usr/bin/env python3
"""UK Environment Agency hydrology temperature station catalog. Metadata only.

Does not download time series. Does not invent daily years. Not a T8 count.
The hydrology API is documented as sub-daily; dateOpened is not an 8-year daily span.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import urllib.parse

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.http_json import get_json

OUTPUT = ROOT / "results/framework/public_catalog"
EA_STATIONS = "https://environment.data.gov.uk/hydrology/id/stations.json"
PAGE = 200


def _fetch_all() -> list[dict]:
    items: list[dict] = []
    offset = 0
    while True:
        url = EA_STATIONS + "?" + urllib.parse.urlencode(
            {
                "observedProperty": "temperature",
                "_limit": str(PAGE),
                "_offset": str(offset),
            }
        )
        document = get_json(url, timeout=60, retries=3)
        chunk = document.get("items") or []
        items.extend(chunk)
        if len(chunk) < PAGE:
            break
        offset += PAGE
        if offset > 5000:
            break
    return items


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    try:
        raw = _fetch_all()
    except Exception as error:
        manifest = {
            "what_this_is": "UK EA temperature station catalog attempt.",
            "what_this_is_not": "Not daily years. Not T8.",
            "ok": False,
            "error": str(error),
            "n_stations": 0,
            "countable_toward_t8": False,
            "europe_daily_years_invented": False,
        }
        (OUTPUT / "uk_ea_catalog_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(manifest, indent=2))
        return
    rows = []
    for item in raw:
        opened = item.get("dateOpened")
        rows.append(
            {
                "site_id": item.get("notation") or item.get("@id"),
                "name": item.get("label"),
                "river": item.get("riverName"),
                "latitude": item.get("lat"),
                "longitude": item.get("long"),
                "date_opened": opened,
                "source": "uk_ea_hydrology",
                "temporal_resolution": "sub_daily_api",
                "has_public_daily_span": False,
            }
        )
    frame = pd.DataFrame(rows).drop_duplicates("site_id")
    frame.to_csv(OUTPUT / "uk_ea_temperature_stations.csv", index=False)
    clusters = pd.DataFrame()
    if not frame.empty and "river" in frame.columns:
        named = frame.loc[frame["river"].fillna("").astype(str).str.strip().ne("")]
        counts = named.groupby("river", sort=False).size()
        keep = counts[counts.ge(3)].index
        if len(keep):
            clusters = (
                named.loc[named["river"].isin(keep)]
                .groupby("river", sort=False)
                .agg(n_stations=("site_id", "nunique"), site_ids=("site_id", lambda s: ",".join(s)))
                .reset_index()
            )
            clusters["countable_public_daily"] = False
            clusters.to_csv(OUTPUT / "uk_ea_river_clusters.csv", index=False)
    manifest = {
        "what_this_is": (
            "UK EA hydrology stations with observedProperty=temperature "
            "(sub-daily API)."
        ),
        "what_this_is_not": (
            "Not dated daily series. Not eight-year overlap. Not T8. "
            "dateOpened is not a daily-year span."
        ),
        "ok": True,
        "n_stations": int(len(frame)),
        "n_with_river_name": int(frame["river"].fillna("").astype(str).str.strip().ne("").sum()) if not frame.empty else 0,
        "n_name_clusters_3plus": int(len(clusters)),
        "countable_toward_t8": False,
        "europe_daily_years_invented": False,
        "temporal_resolution": "sub_daily_api",
        "formal_evidence": False,
    }
    (OUTPUT / "uk_ea_catalog_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

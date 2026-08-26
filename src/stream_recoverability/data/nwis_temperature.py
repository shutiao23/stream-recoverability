"""USGS NWIS site catalog and daily temperature. Used when the newer API is limited."""

from __future__ import annotations

import time
import urllib.parse
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.data.http_json import USER_AGENT, get_json
from stream_recoverability.data.public_river_inventory import years_from_span

NWIS_SITE = "https://waterservices.usgs.gov/nwis/site/"
NWIS_DV = "https://waterservices.usgs.gov/nwis/dv/"
STATE_CDS = {
    "al": "Alabama",
    "ak": "Alaska",
    "az": "Arizona",
    "ar": "Arkansas",
    "ca": "California",
    "co": "Colorado",
    "ct": "Connecticut",
    "de": "Delaware",
    "fl": "Florida",
    "ga": "Georgia",
    "id": "Idaho",
    "il": "Illinois",
    "in": "Indiana",
    "ia": "Iowa",
    "ks": "Kansas",
    "ky": "Kentucky",
    "la": "Louisiana",
    "me": "Maine",
    "md": "Maryland",
    "ma": "Massachusetts",
    "mi": "Michigan",
    "mn": "Minnesota",
    "ms": "Mississippi",
    "mo": "Missouri",
    "mt": "Montana",
    "ne": "Nebraska",
    "nv": "Nevada",
    "nh": "New Hampshire",
    "nj": "New Jersey",
    "nm": "New Mexico",
    "ny": "New York",
    "nc": "North Carolina",
    "nd": "North Dakota",
    "oh": "Ohio",
    "ok": "Oklahoma",
    "or": "Oregon",
    "pa": "Pennsylvania",
    "ri": "Rhode Island",
    "sc": "South Carolina",
    "sd": "South Dakota",
    "tn": "Tennessee",
    "tx": "Texas",
    "ut": "Utah",
    "vt": "Vermont",
    "va": "Virginia",
    "wa": "Washington",
    "wv": "West Virginia",
    "wi": "Wisconsin",
    "wy": "Wyoming",
}


def _get_text(url: str, timeout: int = 90) -> str:
    import urllib.request

    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/plain"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def read_rdb(text: str) -> pd.DataFrame:
    lines = [
        line
        for line in text.splitlines()
        if line and not line.startswith("#")
    ]
    if len(lines) < 3:
        return pd.DataFrame()
    body = "\n".join([lines[0], *lines[2:]])
    return pd.read_csv(StringIO(body), sep="\t", dtype={"site_no": str})


def nwis_state_daily_temperature_catalog(state_cd: str) -> pd.DataFrame:
    url = NWIS_SITE + "?" + urllib.parse.urlencode(
        {
            "format": "rdb",
            "stateCd": state_cd.lower(),
            "parameterCd": "00010",
            "siteType": "ST",
            "hasDataTypeCd": "dv",
            "outputDataTypeCd": "dv",
            "siteStatus": "all",
        }
    )
    frame = read_rdb(_get_text(url))
    if frame.empty:
        return frame
    parm = pd.to_numeric(frame.get("parm_cd"), errors="coerce")
    stat = pd.to_numeric(frame.get("stat_cd"), errors="coerce")
    keep = frame.loc[parm.eq(10) & stat.eq(3)].copy()
    if keep.empty:
        return keep
    keep["site_id"] = keep["site_no"].astype(str)
    keep["name"] = keep["station_nm"]
    keep["latitude"] = pd.to_numeric(keep["dec_lat_va"], errors="coerce")
    keep["longitude"] = pd.to_numeric(keep["dec_long_va"], errors="coerce")
    keep["huc"] = keep["huc_cd"].astype(str)
    keep["daily_begin"] = keep["begin_date"]
    keep["daily_end"] = keep["end_date"]
    keep["span_years"] = [
        years_from_span(start, stop)
        for start, stop in zip(keep["daily_begin"], keep["daily_end"])
    ]
    keep["state_name"] = STATE_CDS.get(state_cd.lower(), state_cd)
    keep["site_type"] = "Stream"
    keep["found"] = True
    keep["has_daily_temperature"] = True
    return keep[
        [
            "site_id",
            "name",
            "latitude",
            "longitude",
            "huc",
            "daily_begin",
            "daily_end",
            "span_years",
            "state_name",
            "site_type",
            "found",
            "has_daily_temperature",
        ]
    ].drop_duplicates("site_id")


def nwis_national_daily_temperature_catalog(pause_s: float = 0.35) -> pd.DataFrame:
    frames = []
    for code, name in STATE_CDS.items():
        try:
            table = nwis_state_daily_temperature_catalog(code)
        except Exception as error:
            print(f"nwis catalog {name}: {error}", flush=True)
            time.sleep(pause_s)
            continue
        print(f"nwis catalog {name}: {len(table)} daily-mean T sites", flush=True)
        if not table.empty:
            frames.append(table)
        time.sleep(pause_s)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates("site_id")


def nwis_daily_temperature(
    site_id: str,
    start: str,
    end: str,
    *,
    cache_dir: Path | None = None,
) -> pd.DataFrame:
    root = Path("data/public_rivers") if cache_dir is None else Path(cache_dir)
    dest = root / "nwis" / f"{site_id}_{start}_{end}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        frame = pd.read_csv(dest)
        frame["date"] = pd.to_datetime(frame["date"])
        return frame
    url = NWIS_DV + "?" + urllib.parse.urlencode(
        {
            "format": "json",
            "sites": site_id,
            "parameterCd": "00010",
            "statCd": "00003",
            "startDT": start,
            "endDT": end,
        }
    )
    document = get_json(url, timeout=120, retries=4, base_pause_s=1.0)
    series = ((document.get("value") or {}).get("timeSeries") or [])
    rows: list[dict[str, Any]] = []
    for item in series:
        for point in ((item.get("values") or [{}])[0].get("value") or []):
            rows.append(
                {
                    "site_id": site_id,
                    "date": point.get("dateTime"),
                    "temperature_c": point.get("value"),
                    "qualifier": point.get("qualifiers"),
                }
            )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce").dt.tz_localize(
            None
        ).dt.normalize()
        frame["temperature_c"] = pd.to_numeric(frame["temperature_c"], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date")
    else:
        frame = pd.DataFrame(columns=["site_id", "date", "temperature_c", "qualifier"])
    frame.to_csv(dest, index=False)
    return frame


__all__ = [
    "nwis_daily_temperature",
    "nwis_national_daily_temperature_catalog",
    "nwis_state_daily_temperature_catalog",
    "read_rdb",
]

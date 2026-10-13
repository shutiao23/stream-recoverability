#!/usr/bin/env python3
"""Standalone provenance check: the scripts/242 code-1 window path == shared module path.

No candidate station in the transport panel carries Sandre code 1, so the ingest's own
module-consistency check reports "not performed".  This check exercises the same code-1
URL/row path on a station that the Hub'Eau API itself reports as having code-1 data.

Writes scratch/hubeau_ingest/module_check_code1.json
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.parse
from pathlib import Path

import pandas as pd

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.data.hubeau_temperature import (  # noqa: E402
    HUBEAU_CHRONIQUE,
    hubeau_chronique_rows,
    hubeau_window_url,
)
from stream_recoverability.data.http_json import get_json  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "ing242", ROOT / "scripts/242_multi_agency_hubeau_ingest.py"
)
ing = importlib.util.module_from_spec(spec)
sys.modules["ing242"] = ing
spec.loader.exec_module(ing)

# 1) let the API name a station that has Sandre code 1 data
listing = get_json(
    HUBEAU_CHRONIQUE
    + "?"
    + urllib.parse.urlencode({"code_qualification": "1", "size": "1", "page": "1", "sort": "asc"}),
    timeout=60,
)
first = (listing.get("data") or [{}])[0]
station_id = str(first.get("code_station"))
year = int(str(first.get("date_mesure_temp"))[:4])
span = get_json(
    HUBEAU_CHRONIQUE
    + "?"
    + urllib.parse.urlencode(
        {"code_station": station_id, "code_qualification": "1", "size": "1", "page": "1", "sort": "desc"}
    ),
    timeout=60,
)
last_year = int(str((span.get("data") or [{}])[0].get("date_mesure_temp"))[:4])

hub = ing.CachedHub(ing.RAW, workers=1, timeout=90, retries=3, pause=0.0, outer_retries=2)
start = pd.Timestamp(year=year, month=1, day=1)
end = pd.Timestamp(year=year, month=12, day=31)
url_script = ing.window_url(station_id, str(start.date()), str(end.date()), "1")
url_module = hubeau_window_url(station_id, str(start.date()), str(end.date()))
script_rows = ing.fetch_window(hub, station_id, start, end, "1")
module_rows = hubeau_chronique_rows(station_id, start, end)


def key(item):
    value = item.get("temperature_c") if "temperature_c" in item else item.get("resultat")
    return (str(item.get("date") or item.get("date_mesure_temp")), round(float(value), 6))


payload = {
    "station_id": station_id,
    "station_span_years_with_code1": [year, last_year],
    "window": f"{start.date()}..{end.date()}",
    "url_identical": url_script == url_module,
    "url": url_module,
    "n_script_rows": len(script_rows),
    "n_module_rows": len(module_rows),
    "rows_identical_on_date_and_value": sorted(map(key, script_rows)) == sorted(map(key, module_rows)),
    "script_rows_carry_heure_mesure_temp": bool(script_rows and "heure" in script_rows[0]),
    "note": (
        "scripts/242 window_url asserts byte-equality with hubeau_window_url for every code-1 "
        "request; this check exercises that path on an API-listed code-1 station"
    ),
}
(ROOT / "scratch/hubeau_ingest/module_check_code1.json").write_text(
    json.dumps(payload, indent=2) + "\n"
)
print(json.dumps(payload, indent=2))

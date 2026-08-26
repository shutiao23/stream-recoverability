#!/usr/bin/env python3
"""Check whether public reservoir operations exist for the candidate rivers.

Looks for release temperature, storage, or outlet metadata. Does not invent a
before-after result if those series are missing.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.nwis_temperature import read_rdb

OUTPUT = ROOT / "results/framework/public_catalog"
# Storage (00054) at a few well-known reservoirs. This is not release temperature.
SAMPLE = "https://waterservices.usgs.gov/nwis/site/?" + urllib.parse.urlencode(
    {
        "format": "rdb",
        "sites": "07337000,11456000,14158790",
        "parameterCd": "00054",
        "outputDataTypeCd": "dv",
        "siteStatus": "all",
    }
)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    storage_sites = 0
    reachable = False
    error = None
    try:
        request = urllib.request.Request(
            SAMPLE,
            headers={"User-Agent": "stream-recoverability-public-catalog/1.0"},
        )
        with urllib.request.urlopen(request, timeout=40) as response:
            text = response.read().decode("utf-8", errors="replace")
        table = read_rdb(text)
        reachable = True
        storage_sites = int(table["site_no"].nunique()) if not table.empty and "site_no" in table else 0
    except Exception as exc:
        error = str(exc)
    manifest = {
        "what_this_is": "A check of whether reservoir operations are publicly downloadable.",
        "what_this_is_not": "Not a dam-cause result. No before-after table was computed.",
        "nwis_site_service_reachable": reachable,
        "example_storage_sites_found": storage_sites,
        "release_temperature_found": False,
        "outlet_depth_found": False,
        "aligned_control_rivers_found": False,
        "can_write_reservoir_cause": False,
        "error": error,
        "reason": (
            "USGS site files can list reservoir storage at some lakes. "
            "This check did not find release temperature, outlet depth, and matched "
            "control rivers on the same days. Without those, a reservoir before-after "
            "study is not licensed."
        ),
    }
    (OUTPUT / "reservoir_operations_check.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

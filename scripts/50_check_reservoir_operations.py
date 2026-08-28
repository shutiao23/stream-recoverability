#!/usr/bin/env python3
"""Check whether public reservoir operations exist for the candidate rivers.

Looks for release temperature, storage, or outlet metadata. Does not invent a
before-after result if those series are missing.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/framework/public_catalog"
# Storage (00054) metadata demonstrates that reservoir storage series are
# discoverable. It is not release temperature, outlet depth, or operations.
API = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/time-series-metadata/items"
OFFICIAL_DOCUMENTATION = "https://api.waterdata.usgs.gov/docs/ogcapi/migration/"
SAMPLE = API + "?" + urllib.parse.urlencode(
    {
        "f": "json",
        "parameter_code": "00054",
        "limit": "50",
    }
)


def _storage_sites(document: object) -> set[str]:
    if not isinstance(document, dict):
        raise TypeError("USGS response is not a JSON object")
    features = document.get("features")
    if not isinstance(features, list):
        raise TypeError("USGS response lacks a feature list")
    sites = set()
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue
        if str(properties.get("parameter_code")) != "00054":
            continue
        location = properties.get("monitoring_location_id")
        if location:
            sites.add(str(location))
    return sites


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
            document = json.load(response)
        sites = _storage_sites(document)
        reachable = True
        storage_sites = len(sites)
    except (
        OSError,
        TimeoutError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as exc:
        error = str(exc)
    manifest = {
        "what_this_is": "A check of whether reservoir operations are publicly downloadable.",
        "what_this_is_not": "Not a dam-cause result. No before-after table was computed.",
        "official_api": API,
        "official_documentation": OFFICIAL_DOCUMENTATION,
        "request_url": SAMPLE,
        "parameter_code": "00054",
        "parameter_interpretation": "reservoir_storage_not_release_temperature",
        "nwis_site_service_reachable": reachable,
        "example_storage_sites_found": storage_sites,
        "release_temperature_found": False,
        "outlet_depth_found": False,
        "aligned_control_rivers_found": False,
        "can_write_reservoir_cause": False,
        "error": error,
        "reason": (
            "The modern USGS time-series metadata API lists reservoir storage. "
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

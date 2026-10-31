#!/usr/bin/env python3
"""Investigate all additional metadata-qualified YSI/EXO/HOBO channel pairs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlparse

import pandas as pd
import requests

import wrr_r3_common as C

RAW = C.ROOT / "data/external/wrr_public_backup_20261021"
OUT = C.READY / "followup_20261021/public_backup_search/named_instruments"
CONFIG = C.ROOT / "configs/wrr_usgs_named_instruments_20261021.json"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def modules():
    resource = importlib.import_module("394_wrr_public_backup_resource")
    qualification = importlib.import_module("395_wrr_usgs_backup_qualification")
    for module in [resource, qualification]:
        module.CONFIG = CONFIG
        module.OUT = OUT
    resource.SELECTION = OUT / "usgs_metadata_selection.json"
    return resource, qualification


def native_channel_ids(item):
    descriptions = {}
    with (RAW / f"usgs_{item['site']}_native_temperature.rdb").open() as handle:
        for line in handle:
            if not line.startswith("#"):
                break
            match = re.match(r"#\s+([a-zA-Z0-9]+)\s+00010\s+(.+)", line)
            if match:
                descriptions[match[1] + "_00010"] = match[2].strip()
    backup = [key for key, value in descriptions.items() if item["native_backup_marker"].casefold() in value.casefold()]
    primary = [key for key in descriptions if key not in backup]
    if len(primary) != 1 or len(backup) != 1:
        raise RuntimeError(f"Ambiguous channel-to-metadata assignment at {item['site']}")
    return primary[0], backup[0]


def fetch_annual(resource):
    """Partition an oversized public request without changing the analysis dates."""
    resource.record_selection()
    settings = json.loads(CONFIG.read_text())
    for item in settings["candidates"]:
        native = RAW / f"usgs_{item['site']}_native_temperature.rdb"
        if native.exists():
            continue
        pieces, custody, descriptions = [], [], {}
        for year in range(int(item["acquire_from"][:4]), int(item["acquire_through"][:4]) + 1):
            path = RAW / "annual_native" / f"{item['site']}_{year}.rdb"
            params = {"format": "rdb", "sites": item["site"], "parameterCd": "00010",
                      "startDT": f"{year}-01-01", "endDT": f"{year}-12-31", "siteStatus": "all"}
            if not path.exists():
                response = requests.get("https://waterservices.usgs.gov/nwis/iv/", params=params, timeout=120)
                response.raise_for_status()
                if len(response.content) > 64 << 20:
                    raise RuntimeError("Annual native response exceeded 64 MiB")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(response.content)
            text = path.read_text()
            for line in text.splitlines():
                match = re.match(r"#\s+(\d+)\s+00010\s+(.+)", line)
                if match:
                    descriptions[match[1]] = match[2].strip()
            pieces.append(pd.read_csv(io.StringIO(text), sep="\t", comment="#", dtype=str).iloc[1:])
            custody.append({"path": str(path.relative_to(C.ROOT)),
                            "parameters": params, "bytes": path.stat().st_size})
            print(f"[396] staged annual native {item['site']} {year}", flush=True)
        combined = pd.concat(pieces, ignore_index=True)
        comments = ["# Composite of byte-preserved annual public responses listed in annual acquisition manifest.",
                    "# TS_ID Parameter Description"]
        comments.extend(f"# {key} 00010 {value}" for key, value in sorted(descriptions.items()))
        schema = pd.DataFrame([{column: "32s" for column in combined.columns}])
        temporary = native.with_suffix(".partial")
        with temporary.open("w") as handle:
            handle.write("\n".join(comments) + "\n")
            pd.concat([schema, combined], ignore_index=True).to_csv(handle, sep="\t", index=False)
        temporary.replace(native)
        C.write_json(OUT / f"annual_acquisition_{item['site']}.json", {
            "site": item["site"], "reason": "original long public request returned HTTP 503 twice",
            "native_values_interpolated_or_edited": False, "annual_provider_responses": custody,
            "composite_path": str(native.relative_to(C.ROOT))})
    resource.fetch()


def ogc_native_rows(features, site, allowed_ids):
    rows = []
    for feature in features:
        item = feature["properties"]
        identifier = item["time_series_id"]
        if identifier not in allowed_ids or item["monitoring_location_id"] != "USGS-" + site or item["parameter_code"] != "00010" or item["unit_of_measure"] != "degC":
            raise ValueError("OGC response does not match the selected temperature channels")
        status = {"Approved": "A", "Provisional": "P"}.get(item["approval_status"])
        if status is None:
            raise ValueError("Unrecognised USGS observation approval status")
        qualifier = item.get("qualifier")
        if qualifier:
            status += "," + (";".join(map(str, qualifier)) if isinstance(qualifier, list) else str(qualifier))
        channel = identifier + "_00010"
        rows.append({"agency_cd": "USGS", "site_no": site, "datetime": item["time"], "tz_cd": "UTC",
                     channel: item["value"], channel + "_cd": status})
    return rows


def fetch_ogc(resource):
    """Use the documented public replacement API when legacy retrieval fails."""
    resource.record_selection()
    settings = json.loads(CONFIG.read_text())
    for item in settings["candidates"]:
        native = RAW / f"usgs_{item['site']}_native_temperature.rdb"
        if native.exists():
            continue
        site = item["site"]
        allowed_ids = {item["primary_metadata_id"], item["backup_metadata_id"]}
        rows, custody = [], []
        for year in range(int(item["acquire_from"][:4]), int(item["acquire_through"][:4]) + 1):
            url = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items"
            params = {"f": "json", "monitoring_location_id": "USGS-" + site, "parameter_code": "00010",
                      "time": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z", "limit": 50000}
            page = 1
            while url:
                if urlparse(url).hostname != "api.waterdata.usgs.gov":
                    raise RuntimeError("Unexpected OGC pagination host")
                path = RAW / "ogc_native" / f"{site}_{year}_{page:03d}.json"
                if not path.exists():
                    response = requests.get(url, params=params, timeout=120)
                    response.raise_for_status()
                    if len(response.content) > 64 << 20:
                        raise RuntimeError("OGC page exceeded 64 MiB")
                    path.parent.mkdir(exist_ok=True, parents=True)
                    path.write_bytes(response.content)
                payload = json.loads(path.read_text())
                features = payload["features"]
                if payload.get("numberReturned", len(features)) != len(features):
                    raise RuntimeError("Truncated OGC page")
                rows.extend(ogc_native_rows(features, site, allowed_ids))
                custody.append({"path": str(path.relative_to(C.ROOT)),
                                "bytes": path.stat().st_size, "rows": len(features)})
                next_links = [link["href"] for link in payload.get("links", []) if link.get("rel") == "next"]
                if len(next_links) > 1 or page > 30:
                    raise RuntimeError("Invalid OGC pagination")
                url, params = (next_links[0], None) if next_links else (None, None)
                print(f"[396] OGC {site} {year} page {page}: {len(features)} native observations", flush=True)
                page += 1
        combined = pd.DataFrame(rows)
        comments = ["# Derived tabular serialization of unchanged public OGC time/value/status strings.",
                    "# OGC_series_id Parameter Description",
                    f"# {item['primary_metadata_id']} 00010 Temperature, water, degrees Celsius",
                    f"# {item['backup_metadata_id']} 00010 Temperature, water, degrees Celsius, {item['native_backup_marker']}"]
        schema = pd.DataFrame([{column: "80s" for column in combined.columns}])
        temporary = native.with_suffix(".partial")
        with temporary.open("w") as handle:
            handle.write("\n".join(comments) + "\n")
            pd.concat([schema, combined], ignore_index=True).to_csv(handle, sep="\t", index=False)
        temporary.replace(native)
        C.write_json(OUT / f"ogc_acquisition_{site}.json", {
            "site": site, "endpoint": "https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items",
            "public_unauthenticated_access": True, "reason": "legacy full-range and annual retrieval returned HTTP 503",
            "native_values_interpolated_or_edited": False, "provider_pages": custody,
            "composite_path": str(native.relative_to(C.ROOT)),
            "status_serialization": "Approved -> A; Provisional -> P; every nonempty qualifier appended and excluded by main reference QC"})
    resource.fetch()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["fetch", "fetch-annual", "fetch-ogc", "qualify", "qualify-available"])
    args = parser.parse_args()
    resource, qualification = modules()
    if args.action == "fetch":
        try:
            resource.fetch()
        except requests.HTTPError as error:
            if error.response is None or error.response.status_code not in {500, 502, 503, 504}:
                raise
            print("[396] legacy service failed; continuing via the public OGC replacement", flush=True)
            fetch_ogc(resource)
    elif args.action == "fetch-annual":
        fetch_annual(resource)
    elif args.action == "fetch-ogc":
        fetch_ogc(resource)
    else:
        settings = json.loads(CONFIG.read_text())
        available = [item for item in settings["candidates"] if (RAW / f"usgs_{item['site']}_native_temperature.rdb").exists()]
        qualification.CHANNELS = {item["site"]: native_channel_ids(item) for item in available}
        if args.action == "qualify-available":
            records = [{"site": item["site"], "path": str((RAW / f"usgs_{item['site']}_native_temperature.rdb").relative_to(C.ROOT))}
                       for item in available]
            path = OUT / "usgs_partial_acquisition.json"
            C.write_json(path, {"records": records,
                               "pending_sites": [item["site"] for item in settings["candidates"] if item not in available],
                               "pending_sites_are_not_zero_eligible_sites": True})
            qualification.qualify(acquisition_path=path, allow_pending=True)
        else:
            qualification.qualify()
        C.write_json(OUT / "named_instrument_implementation.json", run_record(
                     {"resource_script": Path(resource.__file__),
                      "qualification_script": Path(qualification.__file__), "configuration": CONFIG},
                     channel_matching_uses_only_native_header_descriptions=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

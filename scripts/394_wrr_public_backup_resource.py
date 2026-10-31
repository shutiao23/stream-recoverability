#!/usr/bin/env python3
"""Record metadata-selected USGS pairs and acquire their public native records."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import requests

import wrr_r3_common as C

RAW = C.ROOT / "data/external/wrr_public_backup_20261021"
OUT = C.READY / "followup_20261021/public_backup_search"
CONFIG = C.ROOT / "configs/wrr_usgs_backup_20261021.json"
SELECTION = OUT / "usgs_metadata_selection.json"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def record_selection():
    """Record the metadata-selected candidates once, before historical temperatures are acquired."""
    settings = json.loads(CONFIG.read_text())
    if SELECTION.exists():
        return
    inputs = {"protocol": CONFIG,
              "national_channel_metadata": RAW / "usgs_national_instantaneous_temperature_metadata.json",
              "native_QC_schema": RAW / "usgs_continuous_queryables.json",
              "original_daily_qualification": C.ROOT / "scripts/388_wrr_natural_backup_validation.py"}
    for item in settings["candidates"]:
        inputs[f"site_{item['site']}"] = RAW / f"usgs_site_{item['site']}_metadata.json"
    C.write_json(SELECTION, run_record(inputs,
                 historical_temperature_values_inspected=False,
                 recovery_errors_inspected=False,
                 native_record_qualification_is_not_physical_sensor_verification=True))
    print(f"[394] recorded {len(settings['candidates'])} metadata candidates before historical temperature acquisition", flush=True)


def fetch():
    record_selection()
    settings = json.loads(CONFIG.read_text())
    evidence = []
    for item in settings["candidates"]:
        path = RAW / f"usgs_{item['site']}_native_temperature.rdb"
        params = {"format": "rdb", "sites": item["site"], "parameterCd": "00010",
                  "startDT": item["acquire_from"], "endDT": item["acquire_through"],
                  "siteStatus": "all"}
        if not path.exists():
            response = requests.get("https://waterservices.usgs.gov/nwis/iv/",
                                    params=params, timeout=120, stream=True)
            if response.status_code != 200:
                body = response.text
                C.write_json(OUT / f"usgs_{item['site']}_access_failure.json",
                             {"http_status": response.status_code, "url": response.url,
                              "response": body[:3000], "eligible_case_count": None})
                response.raise_for_status()
            temporary = path.with_suffix(".partial")
            count = 0
            with temporary.open("wb") as handle:
                for block in response.iter_content(1 << 20):
                    count += len(block)
                    if count > 256 << 20:
                        raise RuntimeError("USGS response exceeded 256 MiB staging limit")
                    handle.write(block)
            temporary.replace(path)
        evidence.append({"site": item["site"], "path": str(path.relative_to(C.ROOT)),
                         "bytes": path.stat().st_size,
                         "endpoint": "https://waterservices.usgs.gov/nwis/iv/", "parameters": params})
        print(f"[394] staged {item['site']} {path.stat().st_size} bytes", flush=True)
    payload = {"records": evidence,
               "acquisition_does_not_establish_eligibility_or_physical_independence": True}
    C.write_json(OUT / "usgs_acquisition.json", payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["select", "fetch-usgs"])
    args = parser.parse_args()
    if args.action == "select":
        record_selection()
    else:
        fetch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

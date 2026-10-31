#!/usr/bin/env python3
"""Inspect bounded large-river schemas without opening temperature measurements."""
from __future__ import annotations

import importlib
import io
import json
from pathlib import Path
import zipfile

import pandas as pd

import wrr_r3_common as C

M = importlib.import_module("397_wrr_public_neon_metadata")
OUT = C.READY / "followup_20261021/neon_large_river_metadata"
RAW = M.RAW / "large_river_metadata"
SITES = ("BLWA", "FLNT", "TOMB")
WORDS = ("variables_", "sensor_positions_", "readme_", "issueLog_")


def measured_temperature_fields(schema, table):
    rows = schema.loc[schema.table.eq(table)].copy()
    units = rows.units.fillna("").astype(str).str.lower()
    fields = rows.fieldName.astype(str)
    temperature = units.isin(["celsius", "degc", "°c"]) | fields.str.contains("temp", case=False)
    flag = fields.str.contains(r"QF$|QM$|Flag$", regex=True)
    return sorted(fields.loc[temperature & ~flag].tolist())


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    RAW.mkdir(exist_ok=True, parents=True)
    sources = []
    with zipfile.ZipFile(M.PublicArchive()) as outer:
        for kind in ("depth", "water_quality"):
            directory = M.OUT / f"figshare_{kind}_directory.json"
            manifest = json.loads(directory.read_text())
            info = outer.getinfo(manifest["archive"])
            if info.compress_type != 0:
                raise RuntimeError("Nested public archive is not the recorded stored member")
            offset = M.nested_offset(info)
            if offset != manifest["payload_offset"]:
                raise RuntimeError("Public nested archive offset changed")
            with zipfile.ZipFile(M.PublicArchive(offset, info.file_size)) as inner:
                for entry in inner.infolist():
                    pieces = entry.filename.split("/")
                    if len(pieces) != 3 or pieces[1] not in SITES or not any(word in Path(entry.filename).name for word in WORDS):
                        continue
                    payload = M.metadata_payload(inner, offset, entry)
                    path = RAW / f"{kind}_{pieces[1]}_{Path(entry.filename).name}"
                    if path.exists() and path.read_bytes() != payload:
                        raise RuntimeError("Previously acquired public metadata bytes changed")
                    path.write_bytes(payload)
                    pd.read_feather(io.BytesIO(payload)).to_csv(path.with_suffix(".csv"), index=False)
                    sources.append({"path": str(path.relative_to(C.ROOT)), "archive_entry": entry.filename,
                                    "uncompressed_bytes": entry.file_size, "measurement_table": False})
    if len(sources) != 24:
        raise RuntimeError("The expected three-site metadata inventory is incomplete")
    rows = []
    for site in SITES:
        depth = pd.read_feather(RAW / f"depth_{site}_variables_20264.feather")
        water = pd.read_feather(RAW / f"water_quality_{site}_variables_20288.feather")
        positions = pd.read_feather(RAW / f"depth_{site}_sensor_positions_20264.feather")
        fields = set(depth.loc[depth.table.eq("TSD_30_min"), "fieldName"])
        independent_keys = fields & {"sensorID", "sensorSerialNumber", "serialNumber", "deviceID", "sensorLocationID"}
        shallow = positions.loc[positions["HOR.VER"].astype(str).eq("103.501")]
        rows.append({"site": site, "depth_temperature_fields": ";".join(measured_temperature_fields(depth, "TSD_30_min")),
                     "WQ_measured_temperature_fields": ";".join(measured_temperature_fields(water, "waq_instantaneous")),
                     "separate_instrument_key_in_measurement_schema": ";".join(sorted(independent_keys)),
                     "shallow_metadata_location_ids": shallow.sensorLocationID.nunique(),
                     "shallow_metadata_depth_m": ";".join(map(str, sorted(shallow.zOffset.dropna().unique()))),
                     "multiple_metadata_names_prove_simultaneous_backup": False,
                     "one_minute_and_30_minute_are_independent_sensors": False,
                     "independent_backup_reference_identified": False,
                     "temperature_measurement_tables_opened": False})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "site_schema_scope.csv", index=False)
    C.write_json(OUT / "metadata_acquisition.json", {"sources": sources, "bounded_public_archive_metadata_only": True,
                 "independent_backup_measurement_series_acquired": False, "new_prediction_errors_opened": False})
    C.write_json(OUT / "summary.json", {"sites": list(SITES), "metadata_files": len(sources),
                 "water_quality_schemas_with_measured_temperature": int(frame.WQ_measured_temperature_fields.ne("").sum()),
                 "temperature_chain_measurement_schema_has_independent_device_key": bool(frame.separate_instrument_key_in_measurement_schema.ne("").any()),
                 "duplicate_shallow_position_metadata_resolves_sensor_custody": False,
                 "independent_backup_reference_identified": False,
                 "qualified_actual_gap_cases": None,
                 "unknown_case_count_is_not_zero_observations": True,
                 "temperature_measurement_tables_opened": False,
                 "scope": "no usable independent duplicate series identified by available schemas; multiple depths and aggregation periods do not establish such a reference",
                 "further_requirement": "separately identifiable simultaneous instruments, actual deployment and common-depth provenance, then unchanged overlap/history/coverage qualification"})
    print("[419] three large-river schemas checked; independent backup not identified; measurement tables unopened", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

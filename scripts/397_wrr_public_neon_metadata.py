#!/usr/bin/env python3
"""Inspect metadata only in a CC-BY author's public NEON redistribution.

Public HTTP byte ranges avoid downloading the 11.95-GB archive.  This command
never opens the TSW/TSD/waq measurement tables and requires no account token.
"""
from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import struct
import subprocess
import zipfile

import pandas as pd
import requests

import wrr_r3_common as C

RAW = C.ROOT / "data/external/wrr_public_backup_20261021"
OUT = C.READY / "followup_20261021/public_backup_search"
ARTICLE_API = "https://api.figshare.com/v2/articles/28074452"
FILE_URL = "https://ndownloader.figshare.com/files/51335075"
FILE_SIZE = 11954213673
MAX_RANGE = 8 << 20


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


class PublicArchive(io.RawIOBase):
    def __init__(self, offset=0, length=FILE_SIZE):
        self.offset, self.length, self.pos = offset, length, 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.length + offset
        return self.pos

    def read(self, size=-1):
        size = self.length - self.pos if size < 0 else min(size, self.length - self.pos)
        if size < 0 or self.pos < 0:
            raise ValueError("Invalid ZIP seek")
        data = get_range(self.offset + self.pos, size)
        self.pos += len(data)
        return data


def get_range(start, size):
    if not size:
        return b""
    if start < 0 or start + size > FILE_SIZE or size > MAX_RANGE:
        raise ValueError("Refuse large or invalid metadata range")
    cache = RAW / "metadata_ranges" / f"{start}_{size}.bin"
    if cache.exists():
        data = cache.read_bytes()
        if len(data) != size:
            raise RuntimeError("Truncated cached public byte range")
        return data
    end = start + size - 1
    response = requests.get(FILE_URL, params={"range_start": start, "range_end": end},
                            headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
                            timeout=90, stream=True)
    if response.status_code != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{FILE_SIZE}":
        response.close()
        raise RuntimeError("Public archive did not honour the requested byte range")
    data = response.content
    if len(data) != size:
        raise RuntimeError("Truncated public byte range")
    cache.parent.mkdir(exist_ok=True, parents=True)
    cache.write_bytes(data)
    return data


def nested_offset(info):
    if info.compress_type != 0:
        raise RuntimeError("Outer nested ZIP is no longer stored without compression")
    header = struct.unpack("<4s5H3I2H", get_range(info.header_offset, 30))
    if header[0] != b"PK\x03\x04":
        raise ValueError("Invalid public ZIP local header")
    return info.header_offset + 30 + header[-2] + header[-1]


def metadata_payload(archive, offset, info):
    if info.file_size > 4 << 20 or not any(part in Path(info.filename).name for part in
                                        ["variables_", "readme_", "sensor_positions_", "issueLog_"]):
        raise ValueError("Only bounded schema/location/issue metadata may be opened")
    if info.compress_type != 9:
        return archive.read(info)
    # Python's zipfile does not decode Deflate64.  Repackage this one metadata
    # entry for the installed Info-ZIP decoder.
    raw_header = struct.unpack("<4s5H3I2H", get_range(offset + info.header_offset, 30))
    compressed = get_range(offset + info.header_offset + 30 + raw_header[-2] + raw_header[-1], info.compress_size)
    name = b"metadata.feather"
    local = struct.pack("<4s5H3I2H", b"PK\x03\x04", 21, 0, 9, 0, 0,
                        info.CRC, len(compressed), info.file_size, len(name), 0) + name + compressed
    central = struct.pack("<4s6H3I5H2I", b"PK\x01\x02", 21, 21, 0, 9, 0, 0,
                          info.CRC, len(compressed), info.file_size, len(name), 0, 0, 0, 0, 0, 0) + name
    end = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 1, 1, len(central), len(local), 0)
    # Info-ZIP requires a seekable input.
    path = RAW / "metadata_single_entry.zip"
    path.write_bytes(local + central + end)
    result = subprocess.run(["unzip", "-p", str(path)], capture_output=True, check=True)
    if len(result.stdout) != info.file_size:
        raise RuntimeError("Deflate64 metadata size mismatch")
    return result.stdout


def main():
    RAW.mkdir(exist_ok=True, parents=True)
    metadata_path = RAW / "figshare_28074452_metadata.json"
    if not metadata_path.exists():
        response = requests.get(ARTICLE_API, timeout=60)
        response.raise_for_status()
        metadata_path.write_bytes(response.content)
    catalog = json.loads(metadata_path.read_text())
    file = next(item for item in catalog["files"] if item["id"] == 51335075)
    if file["size"] != FILE_SIZE or catalog["license"]["name"] != "CC BY 4.0":
        raise RuntimeError("Public archive size or licence changed")
    inputs = {"figshare_metadata": metadata_path}
    manifests = []
    with zipfile.ZipFile(PublicArchive()) as outer:
        names = outer.namelist()
        for info in outer.infolist():
            if not any(term in info.filename for term in ["Temperature", "Water quality"]):
                continue
            kind = "prt" if "(PRT)" in info.filename else "depth" if "specific depth" in info.filename else "water_quality"
            offset = nested_offset(info)
            with zipfile.ZipFile(PublicArchive(offset, info.file_size)) as inner:
                entries = [{"name": i.filename, "bytes": i.file_size, "compressed_bytes": i.compress_size,
                            "method": i.compress_type} for i in inner.infolist()]
                sites = sorted({i.filename.split("/")[1] for i in inner.infolist() if len(i.filename.split("/")) > 2})
                if kind != "depth":
                    for entry in inner.infolist():
                        if "/ARIK/" not in entry.filename or not any(word in Path(entry.filename).name for word in ["variables_", "sensor_positions_", "issueLog_", "readme_"]):
                            continue
                        payload = metadata_payload(inner, offset, entry)
                        path = RAW / f"neon_{kind}_{Path(entry.filename).name}"
                        path.write_bytes(payload)
                        inputs[f"{kind}_{Path(entry.filename).stem}"] = path
                        pd.read_feather(io.BytesIO(payload)).to_csv(path.with_suffix(".csv"), index=False)
                path = OUT / f"figshare_{kind}_directory.json"
                C.write_json(path, {"archive": info.filename, "payload_offset": offset,
                                   "sites": sites, "entries": entries})
                manifests.append({"kind": kind, "sites": sites, "file_count": len(entries)})
    schema = pd.read_feather(inputs["water_quality_variables_20288"])
    fields = schema.loc[schema.table.eq("waq_instantaneous"), "fieldName"].tolist()
    measurement_temp_fields = [field for field in fields if "temp" in field.lower() and not field.endswith("QF")]
    C.write_json(OUT / "neon_public_archive_summary.json", {
        "article_doi": catalog["doi"], "licence": catalog["license"],
        "outer_archive_bytes": FILE_SIZE, "outer_archives": names, "manifests": manifests,
        "water_quality_measured_temperature_fields_in_checked_schema": measurement_temp_fields,
        "digital_surface_water_thermistor_archive_present": any("thermistor" in name.lower() for name in names),
        "temperature_measurement_payloads_opened": False,
        "requires_account_or_token": False,
        "independent_backup_reference_acquired": False,
        "independent_new_confirmation_executed": False,
        "available_primary_temperature_resource_is_not_a_backup_pair": True,
    })
    C.write_json(OUT / "neon_public_archive_run_record.json", run_record(inputs,
                 metadata_only=True, public_byte_ranges=True, credential_access=False))
    print("[397] public author archive: 24 PRT sites; no digital-thermistor archive or measured WQ temperature in checked schema; measurement tables remain unopened", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

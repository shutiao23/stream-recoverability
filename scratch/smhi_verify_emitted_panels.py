#!/usr/bin/env python3
"""Independent verification of the EMITTED SMHI panels (O stratum).

Separate parser, raw_cache bytes only; re-derives networks, complete years and
panel grids and compares them with what the ingest wrote. Read-only.

Run: PYTHONPATH=src python3 scratch/smhi_verify_emitted_panels.py
"""

from __future__ import annotations

import collections
import csv
import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "wrr_submission_ready" / "multi_agency_ingest" / "smhi"
RAW = OUT / "raw_cache"
ING = json.loads((OUT / "ingest.json").read_text())
CAT = json.loads((RAW / "parameter_4_catalog.json").read_text())
report: dict[str, object] = {}

catchment = {str(s["id"]): s["catchmentNumber"] for s in CAT["station"]}
name = {str(s["id"]): s["name"] for s in CAT["station"]}


def need_days(year: int) -> int:
    return 366 if (year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)) else 365


def parse_dates(path: Path) -> pd.Series:
    text = path.read_bytes().decode("utf-8-sig")
    lines = text.splitlines()
    hidx = next(i for i, l in enumerate(lines) if l.startswith("Datum"))
    reader = io.StringIO(text)
    for _ in range(hidx + 1):
        next(reader)
    records = []
    for row in csv.reader(reader, delimiter=";"):
        if not row or not re.match(r"^\d{4}-\d{2}-\d{2}$", row[0].strip()):
            continue
        code = row[2].strip() if len(row) > 2 else ""
        if len(code) > 1:
            continue
        try:
            value = float((row[1] if len(row) > 1 else "").replace(",", "."))
        except ValueError:
            continue
        records.append((row[0].strip(), value))
    frame = pd.DataFrame(records, columns=["date", "value"]).drop_duplicates("date")
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")["value"].sort_index()


series = {sid: parse_dates(RAW / f"station_{sid}.csv") for sid in sorted(catchment)}
report["n_series_reparsed"] = len(series)


def complete_years(s: pd.Series) -> list[int]:
    years = []
    for year, block in s.groupby(s.index.year):
        if int(block.notna().sum()) >= need_days(int(year)):
            years.append(int(year))
    return years


years_by_station = {sid: complete_years(s) for sid, s in series.items()}
ge4 = {sid: y for sid, y in years_by_station.items() if len(y) >= 4}
report["recomputed"] = {
    "n_stations": len(series),
    "n_stations_ge_4_complete_years": len(ge4),
    "n_complete_station_years_all_stations": int(sum(len(y) for y in years_by_station.values())),
    "n_complete_station_years_stations_ge_4_years": int(sum(len(y) for y in ge4.values())),
}

# networks the independent recomputation would emit
by_net: dict[str, list[str]] = collections.defaultdict(list)
for sid in ge4:
    by_net[f"smhi_catchment_{catchment[sid]}"].append(sid)
expected_networks = {net: sorted(ids) for net, ids in by_net.items() if len(ids) >= 2}
report["recomputed"]["n_networks"] = len(expected_networks)
report["recomputed"]["n_complete_station_years_in_recomputed_networks"] = int(
    sum(len(years_by_station[s]) for ids in expected_networks.values() for s in ids)
)

# emitted artifacts
emitted_dirs = sorted(p.name for p in (OUT / "networks").glob("*")) if (OUT / "networks").is_dir() else []
report["emitted_network_dirs"] = emitted_dirs
problems: list[str] = []
if set(emitted_dirs) != set(expected_networks):
    problems.append(f"network set mismatch: emitted={sorted(set(emitted_dirs) ^ set(expected_networks))}")

# per-network panel checks: grid, columns, blank where missing, values equal raw
panel_stats = {}
for net in emitted_dirs:
    path = OUT / "networks" / net / "daily_wide_temperature.csv"
    panel = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    panel.columns = [str(c) for c in panel.columns]
    index = pd.date_range(panel.index.min(), panel.index.max(), freq="D")
    if len(index) != len(panel):
        problems.append(f"{net}: {len(panel)} rows for a {len(index)}-day grid")
    if not panel.index.equals(index):
        problems.append(f"{net}: date index is not a complete daily grid")
    members = [sid for sid in panel.columns]
    eligible = [sid for sid in members if len(years_by_station[sid]) >= 4]
    if sorted(eligible) != expected_networks.get(net, []):
        problems.append(f"{net}: eligible stations differ from recomputation")
    for sid in members:
        raw = series[sid].reindex(index)
        col = pd.to_numeric(panel[sid], errors="coerce")
        if not np.allclose(raw.to_numpy(dtype=float), col.to_numpy(dtype=float), equal_nan=True, atol=1e-9):
            problems.append(f"{net}/{sid}: panel values differ from raw cache")
    panel_stats[net] = {
        "n_rows": int(len(panel)),
        "n_columns": int(panel.shape[1]),
        "n_eligible_stations": len(eligible),
        "n_complete_station_years": int(sum(len(years_by_station[s]) for s in eligible)),
        "first_date": str(panel.index.min().date()),
        "last_date": str(panel.index.max().date()),
    }
report["panel_stats"] = panel_stats

# stations.csv contract
stations = pd.read_csv(OUT / "stations.csv", dtype={"station_id": str})
required = [
    "network_id", "station_id", "provider", "river_name", "latitude", "longitude",
    "n_complete_years", "complete_years", "first_date", "last_date", "n_days",
    "n_dropped_qc", "accepted_quality_codes", "measurement_statistic", "quality_assurance",
]
missing = [c for c in required if c not in stations.columns]
if missing:
    problems.append(f"stations.csv missing columns: {missing}")
if set(stations["accepted_quality_codes"].astype(str)) != {"O"}:
    problems.append("stations.csv accepted_quality_codes is not uniformly O")
if set(stations["quality_assurance"].astype(str)) != {"provider_published_unqualified"}:
    problems.append("stations.csv quality_assurance is not the declared stratum")
panel_columns = {
    sid for net in emitted_dirs
    for sid in pd.read_csv(OUT / "networks" / net / "daily_wide_temperature.csv", nrows=1).columns
    if sid != "date"
}
if set(stations["station_id"]) != panel_columns:
    problems.append("stations.csv station set differs from the union of panel columns")
report["stations_csv"] = {
    "n_rows": int(len(stations)),
    "n_eligible_ge_4_years": int((stations["n_complete_years"] >= 4).sum()),
    "n_complete_station_years_eligible": int(
        stations.loc[stations["n_complete_years"] >= 4, "n_complete_years"].sum()
    ),
    "sha256": hashlib.sha256((OUT / "stations.csv").read_bytes()).hexdigest(),
    "measurement_statistic_unique": sorted(stations["measurement_statistic"].unique()),
}

# cross-check the emitted numbers against ingest.json claims
claims = {
    "n_networks": ING["n_networks"],
    "n_stations_emitted": ING["n_stations_emitted"],
    "n_stations_emitted_ge_4_complete_years": ING["n_stations_emitted_ge_4_complete_years"],
    "n_complete_station_years_in_emitted_networks": ING["n_complete_station_years_in_emitted_networks"],
    "n_complete_station_years": ING["n_complete_station_years"],
    "n_complete_station_years_stations_ge_4_years": ING["n_complete_station_years_stations_ge_4_years"],
    "n_stations": ING["n_stations"],
    "qc_stratum": ING["qc_stratum"],
}
recomputed = {
    "n_networks": len(expected_networks),
    "n_stations_emitted": len(panel_columns),
    "n_stations_emitted_ge_4_complete_years": sum(
        len([s for s in ids if len(years_by_station[s]) >= 4]) for ids in expected_networks.values()
    ),
    "n_complete_station_years_in_emitted_networks": int(
        sum(len(years_by_station[s]) for ids in expected_networks.values() for s in ids)
    ),
    "n_complete_station_years": int(sum(len(y) for y in years_by_station.values())),
    "n_complete_station_years_stations_ge_4_years": int(sum(len(y) for y in ge4.values())),
    "n_stations": len(ge4),
    "qc_stratum": "provider_published_unqualified",
}
mismatches = {k: {"claim": claims[k], "recomputed": recomputed[k]} for k in claims if claims[k] != recomputed[k]}
report["claim_vs_recomputed"] = {"claims": claims, "recomputed": recomputed, "mismatches": mismatches}
problems.extend(f"claim mismatch {k}: {v}" for k, v in mismatches.items())

# strict-gate audit artifacts must still be present
for kept in [
    "QC_AND_ELIGIBILITY_FAILURE.md", "QC_legend_verbatim.json", "networks_not_eligible.csv",
    "INGEST_STATUS.json", "raw_cache_manifest.csv",
]:
    if not (OUT / kept).is_file():
        problems.append(f"audit artifact missing: {kept}")

report["problems"] = problems
report["ok"] = not problems
print(json.dumps(report, indent=2, ensure_ascii=False))
(ROOT / "scratch" / "smhi_verify_emitted_report.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False) + "\n"
)

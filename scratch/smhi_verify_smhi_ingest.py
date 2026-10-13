#!/usr/bin/env python3
"""Independent re-verification of the SMHI ingest from the raw cache bytes.

Deliberately does NOT import the ingest script or its parser: it re-reads
raw_cache/ with a separate minimal scanner and checks the ingest's claims.
Reads only; writes scratch/smhi_verify_*.{json,txt}.

Run: PYTHONPATH=src python3 scratch/smhi_verify_smhi_ingest.py
"""

from __future__ import annotations

import collections
import csv
import hashlib
import io
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "wrr_submission_ready" / "multi_agency_ingest" / "smhi"
RAW = OUT / "raw_cache"
INGEST = json.loads((OUT / "ingest.json").read_text())
STATIONS = pd.read_csv(OUT / "stations_all.csv", dtype={"station_id": str})

report: dict[str, object] = {}

# ---- 1. re-scan every raw file with an independent scanner ---------------- #
qc_counter: collections.Counter = collections.Counter()
comma_values = 0
non_integer_quality_rows = 0
per_station = {}
n_files = 0
for path in sorted(RAW.glob("station_*.csv")):
    n_files += 1
    sid = path.stem.split("_", 1)[1]
    text = path.read_bytes().decode("utf-8-sig")
    lines = text.splitlines()
    hidx = next(i for i, l in enumerate(lines) if l.startswith("Datum"))
    codes = collections.Counter()
    n_rows = 0
    first = last = None
    reader = io.StringIO(text)
    for _ in range(hidx + 1):
        next(reader)
    for row in csv.reader(reader, delimiter=";"):
        if not row or not re.match(r"^\d{4}-\d{2}-\d{2}$", row[0].strip()):
            continue
        code = row[2].strip() if len(row) > 2 else ""
        value_raw = row[1].strip() if len(row) > 1 else ""
        # a real observation row: single-character/blank code and numeric/blank value
        if len(code) > 1 or not re.match(r"^$|^-?\d+(?:[.,]\d+)?$", value_raw):
            continue
        n_rows += 1
        codes[code] += 1
        if len(row) > 1 and "," in row[1]:
            comma_values += 1
        first = first or row[0]
        last = row[0]
    qc_counter.update(codes)
    per_station[sid] = {"n_rows": n_rows, "codes": dict(codes), "first": first, "last": last}

report["independent_rescan"] = {
    "n_station_files": n_files,
    "quality_code_counts": dict(sorted(qc_counter.items())),
    "n_rows_total": sum(per_station[s]["n_rows"] for s in per_station),
    "n_rows_with_comma_decimal_value": comma_values,
    "n_stations_with_any_G": sum(1 for s in per_station.values() if s["codes"].get("G")),
    "n_stations_with_any_Y": sum(1 for s in per_station.values() if s["codes"].get("Y")),
    "earliest_date_seen": min(s["first"] for s in per_station.values()),
    "latest_date_seen": max(s["last"] for s in per_station.values()),
    "codes_seen_across_files": sorted(qc_counter),
}

# ---- 2. cross-check against ingest.json claims ---------------------------- #
mismatches = []
claims = {
    "n_downloaded": INGEST["n_downloaded"],
    "n_catalog_stations": INGEST["n_catalog_stations"],
}
if claims["n_downloaded"] != n_files:
    mismatches.append(f"n_downloaded={claims['n_downloaded']} vs raw files={n_files}")
ingest_dist = INGEST["qc"]["quality_code_distribution_rows_parsed"]
if {k or "blank": v for k, v in ingest_dist.items()} != dict(qc_counter):
    mismatches.append(f"quality distribution mismatch: {ingest_dist} vs {dict(qc_counter)}")
if INGEST["qc"]["n_value_rows_parsed"] != report["independent_rescan"]["n_rows_total"]:
    mismatches.append("n_value_rows_parsed mismatch")
# stratum-aware check: the accepted set is whatever ingest.json declares
accepted_codes = set(INGEST["qc"]["accepted_quality_codes"])
rescan_accepted_rows = sum(qc_counter.get(code, 0) for code in accepted_codes)
if rescan_accepted_rows != INGEST["counts"]["n_rows_accepted"]:
    mismatches.append(
        f"accepted rows mismatch: ingest={INGEST['counts']['n_rows_accepted']} rescan={rescan_accepted_rows}"
    )
rescan_accepted_stations = sum(
    1 for s_ in per_station.values() if sum(s_["codes"].get(c, 0) for c in accepted_codes) > 0
)
if rescan_accepted_stations != INGEST["n_stations_with_accepted_days"]:
    mismatches.append(
        "accepted-station mismatch: "
        f"ingest={INGEST['n_stations_with_accepted_days']} rescan={rescan_accepted_stations}"
    )
report["stratum_check"] = {
    "qc_stratum": INGEST["qc_stratum"],
    "accepted_quality_codes": sorted(accepted_codes),
    "rescan_rows_with_accepted_codes": rescan_accepted_rows,
    "rescan_stations_with_accepted_codes": rescan_accepted_stations,
    "ingest_n_rows_accepted": INGEST["counts"]["n_rows_accepted"],
    "ingest_n_stations_with_accepted_days": INGEST["n_stations_with_accepted_days"],
}
report["cross_check_mismatches"] = mismatches

# ---- 3. verify per-station sha256 recorded in stations_all.csv ------------ #
bad_hashes = []
for row in STATIONS.to_dict("records"):
    path = RAW / f"station_{row['station_id']}.csv"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != row["raw_sha256"]:
        bad_hashes.append(str(row["station_id"]))
report["n_stations_with_bad_sha256"] = len(bad_hashes)
report["bad_sha256_station_ids"] = bad_hashes[:10]

# ---- 4. coverage summary of the downloaded archive ------------------------ #
first_dates = pd.to_datetime(STATIONS["first_date_any_quality"])
last_dates = pd.to_datetime(STATIONS["last_date_any_quality"])
report["coverage"] = {
    "min_first_date": str(first_dates.min().date()),
    "max_last_date": str(last_dates.max().date()),
    "median_first_date": str(first_dates.median().date()),
    "median_last_date": str(last_dates.median().date()),
    "n_stations_ending_before_1990": int((last_dates < "1990-01-01").sum()),
    "n_stations_ending_2000_or_later": int((last_dates >= "2000-01-01").sum()),
    "date_column_header": INGEST["qc"]["header_block_verbatim_example"],
}

# ---- 5. COUNTERFACTUAL: what an O-accepting rule would have yielded ------- #
# Diagnostic only. This is NOT the ingest result and must not be sealed as one.
need_days = {y: (366 if (y % 400 == 0 or (y % 4 == 0 and y % 100 != 0)) else 365) for y in range(1940, 2010)}
cf_rows = []
cf_wide_ok = []
for row in STATIONS.to_dict("records"):
    sid = str(row["station_id"])
    path = RAW / f"station_{sid}.csv"
    text = path.read_bytes().decode("utf-8-sig")
    lines = text.splitlines()
    hidx = next(i for i, l in enumerate(lines) if l.startswith("Datum"))
    reader = io.StringIO(text)
    for _ in range(hidx + 1):
        next(reader)
    records = []
    for r in csv.reader(reader, delimiter=";"):
        if not r or not re.match(r"^\d{4}-\d{2}-\d{2}$", r[0].strip()):
            continue
        code = r[2].strip() if len(r) > 2 else ""
        if len(code) > 1:
            continue
        try:
            value = float(r[1].replace(",", "."))
        except (ValueError, IndexError):
            continue
        records.append((r[0].strip(), value))
    frame = pd.DataFrame(records, columns=["date", "value"]).drop_duplicates("date")
    frame["date"] = pd.to_datetime(frame["date"])
    series = frame.set_index("date")["value"].sort_index()
    years = []
    for year, block in series.groupby(series.index.year):
        if int(block.notna().sum()) >= need_days.get(int(year), 365):
            years.append(int(year))
    cf_rows.append(
        {
            "station_id": sid,
            "n_accepted_days_if_O_allowed": int(series.notna().sum()),
            "n_complete_years_if_O_allowed": len(years),
            "complete_years_if_O_allowed": ";".join(str(y) for y in years),
        }
    )
    if len(years) >= 4:
        cf_wide_ok.append(sid)

cf = pd.DataFrame(cf_rows)
cf.to_csv(ROOT / "scratch" / "smhi_verify_counterfactual_station_years.csv", index=False)
network_ok = []
for network_id, group in cf.groupby(STATIONS.set_index("station_id").loc[cf["station_id"], "network_id"].to_numpy()):
    qualifying = group.loc[group["n_complete_years_if_O_allowed"] >= 4]
    if len(qualifying) >= 2:
        network_ok.append({"network_id": network_id, "n_stations_ge4": len(qualifying)})
report["counterfactual_if_uncontrolled_O_were_accepted"] = {
    "label": "DIAGNOSTIC ONLY - not the ingest result, not an eligible panel",
    "n_stations_with_ge_4_complete_years": int(len(cf_wide_ok)),
    "n_networks_with_ge_2_such_stations": len(network_ok),
    "n_complete_station_years": int(cf["n_complete_years_if_O_allowed"].sum()),
    "networks": network_ok,
}
pd.DataFrame(network_ok).to_csv(ROOT / "scratch" / "smhi_verify_counterfactual_networks.csv", index=False)

# ---- 6. boreal / hydropower evidence (textual only) ---------------------- #
hydro = STATIONS.loc[STATIONS["hydropower_name_evidence"] == True]  # noqa: E712
report["hydropower_name_evidence"] = {
    "n_stations_with_name_token": int(len(hydro)),
    "tokens": sorted({t for value in hydro["hydropower_evidence"] for t in str(value).split(":")[-1].split("|")}),
    "examples": sorted(hydro["river_name"].astype(str).tolist())[:15],
}
report["latitude"] = {
    "min": float(STATIONS["latitude"].min()),
    "max": float(STATIONS["latitude"].max()),
    "n_north_of_60N": int((STATIONS["latitude"] >= 60).sum()),
    "boreal_nordic_declared_by_seal_context_map": "boreal_nordic",
}

# ---- 7. summary of the panel the coordinator can actually seal ----------- #
report["panel_available_for_seal"] = {
    "stations_csv_rows": int(len(pd.read_csv(OUT / "stations.csv"))),
    "networks_dir_exists": (OUT / "networks").is_dir(),
    "station_daily_files": len(list((OUT / "station_daily").glob("*.csv"))),
}

print(json.dumps(report, indent=2, ensure_ascii=False))
(ROOT / "scratch" / "smhi_verify_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

#!/usr/bin/env python3
"""Independent verification of the Hub'Eau ingest outputs (scratch, not a deliverable).

Recomputes, from the raw cached API payloads and the written CSVs, the numbers the
ingest reports: network/station/station-year counts, per-code observation counts,
the daily aggregation rule, complete calendar years, and the quality labels.
Writes nothing except stdout and scratch/hubeau_ingest/verify_report.json.
"""

from __future__ import annotations

import calendar
import glob
import gzip
import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
OUT = ROOT / "results/wrr_submission_ready/multi_agency_ingest/hubeau"
RAW = OUT / "raw_cache"
SCRATCH = ROOT / "scratch/hubeau_ingest"
SCRATCH.mkdir(parents=True, exist_ok=True)
report: dict[str, object] = {}
problems: list[str] = []


def check(name: str, ok: bool, detail: object) -> None:
    report[name] = {"ok": bool(ok), "detail": detail}
    if not ok:
        problems.append(f"{name}: {detail}")
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# ---------------------------------------------------------------- envelopes
def envelopes(subdir: str) -> list[dict]:
    out = []
    for path in sorted((RAW / subdir).glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            out.append(json.loads(handle.read()))
    return out


station_catalog = envelopes("catalog")[0]
catalog_rows = station_catalog["document"]["data"]
check("station_catalog_complete", len(catalog_rows) == int(station_catalog["document"]["count"]),
      f"{len(catalog_rows)} rows, count field {station_catalog['document']['count']}")

global_env = {env["label"]: env for env in envelopes("qualification_global")}
global_counts = {label: int(env["document"].get("count") or 0) for label, env in global_env.items()}
check("global_counts_sum_matches_total",
      global_counts.get("all_codes") == sum(global_counts.get(f"code_{c}", 0) for c in "1234"),
      {k: v for k, v in sorted(global_counts.items())})

# ---------------------------------------------------------------- spans
span_env: dict[str, dict[str, dict]] = defaultdict(dict)
for env in envelopes("spans"):
    station, kind = env["label"].rsplit("_", 1)
    span_env[station][kind] = env["document"]
n_spans_complete = sum(1 for v in span_env.values() if {"asc", "desc"} <= set(v))
check("span_screen_complete", n_spans_complete == len(catalog_rows),
      f"{n_spans_complete} stations with asc+desc of {len(catalog_rows)} catalogued")

# ---------------------------------------------------------------- qualification cache
qual_cache: dict[str, dict[str, int]] = defaultdict(dict)
for env in envelopes("qualification_station"):
    station, code = env["label"].rsplit("_code", 1)
    qual_cache[station][code] = int(env["document"].get("count") or 0)
check("qualification_audit_present", len(qual_cache) > 0, f"{len(qual_cache)} stations audited per code")

# ---------------------------------------------------------------- written outputs
stations_csv = pd.read_csv(OUT / "stations.csv", dtype={"station_id": str})
ingest = json.loads((OUT / "ingest.json").read_text())
networks_csv = pd.read_csv(OUT / "networks.csv", dtype=str)
network_dirs = sorted(p for p in (OUT / "networks").iterdir() if p.is_dir())
check("network_dirs_match_csv", len(network_dirs) == len(networks_csv),
      f"{len(network_dirs)} dirs vs {len(networks_csv)} rows in networks.csv")
check("stations_csv_rows_match_ingest", len(stations_csv) == int(ingest["counts"]["n_stations"]),
      f"{len(stations_csv)} vs {ingest['counts']['n_stations']}")

# ---------------------------------------------------------------- per-station recheck
complete_years_recomputed: dict[str, list[int]] = {}
daily_recomputed: dict[str, pd.Series] = {}
for row in stations_csv.itertuples(index=False):
    station_id = str(row.station_id)
    code = str(row.accepted_quality_codes)
    raw_rows = []
    for path in sorted((RAW / "chronique").glob(f"{station_id}_{code}_*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            env = json.loads(handle.read())
        for item in env["document"].get("data") or []:
            raw_rows.append((item.get("date_mesure_temp"), item.get("resultat"), item.get("code_qualification")))
    codes_seen = {str(item[2]) for item in raw_rows}
    if codes_seen != {code}:
        problems.append(f"{station_id}: raw cache mixes codes {codes_seen} vs accepted {code}")
    frame = pd.DataFrame(raw_rows, columns=["date", "temperature_c", "quality_code"])
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["temperature_c"] = pd.to_numeric(frame["temperature_c"], errors="coerce")
    frame = frame.dropna(subset=["date", "temperature_c"])
    frame = frame.loc[frame["temperature_c"].between(-2.0, 45.0)]
    per_day = frame.groupby("date")["temperature_c"].agg(["size", "mean"])
    formed = per_day.loc[per_day["size"] >= int(row.min_obs_per_day_rule), "mean"]
    daily_recomputed[station_id] = formed
    years = []
    for year, block in formed.groupby(formed.index.year):
        need = 366 if calendar.isleap(int(year)) else 365
        if len(block) >= need:
            years.append(int(year))
    complete_years_recomputed[station_id] = years

mismatch_years = {
    str(row.station_id): (str(row.complete_years), ";".join(map(str, complete_years_recomputed[str(row.station_id)])))
    for row in stations_csv.itertuples(index=False)
    if str(row.complete_years) != ";".join(map(str, complete_years_recomputed[str(row.station_id)]))
}
check("complete_years_recomputed_from_raw", not mismatch_years, mismatch_years or "all stations agree")
n_station_years = sum(len(v) for v in complete_years_recomputed.values())
check("station_years_match_ingest", n_station_years == int(ingest["counts"]["n_station_years"]),
      f"{n_station_years} vs {ingest['counts']['n_station_years']}")
check("all_stations_ge4_complete_years",
      all(len(v) >= 4 for v in complete_years_recomputed.values()),
      f"min complete years = {min(len(v) for v in complete_years_recomputed.values())}")

# daily n_days recheck
n_days_mismatch = {
    str(row.station_id): (int(row.n_days), int(len(daily_recomputed[str(row.station_id)])))
    for row in stations_csv.itertuples(index=False)
    if int(row.n_days) != int(len(daily_recomputed[str(row.station_id)]))
}
check("n_days_recomputed_from_raw", not n_days_mismatch, n_days_mismatch or "all n_days agree")

# ---------------------------------------------------------------- quality labels
labels_ok = []
for row in stations_csv.itertuples(index=False):
    station_id = str(row.station_id)
    counts = qual_cache.get(station_id, {})
    code = str(row.accepted_quality_codes)
    expected = "unqualified (Sandre code 4)" if code == "4" else "qualified (Sandre code 1 Correcte)"
    labels_ok.append(str(row.quality) == expected and str(row.measurement_statistic_quality) == expected)
    if code == "1" and counts.get("1", 0) < int(row.min_obs_per_day_rule):
        problems.append(f"{station_id}: accepted code 1 but audit count {counts.get('1')}")
check("quality_labels_match_audit", all(labels_ok), f"{len(labels_ok)} station labels checked")
code_usage = stations_csv["accepted_quality_codes"].astype(str).value_counts().to_dict()
check("no_station_mixes_codes", not any("," in str(v) or ";" in str(v) for v in stations_csv["accepted_quality_codes"]),
      code_usage)

# ---------------------------------------------------------------- wide panels
wide_problems = []
for directory in network_dirs:
    wide_path = directory / "daily_wide_temperature.csv"
    wide = pd.read_csv(wide_path, dtype={0: str})
    if wide.columns[0] != "date":
        wide_problems.append(f"{directory.name}: first column {wide.columns[0]}")
        continue
    wide["date"] = pd.to_datetime(wide["date"])
    expected = set(
        stations_csv.loc[stations_csv.network_id.astype(str).eq(directory.name), "station_id"].astype(str)
    )
    if set(map(str, wide.columns[1:])) != expected:
        wide_problems.append(f"{directory.name}: columns {sorted(wide.columns[1:])} != stations {sorted(expected)}")
    if wide["date"].duplicated().any():
        wide_problems.append(f"{directory.name}: duplicated dates")
    full = pd.date_range(wide["date"].min(), wide["date"].max(), freq="D")
    if len(full) != len(wide):
        wide_problems.append(f"{directory.name}: {len(wide)} rows for {len(full)} calendar days")
    for station_id in expected:
        series = wide.set_index("date")[station_id].dropna()
        if not series.index.equals(daily_recomputed[station_id].index):
            wide_problems.append(f"{directory.name}/{station_id}: daily index differs from raw recomputation")
        elif not (series - daily_recomputed[station_id]).abs().max() < 1e-9:
            wide_problems.append(f"{directory.name}/{station_id}: daily values differ from raw recomputation")
    per_network = pd.read_csv(directory / "stations.csv", dtype={"station_id": str})
    if len(per_network) < 2:
        wide_problems.append(f"{directory.name}: fewer than 2 stations")
check("wide_panels_verified_against_raw", not wide_problems, wide_problems[:5] or f"{len(network_dirs)} panels OK")

# ---------------------------------------------------------------- per-code panning
per_station_total = {
    code: sum(counts.get(code, 0) for counts in qual_cache.values()) for code in "1234"
}
check("audited_code_totals_match_ingest",
      per_station_total == {k.replace("count_code_", ""): v for k, v in
                            ingest["qualification_counts"]["per_station_code_totals_over_audited_rivers"].items()},
      per_station_total)

# ---------------------------------------------------------------- prior access
prior_files = [
    ROOT / "results/v17_fitness/step1_panel/station_roster.csv",
    ROOT / "results/wrr_revision/step1_universe/trusted_river_complete_years.csv",
    ROOT / "results/wrr_submission_ready/prior_access_ledger_reserved_station_years.csv",
    ROOT / "results/wrr_submission_ready/confirmation_inputs_manifest.csv",
]
prior_ids: set[str] = set()
for path in prior_files:
    if path.is_file():
        frame = pd.read_csv(path, dtype=str, low_memory=False)
        for column in frame.columns:
            if column in {"station_id", "site_id"}:
                prior_ids |= {str(v).strip() for v in frame[column].dropna()}
            if column in {"station_ids_ge4", "site_ids", "station_ids"}:
                for value in frame[column].dropna():
                    prior_ids |= {p.strip() for p in re.split(r"[;,]", str(value)) if p.strip()}
overlap = sorted(set(stations_csv["station_id"].astype(str)) & prior_ids)
check("no_prior_programme_station", not overlap, overlap or "no overlap with prior v17/v18 station rosters")

# ---------------------------------------------------------------- request log
manifest = pd.read_csv(RAW / "url_manifest.csv")
kinds = manifest["kind"].value_counts().to_dict()
report["request_manifest_kinds"] = kinds
stamps = manifest["retrieved_utc"].dropna()
report["retrieved_utc_cached_range"] = (
    [str(stamps.min()), str(stamps.max())] if len(stamps) else None
)
check("manifest_rows_all_envelopes", bool(manifest["url"].notna().all()),
      f"{int(manifest['url'].isna().sum())} non-envelope rows ignored")
check("url_manifest_nonempty", len(manifest) > 0, kinds)

report["problems"] = problems
(SCRATCH / "verify_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
print("\nPROBLEMS:", len(problems))
for problem in problems[:20]:
    print(" -", problem)
print("report ->", SCRATCH / "verify_report.json")

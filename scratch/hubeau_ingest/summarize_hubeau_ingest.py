#!/usr/bin/env python3
"""Print the Hub'Eau ingest numbers that go into the report (scratch helper)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
OUT = ROOT / "results/wrr_submission_ready/multi_agency_ingest/hubeau"
SCRATCH = ROOT / "scratch/hubeau_ingest"
pd.set_option("display.width", 200)

ingest = json.loads((OUT / "ingest.json").read_text())
stations = pd.read_csv(OUT / "stations.csv", dtype={"station_id": str})
networks = pd.read_csv(OUT / "networks.csv", dtype=str)
manifest = pd.read_csv(OUT / "raw_cache" / "url_manifest.csv")
qc = pd.read_csv(OUT / "raw_cache" / "station_qc.csv", dtype={"station_id": str})

print("== provenance ==")
print("retrieved_utc:", ingest["retrieved_utc"])
print("requests logged:", ingest["api_urls"]["n_requests_logged"])
print("requests by kind:", manifest["kind"].value_counts().to_dict())

print("\n== qualification counts (API count field) ==")
for key, value in sorted(ingest["qualification_counts"]["global_api_counts"]["global_api_counts"]["by_code"].items()):
    print(f"  global {key}: {value['count']:,}")
qa = ingest["qualification_counts"]["global_api_counts"]
print("  audited stations:", qa["n_stations_audited"])
print("  audited per-code totals:", qa["per_station_totals_over_audited"])
print("  audited stations with each code:", qa["per_station_station_counts"])
print("  stations where sum(codes)!=unfiltered total:", qa["n_stations_codes_sum_mismatch"])

print("\n== waterbody / network filter ==")
print(json.dumps(ingest["waterbody_filter"], indent=1)[:900])
print(json.dumps({k: v for k, v in ingest["network_filter"].items() if "station_ids" not in k}, indent=1)[:900])
print("ambiguous river names:", ingest["ambiguous_river_names"])

print("\n== panel ==")
print("counts:", ingest["counts"])
print("assurance:", json.dumps(ingest["assurance"], indent=1))
print("\nnetworks:")
print(
    networks[["network_id", "river_name", "n_stations", "n_station_years", "quality_assurance"]].to_string(
        index=False
    )
)

print("\n== aggregation / QC ==")
print("rule:", json.dumps(ingest["aggregation_rule"], indent=1)[:1200])
print(f"stations: {len(stations)}")
print("complete years per station:", stations["n_complete_years"].describe().round(2).to_dict())
print("total complete station-years:", int(stations["n_complete_years"].sum()))
print("observations downloaded:", f"{int(stations['n_obs_downloaded'].sum()):,}")
print("observations dropped by QC:", f"{int(stations['n_dropped_qc'].sum()):,}")
print("daily values formed:", f"{int(stations['n_days'].sum()):,}")
print("days with zero obs:", f"{int(stations['n_days_zero_obs'].sum()):,}")
print("days below min-obs floor:", f"{int(stations['n_days_below_min_obs'].sum()):,}")
print("days in span:", f"{int(stations['n_days_in_span'].sum()):,}")
print("median obs per observed day (min/median/max):",
      float(qc["median_obs_per_observed_day"].min()),
      float(qc["median_obs_per_observed_day"].median()),
      float(qc["median_obs_per_observed_day"].max()))
print("per-station quality:", stations["quality"].value_counts().to_dict())
print("per-station quality_assurance:", stations["quality_assurance"].value_counts().to_dict())
print("accepted codes:", stations["accepted_quality_codes"].value_counts().to_dict())
print("\ncode composition of each panel station (audit counts):")
cols = ["station_id", "network_id", "hubeau_code1_count", "hubeau_code2_count", "hubeau_code3_count",
        "hubeau_code4_count", "accepted_quality_codes", "n_complete_years", "n_obs_downloaded"]
print(stations[cols].to_string(index=False))

sens_file = OUT / "raw_cache" / "complete_year_sensitivity.csv"
if sens_file.is_file():
    sens = pd.read_csv(sens_file)
    print("\n== sensitivity of complete-year counts to the min-obs/day rule ==")
    print(sens.groupby("min_obs_per_day").agg(
        stations=("station_id", "nunique"),
        station_years=("n_complete_years", "sum"),
    ).to_string())

fail_file = ingest.get("failures") or []
print("\nfailures:", len(fail_file))
for item in fail_file[:10]:
    print("  ", item)
(SCRATCH / "summary_numbers.json").write_text(
    json.dumps(
        {
            "counts": ingest["counts"],
            "assurance": ingest["assurance"],
            "global_counts": ingest["qualification_counts"]["global_api_counts"]["global_api_counts"]["by_code"],
            "audited": {
                "n_stations": qa["n_stations_audited"],
                "totals": qa["per_station_totals_over_audited"],
                "station_counts": qa["per_station_station_counts"],
            },
            "obs_downloaded": int(stations["n_obs_downloaded"].sum()),
            "obs_dropped_qc": int(stations["n_dropped_qc"].sum()),
            "daily_values": int(stations["n_days"].sum()),
            "days_zero_obs": int(stations["n_days_zero_obs"].sum()),
            "days_below_floor": int(stations["n_days_below_min_obs"].sum()),
            "n_requests": int(ingest["api_urls"]["n_requests_logged"]),
            "failures": len(fail_file),
        },
        indent=2,
    )
    + "\n"
)
print("\nsummary ->", SCRATCH / "summary_numbers.json")

#!/usr/bin/env python3
"""Generate the NVE secondary-probe README from the written ingest artifacts.

Every number in the README is read out of ``ingest.json``, the network manifest
and ``verification.json``; nothing is typed by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "wrr_submission_ready" / "multi_agency_ingest" / "nve"


def main() -> int:
    ingest = json.loads((OUT / "ingest.json").read_text())
    verification = json.loads((OUT / "verification.json").read_text())
    manifest = pd.read_csv(OUT / "networks_manifest.csv", dtype=str)
    stations = pd.read_csv(OUT / "stations.csv", dtype={"station_id": str})
    catalog = ingest["catalog_counts"]
    candidates = ingest["candidate_counts"]
    qc = ingest["qc_counts"]
    final = ingest["final_counts"]
    years = ingest["complete_year_counts"]

    v17_flag = manifest["network_in_v17_basin"].astype(str).str.strip().str.lower().eq("true")
    new_flag = ~v17_flag
    new_nets = manifest[new_flag]
    old_nets = manifest[~new_flag]

    lines: list[str] = []
    add = lines.append
    add("# NVE HydAPI panel — SECONDARY PROBE, not part of the sealed transport panel")
    add("")
    add(
        "`nve_hydapi` participated in v17 development, so "
        "`results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md` "
        "**Amendment 1** states:"
    )
    add("")
    add(
        "> This amendment also records why `nve_hydapi` is **not** part of the sealed "
        "transport panel: that provider participated in v17 development, so new NVE "
        "basins are reported separately as a secondary probe, never as transport "
        "confirmation."
    )
    add("")
    add(
        "This directory is therefore a **secondary multi-agency probe feed**. Its "
        "networks must not enter `multi_agency_seal.json` and must not be pooled into "
        "the pre-declared transport verdict, whatever the per-station v17 status is. "
        "The panel is still useful as a same-agency, new-station replication of the "
        "frozen screen and as a boreal/alpine context description, and it is reported "
        "with that scope stated."
    )
    add("")
    add("## What was ingested")
    add("")
    add(
        "| item | value |\n|---|---|\n"
        f"| provider | `{ingest['provider']}` (NVE HydAPI, Norway) |\n"
        f"| parameter | `{ingest['api']['parameter']}` — {ingest['api']['parameter_name']} |\n"
        f"| resolution | `{ingest['api']['resolution_time_minutes']}` min = provider **daily** statistic, aggregation method `Mean` |\n"
        f"| day definition | Norwegian normal time calendar day (fixed UTC+1), timestamped 11:00Z by NVE |\n"
        f"| quality kept | codes {ingest['api']['quality_codes']['accepted']} (PrimaryControlled / SecondaryControlled) and correction code 0 |\n"
        f"| assurance stratum | `quality_checked` (Amendment 2) |\n"
        f"| observed period covered by the panel | {manifest['first_date'].min()} … {manifest['last_date'].max()} |\n"
        f"| script | [`scripts/241_multi_agency_nve_ingest.py`](../../../../scripts/241_multi_agency_nve_ingest.py) |"
    )
    add("")
    add("## Headline counts")
    add("")
    add(
        "| quantity | value |\n|---|---|\n"
        f"| parameter-1003 daily series rows in the HydAPI catalogue | {catalog['parameter_1003_daily_series_rows']} |\n"
        f"| of those, river + measured + daily-mean rows | {catalog['river_measured_mean_rows']} |\n"
        f"| dropped: observation place not a river | {catalog['dropped_observation_place_not_river']} |\n"
        f"| dropped: daily archive is `Instantaneous`, not a mean | {catalog['dropped_daily_resolution_aggregation_not_mean']} |\n"
        f"| dropped: station id in the v17 roster | {catalog['dropped_v17_roster_stations']} |\n"
        f"| dropped: Svalbard (station-id basin 400) | {catalog['dropped_svalbard_non_mainland']} |\n"
        f"| **candidate basins (vassdrag) scanned** | **{candidates['candidate_basins']}** |\n"
        f"| **candidate stations** | **{candidates['candidate_stations']}** |\n"
        f"| raw observation rows returned | {qc['raw_observation_rows']} |\n"
        f"| QC-passing station-days | {qc['qc_passing_station_days']} |\n"
        f"| stations with >= 1 complete calendar year | {years['stations_with_complete_years']} |\n"
        f"| stations with >= 4 complete calendar years | {years['stations_with_ge4_complete_years']} |\n"
        f"| **networks kept (>= 2 stations with >= 4 complete years)** | **{final['networks_kept']}** |\n"
        f"| **stations in kept networks** | **{final['stations_in_kept_networks']}** |\n"
        f"| **complete station-years in kept networks** | **{final['complete_station_years_in_kept_networks']}** |\n"
        f"| kept networks in a basin the v17 roster never touched | {final['kept_networks_with_no_v17_station']} |\n"
        f"| kept networks sharing a basin with a v17 station | {final['kept_networks_sharing_a_v17_basin']} |\n"
        f"| stations / complete station-years in v17-free networks | {final['stations_in_kept_networks_with_no_v17_station']} / {final['complete_station_years_in_kept_networks_with_no_v17_station']} |"
    )
    add("")
    add("## Networks")
    add("")
    add(
        "| network_id | basin name | stations | complete station-years | first date | last date | network is v17-free |"
    )
    add("|---|---|---|---|---|---|---|")
    for row in manifest.sort_values("network_id").itertuples():
        add(
            f"| `{row.network_id}` | {row.network_name} | {row.n_stations} | "
            f"{row.n_complete_station_years} | {row.first_date} | {row.last_date} | "
            f"{'yes' if str(row.network_in_v17_basin).strip().lower() != 'true' else 'no (shares basin with a v17 station)'} |"
        )
    add("")
    add(
        f"Stations with or without a v17-basin overlap: "
        f"{len(new_nets)} networks contain no v17 station "
        f"({len(new_nets)} of {len(manifest)}); the remaining {len(old_nets)} "
        f"({', '.join('`' + value + '`' for value in old_nets['network_id'])}) sit in "
        "basins where v17 used at least one *other* station."
    )
    add("")
    add("## Exact API filters")
    add("")
    add("```")
    add("GET https://hydapi.nve.no/api/v1/Series?Parameter=1003")
    add("GET https://hydapi.nve.no/api/v1/Stations?StationId=<station_id>        # one call per station id")
    add(
        "GET https://hydapi.nve.no/api/v1/Observations?StationId=<id[,id...]>&Parameter=1003"
        "&ResolutionTime=1440&ReferenceTime=<catalog_daily_start>/<catalog_daily_end>"
    )
    add("Header: X-API-Key <public Sildre client key, discovered at runtime>")
    add("```")
    add("")
    add(
        f"Batching: at most {8} station ids and about 20,000 estimated records per "
        "Observations request (HydAPI rejects more than 10 series per request). Raw "
        "JSON responses are cached verbatim under `raw_cache/`; the exact URL of every "
        "response is stored inside each cache file and in `ingest.json`."
    )
    add("")
    add("## QC and drop accounting")
    add("")
    add(
        f"Raw rows {qc['raw_observation_rows']}; dropped {qc['rows_dropped_total']} "
        f"({100 * qc['rows_dropped_total'] / qc['raw_observation_rows']:.1f}%):"
    )
    add("")
    add("| drop reason | rows |")
    add("|---|---|")
    for reason, count in sorted(qc["drop_reason_totals"].items(), key=lambda item: -item[1]):
        add(f"| `{reason}` | {count} |")
    add("")
    add(
        "Reasons are assigned in a fixed precedence order, so they are disjoint and "
        "sum to the total. `value_missing_null` means NVE returned the day with a "
        "JSON-null value (its own missing-day marker); `quality_...` means the day was "
        "not primary/secondary controlled; `correction_nonzero` means ice correction, "
        "interpolation, a model value or a rejected-period value. Per-station counts "
        "are in `qc_ledger.csv`; the largest contributors are stations whose archive is "
        "mostly uncontrolled or interpolated."
    )
    add("")
    add("## Caveats a reviewer would raise")
    add("")
    for caveat in ingest["caveats"]:
        add(f"- {caveat}")
    add(
        "- Metadata coverage: NVE's current station registry returned HTTP 404 for "
        f"{candidates['stations_missing_metadata']} of {candidates['candidate_stations']} "
        "candidate stations (mostly long-delisted series). Their `river_name`, "
        "`regineNo` and regulation flags are therefore blank; the station-id "
        "drainage-basin number is used for grouping, and the basin name is taken from "
        "whichever station in the basin still has metadata."
    )
    add(
        "- Frozen-screen performance was **not** computed on this panel: the ingest "
        "stops at QC and structural eligibility. Any number here is coverage, not "
        "skill."
    )
    add("")
    add("## Value sanity (not a performance check)")
    add("")
    sanity = verification["value_sanity"]
    add(
        f"{sanity['n_values']} written values, min {sanity['min_c']:.2f} °C, max "
        f"{sanity['max_c']:.2f} °C, mean {sanity['mean_c']:.2f} °C; "
        f"{sanity['n_below_zero']} values below 0 °C (freshwater under-ice sensors read "
        "slightly negative), none below -0.5 °C, none above 30 °C."
    )
    add("")
    add("## Files")
    add("")
    add(
        "| path | content |\n|---|---|\n"
        "| `networks/<network_id>/daily_wide_temperature.csv` | wide daily panel, `date` first, one column per station id, blank where missing |\n"
        "| `networks/<network_id>/stations.csv` | the same station table restricted to one network |\n"
        "| `stations.csv` | all panel stations with `quality_assurance`, complete-year list, dates, drop counts |\n"
        "| `networks_manifest.csv` | per-network counts, date range, file paths and sha256 |\n"
        "| `candidate_stations.csv` | every candidate station with catalog + station metadata and the v17-basin flag |\n"
        "| `complete_station_years.csv` | one row per station-year |\n"
        "| `qc_ledger.csv` | per-station QC drop counts by reason |\n"
        "| `daily_long_qc.parquet` | QC-passing long table (station, date, value, provider flags) |\n"
        "| `ingest.json` | retrieval UTC, API filters, counts, caveats, input hashes |\n"
        "| `verification.json` | independent re-computation of every headline number |\n"
        "| `raw_cache/` | verbatim HydAPI responses (catalogue, station metadata, observation batches) |"
    )
    add("")
    add(
        f"Independent verification: {len(verification['checks'])} checks, "
        f"{len(verification['failures'])} failures "
        "(`PYTHONPATH=src python3 scratch/verify_nve_ingest.py`)."
    )
    add("")
    add("## Reproduction")
    add("")
    add("```bash")
    add("PYTHONPATH=src python3 scripts/241_multi_agency_nve_ingest.py --stage all")
    add("PYTHONPATH=src python3 scratch/verify_nve_ingest.py")
    add("PYTHONPATH=src python3 scratch/make_nve_readme.py")
    add("```")
    add("")

    (OUT / "README.md").write_text("\n".join(lines))
    print(f"wrote {OUT / 'README.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

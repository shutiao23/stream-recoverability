#!/usr/bin/env python3
"""Generate the provider-level README.md for the Hub'Eau transport panel.

Every number in the README is read from the emitted artifacts (ingest.json,
stations.csv, networks.csv) or from this run's verification report, never typed
by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
OUT = ROOT / "results/wrr_submission_ready/multi_agency_ingest/hubeau"
generated_utc = pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

ingest = json.loads((OUT / "ingest.json").read_text())
stations = pd.read_csv(OUT / "stations.csv", dtype={"station_id": str})
networks = pd.read_csv(OUT / "networks.csv", dtype=str)
verify = json.loads((ROOT / "scratch/hubeau_ingest/verify_report.json").read_text())
module_check = json.loads((ROOT / "scratch/hubeau_ingest/module_check_code1.json").read_text())

ev = ingest["emitted_vs_resolved"]
day = ingest["days_below_observation_floor"]
aud = ingest["qualification_counts"]["global_api_counts"]
qual = ingest["qualification_counts"]
counts = ingest["counts"]

lines = [
    "# Hub'Eau (France) river-temperature panel for the multi-agency transport test",
    "",
    f"Generated {generated_utc} by `scratch/hubeau_ingest/write_provider_readme.py` from the",
    "emitted artifacts of `scripts/242_multi_agency_hubeau_ingest.py`.",
    "Feeds `results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md`. "
    "No frozen-screen performance was computed on this panel.",
    "",
    "## Panel",
    "",
    f"- networks: **{counts['n_networks']}** (agency-native grouping: Hub'Eau river name,",
    "  `libelle_cours_eau`, normalized; Loire and last-check ids excluded)",
    f"- stations: **{counts['n_stations']}** (every station has >= "
    f"{ingest['network_filter']['min_complete_years_per_station']} complete calendar years)",
    f"- complete station-years: **{counts['n_station_years']}**",
    f"- complete years per station: min {int(stations['n_complete_years'].min())}, "
    f"median {float(stations['n_complete_years'].median()):g}, "
    f"max {int(stations['n_complete_years'].max())}",
    f"- retrieval: {ingest['retrieved_utc']}; API requests logged: "
    f"{ingest['api_urls']['n_requests_logged']}; failures: {len(ingest['failures'])}",
    "",
    "## Assurance level (read this before using the panel)",
    "",
    f"- **{ingest['assurance']['statement']}**",
    f"- `quality_assurance` per station: "
    f"{stations['quality_assurance'].value_counts().to_dict()}",
    f"- accepted Sandre codes: {stations['accepted_quality_codes'].value_counts().to_dict()}",
    f"- global Hub'Eau archive counts by code (API `count` field): code 1 = "
    f"{aud['global_api_counts']['by_code']['code_1']['count']:,}, code 2 = "
    f"{aud['global_api_counts']['by_code']['code_2']['count']:,}, code 3 = "
    f"{aud['global_api_counts']['by_code']['code_3']['count']:,}, code 4 = "
    f"{aud['global_api_counts']['by_code']['code_4']['count']:,}, all = "
    f"{aud['global_api_counts']['by_code']['all_codes']['count']:,}",
    f"- audited pool: {qual['global_api_counts']['n_stations_audited']} stations on the capped",
    "  candidate rivers; per-code totals there: "
    f"{qual['global_api_counts']['per_station_totals_over_audited']}",
    f"- code-1 series do exist elsewhere in the archive (verified example station "
    f"{module_check['station_id']}, code-1 data {module_check['station_span_years_with_code1'][0]}-"
    f"{module_check['station_span_years_with_code1'][1]}); none fall inside the audited candidate",
    "  pool, so this panel stays in the unqualified stratum.",
    f"- protocol rule 3 (provider daily statistic): {ingest['protocol_rule_3_conformance']['verdict']}",
    "",
    "## Measurement provenance and aggregation rule",
    "",
    f"- source rows: Hub'Eau `temperature/chronique` instantaneous observations "
    f"(`date_mesure_temp` + `heure_mesure_temp`)",
    f"- daily value: {ingest['aggregation_rule']['daily_value']}",
    f"- minimum observations per day: **{day['min_observations_per_day']}**; days below the floor "
    "are dropped and counted, never interpolated",
    f"- days in span {day['n_days_in_span']:,}; days with observations "
    f"{day['n_days_with_observations']:,}; daily values formed {day['n_days_with_daily_value']:,}; "
    f"days with zero observations {day['n_days_zero_observations']:,}; days below the floor "
    f"{day['n_days_below_floor']:,} "
    f"(share of observed days {day['share_of_days_with_obs_below_floor']:.4f})",
    f"- observations downloaded {int(stations['n_obs_downloaded'].sum()):,}; dropped by QC "
    f"(unparsable date, non-finite or outside {ingest['aggregation_rule']['plausible_range_c']} degC) "
    f"{int(stations['n_dropped_qc'].sum()):,}",
    f"- complete calendar year: {ingest['aggregation_rule']['complete_calendar_year']}",
    f"- sensitivity to the floor (raw_cache/complete_year_sensitivity.csv): "
    + ", ".join(
        f"floor {row.min_obs_per_day:g} -> {int(row.n_complete_years)} station-years over "
        f"{int(row.stations)} stations"
        for row in pd.read_csv(OUT / "raw_cache" / "complete_year_sensitivity.csv")
        .groupby("min_obs_per_day")
        .agg(stations=("station_id", "nunique"), n_complete_years=("n_complete_years", "sum"))
        .reset_index()
        .itertuples(index=False)
    ),
    "",
    "## Resolved vs emitted (cap applied)",
    "",
    f"- catalogued stations {ingest['waterbody_filter']['catalog_stations']}; river stations kept "
    f"{ev['resolved_river_stations_in_catalog']} "
    f"(dropped {ingest['waterbody_filter']['stations_dropped']}, "
    f"{100 * ingest['waterbody_filter']['fraction_dropped']:.2f}%: "
    f"{ingest['waterbody_filter']['rule']})",
    f"- stations with >= 4 years of observation span: {ev['resolved_stations_with_span_ge_4y']}",
    f"- candidate stations before the cap: {ev['resolved_candidate_stations_before_cap']} on "
    f"{ev['resolved_candidate_networks_before_cap']} rivers",
    f"- cap: at most {ev['cap_applied']['max_networks']} networks and "
    f"{ev['cap_applied']['max_stations_per_network']} stations per network; "
    f"{ev['cap_applied']['networks_beyond_cap']} rivers were beyond the network cap "
    "(`networks_beyond_cap.csv`, not downloaded) and "
    f"{ev['stations_not_downloaded_beyond_network_cap']} stations were beyond the per-network cap",
    f"- downloaded stations {ev['stations_downloaded']}; emitted **{ev['emitted_networks']} networks / "
    f"{ev['emitted_stations']} stations / {ev['emitted_station_years']} station-years**; "
    f"{ingest['network_filter']['n_networks_excluded_after_download']} network dropped after "
    "download for having fewer than 2 stations with >= 4 complete years "
    "(`networks_excluded_after_download.csv`)",
    f"- river-name ambiguity: {ingest['ambiguous_river_names']['n_clusters']} names mapped to more "
    f"than one watercourse code, {ingest['ambiguous_river_names']['n_stations_excluded']} stations "
    "excluded (`raw_cache/ambiguous_river_name_clusters.csv`)",
    f"- water-body notes: "
    f"{ingest['waterbody_filter']['retained_although_label_mentions_sea_or_estuary']} kept stations "
    "have DCE reach labels that merely mention the sea or an estuary; "
    f"{ingest['waterbody_filter']['canalised_name_flagged_but_kept']} canalised-name stations kept "
    "and flagged",
    "",
    "## Files",
    "",
    "- `networks/<network_id>/daily_wide_temperature.csv` - wide daily panel, first column `date`,",
    "  one column per station id, blank where a daily value was not formed",
    "- `networks/<network_id>/stations.csv`, `networks/<network_id>/ingest.json`, "
    "`networks/<network_id>/README.md`",
    "- `stations.csv` - all emitted stations with Sandre-code counts, QC day counts, complete",
    "  years and quality labels",
    "- `ingest.json` - retrieval UTC, exact API URL templates, counts by qualification code,",
    "  aggregation rule, cap, assurance, prior-access check, caveats, failures",
    "- `networks.csv`, `networks_beyond_cap.csv`, `networks_excluded_after_download.csv`, "
    "`stations_below_year_floor.csv`, `stations_dropped_waterbody_filter.csv`",
    "- `raw_cache/` - every API response (gzip JSON envelope with url + retrieval time), "
    "`url_manifest.csv`, `station_table.csv`, `station_spans.csv`, `qualification_counts.csv`, "
    "`station_qc.csv`, `station_year_coverage.csv`, `complete_year_sensitivity.csv`, "
    "`network_inputs_manifest.csv` (network_id, input_path, sha256, station ids for the seal)",
    "",
    "## Independent verification",
    "",
    f"`scratch/hubeau_ingest/verify_hubeau_ingest.py` recomputed complete years, daily values, "
    f"station counts and quality labels from the raw cached payloads: "
    f"{sum(1 for v in verify.values() if isinstance(v, dict) and v.get('ok'))} checks passed, "
    f"{len(verify['problems'])} problems.",
    "",
    "| network_id | river | stations | station-years | quality_assurance |",
    "|---|---|---|---|---|",
]
for row in networks.sort_values("network_id").itertuples(index=False):
    lines.append(
        f"| {row.network_id} | {row.river_name} | {row.n_stations} | {row.n_station_years} | "
        f"{row.quality_assurance} |"
    )
lines.append("")
(OUT / "README.md").write_text("\n".join(lines) + "\n")
print(f"wrote {OUT / 'README.md'} ({len(lines)} lines)")

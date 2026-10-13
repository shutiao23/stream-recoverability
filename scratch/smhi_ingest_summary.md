# SMHI multi-agency ingest — final state (all numbers from artifacts written this session)

Script: `scripts/240_multi_agency_smhi_ingest.py` (new)
Commands:
  PYTHONPATH=src python3 scripts/240_multi_agency_smhi_ingest.py --qc-stratum quality_checked            # strict run, exit 3 (recorded, kept)
  PYTHONPATH=src python3 scripts/240_multi_agency_smhi_ingest.py --qc-stratum provider_published_unqualified  # emit run, exit 0
  PYTHONPATH=src python3 scratch/smhi_verify_smhi_ingest.py                # independent raw-byte re-parse + stratum check
  PYTHONPATH=src python3 scratch/smhi_verify_emitted_panels.py             # independent panel/grid/value re-derivation
  PYTHONPATH=src python3 scratch/smhi_prior_use_scan.py                    # repo-wide station_id prior-use scan
  PYTHONPATH=src python3 scratch/smhi_seal_dryrun_preview.py               # read-only preview of scripts/249 build_manifest
Output root: `results/wrr_submission_ready/multi_agency_ingest/smhi/`

## Amendment 2 strata

- `quality_checked` (G, Y): 0 of 1,063,746 rows pass -> 0 stations, 0 networks.
  Record kept in `QC_AND_ELIGIBILITY_FAILURE.md` (byte-identical to the strict run) and in
  `ingest.json::stratum_provenance.strict_gate_audit`.
- `provider_published_unqualified` (O, the emitted stratum): full panel emitted.

## Emitted panel

| item | value |
|---|---|
| stations downloaded | 176 of 176, 0 failures, 1,063,746 rows, all code O |
| stations with >= 4 complete calendar years | 118 (provider-wide) |
| networks (>= 2 such stations per catchmentNumber) | 16 |
| stations appearing in emitted panels | 143 |
| eligible (>= 4 y) stations inside emitted panels | 101 |
| complete station-years, all 176 stations | 1601 |
| complete station-years, the 118 eligible stations | 1549 |
| complete station-years inside emitted networks | 1372 |
| complete station-years stranded in <2-station catchments (17 stations) | 177 |
| stations.csv sha256 | 7ee0e9ad8ecf62e2b1dc6c2bea643ae0a5839bd112efb82613f4368bac8595f9 |

Per-network: `networks_summary.csv` (2-16 eligible stations each, 13-236 complete station-years).
Panels: `networks/<network_id>/daily_wide_temperature.csv`, first column `date`, one column per
station id, one row per calendar day min->max, blank where missing (verified against raw bytes).

## Verification evidence

- `scratch/smhi_verify_report.json` — separate parser over the 176 raw files: 1,063,746 rows,
  codes {O: 1063746}, 0 G/Y rows, 0 cross-check mismatches, 0 bad sha256, 0 decimal commas;
  stratum check matches ingest.json (rows and stations).
- `scratch/smhi_verify_emitted_report.json` — re-derived networks, eligible sets, grids and cell
  values: `ok: true`, 0 problems, 0 claim-vs-recomputed mismatches; 16 networks; stations.csv
  143 rows / 101 eligible / sha256 above.
- `scratch/smhi_prior_use_scan.json` — 413 CSVs with a station_id column scanned repo-wide:
  0 overlaps with the 176 SMHI ids.
- `scratch/smhi_seal_dryrun_preview.json` — read-only `scripts/249.build_manifest()` view:
  18 network rows, 2 providers, 2 contexts, 1405 station-years (smhi 16/101/1372,
  uk_ea 2/4/33). SMHI adds `boreal_nordic`; the >=3-context design floor still depends on
  another provider.

## Audited record

`ingest.json` (qc_stratum, counts, stratum_provenance, legend verbatim), `INGEST_STATUS.json`
(strict-gate block preserved + amended-stratum block), `QC_legend_verbatim.json`,
`networks_not_eligible.csv` (42 rows), `raw_cache_manifest.csv`, `stations_all.csv`,
`station_years.csv`, `README.md`, `run.log`.

## Caveats

1. Daily aggregation operator undocumented: SMHI says "Daglig uppgift om
   vattendragstemperaturer i vattendrag i Sverige." (Enhet: Grader Celsius). Recorded as a daily
   provider statistic in degC, not a confirmed daily mean.
2. Date header "Datum (svensk sommartid)" (UTC+2) conflicts with the portal text saying UTC.
3. Values are provider-labelled uncontrolled; stratum must be carried into scoring and reporting.
4. All stations are `Övriga stationer` (outside SMHI's own network); archive is historical
   (1946-2003, no active parameter-4 station), so no overlap with the frozen model's recent period.
5. Latitudes 55.45-68.36 N (109/176 north of 60 N) -> boreal/Nordic. Name evidence only:
   117 stations named "KRV" (kraftverk), 48 "FORS"/"FORSEN" (hydropower_evidence.csv).

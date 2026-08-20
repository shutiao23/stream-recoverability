# Data and software rights

This document is a conservative rights record for reviewers and editors. It is not a performance claim, not an IRB statement, and not a FAIR/open-data declaration.

The MIT `LICENSE` covers original software only. It does not cover third-party observations, and it does not convert files under `data/raw/`, `data/processed/`, or `data_versions/` into open study data. `pyproject.toml` license metadata is a follow-on for the agent that owns that file; absence of a matching project-license field here is not a silent MIT grant over the data.

The public GitHub tree (`https://github.com/shutiao23/stream-recoverability`) is a development host. GitHub is not an AGU archival software repository. Presence of restricted columns in that tree is a remaining public-hosting defect, not evidence that the study data are open. This wave does not delete `data/raw`.

Machine-readable rows are in [`metadata/data_rights.csv`](metadata/data_rights.csv).

## What the supplied files actually contain

Internal CSVs (`data/raw/b1.csv`, `s2.csv`, `p3.csv`) have the header:

`DATE,WTEMP,WLEVEL,FLOW,TEMP,WDSP,PRCP,RHMEAN,DH`

They contain no embedded station names, units, time zone, hydrological-day cutoff, or per-value quality flags. Provenance is reconstructed in [`metadata/data_dictionary.csv`](metadata/data_dictionary.csv), [`metadata/station_metadata.csv`](metadata/station_metadata.csv), and [`metadata/source_documentation/README.md`](metadata/source_documentation/README.md). IRB, LOD, and LOQ do not apply to this observational case study and are not claimed.

Column groups are mixed in every raw file:

| Columns | Literature / dictionary attribution | Conservative rights |
| --- | --- | --- |
| `WTEMP`, `WLEVEL`, `FLOW` (`T`, `F`, `L`) | *Annual Hydrological Report of the People's Republic of China, Volume VI* | `redistribution_allowed=false` |
| `RHMEAN`, `DH` (`RH`, `DH`) | CMA surface climate daily value dataset V3.0 | `redistribution_allowed=false` (member-service; no transfer) |
| `TEMP`, `WDSP`, `PRCP` (`Ta`, `W`, `P`) | WMO/CMA station series that independently match converted NOAA GSOD records | contested / restricted; **not** public-domain NOAA-open |

A file that mixes these columns takes the most restrictive reading: the whole CSV is not redistributable.

## Yearbook hydrology (`T` / `F` / `L`)

Published papers attribute daily stream temperature and discharge at these stations to the *Annual Hydrological Report of the People's Republic of China, Volume VI: Hydrological Data of the Changjiang River Basin* (Wei et al. 2026; Wang et al. 2024). No in-repo license, copyright page, or transfer grant was found for the supplied daily extracts.

**Decision:** `redistribution_allowed=false` for hydrological observation columns and for any table that preserves those daily values. The manuscript already states that permission to redistribute the analysed daily hydrological files was not established. Those files must not be described as openly available.

`derived_output_allowed=restricted`: journal figures and aggregate metrics that do not republish the daily yearbook series are the usual publication path; reconstructed or byte-preserving daily `T`/`F`/`L` tables are not a licensed derived release.

## CMA `RH` / `DH`

`RHMEAN` and `DH` are the V3.0 names for mean relative humidity and sunshine duration. CMA/NMIC access for `SURF_CLI_CHN_MUL_DAY_V3.0` is typically a registered member service. Member-service terms are treated here as **no transfer**: this repository cannot claim a right to give those columns, or a derived daily table of them, to other users.

**Decision:** `redistribution_allowed=false`. Do not call CMA columns open.

## `TEMP` / `WDSP` / `PRCP` are not NOAA-open

The data dictionary does **not** say the supplied air-temperature, wind, and precipitation columns are a NOAA redistribution. It says they are a WMO/CMA station series whose values independently match converted NOAA GSOD records (GSOD `TEMP` °F→°C; `WDSP` knots; `PRCP` inches). Matching a public US product is a provenance check, not a license.

NCEI documentation implementing WMO Resolution 40 states that non-U.S. GSOD data, and products derived from them, must not be provided to other users. The matched stations (Batang 56247099999, Lijiang 56651099999, Huili 56671099999) are not U.S. stations.

**Decision:** mark these columns `contested_wmo_res40`, `redistribution_allowed=false`, `derived_output_allowed=false`. Do not mark them public-domain, USGov-unrestricted, or NOAA-open. Cite GSOD as a reconciliation source only.

## Figshare is not a license for the supplied CSVs

Figshare `10.6084/m9.figshare.29002466.v4` (Wei et al.) is CC BY 4.0. That license applies to that mixed observed/simulated package. This project used it only for monthly provenance reconciliation (Batang mostly agrees; Shigu has a 2013–2019 year-order discrepancy). CC BY 4.0 on Figshare is **not** a license to republish the yearbook, the supplied daily CSVs, or CMA/WMO columns in this repository.

## Processed tables and data versions inherit the same restrictions

`data/processed/daily_long.parquet`, `daily_wide.parquet`, split parquets, `event_labels.parquet`, and `scaler.json` are derived from the mixed raw files. They inherit the column restrictions above.

`data_versions/published_v1` is the published-reference version: published values with no additional quality exclusions or adjustments (byte-preserving relative to the prepared published table). It does not create a new license.

The three frozen sensitivities inherit the same input rights:

- `no_s2_suspect_v1` — excludes S2 `T`/`F`/`L` analysis values for 2013–2019; does not open the remaining values
- `b1_no_level_v1` — excludes B1 `L`; does not open other columns
- `b1_shift_sensitivity_v1` — hypothetical −8.48 m adjustment to B1 `L` from 2019; a sensitivity, not a factual correction and not a rights upgrade

Version manifests are project-authored JSON. Observation tables and scalers that store hydrological or meteorological moments remain restricted.

## Mask libraries (`masks/test`, `masks/validation`)

Tracked artifacts are `masks/{test,validation}/{masks.npz,manifest.json,manifest.csv}`.

`masks.npz` stores compact 3-D boolean bitmasks (date × station × variable). Arrays are `bool` only and do **not** embed hydrological or meteorological observation values.

The paired manifests list the full restricted-series date axis and, for block scenarios, `start_dates` / `end_dates` of hidden gaps. Those dates, plus bitmasks aligned to that calendar, can reconstruct which days of the restricted series were hidden. Eligibility for masking used `quality_approved` from the prepared restricted table.

**Decision:** `redistribution_allowed=restricted` for the six tracked mask files. They are compact bitmasks without hydrology values, but they are not an open date-index release.

## Software

Original code under `src/`, `scripts/`, `tests/`, and project-authored configs/docs is MIT, separate from data. `CITATION.cff` is the software citation. No archival DOI has been minted (`doi` is unset; not a Zenodo record). GitHub is the development URL, not the AGU archive.

## Confirmatory USGS / NASA (not opened)

The frozen external protocol uses five USGS sites on **one** Upper-to-Middle Chattahoochee mainstem network panel (not Lower Chattahoochee) and NASA POWER meteorology. USGS and NASA POWER products are generally publishable after acquisition and citation. Current evidence status is `confirmatory_data: not_opened`. Planned public confirmatory data do **not** sanitize or replace restricted Jinsha inputs.

Internal NASA POWER `Rs` (`ALLSKY_SFC_SW_DWN`, UTC) was added to `published_v1` without editing yearbook or CMA/GSOD columns. That shortwave series is generally citable. It does not license `T`/`F`/`L`/`RH`/`DH`/`TEMP`/`WDSP`/`PRCP`.

## Reviewer access route

Do not treat “available upon request” as the access story. No private-repository URL or software DOI is invented here.

1. **Software.** Reviewers can read the MIT-licensed code on the public GitHub development host. That is not an AGU archival deposit. A minted archival DOI does not exist yet (`CITATION.cff` leaves `doi` unset).
2. **Restricted Jinsha working tree** (raw CSVs, processed/versioned tables, mask libraries, and metadata that embed dates or values). Concrete process: upload the restricted working tree through **AGU GEMS → Data Files for Peer Review** (confidential review files). Editors then mediate reviewer access under GEMS confidentiality. That upload is not a sublicense, not a CMA transfer, not a grant to provide non-U.S. GSOD-matched columns or derived products to other users, and not a public data release. Yearbook permission was not established; a yearbook or rights-holder confirmation would still be required before any public or post-review release of `T`/`F`/`L`.
3. **Figshare v4.** Reviewers may inspect the CC BY 4.0 package for provenance only. It is not a substitute for the analysed daily files.
4. **NOAA GSOD and CMA portals.** Reviewers may obtain those products under each provider’s own terms. Independent download does not license the supplied mixed CSVs.
5. **USGS / NASA confirmatory.** Not opened. After roster authorization, acquisition would use the documented public APIs. That path is independent of Jinsha rights and does not sanitize Jinsha inputs.

## Public-hosting defect

Restricted hydrological and meteorological columns are presently in the public GitHub tree (`data/raw/*.csv`, processed parquets, `data_versions/*` tables, and date-bearing mask manifests). That hosting fact is a remaining defect. It must not be cited as open or FAIR study data.

This wave records the defect with `scripts/26_audit_restricted_hosting.py`. It does not rewrite git history. History rewrite requires an institutional immutable mirror first, then a coordinated public-history cleanup. Until that happens, the public tip remains defective.

## What still blocks an AGU Availability Statement

An honest AGU Data and Code Availability statement cannot yet say that the study data are openly available, or that GitHub is the archival software record. Blockers:

1. Yearbook `T`/`F`/`L`: permission to redistribute was not established (`redistribution_allowed=false`).
2. CMA `RH`/`DH`: member-service, no transfer (`redistribution_allowed=false`).
3. `TEMP`/`WDSP`/`PRCP`: WMO/CMA series independently matching GSOD; NCEI WMO Resolution 40 language forbids providing non-U.S. GSOD data or derived products to other users. Contested/restricted, not NOAA-open.
4. Figshare CC BY 4.0 does not license the supplied daily CSVs.
5. Processed and versioned tables inherit those restrictions; `published_v1` remains restricted even after the additive NASA `Rs` rebuild.
6. Public GitHub currently hosts those restricted columns (defect; not a FAIR dataset).
7. GitHub is not an AGU archival software repository; no software DOI has been minted (`CITATION.cff` `doi` unset).
8. Confirmatory USGS/NASA data are `not_opened` and, when opened, do not sanitize Jinsha inputs.
9. `pyproject.toml` license metadata is a follow-on and is not set in this wave.
10. Public-hosting remediation (remove restricted columns from the public git tip and history) remains a separate wave.

Until those are resolved, the Availability Statement should remain the restricted wording already in `paper/manuscript.md` §5, plus a software-archive DOI after one exists.

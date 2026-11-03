# Data and software rights

This document is a conservative rights record for reviewers and editors. It is not a performance claim, not an IRB statement, and not a FAIR/open-data declaration.

The MIT `LICENSE` covers original software only. It does not cover third-party observations, and it does not convert files under `data/raw/`, `data/processed/`, or `data_versions/` into open study data. `pyproject.toml` license metadata is a follow-on for the agent that owns that file; absence of a matching project-license field here is not a silent MIT grant over the data.

The GitHub development host (`https://github.com/shutiao23/stream-recoverability`) is not an AGU archival software repository. The local tracked-path audit on 2026-10-27 found none of its listed restricted paths; this check does not establish that every possible restricted value or remote history has been inspected. Restricted local working inputs are not an open-data grant.

Machine-readable rows are in [`metadata/data_rights.csv`](metadata/data_rights.csv).

The 2026-10-27 source-specific review identified a more relevant LUBW route than
the general website copyright notice alone. The official [chemical monitoring
metadata](https://rips-metadaten.lubw.de/trefferanzeige?docuuid=fff497a2-4fbf-41c1-b871-22f23f3a3a77)
and the actual online-station acquisition landing both link to the [UIS usage
agreement](https://www.lubw.baden-wuerttemberg.de/umweltinformationssystem/nutzungsvereinbarung).
An indexed provider-page excerpt describes attributed reuse and additional
commercial-use restrictions for four named GIS products; the full live terms
page returned 403 here. The applicability to the archived temperature exports,
their acquisition vintage and trained/case derivatives remains to be confirmed.
The LUBW `redistribution_allowed=false` field is therefore a current operational
sharing hold, not a finding that every UIS reuse requires separate permission.
The register and unsent clarification draft now reflect this distinction. No
sharing right is granted by this local review; see
`results/wrr_review_response_20261027/source_rights/lubw_terms_review_20261027.json`.

## Whole-archive source model dependencies

The post-hoc summer-air point comparison in `summer_proxy_archive/` reuses
the existing restricted whole-archive cases, input panels and fixed model
predictions. The candidate package includes its aggregate results, plans and
code, but not the private case-level files or all inputs needed to rerun it.
The local independent audit is therefore not an external reproducibility claim.

The 42 target stations in the whole-archive analysis have recorded provider
reuse paths, but the original seed-zero estimator fitting roles contain
positive-weight LUBW cases in all 13 mode-region combinations; six of the 13
interval-calibration roles also contain such cases. These are repeated masked
case rows. The finding establishes a data-dependency path, not a legal ruling
on any specific model or prediction. Provider permission for model weights,
calibration and case-level derivatives remains unresolved. Source-role counts
and the post-hoc filtered-source sensitivity plan and aggregate results are
included in the review candidate. The completed sensitivity uses candidate-provider
source cases and strictly excludes target-region groups. Its models and case outputs remain local pending
a complete rights and provenance review; it is not the manuscript's original
model. See `results/wrr_review_response_20261027/audit/` and
`open_source_sensitivity/plan.json`.

The candidate source-provider filter identifies the target case's provider;
it does not by itself identify every donor's upstream source. A post-hoc audit
reconstructed masked-day donor visibility for 194,370 candidate source rows;
39 of 52 source-role cells included positive-weight rows with a finite donor
estimate and a visible donor absent from the original three local catalogs.
The 73 USGS-labeled unmatched panel-column occurrences correspond to 69
distinct identifiers, all present in current USGS site metadata; one GKD
column also matches a project-generated network-QC table. These additional
identity matches do not prove the cached temperature lineage or grant rights
to redistribute observations, case outputs, models, or calibration tables.
For the 69 USGS identifiers, a later post-hoc comparison retrieved current
USGS daily mean responses. All 292,285 panel-column days with a unique finite
current value agreed with the local value to 1e-6 C; 1,525 days had multiple
different reported values and the local value matched at least one, while 41
local finite days had no finite value in the response. Selecting a matching
alternative after seeing multiple values does not identify the historic source
series. These counts include repeated site-days in different panels. The local
candidate includes the current USGS public site metadata and daily API
responses, along with aggregate audit results; local panel-to-station mappings
and cached model-input water values remain local. The public responses alone
cannot reproduce the local comparison or establish historic vintage or
derivative permissions. `make review-donor-usgs-snapshot` checks both public
snapshots offline.

## Main observation-record subset

The local review candidate contains project-processed daily temperature for 95
of the 96 previously eligible stations, from USGS, GKD Bayern, CHMI and FOEN,
with provider-specific source attribution and licensing. The one LUBW station
is excluded pending permission; it is not a complete public reconstruction of
the 96-station eligible population. The included 95 stations contain all 35
reported original observation witnesses. `make review-open-observed-reproduction`
independently recomputes their reference years, windows and screening decisions
from these processed values. Provider-native observations, prior quality filtering,
sensor accuracy, omitted station eligibility and main-model fitting are not
verified. The local candidate is not a permanent public archive. See the snapshot
`ATTRIBUTION.txt` and source roster for required credits, links and modifications.
The seasonal-window and screening-rule comparison uses this same 95-station
snapshot and supplied project connected-group and regulation labels. A reviewer
can run `make review-summer-snapshot` to reproduce the numerical comparisons;
this does not independently verify those labels, source quality, climate
representativeness or authorization for a permanent public deposit.
The retrospective past-only warm-season sensitivity also uses the same
current-vintage snapshot. `make review-past-season-snapshot` reproduces its
screening decisions and future-value perturbation checks; the output is not an
as-of-vintage data release or prospective validation.

The optional `make review-isolated-groupmax` check mounts additional local
source-model weights, whole-archive cases, the required pre-2010 bridge-repair
table and processed input panels read-only
outside the candidate ZIP. It checks the later group-maximum summaries in an
isolated environment; it does not authorize redistributing those materials or
establish that their provider and derivative permissions have been resolved.
The twenty historical source-seed repairs and the offline and forward
open-source archive repairs are also local inputs. Their post-hoc dependency
reports disclose aggregate effects, not permission to redistribute
the underlying tables or related per-case evidence.

## Truckee DWR exploratory reference

The local candidate includes the 12 publicly released Truckee source files,
their EDI metadata, station/instrument tables, reconstructed finite daily means,
and NASA POWER daily and hourly UTC/LST responses. The source is Frantzich and Davis
(2026), California Department of Water Resources / Environmental Data
Initiative, https://doi.org/10.6073/pasta/aefcf302d088aeacc40459091d7e990c.
EDI EML states CC0 1.0, while the California discovery catalog labels the
dataset Creative Commons Attribution without specifying a version. Attribution
is included; reconcile this discrepancy before permanent publication.
NASA POWER requests attribution, service version and access date, and requests
notification when data are transmitted to other researchers. No notification
or external release has been made. The bundled reference replay does not
include the source-model weights, calibration, target masks or case predictions;
the rights and reviewer-access conditions of those dependencies remain open.
The hourly POWER snapshot reproduces the current numeric UTC/LST relationship;
it does not prove the provider water sensor's actual clock convention.
The local candidate also stages a 16-field subset of 60 Water Quality Portal
field results for the same DWR station. California's catalog labels a separate
DWR-collected discrete water-quality dataset public domain, but the exact
record-level crosswalk to this WQP feed has not been independently verified.
The WQP source and transformations are attributed; confirm source terms before
permanent deposit. The field data do not establish an independent instrument.

## Additional USGS observation-only snapshot

The local review candidate contains the ten USGS daily-value API payloads used
for the additional observation-only record comparison, their acquisition queries,
station metadata and computed witness tables. USGS says
USGS-produced data are public domain and requests acknowledgment; its policy also
warns that third-party material can have separate restrictions ([USGS copyrights
and credits](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits)).
The snapshot identifies the USGS agency and source per site and includes an
attribution; it does not license data from other providers. A reviewer can run
`make review-usgs-observed-reproduction` from the candidate package. This is an
observation-only replay, not a permanent archive, full manuscript reconstruction,
or independent accuracy validation.

## British Columbia published reference derivative

The exploratory BC analysis uses the authors’ public Zenodo version 1, [Moore and Callahan (2024)](https://doi.org/10.5281/zenodo.14502248), under CC BY 4.0. The original daily CSV and station roster are included in the local candidate package with attribution and licence notice; quality and 20-hour limitations are recorded in the accompanying plan. This permission does not apply to other providers’ observations. The historical source-model training inputs and trained weights are still absent from the package.

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

## Confirmatory USGS / NASA (evaluate-once complete)

The frozen external protocol uses five USGS sites on **one** Upper-to-Middle Chattahoochee mainstem network panel (not Lower Chattahoochee) and NASA POWER meteorology. USGS and NASA POWER products are generally publishable after acquisition and citation. Acquisition, feasibility, and the 540-unit evaluate-once run are complete. These public-source external data and permitted derived aggregates may be archived with their request/provenance records. They do **not** sanitize or replace restricted Jinsha inputs.

## National USGS/GAGES-II regulation panel

The separately frozen national panel uses USGS daily water temperature and metadata, the USGS GAGES-II data release, and an official legacy USGS daily-values fallback after modern API rate limiting. These are public US-government sources and the compact aggregate panel outputs may be archived with citations. Re-downloadable raw caches are excluded from Git because they contain millions of public rows and a 55 MB source archive; `artifact_manifest.json` records their identities. The national pipeline statically and dynamically excludes all Chattahoochee confirmatory paths.

Internal NASA POWER `Rs` (`ALLSKY_SFC_SW_DWN`, UTC) was added to `published_v1` without editing yearbook or CMA/GSOD columns. That shortwave series is generally citable. It does not license `T`/`F`/`L`/`RH`/`DH`/`TEMP`/`WDSP`/`PRCP`.

## Reviewer access route

Do not treat “available upon request” as the access story. No private-repository URL or software DOI is invented here.

1. **Software.** Reviewers can read the MIT-licensed code on the public GitHub development host. That is not an AGU archival deposit. A minted archival DOI does not exist yet (`CITATION.cff` leaves `doi` unset).
2. **Restricted Jinsha working tree** (raw CSVs, processed/versioned tables, mask libraries, and metadata that embed dates or values). Concrete process: upload the restricted working tree through **AGU GEMS → Data Files for Peer Review** (confidential review files). Editors then mediate reviewer access under GEMS confidentiality. That upload is not a sublicense, not a CMA transfer, not a grant to provide non-U.S. GSOD-matched columns or derived products to other users, and not a public data release. Yearbook permission was not established; a yearbook or rights-holder confirmation would still be required before any public or post-review release of `T`/`F`/`L`.
3. **Figshare v4.** Reviewers may inspect the CC BY 4.0 package for provenance only. It is not a substitute for the analysed daily files.
4. **NOAA GSOD and CMA portals.** Reviewers may obtain those products under each provider’s own terms. Independent download does not license the supplied mixed CSVs.
5. **USGS / NASA confirmatory.** Acquired from documented public APIs after roster authorization; evaluate-once evidence is complete. This path is independent of Jinsha rights and does not sanitize Jinsha inputs.

## Public-history remediation

The historical public Git tree was rewritten to remove raw/processed Jinsha observations, internal data versions, date-bearing masks/catalogs, and other restricted daily artifacts from every public commit. Before the rewrite, a complete private Git bundle was created and verified; the public release includes an old-to-new commit map but not the restricted bundle. `scripts/26_audit_restricted_hosting.py --fail-if-present` now passes with zero restricted tracked paths. This remediation is not a grant to redistribute the private working inputs.

## What still blocks an AGU Availability Statement

An honest AGU Data and Code Availability statement cannot yet say that the study data are openly available, or that GitHub is the archival software record. Blockers:

1. Yearbook `T`/`F`/`L`: permission to redistribute was not established (`redistribution_allowed=false`).
2. CMA `RH`/`DH`: member-service, no transfer (`redistribution_allowed=false`).
3. `TEMP`/`WDSP`/`PRCP`: WMO/CMA series independently matching GSOD; NCEI WMO Resolution 40 language forbids providing non-U.S. GSOD data or derived products to other users. Contested/restricted, not NOAA-open.
4. Figshare CC BY 4.0 does not license the supplied daily CSVs.
5. Processed and versioned tables inherit those restrictions; `published_v1` remains restricted even after the additive NASA `Rs` rebuild.
6. Public history remediation is complete; future releases must keep the restricted-path audit at zero.
7. GitHub is not an AGU archival software repository; no software DOI has been minted (`CITATION.cff` `doi` unset).
8. Confirmatory USGS/NASA data and aggregates require an explicit public archive entry; their public status does not sanitize Jinsha inputs.
9. `pyproject.toml` license metadata is a follow-on and is not set in this wave.
10. The public release must retain the private-history backup ledger and commit map so pre-rewrite evidence remains auditable.

Until the DOI and confidential-review upload are resolved, the Availability Statement should retain the restricted wording in `paper/manuscript.md` §6 and add the real software archive identifier only after it exists.

## Newfoundland and Labrador redundant logger supplement

The 2026-10-21 follow-up inspects Fisheries and Oceans Canada's public
[Water Temperature and Level Monitoring in Newfoundland and Labrador Rivers](https://open.canada.ca/data/en/dataset/bef00bd7-255e-461c-a08b-09f81977170c),
published 2024-01-01 with catalogue metadata updated 2026-03-24. The provider
identifies the [Open Government Licence Canada](https://open.canada.ca/en/open-government-licence-canada).
Contains information licensed under the Open Government Licence Canada.

The provider describes year-round water loggers and some duplicate deployments.
The project stages the original archive locally and derives
UTC-day means, paired-sensor compatibility checks and actual missing-record
cases. These are project aggregates and are not promoted into provider-certified
daily means or exact sensor-error guarantees. The derived analysis is not an
official DFO product or endorsement. Raw logger exports, daily sensor caches
and normalized neural arrays remain excluded from the public software tree;
reproduction uses the provider download recorded in the acquisition ledger.
The archive's public status supplies no permission for unrelated restricted
Jinsha, CMA or other historical inputs described above.

The separate short-history sensitivity uses retrospective daily T2M forcing
downloaded from the [NASA POWER daily point API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/).
Input locations are recorded in
`natural_backup/short_history/input_records.csv`; responses remain local.
The freely retrieved forcing is incorporated directly and is not treated as a
paid information-acquisition action.

## Additional public USGS and NEON source qualification

The no-login follow-up stages native USGS temperature observations and their
approval/qualifier metadata through the public legacy and OGC Water Data APIs.
The OGC-to-tabular serialization and candidate
exclusions are recorded under
`results/wrr_submission_ready/followup_20261021/public_backup_search/`.
Provisional status is retained; those records do not enter the prespecified
approved-observation reference qualification. The study's UTC-day means are
project aggregates rather than a USGS certification of daily-mean truth.
Raw responses remain in the ignored local source cache.

The separate [NEON metabolism author archive](https://doi.org/10.6084/m9.figshare.28074452.v1)
identifies CC BY 4.0. The 2026-10-27 review response retrieved the public
half-hourly PRT temperature tables for 24 sites through bounded archive byte
ranges and produced a quality-filtered daily qualification table. The source
author and DOI must be attributed; the derived tables are not a NEON-certified
daily product. No independent digital-thermistor backup was obtained, and no
site met the four-complete-year reference criterion. The licence applies to
this specific author archive; it does not alter rights of other inputs.

The 2026-10-27 response additionally acquired qualification-code-1 continuous
temperature observations at five metadata-selected Réunion sites from the
Hub'Eau/Naïades API. The project-derived 24-hour-bin daily means and screening
results are identified separately from provider-published daily values. The
existing Hub'Eau rights entry records the Licence Ouverte Etalab 2.0 and the
need to credit OFB and station data producers; dataset-specific permissions,
time-zone convention and appropriate attribution still require confirmation
before an archival release. None of these sites met the four-complete-hot-year
reference criterion, and no external prediction accuracy was calculated.

## Australian public reference intake and NEON watershed metadata

The additional local intake uses the public BoM Water Data Online service and
Geofabric V3.3 station-catchment metadata. The source bank and roles were fixed
before Australian daily-temperature acquisition; 148 station archives and 869
native station-year intervals were acquired. The resulting 80 candidate
reference station-years belonged to an earlier F2 intake whose recorded risk
test gate was closed. This audit did not evaluate that F2 model. A later audit shows that 79 of those station-years
had evaluable cases in a separate earlier-method Australian evaluation, including
all 10 originally designated F2 test-role years. They are not unopened
independent target records for a new evaluation.
Raw observations, transformed daily caches and fitted model banks remain
ignored local artifacts; none has been publicly deposited by this workflow.

Public access is not a blanket redistribution licence. Water Data Online
[copyright](https://www.bom.gov.au/waterdata/wiski-web-public/copyright.htm)
and [FAQ](https://www.bom.gov.au/waterdata/wiski-web-public/faq.htm) assign terms
to the supplying organisation. Of the owners in this qualified pool, the
Water Data Online copyright page explicitly lists WA Department of Water and
Environmental Regulation under Creative Commons, with attribution
© Government of Western Australia. The QLD, NSW, VIC and SA owner names in the
current metadata require their applicable product-specific terms to be
recorded before a public data release; no permission for them is inferred from
a licence on a different BoM product or from another organisation's licence.
The workflow has not contacted providers or asserted a completed rights clearance.

The official [Geofabric layer](https://hosting.wsapi.cloud.bom.gov.au/arcgis/rest/services/ahgf/Geofabric_V3x_All_Products/FeatureServer/49)
requests attribution © Commonwealth of Australia (Bureau of Meteorology) 2022.
The earlier NEON metadata audit used official site profiles, watershed geometry
and public USGS station locations. At that earlier stage it had not opened NEON temperature measurement
tables or altered the previously documented author-archive licence scope.

The conservative dependence extension also uses the retained Geofabric V3.3
AHGFNetworkConnectivityDown topology (layer 38), with the same attribution
© Commonwealth of Australia (Bureau of Meteorology) 2022. It derives station
connectivity and scope tables from metadata; it opens no additional temperature
measurement payload and grants no additional redistribution rights.

The later USGS preflight and NLDI connectivity work requests only public
time-series/location/network metadata. Other-agency time series in the federal
catalog are retained in the inventory but excluded from the declared USGS
reference scope. Old cache evidence exports identities, not
request headers or new temperature observations. The workflow has not publicly
released the existing raw archives. NLDI quota responses and their Retry-After
requirements are preserved; the resume controller uses the same public endpoint
after the observed wait, without alternate credentials or access routes.

The subsequent NorWeST and EcoDrought scope audit retains official project,
catalog, processing and schema metadata locally, together with public download
header observations. It acquires no temperature measurement archive, uses no
modeled scenario as observational truth, and asserts no additional
redistribution permission. Original HTML/PDF/XML responses stay in the ignored
`data/external/wrr_additional_sources_20261021/` directory; compact response
status and source URLs remain in the evidence bundle. Public metadata
or an HTTP access failure does not establish measurement custody or eligibility.

The catchment metadata extension additionally queries Geofabric V3.3
AHGFCatchment (SH_Network), layer 7, at recorded provider coordinates. It uses
the same attribution © Commonwealth of Australia (Bureau of Meteorology) 2022.
Catchment identifiers and their explicit network-node links are conservative
metadata proxies; they do not verify physical gauge attachment or establish a
new independent temperature reference. Source responses remain local ignored
artifacts, with their request parameters retained for audit.

The 2019–2024 Nechako Watershed temperature archive is supplied by Kokoszka
et al. (2025), https://doi.org/10.5281/zenodo.15053907, under CC BY 4.0 as
stated on the Zenodo record. The candidate package includes its unmodified
`01_Data.zip` and a source attribution file. This permission concerns that
archive only and does not resolve the separate terms for other source data.
The project has evaluated completeness and recommended quality flags for one
selected site, not certified the archive as error-free or climate-independent.

The Poudre Water Quality Network source files are distributed by Struthers,
Willi, De La Torre and Ross through HydroShare,
https://doi.org/10.4211/hs.521e317e189e498581d0aaa08c3f32bc, with the resource
metadata stating CC BY 4.0. The candidate package includes the five unmodified
2020–2024 raw Parquet files and source attribution. They contain multiple sites
and parameters; the project examined temperature completeness and PASS flags
only at four preselected sites. This licence does not settle the terms of
other providers or make the observations independent or error-free.

The 2009–2017 four-station Nova Scotia Open Data Portal subset is provided
under the Open Government Licence – Nova Scotia, as identified by the portal.
Source: Government of Nova Scotia, Surface Water Quality Monitoring Network
Continuous Water Quality Data, https://data.novascotia.ca/datasets/bkfi-mjgw.
Contains information licensed under the Open Government Licence – Nova Scotia:
https://support.novascotia.ca/services/open-data-portal-licence.
The project subset and analyses are not official or endorsed. These rights do
not automatically establish terms for the separately obtained legacy verified
workbooks, which remain in an ignored local-only directory.

The separate Nova Scotia exploratory inputs comprise the selected reported-hour
means derived from the previously attributed Nova Scotia Open Data Portal and
two NASA POWER T2M API responses. NASA POWER requests attribution; the original
response archives, request URLs and source acknowledgement are included in the
candidate package. Their inclusion does not establish the legacy workbook's
licence, physical water-day convention or measurement quality. Source model
weights, per-case model inputs and predictions remain in local restricted paths.

The Nova Scotia clock-sensitivity daily inputs are derived from the same
attributed Open Data Portal subset using hypothetical one-hour reporting-day
shifts. Their inclusion under the Open Government Licence – Nova Scotia does
not identify the provider's true timezone or authorize redistribution of the
separate local-only legacy workbooks or source-model case predictions.

The interannual summer-peak proxy includes a small extract of the project's
previously processed NASA POWER-based daily air table for 22 open-subset
stations. NASA requests attribution and notification upon redistribution
([NASA POWER referencing guide](https://power.larc.nasa.gov/docs/referencing/)).
The candidate is a local review artifact; no notification has been sent. For
these original stations the historical raw API responses and service version
were not retained. Current responses were subsequently checked for 15
representative saved series; their numerical agreement does not establish the
historical version or water-day alignment. Source water permissions and model
rights remain separate.

The later field-date diagnostic uses a separate Government of Nova Scotia
dataset, [Surface Water Quality Monitoring Network Grab Sample Water Quality
Data, version 6.0.0](https://doi.org/10.25976/sfmj-kf56). Its DataStream
metadata identifies an Open Government Licence and links the [Canadian Open
Government Licence](https://open.canada.ca/en/open-government-licence-canada);
the dataset disclaimer and source attribution still apply. The candidate
contains aggregate diagnostic counts and code, not the field-source CSV or
row-level comparisons. The original may be acquired through the provider's
public download endpoint; the separate legacy workbooks and trained model
outputs remain subject to their own unresolved access conditions.

Three RivTemp partner files (MFFP QC, INRS and Vision H2O) were downloaded from
DataStream solely for a metadata and date-label availability screen. Their
catalog pages describe ODC-BY attribution, while their dataset disclaimers
also say that the database cannot be transferred to another organization in
whole or part. The scope of redistribution, derivatives and reviewer access
is therefore unresolved. Original CSV files and station-level screening tables
remain in `private/wrr_rivtemp_reference_20261026/`, are ignored by Git, and
are excluded from the candidate ZIP. Only aggregate screening counts, the
source citations and the stated limitations are included. No temperature
values or model predictions were examined in this screen. The local file
retrieval followed DataStream's published site terms and dataset disclaimers;
it does not settle redistribution rights or qualify the data as an independent
reference.

The local candidate contains two-column extracts (timestamp and temperature)
of ten level-1 files from Van Horn et al.'s 2026 USACE reservoir-water-quality
collection on HydroShare, licensed CC BY 4.0. Resource-specific attribution,
links and the column-selection change are recorded in the
snapshot manifest. Source creators request courtesy notification of derivative
products; none has been sent. The local candidate is not an external release.
This permission does not resolve the rights of other source data or model files.
The reservoir partial-history comparison additionally stages four NASA POWER
daily responses and a derived air table. NASA requests attribution and
notification upon redistribution; no notification has been sent for this local
candidate. The comparison's source-model weights and detailed predictions are
not included and remain subject to their separate unresolved conditions.
The matched source-history sensitivity stages a 15-station subset of the
project's previously processed NASA POWER-based daily air inputs for 2009-2017.
Source-service versions, exact historical responses and water-day alignment
remain unresolved; NASA attribution is supplied and its requested notification
has not been sent. Region-held models and case-level predictions remain local.

New Jersey DEP continuous-monitoring data were acquired for four post-hoc
selected station IDs and 2016–2019 solely for reported-timestamp qualification.
The portal states that downloadable observations are quality reviewed, but its
source-specific redistribution and downstream reuse conditions have not been
resolved for this study. Original station-year CSV files, site-level metadata and
screening outputs stay in `private/wrr_njdep_reference_20261026/` and are
excluded from the candidate package. Only aggregate time-label counts and public
provenance are included. No water-temperature values were used for recovery
scoring; incomplete date labels do not determine sensor accuracy or source QA.

The temporary USGS partial-history snapshot includes public USGS continuous
responses and processed daily derivatives plus four attributed NASA POWER
responses. The project-specific quality processing and clock assumptions are
recorded; NASA requests notification on redistribution, which has not been sent.
The source model, calibration and individual model predictions remain excluded
and subject to their separate unresolved access conditions.

## Scope of the MIT LICENSE (moved from LICENSE)

The MIT `LICENSE` covers original software only: source code, scripts, tests,
project configuration and project-authored documentation. It grants no license
in third-party observational data, including files under `data/raw/`,
`data/processed/` and `data_versions/`, or upstream products of FOEN, GKD
Bayern, USGS, NASA POWER, LUBW or other providers; each provider's terms
continue to govern access, use and redistribution. Presence of data files in a
public working tree is a hosting fact, not a redistribution licence. Restricted
paths listed in `metadata/data_rights.csv` were spot-checked on 2026-11-03 and
were found neither tracked in the public git tip nor present in commit history;
that spot check does not replace a full provenance audit. Third-party Python
dependencies retain their own licences.

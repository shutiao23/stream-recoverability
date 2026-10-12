# eHYD (Austria) — INFEASIBLE for the daily transport panel

Verdict: **infeasible**. Retrieved 2026-10-12T09:55:12.123454+00:00 by
`scripts/243_multi_agency_ehyd_ingest.py`
(`PYTHONPATH=src python3 scripts/243_multi_agency_ehyd_ingest.py`).

Transport protocol rule 3 requires *a provider daily statistic in °C*
(`MULTI_AGENCY_TRANSPORT_PROTOCOL.md`). eHYD's only surface-water
(river) temperature product is **`owf_wassertemp_monatsmittel` — a monthly
mean**. No daily surface-water water-temperature product exists in the
eHYD station catalogue, in the bulk data package, or in the service that the
eHYD web application itself uses to build its download offer. No network is
emitted; nothing was scored.

## 1. The station catalogue has no daily surface-water temperature file type

`GET https://ehyd.gv.at/services/Messstellen/json?filter=alle` (HTTP 200, 6,722,863 bytes,
sha256 `9253bb55c0612c5ee4269a34f24515b484cfa27357aae0511df53583b768e022`) returns a GeoJSON FeatureCollection of
**5,662 stations** whose `fjson`
property lists every published file per station:
**26,819 file entries,**
**22 distinct file types**.
Census written to `results/wrr_submission_ready/multi_agency_ingest/ehyd/raw_cache/ftyp_census.csv`.

Temperature file types present anywhere in the catalogue:

- every catalogue file type whose identifier contains `wassertemp`: `owf_wassertemp_monatsmittel`, `qu_quellwassertemp`
- of those, surface-water (`owf_*`): `owf_wassertemp_monatsmittel`

Daily (`*tages*`) temperature file types **for surface water**: none
(`daily_surface_temperature_file_types = []`).

The only daily *temperature* type in the whole catalogue is
`qu_quellwassertemp` ("Quellwassertemperatur-Tagesmittel", spring water
temperature) with 97 files.
It is a spring/groundwater-source series, not a river waterbody series, so it
fails protocol rule 2 (river-only) and rule 3 (station is not a river site).
`gw_temp_monatsmittel` (1623 files)
is groundwater temperature and monthly in any case.

## 2. The official bulk package contains monthly WT only

`GET https://gis.lfrz.gv.at/api/ehyd/messstellen/paket/ehyd_messstellen_all_owf.zip` (HTTP 200, content-length
105735422 declared; downloaded
105,735,422 bytes, sha256 `2fb165ee97520cdef280a9e8ee9921a6f0f1d1a727c1e98db3bb9a9ad9aa7265`) unpacks to
5,336 entries in 12 folders
(`results/wrr_submission_ready/multi_agency_ingest/ehyd/raw_cache/package_folder_census.csv`):

| folder | entries |
|---|---|
| Stammdaten | 798 |
| W-Monatsmaxima | 763 |
| W-Tagesmittel | 763 |
| W-Monatsminima | 763 |
| Q-Tagesmittel | 628 |
| Q-Monatsminima | 628 |
| Q-Monatsmaxima | 628 |
| WT-Monatsmittel | 324 |
| Schwebstoff-Tagesfracht | 34 |
| Geschiebe-Tagesfracht | 5 |
| messstellen_owf.csv | 1 |
| messstellen_alle.csv | 1 |

The only surface-water temperature folder is `WT-Monatsmittel`
(324 files = 324 stations
with metadata, 199 distinct official river names).
There is no `WT-Tageswerte` / `WT-Tagesmittel` folder, and the data folders that
do carry daily values are `Q-Tagesmittel` (discharge), `W-Tagesmittel` (water
level), `Geschiebe-`/`Schwebstoff-Tagesfracht` (sediment).

## 3. eHYD's own download service enumerates the allowed types server-side

`GET https://ehyd.gv.at/services/AreaSelection/download?cat=owf_wassertemp_monatsmittel&reg=0` returns
HTTP 200 with the server's own list of the
21 downloadable data types:

```
empty dat-parameter; allowed types are gw_jahresmaxima, gw_jahresminima, gw_monatsmittel, gw_temp_monatsmittel, nlv_tagessummen, nlv_minutensummen, nlv_5minutensummen, nlv_schneehoehe, nlv_neuschnee, qu_quellschuettung, qu_quellwassertemp, qu_quellleitfaehigkeit, owf_abfl_tagesmittel, owf_abfl_monatsmaxima, owf_abfl_monatsminima, owf_wasserst_tagesmittel, owf_wasserst_monatsmaxima, owf_wasserst_monatsminima, owf_wassertemp_monatsmittel, owf_geschiebe_tagesfracht, owf_schwebstoff_tagesfracht
```

Temperature entries in that list: `qu_quellwassertemp`, `owf_wassertemp_monatsmittel`.
Daily surface-water temperature entries:
`[]`.
A daily surface-water temperature type was probed explicitly
(`...&cat=owf_wassertemp_tagesmittel`) and is rejected by the same
server-side enumeration (`https://ehyd.gv.at/services/AreaSelection/download?cat=owf_wassertemp_tagesmittel&reg=0`).
Direct guesses at a daily WT package URL are also 404
(`ehyd_messstellen_all_owf_wassertemp_tagesmittel.zip`,
`ehyd_messstellen_all_wt.zip`), while `ehyd_messstellen_all_gw.zip` returns 200 —
i.e. the package namespace exists, the daily WT member does not.

## 4. The shipped web application offers monthly only

The eHYD Angular bundle (`https://ehyd.gv.at/main-UFXEVZGM.js`, sha256
`3d3fcf632b915cc1f6468dded6c3f477e05db8befa264aeecd14e4b0b5752826`) builds its data-type menu with the same ids.
Under "Oberflächengewässer" the temperature entry is
`owf_wassertemp_monatsmittel` (Wassertemperatur-Monatsmittel). `Wassertemperatur-Monatsmittel` is the only temperature option;
the daily options there are discharge, water level, snow height, bedload and
suspended-sediment.

## 5. Payload samples prove the delivered resolution is monthly


**`WT-Monatsmittel/WT-Monatsmittel-200048.csv`** (10081 bytes, 179 monthly data rows, cp1252 payload).

Header block (first lines):

```
Messstelle:                ;Schruns (Vonbunweg)
HZB-Nummer:                ;200048
HD-Nummer:                 ;
DBMS-Nummer:               ;8001004
Gewässer:                  ;Litz
Sachgebiet:                ;OWF
Dienststelle:              ;HD-Vorarlberg
Messstellenbetreiber:      ;Hydrographischer Dienst
orogr.Einzugsgebiet [km²]: ;101,37
Pegelnullpunkt:
  gültig seit:             ;Höhe [m ü.A.]:
   01.01.1976              ;00705,62
   01.01.1980              ;00671,13
   01.01.1997              ;00673,25
Bundesmeldenetz(BMN)-Koordinaten:
  gültig seit:             ;Rechtswert y [m] - Hochwert x [m]:
   01.01.1959              ;118023,88 - 215726,79
   01.01.1997              ;118153,00 - 215792,00
```

First data rows:

```
01.01.1997 00:00:00;   1,3
01.02.1997 00:00:00;   1,7
01.03.1997 00:00:00;   3,2
01.04.1997 00:00:00;   3,0
01.08.1997 00:00:00;  10,5
01.09.1997 00:00:00;  10,3
```

Last data rows:

```
01.10.2023 00:00:00;   9,1
01.11.2023 00:00:00;   5,0
01.12.2023 00:00:00;   4,4
```

**`WT-Monatsmittel/WT-Monatsmittel-200147.csv`** (10472 bytes, 149 monthly data rows, cp1252 payload).

Header block (first lines):

```
Messstelle:                ;Gisingen
HZB-Nummer:                ;200147
HD-Nummer:                 ;
DBMS-Nummer:               ;8001014
Gewässer:                  ;Ill
Sachgebiet:                ;OWF
Dienststelle:              ;HD-Vorarlberg
Messstellenbetreiber:      ;Hydrographischer Dienst
orogr.Einzugsgebiet [km²]: ;1278,17
Pegelnullpunkt:
  gültig seit:             ;Höhe [m ü.A.]:
   01.01.1912              ;00434,34
   01.01.1928              ;00439,37
   01.11.1939              ;00434,37
   01.01.1976              ;00434,34
   01.01.1996              ;00434,35
   01.03.2002              ;00434,30
   06.03.2018              ;00434,31
```

First data rows:

```
01.04.1996 00:00:00;   6,8
01.05.1996 00:00:00;   8,2
01.06.1996 00:00:00;  10,4
01.07.1996 00:00:00;  10,4
01.08.1996 00:00:00;  10,7
01.09.1996 00:00:00;   9,1
```

Last data rows:

```
01.10.2023 00:00:00;  10,2
01.11.2023 00:00:00;   6,8
01.12.2023 00:00:00;   5,9
```


Parsed with `parse_monthly_temperature` / `monthly_network`:

| station | rows | first | last | day-of-month | years | rows/year |
|---|---|---|---|---|---|---|
| 200048 | 179 | 1997-01-01 | 2023-12-01 | [1] | 21 | 8.524 |
| 210534 | 563 | 1976-02-01 | 2022-12-01 | [1] | 47 | 11.979 |
| 212704 | 164 | 2007-05-21 | 2020-12-21 | [21] | 14 | 11.714 |

All rows of a station-year sit on a single day of month (e.g. day 21, or day 1),
≈12 rows per year: these are month labels carrying a monthly mean, not daily
values. Expanding them to daily would invent data.

Per-station long-term daily archives are not served either — the diagram service
used by the app returns discharge statistics for the current year only:

| URL | parameter | n points | first | last |
|---|---|---|---|---|
| https://ehyd.gv.at/services/Diagram/pegelLongterm?hzbnr=200048 | Abfluss | 365 | 2026-01-01 | 2026-12-31 |
| https://ehyd.gv.at/services/Diagram/pegelLongterm?hzbnr=212704 | None | 0 | None | None |

Station 212704 is a WT-only station and returns an empty diagram document;
station 200048 measures both discharge and water temperature and returns
`parameter = "Abfluss"` (discharge). No daily WT series is retrievable.

## 6. What would have been available if monthly were admissible (not used)

The 324 monthly WT stations yield 23
river-name groups with ≥3 stations and ≥8 common metadata years (the module's
own candidate rule), e.g.:

| network_id | river | stations | common metadata years |
|---|---|---|---|
| ehyd_donau | Donau | 13 | 2005-2023 |
| ehyd_enns | Enns | 8 | 2011-2023 |
| ehyd_inn | Inn | 7 | 1997-2023 |
| ehyd_neusiedler_see | Neusiedler See | 7 | 1998-2023 |
| ehyd_salzach | Salzach | 7 | 2009-2023 |
| ehyd_drau | Drau | 6 | 2013-2023 |
| ehyd_traun | Traun | 6 | 1992-2023 |
| ehyd_ager | Ager | 4 | 1993-2023 |
| ehyd_bregenzerach | Bregenzerach | 4 | 1994-2023 |
| ehyd_alm | Alm | 3 | 1989-2023 |

This is recorded only to show the shortfall is the *temporal resolution*, not the
station count. Several groups are lakes in the official river-name field
(e.g. `ehyd_neusiedler_see`, Altausseer See), which would also require river-only
filtering. `results/wrr_submission_ready/multi_agency_ingest/ehyd/raw_cache/ehyd_monthly_river_candidates.csv` holds the full table;
its `candidate_status` is `source_qc_failed_monthly_only`.

## 7. Roster check

v17 roster overlap for the eHYD HZB station numbers:
0 overlapping ids
([]). Not applicable in
practice because no series is ingested.

## 8. What a reviewer should check

- That no *other* Austrian provider with daily river water temperature was used
  as a silent substitute: none was. This report is the whole eHYD outcome.
- That monthly means were not silently expanded to daily: they were not.
- That `qu_quellwassertemp` was not repackaged as river temperature: it was not.
- That nothing was scored: no frozen-screen performance was computed on any eHYD
  payload (protocol HARD RULE 4).

## Reproduce

```bash
PYTHONPATH=src python3 scripts/243_multi_agency_ehyd_ingest.py
```

Raw caches (listing, package, service probes, bundle, diagram documents) are under
`results/wrr_submission_ready/multi_agency_ingest/ehyd/raw_cache/`; machine-readable
counts are in `results/wrr_submission_ready/multi_agency_ingest/ehyd/ingest.json`.

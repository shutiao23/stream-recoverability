# Measurement provenance dictionary (F09 closure evidence)

Review date: 2026-10-12. Scope: the twelve providers whose temperature series feed
the WRR submission — the nine study providers with ingested panels
(`usgs, arso, chmi, foen, gkd_bayern, lubw, nve_hydapi, rws_waterwebservices,
syke`) and the three transport providers with ingested panels (`smhi, hubeau,
uk_ea`).

Companion artifacts:

- `results/wrr_submission_ready/measurement_provenance_dictionary.csv` — one row per
  provider, 17 columns, produced by
  `scripts/257_wrr_measurement_provenance_dictionary.py`.
- `results/wrr_submission_ready/current_data_acquisition.csv` — one row per network in
  `results/wrr_submission_ready/current_data_manifest.csv` (146/146) with provider,
  country, product, acquisition route and manifest path.

Every non-"unverified" statement below was re-checked **live** against the
provider's own page, API response, ISO-19139 metadata record or PDF on 2026-10-12;
the fetched bodies are cached in `scratch/prov/raw/` and the verbatim quotes are in
the `evidence_quote` column of the dictionary. No quote, licence or statistic in
this review was inferred or paraphrased from memory.

## 1. Per-provider verdict on the "daily mean" claim

Manuscript claim under test (claim registry `MEAS`, finding F09): *all series are
daily mean water temperature (°C)*.

| provider | what the parser actually reads | provider-documented statistic | verdict |
|---|---|---|---|
| usgs | NWIS DV `parameterCd=00010` `statCd=00003`, first values block | statistic code 00003 = `MEAN` / `MEAN VALUES`; 00010 = `Temperature, water`, `deg C` | **daily mean** |
| foen | GraphQL `water.observations.data_1day_mean`, `parameterName="WT"` | `data_1day_mean` is one of the published aggregations; `WT` = water temperature | **daily mean** |
| gkd_bayern | download `wertart=tmw&geprueft=1`, CSV column `Mittelwert` | `Werteart` offers `Einzelwerte` vs `Tageswerte` (tmw); the CSV column read is literally the mean | **daily mean** |
| nve_hydapi | `Parameter=1003&ResolutionTime=1440` | "The rest of the parameters are using type 'mean'"; day series stamped 11:00Z, day computed in Norwegian normal time UTC-1 | **daily mean** |
| uk_ea | measure `<id>-temp-m-86400-C-qualified` `/readings.json` | measure label "Daily mean Temperature (°C) time series", `period 86400`, `valueType "mean"` | **daily mean** |
| lubw | Cadenza export table row where parameter `Temperatur`, unit `°C` | LUBW page: older data are available "als Tagesmittelwerte" in the Daten- und Kartendienst; workbook attribute `Tagesmittelwert` on object type `Online Messwerte` | **daily mean (documented); exact export column only partially verified** |
| arso | HIDARHIV daily table column `temp. vode (°C)` | page titled `Dnevne vrednosti` (daily values); no statement whether it is a daily mean or a fixed-hour reading | **unverified** |
| smhi | parameter 4 `corrected-archive` CSV, quality `G` rows kept | "Daglig uppgift om vattendragstemperaturer" (daily information); no aggregation statement | **daily value documented, mean unverified** |
| chmi | `H_<station>_OT_<year>.json`, `tsConID == "TO"`, averaged per Europe/Prague day | CHMI code list: `TO` = *Měřené okamžité teploty vody* (**measured instantaneous** water temperatures); the daily-mean code is `TD` = *Průměrné denní teploty vody* | **not a provider daily mean** |
| rws_waterwebservices | `Grootheid T / OW / WaardeBewerkingsMethode NVT / ProcesType meting`, averaged per calendar date | catalogue: NVT entry is plain `Temperatuur in Oppervlaktewater`; the 24-hour mean is a **separate** parameter `GEM24H` = `Etmaalgemiddelde Temperatuur in Oppervlaktewater in oC`, which the study does not use | **not a provider daily mean** |
| syke | OData `LampoPintavesi`, `Arvo` grouped by date | "Pintaveden lämpötila mitataan perinteisesti vedenkorkeusasteikkopaikkojen rannan läheisyydestä aamuisin klo 8 20 cm pinnasta alaspäin" — near-shore morning reading at 08:00, 20 cm below the surface, open-water season only, "ohjeellisia" (indicative of the site) | **not a daily mean** |
| hubeau | `/temperature/chronique` `resultat`, Sandre code 1, resampled to daily mean | "chroniques de températures **en continu**"; each record carries `date_mesure_temp` **and** `heure_mesure_temp` | **not a provider daily statistic** |

Structural observations that a reviewer will make:

1. **Two study panels are project-derived, not provider daily statistics.** CHMI and
   RWS both define a provider daily-mean product that the study does not read: RWS's
   `GEM24H` (`Etmaalgemiddelde`) is live in the catalogue and directly re-ingestable,
   while CHMI's `TD` (`Průměrné denní teploty vody`) is documented in the CHMI code list
   but no `TD` files were located in the open-data `data/daily/` directory (which
   carries `DQ` daily discharge), so that route still needs confirmation. The study's
   "daily mean" for those two panels is an artefact of the parser's
   `groupby(date).mean()`. The derivation is honest but it is not the provider's
   contract, and it fixes a day boundary the provider never published
   (Europe/Prague for CHMI; a flat `+01:00` request window for RWS).
2. **CHMI's source cadence is 10 minutes, not daily.** A live 2023 station file
   contains 52,560 values (144 per day, timestamps in UTC, header `DT,VAL`), so each
   CHMI "daily mean" is the mean of 144 instantaneous readings — defensible, but it
   must be described as such, and it is a different quantity from a provider daily
   mean.
3. **SYKE is confirmed as a non-daily statistic.** The suspicion recorded in F09 is
   correct and is now documented: the value is a morning near-shore reading, and
   SYKE itself calls it indicative of the site rather than representative of a
   reach.
4. **Quality flags are mostly discarded, not used.** Of the twelve providers only
   four have a provider quality gate that survives into the panel (gkd_bayern
   `Geprueft`, nve_hydapi `quality>=2 and correction==0`, smhi `G`, hubeau Sandre
   `1`). usgs, arso, chmi, lubw, rws, syke and uk_ea all have the parser or the
   pipeline assign `qualifier="A"` itself. For uk_ea the provider's per-reading
   `quality` (`Good/Estimated/Suspect/Unchecked/Missing`), `completeness` and
   `qflag` fields are dropped entirely; for foen `releaseState` 1 (provisional) is
   labelled `P` and later counted as a provisional drop rather than being retained
   as a documented provisional value.
5. **RWS keeps interpolated values as if measured.** The parser's keep-list
   `{00,10,20,25,30,40}` includes `10/20/25`, which RWS's own attribute document
   defines as *Geïnterpoleerde waarde* (interpolated in space, time, or both), while
   the ordinary measured value is `0`. Codes `30` and `40` do not appear in that
   document at all. This is a data-assurance defect independent of the statistic
   question.
6. **SMHI's audited archive carried only uncontrolled values.** All 176 parameter-4
   stations returned quality `O` = *Okontrollerade värden* (1,063,746 rows), so the
   transport stratum for SMHI is `provider_published_unqualified` by construction.
   SMHI's own legend also defines `Y` as "grovt kontrollerade värden, **misstänkta
   eller aggregerade** värden" — i.e. `Y` covers suspected and aggregated values, not
   only coarsely checked ones — while the transport ingest gate accepted `G` and `Y`
   and the protocol's stratum description names only code `O`. The gate and the
   documented legend should be reconciled before the SMHI stratum is described in
   print.

## 2. Providers that must be stratified out of a unified "daily mean" claim

The manuscript cannot defend one pooled "daily mean water temperature (°C)" input
statement. Four separate strata are needed:

| stratum | providers | wording the manuscript can defend |
|---|---|---|
| A. provider daily mean | usgs, foen, gkd_bayern, nve_hydapi, uk_ea, lubw | "provider-published daily mean water temperature" |
| B. project-derived daily mean from provider sub-daily values | chmi, rws_waterwebservices | "calendar-day mean computed by us from the provider's sub-daily values" |
| C. non-daily provider statistic | syke, hubeau | "provider spot/continuous reading (SYKE: near-shore 08:00 morning reading; Hub'Eau: continuous sub-daily), aggregated by us to a day where a panel exists" |
| D. undetermined | arso, smhi | "provider daily value whose aggregation is not documented (SMHI) / not published (ARSO)" |

Providers to flag explicitly in Methods and limitations: **syke, chmi, rws_waterwebservices,
hubeau, arso, smhi**. `syke` is already excluded from the unified claim
(`results/wrr_submission_ready/measurement_provenance.csv`); `chmi`,
`rws_waterwebservices`, `arso` and `smhi` are not, and all four carry study panels
(`chmi` 17 networks, `rws_waterwebservices` 2, `arso` 12, plus `smhi` transport). If
the authors prefer a strict single-statistic claim, the executable alternative is to
re-ingest CHMI `TD` and RWS `GEM24H`, which removes stratum B for those two
providers; ARSO and SMHI cannot be repaired from public documentation and must be
described as unverified, not relabelled.

## 3. Licence and redistribution table

| provider | licence (as published) | raw values redistributable? | derived outputs? | required attribution |
|---|---|---|---|---|
| usgs | U.S. Public Domain | yes | yes | "Credit: U.S. Geological Survey" |
| foen | opendata.swiss "Open use. Must provide the source." | yes | yes | author, title and link to the dataset |
| gkd_bayern | CC BY 4.0 | yes | yes | "Datenquelle: Bayerisches Landesamt für Umwelt, www.lfu.bayern.de" |
| nve_hydapi | NLOD (compatible with CC BY 3.0 Norway) | yes | yes | NVE / HydAPI as origin |
| uk_ea | Open Government Licence v3.0 (API `licenseName "OGL 3"`) | yes | yes | Environment Agency / OGL v3.0 |
| chmi | CC BY 4.0 | yes | yes | CHMI (Český hydrometeorologický ústav) |
| syke | CC BY 4.0 | yes | yes | Finnish Environment Institute (Syke) + dataset name |
| smhi | CC BY 4.0 SE | yes | yes | SMHI as source, note modifications |
| hubeau | Licence Ouverte / Open Licence Etalab | yes | yes | author of the dataset |
| rws_waterwebservices | no named licence; "open data … iedereen is vrij om … te hergebruiken" + source/date condition | yes, with source and retrieval date | yes | Rijkswaterstaat, with retrieval date |
| arso | no named licence; terms require citing ARSO on publication/distribution | conditional on citation | conditional on citation | ARSO |
| **lubw** | **no open licence — data are "urheberrechtlich geschützt"; modification, reproduction and passing to third parties require LUBW consent** | **no** | **no (consent required)** | LUBW as source |

**What may not be published.** Only LUBW is a blocker: its own copyright notice
reserves the data, so neither the seven LUBW network panels nor raw LUBW values may
be redistributed, and derived reuse needs LUBW consent. The other eleven providers
permit redistribution with attribution, so the current practice of shipping
aggregate outputs and re-download routes is safe for them. The manuscript's
data-availability statement should name LUBW as a redistribution exception (route
only, no values) and should not describe the LUBW panel as open data. ARSO and RWS
have no named licence: redistributing their values with a citation is the published
condition, but if the authors want an unambiguous grant they should ask ARSO
(`gp.arso@gov.si`) and Rijkswaterstaat before archiving raw values.

## 4. Claims that remain unverifiable from public documentation

These are the residual F09 gaps. They cannot be closed by more scraping of the same
pages; each needs a specific new source.

1. **ARSO — is the daily `temp. vode` value a daily mean or a reading at a fixed
   hour?** The HIDARHIV page offers only "Dnevne vrednosti"; the same page prints
   monthly max/min rows *with* clock times (`17. ob 22:30`) but gives no time for the
   daily water-temperature value, and the 2003 yearbook explanation defines only
   monthly/annual `Ts` (srednja). *Needed to close:* an ARSO station-description or
   monitoring-programme document (or written confirmation to `gp.arso@gov.si`)
   stating the observation hour or the aggregation for `T` at the study stations.
2. **SMHI — is the daily `Vattendragstemperatur` a daily mean or a once-daily
   reading?** The ISO-19139 record states only "Daglig uppgift om
   vattendragstemperaturer" and the lineage statement is "-". The published CSV has a
   date column only (`Datum (svensk sommartid)`), no hour. *Needed to close:* SMHI's
   hydroobs product description or measurement instruction for parameter 4 (SMHI
   customer service / `dataleveranser@smhi.se`), or a station-level measurement
   programme record.
3. **USGS — day boundary and timezone of a daily value.** Statistic 00003 is
   documented as MEAN, but no page fetched states the averaging window or the water-day
   convention. *Needed to close:* the NWIS daily-values service documentation
   (legacy `waterservices.usgs.gov/rest/DV-Service.html` is now a 404) or the OGC
   daily collection's per-timeseries metadata, which should give the local time
   basis.
4. **LUBW — the exact statistic of the parsed export column.** The daily-mean
   semantics are documented (page text + workbook attribute `Tagesmittelwert`), but
   the Cadenza workbook id/hash is created per session, so the column index the
   parser reads (`values[12]`, unit at `values[13]`) could not be re-verified against
   a durable URL. *Needed to close:* a durable LUBW export/documentation route, or
   column names captured in-session and recorded in the ingest manifest.
5. **RWS — meaning of the kept quality codes `30` and `40`, and the day boundary of
   the derived mean.** The RWS attribute document defines `0, 3, 6/7, 10/15/20/25,
   31, 99` and refers elsewhere for other codes ("Voor overige codes zie Aquo, WRD").
   *Needed to close:* the Aquo `Kwaliteitswaardecode` domeintabel (or the DDAPI20
   documentation), plus a statement of the local day used by `Etmaalgemiddelde`.

Subsidiary note: the full Sandre qualification table (`1 Correcte`, `2`, `3`,
`4 Non qualifié`) could not be re-fetched because `sandre.eaufrance.fr` was
unreachable at retrieval time; the code-4 label is nevertheless documented live in
Hub'Eau's own example payload, and the repository's earlier citation of Sandre ALQ
2.2 remains the source for codes 2 and 3.

## 5. Changes made to `metadata/data_rights.csv`

Seven rows were updated from `provider_terms_not_verified_for_redistribution` after
live re-verification (29 field changes); all other 46 rows are byte-identical.

| row | new `license` | redistribution | evidence URL added to `reviewer_access_route` |
|---|---|---|---|
| v11 ARSO confirmation temperature | `ARSO_terms_of_use_no_named_licence_citation_required` | conditional on citation | https://vode.arso.gov.si/hidarhiv/ |
| v11 CHMI confirmation temperature | `CC-BY-4.0` | true | https://www.chmi.cz/-/jak-mohu-používat-otevřená-data-čhmú- |
| v11 GKD Bayern confirmation temperature | `CC-BY-4.0` | true | https://www.gkd.bayern.de/de/impressum |
| v11 LUBW confirmation temperature | `lubw_copyright_reuse_and_redistribution_require_LUBW_consent` | false (derived outputs also false) | https://www.lubw.baden-wuerttemberg.de/impressum |
| v11 RWS confirmation temperature | `rijkswaterstaat_open_data_no_named_licence_source_and_retrieval_date_required` | true | https://www.rijkswaterstaat.nl/zakelijk/open-data ; https://rijkswaterstaatdata.nl/vaste-onderdelen/verantwoording/ |
| v11 FOEN confirmation temperature | `opendata.swiss_open_use_must_provide_the_source_terms_by` | true | https://api.data-platform.cloud.bafu.admin.ch/en/lizenz-und-quelle |
| v11 SYKE candidate temperature | `CC-BY-4.0` | true | https://www.syke.fi/en/environmental-data/use-license-and-responsibilities |

Left untouched deliberately: `v11 eHYD candidate temperature` (Austrian terms not
re-verified in this pass) and `v11 NVE second-confirmation temperature`, which
already records the verified `NLOD_compatible_CC_BY_3`.

## 6. Reproduction

```bash
PYTHONPATH=src python3 scripts/257_wrr_measurement_provenance_dictionary.py
python3 scratch/prov/update_data_rights.py     # already applied; re-running is a no-op
```

Raw live evidence (HTML/JSON/PDF bodies, one file per fetch, plus `raw/*.txt`
PDF extractions) is under `scratch/prov/raw/`; the fetch helper and the compact
excerpt tool are `scratch/prov/fetch.sh` and `scratch/prov/x.py`.

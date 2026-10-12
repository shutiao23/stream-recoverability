"""Build the WRR measurement-provenance dictionary and the acquisition map.

Answers adversarial finding F09: the manuscript states that every provider input
is a daily mean water temperature in degrees C.  This script records, per
provider, (a) the data product actually read by the repository parser, (b) the
statistic the provider documents for that value, (c) the aggregation interval and
day boundary, (d) the quality codes retained or dropped, (e) licence and
redistribution terms, (f) the route a third party would use, and (g) the evidence
URL plus a short verbatim quote.

Every non-"unverified" cell was checked against a live provider page, API
response, ISO-19139 metadata record or PDF on 2026-10-12 (raw bodies are cached
under scratch/prov/raw/).  Quotes are verbatim from those bodies, shortened.

The script is offline and deterministic: it reads
`results/wrr_submission_ready/current_data_manifest.csv` and writes two CSVs.  It
does not fetch anything and does not modify any other artifact.

    PYTHONPATH=src python3 scripts/257_wrr_measurement_provenance_dictionary.py

Outputs
-------
results/wrr_submission_ready/measurement_provenance_dictionary.csv
results/wrr_submission_ready/current_data_acquisition.csv
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "results/wrr_submission_ready/current_data_manifest.csv"
OUT_DICTIONARY = (
    ROOT / "results/wrr_submission_ready/measurement_provenance_dictionary.csv"
)
OUT_ACQUISITION = ROOT / "results/wrr_submission_ready/current_data_acquisition.csv"

RETRIEVED = "2026-10-12"

DICTIONARY_COLUMNS = [
    "provider",
    "country",
    "product",
    "statistic_documented",
    "statistic_as_parsed",
    "aggregation_interval",
    "day_boundary_tz",
    "quality_codes_kept",
    "quality_codes_dropped",
    "license",
    "redistribution_allowed",
    "derived_output_allowed",
    "required_citation",
    "acquisition_route",
    "evidence_url",
    "evidence_quote",
    "verification_status",
]

ACQUISITION_COLUMNS = [
    "network_id",
    "provider",
    "country",
    "product",
    "acquisition_route",
    "manifest_path",
    "source_root",
    "split_role",
    "n_stations",
    "n_station_years",
]

# --------------------------------------------------------------------------
# Per-provider provenance records.  One dict per provider; each evidence_quote is
# verbatim (shortened) from the page named in evidence_url.
# --------------------------------------------------------------------------
PROVIDERS: list[dict[str, str]] = [
    {
        "provider": "usgs",
        "country": "United States",
        "product": (
            "USGS NWIS daily values (DV): waterservices.usgs.gov/nwis/dv with "
            "parameterCd=00010 and statCd=00003; the modern equivalent is the "
            "api.waterdata.usgs.gov OGC API daily collection"
        ),
        "statistic_documented": (
            "daily mean: statistic code 00003 is documented as MEAN VALUES; "
            "parameter 00010 is 'Temperature, water, deg C'"
        ),
        "statistic_as_parsed": (
            "daily mean: parser reads the first values block of the statCd=00003 "
            "time series and keeps the point 'value' plus 'qualifiers'"
        ),
        "aggregation_interval": (
            "one value per calendar day (daily value / DV); the averaging window "
            "is not stated on the pages fetched"
        ),
        "day_boundary_tz": "unverified (no water-day/timezone statement found)",
        "quality_codes_kept": (
            "all returned values; the JSON 'qualifiers' array is carried through "
            "unfiltered, and the OGC daily collection exposes 'approvals_status' "
            "(example: ['Approved'])"
        ),
        "quality_codes_dropped": (
            "none dropped at parse time; the study does not gate on "
            "Approved/Provisional, so provisional values are admitted"
        ),
        "license": (
            "US Government public domain: 'USGS-authored or produced data and "
            "information are considered to be in the U.S. Public Domain.'"
        ),
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "'Credit: U.S. Geological Survey' (USGS asks that proper credit be "
            "given); cite the USGS Water Data APIs used"
        ),
        "acquisition_route": (
            "https://waterservices.usgs.gov/nwis/dv/?format=json&sites=<site_no>"
            "&parameterCd=00010&statCd=00003&startDT=<YYYY-MM-DD>&endDT=<YYYY-MM-DD>"
            " or https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items"
            "?monitoring_location_id=USGS-<site_no>&parameter_code=00010"
            "&statistic_id=00003 ; no key required"
        ),
        "evidence_url": (
            "https://api.waterdata.usgs.gov/ogcapi/v0/collections/statistic-codes/"
            "items?f=json&limit=200 ; https://api.waterdata.usgs.gov/ogcapi/v0/"
            "collections/parameter-codes/items?f=json&id=00010 ; "
            "https://waterdata.usgs.gov/nwis/dv ; "
            "https://www.usgs.gov/information-policies-and-instructions/"
            "copyrights-and-credits"
        ),
        "evidence_quote": (
            '{"id": "00003", "statistic_name": "MEAN", "statistic_description": '
            '"MEAN VALUES"} | {"id": "00010", "parameter_name": "Temperature, '
            'water", "unit_of_measure": "deg C"} | "These data have also been '
            'referred to as \u201cdaily values\u201d or \u201cDV\u201d." | '
            '"USGS-authored or produced data and information are considered to '
            'be in the U.S. Public Domain."'
        ),
        "verification_status": (
            "statistic and licence verified live; day boundary/timezone unverified"
        ),
    },
    {
        "provider": "arso",
        "country": "Slovenia",
        "product": (
            "ARSO HIDARHIV surface-water archive table (pov_arhiv_tab.php), column "
            "'temp. vode (\u00b0C)'"
        ),
        "statistic_documented": (
            "unverified: the page is titled 'Dnevne vrednosti' (daily values) and "
            "publishes one water-temperature value per day, but no page fetched "
            "states whether it is a daily mean or a reading at a fixed hour"
        ),
        "statistic_as_parsed": (
            "the single daily 'temp. vode' cell; the parser hard-codes qualifier "
            "'A' and never sees a provider flag"
        ),
        "aggregation_interval": (
            "one value per calendar day (daily table); monthly max/min rows on the "
            "same page do carry explicit clock times (e.g. '17. ob 22:30')"
        ),
        "day_boundary_tz": "unverified (no day-boundary or timezone statement)",
        "quality_codes_kept": (
            "none published in the table; parser assigns 'A' itself"
        ),
        "quality_codes_dropped": (
            "n/a - the daily table exposes no qualification column"
        ),
        "license": (
            "no named licence published; ARSO terms of use require source "
            "citation on publication or distribution"
        ),
        "redistribution_allowed": (
            "conditional: terms contemplate publication/distribution provided "
            "ARSO is cited as the source; no open licence text found"
        ),
        "derived_output_allowed": (
            "conditional: no prohibition found, citation of ARSO required"
        ),
        "required_citation": (
            "ARSO (Agencija Republike Slovenije za okolje) as the data source"
        ),
        "acquisition_route": (
            "https://vode.arso.gov.si/hidarhiv/pov_arhiv_tab.php?p_vodotok=<river>"
            "&p_postaja=<station_id>&p_leto=<year>&b_arhiv=Prika\u017ei (HTML table, "
            "one request per station-year; no key)"
        ),
        "evidence_url": (
            "https://vode.arso.gov.si/hidarhiv/pov_arhiv_tab.php?p_vodotok=Sava&"
            "p_postaja=3420&p_leto=2015&b_arhiv=Prika%C5%BEi ; "
            "https://vode.arso.gov.si/hidarhiv/"
        ),
        "evidence_quote": (
            '"Arhiv hidrolo\u0161kih podatkov - dnevni podatki" / "Dnevne vrednosti" / '
            'header "Datum vodostaj (cm) pretok (m3/s) temp. vode (\u00b0C)" | '
            '"Pri objavi, distribuciji ali uporabi podatkov v kakr\u0161nekoli namene '
            'je potrebno citirati vir podatkov: Agencije Republike Slovenije za '
            'okolje (ali skraj\u0161ano: ARSO)." | "Podatki v arhivu so pregledani"'
        ),
        "verification_status": (
            "product, daily cadence, terms and citation verified live; statistic "
            "and day boundary unverified"
        ),
    },
    {
        "provider": "chmi",
        "country": "Czechia",
        "product": (
            "CHMI open-data historical measured_temperature: "
            "H_<station>_OT_<year>.json, series tsConID='TO'"
        ),
        "statistic_documented": (
            "instantaneous, NOT a daily mean: CHMI's own code list defines "
            "TO = 'M\u011b\u0159en\u00e9 okam\u017eit\u00e9 teploty vody' (measured instantaneous "
            "water temperatures) and separately defines TD = 'Pr\u016fm\u011brn\u00e9 denn\u00ed "
            "teploty vody' (average daily water temperatures)"
        ),
        "statistic_as_parsed": (
            "project-derived daily mean: the parser averages every 10-minute TO "
            "value per calendar day (Europe/Prague); the provider's daily series "
            "(code TD) is not used"
        ),
        "aggregation_interval": (
            "source values every 10 minutes; a live 2023 file carries 52,560 "
            "values (144/day) with header 'DT,VAL'"
        ),
        "day_boundary_tz": (
            "source timestamps are UTC (e.g. 2023-01-01T00:00:00Z); the day "
            "boundary is the project's Europe/Prague conversion, not a CHMI "
            "statement"
        ),
        "quality_codes_kept": "none published; parser sets 'published_historical' and 'A'",
        "quality_codes_dropped": (
            "n/a - the OT schema has no qualification field (schema is objID + "
            "tsList only)"
        ),
        "license": "Creative Commons BY 4.0 (CHMI open data)",
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": "CHMI (\u010cesk\u00fd hydrometeorologick\u00fd \u00fastav) as the data source",
        "acquisition_route": (
            "https://opendata.chmi.cz/hydrology/historical/data/measured_temperature/"
            "H_<station>_OT_<year>.json (instantaneous 10-min); morning readings at "
            ".../data/morning_temperature/H_<station>_OT7_<year>.json; daily "
            "discharge at .../data/daily/ ; code list at "
            "https://opendata.chmi.cz/hydrology/historical/metadata/meta2.json ; no key"
        ),
        "evidence_url": (
            "https://opendata.chmi.cz/hydrology/historical/metadata/meta2.json ; "
            "https://opendata.chmi.cz/hydrology/historical/metadata/H_SCHEMA_OT.json ; "
            "https://opendata.chmi.cz/hydrology/historical/data/measured_temperature/"
            "H_0-203-1-000400_OT_2023.json ; "
            "https://www.chmi.cz/-/jak-mohu-pou%C5%BE%C3%ADvat-otev%C5%99en%C3%A1-"
            "data-%C4%8Dhm%C3%BA-"
        ),
        "evidence_quote": (
            '["TO","M\u011b\u0159en\u00e9 okam\u017eit\u00e9 teploty vody","0C","\u00b0C"] | '
            '["TD","Pr\u016fm\u011brn\u00e9 denn\u00ed teploty vody","0C","\u00b0C"] | '
            '"Teplota vody / Water temperature" (tsConID TO) with header "DT,VAL" | '
            '"Otev\u0159en\u00e1 data \u010cHM\u00da m\u016f\u017eete vyu\u017e\u00edvat bezplatn\u011b p\u0159i '
            'respektov\u00e1n\u00ed licence Creative Commons BY 4.0."'
        ),
        "verification_status": (
            "statistic (instantaneous), cadence, schema and licence verified live; "
            "the code list documents a provider daily-mean series (TD) but no TD "
            "files were found in data/daily/ (which carries DQ daily discharge), so "
            "that route is not yet confirmed"
        ),
    },
    {
        "provider": "foen",
        "country": "Switzerland",
        "product": (
            "FOEN/BAFU water-observations GraphQL API, field "
            "water.observations.data_1day_mean with parameterName='WT'"
        ),
        "statistic_documented": (
            "daily mean: the platform lists 'data_1day_mean' among the available "
            "aggregations and WT as water temperature"
        ),
        "statistic_as_parsed": (
            "daily mean read directly from data_1day_mean (value + unitSymbol + "
            "releaseState; no re-aggregation)"
        ),
        "aggregation_interval": "1 day; timestamp is the start of the aggregation interval",
        "day_boundary_tz": (
            "timestamps are ISO-8601 UTC ('Aggregation interval start (ISO-8601 "
            "UTC)'); the local boundary behind the 1-day aggregate is not stated"
        ),
        "quality_codes_kept": (
            "releaseState 2 (validated) and 3 (final/replaced); the parser maps "
            "these to qualifier 'A'"
        ),
        "quality_codes_dropped": (
            "releaseState 1 (provisional) is labelled qualifier 'P' and is counted "
            "as a provisional drop by the daily QC gate"
        ),
        "license": (
            "opendata.swiss 'Open use. Must provide the source.' (terms_by): use "
            "for non-commercial and commercial purposes, source must be named"
        ),
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "name the source (author, title and link to the dataset), i.e. FOEN/"
            "BAFU hydrological observations via data.bafu.admin.ch"
        ),
        "acquisition_route": (
            "POST https://data.bafu.admin.ch/api with the GraphQL selection "
            "water { observations { data_1day_mean(where: {station: {no: {_eq: "
            "\"<station>\"}}, parameterName: {_eq: \"WT\"}, timestamp: {_gte: ..., "
            "_lt: ...}}) { timestamp parameterName value unitSymbol releaseState } } } "
            "in disjoint calendar-year windows; no key"
        ),
        "evidence_url": (
            "https://api.data-platform.cloud.bafu.admin.ch/en/"
            "dataproduct-water-observations ; "
            "https://api.data-platform.cloud.bafu.admin.ch/en/lizenz-und-quelle ; "
            "https://data.bafu.admin.ch/api"
        ),
        "evidence_quote": (
            '"Available aggregations: data_10min_mean, data_1hour_mean, '
            'data_1day_mean, data_1day_min, data_1day_max, data_1month_mean, '
            'data_1year_mean, and data_live." | "parameterName ... Common values: '
            'Q (discharge), W (water level), WT (water temperature)." | "timestamp '
            '| AWSDateTime | Aggregation interval start (ISO-8601 UTC)." | "The data '
            'provided through the platform is published under the \"Open use. Must '
            'provide the source.\" licence"'
        ),
        "verification_status": "statistic, interval, release states and licence verified live",
    },
    {
        "provider": "gkd_bayern",
        "country": "Germany (Bavaria)",
        "product": (
            "Gew\u00e4sserkundlicher Dienst Bayern download center: daily "
            "water-temperature archive (wertart=tmw, geprueft=1) delivered as a "
            "semicolon CSV member of a ZIP"
        ),
        "statistic_documented": (
            "daily mean: the download form offers 'Einzelwerte' (ezw) vs "
            "'Tageswerte' (tmw = Tagesmittelwerte) plus 'Nur gepr\u00fcfte Werte', and "
            "the CSV column read by the parser is literally 'Mittelwert'"
        ),
        "statistic_as_parsed": (
            "daily mean: parser reads the 'Mittelwert' column; 'Maximum' and "
            "'Minimum' are carried but not used as the study value"
        ),
        "aggregation_interval": "1 day (Tageswerte)",
        "day_boundary_tz": "unverified (no day-boundary/timezone statement found)",
        "quality_codes_kept": (
            "'Geprueft' (checked) rows -> qualifier 'A'; the request already pins "
            "geprueft=1"
        ),
        "quality_codes_dropped": (
            "unchecked rows are excluded at request time; any non-'Geprueft' "
            "Pr\u00fcfstatus would map to qualifier 'P'"
        ),
        "license": (
            "CC BY 4.0: 'Namensnennung 4.0 International (CC BY 4.0)' for GKD "
            "download data, commercial use included"
        ),
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "'Datenquelle: Bayerisches Landesamt f\u00fcr Umwelt, www.lfu.bayern.de'"
        ),
        "acquisition_route": (
            "station index https://www.gkd.bayern.de/de/fluesse/wassertemperatur/"
            "tabellen -> station download page .../messwerte?method=tabellen -> "
            "POST https://www.gkd.bayern.de/de/downloadcenter/enqueue_download with "
            "wertart=tmw&geprueft=1&zr=gesamt then GET the returned deeplink + '&dl=1'; "
            "no key"
        ),
        "evidence_url": (
            "https://www.gkd.bayern.de/de/downloadcenter ; "
            "https://www.gkd.bayern.de/de/impressum"
        ),
        "evidence_quote": (
            '"Werteart ... Tageswerte" (input name="wertart" value="tmw") ; "Nur '
            'gepr\u00fcfte Werte" | CSV header "Datum;Mittelwert;Maximum;Minimum;'
            'Pr\u00fcfstatus" | "Die Download-Daten im GKD wurden von der Fachseite '
            'her mit der \"Namensnennung 4.0 International (CC BY 4.0)\" lizensiert." '
            '| "Datenquelle: Bayerisches Landesamt f\u00fcr Umwelt, www.lfu.bayern.de"'
        ),
        "verification_status": (
            "statistic (daily mean), quality gate and licence verified live; day "
            "boundary unverified"
        ),
    },
    {
        "provider": "lubw",
        "country": "Germany (Baden-W\u00fcrttemberg)",
        "product": (
            "LUBW Daten- und Kartendienst public Cadenza workbook 'Daten der "
            "Online-Messstationen', export table view u6gf2s5q46r310DCsAlb "
            "('Exporttabelle Messwerte')"
        ),
        "statistic_documented": (
            "daily mean: LUBW's river-data page states that older data are "
            "available as daily means ('Tagesmittelwerte'), and the live workbook "
            "defines an attribute with the printed name 'Tagesmittelwert' on object "
            "type 'Online Messwerte'"
        ),
        "statistic_as_parsed": (
            "parser keeps rows with parameter 'Temperatur' and unit '\u00b0C' and "
            "takes the value cell of the export table; the exact column index could "
            "not be re-verified because the workbook state id is session-opaque"
        ),
        "aggregation_interval": "1 day for the Tagesmittelwert attribute",
        "day_boundary_tz": (
            "source timestamps are parsed with tz_convert('Europe/Berlin') then "
            "normalised; the provider's own day convention is not stated"
        ),
        "quality_codes_kept": (
            "none published in the export; parser sets provider_quality_status="
            "'published_daily_mean' and qualifier 'A'"
        ),
        "quality_codes_dropped": "n/a - no qualification column identified",
        "license": (
            "no open licence: LUBW copyright notice reserves the data "
            "('urheberrechtlich gesch\u00fctzt', reproduction/passing to third parties "
            "only with LUBW consent); source must be named as LUBW"
        ),
        "redistribution_allowed": (
            "false: redistribution of raw values requires LUBW consent"
        ),
        "derived_output_allowed": (
            "unverified/consent required: the same notice covers derived reuse; "
            "aggregate published outputs should be cleared by the editor"
        ),
        "required_citation": (
            "LUBW as the source, with the processing date where possible "
            "('Als Quelle ist die LUBW zu nennen')"
        ),
        "acquisition_route": (
            "https://umweltdaten.lubw.baden-wuerttemberg.de/w/online-messstationen "
            "-> read the ephemeral workbook id/hash from the 'initial-workbook-state' "
            "payload -> GET https://umweltdaten.lubw.baden-wuerttemberg.de/workbooks/"
            "<id>,hash=<hash>/views/u6gf2s5q46r310DCsAlb/tableData?offset=&limit= ; "
            "the state id must be re-derived per session (a durable URL returns 404)"
        ),
        "evidence_url": (
            "https://www.lubw.baden-wuerttemberg.de/wasser/fliessgewaesserdaten ; "
            "https://umweltdaten.lubw.baden-wuerttemberg.de/w/online-messstationen ; "
            "https://www.lubw.baden-wuerttemberg.de/impressum"
        ),
        "evidence_quote": (
            '"L\u00e4nger zur\u00fcckliegende Daten finden Sie als Tagesmittelwerte ebenfalls '
            'im Daten- und Kartendienst der LUBW." | workbook attribute printName '
            '"Tagesmittelwert" (objecttype "Online Messwerte") | "Alle auf dieser '
            'Internetseite ver\u00f6ffentlichten Beitr\u00e4ge, Abbildungen und Daten sind '
            'urheberrechtlich gesch\u00fctzt. Sie d\u00fcrfen nur mit Zustimmung der LUBW '
            'ver\u00e4ndert, vervielf\u00e4ltigt, in Vervielf\u00e4ltigungen an Dritte abgegeben '
            'oder zu \u00f6ffentlichen Wiedergaben verwendet werden."'
        ),
        "verification_status": (
            "documented statistic, licence and route verified live; the parsed "
            "column mapping is partially verified (ephemeral workbook state)"
        ),
    },
    {
        "provider": "nve_hydapi",
        "country": "Norway",
        "product": (
            "NVE HydAPI v1 Series and Observations, Parameter=1003 (water "
            "temperature), ResolutionTime=1440"
        ),
        "statistic_documented": (
            "daily mean: HydAPI documents that all parameters except "
            "precipitation (sum) and snow depth (instant) use aggregation type "
            "'mean', and water temperature is parameter 1003"
        ),
        "statistic_as_parsed": (
            "daily mean read directly from ResolutionTime=1440 (no re-aggregation)"
        ),
        "aggregation_interval": (
            "1440 minutes; day series are timestamped 11:00Z and the day is "
            "computed in 'Norwegian normal time' UTC-1"
        ),
        "day_boundary_tz": (
            "UTC-1 (Norwegian normal time) for the day value; API timestamps are "
            "UTC-0 and day series are stamped 11:00Z"
        ),
        "quality_codes_kept": (
            "quality 2 (PrimaryControlled) and 3 (SecondaryControlled) with "
            "correction == 0 ('No changes')"
        ),
        "quality_codes_dropped": (
            "quality 0 (Unknown) and 1 (Uncontrolled); every correction code "
            "other than 0, including 2 Interpolation and 4 'Daily mean computed "
            "with arithmetic mean'"
        ),
        "license": (
            "NLOD (Norwegian License for Open Government Data), compatible with "
            "CC BY 3.0 Norway; data provided 'as is'"
        ),
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "refer to the HydAPI service as the origin of data; attribute NVE and "
            "the NLOD/CC BY 3.0 Norway licence"
        ),
        "acquisition_route": (
            "https://hydapi.nve.no/api/v1/Series?Parameter=1003 then "
            "https://hydapi.nve.no/api/v1/Observations?StationId=<ids>&Parameter=1003"
            "&ResolutionTime=1440&ReferenceTime=<start>/<end> with header "
            "'X-API-Key: <key>' (key from https://hydapi.nve.no/)"
        ),
        "evidence_url": (
            "https://hydapi.nve.no/UserDocumentation/"
        ),
        "evidence_quote": (
            '"The rest of the parameters are using type \"mean\"." | "The quality '
            'types is indicating if the observed values is be quality checked ... '
            'Unknown = 0, Uncontrolled = 1, PrimaryControlled = 2, '
            'SecondaryControlled = 3" | "All the timestamps returned from the API '
            'are given in the timezone UTC-0 (Zulu-time). Time series with '
            'resolutiontime day, is timestamped with 11:00Z. The data for a day '
            'observation is calculted using \"Norwegian normal time\" UTC-1." | '
            '"The data provided by the API is licensed under the Norwegian License '
            'for Open Government Data (NLOD)"'
        ),
        "verification_status": (
            "statistic, quality codes, day boundary and licence verified live"
        ),
    },
    {
        "provider": "rws_waterwebservices",
        "country": "Netherlands",
        "product": (
            "Rijkswaterstaat DDAPI20 WaterWebservices: OphalenCatalogus + "
            "OphalenWaarnemingen for Grootheid T / Compartiment OW / "
            "WaardeBewerkingsMethode NVT / ProcesType 'meting'"
        ),
        "statistic_documented": (
            "instantaneous raw measurement, NOT a daily mean: the NVT parameter is "
            "catalogue entry 'Temperatuur in Oppervlaktewater in oC'; RWS also "
            "publishes a separate 24-hour mean parameter, GEM24H "
            "'Etmaalgemiddelde Temperatuur in Oppervlaktewater in oC', which the "
            "study does not use"
        ),
        "statistic_as_parsed": (
            "project-derived daily mean: parser keeps raw 'MetingenLijst' values "
            "whose Kwaliteitswaardecode is in {00,10,20,25,30,40} and averages them "
            "per calendar date"
        ),
        "aggregation_interval": (
            "irregular raw measurement times within each yearly request window; "
            "the study aggregates them to one value per day"
        ),
        "day_boundary_tz": (
            "request windows are written with a flat +01:00 offset on both bounds "
            "(winter and summer); the resulting day boundary is therefore the "
            "project's, and the provider's own Etmaalgemiddelde boundary is not "
            "stated"
        ),
        "quality_codes_kept": (
            "Kwaliteitswaardecode 00 (documented as a normal measured value); the "
            "parser also keeps 10/20/25, which the RWS attribute document defines "
            "as interpolated values, plus 30 and 40 (not found in that document)"
        ),
        "quality_codes_dropped": (
            "all other codes, e.g. 99 (hiaatwaarde/gap), 3 and 31; 15 "
            "(interpolated) is dropped even though 10/20/25 are kept"
        ),
        "license": (
            "no named licence published: Rijkswaterstaat states its data are open "
            "data and free to reuse, and its site notice requires source + retrieval "
            "date"
        ),
        "redistribution_allowed": (
            "true per the open-data statement; cite the source site and the date "
            "the information was taken"
        ),
        "derived_output_allowed": "true",
        "required_citation": (
            "Rijkswaterstaat WaterWebservices as the source, with the retrieval date"
        ),
        "acquisition_route": (
            "POST https://ddapi20-waterwebservices.rijkswaterstaat.nl/"
            "METADATASERVICES/OphalenCatalogus to resolve the parameter, then POST "
            "https://ddapi20-waterwebservices.rijkswaterstaat.nl/"
            "ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen with Locatie/Grootheid/"
            "Periode JSON; no key"
        ),
        "evidence_url": (
            "https://ddapi20-waterwebservices.rijkswaterstaat.nl/"
            "METADATASERVICES/OphalenCatalogus ; "
            "http://rijkswaterstaatdata.nl/publish/pages/223004/"
            "uitleg-attributen-bij-bulkwaarnemingenservice-dd-06-11-2023-.pdf ; "
            "https://www.rijkswaterstaat.nl/zakelijk/open-data ; "
            "https://rijkswaterstaatdata.nl/vaste-onderdelen/verantwoording/"
        ),
        "evidence_quote": (
            '"Parameter_Wat_Omschrijving": "Temperatuur in Oppervlaktewater in oC", '
            '"WaardeBewerkingsMethode": {"Code": "NVT"} | "Parameter_Wat_'
            'Omschrijving": "Etmaalgemiddelde Temperatuur in Oppervlaktewater in '
            'oC", "WaardeBewerkingsMethode": {"Code": "GEM24H"} | '
            '"Kwaliteitsoordeel_Code ... 0 geeft een normale gemeten waarde aan ... '
            '10, 15, 20, 25 Geinterpoleerde waarde (resp. ruimte, normaal, tijd, '
            'beide) ... 99 geeft een hiaatwaarde aan." | "Iedereen is vrij om data '
            'van Rijkswaterstaat in te zien en te hergebruiken."'
        ),
        "verification_status": (
            "product, raw-measurement semantics, code table and open-data statement "
            "verified live; the day boundary and the meaning of kept codes 30/40 are "
            "unverified"
        ),
    },
    {
        "provider": "syke",
        "country": "Finland",
        "product": (
            "SYKE Hydrologiarajapinta 1.2 OData entity LampoPintavesi "
            "(surface-water temperature), fields Paikka_Id, Aika, Arvo"
        ),
        "statistic_documented": (
            "NOT a daily mean: SYKE documents a morning near-shore reading - "
            "'Pintaveden l\u00e4mp\u00f6tila mitataan perinteisesti "
            "vedenkorkeusasteikkopaikkojen rannan l\u00e4heisyydest\u00e4 aamuisin klo 8 20 cm "
            "pinnasta alasp\u00e4in' (measured near the shore at 8 a.m., 20 cm below the "
            "surface), open-water season only, and indicative of the site"
        ),
        "statistic_as_parsed": (
            "the groupby('site_id','date').mean() in the parser reproduces the "
            "morning reading when one value per day exists; it is not a "
            "provider-documented daily mean"
        ),
        "aggregation_interval": (
            "one observation per day in practice (morning reading); the entity key "
            "is (Paikka_Id, Aika) with no stated interval"
        ),
        "day_boundary_tz": (
            "unverified: Aika is Edm.DateTime with no offset and no documented "
            "timezone"
        ),
        "quality_codes_kept": (
            "none: LampoPintavesi has no flag property (unlike LumiPiste, which has "
            "Lippu_Id); parser sets provider_quality_status='published_no_flag_field'"
        ),
        "quality_codes_dropped": "n/a - no quality field exists on this entity",
        "license": (
            "Creative Commons Attribution 4.0 International (CC BY 4.0) for SYKE "
            "open data"
        ),
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "'the name of the licensor and the name of the data', e.g. Surface "
            "water temperature / Source: Finnish Environment Institute (Syke)"
        ),
        "acquisition_route": (
            "https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.2/odata/"
            "LampoPintavesi?$filter=Paikka_Id eq <id> (paged by odata.nextLink); "
            "station catalogue .../Paikka?$filter=Suure_Id eq 11 ; no key"
        ),
        "evidence_url": (
            "https://wwwi3.ymparisto.fi/i3/tilanne/fin/Lampotila/Lampotila.htm ; "
            "https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.2/odata/"
            "$metadata ; "
            "https://www.syke.fi/en/environmental-data/use-license-and-responsibilities"
        ),
        "evidence_quote": (
            '"Pintaveden l\u00e4mp\u00f6tila mitataan perinteisesti '
            'vedenkorkeusasteikkopaikkojen rannan l\u00e4heisyydest\u00e4 aamuisin klo 8 20 cm '
            'pinnasta alasp\u00e4in." | "<Property Name=\"Arvo\" Type=\"Edm.Decimal\" '
            'Nullable=\"false\" />" (LampoPintavesi key Paikka_Id + Aika, no flag) | '
            '"Open data distributed by the Finnish Environment Institute (Syke) is '
            'licenced under Creative Commons Attribution 4.0 International licence."'
        ),
        "verification_status": (
            "morning 08:00 near-shore reading, absent quality field and licence "
            "verified live; timezone unverified"
        ),
    },
    {
        "provider": "smhi",
        "country": "Sweden",
        "product": (
            "SMHI HydroObs open-data parameter 4 'Vattendragstemperatur', period "
            "'corrected-archive' CSV (Datum;Vattendragstemperatur;Kvalitet)"
        ),
        "statistic_documented": (
            "daily value, aggregation unverified: the ISO-19139 record for "
            "parameter 4 states 'Daglig uppgift om vattendragstemperaturer' (daily "
            "information on river temperatures) but never says whether it is a "
            "daily mean or a once-daily reading"
        ),
        "statistic_as_parsed": (
            "one value per dated row; the parser keeps quality 'G' rows unchanged "
            "and does not re-aggregate"
        ),
        "aggregation_interval": "one row per calendar day",
        "day_boundary_tz": (
            "the CSV header declares the date axis as 'Datum (svensk sommartid)' "
            "(Swedish summer time); no hour is published"
        ),
        "quality_codes_kept": "'G' (Gr\u00f6n = kontrollerade och godk\u00e4nda v\u00e4rden)",
        "quality_codes_dropped": (
            "'Y' (Gul = grovt kontrollerade, misst\u00e4nkta eller aggregerade v\u00e4rden) "
            "and 'O' (Orange = okontrollerade v\u00e4rden); every parameter-4 station in "
            "the audited archive carried only 'O'"
        ),
        "license": "Creative Commons Attribution 4.0 SE (CC BY 4.0 SE)",
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "state SMHI as the source ('Ange om m\u00f6jligt SMHI som k\u00e4lla') and note "
            "any modification"
        ),
        "acquisition_route": (
            "https://opendata-download-hydroobs.smhi.se/api/version/latest/"
            "parameter/4.json (catalogue) then .../parameter/4/station/<id>/period/"
            "corrected-archive/data.csv ; no key"
        ),
        "evidence_url": (
            "https://opendata-download-hydroobs.smhi.se/api/version/latest/"
            "parameter/4/metadata.json ; "
            "https://www.smhi.se/data/om-smhis-data/villkor-for-anvandning"
        ),
        "evidence_quote": (
            '"Egenskaper: Daglig uppgift om vattendragstemperaturer i vattendrag i '
            'Sverige." | "Kvalitetskoder: Gr\u00f6n (G) = Kontrollerade och godk\u00e4nda '
            'v\u00e4rden. Gul (Y) = Grovt kontrollerade v\u00e4rden, misst\u00e4nkta eller '
            'aggregerade v\u00e4rden. Orange (O) = Okontrollerade v\u00e4rden" | "Med v\u00e5ra '
            '\u00f6ppna data f\u00f6ljer licensvillkoren Creative commons Erk\u00e4nnande 4.0 SE."'
        ),
        "verification_status": (
            "daily cadence, quality legend, day-label convention and licence "
            "verified live; the aggregation statistic is unverified"
        ),
    },
    {
        "provider": "hubeau",
        "country": "France",
        "product": (
            "Hub'Eau temperature API v1, endpoint /api/v1/temperature/chronique "
            "(continuous water-temperature chronicles), field resultat"
        ),
        "statistic_documented": (
            "continuous sub-daily measurement, NOT a daily statistic: Hub'Eau "
            "describes the endpoint as 'chroniques de temp\u00e9ratures en continu', and "
            "each record carries both date_mesure_temp and heure_mesure_temp"
        ),
        "statistic_as_parsed": (
            "project-derived daily mean: parser keeps code_qualification == 1 rows "
            "and resamples to a calendar-day mean"
        ),
        "aggregation_interval": (
            "per-measurement timestamps (date + hour, e.g. 2013-05-17 01:00:00); "
            "no provider daily statistic"
        ),
        "day_boundary_tz": (
            "unverified: the API returns local French date and hour fields with no "
            "offset, and no day-boundary statement was found"
        ),
        "quality_codes_kept": (
            "Sandre code 1 only (Correcte); live examples label code 4 as "
            "'Non qualifi\u00e9'"
        ),
        "quality_codes_dropped": (
            "codes 2 (incorrect), 3 (uncertain) and 4 (unqualified); the audited "
            "long chronicles carried only code 4, so no station-year qualified"
        ),
        "license": (
            "Licence Ouverte / Open Licence Etalab; free and free-of-charge reuse "
            "including commercial use, author must be cited"
        ),
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "cite the author of the dataset (Hub'Eau / the producing agencies) and "
            "the Etalab open licence"
        ),
        "acquisition_route": (
            "https://hubeau.eaufrance.fr/api/v1/temperature/chronique?code_station="
            "<id>&date_debut_mesure=<date>&date_fin_mesure=<date>"
            "&code_qualification=1&size=20000&page=1&sort=asc (split into year "
            "windows because page*size must stay <= 20000); no key"
        ),
        "evidence_url": (
            "https://hubeau.eaufrance.fr/page/api-temperature-continu ; "
            "https://hubeau.eaufrance.fr/page/conditions-generales"
        ),
        "evidence_quote": (
            '"chronique, permettant de rechercher les chroniques de temp\u00e9ratures en '
            'continu dans les cours d\'eau mesur\u00e9es aux diff\u00e9rentes stations." | '
            '"date_mesure_temp" : "2013-05-17", "heure_mesure_temp" : "01:00:00", '
            '"resultat" : 13.329, "code_qualification" : "4", '
            '"libelle_qualification" : "Non qualifi\u00e9" | "La r\u00e9utilisation des Jeux '
            'de donn\u00e9es est r\u00e9gie par la licence ouverte Etalab ... librement et '
            'gratuitement utilisables et r\u00e9utilisables, y compris dans un but '
            'commercial. L\'utilisateur de ces donn\u00e9es doit n\u00e9anmoins veiller \u00e0 citer '
            'l\'auteur des Jeux de donn\u00e9es."'
        ),
        "verification_status": (
            "continuous sub-daily semantics, qualification field and licence "
            "verified live; the full Sandre code table and the day boundary are "
            "unverified (sandre.eaufrance.fr was unreachable at retrieval time)"
        ),
    },
    {
        "provider": "uk_ea",
        "country": "United Kingdom (England)",
        "product": (
            "Environment Agency Hydrology API measure "
            "'<station>-temp-m-86400-C-qualified' (readings.json), i.e. the "
            "provider daily mean temperature series"
        ),
        "statistic_documented": (
            "daily mean: the measure resource is labelled 'Daily mean Temperature "
            "(\u00b0C) time series', period 86400, periodName 'daily', valueType "
            "'mean', valueStatistic comment 'Measurements which represent the mean "
            "value over the measurement period.'"
        ),
        "statistic_as_parsed": (
            "daily mean read directly from the provider measure (no re-aggregation); "
            "the parser also derives a daily mean from the 15-minute series only for "
            "a QC diagnostic, never for a panel"
        ),
        "aggregation_interval": (
            "86400 s (daily); one value per calendar date, dateTime at T00:00:00 "
            "with no offset"
        ),
        "day_boundary_tz": (
            "UK local time as published (no offset emitted, no shift applied by the "
            "parser); no explicit timezone statement in the reference document"
        ),
        "quality_codes_kept": (
            "no per-reading quality filter: the parser reads dateTime and value only "
            "and marks 'Missing' days as dropped"
        ),
        "quality_codes_dropped": (
            "the provider's per-reading 'quality' (Good, Estimated, Suspect, "
            "Unchecked, Missing), 'completeness' (Complete, Incomplete) and 'qflag' "
            "(Edited, WithinRating, NoRating, ...) fields are not carried into the "
            "daily panel"
        ),
        "license": (
            "Open Government Licence v3.0 (the API meta returns licenseName 'OGL 3')"
        ),
        "redistribution_allowed": "true",
        "derived_output_allowed": "true",
        "required_citation": (
            "attribute the Environment Agency and the Open Government Licence v3.0"
        ),
        "acquisition_route": (
            "discover measures at https://environment.data.gov.uk/hydrology/id/"
            "measures.json (paged), then GET https://environment.data.gov.uk/"
            "hydrology/id/measures/<measure_id>/readings.json?mineq-date=<start>"
            "&max-date=<end>&_limit=2000&_offset=<n> ; no key"
        ),
        "evidence_url": (
            "https://environment.data.gov.uk/hydrology/id/measures/"
            "bbaa85be-3a06-4d2b-b5ad-7f1f55b6554d-temp-m-86400-C-qualified.json ; "
            "https://environment.data.gov.uk/hydrology/doc/reference"
        ),
        "evidence_quote": (
            '"label": "Daily mean Temperature (\u00b0C) time series for Evesham", '
            '"period": 86400, "periodName": "daily", "valueType": "mean" | '
            '"Measurements which represent the mean value over the measurement '
            'period." | "quality ... Good Estimated Suspect Unchecked Missing" | '
            '"licenseName": "OGL 3"'
        ),
        "verification_status": (
            "daily-mean statistic, measured qualifiers and licence verified live; "
            "the explicit timezone statement is unverified"
        ),
    },
]

# --------------------------------------------------------------------------
# Manifest provider -> acquisition-map labels
# --------------------------------------------------------------------------
MANIFEST_PROVIDER_PRODUCT = {
    "usgs": (
        "United States",
        "USGS NWIS daily values (DV), parameterCd=00010, statCd=00003 (daily mean)",
        "GET https://waterservices.usgs.gov/nwis/dv/?format=json&sites=<site_no>"
        "&parameterCd=00010&statCd=00003&startDT=<start>&endDT=<end> ; no key",
    ),
    "arso": (
        "Slovenia",
        "ARSO HIDARHIV surface-water daily archive, 'temp. vode (\u00b0C)' column",
        "GET https://vode.arso.gov.si/hidarhiv/pov_arhiv_tab.php?p_vodotok=<river>"
        "&p_postaja=<station_id>&p_leto=<year>&b_arhiv=Prika\u017ei, one request per "
        "station-year ; no key",
    ),
    "chmi": (
        "Czechia",
        "CHMI open-data measured_temperature H_<station>_OT_<year>.json "
        "(tsConID TO, 10-minute instantaneous values, scanned by 2026-10-12 as "
        "declared by metadata/meta2.json)",
        "GET https://opendata.chmi.cz/hydrology/historical/data/measured_temperature/"
        "H_<station>_OT_<year>.json ; no key",
    ),
    "foen": (
        "Switzerland",
        "FOEN/BAFU water observations GraphQL data_1day_mean, parameterName='WT'",
        "POST https://data.bafu.admin.ch/api GraphQL data_1day_mean query per "
        "station-year window ; no key",
    ),
    "gkd_bayern": (
        "Germany (Bavaria)",
        "GKD Bayern daily water-temperature archive (wertart=tmw, geprueft=1), "
        "column 'Mittelwert'",
        "POST https://www.gkd.bayern.de/de/downloadcenter/enqueue_download with "
        "wertart=tmw&geprueft=1 then GET the deeplink + '&dl=1' ; no key",
    ),
    "lubw": (
        "Germany (Baden-W\u00fcrttemberg)",
        "LUBW Daten- und Kartendienst 'Daten der Online-Messstationen' export table "
        "(Tagesmittelwert of Temperatur)",
        "GET https://umweltdaten.lubw.baden-wuerttemberg.de/w/online-messstationen, "
        "read the ephemeral workbook id/hash, then GET /workbooks/<id>,hash=<hash>/"
        "views/u6gf2s5q46r310DCsAlb/tableData?offset=&limit= ; no key",
    ),
    "nve_hydapi": (
        "Norway",
        "NVE HydAPI parameter 1003 water temperature, ResolutionTime=1440 "
        "(daily mean)",
        "GET https://hydapi.nve.no/api/v1/Observations?StationId=<ids>&Parameter=1003"
        "&ResolutionTime=1440&ReferenceTime=<start>/<end> with X-API-Key header",
    ),
    "rws_waterwebservices": (
        "Netherlands",
        "Rijkswaterstaat DDAPI20 OphalenWaarnemingen, Grootheid T / Compartiment OW "
        "/ WaardeBewerkingsMethode NVT / ProcesType 'meting' (raw instantaneous)",
        "POST https://ddapi20-waterwebservices.rijkswaterstaat.nl/"
        "ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen with Locatie/Grootheid/"
        "Periode JSON ; no key",
    ),
    "syke": (
        "Finland",
        "SYKE Hydrologiarajapinta 1.2 OData LampoPintavesi (morning surface-water "
        "temperature reading)",
        "GET https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.2/odata/"
        "LampoPintavesi?$filter=Paikka_Id eq <id> ; no key",
    ),
}


def build_dictionary() -> None:
    with OUT_DICTIONARY.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DICTIONARY_COLUMNS)
        writer.writeheader()
        for row in PROVIDERS:
            missing = set(DICTIONARY_COLUMNS) - set(row)
            if missing:
                raise ValueError(f"{row['provider']} is missing {sorted(missing)}")
            if not row["evidence_quote"] or not row["evidence_url"]:
                raise ValueError(f"{row['provider']} has no evidence")
            writer.writerow({key: row[key] for key in DICTIONARY_COLUMNS})


def build_acquisition() -> None:
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    unknown = sorted({row["provider"] for row in manifest} - set(MANIFEST_PROVIDER_PRODUCT))
    if unknown:
        raise ValueError(f"manifest providers without an acquisition route: {unknown}")
    with OUT_ACQUISITION.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ACQUISITION_COLUMNS)
        writer.writeheader()
        for row in manifest:
            country, product, route = MANIFEST_PROVIDER_PRODUCT[row["provider"]]
            writer.writerow(
                {
                    "network_id": row["network_id"],
                    "provider": row["provider"],
                    "country": country,
                    "product": product,
                    "acquisition_route": route,
                    "manifest_path": row["input_path"],
                    "source_root": row["source_root"],
                    "split_role": row["split_role"],
                    "n_stations": row["n_stations"],
                    "n_station_years": row["n_station_years"],
                }
            )
    print(f"acquisition rows: {len(manifest)}")


def main() -> None:
    build_dictionary()
    build_acquisition()
    verdicts = {
        "daily mean": ["usgs", "foen", "gkd_bayern", "nve_hydapi", "uk_ea"],
        "daily mean documented, exact column partially verified": ["lubw"],
        "not a daily mean": ["chmi", "rws_waterwebservices", "syke", "hubeau"],
        "daily value documented, aggregation unverified": ["smhi"],
        "unverified": ["arso"],
    }
    print(f"dictionary rows: {len(PROVIDERS)} -> {OUT_DICTIONARY}")
    for label, providers in verdicts.items():
        print(f"  {label}: {', '.join(providers)}")


if __name__ == "__main__":
    main()

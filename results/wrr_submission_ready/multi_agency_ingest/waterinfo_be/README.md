# waterinfo.be (Flanders, Belgium) -- multi-agency transport ingest

Provider: Vlaamse waterbeheerders / Vlaamse Milieumaatschappij (VMM) via the waterinfo.be
KiWIS (KISTERS WISKI) web service.

## Statistic used

- provider daily mean, degrees C: KiWIS ts_name 'DagGem' (daggemiddelde) of parametertype WT, ts_unitname 'degree Celsius', ts_unitsymbol '°C'; one value per calendar day, KiWIS timestamp is local clock 01:00 with the Brussels UTC offset of that date
- the provider's own daily statistic is used as published; no sub-daily value is aggregated
  into the panel
- quality assurance: `provider_published_unqualified` -- the KiWIS values payload carries no quality flag ('Timestamp,Value' only) and no provider statement that these series are checked/approved was found on https://www.waterinfo.vlaanderen.be/ (disclaimer read 2026-10-12); the umbrella disclaimer states the data are offered for informative, non-commercial use
- licence/terms: https://www.waterinfo.vlaanderen.be/default.aspx?path=NL/Algemene_Info/Disclaimer

## Retrieval status (read this before using the panel)

- catalogued daily-mean water-temperature series: 408
- series in the raw cache (used here): 150
- series not retrieved: 258
- stopped by the provider credit limit: `None`
- resume with: `python3 scripts/260_multi_agency_be_es_ingest.py --provider be`

The KiWIS service answers HTTP 429 with `exceptionCode='AuthCreditLimit'` once the per-IP
credit quota is exhausted. The ingest stops at that point, keeps the raw cache and resumes
from it on the next run, so nothing is downloaded twice.

## Panel yield

- stations retrieved: 133
- stations with >= 4 complete calendar years: 0
- maximum complete calendar years seen: 3
- networks emitted: 0

**UNDER-DELIVERY in the retrieved tranche: no station of the retrieved Flemish daily-mean series reaches the frozen >= 4 complete calendar years, so the provider contributes no network yet. This is a reported failure, not a silent drop.**

only the retrieved tranche is evidence; the unretrieved series were blocked by the provider credit quota and must be fetched before any provider-level claim is made

The frozen complete-calendar-year definition needs >= 365 (366) QC-passing values, i.e. a
gap-free year. The retrieved Flemish daily means have scattered single missing days, which is
why so few years qualify; `ingest.json` carries the shortfall distribution under
`complete_year_gap_evidence`.

## Files

- `stations.csv` -- panel rows (may be header-only when no network reaches the floor)
- `stations_all.csv` -- every retrieved station with class, rule and completeness columns
- `networks_manifest.csv`, `networks/<network_id>/daily_wide_temperature.csv`
- `networks_not_eligible.csv` -- per-watercourse census including the reason nothing was emitted
- `daily_long_qc.csv.gz` -- QC-passing long table
- `raw_cache/` -- station list, series catalogue, per-series raw JSON (gzip), watercourse census
- `download_failures.csv` -- series that failed or were cut off by the credit limit

## Reproduction

```bash
python3 scripts/260_multi_agency_be_es_ingest.py --provider be
# re-process a partial ingest without downloading:
python3 scripts/260_multi_agency_be_es_ingest.py --provider be --offline
```

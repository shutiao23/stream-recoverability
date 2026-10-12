# Spain (`roea_es`) -- what is in this directory and why

Two different things live here; do not conflate them.

1. **CEDEX / ROEA *Anuario de Aforos* -> infeasible** (`INFEASIBLE.md`, `raw_cache/evidence.json`):
   the national aforo archive publishes discharge, reservoir, canal, evaporation and
   water-quality-sampling tables, but no water-temperature series at all.
2. **SAIH Ebro -> the Spanish series that do exist** (`stations.csv`, `networks*/`,
   `daily_long_qc.csv.gz`, `ingest.json`): the Confederacion Hidrografica del Ebro (CHE)
   automatic hydrologic information system publishes a *consolidated daily* water
   temperature (column `MEDIA (oC)`, i.e. a provider daily mean) through
   `https://www.saihebro.com/api/datos-historicos`. The `provider` column of every row is `saih_ebro`, **not** `roea_es`:
   the directory name was fixed by the ingest contract and is kept for the coordinator's
   file layout, but no CEDEX/ROEA value is present anywhere in the panel files.

## Headline counts (from `ingest.json`)

- river stations with a daily water-temperature signal: 3
- of those, stations with >= 4 complete calendar years: 2
- networks emitted: 1
- complete station-years in the emitted panel: 18

## Caveats the coordinator must read before sealing

- Only three SAIH Ebro river stations publish a consolidated daily water-temperature signal (A017 Rio Cinca en Fraga, A027 Rio Ebro en Tortosa, A263 Rio Ebro en Gelsa); a fourth TEMPA station is a reservoir (E104 Embalse de Nagore) and is dropped by protocol rule 2.
- Complete-year floor bites: A263 (Ebro at Gelsa) has only 3 complete calendar years, so the river-watercourse network 'Ebro' does not reach >= 2 stations x >= 4 complete years. The only grouping that does is the flagged basin-level fallback 'saih_ebro_ebro_basin' (A017 + A027), whose stations are on different rivers hundreds of km apart.
- A027 'Rio Ebro en Tortosa' sits at the tidal limit of the Ebro; if the coordinator reads protocol rule 2 strictly (no estuary-influenced sites) the Spanish panel becomes empty.
- The provider publishes no coordinates in these API responses, so latitude/longitude are blank; station identity is the CHE station code and the river name comes from the station label ('Rio <name> en <place>').
- The daily file also carries 'MINIMO (oC)' and 'MAXIMO (oC)' with intra-day timestamps; the ingest QC records the share of days whose min/max timestamps fall inside the stamped calendar day (evidence that the daily stamp is the calendar day).
- the ingested series come from the 'diario' (consolidated daily) endpoint of the provider's 'Datos historicos' API, not from the real-time feed, but no fetched page states that these consolidated values are checked/approved. The provider's own notice (https://www.saihebro.com/info/datos-provisionales-ebro) says real-time data are 'de naturaleza provisional hasta que sean revisados, depurados y validados por el Servicio de Hidrologia'; the human-facing 'Datos historicos' page (https://www.saihebro.com/datos/historicos) asks for a (free) user account, while the API endpoint answered without credentials at retrieval time.
- No frozen-screen endpoint, retention, model or score is computed by this script (ingest and QC only).

## Reproduction

```bash
python3 scripts/260_multi_agency_be_es_ingest.py --provider es
```

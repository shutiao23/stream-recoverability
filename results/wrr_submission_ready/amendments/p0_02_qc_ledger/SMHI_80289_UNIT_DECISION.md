# SMHI station 80289 — unit/coding decision

## Evidence

- Raw file: `multi_agency_ingest/smhi/raw_cache/station_80289.csv`
- Header declares `Parameternamn;Enhet` / `Vattendragstemperatur;°C`
- All 1,878 values lie in 27325–29705 (median 28065)
- Neighbouring SMHI stations with the same header schema store ordinary °C
  (e.g. 80178: 7–9 °C)
- Catalogue unit quote is also °C; no SMHI field documents a 0.01 °C or mK scale

## Decision (F01)

**Quarantine the entire station series as non-temperature.** Do not apply a
guessed rescale (÷1000, −27315, etc.). Remove 80289 from complete-year
eligibility, donor pools, and transport networks until SMHI confirms the
encoding in writing.

## Scope

Among 176 `station_daily` files, **only 80289** fails the (−5, 50) °C band.
Earlier sanitize tallies that blanked ~1e6 SMHI cells were a bug: `station_id`
was treated as a temperature column. That bug is fixed in
`scripts/274_wrr_sanitize_confirmation_panels.py`.

## Network impact

`smhi_catchment_86000` listed 80289 with 4 complete years. After quarantine the
network must be rebuilt from remaining stations or dropped if it falls below
two eligible stations.

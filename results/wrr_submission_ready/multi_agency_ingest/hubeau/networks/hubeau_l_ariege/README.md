# hubeau_l_ariege (Hub'Eau river-temperature network)

- provider: `hubeau` (Hub'Eau / Eaufrance, France)
- river: L'Ariège
- retrieved_utc: 2026-10-12T11:38:46Z
- stations in panel: 3 (all with >= 4 complete calendar years)
- complete station-years: 27
- quality_assurance: provider_published_unqualified
- accepted Sandre codes: 4

## Files

- `daily_wide_temperature.csv` - wide daily panel, first column `date`, one
  column per station id, blank where a daily value was not formed.
- `stations.csv` - per-station provenance, Sandre code counts, QC day counts,
  complete calendar years, quality labels.
- `ingest.json` - machine-readable record for this network.

## Measurement provenance

Daily value = arithmetic mean of the station's single accepted Sandre code
observations within one calendar day, using only days with >= 4 acceptable observations; days below that floor are
dropped and counted (never interpolated). Complete calendar year = every calendar
day of an ended year carries a daily value.

Sandre code 1 = `quality_checked` (Correcte); code 2/3 are never ingested;
code 4 = `provider_published_unqualified` (Non qualifie) - a lower-assurance
subset that must be reported as such. No station mixes codes.

No frozen-screen performance was computed on this panel.

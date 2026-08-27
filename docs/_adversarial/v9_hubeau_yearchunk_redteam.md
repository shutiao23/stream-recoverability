# Red team: Hub'Eau year-chunk daily derivation

Date: 2026-08-26
Target: `src/stream_recoverability/data/hubeau_temperature.py`, `scripts/62_hubeau_daily_from_chronique.py`
Status: parent-reviewed after implementation. Not a result.

## Attacks

1. **Pagination 20k cap.** Hub'Eau returns HTTP 400 when `page * size > 20000`. The previous walk followed `next` until page 5 at size 5000. Year-chunk must never emit `page>=2` on a 20000-size window. Tests lock `page=1` and `date_debut_mesure`.
2. **Empty cache poisoning.** The old writer saved empty CSVs on connection reset, so later runs "succeeded" with 0 days. Year-chunk cache unlinks empty files and does not write empty success caches.
3. **Truncated `_daily.csv` reuse.** Old Rhône/Saône files are ~1–2 years. New cache suffix `_daily_yearchunk.csv` ignores them.
4. **Invented Europe years.** Date windows come from public `date_mesure_temp` spans. Empty windows return no rows. Script still sets `europe_daily_years_invented: false` and `countable_toward_t8` only after 3 stations / 8 overlap years / 1825 concurrent days.
5. **Loire last-check.** Script still filters `last_check_site_ids()` and `exclude_loire=True`. Loire remains unopened.
6. **Name cluster ≠ T8.** Ranking by station count does not count a river until `complete_enough`.
7. **HTTP 400 not retried as success.** `get_json` still raises on 400. The fix is not to treat 400 as empty data.

## Parent merge

Keep year-chunk. Do not count Hub'Eau toward T8 until overlap.csv shows `complete_enough`. Do not download Loire to "rescue" Europe.

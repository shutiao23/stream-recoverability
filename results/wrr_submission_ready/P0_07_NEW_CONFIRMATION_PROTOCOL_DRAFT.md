# P0-07 — New independent confirmation protocol (draft)

Status: **sealed, not scored**. Hashes live in
`P0_07_NEW_CONFIRMATION_SEAL.json` (`scored: false`). Do not score leftover
opened-wave ingest. New independent primary-panel data must meet the floors
below before a one-time score.

## Purpose

Replace executed-but-invalid USGS / multi-agency scores with a single new
confirmation under repaired data QA, reconstructability contracts, and
panel-isolated quality gates.

## Design floors (locked before recruitment completes)

- ≥30 networks, ≥3 providers, ≥3 climate/hydrology contexts
- ≥2 stations per network; ≥4 complete years per station after QA
- Primary panel only for the gate; secondary strata labelled and non-rescuing
- Power: use development network-cluster variance; 30 networks is a floor, not
  a sufficiency proof

## Pre-declared success rule (must seal before unblinding)

On the primary panel at 70% retention of the **full candidate denominator** and
0.5 °C tolerance, treating reconstruction failure as failure:

1. Δ ≤ −1.0 percentage points
2. 95% network-clustered CI upper bound < 0
3. ≥2 providers same direction
4. Primary quality-checked-only subset agrees (same panel_role, then assurance)

## Required seals

- Method freeze JSON + certificate joblib sha256 + screen.py / frontier.py /
  estimators.py sha256
- Environment lock (`constraints-freeze-certificate.txt` or frozen image digest)
- Input manifest with on-disk existence + sha256 (preflight must fail if absent)
- Prior-access ledger covering CSV / Parquet / JSON and `station_id` / `site_id`

## Failure 收口

If independence or QA floors fail → keep
`[pending — 探索期数据，不可写入结论]`.
If floors met but effect fails → report transport failure and narrow claims;
consider Journal of Hydrology positioning. Do not retune thresholds after score.

# Source provenance v3 — Jinsha quality request

Status: incomplete. This file records what is missing, not what has been obtained.

The supplied B1, S2, and P3 daily $T$, $F$, and $L$ series are complete for 1 January 2006--31 December 2020. Completeness is not a quality pedigree.

## Missing, required before Jinsha can be confirmatory truth

- Yearbook volume, year, and page for each station-variable.
- Sensor or logger model, resolution, and calibration dates.
- Time zone and hydrological-day cut-off used to form the published daily mean.
- Per-value quality codes, estimated/provisional flags, and station-history notes.
- A written statement that the published daily temperatures were not interpolated or manually smoothed.
- Dates of any station relocation, datum change, or instrument replacement.

## Current analysis rule

Until those items exist, Jinsha is an exploratory context network. `observed_unflagged` remains an analysis-eligibility flag, not provider approval. Artificial masks hide published values; they do not prove those values were raw sensor samples. If the data holder cannot supply the list above, the confirmatory centre of gravity stays on public USGS networks.

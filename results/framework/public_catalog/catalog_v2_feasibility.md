# Catalog v2 feasibility (metadata only)

This is a station-year inventory, not a recovery score. Daily temperature
values were not downloaded. Sealed temperatures were not opened. The 12
already-downloaded rivers and Jinsha / Chattahoochee were not remapped
into sealed. Loire and Swiss Aare-Rhine are **not** counted toward T8 or
the non-North-America sealed floor; no European daily years were invented.

v1 grouped by river name + raw HUC prefix and required **every** listed
station to share one window. One short or shifted station killed the
cluster. That rule still yields **31** networks at 4 stations / 8 years.

v2 keeps stream sites with catalog span ≥ 6 years, then takes the largest
subset whose interval intersection is at least T years. Candidate starts
are station begin dates. Official USGS HUC prefixes are used (a missing
leading zero on 7/9/11-digit codes is restored). `grouping=huc8_only`
ignores exact river-name match and is **not** mixed into name-based counts.

- Target independent networks remains **150**. That target is not met.
- Best honest public-USGS count (name+HUC2, 3 stations, 8-year subset): **98**.
- That honest count is still **below 100**. Do not paper over the gap with Loire or FOEN.

## Counts

- v1-style 4 stations / 8 years (whole-group overlap): 31
- v2 name+HUC2 3 stations / 8 years: 98
- v2 name+HUC2 3 stations / 6 years: 112
- v2 name+HUC4 3 stations / 8 years: 99
- v2 HUC8-only 3 stations / 8 years (exploratory, not name-based): 166

## Sensitivity (not the honest headline)

- v2 name+HUC2 4 stations / 8 years: 44
- v2 name+HUC8 3 stations / 8 years: 83
- name+HUC8 is a stricter same-watershed name match; it is still public USGS only.

## What is not a network

- HUC8-only groups can mix differently named streams in one watershed.
- Common river names inside one official HUC2 can still collide.
- Catalog overlap is not concurrent daily completeness.
- Loire Hub'Eau names and Swiss FOEN locations have no public daily-year span here.

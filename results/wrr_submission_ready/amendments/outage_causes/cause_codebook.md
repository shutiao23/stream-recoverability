# Observed outage-cause codebook (USGS NWIS daily values, parameter 00010)

Every definition quoted below is USGS's own text, taken from the response that the
USGS daily-value service generated for this study. The request URL is given so the
quote can be reproduced; the raw response is cached under `raw_cache/` with a
SHA-256 in `raw_cache/manifest.csv`.

## What was retrieved

- Service: `https://waterservices.usgs.gov/nwis/dv/` (RDB format), `parameterCd=00010`,
  `statCd=00003` (mean), one request per USGS station covering its
  incomplete years.
- Series metadata: `https://api.waterdata.usgs.gov/ogcapi/v0/collections/time-series-metadata/items`.
- Stations requested: 200; stations with a daily-value response: 200; stations with a declared 00010 series catalog: 200.
- A second daily-value retrieval per station **without** `statCd`, so every 00010 daily
  statistic is returned, and a series-catalog retrieval
  (`https://waterservices.usgs.gov/nwis/site/?format=rdb&sites=<site>&seriesCatalogOutput=true&parameterCd=00010`)
  that declares the begin/end coverage of each 00010 daily time series.
- Modern-API series metadata was also cached for the 109 stations where unauthenticated bulk access allowed it;
  it agrees with the catalog within one day at 104 of 109 compared stations and is used only as a cross-check.
- First retrieval stamp seen in the RDB headers: 2026-10-12 06:34:41 -04:00	(natwebvaas01) (89 distinct stamps), window 2026-10-12 06:34:41 to 2026-10-12 06:44:01.

## Parameter and statistic

| code | USGS definition | source |
|---|---|---|
| parameter 00010 | `Temperature, water` / `Temperature, water, degrees Celsius`, unit `deg C` | https://api.waterdata.usgs.gov/ogcapi/v0/collections/parameter-codes/items?f=json&id=00010 |
| statistic 00003 | `MEAN` / `MEAN VALUES` | https://api.waterdata.usgs.gov/ogcapi/v0/collections/statistic-codes/items?f=json&id=00003 |

## The two code blocks the RDB header carries

Each daily-value RDB response contains both of the following blocks verbatim, and only
for the codes that occur in that response:

```
# Data-value grade codes included in this output:
#     4    Incomplete or Partial Aggregated Record
#
# Data-value qualification codes included in this output:
#     A  Approved for publication -- Processing and review completed.
#     P  Provisional data subject to revision.
```

The exact request that returns the block above is
`https://waterservices.usgs.gov/nwis/dv/?format=rdb&sites=<site>&parameterCd=00010&statCd=00003&startDT=<y0>-01-01&endDT=<y1>-12-31`;
every such URL is listed per file in `raw_cache/manifest.csv`.

A *grade* code describes how the daily aggregate was formed, not why anything is
missing. A *qualification* code describes the status of the value that is present.
Neither is a cause of absence.

### Data-value grade codes observed

| code | USGS definition | records |
|---|---|---:|
| `[4]` | Incomplete or Partial Aggregated Record | 1,004 |

### Data-value qualification codes observed

| code | USGS definition | records |
|---|---|---:|
| `A` | Approved for publication -- Processing and review completed. | 822,829 |
| `P` | Provisional data subject to revision. | 502 |
| `R` | Records for these data have been revised. | 398 |
| `e` | Value has been estimated. | 13 |
| `(blank)` | empty code cell (the day exists only under a sibling time series) | 9,652 |
| `A:R` | whole cell: qualification token plus another token | 398 |
| `A:e` | whole cell: qualification token plus another token | 13 |

The code cell is a compound string: `A:[4]` means qualification `A` plus grade `[4]`.
Observed shapes: `(blank)`, `A:R`, `A:e`, `A`, `P`
combined with grade codes `[4]`.

## Cause-naming codes: what did and did not appear

NWIS remark vocabularies name causes (`Mnt`, `Eqp`, `Ice`, `Dis`, `Ssn`, `***` and
others). The retrieval below looked for those tokens on every record returned for
parameter 00010 daily mean at the 200 USGS stations of the incomplete-year population.

| token | records observed |
|---|---:|
| `Mnt` | 0 |
| `Eqp` | 0 |
| `Ice` | 0 |
| `Dis` | 0 |
| `Ssn` | 0 |
| `***` | 0 |
| `Rat` | 0 |
| `Fld` | 0 |
| `Dry` | 0 |
| `Bkw` | 0 |

**No cause-naming token was observed.** The legacy USGS help page that enumerated the
data-value qualification vocabulary (`https://help.waterdata.usgs.gov/code/qual_cd_query`)
now serves a client-rendered Code Dictionary that documents parameter codes and observed
properties only; USGS's note on that migration is at
https://waterdata.usgs.gov/blog/wdfn-metadata/ . Because no reachable USGS page in this
environment rendered the definition strings for the cause-naming tokens, this study
assigns them **no meaning and no count**. What is asserted is the negative: they do not
occur in the retrieved records.

## Why a missing day usually has no code at all

The daily-value service attaches a qualification code to a *record*. A day the provider
has no value for is simply absent from the response. The retrieval confirms both halves
of that:

1. Days with a value carry a code (`A`, `P`, or those with a grade).
2. Days with no value produce no row, and therefore no code, at every station-year in
   scope, including the 366-day all-missing years.

A code can still be attached to a record whose value cell is empty when a site has more
than one daily time series for the same parameter and statistic (for example
`... (Mean), TOP` and `... (Mean), BOTTOM`); the empty cell belongs to the series that
had no value that day. This was observed at station 0208114150 and is why the unit of
this analysis is the day, not the row.

## What the codes can and cannot support

| question | supported? |
|---|---|
| Which days the provider considers approved vs provisional | yes, per day |
| Which observed days are incomplete or partial aggregates (`[4]`) | yes, per day |
| Which missing days were caused by maintenance or equipment failure | no |
| Which missing days were ice-affected | no |
| Why a station-year has no records at all | no; only whether the day falls inside the
  declared coverage interval of a 00010 daily series (`begin_date`/`end_date` from the
  series catalog, which is coarse: first and last record of the series) |

## Same parameter, other statistics

The second retrieval dropped the statistic filter. Across the USGS stations in scope, USGS
publishes 00010 daily values under more than one statistic, and the RDB header names them in
the provider's own words, for example:

- 35 distinct series descriptions were observed.
- Statistic codes seen in the catalogs: `00001`, `00002`, `00003`, `00004`, `00005`, `00008`, `00011`.
- Examples, in USGS's wording: `Temperature, water, degrees Celsius (Mean)`; `Temperature, water, degrees Celsius (Mean), Channel WQ`; `Temperature, water, degrees Celsius (Mean), Elevation:      1.000`; `Temperature, water, degrees Celsius (Mean), Hobo`; `Temperature, water, degrees Celsius (Mean), Instream`; `Temperature, water, degrees Celsius (Mean), [(2)]`; `Temperature, water, degrees Celsius (Mean), [Mean Water Temperature]`; `Temperature, water, degrees Celsius (Mean), [Right Bank Pump Stand]`; `Temperature, water, degrees Celsius (Mean), [WQM]`

A day on which the target statistic (00003, `MEAN`) is absent but another 00010 daily
statistic is present is therefore an archive-side loss, not a provider outage. Those days
are counted separately and are never attributed to maintenance or equipment failure.

The `qualifier` field description USGS publishes for the same data through the modern API
is: "This field indicates any qualifiers associated with an observation, for instance if a
sensor may have been impacted by ice or if values were estimated." — i.e. it qualifies an
observation. Source:
https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/queryables?f=json


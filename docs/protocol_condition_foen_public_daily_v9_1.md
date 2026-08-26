# v9.1 condition-satisfied note: FOEN public dated daily path

Frozen on 2026-08-26, before any FOEN temperature-value query.

## Narrow condition that is now satisfied

The v9/v9.1 Swiss exclusion was conditional: Swiss networks could not occupy
the non-North-America sealed seats **until daily values were public and dated**.
FOEN now documents and serves an unauthenticated GraphQL table named
`data_1day_mean`; water temperature is parameter `WT`, rows carry timestamps,
units, and release state. The official sources are:

- https://data.bafu.admin.ch/api
- https://api.data-platform.cloud.bafu.admin.ch/en/dataproduct-water-observations

The W6 audit requested station metadata and, for station 2016 only, seven WT
timestamps/release states from 2025-01-01 through 2025-01-07. The GraphQL
selection omitted `value`. All seven rows were release state 2. This establishes
public, dated, daily API availability; it does not establish an eight-year
qualified station or network.

Because station 2016 was used for that timestamp probe, the complete prospective
Aare metadata network `foen_aare_aaregebiet` is permanently
`never_sealed`/`development_burned`. Moving the probe station out of the group or
retokenizing the group later is forbidden.

## What this unlocks—and what it does not

This condition satisfaction unlocks only a **prospective role assignment before
temperature values are requested**. It does not lower the three-station floor,
the eight common qualified-year rule, the 300-distinct-days rule, the T2
Spearman/calibration gates, or the network-CI floor.

The metadata lock contains eleven accent-normalized `riverName × catchmentName`
candidates drawn from the existing FOEN water-temperature location inventory:

- one burned Aare network containing station 2016;
- ten previously unprobed networks assigned prospective `sealed` roles;
- zero networks claimed qualified and zero networks currently countable toward
  T8.

The ten sealed IDs are Doubs, Emme, Inn, Linth, Reuss, Rhein, Rhône/Rhone,
Simme, Thur, and Ticino under the `foen_*` identifiers in the canonical split.
Accent normalization merges `Rhône` and `Rhone`; it does not count the same
river twice.

Locked files:

- `configs/foen_prospective_catalog_v1.yaml`
- `configs/foen_prospective_split_v1.yaml`
- `results/framework/public_catalog/foen_prospective_split_v1.csv`
- split seed: `20260826`
- split SHA-256:
  `4405cf690ccf9d9b62a8dfa76d2d1d74806e662835bff0043ee9fe1e5619ae59`
- catalog SHA-256:
  `2e348f571a6e19025d8f6d6aca2dfe55997927b94a608a78baedd89819a78727`

`coverageFrom` and `coverageTo` were not requested by the lock builder and are
not present in the locked metadata table. They cannot be used as a substitute
for daily density or concurrency. River-name/catchment membership and
coordinates are prospective metadata only; connectivity and independence must
be audited after the sealed evaluation is authorized.

## Future byte-custody adaptation (not executed here)

The future value query template is locked but was not executed:

- template: `configs/foen_daily_value_query_v1.graphql`
- template SHA-256:
  `978247efe815a79863e0383a3ae1e8c293642ec245d7205bd13a46b2ec3a446d`
- aggregation/parameter: `data_1day_mean` / `WT`
- provider-side release filter: state 2 or 3
- fixed request interval: 1974-01-01 through 2026-01-01 exclusive
- partition: disjoint calendar-year windows, each below the 10,000-row cap

Before that template is ever executed, adapt the existing custody layer as
follows:

1. add a `LockedFoenCatalog` loader that verifies the catalog hash, canonical
   split hash, query-template hash, exact station membership, and yearly request
   grid;
2. derive role only from the locked split; callers may not supply or override
   `sealed`;
3. stream each HTTP response body directly into a provider-specific write-only
   vault while hashing—do not call `.json()`, inspect row counts, or parse error
   payloads for sealed roles;
4. extend the strict registry whitelist with provider, aggregation,
   query-template SHA, station, year window, byte count, response SHA, and
   `content_parsed: false`; do not permit outcome fields;
5. make empty/HTTP-failed yearly objects explicit custody failures and resume
   only from a matching append-only registry without reopening sealed bytes;
6. leave development/validation FOEN parsing disabled in this source-specific
   lock: the only unsealed Swiss network is already burned and may be used only
   in a separately authorized development path;
7. after the one authorized unseal, apply provider QC and require three stations
   with at least 300 distinct state-2/3 days in each of eight common calendar
   years. Failed candidates attrit; they are not replaced after outcomes are
   seen.

No temperature value was queried, downloaded, parsed, scored, or counted while
writing this note and lock.

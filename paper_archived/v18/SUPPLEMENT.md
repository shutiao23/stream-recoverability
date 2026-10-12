# Supporting information

Material that belongs to the record rather than to the argument: data
provenance, protocol history, the predictions that failed, and the reproduction
path. Nothing here is required to follow the article.

## S1. Data sources

Daily water-temperature series were assembled from nine public providers. All
are open archives; none required a data-use agreement.

| provider | country | role in this study |
|---|---|---|
| ARSO | Slovenia | development |
| CHMI | Czechia | development |
| FOEN | Switzerland | development and reserved |
| GKD Bayern | Germany (Bavaria) | development and reserved |
| LUBW | Germany (Baden-Württemberg) | development and reserved |
| NVE | Norway | development and reserved |
| Rijkswaterstaat | Netherlands | development and reserved |
| SYKE | Finland | development and reserved |
| USGS | United States | development and reserved |

Station coordinates were assembled for all 457 stations: from the providers' own
catalogues already held in the repository for FOEN, CHMI, SYKE, LUBW, GKD
Bayern, NVE and Rijkswaterstaat and for nine USGS gauges; from the USGS NWIS
site service for the remaining 195 United States gauges; and from ARSO's public
`hidro_podatki_zadnji.xml` feed for all 47 Slovenian stations. Every row in
`data/interim/v18_station_coordinates.csv` records its source.

Daily 2 m air temperature is NASA POWER (MERRA-2), 1 January 1981 to 31 August
2026, one point per station at the product's native resolution: 16,679 days for
each of the 457 stations. The v17 programme used a much smaller forcing table
covering 2.3% of development cases; both are retained and §5.7 compares them.

Basin characteristics for the United States subset are from GAGES-II (Falcone,
2011), joined on the eight-digit gauge identifier and matching 140 of 204
eligible stations.

## S2. Quality control and the definition of a network

A *network* is a provider's group of stations on a common river system, which is
the unit at which donor stations are available to one another. Networks are the
clustering unit for every interval in the article, because station-years within a
network share weather, regulation and instrumentation.

Waterbody class was assigned per network from the provider's own naming and an
explicit map; seas, lakes, canals, estuaries and deltas are listed and excluded
rather than averaged into a river result. Reference series are never imputed: a
calendar year with any missing day contributes no truth. Stations with fewer than
four fully observed calendar years are excluded, because the leave-one-year-out
estimator protocol requires them.

The resulting denominator, with every exclusion and its count, is in
`results/v17_fitness/step1_panel/`. The same stations contribute 2,422
station-years with at least 360 daily slots and at least one missing day; those
form the deployment panel of §5.10 and appear in
`results/v18_closure/e2_archive_deployment/real_station_years.parquet`.

## S3. Protocol history

The study was pre-registered in
`results/v17_fitness/step9_freeze/SUCCESS_CRITERION_v17.json` before the reserved
networks were opened on 2026-09-23. Three aspects of that freeze were incomplete
or wrong and are recorded here rather than silently repaired.

**The incumbent's imputed limit was mis-stated.** v17 placed the comparison at a
thirteen-week (91-day) limit attributed to Johnson et al. (2021). The source says
twenty weeks. `frontier.py` now uses 140 days and every artifact that used the
old value was re-run; §5.6 reports the corrected operating point. The direction
of the error flattered the incumbent at that point, so correcting it reduces the
screen's advantage there from 6.2 to 4.4 percentage points.

**The weighting between outage arms was not declared.** The case set mixes an
empirical arm, drawn from the outage geometry the same networks experience, with
a stratified arm built to span the decision space. Their base rates differ by an
order of magnitude. The pre-registered test was run on the pooled set, as
declared; §5.9 reports the decomposition and states that the declared effect is
not met on the empirical arm alone.

**The natural scale of the peak has two values.** Computed over the full eligible
roster it is 1.06 °C; recomputed inside the development case table it is 1.08 °C.
The primary tolerance is 0.50 °C throughout except in cross-metric comparisons,
where each endpoint's scale is recomputed on the same footing. The tolerance
sweep shows the axis ordering is unchanged between 0.25 and 1.0 standard
deviations.

## S4. Predictions that failed

Three predictions were written down before the analyses that tested them and
were not met. All three are in the article; they are gathered here because a
reader looking for them should not have to hunt.

1. **The support-restricted advantage will decay monotonically in the support
   width.** It does not: it is a hump peaking at a 60-day support. (§5.3)
2. **The estimand's own support is the best conditioning set at every support
   width.** It is not: below 30 days a fixed 30-day window beats it. (§5.3)
3. **For the sine-fit phase, two hand-chosen transition windows will beat both
   peak-window overlap and outage length.** They beat peak overlap decisively and
   tie outage length. (§5.3)

Failures 1 and 2 have one cause, which we then measured: the support's location
is itself uncertain, so the conditioning set has to be the support dilated by
that uncertainty. Failure 3 has a related cause: a hand-drawn window is a crude
approximation to an influence function that is spread over half the year.

A fourth statement was **withdrawn** rather than falsified. v17 framed the
standing guidance as getting an ordering backwards. On the guidance's own
estimands it does not; §5.4 reports that a completeness threshold is the correct
axis for the sine-fit mean and within 0.02 AUC of the best for the phase.

## S5. Runs that were discarded

Two defects made specific v17 artifacts unusable and both were repaired before
the reserved panel was opened: outage realizations were seeded from a salted
hash, and worker results were concatenated in completion order. A third affected
the calibration rather than the data: an additive, per-estimator conformal scheme
under-covered because selecting the smallest of several bounds is a winner's
curse. All three are described in `paper/v17/SUPPLEMENT.md`; the affected numbers
were discarded rather than reported alongside the repaired ones.

## S6. Verification

- The case table is byte-reproducible including row order, pinned by a test.
- The v18 endpoint table regenerates the same 51,524 realizations from the same
  deterministic seeds, which is how its rows line up with the v17 case table.
- No feature may read a day the outage hides; enforced in `feature_frame` and
  pinned by a test.
- Every v18 table cell and audited inline number in the article is re-derived
  from the artifacts by `scripts/221_v18_audit_manuscript.py`, which the test
  suite runs; the article carries a machine-readable block of its headline
  numbers that is compared against those artifacts.
- Figure sources are `.drawio` XML and the PDFs are generated from them; a test
  checks that every schematic PDF is newer than its source.

## S7. Reproduction

See `paper/v18/PROTOCOL.md`. Total wall time on 128 cores is about ninety
minutes, of which the NASA POWER download is roughly twenty.

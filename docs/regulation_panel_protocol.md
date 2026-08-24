# Regulation-panel protocol (freeze v1)

## Scope and isolation

This is a new station-panel analysis, frozen separately from all earlier case-study
and external-confirmation work. Its sole confirmatory question is whether an
observation-only temperature fingerprint, defined before panel outcomes are
examined, discriminates USGS stream gages with versus without at least one upstream
major dam. The analysis must not read any Chattahoochee confirmatory data, prediction,
metric, once-lock, or roster-derived choice. The executable enforces this by rejecting
input and cache paths containing the forbidden tokens in
`configs/regulation_panel_freeze_v1.yaml`.

The machine-readable freeze is the controlling specification. This document explains
the data-source choices and limitations; it does not authorize deviations from that
file.

## Why GAGES-II is the primary dam source

The modern U.S. Army Corps of Engineers NID exposes a public REST API and an ArcGIS
Feature Service with point locations and fields including dam height, normal storage,
maximum storage, and NID storage. A spatially nearest NID point is not necessarily
upstream of a stream gage, however. Calling it “upstream regulation” without routing
both points on a directed river network would be a classification error.

GAGES-II is therefore the frozen primary source. USGS routed an enhanced 2009 NID
snapshot to each GAGES-II watershed and published station-level fields for total and
major dam counts, storage per watershed area, and straight-line gage distance to the
nearest upstream dam. GAGES-II defines a major dam as at least 50 ft (15 m) high or at
least 5,000 acre-ft in storage. The primary binary outcome is consequently
`MAJ_NDAMS_2009 >= 1`; distance profiles use `RAW_DIS_NEAREST_MAJ_DAM`. The current
NID service is audited for accessibility and field provenance only. It is not silently
substituted for the routed GAGES-II attributes.

This choice has a temporal limitation: the label is an upstream-dam snapshot centered
on 2009, not a time-varying operating record and not proof of thermal release. To
reduce temporal mismatch, temperatures are restricted to 2000–2019. Results describe
association with upstream major-dam presence, not causal effects of operations.

## USGS station discovery and temperature eligibility

The USGS Water Data OGC APIs are used rather than search-engine results or a hand-built
roster. The `time-series-metadata` collection discovers primary daily mean water
temperature (`00010`, statistic `00003`) series; `monitoring-locations` supplies site
type and coordinates; and `daily` supplies observations and approval state. Only
USGS stream sites (`ST`), exact station-number matches to GAGES-II, approved finite
observations, and the frozen 2000–2019 dates are eligible.

USGS metadata warns that long start-to-end spans can contain large gaps. A station is
therefore not admitted from metadata duration. At least 10 calendar years must each
have at least 300 approved distinct daily observations. Multiple primary series are
not spliced: the series with the most approved dates is retained, with predeclared
ties. This prevents an analyst from choosing a visually favorable sensor era.

## Frozen diagnostics

A 366-day circular median climatology uses a ±7-day day-of-year window. Anomalies are
observed temperature minus that climatology. Autocorrelation uses pairs separated by
exactly 30 or 90 calendar days, rather than adjacent retained rows. The station table
contains seasonal variance fraction, anomaly SD, exact-lag ACF30 and ACF90, median
annual amplitude, and the already defined memory–range index:

`memory–range index = ACF30 / (maximum observed temperature − minimum observed temperature)`.

The index is deliberately not redefined after the panel is seen. The working
hypothesis is that major-dam sites have larger values because regulation can narrow
the thermal range while preserving long anomaly memory.

## Frozen inference

The primary coefficient comes from a one-predictor logistic model using the
standardized index and HC1 robust uncertainty. Generalization is measured by pooled
out-of-fold ROC AUC under leave-one-GAGES-II-aggregated-ecoregion-out validation.
No probability threshold is optimized. A 2,000-replicate aggregated-ecoregion cluster
bootstrap supplies the AUC interval.

A predeclared sensitivity adds log drainage area and aggregated-ecoregion fixed
effects. Among sites with an upstream major dam, fixed distance bins summarize the
index, ACF30, and annual amplitude versus `RAW_DIS_NEAREST_MAJ_DAM`, with the same
ecoregion-cluster principle for intervals.

The minimum sample size for a generalizable panel claim is 300 eligible stations.
Below that value, the software still emits the exact flow, estimates, and exclusions,
but the claim is automatically withheld. An AUC near 0.5, a sign reversal, wide
intervals, or a flat distance profile is a valid result and does not reopen the
freeze.

## Reproducibility and cache contract

The default cache is `data/cache/regulation_panel_v1/`, which is independent of every
external-confirmation path. Every downloaded response is accompanied by its request
URL or manifest and a SHA-256 digest. The GAGES-II archive must additionally match the
USGS-published MD5 in the freeze. Daily observations are stored as an immutable raw
Parquet cache after complete pagination; analysis outputs contain file identities and
software/freeze identities. `--offline` permits exact reproduction only when all
required cached sources are present and valid.

Authoritative documentation and releases:

- USGS Water Data APIs: <https://api.waterdata.usgs.gov/>
- USGS OGC API guide: <https://api.waterdata.usgs.gov/docs/ogcapi/>
- USGS migration mapping for daily values and time-series metadata:
  <https://api.waterdata.usgs.gov/docs/ogcapi/migration/>
- GAGES-II USGS release: <https://doi.org/10.5066/P96CPHOT>
- NID public API documentation: <https://nid.sec.usace.army.mil/api/developer>
- NID public Web-GIS services: <https://nid.sec.usace.army.mil/nid/>


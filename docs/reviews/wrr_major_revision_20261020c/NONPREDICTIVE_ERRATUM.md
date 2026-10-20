# Snow-attribute units and hydrological subgroup labels

Discovered while checking the first frozen retrospective test report. The
resource field `Pt as snow` is a percentage (range 2.1--85.1), not a fraction.
The archived metadata builder compared it with 0.5 when naming a
`snow_dominated` subgroup. That is a label error: the physically intended
majority-snow condition is 50 percent. `Glaciers % > 0` remains unchanged.

No score feature, reconstruction fit, gap placement, empirical threshold,
component membership, acquisition eligibility or salted development/calibration/
test role uses this subgroup label. None is changed. Method and deployment
locks remain untouched, as do the original metadata and raw evaluation outputs.
The final analysis supplies a separate corrected descriptive stratification:
glacier influence first; otherwise snow share >= 50%; otherwise other mountain
catchment. Missing physical attributes are unknown rather than invented.
All final hydrological tables and discussion use the corrected labels. The
`hydrological_stratum` rows in script 360's raw CSV are superseded for this
reason; their non-hydrological rows and all admission decisions remain valid.

The case-builder's descriptive `near_natural_published_selection` string is not
an independently verified regulation status and is not used to support a
near-natural or unregulated-catchment claim. This external cohort is described
as mountain catchments; regulation and groundwater classes remain unverified.

This is not a new subgroup chosen because it performs well. It restores the
predeclared majority-snow meaning using the resource's documented units,
applies the same rule to all records and reports its failures and uncertainty.
No failed primary hypothesis is redefined or rescued by the correction.

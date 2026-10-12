# Supporting information

Material that belongs to the record rather than to the argument: data
provenance, protocol history, the runs that were discarded and why, and the
reproduction path. Nothing here is required to follow the article.

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

Basin characteristics for the United States subset are from GAGES-II
(Falcone, 2011), joined on the eight-digit gauge identifier. NASA POWER
supplies air temperature where it was already available in the archive; its
coverage is 2.3% of development cases and 0.85% of reserved cases and no claim
rests on it.

## S2. Quality control and the definition of a network

A *network* is a provider's group of stations on a common river system, which
is the unit at which donor stations are available to one another. Networks are
the clustering unit for every interval in the article, because station-years
within a network share weather, regulation and instrumentation.

Waterbody class was assigned per network from the provider's own naming and an
explicit map; seas, lakes, canals, estuaries and deltas are listed and excluded
rather than averaged into a river result. Reference series are never imputed: a
calendar year with any missing day contributes no truth. Stations with fewer
than four fully observed calendar years are excluded, because the
leave-one-year-out estimator protocol requires them.

The resulting denominator, with every exclusion and its count, is in
`results/v17_fitness/step1_panel/`.

## S3. Protocol history

The study was pre-registered in
`results/v17_fitness/step9_freeze/SUCCESS_CRITERION_v17.json` before the
reserved networks were opened. Two aspects of that freeze were incomplete and
are recorded here rather than silently repaired.

**The weighting between outage arms was not declared.** The case set mixes an
empirical arm, drawn from the outage geometry the same networks experience,
with a stratified arm built to span the decision space. Their base rates differ
by an order of magnitude. The pre-registered test was run on the pooled set, as
declared; the article reports the decomposition alongside, and reports that the
declared effect is not met on the empirical arm alone.

**The natural scale of the peak has two values.** Computed over the full
eligible roster it is 1.06 °C; recomputed inside the development case table it
is 1.08 °C. The primary tolerance is 0.50 °C throughout except in the
cross-metric comparison, where each endpoint's scale is recomputed on the same
footing and the peak tolerance is 0.51 °C. The tolerance sweep shows the axis
ordering is unchanged between 0.25 and 1.0 standard deviations.

## S4. Runs that were discarded

Two defects made specific artifacts unusable. In both cases the affected
numbers were discarded rather than reported alongside the repaired ones, and
the full pipeline was re-run.

1. **Outage realizations were seeded from a salted hash.** Python randomises
   `hash()` for strings per process, so the case table could not be regenerated.
   Repaired with a deterministic digest; two independent runs are now identical.
2. **Worker results were concatenated in completion order.** Content was
   reproducible but row order was not, and the tie-break jitter used by a
   discrete screening rule is assigned positionally. Repaired by writing the
   table in a declared row order.

A third defect affected the calibration rather than the data: an additive,
per-estimator conformal scheme under-covered because selecting the smallest of
several bounds is a winner's curse. It was replaced by the selection-conditional
multiplicative scheme described in the article.

## S4b. Figure S1 — the evidence chain and what it does not yet close

`figures/v17/f3_evidence_chain.pdf` (source: `figures/v17/drawio/f3_evidence_chain.drawio`)
lays the study out as a chain and labels each link with the research question
that establishes it: real archive, complete-year truth, outage placement,
reconstruction, error of the derived statistic (RQ0), which axis governs (RQ1,
RQ2), the screening decision (RQ3, RQ3b, RQ4), the held-out confirmation and
its calibration (RQ5, RQ6), the downstream judgement (RQ7) and the assumption
checks (RQ8).

Two links are drawn open, because they are. The rule has never been applied to
one of the 2,422 genuinely incomplete station-years in the same archive — those
records carry no truth and enter this design only as a source of realistic
outage geometry — and no archive-level number is shown to change under it: the
exceedance analysis of §5.9 is computed on the same simulated cases, so it is
downstream of the simulation rather than downstream of the archive. The figure
is in the supporting information rather than the article because a schematic of
what a study has not done belongs to the record, not to the argument.

## S5. Verification

- The case table is byte-reproducible including row order, pinned by a test.
- No feature may read a day the outage hides; enforced in `feature_frame` and
  pinned by a test.
- Every table cell and audited inline number in the article is re-derived from
  the artifacts by `scripts/199_v17_audit_manuscript.py`, which the test suite
  runs; the article carries a machine-readable block of its headline numbers
  that is compared against `results/v17_fitness/paper_numbers.json`.
- Provenance for each claim — script, artifact, digest, article section — is in
  `results/v17_fitness/evidence_ledger.csv`.

## S6. Reproduction

Schematic figures are rebuilt from their draw.io sources with `make
figures-drawio`; the sources and the export rules are documented in
`figures/v17/drawio/README.md`. The analysis figures and every artifact behind
the article come from the pipeline below.

```
python3 scripts/180_v17_panel.py
python3 scripts/181_v17_cases.py --workers 96
python3 scripts/181_v17_cases.py --workers 96 --fit-protocol strictly_prior_years \
        --out cases_prior_years.parquet
python3 scripts/182_v17_ceiling.py
python3 scripts/183_v17_mechanism.py --workers 96
python3 scripts/184_v17_screen_frontier.py
python3 scripts/185_v17_downstream.py
python3 scripts/186_v17_freeze.py
python3 scripts/187_v17_confirm.py
python3 scripts/189_v17_arm_robustness.py
python3 scripts/190_v17_ablations.py
python3 scripts/191_v17_prior_years.py
python3 scripts/192_v17_paper_tables.py
python3 scripts/194_v17_baseline_strength.py
python3 scripts/195_v17_simple_rule.py
python3 scripts/196_v17_metric_generality.py
python3 scripts/197_v17_cluster_conformal.py
python3 scripts/198_v17_weighting.py
python3 scripts/200_v17_round4_gaps.py
python3 scripts/201_v17_hydrology.py
python3 scripts/202_v17_robustness.py
python3 scripts/188_v17_figures.py
python3 scripts/193_v17_paper_numbers.py
python3 scripts/203_v17_evidence_ledger.py
python3 scripts/199_v17_audit_manuscript.py
python3 -m pytest tests/test_v17_fitness.py
```

About one hour on 128 cores.

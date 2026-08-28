# Submission checklist

## Scientific package

- [x] Network-level inference is primary; pooled and within-network results are diagnostic.
- [x] Fitting-period empirical-transfer baseline is implemented and reported.
- [x] All 1,440 cells have a prediction-source audit; 660 network-mean fallbacks are reported separately from 780 directly supported units.
- [x] Supported-only and complete-panel empirical metrics are both reported against the simple model.
- [x] Learned error model tests analytic-risk increment.
- [x] Three recovery-model families use identical outer gaps.
- [x] The actual BiLSTM sensitivity covers 14 networks, eight providers, and seven countries and is bounded as non-SOTA, nonconverged, and not a full roster.
- [x] The published air2stream-8 equation is evaluated on a fixed independent US subset with exact input-QC, optimizer, scope, and day-boundary caveats.
- [ ] The air2stream-equivalent baseline is extended beyond the eight-network US subset with harmonized daily boundaries.
- [x] The v11 empirical predictor is evaluated on 1,327 matched planted field-outage geometries with paired network inference and fallback audit.
- [ ] Actual missing-day performance or field-failure selection bias is estimable from truth-bearing data.
- [x] US mixed heterogeneity reports random intercepts/slopes, phase interactions, broad HUC2/GAGES-II strata, and noncausal boundaries.
- [x] Conditional-variance saturation mechanism uses a fixed 61-station roster.
- [x] Original and horizon-Mondrian interval coverage/width are reported.
- [x] Real-data placement replay includes MI, QR, distance, random, and oracle comparators.
- [x] Exact learn-then-test triage reports empty certified sets.
- [x] Domain recalibration is labelled post-confirmation development.
- [x] Second-confirmation scoring excludes all 42 first-panel scored networks; three source/QC-only networks are disclosed separately.
- [x] Second confirmation reports 60 attempted, three attrited, and 57 scored networks.
- [x] Second confirmation reports 874 direct-horizon and 572 network-mean-fallback units separately.
- [x] Second-confirmation rank and calibration results are reported with failed interval-efficiency and empty-triage endpoints.
- [x] Second-panel placement reports all 13 complete matrices, zero attrition, and the small directional regret difference without a confirmatory utility claim.

## Manuscript package

- [x] Key Points and Plain Language Summary match the empirical-transfer claim.
- [x] Methods are self-contained; YAML is a reproducibility contract, not a substitute.
- [x] Five main figures and one development-only supporting figure are identified, including Figure 5 heterogeneity.
- [x] Monitoring-design, empirical-gap, kriging-variance, and conformal references are included.
- [x] Internal workflow codes and audit language are absent from the main manuscript.
- [x] Provider access and redistribution treatment are listed in SI.
- [x] Cover letter targets *Water Resources Research*.
- [x] Abstract reports the network-level headline and omits secondary number density.
- [x] Trial-gap novelty is positioned as cross-network transfer, not invention.
- [x] The development placement figure is confined to Supporting Information; second-panel directional results remain nonconfirmatory.
- [x] Open Research text distinguishes releasable artifacts from restricted provider values.
- [x] Package manifest lists manuscript, SI, captions, figures, result tables, and external dependencies.
- [x] Compact metrics and audits are primary artifacts; large placement-level empirical predictions are marked regenerable rather than required for a fresh clone.
- [x] The second-confirmation amendment is described as internally hash-bound, same-commit evidence rather than externally preregistered.

## External items that cannot be fabricated in-repository

- [ ] Authors confirm names, affiliations, ORCIDs, CRediT contributions, corresponding author, and email.
- [ ] Authors confirm conflicts, funding, acknowledgments, author approval, and related-manuscript status.
- [ ] The permitted archival package is deposited and its minted DOI replaces `pending` in `.zenodo.json`, `CITATION.cff`, the manuscript, and submission metadata.
- [ ] Provider-specific redistribution permissions are attached where raw daily values will be archived; otherwise those values remain omitted.
- [ ] Final journal word count, figure format, and author declarations are checked in the submission portal.
- [ ] Every repository URL, DOI, reference key, figure callout, and SI callout is resolved in the rendered submission files.

The unchecked external items require author identity, a third-party archive
action, provider permission, or submission-portal review. They are not silently
marked complete by code generation.

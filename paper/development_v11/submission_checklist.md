# Submission checklist

## Scientific package

- [x] Network-level inference is primary; pooled and within-network results are diagnostic.
- [x] Fitting-period empirical-transfer baseline is implemented and reported.
- [x] Learned error model tests analytic-risk increment.
- [x] Three recovery-model families use identical outer gaps.
- [x] Conditional-variance saturation mechanism uses a fixed 61-station roster.
- [x] Original and horizon-Mondrian interval coverage/width are reported.
- [x] Real-data placement replay includes MI, QR, distance, random, and oracle comparators.
- [x] Exact learn-then-test triage reports empty certified sets.
- [x] Domain recalibration is labelled post-confirmation development.
- [x] Second-confirmation protocol excludes the first 42 networks.

## Manuscript package

- [x] Key Points and Plain Language Summary match the empirical-transfer claim.
- [x] Methods are self-contained; YAML is a reproducibility contract, not a substitute.
- [x] Five generated main figures exist and use domain-level legends.
- [x] Monitoring-design, empirical-gap, kriging-variance, and conformal references are included.
- [x] Internal workflow codes and audit language are absent from the main manuscript.
- [x] Provider access and redistribution treatment are listed in SI.
- [x] Cover letter targets *Water Resources Research*.

## External items that cannot be fabricated in-repository

- [ ] Authors confirm names, affiliations, ORCIDs, contributions, conflicts, and corresponding author.
- [ ] Zenodo release is deposited and its minted DOI replaces `pending` in `.zenodo.json` and `CITATION.cff`.
- [x] A second independent panel reached 60 strict-QC networks across US, Czech, and Norwegian domains.
- [ ] A validated Canadian network arrives and authorizes second-confirmation scoring under the registered protocol.
- [ ] Provider-specific redistribution permissions are attached where raw daily values will be archived; otherwise those values remain omitted.
- [ ] Final journal word count, figure format, and author declarations are checked in the submission portal.

The unchecked items require author identity, a third-party archive action, new
independent observations, or provider permission. They are not silently marked
complete by code generation.

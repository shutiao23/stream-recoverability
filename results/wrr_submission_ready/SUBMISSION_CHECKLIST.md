# P0-08 submission checklist

## Science package (agent-completable)

- [x] Claim registry with evidence types (`claim_registry.csv`, 25 rows)
- [x] Repo-wide prior-access audits: sealed USGS panel corrected
      (`AMENDMENT_prior_access_sealed_panel.md`) and all 291 transport stations
      never used (`prior_access_audit_multi_agency.csv`)
- [x] Input hashes for 146 study networks (`current_data_manifest.csv`, 0 missing)
- [x] Measurement provenance dictionary and per-network acquisition routes;
      CHMI/RWS/SYKE/ARSO/SMHI stratified, LUBW redistribution restriction recorded
- [x] Reviewer access route and frozen input bundle
      (`docs/reviews/wrr_input_access_route.md`, `scripts/262`)
- [x] Run identity / preflight / fail-closed runs / generation hash guard
- [x] F02/F03/F11/F12 code fixes recomputed with pre-fix bytes preserved
- [x] Certificate.predict on real incomplete years, invariance-tested
- [x] Method freeze (`P0_06_method_freeze.json`)
- [x] Wave-2 independent confirmation scored once (49 networks; USGS+Hub'Eau+UK EA;
      Δ=−5.89 pp [−6.92, −4.91]; 0 recon failures; seal scored)
- [x] First sealed USGS / multi-agency transport scores preserved as withdrawn
      audit artifacts (not live claims)
- [x] Fig2b includes wave-2 confirmation row; binding check `hard_ok`
- [x] Headline narrowing in title/abstract/key points/conclusions, enforced by
      `scripts/254_wrr_claim_binding_check.py`
- [x] Desk checks green except author block
- [x] F-findings closure audit (`F_FINDINGS_CLOSURE_AUDIT.csv`, 22 rows)
- [x] P1 supplements: hidden-bias grid, error scenarios, cold endpoint, phase
      identifiability rule, regulatory endpoint bias, faithful baseline
- [x] P2: outage-cause closure, transfer boundary, companion dataset + dashboard

## Human-required before GEMS upload

- [ ] Fill `metadata/submission_author_metadata.json` and approve
- [ ] Remove AUTHOR placeholders; rebuild PDF
- [ ] Confirm data-rights / redistribution language with ARSO, Rijkswaterstaat and
      LUBW (the three without a named open licence)
- [ ] Optional: extend the transport panel beyond four agencies
- [ ] Optional: mint the Zenodo DOI for the archived snapshot

## Reproduce (current study)

```bash
PYTHONPATH=src python3 scripts/229_wrr_preflight.py
PYTHONPATH=src python3 scripts/228_wrr_rebuild_from_inputs.py --clear-cache
PYTHONPATH=src python3 scripts/231_wrr_certificate_deploy_predict.py
PYTHONPATH=src python3 scripts/254_wrr_claim_binding_check.py
PYTHONPATH=src python3 scripts/263_wrr_objective_completion_audit.py
# both sealed confirmations are already scored exactly once; the score scripts
# refuse to run again unless the seal is intentionally rebuilt and re-amended
python3 scripts/223_wrr_build.py
```

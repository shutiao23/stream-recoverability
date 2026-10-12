# P0-08 submission checklist

## Science package (agent-completable)

- [x] Claim registry with evidence types (`claim_registry.csv`)
- [x] Prior-access ledger for reserved panel
- [x] Input hashes for 146 study networks (`current_data_manifest.csv`)
- [x] Measurement provenance; SYKE excluded from unified daily-mean claim
- [x] Run identity / preflight / fail-closed runs
- [x] F02/F03/F11/F12 code fixes
- [x] Certificate.predict on real incomplete years
- [x] Method freeze (`P0_06_method_freeze.json`)
- [x] Sealed never-used confirmation (USGS 39 networks) scored once
- [x] NVE multi-agency probe attempted; below floor; transfer not supported
- [x] Headline narrowing in title/abstract/keypoints/conclusions
- [x] Desk checks green except author block
- [x] F-findings closure audit (`F_FINDINGS_CLOSURE_AUDIT.csv`)

## Human-required before GEMS upload

- [ ] Fill `metadata/submission_author_metadata.json` and approve
- [ ] Remove AUTHOR placeholders; rebuild PDF
- [ ] Confirm data-rights / redistribution language with providers as needed
- [ ] Optional: expand multi-agency never-used panel to ≥30 non-USGS networks
- [ ] Optional: redraw Figure 1 for non-expert 30-second read

## Reproduce (current study)

```bash
PYTHONPATH=src python3 scripts/229_wrr_preflight.py
PYTHONPATH=src python3 scripts/228_wrr_rebuild_from_inputs.py --clear-cache
PYTHONPATH=src python3 scripts/231_wrr_certificate_deploy_predict.py
# sealed confirmation already scored; do not re-run 234 unless intentionally amending
python3 scripts/223_wrr_build.py
```

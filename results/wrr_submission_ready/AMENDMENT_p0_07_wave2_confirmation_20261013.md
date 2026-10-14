# P0-07 wave-2 independent confirmation — scored once (2026-10-13)

## Gate

- Protocol seal: `P0_07_NEW_CONFIRMATION_SEAL.json` (`scored: true` after this run)
- Manifest: `p0_07_wave2_ingest/wave2_inputs_manifest.csv`
  (sha256 `d4d9227f3b6361da148428049b6a5a731a8a0be8486ec031aab06c64c9da318d`)
- Prior-access: `wave2_prior_access_summary.json` (`clean: true`; programme-used
  stations excluded at assemble)
- Floors: 49 networks / 3 providers (usgs, hubeau, uk_ea) / 13 contexts

## Verdict (do not retune)

| Metric | Value |
|---|---|
| Δ (pp) at 70% / 0.5 °C | **−5.89** |
| 95% CI (pp) | **[−6.92, −4.91]** |
| n_networks / n_stations / n_cases | 49 / 143 / 13017 |
| Reconstruction failures | **0** |
| Providers same direction | USGS −5.87; Hub'Eau −10.70 (≥2) |
| QC subset (USGS) agrees | yes (−5.87; CI upper < 0) |
| `predeclared_success_rule_met` | **true** |

Artifact: `p0_07_wave2_ingest/p0_07_wave2_confirmation/verdict.json`.

## Not scored

- Leftover opened-wave `confirmation_ingest/`
- Historical `p0_07_sealed_confirmation/` and `p0_07b_multi_agency_transport/`
  (audit-failed; preserved)
- UK EA provider split underpowered (`n_cases < 100`); station years still in pooled panel

## Claim status

- P0-07 wave-2: **confirmed_with_scope_limits** (multi-provider; repaired QA)
- First sealed USGS / transport seals: remain **executed_audit_failed**
- Formal external effect for wave-2 may enter abstract/conclusions; withdrawn
  seals must stay labelled as withdrawn

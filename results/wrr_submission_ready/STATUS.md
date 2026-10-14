# WRR submission-readiness — science package closed; author human gate open

Locked review commit: `1e0f24e32723e3b14dbacdba3dfa851ff60f58fe` (2026-10-13 00:00:01 UTC).

## Objective gates (2026-10-13 audit)

| Requirement | Verdict | Evidence |
|---|---|---|
| Truth values valid (no −999999 / unit failures in confirmation) | **met** | P0-02 sanitize/quarantine; wave-2 assemble rejects implausible °C |
| Admitted ⇒ finite hottest-30; full 70% denominator | **met** | wave-2 `n_cert_reconstruction_failures=0`; `n_candidate_cases=n_cases=13017` |
| Primary confirmation passes preregistered gates, no NVE leakage | **met** | wave-2 Δ=−5.89 pp [−6.92,−4.91]; providers usgs/hubeau/uk_ea; QC subset agrees |
| Mechanism claims falsifiable / narrowed | **met** | “governs” withdrawn; paired dominate claim hedged; crossover exploratory |
| Reviewers can reproduce from hashed legal inputs | **met** | `wave2_inputs_manifest.csv`; access route; binding `hard_ok` |
| P0-01 … P0-07 | **met** | freeze; sanitize; recon; env; MNAR; reanalysis; wave-2 scored once |
| P0-08 manuscript + key figures | **met except author** | TeX/PDF rebuilt; Fig2b includes wave-2; desk length checks green |
| P1 preparation | **met (scaffold)** | `amendments/p1_01_uncertainty_sources/`; day-level MNAR exploratory |
| Author block for GEMS | **human gate** | `metadata/submission_author_metadata.json` `complete=false` |

## Formal external confirmation (live)

**Wave-2 independent confirmation:** Δ = −5.89 pp at 70% / 0.5 °C,
CI [−6.92, −4.91], 49 networks / 143 stations / 13 017 cases
(USGS + Hub'Eau + UK EA), 0 reconstruction failures.
`P0_07_NEW_CONFIRMATION_SEAL.json` scored; leftover opened-wave not scored.

**Withdrawn first seals (do not quote):** `p0_07_sealed_confirmation/`,
`p0_07b_multi_agency_transport/`.

**Retrospective holdout (allowed):** 9.7%→2.5% (Δ=−7.13 pp).

## Residual (blocks GEMS upload only)

1. Fill and approve `metadata/submission_author_metadata.json`
2. Remove AUTHOR placeholders; rebuild PDF (agent rebuild succeeds once metadata complete)
3. Optional: ARSO / Rijkswaterstaat / LUBW redistribution confirmation

See `AUTHOR_METADATA_FAILURE_SHOUKOU.md`. Inventing author names is forbidden.

## Reproduce

```bash
PYTHONPATH=src python3 scripts/254_wrr_claim_binding_check.py
PYTHONPATH=src python3 scripts/263_wrr_objective_completion_audit.py
python3 scripts/223_wrr_build.py
```

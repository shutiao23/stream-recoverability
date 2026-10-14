# Claim-status freeze — 2026-10-13 audit

Locked review commit: `1e0f24e32723e3b14dbacdba3dfa851ff60f58fe` (2026-10-13 00:00:01 UTC).

This amendment does **not** overwrite sealed scores or historical verdict
bytes. It reclassifies what those artifacts may enter in the abstract,
conclusions, and figure captions under the 2026-10-13 audit (F01–F14).

## Evidence classes

| Class | Meaning | May enter abstract/conclusions? |
|---|---|---|
| `valid_retrospective` | Archived development / reserved holdout with finite selected errors; prior-access caveats apply | Yes, with explicit "retrospective holdout" label |
| `executed_audit_failed` | Panel was sealed and scored, but data QA, support contract, or protocol gating failed | No — mark pending; keep raw seal for transparency |
| `pending_confirmation` | Requires repaired inputs + new independent score under locked protocol | No |
| `exploratory` | Opened-panel or incomplete-implementation analyses | No (SI / methods only) |

## Headline reclassification

| Claim ID | Previous status | Frozen status | Reason |
|---|---|---|---|
| V17-H2 | retrospective_only | **valid_retrospective** | Reserved 9.7%→2.5% (−7.13 pp); selected errors finite; not upgraded to cross-agency confirmation |
| V17-A1 | retrospective_only | valid_retrospective (empirical arm caveat) | Keep as holdout arm contrast; not transport |
| P0-07 / P0-07-POOL | confirmed_with_scope_limits | **executed_audit_failed** | F01 (−999999 truth years); F02 (NaN selected errors dropped from 70% denominator) |
| P0-07-TRANSPORT | transport_supported | **executed_audit_failed** | F01 (SMHI unit/coding); F02 (NaN drop); F03 (quality_checked mixes NVE secondary) |
| NVE-PROBE | failed_transfer_or_underpowered | exploratory secondary only | Must not rescue primary transport |
| M1 (MNAR) | exploratory_with_bias_sensitivity | **executed_audit_failed** (implementation) | F06: no day-level re-peak; pending recompute |
| D2 (proxy→counts) | proxy_quantified_labelled | exploratory; withdraw headcount transport | F10 |
| L1 (governs) | pending_new_confirmation | pending; withdraw governs wording | F04 |
| DEPLOY-CERT | confirmed_interface | executed_audit_failed for admission semantics | F02: 198 admit-with-NaN |

## Formal external effects

**Wave-2 confirmation (2026-10-13, after this freeze):** scored once under
`P0_07_NEW_CONFIRMATION_SEAL.json`; Δ=−5.89 pp [−6.92, −4.91]; may enter
abstract/conclusions. See `AMENDMENT_p0_07_wave2_confirmation_20261013.md`.

**Still withdrawn / pending (do not quote as confirmation):**

> **[pending — 探索期数据，不可写入结论]**

Applies to: the *first* sealed USGS confirmation contrasts, multi-agency
transport contrasts, quality-checked transport gate, and any caption that
treats those audit-failed panels as completed confirmation.

## Preserved retrospective sentence (allowed)

On the archived reserved holdout, at 70% retention and 0.5 °C tolerance,
consequential-error rate falls from about 9.7% to about 2.5%
(Δ = −7.13 pp, network-clustered 95% CI [−8.97, −5.36]). Label as
**retrospective network holdout**, not cross-agency confirmation.

## Artifacts

- Updated `claim_registry.csv` (status + finding_ids + notes)
- `claim_status_freeze_20261013.csv` (machine-readable freeze table)
- `STATUS.md` reset to audit-open (gates unmet until repair)
- Original seals/verdicts under `p0_07_*` left byte-intact

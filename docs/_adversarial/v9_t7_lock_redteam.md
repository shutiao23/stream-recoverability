# Red team: T7 public confirmatory lock

Date: 2026-08-26
Target: `src/stream_recoverability/analysis/public_confirmatory_lock.py`, `scripts/66_propose_public_confirmatory_lock.py`
Status: parent-reviewed. Not confirmatory.

## Attacks

1. **Locking without 40 + 10 non-NA.** Refusal must not create `confirmatory_once.lock.json`. A refusal sidecar is allowed. Tests require `enough_to_lock is False` below floors.
2. **Opening temperatures to assign sealed.** Proposal reads overlap metadata only (`complete_enough`, continent). No wide CSV values.
3. **Sealing burned / last-check.** `never_sealed_networks` from v9 freeze, last-check name tokens, and v1 last-check IDs are forbidden. Willamette, Jinsha, Loire, Colorado cannot enter sealed.
4. **Remapping catalog v1.** Script does not write `configs/network_catalog_v1.yaml`.
5. **Writing a lock now would be a lie.** Current Europe complete_enough is 0. The attempt must refuse. Do not lower the floor to lock early.
6. **Reuse of historical Chattahoochee once-lock path.** This lock is under `results/framework/` and is independent of the Jinsha/Chattahoochee confirmatory once-lock.

## Parent merge

Keep the refuse-until-floors behavior. Do not mark T7 complete.

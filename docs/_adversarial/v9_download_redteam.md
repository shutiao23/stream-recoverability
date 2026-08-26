# Red team: catalog v2 download (Phase 3)

Date: 2026-08-26
Target: `src/stream_recoverability/data/v2_download_policy.py`, `scripts/57_download_catalog_v2_candidates.py`, `tests/test_v2_download_policy.py`.
Sealed last-check temperatures were not opened for this review.

## Attacks that do not land

- Last-check site IDs are excluded before fetch. `09379500` / Columbia `14105700` / Ohio / Deschutes cannot enter `download_site_ids`. San Juan is blocked as `last_check_site`.
- Columbia / Colorado / Deschutes / Loire names are blocked even if the v2 cluster uses other IDs.
- Chattahoochee / Jinsha are `historical`. Burned Delaware / Willamette / … names are not re-downloaded as new independent units.
- `network_catalog_v1.yaml` is not rewritten. Manifest locks `last_check_temperatures_opened: false` and `formal_evidence: false`.
- `complete_enough` requires 3 stations, ≥8 overlap years, **and** ≥5×365 same-day rows. Catalog overlap is labeled `catalog_overlap_is_not_concurrency`.

## Must-fix / residual

1. **Concurrency is still a running count, not T2.** Honest catalog remains 98. Target remains 150. Early download rows (Missouri, Snake, …) being `complete_enough=True` must not be written as the 150-network corpus.
2. **`independent_unit` is site-subset only.** Name-nested tributaries with disjoint IDs (Animas vs San Juan; McKenzie vs Willamette already burned) can still be counted twice.
3. **James River dropped to 2 sites after unique-ID assignment.** That is honest, but the plan still reports it as attempted. Do not pad it back with last-check IDs.
4. **Europe is not closed.** Hub'Eau name clusters (40 non-Loire) are not daily concurrent networks. Instantaneous chronique ≠ daily T8.
5. **Script 57 writes new wides under `public_rivers_v2/`** while the 12 burned wides stay in `public_rivers/`. A later ablation that only globes one directory will undercount.

## Verdict

Download policy is the first executable unique-station / never-open-last-check gate. It does not make T2 true. Do not freeze split roles from this run.

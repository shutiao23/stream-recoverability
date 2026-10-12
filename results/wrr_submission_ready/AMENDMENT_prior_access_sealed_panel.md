# Amendment: prior-access status of the sealed USGS confirmation panel

Status: correction of record, 2026-10-12. The primary sealed score is **unchanged**
(`p0_07_sealed_confirmation/verdict.json`, scored once, not re-run).

## What was claimed

`confirmation_inputs_manifest.csv` labels all 39 networks
`prior_access_bucket = never_used_in_repo_programme`, and
`CONFIRMATION_PROTOCOL_SEALED.md` / the manuscript abstract call the panel
"never-used".

## What a repo-wide audit finds

`scripts/245_multi_agency_prior_access_audit.py` now scans **every CSV in the
repository that carries a `station_id` column** (provider-aware, so an 8-digit
French Hub'Eau id cannot be mistaken for a USGS gauge), and splits prior use into

- **outcome-bearing** artifacts (losses, predictions, scores, metrics), and
- **descriptive** artifacts (catalogues, exclusions, span/coverage audits).

Earlier programme iterations — `results/framework/t2_recovery_benchmark_v*/`,
`results/development_v11/recovery_scoring/`, `results/revision_v12/`,
`results/regulation_panel_v1_legacy_transport/` — do contain station-level
records for part of the panel. Result for the 91 sealed stations / 39 networks:

| Class | Stations | Networks (every station clean) |
|---|---|---|
| No prior use of any kind (repo-wide) | 21 | 4 |
| No outcome-bearing prior use | 45 | 15 |
| Has outcome-bearing prior use | 46 | 24 (at least one station) |

The strict "never used anywhere in the programme" label is therefore **false for
the panel as a whole**, and the earlier audit understated it because it read only
the v16/v17 ledgers. What remains true: none of the 91 stations is in the v17
fitness panel (`step1_panel/station_roster.csv`), so the frozen certificate was
not fitted on them, and no v17/v18 rule, window or caption was selected on them.

## Diagnostic on the clean subsets (post-seal, disclosed)

`scripts/256_wrr_sealed_prior_access_diagnostic.py` reads the **already-scored**
cases and reports the same contrast restricted to clean subsets. It cannot
strengthen the primary result; it tests whether the result depends on
previously used networks.

| Subset | Networks | Stations | Cases | Pooled Δ (pp) | Empirical-arm Δ (pp) |
|---|---|---|---|---|---|
| All (primary) | 39 | 91 | 8973 | −7.94 [−10.17, −5.90] | −1.74 [−2.98, −0.68] |
| Networks clean of outcome use | 15 | 26 | 1923 | −9.42 [−12.44, −6.03] | −3.65 [−5.80, −1.62] |
| Stations clean of outcome use | 28 | 45 | 3494 | −8.26 [−10.35, −6.37] | −2.71 [−4.86, −1.41] |
| Stations clean of any prior use | 18 | 21 | 1794 | −7.27 [−10.28, −4.58] | −1.74 [−4.96, −0.43] |
| Networks clean of any prior use | 18 | 21 | 187 | below the 200-case floor; not scored | — |

The effect is at least as large on every clean subset, and the empirical-arm gain
is non-zero there. The conclusion does not depend on the contaminated networks;
the labelling, not the number, was wrong.

## Required reporting changes

1. Manuscript abstract, Key Points and the confirmation section must say:
   panel outside the development programme; state the 15/39 fully-outcome-clean
   network split; report the clean-subset diagnostic alongside the primary number.
2. `claim_registry.csv` rows `P0-07` and `P0-07-POOL` updated to this scope.
3. The transport panel (pre-registered separately) applies the *strict* rule:
   every station must be `never_used_repo_wide = True` before sealing.
4. The sealed manifest file itself is left byte-identical (its sha256 is part of
   the seal); this amendment supersedes its label.

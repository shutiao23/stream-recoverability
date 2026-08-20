# WRR / AGU GEMS submission checklist

This checklist records what a Water Resources Research package can honestly contain. Items that require unobserved performance remain open. Do not tick them by inventing numbers.

## Journal files

| File | Role | Status |
| --- | --- | --- |
| `manuscript.md` | Main text; Results are `RESULTS_PENDING` | Present; no MAE/skill/frontier claims; executable freeze is v3 |
| `methods.md` | Extended methods for SI | Present; grid counts locked to builders |
| `si.md` / `si_independence_audits.md` | Supplement | Present; audits are not ranks |
| `cover_letter.md` | Editor letter | Present; no performance claim |
| `key_points.md` | AGU Key Points | Present; ≤140 characters; no ranks |
| `plain_language_summary.md` | AGU PLS | Present; no ranks |
| `figure_captions.md` | Caption inventory | Present |
| `references.bib` | Bibliography | Present |
| `CITATION.cff` | Software citation | Present; `doi` unset |
| `LICENSE` | MIT software only | Present |
| `DATA_RIGHTS.md` | Restricted observations | Present; GEMS reviewer route |

## Figures and tables

| Artifact | Expected input | Honest outcome until roster + formal manifests |
| --- | --- | --- |
| Figure 1 | Station metadata + EDA coverage | Generated from descriptive files |
| Figure 2 | None (schematic) | Generated |
| Table 1 | Station metadata + EDA coverage | Generated |
| Figures 3–8, Tables 2–5 | Current-protocol formal results | Skipped; files must not exist as placeholders |

## Protocol gates (not optional)

1. Validation funnel stages complete **under `design_freeze_v3`**, including diagnostics, stability, go/no-go, and branch ablation or the frozen not-applicable path. v2 artifacts are not reusable.
2. Hash-verified `finalized_model_roster_v1` with no `budget_unstable` retained model.
3. Formal internal suites on `published_v2` using that roster only.
4. Three sensitivity data versions (`no_s2_suspect_v2`, `b1_no_level_v2`, `b1_shift_sensitivity_v2`), separately registered.
5. Frozen statistics: climatology-relative **and** best-simple-baseline-relative frontiers; donor-C lag/permutation falsification; no application frontier unless predeclared.
6. Confirmatory feasibility 60/60, then exactly-once performance after once-lock.
7. README evidence-status JSON updated only after those facts are true.
8. Archival software DOI minted only after a real deposit; do not invent Zenodo.

## Known remaining defects (do not hide)

- Restricted Jinsha columns are still present on the public GitHub development host. `scripts/26_audit_restricted_hosting.py` records that defect. History rewrite is not performed in this wave.
- No archival DOI exists.
- Pre-freeze `results/formal/` dumps are invalid and must not be submitted as results.

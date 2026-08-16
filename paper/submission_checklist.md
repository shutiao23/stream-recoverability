# WRR / AGU GEMS submission checklist

This checklist records what a Water Resources Research package can honestly contain. Items that require unobserved performance remain open. Do not tick them by inventing numbers.

## Journal files

| File | Role | Status |
| --- | --- | --- |
| `manuscript.md` | Main text; Results are `RESULTS_PENDING` | Present; no MAE/skill/frontier claims |
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

1. Validation funnel stages complete, including diagnostics, stability, go/no-go, and branch ablation or the frozen not-applicable path.
2. Hash-verified `finalized_model_roster_v1`.
3. Formal internal suites on `published_v1` using that roster only.
4. Three sensitivity data versions, separately registered.
5. Frozen statistics: climatology-relative **and** best-simple-baseline-relative frontiers; no application frontier unless predeclared.
6. Confirmatory feasibility 60/60, then exactly-once performance after once-lock.
7. README evidence-status JSON updated only after those facts are true.
8. Archival software DOI minted only after a real deposit; do not invent Zenodo.

## Known remaining defects (do not hide)

- Restricted Jinsha columns are still present on the public GitHub development host. That is a hosting defect, not an open-data release.
- No archival DOI exists.
- Pre-freeze `results/formal/` dumps are invalid and must not be submitted as results.

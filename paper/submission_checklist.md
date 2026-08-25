# WRR / AGU GEMS submission checklist

## Scientific revision

| Requirement | Evidence | Status |
| --- | --- | --- |
| Regulation mechanism and title | P3 transition, Guanyinyan history, 8-site fingerprint | Complete |
| P3 annual minima/amplitudes | `results/revision/annual_thermal_metrics.csv` | Complete |
| Stationarity-controlled budget | 2016--2017 and post-hoc 2016--2020 tables | Complete |
| Low-frequency robustness | Annual-mean-removed skill table | Complete |
| External placement uncertainty | 20 validation seeds; 2,700 cells; confirmation/lock untouched | Complete |
| Formal P3 change-date sensitivity | Pettitt + least-squares, year-block permutation, block-bootstrap CI | Complete |
| Independently frozen national panel | N=335; primary null, adjusted/distance sensitivities, isolation audit | Complete |
| Post-hoc LOEO within-fold AUC diagnosis | `results/revision/loeo_within_fold_auc.csv`; mean 0.526; SEPlains 0.132; freeze untouched | Complete / post-hoc |
| Expanded measured-covariate budget | `expanded_covariate_budget.csv` | Complete |
| One frontier code path | 27/27 climatology cells asserted identical | Complete |
| Nondegenerate hypothesis family | 24 finite tests + 3 reference rows; BH reported | Complete |
| Non-oracle node importance | Leave-one-year-out model selection; 9 target/failure summaries with 95% intervals | Complete |
| Absolute MAE in main evidence | Figure 3 and Table 4 | Complete |
| Natural-missingness disclosure | 0 missing hydrological days; masks described as probes | Complete |
| Deep material moved to SI | Main text limited to roster outcome | Complete |
| Evaluate-once artifact preservation | 540/540 units; complete once-lock and manifest; envelope descriptive only | Complete |
| External fixed-model sensitivity | Validation selects XGBoost; fixed 2023--2025 scoring | Complete / post-hoc |
| Confirmatory artifact preservation | 308 output files + once-lock tracked at original hashes | Complete |
| Manuscript/Key Points/PLS/captions | Association-focused revision; PLS <=200 words | Complete |
| AGU main manuscript and SI PDF | Template-compatible build with seven main figures | Complete locally |

## Evidence gates

- `results/analysis/analysis_manifest.json`: `status=complete`.
- `statistical_frontiers.csv` and climatology rows of `dual_frontier_comparison.csv`: 27 matched cells.
- `frontier_model_vs_climatology`: 24 finite tests; climatology rows are `reference_not_tested`.
- External `completion_manifest.json`: `complete=true`, `formal_evidence=true`, 540 completed units.
- External once-lock: `status=complete`; evaluate-once cannot be rerun.
- Frozen internal and external predictions remain unmodified.

## Submission blockers

| Item | Status | Required action |
| --- | --- | --- |
| Restricted Jinsha bytes on public history | Complete | Verified private bundle + commit map; rewritten public history; remote/tree audit reports zero restricted paths |
| Archival software DOI | **Blocking / open** | Deposit the sanitized release in a real archive and insert the minted DOI in `CITATION.cff` and manuscript |
| Restricted-data editorial exception | **Blocking / open** | Send the packet in `paper/editor_inquiry_send_checklist.md`; keep `accepted=false` until a written reply exists |
| Author metadata and declarations | **Blocking / open** | Complete `metadata/submission_author_metadata.json` and replace all bracketed title-page/cover-letter fields |
| GEMS confidential reviewer data upload | Open | Local bundle is at `private/gems_reviewer_bundle/` (gitignored). Upload in GEMS only after written editor acceptance |
| Public external derived-data archive | Complete candidate | Rights-filtered 301-file, 18-MB archive candidate; zero restricted paths; DOI still open |
| Reproduction report on sanitized release | Complete within public scope | 72/72 public-safe tests; confidential-fixture tests covered by the 456/456 private suite |

The package remains **NO-GO for submission** until the archival DOI, written restricted-data approval, author metadata, and remaining upload/reproduction tasks are closed. No placeholder DOI or claim that restricted data are open is permitted.

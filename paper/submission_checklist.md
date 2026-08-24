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
| Expanded measured-covariate budget | `expanded_covariate_budget.csv` | Complete |
| One frontier code path | 27/27 climatology cells asserted identical | Complete |
| Nondegenerate hypothesis family | 24 finite tests + 3 reference rows; BH reported | Complete |
| Best-available node importance | 36 corrected target-gap-failure rows | Complete |
| Absolute MAE in main evidence | Figure 3 and Table 4 | Complete |
| Natural-missingness disclosure | 0 missing hydrological days; masks described as probes | Complete |
| Deep material moved to SI | Main text limited to roster outcome | Complete |
| Evaluate-once confirmation | 540/540 units; complete once-lock and manifest | Complete |
| Confirmatory artifact preservation | 308 output files + once-lock tracked at original hashes | Complete |
| Manuscript/Key Points/PLS/captions | Regulation-focused revision | Complete |

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
| Restricted Jinsha bytes on public development history | **Blocking / open** | Follow `docs/public_release_remediation.md`: create a clean code-only repository or coordinate a verified history rewrite |
| Archival software DOI | **Blocking / open** | Deposit the sanitized release in a real archive and insert the minted DOI in `CITATION.cff` and manuscript |
| GEMS confidential reviewer data upload | Open | Upload restricted working files via AGU GEMS Data Files for Peer Review |
| Public external derived-data archive | Open | Archive USGS/NASA provenance and permitted aggregate outputs with the software release |
| Reproduction report on sanitized release | Open | Run tests and manuscript artifact checks from the archive candidate |

The package remains **NO-GO for submission** until every blocking item is closed. No placeholder DOI or claim that restricted data are open is permitted.

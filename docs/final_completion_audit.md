# Final completion audit

Audit date: 2026-08-28 UTC
Base commit inspected: `58630d3c5722beaea0715eacd9a42732bd041870` plus the current shared worktree.

## Verdict

The repository's requested in-scope analyses are complete, including the
first-panel v11 study, a 57-network independent second outcome evaluation, a
true BiLSTM sensitivity, an independent air2stream-equivalent subset, matched
planted field-outage geometry, and 100-network mixed heterogeneity models. The
goal is **not honestly 100% complete** only because author/legal declarations
and archival DOI minting require people or external services. Negative gates
and bounded sensitivities remain negative or bounded; completion does not turn
them into positive evidence.

Scientific gate failures are counted as completed negative experiments. They
are not counted as missing work, and they are not relabelled as successes.

| Area | Audit status | Evidence and boundary |
| --- | --- | --- |
| v9 lineage | Closed negative | Evaluate-once QC read 2,880 objects, retained 32/40 networks, withheld scoring, and consumed the authorization. Rerun, replacement, floor reduction, and scoring the 32 as confirmation are forbidden. |
| v4 lineage | Unbound from WRR | Canonical case-study package targets *Journal of Hydrology* and remains NO-GO on editor permission, author metadata, confidential-data handling, and DOI. |
| v11 public-data route | Complete for current local analyses | Development and confirmation acquisition routes are public providers; raw provider series are omitted from the commit unless redistribution terms are explicit. |
| Empirical transfer, supported cells | Complete positive | 780 directly supported confirmation cells; network Spearman 0.922, pooled Spearman 0.934, and R2 0.812. |
| Empirical transfer, all cells | Complete weaker result | All 1,440 cells have non-null predictions: 780 within-horizon and 660 network-mean fallbacks. Network Spearman is 0.767, pooled Spearman 0.633, and R2 0.145. |
| Analytic increment | Complete negative | The analytic-risk increment remains below the frozen useful-increment threshold. |
| Intervals | Complete negative | Network-simultaneous coverage is 0.929, but median width/loss is 2.217 and fails the width gate. |
| Statistical model roster | Complete within stated scope | Seasonal-boundary ridge, donor BLUP ridge, and XGBoost were evaluated; this does not establish recurrent/process-model robustness. |
| Recurrent sensitivity | Complete bounded negative | The six-network BRITS/GRU-style screen gave empirical-vs-model station-gap Spearman 0.384. A separate true bidirectional `torch.nn.LSTM` sensitivity completed 14 networks across eight providers: empirical-vs-LSTM station-gap Spearman was 0.338 and network Spearman 0.631. It remains bounded, post-confirmation, and not a SOTA/full-roster comparison. |
| Process sensitivity | Complete equivalent independent-subset negative | The development Ta + approved-flow ridge proxy was weak. A published air2stream 8-equation Crank-Nicolson Python equivalent then scored 8 US second-confirmation networks/14 stations selected only by input availability. Empirical-risk versus air2stream-loss network Spearman was 0.238. The original executable was not used, deterministic multistart least squares replaced PSO, and the result is US-only. |
| Real outage experiment | Complete matched planted-geometry negative transfer | The v11 empirical and nested-simple predictors were applied to 1,327 truth-bearing XGBoost B+D observed counterparts across 49 networks and paired to the same station's nearest artificial-grid horizon. Empirical network Spearman was 0.566 on natural geometry versus 0.734 on matched artificial geometry; the paired delta was -0.168 (95% network-bootstrap interval -0.328 to -0.012). Simple rank changed by -0.054 (interval -0.234 to 0.128). Actual missing days still have no truth; the result tests planted geometry, not the failure-selection process. |
| Placement | Complete independent directional result; utility claim unlicensed | Thirteen of thirteen eligible second-confirmation networks had complete replay matrices. Simple minimax mean regret was 0.240825 versus 0.256213 for random, a 6.01% directional reduction. There was no preregistered margin or significance threshold, QR had lower mean regret than minimax, and the artifact explicitly sets `confirmatory_utility_claim_licensed=false`. |
| Triage | Complete independent negative | Development-only calibration certified no nonempty simple or empirical release; evaluation on all 1,446 second-confirmation cells therefore released zero rows. The 5% endpoint failed without fabricating a safe set. |
| Heterogeneity | Complete descriptive mixed model | Cross-phase US mixed models use network random intercepts and prediction slopes. The simple panel has 104 networks and the empirical panel 100; regulation is known for 92 and 89, respectively. HUC2 climate groups, GAGES-II 2009 major-dam strata, phase/QC regime, and network size are descriptive boundaries, not site-scale climate attribution or causal regulation effects. |
| Second-confirmation gate | Internally complete, not externally preregistered | Canada failed an external provider-quality condition. A v2 amendment substitutes the exact Czech/Norwegian/US roster, binds canonical inputs by SHA-256, rejects forged readiness files, and is disclosed as same-commit/internal rather than externally timestamped preregistration. |
| Second-confirmation scoring | Complete positive ranking/calibration; interval-width negative | The canonical gate attempted 60 networks, recorded 3 prespecified attritions, and scored 57 above the floor of 40. Simple-model network Spearman was 0.614 with slope 1.017; empirical network Spearman was 0.715 with slope 0.950. Empirical simultaneous coverage was 1.0 but median interval width/loss was 8.398, so the width gate failed. |
| Author and DOI actions | External blockers | Author identities/declarations are intentionally blank and no archival DOI has been minted. These cannot be invented in-repository. |

## Independent validation

- Final post-extension full suite: **1,026 passed**, 2,074 warnings, 553.98 seconds.
  Warnings were existing pandas/scikit-learn deprecations and two PyPOTS user
  warnings; there were no failures.
- New recurrent, BiLSTM, process-hybrid, air2stream-equivalent,
  matched-geometry, US heterogeneity, goal-audit/second-gate, and Tier-2
  readiness boundary tests also passed in focused reruns.
- Changed-Python Ruff audit: **passed** after limiting the check to changed/new
  Python files. Whole-repository Ruff is not a clean baseline (652 legacy
  findings, primarily under `scratch/` and old tests).
- `python scripts/125_validate_reviewer_completion.py`: **passed** after the
  manuscript/result update.
- `git diff --check`: **passed**.
- All changed or new JSON files parsed successfully in the independent scan.
- Canonical second-confirmation false-path test observed zero temperature reads,
  zero model fits, and zero outcomes. A forged `scoring_authorized: true` file
  is rejected because authorized execution requires the canonical path and
  recomputed hash-bound roster.
- Visual inspection of the main calibration and saturation figures found the
  1:1 line, domain colors, network summaries, residual panel, and long-gap
  saturation contrast legible and consistent with captions.

## Commit and release hygiene

- Recomputable v11 raw daily panels, per-placement loss tables, and auxiliary
  station-day tables are ignored rather than added as a roughly 376 MiB
  generated payload. Compact aggregate evidence remains eligible for commit.
- The changed/new text scan found no API key, access-token, client-secret,
  password, authorization-header, or bearer-token match.
- Existing release-candidate archives contain no `private/`, `.git/`, raw-data,
  attachment, credential, secret, or token path match.
- Required package-manifest paths all exist and are either already tracked or
  eligible compact artifacts for the final commit. Large empirical placement
  predictions are explicitly classified as regenerable local outputs, and the
  v9 package points to the compact Markdown completion audit rather than an
  ignored JSON path.

## Final acceptance conditions

Before calling the user goal complete, the final committer must:

1. integrate the completed second-confirmation result only after checking the
   recomputed canonical gate, three-network attrition record, and post-scoring floor;
2. regenerate the amendment-aware goal audit from the actual scoring schema;
3. rerun the targeted changed-file tests, reviewer-completion validator, Ruff,
   JSON parsing, `git diff --check`, and package-path consistency check;
4. stage only intended compact/public artifacts, inspect the staged diff, and
   commit it;
5. report the remaining operational decision-utility, author, DOI, and
   provider-permission gaps rather than claiming they were completed; preserve
   the bounded LSTM, air2stream-equivalent/US-only, descriptive heterogeneity,
   and planted-counterpart boundaries.

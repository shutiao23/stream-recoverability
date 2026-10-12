# WRR claim-binding audit — F19 (overstated reproducibility) and F21 (figure/SI/caption inconsistency)

Independent read-only audit of whether the live WRR manuscript and SI are bound to the
evidence their prose names. No file was modified except this report and
`results/wrr_submission_ready/amendments/manuscript_audit/claim_binding_table.csv`.
Registered in git as untracked; the coordinator commits.

## 0. Audited revision (the target moved while the audit ran)

The coordinator edited the manuscript three times during the audit (10:25:47, 10:29:00,
10:34:17) and the claim registry once (10:29:00). Every line number below is pinned to the
revision in this table; the two outputs must be read against it.

| file | sha256 (first 16) | mtime (UTC) |
|---|---|---|
| `paper/wrr/wrr_manuscript.tex` | `b8896c288799a2f4` | 2026-10-12 10:34:17 |
| `paper/wrr/wrr_supporting_information.tex` | `ac9b408c68601ad5` | 2026-10-12 10:26:38 |
| `results/wrr_submission_ready/claim_registry.csv` | `5ab529b3cc3f7483` | 2026-10-12 10:29:00 |
| `paper/wrr/README.md` | `0519ca3ac1e2d333` | 2026-10-12 01:06:20 |
| `scripts/223_wrr_build.py` | `2e24a3087ea40982` | — |
| `scripts/254_wrr_claim_binding_check.py` | `cde6ba6a7d33a568` | — |
| `paper/wrr/wrr_manuscript.pdf` | `ab96efd935b8fcba` | built 10:26:39 |
| `paper/wrr/wrr_supporting_information.pdf` | `346120fbcf7047f2` | built 10:26:39 |

Two values were corrected **in the manuscript only** during the audit and are therefore
recorded here as findings against the other copies (SI, registry, build script, PDF):

* the crossing interval: 76 → 77 days (manuscript lines 627 and 646 now say `[77,107]`);
* the 90-day grid point: `-0.019 to +0.027, positive in 57%` → `-0.018 to +0.026, positive in 55%` (manuscript lines 623–624).

Page counts, from `pdfinfo` at audit time (the task brief's "48 / 9 pages" is wrong for the SI):
manuscript **48** pp (draft layout), SI **11** pp, published layout **27** pp. The manuscript
PDF predates the 10:29 and 10:34 source edits: it still prints `[76, 107]` and
`-0.019 to +0.027, positive in 57%` (verified by `pdftotext -layout`), so the submission copy
contradicts its own source and `tests/test_wrr_submission.py::test_built_pdfs_are_current`
(pdf mtime 10:26:39 < manuscript mtime 10:34:17) cannot pass now.

Evidence-identity vocabulary used below: development panel / retrospective reserved holdout /
sealed USGS confirmation / opened-panel exploratory post-open / schematic.

## 1. Counts

The CSV has 84 claim nodes in 14 columns. Statuses: `bound`, `value-ok-but-scope-unclear`,
`unbound`, `overstated`; caption nodes additionally use `partial` / `fail` (they assert
identity–n–units–error-bar, not a numeric value).

**Headline nodes (key points 3 + abstract 10 + conclusions 7 = 20)** — the regions the registry governs:

| status | count | nodes |
|---|---|---|
| bound | 4 | AB-1 (S1 panel counts), AB-4 (sealed −7.9/−10.2/−5.8), AB-5 (−9.4 on 15 networks), AB-8 (15.1%) |
| value-ok-but-scope-unclear | 10 | KP-1, KP-3, AB-6, AB-7, AB-9, CN-1, CN-3, CN-4, CN-6, CN-7 |
| unbound | 0 | — |
| overstated | 6 | KP-2, AB-2, AB-3, AB-10, CN-2, CN-5 |

**Caption nodes (10 main figures + 12 main tables + 1 SI table + 5 SI figures = 28):**
8 pass/bound, 15 partial, **5 fail** (CAP-3 Figure 3, CAP-5 Figure 5, CAP-6 Figure 6,
CAP-24 Figure S1, CAP-27 Figure S4).

**All other nodes (main text 9, SI prose 14, registry 3, tooling 4, README 3, Open Research 3 = 36):**
bound 8, value-ok-but-scope-unclear 2, **unbound 20**, overstated 6.
Overall: 84 rows — bound 20, scope-unclear 12, unbound 20, overstated 12, partial 15, fail 5.

## 2. Every headline number, against its artifact

All artifact values were read from the files named; nothing was re-run.

| node | where (tex line) | claim | registry row / may_enter | artifact value | verdict |
|---|---|---|---|---|---|
| KP-1 | 68 | support is "a screening axis, not a universal law" | L1 / False | qualitative | value-ok-but-scope-unclear; hedged, but barred row |
| KP-2 | 69 | 9.7→2.5% at 70% retention; empirical-arm gain unresolved | V17-H2, V17-A1 / **False** | `step10_confirmation/verdict.json`: −7.12965 pp, CI [−8.96566, −5.35736]; length 9.6646% → certificate 2.5350%; `arm_contrasts.csv` reserved empirical −0.70696 pp [−2.35601, +0.05445] | **overstated** (values bound; barred from this region) |
| KP-3 | 70 | 2422 real years; rules disagree; wholly-hidden counts use a proxy | D1 True, D2 False | `threshold_disagreement.csv` 15.070190% | value-ok-but-scope-unclear (proxy correctly labelled) |
| AB-1 | 78–79 | 5114 station-years, 146 networks, 51524 outages | S1 / True | `step3_cases/summary.json` 146 / 457 / 5114 / 51524 | **bound** |
| AB-2 | 79–82 | cuts consequential errors 9.7%→2.5%, "about [−8.97,−5.36] points" | V17-H2 / **False** | verdict.json as above | **overstated** (value bound; retrospective scope stated, registry bar violated) |
| AB-3 | 82 | "the empirical arm is unresolved" | V17-A1 / **False** | interval contains zero | **overstated** (correct hedge, barred row) |
| AB-4 | 82–84 | sealed USGS: 39 HUC4 networks, 8973 cases, ≈−7.9 ([−10.2,−5.8]) | P0-07-POOL / True | `p0_07_sealed_confirmation/verdict.json` −7.94360, CI [−10.15399, −5.75346]; 39/91/8973, `scored_once: true` | **bound** |
| AB-5 | 84–85 | ≈−9.4 points on the 15 outcome-clean networks | P0-07 / True | `amendments/sealed_usgs_prior_access_diagnostic/clean_subset_contrasts.csv` 15 networks, 26 stations, 1923 cases, −9.42085, CI [−12.43519, −6.03142] | **bound** (registry notes contradict it — RG-1) |
| AB-6 | 85 | "the empirical-arm gain is smaller but non-zero" | P0-07 / True | sealed empirical −1.74444, CI [−2.98195, −0.68215] | value-ok-but-scope-unclear (antecedent panel unstated; key point 2 says the empirical gain is *unresolved*) |
| AB-7 | 86–87 | continuum/crossover/dilation "stay exploratory outside that seal" | L1,L3,L7 / False | amendment label `exploratory_post_open`; "Nothing here may be moved into a headline" | value-ok-but-scope-unclear (named, no number, correctly disclaimed) |
| AB-8 | 87–89 | 2422 real incomplete years; 15.1% disagreement | D1 / True | 15.070190% | **bound** |
| AB-9 | 89–90 | proxy PPV "0.74 on scored cases" | D2 / **False** | `peak_proxy_bridge/summary.json` sealed designed PPV 0.73668, CI [0.70899, 0.76118], n=8973 | value-ok-but-scope-unclear (value right, population unnamed, barred row) |
| AB-10 | 90–91 | difficulty screening "can thin high-elevation catchments unless stratified" | R1 / **False** | text 1059–1060: dev ρ=−0.26 p=0.011; reserved ρ=−0.27 **p=0.077** | **overstated** (stated flatly; barred; reserved interval includes zero) |
| CN-1 | 1453–1457 | "we do not claim an unconditional proportion law" | L1 / False | qualitative | value-ok-but-scope-unclear (required hedge) |
| CN-2 | 1457–1459 | retrospective 36-network holdout: 9.7%→2.5% at 70% on pooled designed outages | V17-H2 / **False** | verdict.json | **overstated** (value bound, scope stated, registry bar violated) |
| CN-3 | 1459–1463 | continuum/crossover/dilation exploratory | L1,L3,L7 / False | as AB-7 | value-ok-but-scope-unclear |
| CN-4 | 1466–1468 | "Operational gain under the agencies' own outage geometry is not established on the empirical arm" | V17-A1 / **False** | CI contains zero | value-ok-but-scope-unclear (correct hedge) |
| CN-5 | 1468–1470 | "can thin high, steep, donor-poor catchments unless thresholds are applied within strata" | R1 / **False** | US GAGES-II subset only (140/204 stations, 57 networks) | **overstated** (no subset qualifier, no exploratory label) |
| CN-6 | 1469–1472 | maintenance benefits and "annual peak never observed" counts not retained | A4, D2 / False | A4 exploratory; D2 proxy_quantified | value-ok-but-scope-unclear (correctly withdrawn) |
| CN-7 | 1478–1480 | treat autumn maintenance and regulatory hottest-7 claims as unvalidated | A4, REG / False | as above | value-ok-but-scope-unclear (correct hedge here; see MT-9 for the main text) |

## 3. Registry-forbidden claims still in the abstract, key points or conclusions

`may_enter_abstract_or_conclusions = False` for 17 of 24 registry rows. Hits in the restricted
regions (full sentences, current lines):

1. **V17-H2** — abstract 79–82: "a frozen hottest-30 screen on a retrospective 36-network holdout cuts consequential errors from 9.7\% to 2.5\% at 70\% retention (about $[-8.97,-5.36]$ points)"; key point 2 line 69; conclusions 1457–1459. The row is `False / retrospective_only`, note: "Not independent unseen confirmation for the full research programme; 28/36 reserved networks have prior use."
2. **V17-A1** — abstract 82 ("the empirical arm is unresolved"); key point 2 line 69 ("empirical-arm gain unresolved"); conclusions 1466–1468.
3. **D2** — abstract 89–90 ("a proxy whose positive predictive value for a wholly unobserved realised peak is 0.74 on scored cases"); registry `False / proxy_quantified`, whose note says the counts "remain proxy-based and are labelled as such".
4. **R1** — abstract 90–91 and conclusions 1468–1470; `False / pending_new_confirmation`.
5. **L1/L3/L7** (named, no numbers, explicitly disclaimed) — abstract 86–87; conclusions 1459–1463.
6. **A4/REG** (named as unvalidated) — conclusions 1469–1472 and 1478–1480.
7. **C14** (qualitative hedge only) — conclusions 1445–1450: "A pooled conformal interval is a statement about a population of networks, not an automatic guarantee at a single new site".

The automated checker does not catch 1–3: `scripts/254_wrr_claim_binding_check.py`
lines 99–113 recompute V17-H2 and V17-A1 as *allowed* checks, `BARRED_NUMBERS` (lines 140–148)
does not list them or D2's PPV, and `REGIONS["conclusions"] = (1328, 1358)` (lines 33–37) does
not contain the live Conclusions at 1451–1480. Its stored output
(`results/wrr_submission_ready/claim_binding_check.json`, 10:09) reports `hard_ok: true` against
a revision that no longer exists.

## 4. Cross-consistency

**Title.** Manuscript 52–53: "Support-conditioned screening of incomplete river-temperature
years: retrospective evidence from 146 networks". SI 18–19: "Supporting Information for
'Measure missingness where the statistic lives: a continuous screening law for gap-affected
stream-temperature records'". Two different articles; the SI title is an older working title
and is the first thing a reviewer sees in the SI PDF. Abstract/conclusions agree with the
manuscript title (146 networks line 79, 36-network holdout 80, "retrospective" 1457).

**SI numbering (S-items).** The SI's own contents list (line 32) says "Text S1 to S6". The
compiled SI PDF has eight numbered sections: S1 Data sources, S2 Quality control, S3 Protocol
history, S4 Confirmation/transport/amendment register, S5 Predictions that failed, S6 Runs that
were discarded, S7 Verification and reproduction, S8 Supporting figures. "Figures S1 to S5" and
"Table S1" are correct.

**SI → article cross-references.** All five are stale by one major section (the aux file gives
the real numbers): SI line 89 "Section 5.7" → real 4.9 (`sec:fair`); line 109 "Section 5.10" →
4.12 (`sec:deploy`); line 146 "Section 5.6" → 4.8 (corrected operating point, unlabelled);
line 155 "Section 5.9" → 4.10 (`sec:absent`); line 250 "Section 5.4" → 4.6 (`sec:sine`). None of
these is a `\ref`, so LaTeX cannot catch them.

**Main text → SI.** The manuscript contains no pointer to the SI at all: no "Figure S", "Table S",
"Text S", "supporting information" or "supplement" string anywhere in `wrr_manuscript.tex`
(case-insensitive grep). S1–S8 are therefore orphaned, and the SI figure that claims the
strongest closure ("the deployment and consequence links … are closed here", SI 301–304)
contradicts conclusions 1466–1468 ("Operational gain under the agencies' own outage geometry is
not established on the empirical arm").

**SI strata vs artifact.** SI 111–122 lists five documented-daily-mean providers as "USGS, FOEN,
GKD Bayern, NVE, UK Environment Agency" and four undocumented as "SYKE, ARSO, SMHI, Hub'Eau".
The artifact the sentence's numbers come from (`provider_contract_contrasts.csv`) defines the
documented stratum as `foen;gkd_bayern;lubw;nve_hydapi;usgs` — LUBW is missing from the SI list
and the transport-only UK EA is in it; Hub'Eau and SMHI are not in the 146-network panel at all.
The manuscript's own §2.2 (295–317) gets this right (LUBW documented but partially re-verified;
UK EA "for the transport panel below"; three SYKE stations flagged).

**README vs live files.** `paper/wrr/README.md`:
line 60 "the bibliography actually rendering all 18 entries" — the build renders 28 (`build_report.json`);
line 62 "The current values are 110, 118 and 126 characters; 249 words; and 196 words" — live values are
138 / 140 / 122 characters (key points), 186 abstract words, 119 plain-language words (recomputed with
the build script's own functions);
lines 4–6 and 87–89 "The Markdown in `paper_archived/v18/` remains the source of the prose and of
every number in it … A number that appears in more than one of these is checked in one place
only" — false for the amendment numbers now in the TeX: `paper_archived/v18/manuscript.md`
contains no `12.76`, no `faithful`, no `outcome-clean`, no `9.4 points` and no `provider-contract`,
while the TeX does (this is F19 in one sentence).
Page counts: the README's only page reference is the parenthetical "(rebuild for current page
count)" at line 11; the real counts are 48 / 11 / 27 (§0).

**Registry vs amendment.** `claim_registry.csv` rows 23–24 (`P0-07`, `P0-07-POOL`) still carry
"28 networks clean of outcome-bearing prior use and 18 clean of any prior use", "clean-of-outcome
subset (28 networks, 5608 cases) −8.73 pp CI[−10.68,−7.25]" and "clean-of-any-use subset
(18 networks, 3897 cases) −8.44 pp CI[−10.21,−7.06]". The live amendment says: 15 networks clean
of outcome use (26 stations, 1923 cases, −9.42 [−12.44,−6.03]); 28 networks / 45 stations clean of
outcome use (3494 cases, −8.26 [−10.35,−6.37]); 18 networks / 21 stations clean of any prior use
(1794 cases, −7.27 [−10.28,−4.58]); networks clean of any prior use have 187 cases and are not
scored. The strings `5608` and `3897` do not occur anywhere under `results/` (grep). Row 24's
statement "~8.7 pp on the 28 outcome-clean networks" attaches the station-level subset label to a
contrast the artifact reports as −8.26. Row 8 (`L3`) still says "76-107 days".

## 5. Figure and table captions (task 4)

Test applied to each caption: does it state n (and the level), the endpoint and units, the meaning
of any interval/error bar, and the evidentiary identity? `pass` = all four where applicable;
`partial` = identity present but n/units/error bars missing; `fail` = identity absent or wrong.

| # (compiled) | label / caption line | n | units | error bar | identity | verdict |
|---|---|---|---|---|---|---|
| Fig 1 | `fig:frame` 183 | n/a (schematic) | n/a | n/a | schematic, and gradients called mechanism diagnostics "not the sealed confirmation" | **pass** |
| Fig 2 | `fig:design` 384 | absent | n/a (flow) | n/a | all four classes named (retrospective holdout with mixed prior access / sealed USGS / NVE probe) | partial |
| Fig 3 | `fig:calib` 566 | **absent** | **absent** (coverage %, °C) | **absent** (90% conformal, pooled vs per-network) | **absent** (reserved panel only in the body text) | **fail** |
| Fig 4 | `fig:law` 646 | absent (110 networks / 2000 draws) | days, AUC implied | "network-clustered intervals" stated; [77,107] matches artifact | explicit: "opened panel (not the sealed USGS confirmation)" | partial |
| Fig 5 | `fig:mech` 707 | **absent** | **absent** | **absent** | **absent** (development cases only in body text) | **fail** |
| Fig 6 | `fig:hydro` 849 | **absent** (140/204 stations, 57 networks) | **absent** (ρ, °C) | **absent** (CIs are in the text) | **absent** ("United States subset" only; GAGES-II, exploratory) | **fail** |
| Fig 7 | `fig:frontier` 900 | absent | absent | absent | explicit (development / reserved panel) | partial |
| Fig 8 | `fig:season` 1044 | yes, "6472 real interior gaps" | start month / days | n/a | explicit ("descriptive"; "exploratory … not a verified operational benefit") | **pass** |
| Fig 9 | `fig:repr` 1077 | absent | absent | absent | explicit (reserved panel) | partial |
| Fig 10 | `fig:deploy` 1183 | yes, "2422 real incomplete station-years" | counts | n/a | explicit (real incomplete, no truth) | **pass** |
| Tab 1 | `tab:map` 213 | n/a | n/a | n/a | conceptual | **pass** |
| Tab 2 | `tab:quantities` 389 | n/a | **absent** (units only in body) | n/a | methods | partial |
| Tab 3 | `tab:axes` 595 | absent (development cases) | AUC, endpoint scaling given | "95% CI" in the column header | explicit (development) | partial |
| Tab 4 | `tab:sweep` 651 | absent | AUC, °C, days | 95% clustered CI defined in the note | explicit (development) | partial (and the k=90 upper bound is wrong, MT-7) |
| Tab 5 | `tab:dilate` 740 | absent | days, AUC | no interval on the gain column | explicit (development) | partial |
| Tab 6 | `tab:sine` 795 | absent | AUC, endpoint scaling | none | explicit (development) | partial; also a plain `tabular` with no `\tabletext`, so it keeps the 20 pt double spacing |
| Tab 7 | `tab:tol` 873 | absent (36 networks) | % | none | explicit (reserved panel, 70% retention) | partial |
| Tab 8 | `tab:abl` 920 | absent | % | none | explicit (development, out-of-fold) | partial |
| Tab 9 | `tab:fair` 969 | absent (28493 cases) | % | none | explicit (development, air forcing available) | partial |
| Tab 10 | `tab:arms` 1007 | yes (cases column, e.g. 14995) | % | 95% CI column | explicit per panel, but the sealed panel is absent | **pass** |
| Tab 11 | `tab:repr` 1082 | absent | %, ρ, points | retention SD defined | explicit (reserved panel) | partial |
| Tab 12 | `tab:deploy` 1127 | yes (2422 station-years) | counts | n/a | explicit (real incomplete); note defines the proxy and its PPV and points to the section that measures it | **pass** |
| Tab S1 | SI 58 | nine providers | n/a | n/a | role column | **pass** (but silently omits Hub'Eau, which SI prose then discusses) |
| Fig S1 | SI 301 | absent | absent | absent | claims "every link is labelled with the section" using the stale 5.x refs, and "deployment … closed here" contradicts the conclusions | **fail** |
| Fig S2 | SI 313 | n/a | n/a | n/a | schematic; information barrier explicit | **pass** |
| Fig S3 | SI 319 | "eleven complete years per station" | absent | absent | panel identity absent | partial |
| Fig S4 | SI 325 | **absent** | **absent** | "network-clustered intervals" only | **absent**; it includes the post-fix noise panel (an amendment) without saying so | **fail** |
| Fig S5 | SI 331 | absent | absent | absent | "networks never used for fitting" conflicts with the corrected "never used" label (defensible only under the narrow reading in `AMENDMENT_prior_access_sealed_panel.md` lines 35–37) | partial |

## 6. Open Research statement, LUBW, provider strata (task 5)

**Quoted (manuscript 1503–1512):** "All analysis code, derived artifacts, figures, the editable
draw.io sources of the schematic figures and the frozen pre-registration are in the accompanying
repository. A claim registry … records each headline claim's artifact, endpoint, unit,
denominator, evidence type and whether it may enter the abstract or conclusions. An automated
audit checks a declared set of archived manuscript numbers against artifacts; **it is not yet a
full semantic binding of every live \TeX\ numeral.** Input-file hashes for the 146 study networks
are in … `current_data_manifest.csv`. A permanent archive of the repository and a DOI will be
deposited on acceptance."

That statement is honestly narrowed. The overstatement sits in the **SI's** version (267–293):
"Every table cell and audited inline number in the article is re-derived from the artifacts by an
audit script that the test suite runs" and "The claim registry binds every number allowed into the
abstract, key points and conclusions to an artifact and is checked by
`scripts/254_wrr_claim_binding_check.py`, which recomputes the allowed numbers and flags any
barred number that appears in those regions." Precisely:

* `scripts/221_v18_audit_manuscript.py` audits `paper_archived/v18/manuscript.md` (line 34), not
  the TeX; its 92 checks pass, but they are checks of the archived markdown's numbers block.
  The TeX's amendment numbers (12.76/15.16, −5.7/−6.6, −9.4, 0.74, [77,107], 5.98→6.03) are not in
  that markdown (grep) and therefore not in that audit.
* `scripts/254_wrr_claim_binding_check.py` scans the wrong conclusions region and treats two
  barred rows as allowed (§3); its stored clean verdict is dated 10:09, before the live revision.
* Registry rows 23–24 print numbers that contradict their own amendment artifact (§4).

So the residual F19 exposure is: (i) no check binds the live TeX; (ii) the one script that does
scan the abstract/key points is mis-scoped and omits exactly the claims that matter; (iii) the
registry's own notes are not artifact-bound.

**LUBW.** The restriction is stated twice — manuscript Open Research 1492–1494 ("One, LUBW,
reserves copyright: its raw values are therefore \emph{not} redistributed with this paper, and the
seven LUBW networks are available only through LUBW's own service"; seven confirmed against
`network_split.csv`) and SI 52–55 — but **not** in §2.2 where LUBW's data are first described
(289–317). Suggested one-clause fix at 299–300.

**Provider daily-mean strata.** Stated in §2.2 295–317 (five documented incl. LUBW with its
partial-verification caveat; CHMI/RWS/SYKE/ARSO as non-conforming; the three SYKE stations
flagged) and in the SI S2, but the SI enumeration is inconsistent with the artifact stratum (§4).
`measurement_provenance_dictionary.csv` has 12 providers (adds SMHI, UK EA, Hub'Eau);
`metadata/data_rights.csv` is artifact-level, not provider-level.

**Licence count.** Open Research 1487–1490 says "Eight of the eleven publish under a named open
licence" and then lists **nine** licences: US public domain; CC BY 4.0 for CHMI, GKD Bayern and
SYKE; OGL v3.0 UK EA; opendata.swiss FOEN; NLOD/CC BY NVE; CC BY 4.0 SE SMHI; Licence Ouverte
Hub'Eau. Hub'Eau is not among the eleven providers named at 1484–1485, yet its licence is counted
here and its data are described in the SI as a stratum (SI 117). Either the sentence or the list
is wrong; the provider list and the count must be reconciled.

## 7. Amendment numbers vs amendment artifacts (task 6) — all match except as noted

| claim (manuscript line) | artifact | value read | verdict |
|---|---|---|---|
| noise 5.98→6.03, 6.21→6.22, MAE 0.2361→0.2363 (1219–1220) | `step22_noise_post_fix/noise_sensitivity.json` | dev 5.983926→6.033061; reserved 6.205440→6.218643; dev MAE 0.2361427→0.2363170 | **match** (MAE is development-only, unlabelled) |
| paired change +0.049 (−0.036,+0.150) / +0.013 (−0.175,+0.185) (1221–1222) | same | +0.049135 [−0.035676,+0.149932]; +0.013203 [−0.174719,+0.185126] | **match** |
| AR(1) 2.25×, step 2.12×, 5.95/6.21 dev, 6.19/6.43 res (1225–1227) | `.../REPORT.md` 109–110; `scenario_contrasts.csv` | 2.252930, 2.121823; 5.952339, 6.212052; 6.192237, 6.429892 | **match** |
| "moves the contrast by at most one point", MAE 0.30 °C (1228–1230) | `scenario_contrasts.csv` | reserved bias −0.5 °C: 7.235279 vs clean 6.205440 = **+1.0298** points, change CI [0.349082, 1.823148] excludes zero; dev bias +0.5 °C MAE 0.297595 | **mismatch (overstated)** |
| crossing interval [77,107] days (623–624, 646) | `e6_support_width_uncertainty/crossover.json` | median 90.9378, CI [77.112465, 107.023203]; P(no crossover) 0.000; first non-positive grid 182 | **match** |
| "moves between 85 and 102 days across the tolerance grid" (627) | `REPORT.md` 159 | 101.6 / 91.0 / 84.6 days | **match** |
| Table 4 k=90 interval (−0.018, **0.027**) (665) | `curve_with_ci.csv` | point 0.001581, low −0.017982, high **0.025461**, p 0.549 | **mismatch (table high bound)** |
| 90-day interval in body text (623–624) | same | −0.018 to +0.026, 55% | **match** (fixed at 10:29) |
| donor +0.084 (0.064–0.110) (697) | `step5_mechanism_equal_k/REPORT.md` 53–58, 114–115 | +0.0840, 95% CI 0.0637–0.1100; frozen +0.0824 | **match** |
| faithful 12.76% vs 15.16%, −2.40 [−3.20,−1.62], 1200 draws (959) | `faithful_baseline/comparison.csv`, `contrasts.csv`, `summary.json` | 12.757519 / 15.161619; rate diff −0.024041 [−0.031993,−0.016204]; `bootstrap_draws` 1200 | **match** |
| proxy PPV 0.74 (0.71–0.76), sensitivity 0.87, 3.1% (1141, 1150–1152) | `peak_proxy_bridge/summary.json` | 0.736679 [0.708991, 0.761183]; sensitivity 0.866180; proxy-clear hidden 0.03125; 12.5235 expected true-hidden ([12.05,12.94]) from 17 flagged | **match** |
| prior access: 24/39 outcome-used, 15 clean, 4 never used, −9.4 [−12.4,−6.0], −3.7 [−5.8,−1.6], 45 stations −8.3 [−10.4,−6.4] (367–374) | `prior_access_audit_sealed_usgs.csv`; `clean_subset_contrasts.csv` | 39 networks; 24 with outcome use; 15 clean networks; 4 never-used networks; 45 clean stations; −9.4208 [−12.4352,−6.0314]; empirical −3.6511 [−5.8006,−1.6165]; stations-clean −8.2648 [−10.3525,−6.3700] | **match** |
| provider contract −5.7/−6.6 vs −6.4/−7.1, 84/29 networks (309–311) | `provider_contract_sensitivity/provider_contract_contrasts.csv` | −5.664559 [−6.482764,−4.867344] 84; −6.583184 [−7.865921,−5.277145] 29; −6.345418; −7.129654 | **match** |
| cold-season support beats length; AUC 0.876/0.897 vs 0.819; gaps −0.0050/−0.0059; grouped 0.905 vs 0.813 (585–589) | `winter_regulatory/cold_support_contrast.csv` | 0.876119 / 0.896617 / 0.819068; rate gaps −0.005896 and (0.005405−0.010424)=−0.005019; grouped 0.904849 vs 0.813230 | **match** |

## 8. Prioritised fix list

Order: things that break the build or contradict an artifact first, then governance, then scope.

1. **`scripts/223_wrr_build.py:102`** — `HEADLINE_NUMBERS` still contains `"[76,107]"`. The live TeX
   (627, 646) says `[77,107]` and the artifact is [77.11,107.02]. Verified: `missing_numbers()` returns
   `['[76,107]']`, so `make wrr-check` / `make wrr` now fail. *Fix:* `"[77,107]"`.
2. **`paper/wrr/wrr_supporting_information.tex:245`** — "the bootstrap gives 76 to 107 days".
   Artifact: 77.11 to 107.02. *Fix:* "77 to 107 days".
3. **`results/wrr_submission_ready/claim_registry.csv:23-24`** — the clean-subset numbers
   (28 networks/5608 cases/−8.73; 18/3897/−8.44) match no live artifact and mislabel station-level
   subsets as networks. *Fix:* 15 networks/26 stations/1923 cases/−9.42 [−12.44,−6.03]; 28
   networks/45 stations/3494 cases/−8.26 [−10.35,−6.37]; 18 networks/21 stations/1794 cases/−7.27
   [−10.28,−4.58]; 187 cases not scored. Also fix row 24's statement ("~8.7 pp on the 28
   outcome-clean networks" → "~9.4 pp on the 15 outcome-clean networks; ~8.3 pp on the 45
   outcome-clean stations") and row 8's "76-107".
4. **`scripts/254_wrr_claim_binding_check.py:33-37`** — `REGIONS["conclusions"] = (1328, 1358)`
   does not contain the Conclusions (1451–1480). *Fix:* (1451, 1480) — and make the region
   boundaries derive from `\section{Conclusions}` rather than constants.
5. **`scripts/254_wrr_claim_binding_check.py:99-113,140-148`** — V17-H2 and V17-A1 are recomputed
   as allowed while the registry marks them `False`; their numbers (9.7, 2.5, 8.97, 5.36) and D2's
   0.74 are not in `BARRED_NUMBERS`. *Fix:* either the coordinator's intended policy is that the
   retrospective holdout may be headlined (then change the registry rows to `True` and record why),
   or move the two rows out of `allowed_checks` and add their numbers plus `\b0\.74\b` (D2) to
   `BARRED_NUMBERS`. The current state is the one combination that cannot be defended.
6. **`paper/wrr/wrr_supporting_information.tex:18-19`** — SI title is a different article title.
   *Fix:* "Supporting Information for ``Support-conditioned screening of incomplete
   river-temperature years: retrospective evidence from 146 networks''".
7. **`paper/wrr/wrr_supporting_information.tex:89,109,146,155,250`** — "Section 5.7/5.10/5.6/5.9/5.4"
   should be 4.9/4.12/4.8/4.10/4.6 (aux-confirmed). *Fix:* hard-code the right numbers (the SI is a
   separate document so `\ref` is unavailable) or cite the subsection titles.
8. **`paper/wrr/wrr_supporting_information.tex:32`** — "Text S1 to S6"; compiled SI has S1–S8.
   *Fix:* "Text S1 to S8".
9. **`paper/wrr/wrr_supporting_information.tex:111-122`** — strata enumeration omits LUBW, includes
   the transport-only UK EA, and names Hub'Eau/SMHI which are not in the 146-network panel, while
   quoting numbers from the artifact stratum `foen;gkd_bayern;lubw;nve_hydapi;usgs`. *Fix:* align the
   list with the artifact and say where the transport providers and Hub'Eau sit.
10. **`paper/wrr/README.md:60,62`** — "all 18 entries" (28 rendered) and "110, 118 and 126
    characters; 249 words; and 196 words" (138/140/122; 186; 119). *Fix:* update, or replace both
    sentences with a pointer to `build_report.json`.
11. **`paper/wrr/README.md:4-6,87-89`** (and the TeX header comment 5–8) — "the source of the prose
    and of every number in it" / "checked in one place only". The archived v18 markdown lacks the
    amendment numbers (12.76, outcome-clean, −9.4, provider-contract) that the TeX prints. *Fix:*
    either carry the amendment numbers into the v18 numbers block and re-run 221, or state that
    the TeX holds amendment numbers that 221 does not cover.
12. **`paper/wrr/wrr_supporting_information.tex:301-304`** — "the deployment and consequence links …
    are closed here" contradicts manuscript 1466–1468 ("Operational gain under the agencies' own
    outage geometry is not established on the empirical arm"). *Fix:* "the deployment link is
    closed for pooled designed outages and remains open on the empirical arm".
13. **`paper/wrr/wrr_supporting_information.tex:135`** — cites
    `multi_agency_ingest/QC_SUMMARY.json`, which does not exist. *Fix:* cite
    `multi_agency_ingest/uk_ea/qc_ledger.csv` and `.../uk_ea/frozen_sensor_sensitivity.csv` and
    drop or substantiate "one of them inside a hottest-30 window" (no located artifact states it;
    `ingest.json` lines 110–111 give the two frozen runs).
14. **`paper/wrr/wrr_manuscript.tex:665`** — Table 4 k=90 upper bound `0.027`; artifact 0.025461 and
    the corrected body text say 0.026. *Fix:* `(+0.002, (-0.018, 0.026))`.
15. **`paper/wrr/wrr_manuscript.tex:1228-1230`** — "at most one point" under ±0.5 °C annual bias.
    Artifact: reserved −0.5 °C moves the contrast by +1.03 points with a change CI excluding zero.
    *Fix:* "by up to 1.0 point (reserved, −0.5 °C; change interval 0.35 to 1.82 points)".
16. **`paper/wrr/wrr_manuscript.tex:89-90`** — abstract "0.74 on scored cases". *Fix:* "0.74 on the
    sealed designed cases (n = 8973; network-clustered interval 0.71–0.76)" — or move the PPV out of
    the abstract if D2 stays barred.
17. **`paper/wrr/wrr_manuscript.tex:1487-1490`** — "Eight of the eleven" followed by nine named
    licences including Hub'Eau. *Fix:* reconcile: "Nine of the twelve" with Hub'Eau added to the
    provider list, or drop Hub'Eau from the parenthetical.
18. **`paper/wrr/wrr_manuscript.tex:1399-1403`** — regulatory framing ties the study's 7-day
    *daily-mean* endpoint to 7-DADMax without disclosing the mismatch (registry REG is
    `rewrite_required`). *Fix:* one clause: "regulatory criteria are defined on a seven-day mean of
    daily maxima, while the seven-day endpoint here is a mean of daily means; the illustration is
    not a compliance validation."
19. **`paper/wrr/wrr_manuscript.tex:90-91` / `1468-1470`** — the elevation-thinning claim is
    asserted without the exploratory label and without the subset (US GAGES-II, 140/204 stations);
    the reserved-panel correlation (p=0.077) does not exclude zero. *Fix:* add "on the US subset,
    exploratory" and report both panels' intervals.
20. **Rebuild the PDFs after these edits.** The 10:26 manuscript PDF prints `[76, 107]`,
    `-0.019 to +0.027, positive in 57%` and therefore contradicts the 10:34 source; the SI PDF
    (11 pp) also predates any SI fixes made now.

## 9. Limits of this audit

* Read-only: no pipeline was re-run. Numeric matches are comparisons of printed values against
  stored artifacts (JSON/CSV/parquet), except ratios recomputed by hand (e.g. 9.24−2.93 = 6.31 →
  59%; 0.005405−0.010424 = −0.005019) which are noted as such.
* The registry has no rows for several body-text numbers (e.g. the judgement section's
  6.86/1.97/1.53/0.36, the calibration deciles 6.2/1.6, the 0.98/1.85/0.26 transported risks, the
  trend RMSEs 0.143/0.044/0.048/0.041). They are outside both 221 and 254 and are unbound by
  construction; none of them appears in the abstract, key points or conclusions.
* The files were edited while the audit ran; a later revision may legitimately differ. The hashes
  in §0 are the ones every line number here refers to.
* I did not verify `figures/*.pdf` contents, the draw.io sources, or the repository/DOI promise.

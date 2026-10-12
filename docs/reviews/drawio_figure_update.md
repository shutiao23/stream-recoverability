# draw.io schematics: sources and exports brought in line with the current manuscript

Scope: the five schematic figures that the repository draws in draw.io and
renders through `scripts/205_v17_drawio_export.py` —

| source | PDF | where it appears |
|---|---|---|
| `figures/v17/drawio/f0_problem_frame.drawio` | `figures/v17/f0_problem_frame.pdf` | SI Fig. S2 |
| `figures/v17/drawio/f1_system_architecture.drawio` | `figures/v17/f1_system_architecture.pdf` | SI Fig. S3 |
| `figures/v17/drawio/f2_experiment_design.drawio` | `figures/v17/f2_experiment_design.pdf` | Fig. 2 |
| `figures/v17/drawio/f3_evidence_chain.drawio` | `figures/v17/f3_evidence_chain.pdf` | SI Fig. S1 |
| `figures/v17/drawio/f4_deployment_workflow.drawio` | `figures/v17/f4_deployment_workflow.pdf` | SI Fig. S6 |

Everything below was verified against `paper/wrr/wrr_manuscript.tex`,
`paper/wrr/wrr_supporting_information.tex` and the sealed artifacts, not against
the previous figures. The manuscript was being rewritten concurrently while this
update was made; the facts quoted here were re-checked against the live file at
the end of the session (the transport wording has moved to the records section,
but every number used is still present).

## 1. Why the geometry changed at all

`paper/wrr/template/agujournal2025.cls` sets `\textwidth 5.5in`, and every
schematic is included with `\includegraphics[width=\textwidth]`. The old exports
were 10.08–12.38 in wide, so the manuscript scaled them by 0.44–0.55 and an
11 px label printed at 3.7 pt: `pdftotext -bbox` on the built
`paper/wrr/wrr_manuscript.pdf` gives 3.667 pt for an 11 px label of the old
Fig. 2, which back-solves to an include width of exactly 396 pt = 5.5 in. The
independent harness `scripts/266_wrr_figure_qa.py` measures the same placement
width from the built PDFs (`implied_printed_width_pt.median = 396.012`). The
smallest labels in the old sources were 10–10.5 px and printed at 3.33–4.30 pt
(table in §7), below every journal's minimum.

At a printed width of 5.5 in (396 pt) a label of `f` px in a drawing `W` px wide
prints at `396 f / W` pt, so "at least 5 pt" is the ratio rule

```
f / W  >=  5 / 396  =  1 / 79.2
```

The five sources were therefore re-laid out at 963–998 px wide with no label
below 14 px, and `scripts/205_v17_drawio_export.py` now writes the PDF at the
printed width (`--print-width-in`, default 5.5 in) instead of at the drawing's
natural size. The paper now includes each schematic at scale 1.0, and the type
size in the PDF *is* the type size on the page — the same convention the
analysis figures already follow through
`stream_recoverability.plotting.journal` (`COLUMN_INCHES = 5.5`).

Renderer changes (all in `scripts/205_v17_drawio_export.py`):

1. `--print-width-in` (default `PRINT_WIDTH_IN = 5.5`): the SVG/PDF page is
   written at 5.5 in wide, with the drawing kept in its authoring coordinates
   through the `viewBox`; the exported SVG is at print size too.
2. `html=1` labels with inline `<b>` / `<i>` runs are rendered as such, so the
   sources use draw.io's own rich-text labels (titles are bold, body regular)
   instead of one weight per box.
3. The CLI is now `argparse`-based (same positional `.drawio` arguments, so the
   Makefile target is unchanged).

The native path (`drawio -x -f pdf --crop`) still consumes the identical source;
it writes a larger page because it exports at the drawing's natural size, and at
`\textwidth` the printed type is the same, because the type-to-page ratio is
fixed by the geometry. This is recorded in `figures/v17/drawio/README.md`, which
also now states the 5 pt rule as rule 5.

## 2. `f2_experiment_design.drawio` — Fig. 2 (rebuilt)

The figure is now 12 boxes in a six-row S-flow (left box = stage, right box =
what it yields; the return edge runs leftwards through the inter-row gap), with
11 orthogonal edges and no crossing arrow. Layout: 968×920 px authoring grid,
fonts 14.5–15 px, prints 5.5 × 5.227 in.

| row | left box | right box | facts behind the labels |
|---|---|---|---|
| 1 | Nine national providers (ARSO · CHMI · FOEN · GKD Bayern · LUBW · NVE · Rijkswaterstaat · SYKE · USGS) | River-only, complete-year filter: lakes, seas, canals, estuaries, deltas out; a year with any missing day has no truth; fewer than four complete years out; **146 networks · 457 stations · 5,114 completely observed station-years** | `\subsection{Records, and what each dataset is for}` ("nine national providers … Waterbody class was assigned per network and non-river objects … are excluded"; "Reference series are never imputed: a calendar year with any missing day supplies no truth"; "Stations with fewer than four fully observed calendar years are excluded"; "146 networks, 457 stations and 5114 fully observed station-years") |
| 2 | Split at the network level, never at the station-year level; stratified on provider × donor regime; **110 development · 36 reserved** | Reserved panel: retrospective holdout; 28 of 36 networks have earlier programme use; not an unused confirmation set | same subsection ("Networks — never station-years — were split into development and reserved, stratified on provider and on donor regime, with the seed recorded before any scoring. This gives 110 development and 36 reserved networks"; "That reserved panel is a retrospective network holdout for the frozen v17 screen: 28 of 36 networks have prior development, descriptive or scoring use in earlier programme stages"; "It is not an unused confirmation set for analyses developed after opening") |
| 3 | Outages designed, configuration frozen: **51,524 cases** on two arms; 40,704 development · 10,820 reserved; declared before the panel opened; matched retention, at least five points, network-clustered interval excluding zero | Reserved panel opened once: **9.7% → 2.5% at 70% retention**, −7.13 points [−8.97, −5.36]; the empirical arm is unresolved | `\subsection{Gap design}`, `\subsection{Test protocol}` ("The design yields 51524 cases, 40704 development and 10820 reserved"; "The pre-registered primary criterion, frozen before the reserved panel was opened, is that at the retention of the matched length rule the screen must reduce the consequential-error rate by at least five percentage points with a network-clustered interval excluding zero"), abstract ("from 9.7\% to 2.5\% at 70\% retention (about [−8.97,−5.36] points); the empirical arm is unresolved") |
| 4 | Sealed USGS confirmation: 39 HUC4 networks · 91 stations · 8,973 designed cases, outside the development programme, scored once; **−7.9 points [−10.2, −5.8]** | Prior-access audit and clean subset: 24 of 39 networks appear in earlier work; **15 outcome-clean networks: −9.4 points [−12.4, −6.0]**; a transparency diagnostic, not new confirmation | records subsection ("39 USGS HUC4 networks (91 stations; 18 HUC2 contexts; 8973 designed outage cases) … scored once"; "About −7.9 percentage points (clustered interval about [−10.2,−5.8])"; "finds 24 of the 39 networks appearing in earlier iterations, 15 networks with no outcome-bearing prior use"; "restricted to the 15 outcome-clean networks the pooled contrast is −9.4 points ([−12.4,−6.0])"; "a transparency diagnostic, not new confirmation") |
| 5 | Pre-registered transport panel: SMHI · UK EA · Hub'Eau, **32 primary networks** across three contexts, four assurance strata combinations, sealed and scored once: **−4.6 points [−6.5, −3.3]** | Primary and secondary strata: quality-checked stratum **−6.2 points [−8.4, −4.5]**, agreeing with the pooled verdict; NVE secondary stratum, **21 networks: −6.1 points [−8.7, −4.6]** | SI confirmation/transport section ("The sealed transport panel holds 53 networks: 32 primary networks from Sweden (SMHI, 16), England (UK Environment Agency, 2) and France (Hub'Eau, 14) across three climate contexts and four assurance strata combinations, plus 21 Norwegian (NVE) basins as the secondary stratum"; "pooled contrast −4.6 points ([−6.5,−3.3])"; "quality-checked stratum alone is −6.2 ([−8.4,−4.5])"; "secondary NVE stratum is −6.1 ([−8.7,−4.6])") |
| 6 | Truth-free deployment: **2,422 real incomplete station-years**, which carry no truth; the frozen screen is applied to them unchanged | Two admission rules compared: length rule vs peak-window screening **disagree on 15.1%** of the 2,422 years; the certificate instead supports abstention where the interval straddles the threshold | deployment subsection ("2422 genuinely incomplete station-years … carry no truth and have never been decided"; "they disagree on 15.1% of station-years"; "abstaining only where the interval straddles the threshold judges 92.7% at 0.42%") |

Labels dropped from the old Fig. 2, with where the fact now lives:

* the "Gate before rule (§4.7)" box (oracle ceilings +0.038 / +0.080 °C against a
  0.136 °C resolvable margin) — still in the manuscript's test-protocol
  subsection; dropped to keep the design figure inside 12 boxes;
* the GAGES-II note (140 of 204 US stations) — still in the records subsection
  and in the article's representativeness figure (`figv4_representativeness.pdf`);
  never an input to the screen;
* "marginal coverage 0.909" — present in
  `results/v17_fitness/step10_confirmation/verdict.json`
  (`coverage.marginal = 0.9085`), not in the manuscript, and dropped for space;
* "negative with an interval excluding zero in all nine agencies under
  leave-one-provider-out" — dropped for space (the reserved score and the two
  sealed panels carry the figure's argument);
* the empirical/stratified arm case counts (19,036 / 32,488) — the total and the
  development/reserved split are kept, the arm split is in the gap-design
  subsection;
* the old "36 reserved networks — sealed" wording, which asserted a sealed panel
  rather than a retrospective holdout with mixed prior access.

## 3. `f3_evidence_chain.drawio` — SI Fig. S1 (rebuilt)

The old chain used the v17 `RQ0…RQ8` labels, which no longer exist in the
manuscript. The new chain is nine links against the paper's own three linked
questions (introduction: which property of a gap governs the error, and does it
depend on the statistic; is the dependence a dichotomy or a continuum and where
does it turn over; what does conditioning change), followed by the two sealed
panels and the truth-free deployment. Every link names its question and the
evidence class the SI caption defines (sample fact / retrospective holdout /
sealed confirmation / exploratory post-open). Layout: 963×1002 px, font 15 px,
prints 5.5 × 5.723 in; the closing edge runs up the right-hand margin.

| link | label | class and source |
|---|---|---|
| 1 | Real archive: nine agencies, 146 networks, 457 stations, 5,114 fully observed station-years | sample fact (records subsection) |
| 2 | Designed outages: 51,524 cases on an empirical and a stratified arm; 40,704 development, 10,820 reserved | sample fact (gap-design subsection) |
| 3 | **Q1 · which property of a gap governs the error?** — an annual mean grows 10.2× along missing days and 1.5× along peak-window overlap; the hottest 30-day mean reverses both (3.5× and 9.6×) | sample fact (phenomenon section, "the annual mean grows 10.2× and 1.5×, while the extreme grows 3.5× and 9.6×") |
| 4 | **Q2 · two regimes or a continuum?** — the crossing is an interval, 77 to 107 days; the 90-day point is indistinguishable from zero; the conditioning set is the support dilated by about two location SDs (60 to 90 days) | exploratory post-open (continuum/dilation subsections; claim registry `L3`, `L7` are `exploratory_post_open`) |
| 5 | **Q3 · what does conditioning change?** — 36 reserved networks opened once: 9.7% → 2.5% at 70% retention, −7.13 points [−8.97, −5.36]; the empirical arm is unresolved | retrospective holdout (claim registry `V17-H2`, `evidence_type = retrospective_network_holdout`) |
| 6 | Sealed confirmation, USGS: 39 HUC4 networks, 8,973 cases, scored once: −7.9 points [−10.2, −5.8]; the 15 outcome-clean networks give −9.4 points [−12.4, −6.0] | sealed confirmation (`sealed_confirmation_single_provider_usgs`) |
| 7 | Multi-agency transport: 32 pre-registered primary networks: −4.6 points [−6.5, −3.3]; quality-checked stratum −6.2 [−8.4, −4.5]; NVE secondary stratum, 21 networks, −6.1 [−8.7, −4.6] | sealed confirmation (`sealed_multi_agency_transport_single_score`) |
| 8 | Truth-free deployment: 2,422 real incomplete station-years: the two admission rules disagree on 15.1%; wholly hidden climatological peak windows are a proxy (PPV 0.74) | see the note below |
| 9 | Consequence: admitting incomplete years raises the archive mean by about 0.5 °C and the four rules differ by less than 0.1 °C; at the 140-day limit 17 admitted years hide the peak window | sample fact (deployment subsection and its archive-composition table) |
| bar | Pooled designed outages close the loop; the empirical arm stays open. | SI caption of the figure |

Judgement call, flagged: the SI's four classes have no "deployment" class, and
the claim registry calls the deployment claim `deployment_description` and the
proxy claim `proxy_not_truth`. Links 8 and 9 are therefore tagged **sample
fact** because they are counts computed from the archive that read no truth, and
link 8's label says explicitly that the wholly hidden peak count is a proxy.
The old v17 chain had a "Deployment — closed" box; the caption's own wording
("closed for pooled designed outages and remains open on the empirical arm") is
kept in the bar instead.

## 4. `f0_problem_frame.drawio` — SI Fig. S2 (three labels corrected)

Every numeric and structural label was checked and is unchanged
(40,704 development cases; 10.2× / 1.5× / 3.5× / 9.6×; estimand equations;
support, governing-axis, and incumbent-rule boxes). Two labels were wrong and
one was re-worded; no numeric label changed:

| old | new | why |
|---|---|---|
| "One **law**, not two regimes: measure missingness on the support of the estimand … 'Timing versus length' is that **law** at the two ends of a scale" | "One **scale**, not two regimes: … 'Timing versus length' is that **scale** at its two ends" | the unconditional proportion law was withdrawn from the headlines (claim registry `L1` = `exploratory_post_open`, finding `F04`); the manuscript keeps only "the two regimes reported below are ends of one scale" |
| "the crossover is at a support width of **91 days**" | "the crossing is an **interval, 77 to 107 days**" | the bootstrap interval is [77,107] days and the 90-day grid point is indistinguishable from zero |
| "A support must be located before it can be conditioned on, so the conditioning set is the support dilated by the year-to-year wander of its own location" | "The conditioning set is the support dilated by the wander of its own location: one agency window of 60 to 90 days serves every warm-season endpoint." | wording brought to the manuscript's dilation statement ("a conditioning window dilated around the … dilation of roughly two location standard deviations on each side", "an agency needs one climatological window of 60 to 90 days rather than one per metric") |

Layout only: 998×642 px, fonts 14–15 px, prints 5.5 × 3.538 in; the two
conditioning-set arrows now share a clear band between the support row and the
governing-axis row.

## 5. `f1_system_architecture.drawio` and `f4_deployment_workflow.drawio` (labels checked, corrections made)

**f1** (SI Fig. S3), 988×808 px, fonts 14 px, prints 5.5 × 4.498 in:

* three side notes ("Fitted leave-one-year-out …", "Absent donor columns …",
  "Fitting, calibration and test networks …") were merged into one
  **Notes on fitting and evaluation** box along the bottom, so that the notes
  could keep font 14 without three narrow side columns setting the layout;
* the note's "§5.10 repeats the study under strictly-prior-years fitting" lost
  its section number (numbers drift while the paper is edited) and now reads
  "a prior-years-only refit is reported as a sensitivity";
* the barrier note now reads "enforced in the feature constructor and by a test",
  matching the SI's verification list (the old label said "enforced in
  feature_frame");
* "Reserved panel at 70% retention: 2.5% against 9.7% for the length rule" and
  the abstention numbers (92.7% at 0.42% against 67.5% at 0.36%) are unchanged;
  the abstention line now uses the manuscript's own words, "abstain only where
  the interval straddles the threshold".

**f4** (SI Fig. S6), 988×872 px, fonts 14–15 px, prints 5.5 × 4.854 in:

| old | new | why |
|---|---|---|
| "What it buys, on **36 networks never used for fitting**, at 70% retention: 4.2% … 2.5% … against 9.7% for the length rule" | "What the substitution buys, at 70% retention, on the **retrospective 36-network holdout**: 9.7% → 2.5% for the calibrated screen; the three-variable rule gives 4.2%" | the reserved panel is a retrospective holdout with mixed prior access (28 of 36 networks touched), so "never used" is the claim the manuscript corrects; the two comparisons are kept separate because the calibrated screen is quoted against 9.7% and the three-variable rule against 9.6% |
| "apply the threshold within stratum rather than globally — on our panel that costs **0.2 points or less**" | "apply the threshold within stratum (**about 0.3 points**)" | the current number is 0.31 points on development cases and 0.30 on the reserved panel |
| "Where validity is needed at one site, use the cluster calibration: about 1.5× wider intervals, and the admission decision is unchanged." | "A pooled interval speaks for a population of networks, not for one site; cluster calibration stays exploratory until it is validated outside the development programme." | site-level cluster calibration is `exploratory_level_selected_on_opened` (`C14`) and is barred from the abstract; the manuscript's conclusion is that it must be validated on networks outside the development programme before it is sold as site-level coverage |
| "length is the better axis for **these endpoints** (AUC 0.845 against 0.672 for peak-window overlap)" | "length is the better axis here (**annual mean** AUC 0.845 against 0.672)" | 0.845 vs 0.672 is the annual-mean row of the axis table; the coldest 30-day mean is 0.803 vs 0.447, so the plural claim was not supported by the numbers quoted |
| "If the question is a single threshold judgement … **93% of years judged at the same error rate**" | "… abstaining where the interval straddles the threshold judges **92.7% of years at 0.42%, against 67.5% at 0.36% for screening at 0.5 °C**" | exact manuscript numbers instead of the rounded "93%" (the "same error rate" wording is also softened to the two measured rates) |

Everything else in f4 is unchanged in substance (the two branches, the peak-window
step, the three mask numbers, the logistic coefficients, the guardrail attributes).

## 6. Export

```
python3 scripts/205_v17_drawio_export.py
cp figures/v17/f0_problem_frame.pdf figures/v17/f1_system_architecture.pdf \
   figures/v17/f2_experiment_design.pdf figures/v17/f3_evidence_chain.pdf \
   figures/v17/f4_deployment_workflow.pdf paper/wrr/figures/
```

`make figures-drawio` runs the same script and the same copy. The command also
regenerates the five `figures/v17/*.svg` build products (they are written by the
exporter; the PDFs are the deliverables). Both the `figures/v17/` and the
`paper/wrr/figures/` copies were compared by SHA-256 after the copy and match.

## 7. Verification at final size

Because the PDFs are now written at 5.5 in, the measured type size in the PDF is
the final type size; no scale factor is involved.

| figure | page (in) | words | min text height | max | words outside page | overlapping word pairs | words outside their box | fonts embedded |
|---|---|---|---|---|---|---|---|---|
| f0_problem_frame | 5.5 × 3.538 | 207 | **5.158 pt** | 5.952 pt | 0 | 0 | 0 | yes (4 faces) |
| f1_system_architecture | 5.5 × 4.498 | 298 | **5.611 pt** | 6.012 pt | 0 | 0 | 0 | yes (3 faces) |
| f2_experiment_design | 5.5 × 5.227 | 291 | **5.932 pt** | 6.136 pt | 0 | 0 | 0 | yes (3 faces) |
| f3_evidence_chain | 5.5 × 5.723 | 267 | **6.168 pt** | 6.168 pt | 0 | 0 | 0 | yes (3 faces) |
| f4_deployment_workflow | 5.5 × 4.854 | 239 | **5.611 pt** | 6.012 pt | 0 | 0 | 0 | yes (4 faces) |

Commands and what each one answers:

```
pdfinfo  figures/v17/<name>.pdf     # 1 page, page size in inches
pdffonts figures/v17/<name>.pdf     # every face "emb yes"
pdftotext -bbox figures/v17/<name>.pdf -   # word boxes: containment, overlap, height
python3 scratch/drawio/verify_figures.py   # all of the above plus box containment
```

`scratch/drawio/verify_figures.py` re-parses the `.drawio` source geometry with
the exporter's own reader, maps each `pdftotext -bbox` word box back into
drawing units, and checks that it lies inside the vertex box or the edge-label
box that contains its centre (tolerance 2 units). Its JSON output is in
`scratch/drawio/verify_report.json`.

Fonts: `NimbusSans-Regular` and `NimbusSans-Bold` (the URW Helvetica clone that
the renderer's `Helvetica, Arial, 'Liberation Sans', sans-serif` stack resolves
to), plus `DejaVuSans` for the glyphs Nimbus lacks (`Σ`, `∈`, `₁`). All faces are
embedded and subset, all sans-serif, so the schematics stay consistent with the
matplotlib figures, which embed `DejaVuSans`.

Before/after for the smallest printed label. The "old" column is computed from
the `HEAD` revision of each source (drawing width in px, smallest `fontSize`,
printed at `396 f / W` pt); the Fig. 2 figure was also measured directly in the
built article, where an 11 px label printed at 3.667 pt:

| figure | old drawing width | old smallest label | new smallest label |
|---|---|---|---|
| f0 | 10.08 in | 4.30 pt (10.5 px, edge labels) | 5.16 pt |
| f1 | 12.11 in | 3.40 pt (10 px, edge label) | 5.61 pt |
| f2 | 12.38 in | 3.33 pt (10 px, edge label; 3.50 pt for the 10.5 px notes) | 5.93 pt |
| f3 | 12.17 in | 3.56 pt (10.5 px, edge label) | 6.17 pt |
| f4 | 12.17 in | 3.56 pt (10.5 px, notes) | 5.61 pt |

## 8. Labels I could not verify against the manuscript

None are unverified in the sense of being invented: every label in the five
figures is traceable to the manuscript, the SI, or a sealed artifact. Four items
are judgement calls or paraphrases and are recorded here so a reviewer can
overrule them cheaply:

1. **f3 links 8 and 9, evidence class "sample fact".** The four classes the SI
   caption defines do not include a class for truth-free archive decisions; the
   claim registry uses `deployment_description` and `proxy_not_truth`. The links
   are labelled "sample fact" (with "no truth read" on link 8 and "wholly hidden
   climatological peak windows are a proxy (PPV 0.74)") rather than
   "exploratory post-open", which would be wrong for a count taken from the
   archive.
2. **f2 row 6, "the certificate instead supports abstention where the interval
   straddles the threshold".** The abstention numbers were measured on designed
   cases, not on the 2,422 real incomplete years; the label therefore says the
   certificate *supports* abstention and quotes the manuscript's rule without
   attaching the 92.7% figure to the real records.
3. **f2 row 3, "declared before the reserved panel opened".** The manuscript
   says the pre-registered primary criterion was "frozen before the reserved
   panel was opened"; the box compresses that to five words.
4. **f4, "about 0.3 points".** The two measured values are 0.31 (development)
   and 0.30 (reserved); the figure rounds them, the manuscript keeps both.

Also recorded: the old Fig. 2's "marginal coverage 0.909" is not in the
manuscript at all (it is `coverage.marginal = 0.9085` in
`results/v17_fitness/step10_confirmation/verdict.json`); it was dropped rather
than re-quoted. The old Fig. 3's `RQ0…RQ8` identifiers do not exist in the
current manuscript and were replaced by the three questions the introduction
actually asks.

## 9. Checks run

* `python3 scripts/205_v17_drawio_export.py` — all five sources exported, no
  unsupported shape and no dangling edge.
* `python3 scratch/drawio/verify_figures.py` — 5/5 schematics pass every check
  (table in §7).
* `python3 -m pytest tests/test_v18_closure.py::test_schematics_are_generated_from_their_drawio_sources`
  — passes (each PDF is newer than its source and each source is uncompressed
  XML).
* `python3 scripts/266_wrr_figure_qa.py --json scratch/drawio/figure_qa.json
  --md scratch/drawio/figure_qa_report.md --render-dir scratch/drawio/qa_renders
  --report-only` — the independent QA harness written in parallel by another
  workstream reports **zero hard failures and zero warnings for all five
  schematics** (its hard-failure threshold is 4.5 pt; these figures sit at
  5.16–6.17 pt). Its remaining findings are in other files —
  `f1_example.pdf` (18 words 2.5–3.9 pt outside the page box),
  `fig1_mechanism.pdf` and `figv3_support_law.pdf` (one 4.29 pt word each), and
  the built `wrr_manuscript.pdf` / `wrr_supporting_information.pdf`
  (17 + 2 words 1.0–3.4 pt outside the page, three words below 4.5 pt) — none of
  which are these five schematics. The built article and SI predate the final
  copies of these five PDFs and need one rebuild to pick up the final label
  wording.
* SHA-256 comparison of `figures/v17/<name>.pdf` against
  `paper/wrr/figures/<name>.pdf` — identical for all five.

# Amendment: the WRR article rewritten in the four-step argument

Date: 2026-10-12.  Scope: `paper/wrr/wrr_manuscript.tex`,
`paper/wrr/wrr_supporting_information.tex`, the figure pipeline, and the
figure/typography QA harness.  No result, number, seal or artifact changed: the
claim-binding check, the 92-check numeric audit and the 137-cell table audit all
run against the same artifacts before and after.

## What changed and why

The article now follows the argument structure the author asked for: phenomenon,
conditional response, mechanism, consequence.

1. **Title and key points** state the finding rather than the study object:
   *Gap position, not gap length, governs the error of annual thermal extremes in
   incomplete river-temperature records.*
2. **Abstract** is written in five moves: the prevailing assumption, the precise
   gap (length and position cannot be separated in real records), the design
   (5114 station-years, 51524 designed outages, sealed panels), the result with
   its contrast and mechanism, and the consequence.  239 words.
3. **Introduction** is five paragraphs: importance with the 1.305 °C cost of the
   recorded-days default, the prevailing completeness heuristic, evidence that
   the response is opposite for extremes and means, the three obstacles that make
   the question unanswerable with existing designs (entangled properties,
   unobservable truth, discrimination reported instead of composition), and the
   design plus three questions.
4. **Results** is four steps, each with a lead paragraph that answers its own
   question: *the phenomenon* (recorded-days cost; the reversal across five
   endpoints), *the conditional response* (continuum and crossing; the estimands
   the standing guidance was derived for; the collapse under the real gap
   calendar; agency and assurance dependence), *the mechanism* (support must be
   located; error grows along hidden support and donors carry anomaly
   information; the calibrated bound is honest), and *what it changes* (equal
   retention with the sealed confirmations; the incumbent baseline; the real
   archive; representativeness; where it is hard).
5. **Discussion** runs mechanism, agreement and disagreement, judgement,
   recommendations, generalisation, and limits, behind a paragraph that states
   the contribution in three sentences.
6. **Conclusions** give the design, three quantitative answers, and the
   consequence, with the retrospective-holdout label on the holdout numbers and
   no new literature, mechanism or policy claim.

## Figures

* **Architecture and system-design figures are draw.io sources with exported
  PDFs**, as required: `figures/v17/drawio/{f0_problem_frame,
  f1_system_architecture, f2_experiment_design, f3_evidence_chain,
  f4_deployment_workflow}.drawio`, rendered by `scripts/205_v17_drawio_export.py`
  at the printed 5.5 in column width, so PDF type size equals printed type size.
  The five schematics previously printed at 3.3-4.3 pt; they now measure
  5.16-6.17 pt with zero words outside the page and zero overlaps.
* **Data figures are Python-generated PDFs**, all embedded TrueType
  (`pdf.fonttype = 42`).  The new heterogeneity figure (`scripts/267_...`) reads
  every plotted value from a named artifact and records the artifact path,
  filter and input hash in `figures/wrr/f2_heterogeneity_data.json`.
* Main text: 10 figures (design, phenomenon, heterogeneity, continuum,
  seasonality, mechanism, calibration, frontier, archive deployment,
  representativeness).  SI: 7 figures; the catchment-attribute figure moved from
  the article to the SI and is referenced as Figure S7.

## Typography

* Fonts: every figure PDF and both built documents embed all fonts; the last
  Type 3 face (in `f1_example.pdf`) was removed by re-rendering with Type 42
  outlines.
* Justification: `microtype` plus a breakable `\texttt` (seqsplit) took the
  overfull hboxes from 798 to 47, the worst from 297 pt to 0.18 pt, so no line
  now reaches the page edge.  The SI went from 6 overfull boxes (worst 0.4 pt).
* Two tables (`tab:sine`, `tab:arms`) were re-typeset as full-width `tabularx`
  grids; their column weights sum to the number of X columns, which the table
  test asserts.

## Verification

* `scripts/223_wrr_build.py` (desk checks): all green except the author
  placeholder, which is a human gate.
* `scripts/254_wrr_claim_binding_check.py`: exit 0.
* `scripts/221_v18_audit_manuscript.py`: 92 checks passing.
* `scripts/199_v17_audit_manuscript.py`: 137 table cells match their artifacts.
* `scripts/266_wrr_figure_qa.py`: **0 hard failures** across the 18 figure PDFs
  and the two built documents --- every font embedded, every figure one page, no
  rendered ink clipped at a page edge, no line of type below 4.5 pt, and every
  architecture figure has its draw.io source.  The 24 remaining warnings are
  box-model artefacts (tight-line font-box padding), sub/superscripts, and the
  absent `drawio` desktop binary; `figure_qa_report.md` lists them per file.
* Three defects the harness found were fixed rather than waived: the page number
  was overprinted on the last line of two pages (the two tallest floats and
  their captions were shortened and the panels scaled to 0.95 `\textwidth`); the
  support-law heatmap printed at 260 ppi (re-rendered at 400 dpi); and the
  panel-d winner labels in the mechanism figure merged into one run at print
  size (now rotated).
* Final state: manuscript 53 pp, SI 15 pp, published layout 31 pp, 10 main
  figures and 7 SI figures; overfull hboxes 47 with worst 0.18 pt.

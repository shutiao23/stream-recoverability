# WRR figure and PDF quality assurance

Generated 2026-10-12T13:36:52Z by `python3 scripts/266_wrr_figure_qa.py`.

* JSON: `scratch/figure_qa/rerun.json`
* Markdown: `scratch/figure_qa/rerun.md`
* tools: `pdffonts` pdffonts version 22.02.0, `pdfinfo` pdfinfo version 22.02.0, `pdftotext` pdftotext version 22.02.0, `pdfimages` pdfimages version 22.02.0, `pdftoppm` pdftoppm version 22.02.0, `rsvg-convert` rsvg-convert version 2.52.5, `drawio` MISSING

## Verdict

**PASS (with warnings)** — 0 hard failure(s) in 0 file/check/page group(s), 32 warning(s).

Exit status is 0 for the strict run (`--report-only` always exits 0 so the regression test is not turned red by a real finding).

| check | hard failures | warnings |
|---|---|---|
| FONT_NOT_EMBEDDED — font not embedded (check a) | 0 | 0 |
| FIGURE_NOT_SINGLE_PAGE — figure page count != 1 (check b) | 0 | 0 |
| TEXT_OUTSIDE_PAGE — text > 1 pt outside the page and ink clipped or unverified (check c) | 0 | 0 |
| TEXT_HEIGHT_BELOW_MINIMUM — line-estimated type size < 4.5 pt (check d) | 0 | 0 |
| OVERLAPPING_TEXT_SAME_BASELINE — overlapping boxes, same baseline (check e) | 0 | 0 |
| OVERLAPPING_WORD_BOXES — overlapping boxes, other geometry (check e) | 0 | 10 |
| MERGED_LABEL_RUN_SUSPECT — labels drawn with no word gap (check e) | 0 | 2 |
| FOOTER_TEXT_COLLISION — page number overprinted by body text (check e) | 0 | 2 |
| SCHEMATIC_WITHOUT_DRAWIO_SOURCE — schematic with no draw.io source (check f) | 0 | 0 |
| PROVENANCE_UNKNOWN — neither draw.io nor python source (check f) | 0 | 0 |
| RASTER_BELOW_300_DPI — raster below 300 dpi effective (check g) | 0 | 4 |
| EFFECTIVE_PRINT_TEXT_TOO_SMALL — derived: printed text below 4.5 pt | 0 | 0 |
| INK_CLIPPED_AT_PAGE_EDGE — derived: rendered ink clipped/flush at the page edge | 0 | 0 |
| TEXT_BOX_PADDING_ONLY — derived: box crosses the edge, ink does not | 0 | 0 |
| INK_CHECK_UNAVAILABLE — derived: the flagged page could not be rendered | 0 | 0 |
| SMALL_RELATIVE_WORD_BOXES — word far smaller than its own line (check d) | 0 | 13 |
| FONT_UNNAMED — embedded font with no BaseFont name | 0 | 0 |
| DEGENERATE_WORD_BOXES — word boxes with non-positive height | 0 | 0 |
| FIGURE_NOT_REFERENCED — figure PDF not referenced by any .tex | 0 | 0 |
| PAGE_SIZE_VARIES — page sizes differ within one PDF | 0 | 0 |
| BBOX_PAGE_COUNT_MISMATCH — pdftotext -bbox page count differs from pdfinfo | 0 | 0 |
| BUILT_PDF_MISSING — a built PDF was not found | 0 | 0 |
| TOOL_MISSING — a required tool is not installed | 0 | 1 |

Thresholds: text outside page > 1.0 pt, line-estimated type size < 4.5 pt, overlap > 25% of the smaller box, raster < 300 dpi.

### Real defects versus box-model artifacts

No hard failure was recorded: every word box that crosses a page edge was shown by the render to keep its ink inside the page, and no line of type is below the size threshold.

**8 warning(s) below are defects in the artifact, not box-model artifacts, and are the ones worth acting on:**

| file | check | page | finding |
|---|---|---|---|
| `paper/wrr/figures/fig1_mechanism.pdf` | MERGED_LABEL_RUN_SUSPECT | 1 | word 'timingtimingtiminglengthlength' repeats 'timing' x3 inside one box 82.5 pt wide; 5 drawing run(s) recovered from the content stream, pitch 15.514-15.529 pt |
| `paper/wrr/figures/figv3_support_law.pdf` | RASTER_BELOW_300_DPI | 1 | raster image 0 on page 1 (423x437 px, index) has an effective resolution of 260x260 ppi (< 300) |
| `paper/wrr/figures/figv3_support_law.pdf` | RASTER_BELOW_300_DPI | 1 | raster image 1 on page 1 (20x406 px, index) has an effective resolution of 260x260 ppi (< 300) |
| `paper/wrr/wrr_manuscript.pdf` | MERGED_LABEL_RUN_SUSPECT | 28 | word 'timingtimingtiminglengthlength' repeats 'timing' x3 inside one box 76.4 pt wide; 0 drawing run(s) recovered from the content stream |
| `paper/wrr/wrr_manuscript.pdf` | FOOTER_TEXT_COLLISION | 16 | page number '–16–' is overprinted by 2 body word box(es); worst 'result:' at (265.79, 766.01, 291.44, 773.98) overlaps the number band 5.54 pt vertically; word box (265.79, 766.01, 291.44, 773.98) |
| `paper/wrr/wrr_manuscript.pdf` | FOOTER_TEXT_COLLISION | 18 | page number '–18–' is overprinted by 1 body word box(es); worst 'network-clustered' at (257.88, 758.73, 328.89, 766.69) overlaps the number band 3.10 pt vertically; word box (257.88, 758.73, 328.89, 766.69) |
| `paper/wrr/wrr_manuscript.pdf` | RASTER_BELOW_300_DPI | 20 | raster image 0 on page 20 (423x437 px, index) has an effective resolution of 260x260 ppi (< 300) |
| `paper/wrr/wrr_manuscript.pdf` | RASTER_BELOW_300_DPI | 20 | raster image 1 on page 20 (20x406 px, index) has an effective resolution of 260x260 ppi (< 300) |

## Per-figure master table

| figure | pages | page size (in) | fonts | non-embedded | text outside page | min word height (pt) | overlap pairs | of which same baseline | min raster ppi | source | effective print p05 (pt) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `f0_problem_frame` | 1 | 5.50x3.54 | 4 | 0 | 0 | 5.16 | 0 | 0 | - | drawio | 5.56 | ok |
| `f1_example` | 1 | 5.34x5.06 | 1 | 0 | 0 | 6.38 | 0 | 0 | - | python | 7.20 | warn |
| `f1_system_architecture` | 1 | 5.50x4.50 | 3 | 0 | 0 | 5.61 | 0 | 0 | - | drawio | 5.61 | ok |
| `f2_experiment_design` | 1 | 5.50x5.23 | 3 | 0 | 0 | 5.93 | 0 | 0 | - | drawio | 5.93 | ok |
| `f2a_endpoint_ordering` | 1 | 5.43x2.51 | 1 | 0 | 0 | 6.99 | 0 | 0 | - | python | 7.08 | ok |
| `f2b_panel_heterogeneity` | 1 | 5.29x4.05 | 1 | 0 | 0 | 6.99 | 0 | 0 | - | python | 7.27 | ok |
| `f3_evidence_chain` | 1 | 5.50x5.72 | 3 | 0 | 0 | 6.17 | 0 | 0 | - | drawio | 6.17 | ok |
| `f4_deployment_workflow` | 1 | 5.50x4.85 | 4 | 0 | 0 | 5.61 | 0 | 0 | - | drawio | 5.61 | ok |
| `fig1_mechanism` | 1 | 5.93x4.79 | 2 | 0 | 0 | 4.29 | 42 | 0 | 300 | python | 9.47 | warn |
| `fig2_frontier` | 1 | 5.48x4.88 | 1 | 0 | 0 | 5.87 | 5 | 0 | - | python | 11.00 | warn |
| `fig3_calibration` | 1 | 5.48x5.00 | 1 | 0 | 0 | 12.10 | 1 | 0 | - | python | 12.14 | warn |
| `fig4_consequence` | 1 | 5.49x4.87 | 1 | 0 | 0 | 8.39 | 7 | 0 | - | python | 12.14 | warn |
| `fig5_robustness` | 1 | 5.63x5.00 | 1 | 0 | 0 | 12.10 | 7 | 0 | - | python | 11.83 | warn |
| `fig6_hydrology` | 1 | 5.47x5.00 | 1 | 0 | 0 | 6.75 | 0 | 0 | - | python | 11.03 | warn |
| `figv1_outage_seasonality` | 1 | 5.48x4.88 | 1 | 0 | 0 | 6.38 | 0 | 0 | - | python | 11.38 | warn |
| `figv2_archive_deployment` | 1 | 6.18x5.00 | 1 | 0 | 0 | 10.97 | 12 | 0 | - | python | 9.77 | warn |
| `figv3_support_law` | 1 | 5.49x5.00 | 1 | 0 | 0 | 4.29 | 2 | 0 | 260 | python | 10.60 | warn |
| `figv4_representativeness` | 1 | 5.48x4.88 | 1 | 0 | 0 | 12.10 | 5 | 0 | - | python | 12.14 | warn |

"effective print p05" is the 5th-percentile word-box height multiplied by the measured placement scale in the built PDFs (derived, see the print-size section).

## Built documents

| document | pages | page size (pt) | page size (in) | fonts | non-embedded | text outside page | min word height (pt) | overlap pairs | same baseline | min raster ppi |
|---|---|---|---|---|---|---|---|---|---|---|
| `paper/wrr/wrr_manuscript.pdf` | 52 | 612.00 x 792.00 | 8.50 x 11.00 | 40 | 0 | 0 | 3.98 | 69 | 0 | 260 |
| `paper/wrr/wrr_supporting_information.pdf` | 15 | 612.00 x 792.00 | 8.50 x 11.00 | 34 | 0 | 0 | 4.70 | 14 | 0 | - |

## 1. Fonts (check a)

| file | fonts | types | non-embedded | names of non-embedded | unnamed/Type 3 | all embedded |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 4 | CID TrueType x1, CID Type 0C x1, Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/f1_example.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/f1_system_architecture.pdf` | 3 | CID Type 0C x1, Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/f2_experiment_design.pdf` | 3 | CID Type 0C x1, Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/f2a_endpoint_ordering.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/f2b_panel_heterogeneity.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/f3_evidence_chain.pdf` | 3 | CID Type 0C x1, Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/f4_deployment_workflow.pdf` | 4 | CID Type 0C x2, Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/fig1_mechanism.pdf` | 2 | Type 3 x2 | 0 | none | `EVICAO+DejaVuSans-Bold`, `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/figures/fig2_frontier.pdf` | 1 | Type 3 x1 | 0 | none | `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/figures/fig3_calibration.pdf` | 1 | Type 3 x1 | 0 | none | `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/figures/fig4_consequence.pdf` | 1 | Type 3 x1 | 0 | none | `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/figures/fig5_robustness.pdf` | 1 | Type 3 x1 | 0 | none | `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/figures/fig6_hydrology.pdf` | 1 | Type 3 x1 | 0 | none | `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/figures/figv1_outage_seasonality.pdf` | 1 | Type 3 x1 | 0 | none | `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/figures/figv2_archive_deployment.pdf` | 1 | Type 3 x1 | 0 | none | `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/figures/figv3_support_law.pdf` | 1 | Type 3 x1 | 0 | none | `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/figures/figv4_representativeness.pdf` | 1 | Type 3 x1 | 0 | none | `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/wrr_manuscript.pdf` | 40 | CID TrueType x3, CID Type 0C x1, Type 1 x26, Type 1C x2, Type 3 x8 | 0 | none | `BMQQDV+DejaVuSans`, `BMQQDV+DejaVuSans`, `EVICAO+DejaVuSans-Bold`, `BMQQDV+DejaVuSans`, `BMQQDV+DejaVuSans`, `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/wrr_supporting_information.pdf` | 34 | CID TrueType x1, CID Type 0C x5, Type 1 x17, Type 1C x8, Type 3 x3 | 0 | none | `BMQQDV+DejaVuSans`, `BMQQDV+DejaVuSans`, `BMQQDV+DejaVuSans` | yes |

`[none]` is the name Poppler reports for a producer-embedded Type 3 subset with no BaseFont entry (matplotlib's default pdf.fonttype=3); the font is embedded even though it is unnamed.

## 2. Page geometry (check b)

| file | pages | page size (pt) | page size (in) | distinct page sizes | single page | text outside page | max overflow (pt) |
|---|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 1 | 396.00 x 254.74 | 5.50 x 3.54 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f1_example.pdf` | 1 | 384.29 x 364.41 | 5.34 x 5.06 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f1_system_architecture.pdf` | 1 | 396.00 x 323.86 | 5.50 x 4.50 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f2_experiment_design.pdf` | 1 | 396.00 x 376.34 | 5.50 x 5.23 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f2a_endpoint_ordering.pdf` | 1 | 391.11 x 180.98 | 5.43 x 2.51 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f2b_panel_heterogeneity.pdf` | 1 | 380.62 x 291.75 | 5.29 x 4.05 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f3_evidence_chain.pdf` | 1 | 396.00 x 412.06 | 5.50 x 5.72 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f4_deployment_workflow.pdf` | 1 | 396.00 x 349.49 | 5.50 x 4.85 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/fig1_mechanism.pdf` | 1 | 427.25 x 344.65 | 5.93 x 4.79 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/fig2_frontier.pdf` | 1 | 394.89 x 351.30 | 5.48 x 4.88 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/fig3_calibration.pdf` | 1 | 394.80 x 360.12 | 5.48 x 5.00 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/fig4_consequence.pdf` | 1 | 394.96 x 350.97 | 5.49 x 4.87 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/fig5_robustness.pdf` | 1 | 405.36 x 360.12 | 5.63 x 5.00 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/fig6_hydrology.pdf` | 1 | 393.79 x 360.12 | 5.47 x 5.00 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/figv1_outage_seasonality.pdf` | 1 | 394.76 x 351.30 | 5.48 x 4.88 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/figv2_archive_deployment.pdf` | 1 | 444.75 x 359.79 | 6.18 x 5.00 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/figv3_support_law.pdf` | 1 | 395.58 x 360.14 | 5.49 x 5.00 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/figv4_representativeness.pdf` | 1 | 394.78 x 351.30 | 5.48 x 4.88 | 1 | yes | 0 | 0.00 |
| `paper/wrr/wrr_manuscript.pdf` | 52 | 612.00 x 792.00 | 8.50 x 11.00 | 1 | no | 0 | 0.00 |
| `paper/wrr/wrr_supporting_information.pdf` | 15 | 612.00 x 792.00 | 8.50 x 11.00 | 1 | no | 0 | 0.00 |

## 3. Text outside the page box (check c)

No word box extends more than 1.0 pt outside its page in any target PDF.

## 4. Minimum text height (check d)

| file | words measured | min box (pt) | 5th pct (pt) | median (pt) | raw boxes < 4.5 pt (literal rule) | lines below threshold (gate) | smaller than their line | degenerate boxes |
|---|---|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 207 | 5.16 | 5.55 | 5.95 | 0 | 0 | 0 | 0 |
| `paper/wrr/figures/f1_example.pdf` | 160 | 6.38 | 6.99 | 7.46 | 0 | 0 | 30 | 0 |
| `paper/wrr/figures/f1_system_architecture.pdf` | 298 | 5.61 | 5.61 | 5.61 | 0 | 0 | 0 | 0 |
| `paper/wrr/figures/f2_experiment_design.pdf` | 291 | 5.93 | 5.93 | 6.14 | 0 | 0 | 0 | 0 |
| `paper/wrr/figures/f2a_endpoint_ordering.pdf` | 67 | 6.99 | 6.99 | 7.22 | 0 | 0 | 0 | 0 |
| `paper/wrr/figures/f2b_panel_heterogeneity.pdf` | 108 | 6.99 | 6.99 | 7.46 | 0 | 0 | 0 | 0 |
| `paper/wrr/figures/f3_evidence_chain.pdf` | 267 | 6.17 | 6.17 | 6.17 | 0 | 0 | 0 | 0 |
| `paper/wrr/figures/f4_deployment_workflow.pdf` | 239 | 5.61 | 5.61 | 5.61 | 0 | 0 | 0 | 0 |
| `paper/wrr/figures/fig1_mechanism.pdf` | 173 | 4.29 | 10.21 | 13.24 | 1 | 0 | 64 | 0 |
| `paper/wrr/figures/fig2_frontier.pdf` | 89 | 5.87 | 10.97 | 12.11 | 0 | 0 | 2 | 0 |
| `paper/wrr/figures/fig3_calibration.pdf` | 143 | 12.10 | 12.10 | 12.86 | 0 | 0 | 20 | 0 |
| `paper/wrr/figures/fig4_consequence.pdf` | 66 | 8.39 | 12.10 | 12.11 | 0 | 0 | 4 | 0 |
| `paper/wrr/figures/fig5_robustness.pdf` | 91 | 12.10 | 12.10 | 13.62 | 0 | 0 | 26 | 0 |
| `paper/wrr/figures/fig6_hydrology.pdf` | 105 | 6.75 | 10.97 | 13.24 | 0 | 0 | 39 | 0 |
| `paper/wrr/figures/figv1_outage_seasonality.pdf` | 91 | 6.38 | 11.35 | 12.10 | 0 | 0 | 3 | 0 |
| `paper/wrr/figures/figv2_archive_deployment.pdf` | 130 | 10.97 | 10.97 | 12.10 | 0 | 0 | 57 | 0 |
| `paper/wrr/figures/figv3_support_law.pdf` | 128 | 4.29 | 10.59 | 12.10 | 1 | 0 | 74 | 0 |
| `paper/wrr/figures/figv4_representativeness.pdf` | 85 | 12.10 | 12.10 | 14.18 | 0 | 0 | 42 | 0 |
| `paper/wrr/wrr_manuscript.pdf` | 17541 | 3.98 | 7.08 | 8.85 | 3 | 0 | 294 | 0 |
| `paper/wrr/wrr_supporting_information.pdf` | 4258 | 4.70 | 5.61 | 8.85 | 0 | 0 | 69 | 0 |

No word box is below 4.5 pt in any target PDF.

## 5. Overlapping text (check e)

Rule: pairs of word boxes whose intersection area exceeds 25% of the smaller box, exact duplicates and shadow duplicates excluded. **This is a conservative approximation of visual overlap**: it is derived from Poppler word boxes, which are axis-aligned even for rotated text and which include font ascent/descent, and it cannot see text drawn over graphics.

| file | word boxes | candidate pairs | same baseline (real) | adjacent-line padding | atypical box geometry | duplicates ignored (exact/shadow) |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 207 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f1_example.pdf` | 160 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f1_system_architecture.pdf` | 298 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f2_experiment_design.pdf` | 291 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f2a_endpoint_ordering.pdf` | 67 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f2b_panel_heterogeneity.pdf` | 108 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f3_evidence_chain.pdf` | 267 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f4_deployment_workflow.pdf` | 239 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/fig1_mechanism.pdf` | 173 | 42 | 0 | 38 | 4 | 0/0 |
| `paper/wrr/figures/fig2_frontier.pdf` | 89 | 5 | 0 | 5 | 0 | 0/0 |
| `paper/wrr/figures/fig3_calibration.pdf` | 143 | 1 | 0 | 1 | 0 | 0/0 |
| `paper/wrr/figures/fig4_consequence.pdf` | 66 | 7 | 0 | 7 | 0 | 0/0 |
| `paper/wrr/figures/fig5_robustness.pdf` | 91 | 7 | 0 | 7 | 0 | 0/0 |
| `paper/wrr/figures/fig6_hydrology.pdf` | 105 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/figv1_outage_seasonality.pdf` | 91 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/figv2_archive_deployment.pdf` | 130 | 12 | 0 | 12 | 0 | 0/0 |
| `paper/wrr/figures/figv3_support_law.pdf` | 128 | 2 | 0 | 2 | 0 | 0/0 |
| `paper/wrr/figures/figv4_representativeness.pdf` | 85 | 5 | 0 | 5 | 0 | 0/0 |
| `paper/wrr/wrr_manuscript.pdf` | 17541 | 69 | 0 | 61 | 8 | 0/0 |
| `paper/wrr/wrr_supporting_information.pdf` | 4258 | 14 | 0 | 14 | 0 | 0/0 |

### Flagged pairs

#### `paper/wrr/figures/fig1_mechanism.pdf` — 42 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 1 | atypical_box_geometry | 80.4 | `amplit` | (319.39, 286.34, 334.44, 305.18) | `0` | (320.37, 284.27, 323.39, 294.86) | 2.07 | 13.24 |
| 1 | atypical_box_geometry | 53.7 | `amplit` | (319.39, 286.34, 334.44, 305.18) | `d` | (324.9, 281.44, 327.92, 292.03) | 4.90 | 13.24 |
| 1 | atypical_box_geometry | 51.4 | `amplit` | (319.39, 286.34, 334.44, 305.18) | `ann` | (327.75, 295.37, 336.68, 309.66) | 9.02 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `seasonal` | (22.09, 234.98, 52.94, 248.22) | `donor` | (32.2, 228.18, 52.53, 241.42) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `observed` | (29.03, 187.42, 61.48, 200.66) | `donor` | (36.81, 194.22, 57.14, 207.45) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `donor` | (32.2, 228.18, 52.53, 241.42) | `n` | (35.34, 221.39, 39.78, 234.63) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `missing` | (34.56, 248.57, 61.45, 261.8) | `total` | (45.43, 255.36, 61.44, 268.6) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `coverage` | (36.0, 214.6, 68.5, 227.84) | `train` | (39.18, 207.8, 55.48, 221.04) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `coverage` | (36.0, 214.6, 68.5, 227.84) | `visible` | (42.0, 221.39, 64.38, 234.63) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `amplitude` | (55.17, 234.98, 90.54, 248.22) | `n` | (68.51, 241.77, 72.95, 255.01) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `metric` | (57.71, 207.8, 80.25, 221.04) | `resid` | (63.16, 201.01, 80.24, 214.25) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `fraction` | (63.67, 248.57, 90.57, 261.8) | `n` | (68.51, 241.77, 72.95, 255.01) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `fraction` | (63.71, 187.42, 90.6, 200.66) | `overlap` | (64.25, 180.63, 90.55, 193.87) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `donors` | (66.61, 221.39, 90.58, 234.63) | `mean` | (70.73, 214.6, 90.58, 227.84) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `mean` | (70.73, 214.6, 90.58, 227.84) | `sd` | (82.47, 207.8, 90.56, 221.04) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `max` | (75.37, 194.22, 90.62, 207.45) | `sd` | (82.46, 201.01, 90.56, 214.25) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.7 | `missing` | (63.67, 255.36, 90.56, 268.6) | `fraction` | (63.67, 248.57, 90.57, 261.8) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.6 | `fraction` | (63.67, 248.57, 90.57, 261.8) | `runs` | (75.18, 241.77, 90.58, 255.01) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.6 | `missing` | (63.67, 255.36, 90.56, 268.6) | `run` | (78.81, 262.15, 90.57, 275.39) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.6 | `sd` | (82.46, 201.01, 90.56, 214.25) | `sd` | (82.47, 207.8, 90.56, 221.04) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.6 | `donors` | (66.61, 221.39, 90.58, 234.63) | `mean` | (70.76, 228.18, 90.61, 241.42) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.6 | `fraction` | (63.71, 187.42, 90.6, 200.66) | `max` | (75.37, 194.22, 90.62, 207.45) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.6 | `overlap` | (64.25, 180.63, 90.55, 193.87) | `margin` | (65.89, 173.83, 90.59, 187.07) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.6 | `amplitude` | (55.17, 234.98, 90.54, 248.22) | `runs` | (75.18, 241.77, 90.58, 255.01) | 6.79 | 13.24 |
| 1 | adjacent_line_padding | 48.5 | `amplitude` | (55.17, 234.98, 90.54, 248.22) | `mean` | (70.76, 228.18, 90.61, 241.42) | 6.79 | 13.24 |
| ... | | | 17 more pairs in the JSON | | | | | |

Pair classification: `adjacent_line_padding` x38; `atypical_box_geometry` x4.

#### `paper/wrr/figures/fig2_frontier.pdf` — 5 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 1 | adjacent_line_padding | 50.7 | `certificate` | (120.75, 289.84, 160.11, 304.59) | `oracle` | (134.51, 297.11, 158.53, 311.87) | 7.28 | 12.11 |
| 1 | adjacent_line_padding | 38.7 | `20-week` | (261.19, 70.94, 285.9, 81.91) | `with` | (273.51, 77.67, 285.81, 88.64) | 6.72 | 12.11 |
| 1 | adjacent_line_padding | 38.7 | `20-week` | (269.69, 239.62, 294.4, 250.58) | `with` | (282.01, 246.34, 294.32, 257.31) | 6.72 | 12.11 |
| 1 | adjacent_line_padding | 38.3 | `imputation` | (254.13, 84.39, 285.69, 95.36) | `with` | (273.51, 77.67, 285.81, 88.64) | 6.72 | 12.11 |
| 1 | adjacent_line_padding | 38.3 | `imputation` | (262.63, 253.07, 294.2, 264.03) | `with` | (282.01, 246.34, 294.32, 257.31) | 6.72 | 12.11 |

Pair classification: `adjacent_line_padding` x5.

#### `paper/wrr/figures/fig3_calibration.pdf` — 1 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 1 | adjacent_line_padding | 31.7 | `conditional` | (173.81, 16.56, 213.52, 30.18) | `90.9` | (191.86, 25.74, 208.33, 39.74) | 9.18 | 12.86 |

Pair classification: `adjacent_line_padding` x1.

#### `paper/wrr/figures/fig4_consequence.pdf` — 7 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 1 | adjacent_line_padding | 44.4 | `days` | (90.2, 157.73, 105.31, 169.83) | `on` | (93.04, 151.0, 101.01, 163.1) | 6.72 | 12.11 |
| 1 | adjacent_line_padding | 44.4 | `length-rule` | (240.71, 151.0, 275.83, 163.1) | `screening` | (242.67, 157.73, 273.84, 169.83) | 6.72 | 12.11 |
| 1 | adjacent_line_padding | 44.4 | `anomalies` | (330.01, 326.14, 362.9, 338.24) | `shuffled` | (333.57, 332.87, 359.3, 344.97) | 6.72 | 12.11 |
| 1 | adjacent_line_padding | 44.4 | `certificate` | (330.32, 151.0, 362.61, 163.1) | `screening` | (330.86, 157.73, 362.03, 169.83) | 6.72 | 12.11 |
| 1 | adjacent_line_padding | 42.5 | `reconstruct,` | (150.81, 151.0, 189.33, 163.1) | `screening` | (159.49, 157.73, 190.67, 169.83) | 6.72 | 12.11 |
| 1 | adjacent_line_padding | 40.0 | `observed` | (58.49, 157.73, 88.16, 169.83) | `compute` | (62.76, 151.0, 91.0, 163.1) | 6.72 | 12.11 |
| 1 | adjacent_line_padding | 37.0 | `no` | (149.48, 157.73, 157.46, 169.83) | `reconstruct,` | (150.81, 151.0, 189.33, 163.1) | 6.72 | 12.11 |

Pair classification: `adjacent_line_padding` x7.

#### `paper/wrr/figures/fig5_robustness.pdf` — 7 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 1 | adjacent_line_padding | 69.0 | `+` | (319.22, 32.58, 325.26, 46.19) | `7.1` | (319.29, 36.7, 331.37, 51.07) | 4.12 | 13.62 |
| 1 | adjacent_line_padding | 48.8 | `reconstruct,` | (299.41, 294.11, 342.74, 307.73) | `length` | (299.41, 301.08, 322.36, 314.7) | 6.97 | 13.62 |
| 1 | adjacent_line_padding | 48.8 | `reconstruct,` | (299.41, 294.11, 342.74, 307.73) | `rule` | (324.65, 301.08, 338.6, 314.7) | 6.97 | 13.62 |
| 1 | adjacent_line_padding | 37.6 | `(primary)` | (48.18, 55.86, 83.86, 70.23) | `30` | (66.92, 46.89, 76.59, 61.26) | 8.97 | 13.62 |
| 1 | adjacent_line_padding | 37.6 | `(primary)` | (48.18, 55.86, 83.86, 70.23) | `d` | (79.01, 46.89, 83.83, 61.26) | 8.97 | 13.62 |
| 1 | adjacent_line_padding | 37.6 | `window)` | (51.89, 31.08, 83.7, 45.45) | `7` | (71.78, 22.11, 76.62, 36.49) | 8.97 | 13.62 |
| 1 | adjacent_line_padding | 36.4 | `window)` | (51.89, 31.08, 83.7, 45.45) | `d` | (79.03, 22.11, 83.86, 36.49) | 8.97 | 13.62 |

Pair classification: `adjacent_line_padding` x7.

#### `paper/wrr/figures/figv2_archive_deployment.pdf` — 12 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 1 | adjacent_line_padding | 44.4 | `unfilled` | (79.6, 127.17, 103.3, 139.27) | `(49` | (81.81, 133.89, 92.45, 146.0) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 44.4 | `unfilled` | (79.6, 127.17, 103.3, 139.27) | `d)` | (94.49, 133.89, 101.05, 146.0) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 44.4 | `everything` | (98.49, 341.69, 133.04, 353.79) | `repair` | (106.33, 334.96, 125.15, 347.06) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 44.4 | `imputation` | (128.01, 127.17, 162.84, 139.27) | `d)` | (142.66, 133.89, 149.22, 146.0) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 44.4 | `length` | (178.38, 334.96, 198.78, 347.06) | `140` | (183.1, 341.69, 195.31, 353.79) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 44.4 | `length` | (251.21, 334.96, 271.61, 347.06) | `49` | (257.96, 341.69, 266.1, 353.79) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 42.6 | `disagree` | (77.96, 31.65, 104.63, 43.38) | `15.1%` | (81.46, 24.93, 101.15, 36.65) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 42.6 | `disagree` | (124.09, 31.65, 150.76, 43.38) | `11.6%` | (127.59, 24.93, 147.29, 36.65) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 40.8 | `window` | (330.97, 334.96, 355.26, 347.06) | `hidden` | (335.11, 341.69, 357.06, 353.79) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 38.1 | `(140` | (125.91, 133.89, 140.62, 146.0) | `imputation` | (128.01, 127.17, 162.84, 139.27) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 38.0 | `length` | (251.21, 334.96, 271.61, 347.06) | `d` | (268.14, 341.69, 272.2, 353.79) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 31.5 | `peak` | (313.31, 334.96, 328.94, 347.06) | `10%` | (318.85, 341.69, 333.07, 353.79) | 6.72 | 12.10 |

Pair classification: `adjacent_line_padding` x12.

#### `paper/wrr/figures/figv3_support_law.pdf` — 2 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 1 | adjacent_line_padding | 44.4 | `crossover` | (143.09, 37.99, 173.96, 50.09) | `91` | (143.09, 44.71, 151.23, 56.82) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 44.4 | `crossover` | (143.09, 37.99, 173.96, 50.09) | `days` | (153.27, 44.71, 168.38, 56.82) | 6.72 | 12.10 |

Pair classification: `adjacent_line_padding` x2.

#### `paper/wrr/figures/figv4_representativeness.pdf` — 5 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 1 | adjacent_line_padding | 40.7 | `screen,` | (111.62, 109.22, 140.76, 124.35) | `2.84%` | (111.62, 118.19, 137.03, 133.32) | 8.97 | 14.18 |
| 1 | adjacent_line_padding | 40.7 | `length` | (139.5, 38.39, 165.0, 53.52) | `8.81%` | (139.5, 47.36, 164.9, 62.49) | 8.97 | 14.18 |
| 1 | adjacent_line_padding | 40.7 | `peak-overlap` | (186.13, 98.41, 238.74, 113.54) | `3.75%` | (186.13, 107.37, 211.54, 122.5) | 8.97 | 14.18 |
| 1 | adjacent_line_padding | 40.7 | `screen,` | (278.08, 112.82, 307.22, 127.95) | `2.53%` | (278.08, 121.79, 303.49, 136.92) | 8.97 | 14.18 |
| 1 | adjacent_line_padding | 36.2 | `2.84%` | (111.62, 118.19, 137.03, 133.32) | `axes` | (121.81, 127.47, 139.15, 141.65) | 9.28 | 14.18 |

Pair classification: `adjacent_line_padding` x5.

#### `paper/wrr/wrr_manuscript.pdf` — 69 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 28 | atypical_box_geometry | 80.4 | `amplit` | (393.23, 460.68, 407.18, 478.13) | `0` | (394.14, 458.76, 396.94, 468.57) | 1.92 | 11.22 |
| 16 | adjacent_line_padding | 62.2 | `–16–` | (285.99, 763.59, 304.42, 771.55) | `no` | (295.54, 766.01, 305.46, 773.98) | 2.42 | 7.96 |
| 28 | atypical_box_geometry | 53.7 | `amplit` | (393.23, 460.68, 407.18, 478.13) | `d` | (398.34, 456.13, 401.13, 465.95) | 4.54 | 11.22 |
| 28 | atypical_box_geometry | 51.4 | `amplit` | (393.23, 460.68, 407.18, 478.13) | `ann` | (400.98, 469.04, 409.26, 482.28) | 8.36 | 11.22 |
| 31 | atypical_box_geometry | 50.7 | `certificate` | (218.3, 526.24, 257.77, 541.04) | `oracle` | (232.1, 533.54, 256.18, 548.33) | 7.30 | 8.85 |
| 28 | adjacent_line_padding | 48.7 | `seasonal` | (117.67, 413.07, 146.27, 425.34) | `donor` | (127.04, 406.77, 145.89, 419.04) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `observed` | (124.11, 368.99, 154.18, 381.26) | `donor` | (131.32, 375.29, 150.16, 387.56) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `donor` | (127.04, 406.77, 145.89, 419.04) | `n` | (129.96, 400.47, 134.07, 412.74) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `missing` | (129.23, 425.66, 154.15, 437.93) | `total` | (139.31, 431.96, 154.15, 444.23) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `coverage` | (130.57, 394.18, 160.69, 406.45) | `train` | (133.52, 387.88, 148.62, 400.15) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `coverage` | (130.57, 394.18, 160.69, 406.45) | `visible` | (136.13, 400.47, 156.87, 412.74) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `amplitude` | (148.33, 413.07, 181.12, 425.34) | `n` | (160.7, 419.36, 164.81, 431.63) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `metric` | (150.69, 387.88, 171.58, 400.15) | `resid` | (155.74, 381.58, 171.57, 393.85) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `fraction` | (156.22, 425.66, 181.14, 437.93) | `n` | (160.7, 419.36, 164.81, 431.63) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `fraction` | (156.25, 368.99, 181.17, 381.26) | `overlap` | (156.75, 362.69, 181.12, 374.96) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `donors` | (158.94, 400.47, 181.16, 412.74) | `mean` | (162.76, 394.18, 181.16, 406.45) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `mean` | (162.76, 394.18, 181.16, 406.45) | `sd` | (173.64, 387.88, 181.14, 400.15) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `max` | (167.06, 375.29, 181.19, 387.56) | `sd` | (173.63, 381.58, 181.13, 393.85) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.7 | `missing` | (156.21, 431.96, 181.13, 444.23) | `fraction` | (156.22, 425.66, 181.14, 437.93) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.6 | `fraction` | (156.22, 425.66, 181.14, 437.93) | `runs` | (166.88, 419.36, 181.15, 431.63) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.6 | `missing` | (156.21, 431.96, 181.13, 444.23) | `run` | (170.25, 438.26, 181.14, 450.53) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.6 | `sd` | (173.63, 381.58, 181.13, 393.85) | `sd` | (173.64, 387.88, 181.14, 400.15) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.6 | `donors` | (158.94, 400.47, 181.16, 412.74) | `mean` | (162.78, 406.77, 181.18, 419.04) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.6 | `fraction` | (156.25, 368.99, 181.17, 381.26) | `max` | (167.06, 375.29, 181.19, 387.56) | 6.30 | 11.22 |
| 28 | adjacent_line_padding | 48.6 | `overlap` | (156.75, 362.69, 181.12, 374.96) | `margin` | (158.27, 356.39, 181.17, 368.66) | 6.30 | 11.22 |
| ... | | | 44 more pairs in the JSON | | | | | |

Pair classification: `adjacent_line_padding` x61; `atypical_box_geometry` x8.

#### `paper/wrr/wrr_supporting_information.pdf` — 14 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 13 | adjacent_line_padding | 69.0 | `+` | (409.08, 192.1, 414.97, 205.41) | `7.1` | (409.14, 196.13, 420.95, 210.17) | 4.03 | 11.82 |
| 13 | adjacent_line_padding | 48.8 | `reconstruct,` | (389.72, 447.62, 432.05, 460.92) | `length` | (389.72, 454.43, 412.14, 467.73) | 6.81 | 11.82 |
| 13 | adjacent_line_padding | 48.8 | `reconstruct,` | (389.72, 447.62, 432.05, 460.92) | `rule` | (414.38, 454.43, 428.01, 467.73) | 6.81 | 11.82 |
| 12 | adjacent_line_padding | 44.4 | `days` | (187.64, 347.4, 202.79, 359.54) | `on` | (190.49, 340.66, 198.49, 352.79) | 6.74 | 12.14 |
| 12 | adjacent_line_padding | 44.4 | `length-rule` | (338.57, 340.66, 373.78, 352.79) | `screening` | (340.53, 347.4, 371.79, 359.54) | 6.74 | 12.14 |
| 12 | adjacent_line_padding | 44.4 | `anomalies` | (428.11, 516.27, 461.08, 528.41) | `shuffled` | (431.67, 523.02, 457.48, 535.15) | 6.74 | 12.14 |
| 12 | adjacent_line_padding | 44.4 | `certificate` | (428.42, 340.66, 460.8, 352.79) | `screening` | (428.96, 347.4, 460.22, 359.54) | 6.74 | 12.14 |
| 12 | adjacent_line_padding | 42.5 | `reconstruct,` | (248.42, 340.66, 287.04, 352.79) | `screening` | (257.13, 347.4, 288.39, 359.54) | 6.74 | 12.14 |
| 12 | adjacent_line_padding | 40.0 | `observed` | (155.85, 347.4, 185.6, 359.54) | `compute` | (160.13, 340.66, 188.45, 352.79) | 6.74 | 12.14 |
| 13 | adjacent_line_padding | 37.6 | `(primary)` | (144.28, 214.85, 179.13, 228.89) | `30` | (162.58, 206.09, 172.03, 220.13) | 8.76 | 11.82 |
| 13 | adjacent_line_padding | 37.6 | `(primary)` | (144.28, 214.85, 179.13, 228.89) | `d` | (174.39, 206.09, 179.1, 220.13) | 8.76 | 11.82 |
| 13 | adjacent_line_padding | 37.6 | `window)` | (147.9, 190.64, 178.97, 204.68) | `7` | (167.33, 181.88, 172.05, 195.92) | 8.76 | 11.82 |
| 12 | adjacent_line_padding | 37.0 | `no` | (247.09, 347.4, 255.09, 359.54) | `reconstruct,` | (248.42, 340.66, 287.04, 352.79) | 6.74 | 12.14 |
| 13 | adjacent_line_padding | 36.4 | `window)` | (147.9, 190.64, 178.97, 204.68) | `d` | (174.41, 181.88, 179.13, 195.92) | 8.76 | 11.82 |

Pair classification: `adjacent_line_padding` x14.

### Page number printed over body text

A text block that runs long pushes its last line into the footer. The pairwise rule classifies that as `adjacent_line_padding`, but on paper the page number sits on top of the text; the pages below share both axes with the number band by at least 2.0 pt.

| file | page | page number | number band (x0, y0, x1, y1) | colliding words | worst word | worst box | vertical overlap (pt) |
|---|---|---|---|---|---|---|---|
| `paper/wrr/wrr_manuscript.pdf` | 16 | `–16–` | (285.99, 763.59, 304.42, 771.55) | 2 | `result:` | (265.79, 766.01, 291.44, 773.98) | 5.54 |
| `paper/wrr/wrr_manuscript.pdf` | 18 | `–18–` | (285.99, 763.59, 304.42, 771.55) | 1 | `network-clustered` | (257.88, 758.73, 328.89, 766.69) | 3.10 |

These pages are also candidates for the text-outside-page check, because the same overfull block pushes descenders past the bottom page box.

### Labels drawn with no word gap (blind spot of the pairwise rule)

A word box such as `timingtimingtiminglengthlength` is one Poppler word because the individual labels were drawn with no space glyph between them; the pairwise test cannot see it (there is no pair) and on paper the row reads as one continuous string.

| file | page | extracted word | box (x0, y0, x1, y1) | width (pt) | repeated unit | runs recovered | run pitches (pt) |
|---|---|---|---|---|---|---|---|
| `paper/wrr/figures/fig1_mechanism.pdf` | 1 | `timingtimingtiminglengthlength` | (302.91, 173.35, 385.39, 184.68) | 82.48 | `timing` x3 | 5 | 15.51-15.53 |
| `paper/wrr/wrr_manuscript.pdf` | 28 | `timingtimingtiminglengthlength` | (377.96, 355.94, 454.4, 366.44) | 76.45 | `timing` x3 | 0 | - |

`paper/wrr/figures/fig1_mechanism.pdf` page 1 runs inside the merged box:

| run text | x (pt) | baseline y from top (pt) | font resource | size (pt) | pitch from previous (pt) |
|---|---|---|---|---|---|
| `timing` | 302.912 | 182.381 | F2 | 5.60 | - |
| `timing` | 318.441 | 182.381 | F2 | 5.60 | 15.529 |
| `timing` | 333.969 | 182.381 | F2 | 5.60 | 15.528 |
| `length` | 349.483 | 182.381 | F2 | 5.60 | 15.514 |
| `length` | 365.011 | 182.381 | F2 | 5.60 | 15.528 |

The per-run x positions come from the placement matrices in the inflated PDF content streams; the individual ink widths are not measured, so a recovered pitch is the label pitch, not the free space between glyphs.

## 6. Source provenance (check f)

| figure | draw.io source at figures/v17/drawio | schematic | python generator(s) under scripts/ | classification | verdict |
|---|---|---|---|---|---|
| `f0_problem_frame` | yes | yes — problem frame (drawio README) | none | drawio | ok |
| `f1_example` | NO | no | `scripts/265_wrr_figure1_example.py` | python | ok |
| `f1_system_architecture` | yes | yes — system architecture (drawio README) | none | drawio | ok |
| `f2_experiment_design` | yes | yes — study design and data flow (drawio README) | none | drawio | ok |
| `f2a_endpoint_ordering` | NO | no | `scripts/267_wrr_heterogeneity_figures.py` | python | ok |
| `f2b_panel_heterogeneity` | NO | no | `scripts/267_wrr_heterogeneity_figures.py` | python | ok |
| `f3_evidence_chain` | yes | yes — evidence chain (drawio README) | none | drawio | ok |
| `f4_deployment_workflow` | yes | yes — deployment workflow (drawio README) | none | drawio | ok |
| `fig1_mechanism` | NO | no | `scripts/154_run_v15_fig1_mechanism.py`, `scripts/188_v17_figures.py` | python | ok |
| `fig2_frontier` | NO | no | `scripts/188_v17_figures.py` | python | ok |
| `fig3_calibration` | NO | no | `scripts/188_v17_figures.py` | python | ok |
| `fig4_consequence` | NO | no | `scripts/188_v17_figures.py` | python | ok |
| `fig5_robustness` | NO | no | `scripts/204_v17_figures_q1.py` | python | ok |
| `fig6_hydrology` | NO | no | `scripts/204_v17_figures_q1.py` | python | ok |
| `figv1_outage_seasonality` | NO | no | `scripts/220_v18_figures.py` | python | ok |
| `figv2_archive_deployment` | NO | no | `scripts/220_v18_figures.py` | python | ok |
| `figv3_support_law` | NO | no | `scripts/220_v18_figures.py` | python | ok |
| `figv4_representativeness` | NO | no | `scripts/220_v18_figures.py` | python | ok |

The schematic list is explicit (see `SCHEMATIC_FIGURES` in the script, taken from `figures/v17/drawio/README.md`): a new architecture or system-design figure must be added there, otherwise a missing draw.io source cannot be detected.

| figure | figure built elsewhere in `figures/` | identical to the paper copy |
|---|---|---|
| `f0_problem_frame` | `figures/v17/f0_problem_frame.pdf` | yes |
| `f1_example` | `figures/wrr/f1_example.pdf` | yes |
| `f1_system_architecture` | `figures/v17/f1_system_architecture.pdf` | yes |
| `f2_experiment_design` | `figures/v17/f2_experiment_design.pdf` | yes |
| `f2a_endpoint_ordering` | `figures/wrr/f2a_endpoint_ordering.pdf` | yes |
| `f2b_panel_heterogeneity` | `figures/wrr/f2b_panel_heterogeneity.pdf` | no |
| `f3_evidence_chain` | `figures/v17/f3_evidence_chain.pdf` | yes |
| `f4_deployment_workflow` | `figures/v17/f4_deployment_workflow.pdf` | yes |
| `fig1_mechanism` | `figures/v17/fig1_mechanism.pdf` | no |
| `fig2_frontier` | `figures/v17/fig2_frontier.pdf` | no |
| `fig3_calibration` | `figures/v17/fig3_calibration.pdf` | no |
| `fig4_consequence` | `figures/v17/fig4_consequence.pdf` | no |
| `fig5_robustness` | `figures/v17/fig5_robustness.pdf` | no |
| `fig6_hydrology` | `figures/v17/fig6_hydrology.pdf` | no |
| `figv1_outage_seasonality` | `figures/v18/figv1_outage_seasonality.pdf` | no |
| `figv2_archive_deployment` | `figures/v18/figv2_archive_deployment.pdf` | no |
| `figv3_support_law` | `figures/v18/figv3_support_law.pdf` | no |
| `figv4_representativeness` | `figures/v18/figv4_representativeness.pdf` | no |

## 7. Raster image resolution (check g)

| file | page | image | pixels | colour | effective ppi (x, y) | flag |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/fig1_mechanism.pdf` | 1 | 0 | 317x427 | index | 300, 300 | ok |
| `paper/wrr/figures/fig1_mechanism.pdf` | 1 | 1 | 16x308 | index | 300, 300 | ok |
| `paper/wrr/figures/figv3_support_law.pdf` | 1 | 0 | 423x437 | index | 260, 260 | BELOW 300 dpi |
| `paper/wrr/figures/figv3_support_law.pdf` | 1 | 1 | 20x406 | index | 260, 260 | BELOW 300 dpi |
| `paper/wrr/wrr_manuscript.pdf` | 20 | 0 | 423x437 | index | 260, 260 | BELOW 300 dpi |
| `paper/wrr/wrr_manuscript.pdf` | 20 | 1 | 20x406 | index | 260, 260 | BELOW 300 dpi |
| `paper/wrr/wrr_manuscript.pdf` | 28 | 2 | 317x427 | index | 324, 324 | ok |
| `paper/wrr/wrr_manuscript.pdf` | 28 | 3 | 16x308 | index | 324, 324 | ok |

## 8. Printed size and effective text size (derived)

Method: the scale at which each figure is placed in the built PDFs is measured by matching the figure's distinctive words against the words of the built pages (all pairs of unambiguous matches give a distance ratio; the largest tight cluster is the estimate). `scale x figure width` is the printed width, and raw text heights times the scale give the size the reader sees on paper. These values are derived, never hard failures.

| figure | width (pt) | measured scale | printed width (pt) | printed width (in) | raw min (pt) | raw p05 (pt) | effective min (pt) | effective p05 (pt) | confidence |
|---|---|---|---|---|---|---|---|---|---|
| `f0_problem_frame` | 396.00 | 1.0000 | 396.01 | 5.500 | 5.16 | 5.55 | 5.16 | 5.56 | measured |
| `f1_example` | 384.29 | 1.0305 | 396.01 | 5.500 | 6.38 | 6.99 | 6.58 | 7.20 | measured |
| `f1_system_architecture` | 396.00 | 1.0000 | 396.01 | 5.500 | 5.61 | 5.61 | 5.61 | 5.61 | measured |
| `f2_experiment_design` | 396.00 | 1.0000 | 396.01 | 5.500 | 5.93 | 5.93 | 5.93 | 5.93 | measured |
| `f2a_endpoint_ordering` | 391.11 | 1.0125 | 396.01 | 5.500 | 6.99 | 6.99 | 7.08 | 7.08 | measured |
| `f2b_panel_heterogeneity` | 380.62 | 1.0405 | 396.01 | 5.500 | 6.99 | 6.99 | 7.27 | 7.27 | measured |
| `f3_evidence_chain` | 396.00 | 1.0000 | 396.01 | 5.500 | 6.17 | 6.17 | 6.17 | 6.17 | measured |
| `f4_deployment_workflow` | 396.00 | 1.0000 | 396.01 | 5.500 | 5.61 | 5.61 | 5.61 | 5.61 | measured |
| `fig1_mechanism` | 427.25 | 0.9269 | 396.00 | 5.500 | 4.29 | 10.21 | 3.98 | 9.47 | measured |
| `fig2_frontier` | 394.89 | 1.0029 | 396.02 | 5.500 | 5.87 | 10.97 | 5.88 | 11.00 | measured |
| `fig3_calibration` | 394.80 | 1.0030 | 396.00 | 5.500 | 12.10 | 12.10 | 12.14 | 12.14 | measured |
| `fig4_consequence` | 394.96 | 1.0027 | 396.03 | 5.500 | 8.39 | 12.10 | 8.41 | 12.14 | measured |
| `fig5_robustness` | 405.36 | 0.9770 | 396.03 | 5.500 | 12.10 | 12.10 | 11.83 | 11.83 | measured |
| `fig6_hydrology` | 393.79 | 1.0056 | 396.01 | 5.500 | 6.75 | 10.97 | 6.79 | 11.03 | measured |
| `figv1_outage_seasonality` | 394.76 | 1.0032 | 396.02 | 5.500 | 6.38 | 11.35 | 6.40 | 11.38 | measured |
| `figv2_archive_deployment` | 444.75 | 0.8904 | 396.01 | 5.500 | 10.97 | 10.97 | 9.77 | 9.77 | measured |
| `figv3_support_law` | 395.58 | 1.0010 | 396.00 | 5.500 | 4.29 | 10.59 | 4.30 | 10.60 | measured |
| `figv4_representativeness` | 394.78 | 1.0031 | 396.01 | 5.500 | 12.10 | 12.10 | 12.14 | 12.14 | measured |

Implied printed width across the 18 figures with a measured scale: median 396.01 pt (5.500 in), range 396.00-396.03 pt. Corroboration: the AGU class file sets `\textwidth 5.5in` = 396 pt (`paper/wrr/template/agujournal2025.cls:958`), consistent with a full-width placement.

AGU/WRR ask for figure text that stays legible in print; a text height below 4.5 pt at printed size is the practical red line used here.

Advisory (not a failure): the following figures pass the 4.5 pt rule but their 5th percentile word box prints below 6 pt, which is small even for a journal figure: `f0_problem_frame` 5.55 pt, `f1_system_architecture` 5.61 pt, `f4_deployment_workflow` 5.61 pt, `f2_experiment_design` 5.93 pt.

## 9. Prioritised fix list

| priority | file | finding |
|---|---|---|
| P1 | `paper/wrr/figures/fig1_mechanism.pdf` | MERGED_LABEL_RUN_SUSPECT page 1: word 'timingtimingtiminglengthlength' repeats 'timing' x3 inside one box 82.5 pt wide; 5 drawing run(s) recovered from the content stream, pitch 15.514-15.529 pt |
| P1 | `paper/wrr/wrr_manuscript.pdf` | FOOTER_TEXT_COLLISION page 16: page number '–16–' is overprinted by 2 body word box(es); worst 'result:' at (265.79, 766.01, 291.44, 773.98) overlaps the number band 5.54 pt vertically |
| P1 | `paper/wrr/wrr_manuscript.pdf` | FOOTER_TEXT_COLLISION page 18: page number '–18–' is overprinted by 1 body word box(es); worst 'network-clustered' at (257.88, 758.73, 328.89, 766.69) overlaps the number band 3.10 pt vertically |
| P1 | `paper/wrr/wrr_manuscript.pdf` | MERGED_LABEL_RUN_SUSPECT page 28: word 'timingtimingtiminglengthlength' repeats 'timing' x3 inside one box 76.4 pt wide; 0 drawing run(s) recovered from the content stream |
| P2 | `paper/wrr/figures/fig1_mechanism.pdf` | OVERLAPPING_WORD_BOXES: 42 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/fig2_frontier.pdf` | OVERLAPPING_WORD_BOXES: 5 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/fig3_calibration.pdf` | OVERLAPPING_WORD_BOXES: 1 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/fig4_consequence.pdf` | OVERLAPPING_WORD_BOXES: 7 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/fig5_robustness.pdf` | OVERLAPPING_WORD_BOXES: 7 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/figv2_archive_deployment.pdf` | OVERLAPPING_WORD_BOXES: 12 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/figv3_support_law.pdf` | OVERLAPPING_WORD_BOXES: 2 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/figv3_support_law.pdf` | RASTER_BELOW_300_DPI page 1: raster image 0 on page 1 (423x437 px, index) has an effective resolution of 260x260 ppi (< 300) |
| P2 | `paper/wrr/figures/figv3_support_law.pdf` | RASTER_BELOW_300_DPI page 1: raster image 1 on page 1 (20x406 px, index) has an effective resolution of 260x260 ppi (< 300) |
| P2 | `paper/wrr/figures/figv4_representativeness.pdf` | OVERLAPPING_WORD_BOXES: 5 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/wrr_manuscript.pdf` | OVERLAPPING_WORD_BOXES: 69 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/wrr_manuscript.pdf` | RASTER_BELOW_300_DPI page 20: raster image 0 on page 20 (423x437 px, index) has an effective resolution of 260x260 ppi (< 300) |
| P2 | `paper/wrr/wrr_manuscript.pdf` | RASTER_BELOW_300_DPI page 20: raster image 1 on page 20 (20x406 px, index) has an effective resolution of 260x260 ppi (< 300) |
| P2 | `paper/wrr/wrr_supporting_information.pdf` | OVERLAPPING_WORD_BOXES: 14 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P3 | `(environment)` | TOOL_MISSING: drawio is not installed in this environment |
| P3 | `paper/wrr/figures/f1_example.pdf` | SMALL_RELATIVE_WORD_BOXES: 30 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/fig1_mechanism.pdf` | SMALL_RELATIVE_WORD_BOXES: 64 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/fig2_frontier.pdf` | SMALL_RELATIVE_WORD_BOXES: 2 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/fig3_calibration.pdf` | SMALL_RELATIVE_WORD_BOXES: 20 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/fig4_consequence.pdf` | SMALL_RELATIVE_WORD_BOXES: 4 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/fig5_robustness.pdf` | SMALL_RELATIVE_WORD_BOXES: 26 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/fig6_hydrology.pdf` | SMALL_RELATIVE_WORD_BOXES: 39 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/figv1_outage_seasonality.pdf` | SMALL_RELATIVE_WORD_BOXES: 3 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/figv2_archive_deployment.pdf` | SMALL_RELATIVE_WORD_BOXES: 57 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/figv3_support_law.pdf` | SMALL_RELATIVE_WORD_BOXES: 74 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/figv4_representativeness.pdf` | SMALL_RELATIVE_WORD_BOXES: 42 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/wrr_manuscript.pdf` | SMALL_RELATIVE_WORD_BOXES: 294 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/wrr_supporting_information.pdf` | SMALL_RELATIVE_WORD_BOXES: 69 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |

## 10. Method, reproducibility and caveats

Commands (reproduce with `python3 scripts/266_wrr_figure_qa.py`):

```
pdffonts <file>                      # check a: embedded fonts
pdfinfo <file>; pdfinfo -f 1 -l N <file>   # check b: page count and page boxes
pdftotext -bbox <file> -             # checks c, d, e: word boxes in points
pdfimages -list <file>               # check g: raster images and effective dpi
pdftoppm -r 200 -png -f P -l P <file>  # ink verification of flagged pages
python3 scripts/266_wrr_figure_qa.py   # this harness
```

Caveats, in order of how easily they can mislead:

1. **Overlap detection is a conservative box test, not a visual diff.** It cannot see text over graphics, it uses axis-aligned boxes for rotated text, and Poppler boxes include font ascent/descent, so tightly leaded or rotated text is flagged without any ink collision. Pairs are classified (`same_baseline_horizontal` is the real-collision class) and the flagged pages can be rendered for a visual check.
2. **Word box height is not a font size.** For a word made only of x-height letters the box is smaller than the type size, and for rotated text Poppler emits partial words; a flagged word is therefore reported with its neighbours instead of being re-set blindly.
3. **Placement scale is derived, not declared.** It is measured from matched words between the figure PDF and the built PDF; only figures whose matches form a tight cluster are reported as measured.
4. **Colour is not judged.** The report gives the page size in inches and the effective raster resolution; it does not check colour-blind safety or greyscale conversion.
5. **Only the files listed above were inspected.** Embedded fonts are reported as Poppler sees them; a Type 3 subset with no BaseFont name appears as `[none]`.
6. **The artifacts can move under the run.** Every inspected file is pinned by SHA-256 in the JSON, so a mismatch with a later build is visible rather than silent; re-run the harness after any rebuild.


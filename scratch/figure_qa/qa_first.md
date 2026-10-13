# WRR figure and PDF quality assurance

Generated 2026-10-12T13:16:56Z by `python3 scripts/266_wrr_figure_qa.py`.

* JSON: `scratch/figure_qa/qa_first.json`
* Markdown: `scratch/figure_qa/qa_first.md`
* tools: `pdffonts` pdffonts version 22.02.0, `pdfinfo` pdfinfo version 22.02.0, `pdftotext` pdftotext version 22.02.0, `pdfimages` pdfimages version 22.02.0, `pdftoppm` pdftoppm version 22.02.0, `rsvg-convert` rsvg-convert version 2.52.5, `drawio` MISSING

## Verdict

**FAIL** — 810 hard failure(s), 19 warning(s).

Exit status is 1 for the strict run (`--report-only` always exits 0 so the regression test is not turned red by a real finding).

| check | hard failures | warnings |
|---|---|---|
| FONT_NOT_EMBEDDED — font not embedded (check a) | 0 | 0 |
| FIGURE_NOT_SINGLE_PAGE — figure page count != 1 (check b) | 0 | 0 |
| TEXT_OUTSIDE_PAGE — text > 1 pt outside the page (check c) | 21 | 0 |
| TEXT_HEIGHT_BELOW_MINIMUM — word box < 4.5 pt high (check d) | 789 | 0 |
| OVERLAPPING_TEXT_SAME_BASELINE — overlapping boxes, same baseline (check e) | 0 | 0 |
| OVERLAPPING_WORD_BOXES — overlapping boxes, other geometry (check e) | 0 | 10 |
| SCHEMATIC_WITHOUT_DRAWIO_SOURCE — schematic with no draw.io source (check f) | 0 | 0 |
| PROVENANCE_UNKNOWN — neither draw.io nor python source (check f) | 0 | 0 |
| RASTER_BELOW_300_DPI — raster below 300 dpi effective (check g) | 0 | 2 |
| EFFECTIVE_PRINT_TEXT_TOO_SMALL — derived: printed text below 4.5 pt | 0 | 3 |
| INK_FLUSH_TO_PAGE_EDGE — derived: rendered ink flush with the page edge | 0 | 1 |
| TEXT_BOX_PADDING_ONLY — derived: box crosses the edge, ink does not | 0 | 1 |
| FONT_UNNAMED — embedded font with no BaseFont name | 0 | 0 |
| DEGENERATE_WORD_BOXES — word boxes with non-positive height | 0 | 0 |
| FIGURE_NOT_REFERENCED — figure PDF not referenced by any .tex | 0 | 0 |
| PAGE_SIZE_VARIES — page sizes differ within one PDF | 0 | 0 |
| BBOX_PAGE_COUNT_MISMATCH — pdftotext -bbox page count differs from pdfinfo | 0 | 0 |
| BUILT_PDF_MISSING — a built PDF was not found | 0 | 1 |
| TOOL_MISSING — a required tool is not installed | 0 | 1 |

Thresholds: text outside page > 1.0 pt, word box height < 4.5 pt, overlap > 25% of the smaller box, raster < 300 dpi.

## Per-figure master table

| figure | pages | page size (in) | fonts | non-embedded | text outside page | min word height (pt) | overlap pairs | of which same baseline | min raster ppi | source | effective print p05 (pt) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `f0_problem_frame` | 1 | 10.08x7.02 | 5 | 0 | 0 | 7.88 | 0 | 0 | - | drawio | 4.70 | ok |
| `f1_example` | 1 | 5.26x4.98 | 1 | 0 | 19 | 6.38 | 19 | 0 | - | python | 9.14 | HARD |
| `f1_system_architecture` | 1 | 12.11x7.19 | 3 | 0 | 0 | 7.50 | 0 | 0 | - | drawio | 3.58 | warn |
| `f2_experiment_design` | 1 | 12.38x9.50 | 3 | 0 | 0 | 7.50 | 0 | 0 | - | drawio | 4.59 | ok |
| `f3_evidence_chain` | 1 | 12.17x5.81 | 2 | 0 | 0 | 7.88 | 0 | 0 | - | drawio | 3.73 | warn |
| `f4_deployment_workflow` | 1 | 12.17x8.31 | 3 | 0 | 0 | 7.88 | 0 | 0 | - | drawio | 3.56 | warn |
| `fig1_mechanism` | 1 | 5.93x4.79 | 2 | 0 | 0 | 4.29 | 42 | 0 | 300 | python | 1.08 | HARD |
| `fig2_frontier` | 1 | 5.48x4.88 | 1 | 0 | 0 | 5.87 | 5 | 0 | - | python | - | warn |
| `fig3_calibration` | 1 | 5.48x5.00 | 1 | 0 | 0 | 12.10 | 1 | 0 | - | python | - | warn |
| `fig4_consequence` | 1 | 5.49x4.87 | 1 | 0 | 0 | 8.39 | 7 | 0 | - | python | 12.14 | warn |
| `fig5_robustness` | 1 | 5.63x5.00 | 1 | 0 | 0 | 12.10 | 7 | 0 | - | python | 11.83 | warn |
| `fig6_hydrology` | 1 | 5.47x5.00 | 1 | 0 | 0 | 6.75 | 0 | 0 | - | python | - | ok |
| `figv1_outage_seasonality` | 1 | 5.48x4.88 | 1 | 0 | 0 | 6.38 | 0 | 0 | - | python | 3.34 | ok |
| `figv2_archive_deployment` | 1 | 6.18x5.00 | 1 | 0 | 0 | 10.97 | 12 | 0 | - | python | 4.35 | warn |
| `figv3_support_law` | 1 | 5.49x5.00 | 1 | 0 | 0 | 4.29 | 2 | 0 | 260 | python | 1.63 | HARD |
| `figv4_representativeness` | 1 | 5.48x4.88 | 1 | 0 | 0 | 12.10 | 5 | 0 | - | python | 1.44 | warn |

"effective print p05" is the 5th-percentile word-box height multiplied by the measured placement scale in the built PDFs (derived, see the print-size section).

## Built documents

| document | pages | page size (pt) | page size (in) | fonts | non-embedded | text outside page | min word height (pt) | overlap pairs | same baseline | min raster ppi |
|---|---|---|---|---|---|---|---|---|---|---|
| `paper/wrr/wrr_supporting_information.pdf` | 13 | 612.00 x 792.00 | 8.50 x 11.00 | 32 | 0 | 2 | 3.40 | 14 | 0 | - |

## 1. Fonts (check a)

| file | fonts | types | non-embedded | names of non-embedded | unnamed/Type 3 | all embedded |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 5 | CID TrueType x1, CID Type 0C x2, Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/f1_example.pdf` | 1 | Type 3 x1 | 0 | none | `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/figures/f1_system_architecture.pdf` | 3 | CID Type 0C x1, Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/f2_experiment_design.pdf` | 3 | CID Type 0C x1, Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/f3_evidence_chain.pdf` | 2 | Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/f4_deployment_workflow.pdf` | 3 | CID Type 0C x1, Type 1C x2 | 0 | none | none | yes |
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
| `paper/wrr/wrr_supporting_information.pdf` | 32 | CID TrueType x1, CID Type 0C x4, Type 1 x17, Type 1C x8, Type 3 x2 | 0 | none | `BMQQDV+DejaVuSans`, `BMQQDV+DejaVuSans` | yes |

`[none]` is the name Poppler reports for a producer-embedded Type 3 subset with no BaseFont entry (matplotlib's default pdf.fonttype=3); the font is embedded even though it is unnamed.

## 2. Page geometry (check b)

| file | pages | page size (pt) | page size (in) | distinct page sizes | single page | text outside page | max overflow (pt) |
|---|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 1 | 726.00 x 505.50 | 10.08 x 7.02 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f1_example.pdf` | 1 | 378.53 x 358.65 | 5.26 x 4.98 | 1 | yes | 19 | 3.94 |
| `paper/wrr/figures/f1_system_architecture.pdf` | 1 | 872.25 x 517.50 | 12.11 x 7.19 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f2_experiment_design.pdf` | 1 | 891.00 x 684.00 | 12.38 x 9.50 | 1 | yes | 0 | 0.42 |
| `paper/wrr/figures/f3_evidence_chain.pdf` | 1 | 876.00 x 418.50 | 12.17 x 5.81 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f4_deployment_workflow.pdf` | 1 | 876.00 x 598.50 | 12.17 x 8.31 | 1 | yes | 0 | 0.00 |
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
| `paper/wrr/wrr_supporting_information.pdf` | 13 | 612.00 x 792.00 | 8.50 x 11.00 | 1 | no | 2 | 3.35 |

## 3. Text outside the page box (check c)

21 word box(es) cross a page edge by more than 1.0 pt.

| file | page | word | box (x0, y0, x1, y1) | page box | overflow (pt) |
|---|---|---|---|---|---|
| `paper/wrr/figures/f1_example.pdf` | 1 | `water` | (-2.52, 80.21, 10.72, 100.15) | 378.53 x 358.65 | {"left": 2.523} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `temperature` | (-2.52, 33.98, 10.72, 77.98) | 378.53 x 358.65 | {"left": 2.523} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `(°C)` | (-2.52, 17.9, 10.72, 31.75) | 378.53 x 358.65 | {"left": 2.523} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `annual` | (-2.52, 189.54, 10.72, 213.39) | 378.53 x 358.65 | {"left": 2.523} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `mean` | (-2.52, 167.47, 10.72, 187.32) | 378.53 x 358.65 | {"left": 2.523} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `(°C)` | (-2.52, 151.39, 10.72, 165.24) | 378.53 x 358.65 | {"left": 2.523} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `error` | (-3.8, 324.19, 9.43, 341.16) | 378.53 x 358.65 | {"left": 3.804} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `in` | (-3.8, 315.58, 9.43, 321.96) | 378.53 x 358.65 | {"left": 3.804} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `the` | (-3.8, 301.86, 9.43, 313.35) | 378.53 x 358.65 | {"left": 3.804} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `estimate` | (-3.8, 268.84, 9.43, 299.64) | 378.53 x 358.65 | {"left": 3.804} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `(°C)` | (-3.8, 252.77, 9.43, 266.61) | 378.53 x 358.65 | {"left": 3.804} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `a` | (28.61, -3.94, 33.27, 10.43) | 378.53 x 358.65 | {"top": 3.943} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `One` | (38.1, -3.94, 53.58, 10.43) | 378.53 x 358.65 | {"top": 3.943} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `real` | (55.99, -3.94, 70.41, 10.43) | 378.53 x 358.65 | {"top": 3.943} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `station-year` | (72.82, -3.94, 118.56, 10.43) | 378.53 x 358.65 | {"top": 3.943} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `with` | (120.97, -3.94, 137.1, 10.43) | 378.53 x 358.65 | {"top": 3.943} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `two` | (139.52, -3.94, 153.37, 10.43) | 378.53 x 358.65 | {"top": 3.943} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `30-day` | (155.78, -3.94, 182.18, 10.43) | 378.53 x 358.65 | {"top": 3.943} |
| `paper/wrr/figures/f1_example.pdf` | 1 | `gaps` | (184.59, -3.94, 202.86, 10.43) | 378.53 x 358.65 | {"top": 3.943} |
| `paper/wrr/wrr_supporting_information.pdf` | 3 | `SUMMARY.json` | (552.44, 565.97, 615.21, 574.27) | 612.0 x 792.0 | {"right": 3.208} |
| `paper/wrr/wrr_supporting_information.pdf` | 3 | `repo` | (594.43, 585.9, 615.35, 594.19) | 612.0 x 792.0 | {"right": 3.353} |

### Ink verification of the flagged pages

Word boxes carry font ascent/descent padding, so the flagged pages were rendered with `pdftoppm -r 200` and the ink bounding box was measured (grey level < 200 counts as ink, 1.0 pt counts as flush).

| file | page | ink box (l, t, r, b) | margins (l, t, r, b) | verdict | render |
|---|---|---|---|---|---|
| `paper/wrr/figures/f1_example.pdf` | 1 | (1.08, 1.44, 376.92, 356.76) | (1.08, 1.44, 1.61, 1.89) | box padding only, ink inside the page | `scratch/figure_qa/render/ink_f1_example_p1-1.png` |
| `paper/wrr/wrr_supporting_information.pdf` | 3 | (97.20, 29.88, 611.64, 769.68) | (97.20, 29.88, 0.36, 22.32) | ink flush/clipped at the page edge | `scratch/figure_qa/render/ink_wrr_supporting_information_p3-03.png` |

## 4. Minimum text height (check d)

| file | words measured | min height (pt) | 5th percentile (pt) | median (pt) | below 4.5 pt | degenerate boxes |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 225 | 7.88 | 8.62 | 9.38 | 0 | 0 |
| `paper/wrr/figures/f1_example.pdf` | 160 | 6.38 | 11.35 | 12.10 | 0 | 0 |
| `paper/wrr/figures/f1_system_architecture.pdf` | 295 | 7.50 | 7.88 | 8.25 | 0 | 0 |
| `paper/wrr/figures/f2_experiment_design.pdf` | 407 | 7.50 | 7.88 | 8.25 | 0 | 0 |
| `paper/wrr/figures/f3_evidence_chain.pdf` | 190 | 7.88 | 8.25 | 8.25 | 0 | 0 |
| `paper/wrr/figures/f4_deployment_workflow.pdf` | 292 | 7.88 | 7.88 | 8.25 | 0 | 0 |
| `paper/wrr/figures/fig1_mechanism.pdf` | 173 | 4.29 | 10.21 | 13.24 | 1 | 0 |
| `paper/wrr/figures/fig2_frontier.pdf` | 89 | 5.87 | 10.97 | 12.11 | 0 | 0 |
| `paper/wrr/figures/fig3_calibration.pdf` | 143 | 12.10 | 12.10 | 12.86 | 0 | 0 |
| `paper/wrr/figures/fig4_consequence.pdf` | 66 | 8.39 | 12.10 | 12.11 | 0 | 0 |
| `paper/wrr/figures/fig5_robustness.pdf` | 91 | 12.10 | 12.10 | 13.62 | 0 | 0 |
| `paper/wrr/figures/fig6_hydrology.pdf` | 105 | 6.75 | 10.97 | 13.24 | 0 | 0 |
| `paper/wrr/figures/figv1_outage_seasonality.pdf` | 91 | 6.38 | 11.35 | 12.10 | 0 | 0 |
| `paper/wrr/figures/figv2_archive_deployment.pdf` | 130 | 10.97 | 10.97 | 12.10 | 0 | 0 |
| `paper/wrr/figures/figv3_support_law.pdf` | 128 | 4.29 | 10.59 | 12.10 | 1 | 0 |
| `paper/wrr/figures/figv4_representativeness.pdf` | 85 | 12.10 | 12.10 | 14.18 | 0 | 0 |
| `paper/wrr/wrr_supporting_information.pdf` | 4057 | 3.40 | 3.73 | 8.85 | 787 | 0 |

| file | page | word | box (x0, y0, x1, y1) | height (pt) | width (pt) | neighbour words (text: height) |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/fig1_mechanism.pdf` | 1 | `a` | (269.93, 244.56, 283.17, 248.86) | 4.291 | 13.238 | AUC: 13.24, AUC: 14.80, for: 9.62, consequential: 49.08, error: 16.97, c: 14.37 |
| `paper/wrr/figures/figv3_support_law.pdf` | 1 | `a` | (7.3, 274.13, 20.54, 278.42) | 4.291 | 13.238 | 0.05: 12.10, AUC: 14.80, for: 9.62, consequential: 49.08, error: 16.97, (a): 14.37 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `Real` | (140.82, 82.99, 148.43, 86.72) | 3.729 | 7.604 | Water: 7.96, Resources: 7.96, Research: 7.96, archive: 3.73, nine: 3.73, agencies,: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `archive` | (149.46, 82.99, 161.39, 86.72) | 3.729 | 11.923 | Resources: 7.96, Research: 7.96, Real: 3.73, nine: 3.73, agencies,: 3.73, 146: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `nine` | (127.01, 87.77, 134.06, 91.5) | 3.729 | 7.048 | Research: 7.96, Real: 3.73, archive: 3.73, agencies,: 3.73, 146: 3.73, networks,: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `agencies,` | (135.1, 87.77, 150.96, 91.5) | 3.729 | 15.861 | Real: 3.73, archive: 3.73, nine: 3.73, 146: 3.73, networks,: 3.73, 457: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `146` | (152.0, 87.77, 158.22, 91.5) | 3.729 | 6.221 | archive: 3.73, nine: 3.73, agencies,: 3.73, networks,: 3.73, 457: 3.73, stations: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `networks,` | (159.25, 87.77, 175.2, 91.5) | 3.729 | 15.947 | nine: 3.73, agencies,: 3.73, 146: 3.73, 457: 3.73, stations: 3.73, Complete-year: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `457` | (141.09, 92.56, 147.31, 96.29) | 3.729 | 6.221 | agencies,: 3.73, 146: 3.73, networks,: 3.73, stations: 3.73, Complete-year: 3.73, truth: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `stations` | (148.35, 92.56, 161.12, 96.29) | 3.729 | 12.769 | 146: 3.73, networks,: 3.73, 457: 3.73, Complete-year: 3.73, truth: 3.73, 5,114: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `Complete-year` | (233.08, 82.99, 257.31, 86.72) | 3.729 | 24.226 | networks,: 3.73, 457: 3.73, stations: 3.73, truth: 3.73, 5,114: 3.73, fully: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `truth` | (258.34, 82.99, 265.77, 86.72) | 3.729 | 7.425 | 457: 3.73, stations: 3.73, Complete-year: 3.73, 5,114: 3.73, fully: 3.73, observed: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `5,114` | (221.17, 87.77, 230.5, 91.5) | 3.729 | 9.331 | stations: 3.73, Complete-year: 3.73, truth: 3.73, fully: 3.73, observed: 3.73, station-years,: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `fully` | (231.54, 87.77, 238.14, 91.5) | 3.729 | 6.601 | Complete-year: 3.73, truth: 3.73, 5,114: 3.73, observed: 3.73, station-years,: 3.73, never: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `observed` | (239.17, 87.77, 254.54, 91.5) | 3.729 | 15.369 | truth: 3.73, 5,114: 3.73, fully: 3.73, station-years,: 3.73, never: 3.73, imputed: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `station-years,` | (255.58, 87.77, 277.68, 91.5) | 3.729 | 22.100 | 5,114: 3.73, fully: 3.73, observed: 3.73, never: 3.73, imputed: 3.73, Outage: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `never` | (237.7, 92.56, 246.9, 96.29) | 3.729 | 9.197 | fully: 3.73, observed: 3.73, station-years,: 3.73, imputed: 3.73, Outage: 3.73, placed: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `imputed` | (247.93, 92.56, 261.15, 96.29) | 3.729 | 13.213 | observed: 3.73, station-years,: 3.73, never: 3.73, Outage: 3.73, placed: 3.73, 51,524: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `Outage` | (335.63, 82.99, 347.81, 86.72) | 3.729 | 12.180 | station-years,: 3.73, never: 3.73, imputed: 3.73, placed: 3.73, 51,524: 3.73, cases: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `placed` | (348.85, 82.99, 359.85, 86.72) | 3.729 | 11.005 | never: 3.73, imputed: 3.73, Outage: 3.73, 51,524: 3.73, cases: 3.73, on: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `51,524` | (323.47, 87.77, 334.88, 91.5) | 3.729 | 11.404 | imputed: 3.73, Outage: 3.73, placed: 3.73, cases: 3.73, on: 3.73, an: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `cases` | (335.91, 87.77, 345.66, 91.5) | 3.729 | 9.748 | Outage: 3.73, placed: 3.73, 51,524: 3.73, on: 3.73, an: 3.73, empirical: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `on` | (346.7, 87.77, 350.85, 91.5) | 3.729 | 4.147 | placed: 3.73, 51,524: 3.73, cases: 3.73, an: 3.73, empirical: 3.73, and: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `an` | (351.88, 87.77, 356.03, 91.5) | 3.729 | 4.147 | 51,524: 3.73, cases: 3.73, on: 3.73, empirical: 3.73, and: 3.73, a: 3.73 |
| `paper/wrr/wrr_supporting_information.pdf` | 8 | `empirical` | (357.07, 87.77, 372.01, 91.5) | 3.729 | 14.947 | cases: 3.73, on: 3.73, an: 3.73, and: 3.73, a: 3.73, stratified: 3.73 |
| ... | | 764 more in the JSON | | | | |

The box height is Poppler's only per-word size proxy. A rotated text run is emitted as several partial words whose boxes under-report the printed glyph, so a flagged word must be judged together with its neighbours before the type is re-set.

## 5. Overlapping text (check e)

Rule: pairs of word boxes whose intersection area exceeds 25% of the smaller box, exact duplicates and shadow duplicates excluded. **This is a conservative approximation of visual overlap**: it is derived from Poppler word boxes, which are axis-aligned even for rotated text and which include font ascent/descent, and it cannot see text drawn over graphics.

| file | word boxes | candidate pairs | same baseline (real) | adjacent-line padding | atypical box geometry | duplicates ignored (exact/shadow) |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 225 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f1_example.pdf` | 160 | 19 | 0 | 19 | 0 | 0/0 |
| `paper/wrr/figures/f1_system_architecture.pdf` | 295 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f2_experiment_design.pdf` | 407 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f3_evidence_chain.pdf` | 190 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f4_deployment_workflow.pdf` | 292 | 0 | 0 | 0 | 0 | 0/0 |
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
| `paper/wrr/wrr_supporting_information.pdf` | 4057 | 14 | 0 | 14 | 0 | 0/0 |

### Flagged pairs

#### `paper/wrr/figures/f1_example.pdf` — 19 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 1 | adjacent_line_padding | 40.7 | `complete` | (41.16, 221.58, 69.18, 232.92) | `record` | (45.59, 228.3, 64.78, 239.65) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 40.7 | `window` | (96.34, 228.3, 119.11, 239.65) | `A` | (103.99, 221.58, 108.09, 232.92) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 40.7 | `autumn` | (138.72, 228.3, 162.01, 239.65) | `B` | (148.25, 221.58, 152.37, 232.92) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 40.7 | `complete` | (247.98, 221.58, 276.0, 232.92) | `record` | (252.42, 228.3, 271.6, 239.65) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 40.7 | `window` | (303.17, 228.3, 325.94, 239.65) | `A` | (310.81, 221.58, 314.92, 232.92) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 40.7 | `autumn` | (345.55, 228.3, 368.83, 239.65) | `B` | (355.07, 221.58, 359.19, 232.92) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 40.3 | `3.99` | (297.56, 210.92, 310.91, 222.27) | `17.59` | (297.68, 204.19, 314.86, 215.54) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 34.5 | `1.03` | (90.73, 210.68, 104.09, 222.02) | `9.02` | (92.77, 203.95, 106.13, 215.3) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 33.9 | `that` | (220.74, 256.73, 232.93, 268.07) | `A` | (229.32, 249.66, 233.56, 261.39) | 7.06 | 12.10 |
| 1 | adjacent_line_padding | 31.4 | `+0.24` | (129.98, 151.93, 148.36, 163.28) | `10.30` | (135.13, 145.21, 152.3, 156.56) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 31.4 | `+0.00` | (336.8, 146.82, 355.18, 158.16) | `21.58` | (341.95, 140.09, 359.12, 151.44) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 30.5 | `chmi_berounka` | (80.34, 114.82, 126.14, 126.17) | `Apr` | (109.26, 106.4, 120.33, 118.51) | 8.42 | 12.10 |
| 1 | adjacent_line_padding | 30.5 | `0-203-1-198600,` | (150.61, 114.82, 200.99, 126.17) | `Jun` | (168.19, 106.4, 178.19, 118.51) | 8.42 | 12.10 |
| 1 | adjacent_line_padding | 30.5 | `complete` | (279.06, 114.82, 307.09, 126.17) | `Oct` | (284.46, 106.4, 295.53, 118.51) | 8.42 | 12.10 |
| 1 | adjacent_line_padding | 29.5 | `days)` | (309.0, 114.82, 325.5, 126.17) | `Nov` | (313.42, 106.4, 325.92, 118.51) | 8.42 | 12.10 |
| 1 | adjacent_line_padding | 27.5 | `gap` | (135.05, 221.58, 146.34, 232.92) | `autumn` | (138.72, 228.3, 162.01, 239.65) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 27.5 | `gap` | (341.87, 221.58, 353.16, 232.92) | `autumn` | (345.55, 228.3, 368.83, 239.65) | 6.72 | 12.10 |
| 1 | adjacent_line_padding | 27.3 | `Mar` | (79.08, 106.4, 91.16, 118.51) | `chmi_berounka` | (80.34, 114.82, 126.14, 126.17) | 8.42 | 12.10 |
| 1 | adjacent_line_padding | 27.2 | `station` | (128.05, 114.82, 148.7, 126.17) | `May` | (136.9, 106.4, 150.14, 118.51) | 8.42 | 12.10 |

Pair classification: `adjacent_line_padding` x19.

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

#### `paper/wrr/wrr_supporting_information.pdf` — 14 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 12 | adjacent_line_padding | 69.0 | `+` | (409.08, 192.1, 414.97, 205.41) | `7.1` | (409.14, 196.13, 420.95, 210.17) | 4.03 | 11.82 |
| 12 | adjacent_line_padding | 48.8 | `reconstruct,` | (389.72, 447.62, 432.05, 460.92) | `length` | (389.72, 454.43, 412.14, 467.73) | 6.81 | 11.82 |
| 12 | adjacent_line_padding | 48.8 | `reconstruct,` | (389.72, 447.62, 432.05, 460.92) | `rule` | (414.38, 454.43, 428.01, 467.73) | 6.81 | 11.82 |
| 11 | adjacent_line_padding | 44.4 | `days` | (187.64, 347.4, 202.79, 359.54) | `on` | (190.49, 340.66, 198.49, 352.79) | 6.74 | 12.14 |
| 11 | adjacent_line_padding | 44.4 | `length-rule` | (338.57, 340.66, 373.78, 352.79) | `screening` | (340.53, 347.4, 371.79, 359.54) | 6.74 | 12.14 |
| 11 | adjacent_line_padding | 44.4 | `anomalies` | (428.11, 516.27, 461.08, 528.41) | `shuffled` | (431.67, 523.02, 457.48, 535.15) | 6.74 | 12.14 |
| 11 | adjacent_line_padding | 44.4 | `certificate` | (428.42, 340.66, 460.8, 352.79) | `screening` | (428.96, 347.4, 460.22, 359.54) | 6.74 | 12.14 |
| 11 | adjacent_line_padding | 42.5 | `reconstruct,` | (248.42, 340.66, 287.04, 352.79) | `screening` | (257.13, 347.4, 288.39, 359.54) | 6.74 | 12.14 |
| 11 | adjacent_line_padding | 40.0 | `observed` | (155.85, 347.4, 185.6, 359.54) | `compute` | (160.13, 340.66, 188.45, 352.79) | 6.74 | 12.14 |
| 12 | adjacent_line_padding | 37.6 | `(primary)` | (144.28, 214.85, 179.13, 228.89) | `30` | (162.58, 206.09, 172.03, 220.13) | 8.76 | 11.82 |
| 12 | adjacent_line_padding | 37.6 | `(primary)` | (144.28, 214.85, 179.13, 228.89) | `d` | (174.39, 206.09, 179.1, 220.13) | 8.76 | 11.82 |
| 12 | adjacent_line_padding | 37.6 | `window)` | (147.9, 190.64, 178.97, 204.68) | `7` | (167.33, 181.88, 172.05, 195.92) | 8.76 | 11.82 |
| 11 | adjacent_line_padding | 37.0 | `no` | (247.09, 347.4, 255.09, 359.54) | `reconstruct,` | (248.42, 340.66, 287.04, 352.79) | 6.74 | 12.14 |
| 12 | adjacent_line_padding | 36.4 | `window)` | (147.9, 190.64, 178.97, 204.68) | `d` | (174.41, 181.88, 179.13, 195.92) | 8.76 | 11.82 |

Pair classification: `adjacent_line_padding` x14.

## 6. Source provenance (check f)

| figure | draw.io source at figures/v17/drawio | schematic | python generator(s) under scripts/ | classification | verdict |
|---|---|---|---|---|---|
| `f0_problem_frame` | yes | yes — problem frame (drawio README) | none | drawio | ok |
| `f1_example` | NO | no | `scripts/265_wrr_figure1_example.py` | python | ok |
| `f1_system_architecture` | yes | yes — system architecture (drawio README) | none | drawio | ok |
| `f2_experiment_design` | yes | yes — study design and data flow (drawio README) | none | drawio | ok |
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

## 8. Printed size and effective text size (derived)

Method: the scale at which each figure is placed in the built PDFs is measured by matching the figure's distinctive words against the words of the built pages (all pairs of unambiguous matches give a distance ratio; the largest tight cluster is the estimate). `scale x figure width` is the printed width, and raw text heights times the scale give the size the reader sees on paper. These values are derived, never hard failures.

| figure | width (pt) | measured scale | printed width (pt) | printed width (in) | raw min (pt) | raw p05 (pt) | effective min (pt) | effective p05 (pt) | confidence |
|---|---|---|---|---|---|---|---|---|---|
| `f0_problem_frame` | 726.00 | 0.5455 | 396.00 | 5.500 | 7.88 | 8.62 | 4.30 | 4.70 | measured |
| `f1_example` | 378.53 | 0.8058 | 305.03 | 4.237 | 6.38 | 11.35 | 5.14 | 9.14 | low |
| `f1_system_architecture` | 872.25 | 0.4540 | 396.00 | 5.500 | 7.50 | 7.88 | 3.41 | 3.58 | measured |
| `f2_experiment_design` | 891.00 | 0.5830 | 519.48 | 7.215 | 7.50 | 7.88 | 4.37 | 4.59 | low |
| `f3_evidence_chain` | 876.00 | 0.4520 | 395.99 | 5.500 | 7.88 | 8.25 | 3.56 | 3.73 | measured |
| `f4_deployment_workflow` | 876.00 | 0.4520 | 395.99 | 5.500 | 7.88 | 7.88 | 3.56 | 3.56 | measured |
| `fig1_mechanism` | 427.25 | 0.1062 | 45.38 | 0.630 | 4.29 | 10.21 | 0.46 | 1.08 | low |
| `fig2_frontier` | 394.89 | - | - | - | 5.87 | 10.97 | - | - | unavailable |
| `fig3_calibration` | 394.80 | - | - | - | 12.10 | 12.10 | - | - | unavailable |
| `fig4_consequence` | 394.96 | 1.0027 | 396.03 | 5.500 | 8.39 | 12.10 | 8.41 | 12.14 | measured |
| `fig5_robustness` | 405.36 | 0.9770 | 396.03 | 5.500 | 12.10 | 12.10 | 11.83 | 11.83 | measured |
| `fig6_hydrology` | 393.79 | - | - | - | 6.75 | 10.97 | - | - | unavailable |
| `figv1_outage_seasonality` | 394.76 | 0.2944 | 116.23 | 1.614 | 6.38 | 11.35 | 1.88 | 3.34 | low |
| `figv2_archive_deployment` | 444.75 | 0.3962 | 176.20 | 2.447 | 10.97 | 10.97 | 4.35 | 4.35 | low |
| `figv3_support_law` | 395.58 | 0.1535 | 60.73 | 0.843 | 4.29 | 10.59 | 0.66 | 1.63 | low |
| `figv4_representativeness` | 394.78 | 0.1190 | 46.96 | 0.652 | 12.10 | 12.10 | 1.44 | 1.44 | low |

Implied printed width across the 13 figures with a measured scale: median 395.99 pt (5.500 in), range 45.38-519.48 pt. Corroboration: the AGU class file sets `\textwidth 5.5in` = 396 pt (`paper/wrr/template/agujournal2025.cls:958`), consistent with a full-width placement.

AGU/WRR ask for figure text that stays legible in print; a text height below 4.5 pt at printed size is the practical red line used here.

## 9. Prioritised fix list

| priority | file | finding |
|---|---|---|
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'water' box extends 2.52 pt outside the page ({'left': 2.523}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'temperature' box extends 2.52 pt outside the page ({'left': 2.523}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word '(°C)' box extends 2.52 pt outside the page ({'left': 2.523}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'annual' box extends 2.52 pt outside the page ({'left': 2.523}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'mean' box extends 2.52 pt outside the page ({'left': 2.523}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word '(°C)' box extends 2.52 pt outside the page ({'left': 2.523}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'error' box extends 3.80 pt outside the page ({'left': 3.804}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'in' box extends 3.80 pt outside the page ({'left': 3.804}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'the' box extends 3.80 pt outside the page ({'left': 3.804}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'estimate' box extends 3.80 pt outside the page ({'left': 3.804}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word '(°C)' box extends 3.80 pt outside the page ({'left': 3.804}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'a' box extends 3.94 pt outside the page ({'top': 3.943}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'One' box extends 3.94 pt outside the page ({'top': 3.943}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'real' box extends 3.94 pt outside the page ({'top': 3.943}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'station-year' box extends 3.94 pt outside the page ({'top': 3.943}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'with' box extends 3.94 pt outside the page ({'top': 3.943}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'two' box extends 3.94 pt outside the page ({'top': 3.943}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word '30-day' box extends 3.94 pt outside the page ({'top': 3.943}) |
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE: word 'gaps' box extends 3.94 pt outside the page ({'top': 3.943}) |
| P0 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_OUTSIDE_PAGE: word 'SUMMARY.json' box extends 3.21 pt outside the page ({'right': 3.208}) |
| P0 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_OUTSIDE_PAGE: word 'repo' box extends 3.35 pt outside the page ({'right': 3.353}) |
| P1 | `paper/wrr/figures/f1_system_architecture.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 7.88 pt x placement scale 0.4540 = 3.58 pt on paper (< 4.5 pt); the figure is drawn 872 pt wide and printed 396 pt wide |
| P1 | `paper/wrr/figures/f3_evidence_chain.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 8.25 pt x placement scale 0.4520 = 3.73 pt on paper (< 4.5 pt); the figure is drawn 876 pt wide and printed 396 pt wide |
| P1 | `paper/wrr/figures/f4_deployment_workflow.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 7.88 pt x placement scale 0.4520 = 3.56 pt on paper (< 4.5 pt); the figure is drawn 876 pt wide and printed 396 pt wide |
| P1 | `paper/wrr/figures/fig1_mechanism.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'a' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/figures/fig1_mechanism.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 10.21 pt x placement scale 0.1062 = 1.08 pt on paper (< 4.5 pt); the figure is drawn 427 pt wide and printed 45 pt wide |
| P1 | `paper/wrr/figures/figv1_outage_seasonality.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 11.35 pt x placement scale 0.2944 = 3.34 pt on paper (< 4.5 pt); the figure is drawn 395 pt wide and printed 116 pt wide |
| P1 | `paper/wrr/figures/figv2_archive_deployment.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 10.97 pt x placement scale 0.3962 = 4.35 pt on paper (< 4.5 pt); the figure is drawn 445 pt wide and printed 176 pt wide |
| P1 | `paper/wrr/figures/figv3_support_law.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'a' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/figures/figv3_support_law.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 10.59 pt x placement scale 0.1535 = 1.63 pt on paper (< 4.5 pt); the figure is drawn 396 pt wide and printed 61 pt wide |
| P1 | `paper/wrr/figures/figv4_representativeness.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 12.10 pt x placement scale 0.1190 = 1.44 pt on paper (< 4.5 pt); the figure is drawn 395 pt wide and printed 47 pt wide |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Real' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'archive' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'nine' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'agencies,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '146' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'networks,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '457' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'stations' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Complete-year' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'truth' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '5,114' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'fully' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'observed' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'station-years,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'never' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'imputed' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Outage' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'placed' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '51,524' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'cases' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'an' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'empirical' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'a' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'stratified' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'arm' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Reconstruction' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'six' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'estimators,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'support' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'declared' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'per' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'case' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'RQ5,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'RQ6' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'held' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'out' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'honest' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '36' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'reserved' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'networks' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'opened' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'once;' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'coverage' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'checked' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'RQ3,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'RQ3b,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'RQ4' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'act' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'it' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'frontier,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'an' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'incumbent' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'armed' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'with' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'an' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'oracle,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'ablation' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'RQ1,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'RQ2' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'which' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'axis' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'governs' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'reversal,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'its' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'mechanism,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'which' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'rivers' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'are' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'hard' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'RQ0' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'does' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'problem' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'exist' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '1.305' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '°C' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'recorded' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'days,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '1.23' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'interannual' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'SD' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'RQ7' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'downstream' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'judgement' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'exceedance' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'counts' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'trends,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'simulated' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'cases' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'RQ8' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'survives' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'its' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'assumptions' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'reference' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'noise,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'prior-years' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'fitting,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'transfer' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'across' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'nine' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'agencies' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Deployment' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'closed' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '2,422' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'real' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'incomplete' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'station-years' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'decided;' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'two' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'rules' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'disagree' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '15.1%' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Consequence' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'closed,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'small' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '17' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'station-years' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'with' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'an' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'unobserved' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'peak' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'removed;' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'regional' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'mean' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'moves' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '<' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '0.1' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '°C' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'loop' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'closed' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'The' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'loop' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'closed:' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'a' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'decision' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'taken' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'records' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'that' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'really' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'have' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'holes' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'changes' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'which' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'station-years' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'enter' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'archive.' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'What' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'it' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'does' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'not' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'change' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'much' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'regional' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'mean,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'that' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'reported' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'too.' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'conditioning' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'set' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'matches' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'support' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'conditioning' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'set' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'ignores' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'support' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Visible' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'at' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'decision' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'time' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Outage' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'geometry' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'longest' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'run,' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'total' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'missing,' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'number' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'of' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'runs' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Estimator' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'library' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'support' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'declared' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'per' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'case' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'observed' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'days' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '(current' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'practice)' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '·' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'day-of-year' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'climatology' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'smoothed' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'climatology' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '·' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'linear' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'interpolation' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '(both' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'flanks' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'required)' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'donor' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'ridge' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '(refit' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'visible' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'donors)' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '·' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'air' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'ridge' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '(where' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'forcing' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'exists)' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Support' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'of' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'estimand' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'peak-window' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'overlap,' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'warm-season' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'observed' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'fraction' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Constraint' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'already' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'imposed' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'by' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'observed' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'days' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'observed-peak' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'margin,' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'which' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'flanks' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'survived' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Fitted' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'leave-one-year-out' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'within' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'station.' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '§5.10' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'repeats' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'study' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'under' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'strictly-prior-years' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'fitting.' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'completed-year' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'statistic' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'per' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'estimator' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Risk' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'model' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'predicted' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'upper' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'bound' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '\|' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'q(ŷ)' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '−' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'q(y)' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '\|' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'for' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'each' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'supported' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'estimator' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Absent' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'donor' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'columns' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'are' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'never' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'imputed;' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'model' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'refit' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'visible' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'subset.' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Donor' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'information' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'count,' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'coverage,' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'training-period' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'deseasonalised' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'correlation' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Estimator' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'selection' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'take' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'smallest' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'bound' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Station' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'history' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'record' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'length,' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'training' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'residual' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'scale,' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'seasonal' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'amplitude' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'enforced' box is 3.40 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.40 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'every' box is 3.40 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'feature' box is 3.40 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Information' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'barrier' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'No' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'feature' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'may' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'read' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'a' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'day' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'outage' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'hides.' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Enforced' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'in' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'feature_frame;' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'pinned' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'by' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'a' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'test' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'in' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'suite.' box is 3.92 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Split-conformal' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'calibration' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'selection-conditional' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'calibrated' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'after' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'estimator' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'chosen,' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'because' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'taking' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'smallest' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'of' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'several' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'bounds' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'a' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'winner’s' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'curse' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'that' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'per-estimator' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'calibration' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'cannot' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'see' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'multiplicative' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'error' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'scale' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'spans' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'an' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'order' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'of' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'magnitude' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Fitting,' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'calibration' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'test' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'networks' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'are' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'always' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'disjoint.' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Every' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'interval' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'resamples' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'whole' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'networks.' box is 3.58 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Calibrated' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'certificate' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'for' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'this' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'station-year' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'an' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'interval' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'completed-year' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'statistic,' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'in' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '°C,' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'a' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'risk' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'score' box is 4.09 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Action' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'space' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '1' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'admission' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'retain' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'or' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'exclude' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'station-year' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'at' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'a' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'tolerance' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'τ' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'stated' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'in' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '°C.' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Decides' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'what' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'enters' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'archive.' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Reserved' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'panel' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'at' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '70%' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'retention:' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '2.5%' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'against' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '9.7%' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'for' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'length' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'rule.' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Action' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'space' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '2' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'abstention' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'keep' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'every' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'year' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'decline' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'only' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'judgement' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'interval' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'cannot' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'support.' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Decides' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'what' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'one' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'judgement' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'may' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'say.' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Judges' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '92.7%' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'of' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'years' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'at' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '0.42%' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'misclassification' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'against' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '67.5%' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'at' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '0.36%.' box is 3.75 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'A' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'station-year' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'with' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'an' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'outage' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'arrives' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'at' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'archive' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Which' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'statistic' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'will' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'be' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'computed' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'from' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'this' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'year?' box is 4.07 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'An' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'average' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'over' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'year' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'annual' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'mean,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'coldest' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '30-day' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'mean' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Keep' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'completeness' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'rule' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'you' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'have.' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Threshold' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'number' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'of' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'missing' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'days.' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'On' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'our' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'panel' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'length' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'better' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'axis' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'for' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'these' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'endpoints' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '(AUC' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '0.845' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'against' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '0.672' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'for' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'peak-window' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'overlap).' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'A' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'warm-season' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'extreme' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'hottest' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '7-day' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'or' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '30-day' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'mean' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Locate' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'station’s' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'climatological' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'peak' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'window' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'from' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'its' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'own' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'complete' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'years' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'no' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'data' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'beyond' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'station’s' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'own' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'record' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'needed' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Compute' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'three' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'numbers' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'from' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'outage' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'mask' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'alone' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'peak_overlap' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '·' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'warm_observed_fraction' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '·' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'longest_run_days' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'risk' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '=' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'logistic(' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '−1.302' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '+' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '2.070' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '·' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'peak_overlap' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '−' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '2.412' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '·' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'warm_observed_fraction' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '−' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '0.00187' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '·' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'longest_run_days' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word ')' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Rank' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'station-years' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'by' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'risk' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'admit' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'down' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'to' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'retention' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'monitoring' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'programme' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'can' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'afford' box is 3.90 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'If' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'an' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'uncertainty' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'statement' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'in' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '°C' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'needed,' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'run' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'calibrated' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'screen' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'instead' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'of' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'three-variable' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'rule' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'report' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'its' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'interval.' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Where' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'validity' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'needed' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'at' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'one' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'site,' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'use' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'cluster' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'calibration:' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'about' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '1.5×' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'wider' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'intervals,' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'admission' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'decision' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'unchanged.' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'If' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'question' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'a' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'single' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'threshold' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'judgement' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'was' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'this' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'year' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'above' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'a' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'criterion' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'do' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'not' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'discard' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'year.' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Decline' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'only' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'judgement' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'interval' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'cannot' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'support:' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '93%' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'of' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'years' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'judged' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'at' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'same' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'error' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'rate.' box is 3.56 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'Before' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'adopting' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'it,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'check' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'what' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'rule' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'keeps' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'report' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'retention' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'by' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'site' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'elevation,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'basin' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'slope' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'and' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'donor' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'availability.' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'If' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'retained' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'archive' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'is' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'not' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'representative,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'apply' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'threshold' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'within' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'stratum' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'rather' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'than' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'globally' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '—' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'our' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'panel' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'that' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'costs' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '0.2' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'points' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'or' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'less.' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'What' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'it' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'buys,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'on' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '36' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'networks' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'never' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'used' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'for' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'fitting,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'at' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '70%' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'retention' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '4.2%' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'of' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'retained' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'years' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'wrong' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'by' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'more' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'than' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '0.5' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '°C' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'with' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'three-variable' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'rule,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '2.5%' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'with' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'calibrated' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'screen,' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'against' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word '9.7%' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'for' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'the' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'length' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_HEIGHT_BELOW_MINIMUM: word 'rule' box is 3.73 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_supporting_information.pdf` | INK_FLUSH_TO_PAGE_EDGE: rendered ink reaches within 1.0 pt of the page edge (margins {'left': 97.2, 'top': 29.88, 'right': 0.36, 'bottom': 22.32}): glyphs are clipped or flush |
| P2 | `paper/wrr/figures/f1_example.pdf` | OVERLAPPING_WORD_BOXES: 19 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/fig1_mechanism.pdf` | OVERLAPPING_WORD_BOXES: 42 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/fig2_frontier.pdf` | OVERLAPPING_WORD_BOXES: 5 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/fig3_calibration.pdf` | OVERLAPPING_WORD_BOXES: 1 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/fig4_consequence.pdf` | OVERLAPPING_WORD_BOXES: 7 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/fig5_robustness.pdf` | OVERLAPPING_WORD_BOXES: 7 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/figv2_archive_deployment.pdf` | OVERLAPPING_WORD_BOXES: 12 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/figv3_support_law.pdf` | OVERLAPPING_WORD_BOXES: 2 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/figures/figv3_support_law.pdf` | RASTER_BELOW_300_DPI: raster image 0 on page 1 (423x437 px, index) has an effective resolution of 260x260 ppi (< 300) |
| P2 | `paper/wrr/figures/figv3_support_law.pdf` | RASTER_BELOW_300_DPI: raster image 1 on page 1 (20x406 px, index) has an effective resolution of 260x260 ppi (< 300) |
| P2 | `paper/wrr/figures/figv4_representativeness.pdf` | OVERLAPPING_WORD_BOXES: 5 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/wrr_supporting_information.pdf` | OVERLAPPING_WORD_BOXES: 14 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P3 | `paper/wrr/figures/f1_example.pdf` | TEXT_BOX_PADDING_ONLY: word boxes cross the page edge but the rendered ink stays 1.08 pt inside: Poppler font-descent padding, no clipped glyph |
| P3 | `paper/wrr/figures/f1_system_architecture.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: 5th-percentile word height 7.88 pt x measured placement scale 0.4540 = 3.58 pt on paper (< 4.5 pt) |
| P3 | `paper/wrr/figures/f3_evidence_chain.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: 5th-percentile word height 8.25 pt x measured placement scale 0.4520 = 3.73 pt on paper (< 4.5 pt) |
| P3 | `paper/wrr/figures/f4_deployment_workflow.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: 5th-percentile word height 7.88 pt x measured placement scale 0.4520 = 3.56 pt on paper (< 4.5 pt) |

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


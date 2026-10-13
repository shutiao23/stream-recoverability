# WRR figure and PDF quality assurance

Generated 2026-10-12T13:22:07Z by `python3 scripts/266_wrr_figure_qa.py`.

* JSON: `scratch/figure_qa/qa2.json`
* Markdown: `scratch/figure_qa/qa2.md`
* tools: `pdffonts` pdffonts version 22.02.0, `pdfinfo` pdfinfo version 22.02.0, `pdftotext` pdftotext version 22.02.0, `pdfimages` pdfimages version 22.02.0, `pdftoppm` pdftoppm version 22.02.0, `rsvg-convert` rsvg-convert version 2.52.5, `drawio` MISSING

## Verdict

**FAIL** — 882 hard failure(s) in 24 file/check/page group(s), 38 warning(s).

Exit status is 1 for the strict run (`--report-only` always exits 0 so the regression test is not turned red by a real finding).

| check | hard failures | warnings |
|---|---|---|
| FONT_NOT_EMBEDDED — font not embedded (check a) | 0 | 0 |
| FIGURE_NOT_SINGLE_PAGE — figure page count != 1 (check b) | 0 | 0 |
| TEXT_OUTSIDE_PAGE — text > 1 pt outside the page (check c) | 58 | 0 |
| TEXT_HEIGHT_BELOW_MINIMUM — word box < 4.5 pt high (check d) | 824 | 0 |
| OVERLAPPING_TEXT_SAME_BASELINE — overlapping boxes, same baseline (check e) | 0 | 0 |
| OVERLAPPING_WORD_BOXES — overlapping boxes, other geometry (check e) | 0 | 11 |
| MERGED_LABEL_RUN_SUSPECT — labels drawn with no word gap (check e) | 0 | 3 |
| SCHEMATIC_WITHOUT_DRAWIO_SOURCE — schematic with no draw.io source (check f) | 0 | 0 |
| PROVENANCE_UNKNOWN — neither draw.io nor python source (check f) | 0 | 0 |
| RASTER_BELOW_300_DPI — raster below 300 dpi effective (check g) | 0 | 6 |
| EFFECTIVE_PRINT_TEXT_TOO_SMALL — derived: printed text below 4.5 pt | 0 | 4 |
| INK_FLUSH_TO_PAGE_EDGE — derived: rendered ink flush with the page edge | 0 | 10 |
| TEXT_BOX_PADDING_ONLY — derived: box crosses the edge, ink does not | 0 | 2 |
| FONT_UNNAMED — embedded font with no BaseFont name | 0 | 1 |
| DEGENERATE_WORD_BOXES — word boxes with non-positive height | 0 | 0 |
| FIGURE_NOT_REFERENCED — figure PDF not referenced by any .tex | 0 | 0 |
| PAGE_SIZE_VARIES — page sizes differ within one PDF | 0 | 0 |
| BBOX_PAGE_COUNT_MISMATCH — pdftotext -bbox page count differs from pdfinfo | 0 | 0 |
| BUILT_PDF_MISSING — a built PDF was not found | 0 | 0 |
| TOOL_MISSING — a required tool is not installed | 0 | 1 |

Thresholds: text outside page > 1.0 pt, word box height < 4.5 pt, overlap > 25% of the smaller box, raster < 300 dpi.

## Per-figure master table

| figure | pages | page size (in) | fonts | non-embedded | text outside page | min word height (pt) | overlap pairs | of which same baseline | min raster ppi | source | effective print p05 (pt) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `f0_problem_frame` | 1 | 10.08x7.02 | 5 | 0 | 0 | 7.88 | 0 | 0 | - | drawio | 4.70 | ok |
| `f1_example` | 1 | 5.26x4.98 | 1 | 0 | 19 | 6.38 | 19 | 0 | - | python | 11.87 | HARD |
| `f1_system_architecture` | 1 | 12.11x7.19 | 3 | 0 | 0 | 7.50 | 0 | 0 | - | drawio | 3.58 | warn |
| `f2_experiment_design` | 1 | 12.38x9.50 | 3 | 0 | 0 | 7.50 | 0 | 0 | - | drawio | 3.50 | warn |
| `f2a_endpoint_ordering` | 1 | 5.43x2.51 | 1 | 0 | 0 | 6.99 | 0 | 0 | - | python | 7.08 | ok |
| `f2b_panel_heterogeneity` | 1 | 5.29x4.05 | 1 | 0 | 0 | 6.99 | 0 | 0 | - | python | 7.27 | ok |
| `f3_evidence_chain` | 1 | 12.17x5.81 | 2 | 0 | 0 | 7.88 | 0 | 0 | - | drawio | 3.73 | warn |
| `f4_deployment_workflow` | 1 | 12.17x8.31 | 3 | 0 | 0 | 7.88 | 0 | 0 | - | drawio | 3.56 | warn |
| `fig1_mechanism` | 1 | 5.93x4.79 | 2 | 0 | 0 | 4.29 | 42 | 0 | 300 | python | 9.47 | HARD |
| `fig2_frontier` | 1 | 5.48x4.88 | 1 | 0 | 0 | 5.87 | 5 | 0 | - | python | 11.00 | warn |
| `fig3_calibration` | 1 | 5.48x5.00 | 1 | 0 | 0 | 12.10 | 1 | 0 | - | python | 12.14 | warn |
| `fig4_consequence` | 1 | 5.49x4.87 | 1 | 0 | 0 | 8.39 | 7 | 0 | - | python | 12.14 | warn |
| `fig5_robustness` | 1 | 5.63x5.00 | 1 | 0 | 0 | 12.10 | 7 | 0 | - | python | 11.83 | warn |
| `fig6_hydrology` | 1 | 5.47x5.00 | 1 | 0 | 0 | 6.75 | 0 | 0 | - | python | 11.03 | ok |
| `figv1_outage_seasonality` | 1 | 5.48x4.88 | 1 | 0 | 0 | 6.38 | 0 | 0 | - | python | 11.38 | ok |
| `figv2_archive_deployment` | 1 | 6.18x5.00 | 1 | 0 | 0 | 10.97 | 12 | 0 | - | python | 9.77 | warn |
| `figv3_support_law` | 1 | 5.49x5.00 | 1 | 0 | 0 | 4.29 | 2 | 0 | 260 | python | 10.60 | HARD |
| `figv4_representativeness` | 1 | 5.48x4.88 | 1 | 0 | 0 | 12.10 | 5 | 0 | - | python | 12.14 | warn |

"effective print p05" is the 5th-percentile word-box height multiplied by the measured placement scale in the built PDFs (derived, see the print-size section).

## Built documents

| document | pages | page size (pt) | page size (in) | fonts | non-embedded | text outside page | min word height (pt) | overlap pairs | same baseline | min raster ppi |
|---|---|---|---|---|---|---|---|---|---|---|
| `paper/wrr/wrr_manuscript.pdf` | 51 | 612.00 x 792.00 | 8.50 x 11.00 | 40 | 0 | 18 | 3.33 | 87 | 0 | 260 |
| `paper/wrr/wrr_supporting_information.pdf` | 14 | 612.00 x 792.00 | 8.50 x 11.00 | 33 | 0 | 2 | 5.31 | 0 | 0 | - |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 49 | 612.00 x 792.00 | 8.50 x 11.00 | 39 | 0 | 19 | 3.33 | 87 | 0 | 260 |

## 1. Fonts (check a)

| file | fonts | types | non-embedded | names of non-embedded | unnamed/Type 3 | all embedded |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 5 | CID TrueType x1, CID Type 0C x2, Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/f1_example.pdf` | 1 | Type 3 x1 | 0 | none | `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/figures/f1_system_architecture.pdf` | 3 | CID Type 0C x1, Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/f2_experiment_design.pdf` | 3 | CID Type 0C x1, Type 1C x2 | 0 | none | none | yes |
| `paper/wrr/figures/f2a_endpoint_ordering.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/f2b_panel_heterogeneity.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
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
| `paper/wrr/wrr_manuscript.pdf` | 40 | CID TrueType x2, CID Type 0C x1, Type 1 x26, Type 1C x2, Type 3 x9 | 0 | none | `BMQQDV+DejaVuSans`, `BMQQDV+DejaVuSans`, `BMQQDV+DejaVuSans`, `EVICAO+DejaVuSans-Bold`, `BMQQDV+DejaVuSans`, `BMQQDV+DejaVuSans` | yes |
| `paper/wrr/wrr_supporting_information.pdf` | 33 | CID TrueType x1, CID Type 0C x4, Type 1 x17, Type 1C x8, Type 3 x3 | 0 | none | `BMQQDV+DejaVuSans`, `BMQQDV+DejaVuSans`, `BMQQDV+DejaVuSans` | yes |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 39 | CID Type 0C x1, Type 1 x25, Type 1C x2, Type 3 x11 | 0 | none | `[none]` | yes |

`[none]` is the name Poppler reports for a producer-embedded Type 3 subset with no BaseFont entry (matplotlib's default pdf.fonttype=3); the font is embedded even though it is unnamed.

## 2. Page geometry (check b)

| file | pages | page size (pt) | page size (in) | distinct page sizes | single page | text outside page | max overflow (pt) |
|---|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 1 | 726.00 x 505.50 | 10.08 x 7.02 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f1_example.pdf` | 1 | 378.53 x 358.65 | 5.26 x 4.98 | 1 | yes | 19 | 3.94 |
| `paper/wrr/figures/f1_system_architecture.pdf` | 1 | 872.25 x 517.50 | 12.11 x 7.19 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f2_experiment_design.pdf` | 1 | 891.00 x 684.00 | 12.38 x 9.50 | 1 | yes | 0 | 0.42 |
| `paper/wrr/figures/f2a_endpoint_ordering.pdf` | 1 | 391.11 x 180.98 | 5.43 x 2.51 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f2b_panel_heterogeneity.pdf` | 1 | 380.62 x 291.75 | 5.29 x 4.05 | 1 | yes | 0 | 0.00 |
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
| `paper/wrr/wrr_manuscript.pdf` | 51 | 612.00 x 792.00 | 8.50 x 11.00 | 1 | no | 18 | 2.41 |
| `paper/wrr/wrr_supporting_information.pdf` | 14 | 612.00 x 792.00 | 8.50 x 11.00 | 1 | no | 2 | 3.35 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 49 | 612.00 x 792.00 | 8.50 x 11.00 | 1 | no | 19 | 4.93 |

## 3. Text outside the page box (check c)

58 word box(es) cross a page edge by more than 1.0 pt.

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
| `paper/wrr/wrr_manuscript.pdf` | 7 | `sensitivity/` | (550.25, 725.37, 613.02, 733.67) | 612.0 x 792.0 | {"right": 1.019} |
| `paper/wrr/wrr_manuscript.pdf` | 8 | `stations.cs` | (555.96, 91.75, 613.49, 100.05) | 612.0 x 792.0 | {"right": 1.493} |
| `paper/wrr/wrr_manuscript.pdf` | 9 | `seal` | (593.49, 151.52, 614.41, 159.82) | 612.0 x 792.0 | {"right": 2.407} |
| `paper/wrr/wrr_manuscript.pdf` | 16 | `station-year` | (97.2, 785.62, 144.89, 793.59) | 612.0 x 792.0 | {"bottom": 1.586} |
| `paper/wrr/wrr_manuscript.pdf` | 16 | `belongs` | (147.96, 785.62, 177.96, 793.59) | 612.0 x 792.0 | {"bottom": 1.586} |
| `paper/wrr/wrr_manuscript.pdf` | 16 | `to` | (181.04, 785.62, 189.23, 793.59) | 612.0 x 792.0 | {"bottom": 1.586} |
| ... | | 33 more in the JSON | | | |

### Ink verification of the flagged pages

Word boxes carry font ascent/descent padding, so the flagged pages were rendered with `pdftoppm -r 200` and the ink bounding box was measured (grey level < 200 counts as ink, 1.0 pt counts as flush).

| file | page | ink box (l, t, r, b) | margins (l, t, r, b) | verdict | render |
|---|---|---|---|---|---|
| `paper/wrr/figures/f1_example.pdf` | 1 | (1.08, 1.44, 376.92, 356.76) | (1.08, 1.44, 1.61, 1.89) | box padding only, ink inside the page | `scratch/figure_qa/render/ink_f1_example_p1-1.png` |
| `paper/wrr/wrr_manuscript.pdf` | 7 | (97.20, 29.88, 611.64, 769.68) | (97.20, 29.88, 0.36, 22.32) | ink flush/clipped at the page edge | `scratch/figure_qa/render/ink_wrr_manuscript_p7-07.png` |
| `paper/wrr/wrr_manuscript.pdf` | 8 | (97.20, 29.88, 611.64, 769.68) | (97.20, 29.88, 0.36, 22.32) | ink flush/clipped at the page edge | `scratch/figure_qa/render/ink_wrr_manuscript_p8-08.png` |
| `paper/wrr/wrr_manuscript.pdf` | 9 | (97.20, 29.88, 611.64, 769.68) | (97.20, 29.88, 0.36, 22.32) | ink flush/clipped at the page edge | `scratch/figure_qa/render/ink_wrr_manuscript_p9-09.png` |
| `paper/wrr/wrr_manuscript.pdf` | 16 | (191.52, 29.88, 399.24, 37.44) | (191.52, 29.88, 212.76, 754.56) | box padding only, ink inside the page | `scratch/figure_qa/render/ink_wrr_manuscript_p16-16.png` |
| `paper/wrr/wrr_manuscript.pdf` | 33 | (97.20, 29.88, 611.64, 769.68) | (97.20, 29.88, 0.36, 22.32) | ink flush/clipped at the page edge | `scratch/figure_qa/render/ink_wrr_manuscript_p33-33.png` |
| `paper/wrr/wrr_manuscript.pdf` | 48 | - | - | unavailable: pdftoppm produced no image (rc=1): Syntax Error: Couldn't find trailer dictionary Syntax Error: Couldn't find trailer dictionary Syntax Error: Couldn't read xref table | - |
| `paper/wrr/wrr_supporting_information.pdf` | 3 | - | - | unavailable: pdftoppm produced no image (rc=1): Syntax Error: Couldn't find trailer dictionary Syntax Error: Couldn't find trailer dictionary Syntax Error: Couldn't read xref table | - |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 5 | (97.20, 29.88, 492.12, 791.64) | (97.20, 29.88, 119.88, 0.36) | ink flush/clipped at the page edge | `scratch/figure_qa/render/ink_wrr_manuscript_HEAD_p5-05.png` |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 9 | (97.20, 29.88, 611.64, 769.68) | (97.20, 29.88, 0.36, 22.32) | ink flush/clipped at the page edge | `scratch/figure_qa/render/ink_wrr_manuscript_HEAD_p9-09.png` |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 10 | (97.20, 29.88, 611.64, 769.68) | (97.20, 29.88, 0.36, 22.32) | ink flush/clipped at the page edge | `scratch/figure_qa/render/ink_wrr_manuscript_HEAD_p10-10.png` |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 11 | (97.20, 29.88, 611.64, 769.32) | (97.20, 29.88, 0.36, 22.68) | ink flush/clipped at the page edge | `scratch/figure_qa/render/ink_wrr_manuscript_HEAD_p11-11.png` |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 30 | (97.20, 29.88, 611.64, 769.68) | (97.20, 29.88, 0.36, 22.32) | ink flush/clipped at the page edge | `scratch/figure_qa/render/ink_wrr_manuscript_HEAD_p30-30.png` |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 46 | (97.20, 29.88, 611.64, 769.68) | (97.20, 29.88, 0.36, 22.32) | ink flush/clipped at the page edge | `scratch/figure_qa/render/ink_wrr_manuscript_HEAD_p46-46.png` |

## 4. Minimum text height (check d)

| file | words measured | min height (pt) | 5th percentile (pt) | median (pt) | below 4.5 pt | degenerate boxes |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 225 | 7.88 | 8.62 | 9.38 | 0 | 0 |
| `paper/wrr/figures/f1_example.pdf` | 160 | 6.38 | 11.35 | 12.10 | 0 | 0 |
| `paper/wrr/figures/f1_system_architecture.pdf` | 295 | 7.50 | 7.88 | 8.25 | 0 | 0 |
| `paper/wrr/figures/f2_experiment_design.pdf` | 407 | 7.50 | 7.88 | 8.25 | 0 | 0 |
| `paper/wrr/figures/f2a_endpoint_ordering.pdf` | 67 | 6.99 | 6.99 | 7.22 | 0 | 0 |
| `paper/wrr/figures/f2b_panel_heterogeneity.pdf` | 108 | 6.99 | 6.99 | 7.46 | 0 | 0 |
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
| `paper/wrr/wrr_manuscript.pdf` | 17773 | 3.33 | 7.08 | 8.85 | 411 | 0 |
| `paper/wrr/wrr_supporting_information.pdf` | 1291 | 5.31 | 8.30 | 8.85 | 0 | 0 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 17056 | 3.33 | 7.08 | 8.85 | 411 | 0 |

Grouped by page (one placed figure can carry hundreds of words below the threshold, so the cause is stated once here):

| file | page | words below threshold | min height (pt) | median height (pt) | example words | attributed figure |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/fig1_mechanism.pdf` | 1 | 1 | 4.291 | 4.291 | a | - |
| `paper/wrr/figures/figv3_support_law.pdf` | 1 | 1 | 4.291 | 4.291 | a | - |
| `paper/wrr/wrr_manuscript.pdf` | 5 | 1 | 4.423 | 4.423 | t | f1_example |
| `paper/wrr/wrr_manuscript.pdf` | 10 | 408 | 3.333 | 3.667 | (0.136, (19,036):, (32,488):, (95%, (CH), (CZ), (DE), (FI) | f2_experiment_design |
| `paper/wrr/wrr_manuscript.pdf` | 20 | 1 | 4.296 | 4.296 | a | figv3_support_law |
| `paper/wrr/wrr_manuscript.pdf` | 27 | 1 | 3.977 | 3.977 | a | f2_experiment_design |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 8 | 1 | 4.423 | 4.423 | t | f2_experiment_design |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | 408 | 3.333 | 3.667 | (0.136, (19,036):, (32,488):, (95%, (CH), (CZ), (DE), (FI) | f2_experiment_design |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 20 | 1 | 4.296 | 4.296 | a | figv3_support_law |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 22 | 1 | 3.977 | 3.977 | a | fig1_mechanism |

Smallest boxes overall (up to 25 rows):

| file | page | word | box (x0, y0, x1, y1) | height (pt) | width (pt) | neighbour words (text: height) |
|---|---|---|---|---|---|---|
| `paper/wrr/wrr_manuscript.pdf` | 10 | `sealed` | (461.02, 405.95, 470.82, 409.29) | 3.333 | 9.797 | observed: 3.67, complete-year: 3.67, truth: 3.67, until: 3.33, the: 3.33, freeze: 3.33 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `until` | (471.74, 405.95, 477.84, 409.29) | 3.333 | 6.094 | complete-year: 3.67, truth: 3.67, sealed: 3.33, the: 3.33, freeze: 3.33, exists: 3.33 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `the` | (478.76, 405.95, 483.38, 409.29) | 3.333 | 4.613 | truth: 3.67, sealed: 3.33, until: 3.33, freeze: 3.33, exists: 3.33, Gate: 3.67 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `freeze` | (484.3, 405.95, 493.4, 409.29) | 3.333 | 9.100 | sealed: 3.33, until: 3.33, the: 3.33, exists: 3.33, Gate: 3.67, before: 3.67 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `exists` | (494.33, 405.95, 502.74, 409.29) | 3.333 | 8.414 | until: 3.33, the: 3.33, freeze: 3.33, Gate: 3.67, before: 3.67, rule: 3.67 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `the` | (272.18, 450.95, 276.79, 454.29) | 3.333 | 4.613 | resolves: 3.67, 1.44: 3.67, points: 3.67, frozen: 3.33, rule,: 3.33, unchanged: 3.33 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `frozen` | (277.72, 450.95, 286.82, 454.29) | 3.333 | 9.104 | 1.44: 3.67, points: 3.67, the: 3.33, rule,: 3.33, unchanged: 3.33, Mechanism: 3.67 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `rule,` | (287.75, 450.95, 294.16, 454.29) | 3.333 | 6.414 | points: 3.67, the: 3.33, frozen: 3.33, unchanged: 3.33, Mechanism: 3.67, (H1): 3.67 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `unchanged` | (295.09, 450.95, 311.56, 454.29) | 3.333 | 16.474 | the: 3.33, frozen: 3.33, rule,: 3.33, Mechanism: 3.67, (H1): 3.67, ·: 3.67 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `scored` | (379.46, 454.12, 389.46, 457.45) | 3.333 | 9.997 | disjoint: 3.67, Figure: 7.96, 1.: 7.96, once: 3.33, Reserved: 3.67, panel: 3.67 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `once` | (390.38, 454.12, 397.63, 457.45) | 3.333 | 7.244 | Figure: 7.96, 1.: 7.96, scored: 3.33, Reserved: 3.67, panel: 3.67, opened: 3.67 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | `sealed` | (461.02, 405.95, 470.82, 409.29) | 3.333 | 9.797 | observed: 3.67, complete-year: 3.67, truth: 3.67, until: 3.33, the: 3.33, freeze: 3.33 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | `until` | (471.74, 405.95, 477.84, 409.29) | 3.333 | 6.094 | complete-year: 3.67, truth: 3.67, sealed: 3.33, the: 3.33, freeze: 3.33, exists: 3.33 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | `the` | (478.76, 405.95, 483.38, 409.29) | 3.333 | 4.613 | truth: 3.67, sealed: 3.33, until: 3.33, freeze: 3.33, exists: 3.33, Gate: 3.67 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | `freeze` | (484.3, 405.95, 493.4, 409.29) | 3.333 | 9.100 | sealed: 3.33, until: 3.33, the: 3.33, exists: 3.33, Gate: 3.67, before: 3.67 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | `exists` | (494.33, 405.95, 502.74, 409.29) | 3.333 | 8.414 | until: 3.33, the: 3.33, freeze: 3.33, Gate: 3.67, before: 3.67, rule: 3.67 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | `the` | (272.18, 450.95, 276.79, 454.29) | 3.333 | 4.613 | resolves: 3.67, 1.44: 3.67, points: 3.67, frozen: 3.33, rule,: 3.33, unchanged: 3.33 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | `frozen` | (277.72, 450.95, 286.82, 454.29) | 3.333 | 9.104 | 1.44: 3.67, points: 3.67, the: 3.33, rule,: 3.33, unchanged: 3.33, Mechanism: 3.67 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | `rule,` | (287.75, 450.95, 294.16, 454.29) | 3.333 | 6.414 | points: 3.67, the: 3.33, frozen: 3.33, unchanged: 3.33, Mechanism: 3.67, (H1): 3.67 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | `unchanged` | (295.09, 450.95, 311.56, 454.29) | 3.333 | 16.474 | the: 3.33, frozen: 3.33, rule,: 3.33, Mechanism: 3.67, (H1): 3.67, ·: 3.67 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | `scored` | (379.46, 454.12, 389.46, 457.45) | 3.333 | 9.997 | disjoint: 3.67, Figure: 7.96, 2.: 7.96, once: 3.33, Reserved: 3.67, panel: 3.67 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 12 | `once` | (390.38, 454.12, 397.63, 457.45) | 3.333 | 7.244 | Figure: 7.96, 2.: 7.96, scored: 3.33, Reserved: 3.67, panel: 3.67, opened: 3.67 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `GAGES-II` | (109.2, 271.63, 124.57, 275.13) | 3.500 | 15.366 | protocol: 3.67, requires: 3.67, them): 3.67, basin: 3.50, attributes: 3.50, joined: 3.50 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `basin` | (125.54, 271.63, 133.9, 275.13) | 3.500 | 8.365 | requires: 3.67, them): 3.67, GAGES-II: 3.50, attributes: 3.50, joined: 3.50, for: 3.50 |
| `paper/wrr/wrr_manuscript.pdf` | 10 | `attributes` | (134.88, 271.63, 149.23, 275.13) | 3.500 | 14.351 | them): 3.67, GAGES-II: 3.50, basin: 3.50, joined: 3.50, for: 3.50, 140: 3.50 |
| ... | | 799 more in the JSON | | | | |

The box height is Poppler's only per-word size proxy. A rotated text run is emitted as several partial words whose boxes under-report the printed glyph, so a flagged word must be judged together with its neighbours before the type is re-set. When the attributed figure is a schematic drawn several times wider than the 396 pt text column, the cause is the placement scale, not the figure's own type size.

## 5. Overlapping text (check e)

Rule: pairs of word boxes whose intersection area exceeds 25% of the smaller box, exact duplicates and shadow duplicates excluded. **This is a conservative approximation of visual overlap**: it is derived from Poppler word boxes, which are axis-aligned even for rotated text and which include font ascent/descent, and it cannot see text drawn over graphics.

| file | word boxes | candidate pairs | same baseline (real) | adjacent-line padding | atypical box geometry | duplicates ignored (exact/shadow) |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f0_problem_frame.pdf` | 225 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f1_example.pdf` | 160 | 19 | 0 | 19 | 0 | 0/0 |
| `paper/wrr/figures/f1_system_architecture.pdf` | 295 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f2_experiment_design.pdf` | 407 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f2a_endpoint_ordering.pdf` | 67 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f2b_panel_heterogeneity.pdf` | 108 | 0 | 0 | 0 | 0 | 0/0 |
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
| `paper/wrr/wrr_manuscript.pdf` | 17773 | 87 | 0 | 23 | 64 | 0/0 |
| `paper/wrr/wrr_supporting_information.pdf` | 1291 | 0 | 0 | 0 | 0 | 0/0 |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 17056 | 87 | 0 | 27 | 60 | 0/0 |

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

#### `paper/wrr/wrr_manuscript.pdf` — 87 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 27 | atypical_box_geometry | 80.4 | `amplit` | (393.23, 588.0, 407.18, 605.46) | `0` | (394.14, 586.08, 396.94, 595.9) | 1.92 | 8.85 |
| 16 | adjacent_line_padding | 73.5 | `–16–` | (285.99, 763.59, 304.42, 771.55) | `no` | (292.21, 765.7, 301.93, 773.66) | 2.11 | 7.96 |
| 27 | atypical_box_geometry | 53.7 | `amplit` | (393.23, 588.0, 407.18, 605.46) | `d` | (398.34, 583.46, 401.13, 593.27) | 4.54 | 8.85 |
| 27 | atypical_box_geometry | 51.4 | `amplit` | (393.23, 588.0, 407.18, 605.46) | `ann` | (400.98, 596.37, 409.26, 609.61) | 8.36 | 8.85 |
| 31 | adjacent_line_padding | 50.7 | `certificate` | (218.3, 499.4, 257.77, 514.19) | `oracle` | (232.1, 506.7, 256.18, 521.49) | 7.30 | 12.14 |
| 27 | atypical_box_geometry | 48.7 | `seasonal` | (117.67, 540.39, 146.27, 552.66) | `donor` | (127.04, 534.1, 145.89, 546.37) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `observed` | (124.11, 496.32, 154.18, 508.59) | `donor` | (131.32, 502.61, 150.16, 514.88) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `donor` | (127.04, 534.1, 145.89, 546.37) | `n` | (129.96, 527.8, 134.07, 540.07) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `missing` | (129.23, 552.99, 154.15, 565.26) | `total` | (139.31, 559.29, 154.15, 571.56) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `coverage` | (130.57, 521.5, 160.69, 533.77) | `train` | (133.52, 515.21, 148.62, 527.48) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `coverage` | (130.57, 521.5, 160.69, 533.77) | `visible` | (136.13, 527.8, 156.87, 540.07) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `amplitude` | (148.33, 540.39, 181.12, 552.66) | `n` | (160.7, 546.69, 164.81, 558.96) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `metric` | (150.69, 515.21, 171.58, 527.48) | `resid` | (155.74, 508.91, 171.57, 521.18) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `fraction` | (156.22, 552.99, 181.14, 565.26) | `n` | (160.7, 546.69, 164.81, 558.96) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `fraction` | (156.25, 496.32, 181.17, 508.59) | `overlap` | (156.75, 490.02, 181.12, 502.29) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `donors` | (158.94, 527.8, 181.16, 540.07) | `mean` | (162.76, 521.5, 181.16, 533.77) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `mean` | (162.76, 521.5, 181.16, 533.77) | `sd` | (173.64, 515.21, 181.14, 527.48) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `max` | (167.06, 502.61, 181.19, 514.88) | `sd` | (173.63, 508.91, 181.13, 521.18) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.7 | `missing` | (156.21, 559.29, 181.13, 571.56) | `fraction` | (156.22, 552.99, 181.14, 565.26) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.6 | `fraction` | (156.22, 552.99, 181.14, 565.26) | `runs` | (166.88, 546.69, 181.15, 558.96) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.6 | `missing` | (156.21, 559.29, 181.13, 571.56) | `run` | (170.25, 565.58, 181.14, 577.85) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.6 | `sd` | (173.63, 508.91, 181.13, 521.18) | `sd` | (173.64, 515.21, 181.14, 527.48) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.6 | `donors` | (158.94, 527.8, 181.16, 540.07) | `mean` | (162.78, 534.1, 181.18, 546.37) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.6 | `fraction` | (156.25, 496.32, 181.17, 508.59) | `max` | (167.06, 502.61, 181.19, 514.88) | 6.30 | 8.85 |
| 27 | atypical_box_geometry | 48.6 | `overlap` | (156.75, 490.02, 181.12, 502.29) | `margin` | (158.27, 483.72, 181.17, 495.99) | 6.30 | 8.85 |
| ... | | | 62 more pairs in the JSON | | | | | |

Pair classification: `adjacent_line_padding` x23; `atypical_box_geometry` x64.

#### `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` — 87 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 22 | atypical_box_geometry | 80.4 | `amplit` | (393.23, 447.67, 407.18, 465.13) | `0` | (394.14, 445.75, 396.94, 455.57) | 1.92 | 9.46 |
| 5 | adjacent_line_padding | 73.5 | `–5–` | (288.29, 763.59, 302.11, 771.55) | `no` | (292.21, 765.7, 301.93, 773.66) | 2.11 | 7.96 |
| 22 | atypical_box_geometry | 53.7 | `amplit` | (393.23, 447.67, 407.18, 465.13) | `d` | (398.34, 443.13, 401.13, 452.94) | 4.54 | 9.46 |
| 22 | atypical_box_geometry | 51.4 | `amplit` | (393.23, 447.67, 407.18, 465.13) | `ann` | (400.98, 456.03, 409.26, 469.28) | 8.36 | 9.46 |
| 28 | adjacent_line_padding | 50.7 | `certificate` | (218.3, 499.4, 257.77, 514.19) | `oracle` | (232.1, 506.7, 256.18, 521.49) | 7.30 | 12.14 |
| 22 | atypical_box_geometry | 48.7 | `seasonal` | (117.67, 400.06, 146.27, 412.33) | `donor` | (127.04, 393.76, 145.89, 406.03) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `observed` | (124.11, 355.98, 154.18, 368.25) | `donor` | (131.32, 362.28, 150.16, 374.55) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `donor` | (127.04, 393.76, 145.89, 406.03) | `n` | (129.96, 387.47, 134.07, 399.74) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `missing` | (129.23, 412.66, 154.15, 424.93) | `total` | (139.31, 418.95, 154.15, 431.22) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `coverage` | (130.57, 381.17, 160.69, 393.44) | `train` | (133.52, 374.87, 148.62, 387.14) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `coverage` | (130.57, 381.17, 160.69, 393.44) | `visible` | (136.13, 387.47, 156.87, 399.74) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `amplitude` | (148.33, 400.06, 181.12, 412.33) | `n` | (160.7, 406.36, 164.81, 418.63) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `metric` | (150.69, 374.87, 171.58, 387.14) | `resid` | (155.74, 368.58, 171.57, 380.85) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `fraction` | (156.22, 412.66, 181.14, 424.93) | `n` | (160.7, 406.36, 164.81, 418.63) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `fraction` | (156.25, 355.98, 181.17, 368.25) | `overlap` | (156.75, 349.69, 181.12, 361.96) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `donors` | (158.94, 387.47, 181.16, 399.74) | `mean` | (162.76, 381.17, 181.16, 393.44) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `mean` | (162.76, 381.17, 181.16, 393.44) | `sd` | (173.64, 374.87, 181.14, 387.14) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `max` | (167.06, 362.28, 181.19, 374.55) | `sd` | (173.63, 368.58, 181.13, 380.85) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.7 | `missing` | (156.21, 418.95, 181.13, 431.22) | `fraction` | (156.22, 412.66, 181.14, 424.93) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.6 | `fraction` | (156.22, 412.66, 181.14, 424.93) | `runs` | (166.88, 406.36, 181.15, 418.63) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.6 | `missing` | (156.21, 418.95, 181.13, 431.22) | `run` | (170.25, 425.25, 181.14, 437.52) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.6 | `sd` | (173.63, 368.58, 181.13, 380.85) | `sd` | (173.64, 374.87, 181.14, 387.14) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.6 | `donors` | (158.94, 387.47, 181.16, 399.74) | `mean` | (162.78, 393.76, 181.18, 406.03) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.6 | `fraction` | (156.25, 355.98, 181.17, 368.25) | `max` | (167.06, 362.28, 181.19, 374.55) | 6.30 | 9.46 |
| 22 | atypical_box_geometry | 48.6 | `overlap` | (156.75, 349.69, 181.12, 361.96) | `margin` | (158.27, 343.39, 181.17, 355.66) | 6.30 | 9.46 |
| ... | | | 62 more pairs in the JSON | | | | | |

Pair classification: `adjacent_line_padding` x27; `atypical_box_geometry` x60.

### Labels drawn with no word gap (blind spot of the pairwise rule)

A word box such as `timingtimingtiminglengthlength` is one Poppler word because the individual labels were drawn with no space glyph between them; the pairwise test cannot see it (there is no pair) and on paper the row reads as one continuous string.

| file | page | extracted word | box (x0, y0, x1, y1) | width (pt) | repeated unit | runs recovered | run pitches (pt) |
|---|---|---|---|---|---|---|---|
| `paper/wrr/figures/fig1_mechanism.pdf` | 1 | `timingtimingtiminglengthlength` | (302.91, 173.35, 385.39, 184.68) | 82.48 | `timing` x3 | 6 | 15.51-16.97 |
| `paper/wrr/wrr_manuscript.pdf` | 27 | `timingtimingtiminglengthlength` | (377.96, 483.27, 454.4, 493.77) | 76.45 | `timing` x3 | 2 | - |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 22 | `timingtimingtiminglengthlength` | (377.96, 342.94, 454.4, 353.44) | 76.45 | `timing` x3 | 0 | - |

`paper/wrr/figures/fig1_mechanism.pdf` page 1 runs inside the merged box:

| run text | x (pt) | baseline y from top (pt) | font resource | size (pt) | pitch from previous (pt) |
|---|---|---|---|---|---|
| `1.0` | 285.943 | 176.983 | F1 | 6.40 | - |
| `timing` | 302.912 | 182.381 | F2 | 5.60 | 16.969 |
| `timing` | 318.441 | 182.381 | F2 | 5.60 | 15.529 |
| `timing` | 333.969 | 182.381 | F2 | 5.60 | 15.528 |
| `length` | 349.483 | 182.381 | F2 | 5.60 | 15.514 |
| `length` | 365.011 | 182.381 | F2 | 5.60 | 15.528 |

`paper/wrr/wrr_manuscript.pdf` page 27 runs inside the merged box:

| run text | x (pt) | baseline y from top (pt) | font resource | size (pt) | pitch from previous (pt) |
|---|---|---|---|---|---|
| `0.825` | 356.602 | 494.432 | F1 | 7.00 | - |
| `0.850` | 356.602 | 478.808 | F1 | 7.00 | 0.000 |

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
| `f0_problem_frame` | `figures/v17/f0_problem_frame.pdf` | no |
| `f1_example` | `figures/wrr/f1_example.pdf` | yes |
| `f1_system_architecture` | `figures/v17/f1_system_architecture.pdf` | no |
| `f2_experiment_design` | `figures/v17/f2_experiment_design.pdf` | no |
| `f2a_endpoint_ordering` | `figures/wrr/f2a_endpoint_ordering.pdf` | yes |
| `f2b_panel_heterogeneity` | `figures/wrr/f2b_panel_heterogeneity.pdf` | no |
| `f3_evidence_chain` | `figures/v17/f3_evidence_chain.pdf` | no |
| `f4_deployment_workflow` | `figures/v17/f4_deployment_workflow.pdf` | no |
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
| `paper/wrr/wrr_manuscript.pdf` | 27 | 2 | 317x427 | index | 324, 324 | ok |
| `paper/wrr/wrr_manuscript.pdf` | 27 | 3 | 16x308 | index | 324, 324 | ok |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 20 | 0 | 423x437 | index | 260, 260 | BELOW 300 dpi |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 20 | 1 | 20x406 | index | 260, 260 | BELOW 300 dpi |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 22 | 2 | 317x427 | index | 324, 324 | ok |
| `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | 22 | 3 | 16x308 | index | 324, 324 | ok |

## 8. Printed size and effective text size (derived)

Method: the scale at which each figure is placed in the built PDFs is measured by matching the figure's distinctive words against the words of the built pages (all pairs of unambiguous matches give a distance ratio; the largest tight cluster is the estimate). `scale x figure width` is the printed width, and raw text heights times the scale give the size the reader sees on paper. These values are derived, never hard failures.

| figure | width (pt) | measured scale | printed width (pt) | printed width (in) | raw min (pt) | raw p05 (pt) | effective min (pt) | effective p05 (pt) | confidence |
|---|---|---|---|---|---|---|---|---|---|
| `f0_problem_frame` | 726.00 | 0.5455 | 396.00 | 5.500 | 7.88 | 8.62 | 4.30 | 4.70 | measured |
| `f1_example` | 378.53 | 1.0462 | 396.01 | 5.500 | 6.38 | 11.35 | 6.68 | 11.87 | measured |
| `f1_system_architecture` | 872.25 | 0.4540 | 396.00 | 5.500 | 7.50 | 7.88 | 3.41 | 3.58 | measured |
| `f2_experiment_design` | 891.00 | 0.4445 | 396.01 | 5.500 | 7.50 | 7.88 | 3.33 | 3.50 | measured |
| `f2a_endpoint_ordering` | 391.11 | 1.0125 | 396.01 | 5.500 | 6.99 | 6.99 | 7.08 | 7.08 | measured |
| `f2b_panel_heterogeneity` | 380.62 | 1.0405 | 396.01 | 5.500 | 6.99 | 6.99 | 7.27 | 7.27 | measured |
| `f3_evidence_chain` | 876.00 | 0.4520 | 395.99 | 5.500 | 7.88 | 8.25 | 3.56 | 3.73 | measured |
| `f4_deployment_workflow` | 876.00 | 0.4520 | 395.99 | 5.500 | 7.88 | 7.88 | 3.56 | 3.56 | measured |
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

Implied printed width across the 18 figures with a measured scale: median 396.01 pt (5.500 in), range 395.99-396.03 pt. Corroboration: the AGU class file sets `\textwidth 5.5in` = 396 pt (`paper/wrr/template/agujournal2025.cls:958`), consistent with a full-width placement.

AGU/WRR ask for figure text that stays legible in print; a text height below 4.5 pt at printed size is the practical red line used here.

## 9. Prioritised fix list

| priority | file | finding |
|---|---|---|
| P0 | `paper/wrr/figures/f1_example.pdf` | TEXT_OUTSIDE_PAGE page 1: word 'water' box extends 2.52 pt outside the page ({'left': 2.523}) x19 |
| P0 | `paper/wrr/wrr_manuscript.pdf` | TEXT_OUTSIDE_PAGE page 16: word 'station-year' box extends 1.59 pt outside the page ({'bottom': 1.586}) x13 |
| P0 | `paper/wrr/wrr_manuscript.pdf` | TEXT_OUTSIDE_PAGE page 33: word 'baseline/' box extends 1.99 pt outside the page ({'right': 1.986}) |
| P0 | `paper/wrr/wrr_manuscript.pdf` | TEXT_OUTSIDE_PAGE page 48: word 'informati' box extends 2.35 pt outside the page ({'right': 2.348}) |
| P0 | `paper/wrr/wrr_manuscript.pdf` | TEXT_OUTSIDE_PAGE page 7: word 'sensitivity/' box extends 1.02 pt outside the page ({'right': 1.019}) |
| P0 | `paper/wrr/wrr_manuscript.pdf` | TEXT_OUTSIDE_PAGE page 8: word 'stations.cs' box extends 1.49 pt outside the page ({'right': 1.493}) |
| P0 | `paper/wrr/wrr_manuscript.pdf` | TEXT_OUTSIDE_PAGE page 9: word 'seal' box extends 2.41 pt outside the page ({'right': 2.407}) |
| P0 | `paper/wrr/wrr_supporting_information.pdf` | TEXT_OUTSIDE_PAGE page 3: word 'SUMMARY.json' box extends 3.21 pt outside the page ({'right': 3.208}) x2 |
| P0 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | TEXT_OUTSIDE_PAGE page 10: word 'seal' box extends 2.41 pt outside the page ({'right': 2.407}) |
| P0 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | TEXT_OUTSIDE_PAGE page 11: word 'transport/verdict.json' box extends 4.93 pt outside the page ({'right': 4.926}) |
| P0 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | TEXT_OUTSIDE_PAGE page 30: word 'baseline/' box extends 1.99 pt outside the page ({'right': 1.986}) |
| P0 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | TEXT_OUTSIDE_PAGE page 46: word 'informati' box extends 2.35 pt outside the page ({'right': 2.348}) |
| P0 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | TEXT_OUTSIDE_PAGE page 5: word 'station-year' box extends 1.59 pt outside the page ({'bottom': 1.586}) x13 |
| P0 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | TEXT_OUTSIDE_PAGE page 9: word 'sensitivity/' box extends 1.02 pt outside the page ({'right': 1.019}) x2 |
| P1 | `paper/wrr/figures/f1_system_architecture.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 7.88 pt x placement scale 0.4540 = 3.58 pt on paper (< 4.5 pt); the figure is drawn 872 pt wide and printed 396 pt wide |
| P1 | `paper/wrr/figures/f2_experiment_design.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 7.88 pt x placement scale 0.4445 = 3.50 pt on paper (< 4.5 pt); the figure is drawn 891 pt wide and printed 396 pt wide |
| P1 | `paper/wrr/figures/f3_evidence_chain.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 8.25 pt x placement scale 0.4520 = 3.73 pt on paper (< 4.5 pt); the figure is drawn 876 pt wide and printed 396 pt wide |
| P1 | `paper/wrr/figures/f4_deployment_workflow.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 7.88 pt x placement scale 0.4520 = 3.56 pt on paper (< 4.5 pt); the figure is drawn 876 pt wide and printed 396 pt wide |
| P1 | `paper/wrr/figures/fig1_mechanism.pdf` | MERGED_LABEL_RUN_SUSPECT: word 'timingtimingtiminglengthlength' repeats 'timing' x3 inside one box 82.5 pt wide; 6 drawing run(s) recovered from the content stream, pitch 15.514-16.969 pt |
| P1 | `paper/wrr/figures/fig1_mechanism.pdf` | TEXT_HEIGHT_BELOW_MINIMUM page 1: word 'a' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/figures/figv3_support_law.pdf` | TEXT_HEIGHT_BELOW_MINIMUM page 1: word 'a' box is 4.29 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_manuscript.pdf` | INK_FLUSH_TO_PAGE_EDGE: rendered ink reaches within 1.0 pt of the page edge (margins {'left': 97.2, 'top': 29.88, 'right': 0.36, 'bottom': 22.32}): glyphs are clipped or flush |
| P1 | `paper/wrr/wrr_manuscript.pdf` | INK_FLUSH_TO_PAGE_EDGE: rendered ink reaches within 1.0 pt of the page edge (margins {'left': 97.2, 'top': 29.88, 'right': 0.36, 'bottom': 22.32}): glyphs are clipped or flush |
| P1 | `paper/wrr/wrr_manuscript.pdf` | INK_FLUSH_TO_PAGE_EDGE: rendered ink reaches within 1.0 pt of the page edge (margins {'left': 97.2, 'top': 29.88, 'right': 0.36, 'bottom': 22.32}): glyphs are clipped or flush |
| P1 | `paper/wrr/wrr_manuscript.pdf` | INK_FLUSH_TO_PAGE_EDGE: rendered ink reaches within 1.0 pt of the page edge (margins {'left': 97.2, 'top': 29.88, 'right': 0.36, 'bottom': 22.32}): glyphs are clipped or flush |
| P1 | `paper/wrr/wrr_manuscript.pdf` | MERGED_LABEL_RUN_SUSPECT: word 'timingtimingtiminglengthlength' repeats 'timing' x3 inside one box 76.4 pt wide; 2 drawing run(s) recovered from the content stream |
| P1 | `paper/wrr/wrr_manuscript.pdf` | TEXT_HEIGHT_BELOW_MINIMUM page 10: word 'Nine' box is 3.83 pt high (< 4.5 pt) x408 |
| P1 | `paper/wrr/wrr_manuscript.pdf` | TEXT_HEIGHT_BELOW_MINIMUM page 20: word 'a' box is 4.30 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_manuscript.pdf` | TEXT_HEIGHT_BELOW_MINIMUM page 27: word 'a' box is 3.98 pt high (< 4.5 pt) |
| P1 | `paper/wrr/wrr_manuscript.pdf` | TEXT_HEIGHT_BELOW_MINIMUM page 5: word 't' box is 4.42 pt high (< 4.5 pt) |
| P1 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | INK_FLUSH_TO_PAGE_EDGE: rendered ink reaches within 1.0 pt of the page edge (margins {'left': 97.2, 'top': 29.88, 'right': 0.36, 'bottom': 22.32}): glyphs are clipped or flush |
| P1 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | INK_FLUSH_TO_PAGE_EDGE: rendered ink reaches within 1.0 pt of the page edge (margins {'left': 97.2, 'top': 29.88, 'right': 0.36, 'bottom': 22.32}): glyphs are clipped or flush |
| P1 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | INK_FLUSH_TO_PAGE_EDGE: rendered ink reaches within 1.0 pt of the page edge (margins {'left': 97.2, 'top': 29.88, 'right': 0.36, 'bottom': 22.32}): glyphs are clipped or flush |
| P1 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | INK_FLUSH_TO_PAGE_EDGE: rendered ink reaches within 1.0 pt of the page edge (margins {'left': 97.2, 'top': 29.88, 'right': 0.36, 'bottom': 22.32}): glyphs are clipped or flush |
| P1 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | INK_FLUSH_TO_PAGE_EDGE: rendered ink reaches within 1.0 pt of the page edge (margins {'left': 97.2, 'top': 29.88, 'right': 0.36, 'bottom': 22.68}): glyphs are clipped or flush |
| P1 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | INK_FLUSH_TO_PAGE_EDGE: rendered ink reaches within 1.0 pt of the page edge (margins {'left': 97.2, 'top': 29.88, 'right': 119.88, 'bottom': 0.36}): glyphs are clipped or flush |
| P1 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | MERGED_LABEL_RUN_SUSPECT: word 'timingtimingtiminglengthlength' repeats 'timing' x3 inside one box 76.4 pt wide; 0 drawing run(s) recovered from the content stream |
| P1 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | TEXT_HEIGHT_BELOW_MINIMUM page 12: word 'Nine' box is 3.83 pt high (< 4.5 pt) x408 |
| P1 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | TEXT_HEIGHT_BELOW_MINIMUM page 20: word 'a' box is 4.30 pt high (< 4.5 pt) |
| P1 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | TEXT_HEIGHT_BELOW_MINIMUM page 22: word 'a' box is 3.98 pt high (< 4.5 pt) |
| P1 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | TEXT_HEIGHT_BELOW_MINIMUM page 8: word 't' box is 4.42 pt high (< 4.5 pt) |
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
| P2 | `paper/wrr/wrr_manuscript.pdf` | OVERLAPPING_WORD_BOXES: 87 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/wrr_manuscript.pdf` | RASTER_BELOW_300_DPI: raster image 0 on page 20 (423x437 px, index) has an effective resolution of 260x260 ppi (< 300) |
| P2 | `paper/wrr/wrr_manuscript.pdf` | RASTER_BELOW_300_DPI: raster image 1 on page 20 (20x406 px, index) has an effective resolution of 260x260 ppi (< 300) |
| P2 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | OVERLAPPING_WORD_BOXES: 87 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | RASTER_BELOW_300_DPI: raster image 0 on page 20 (423x437 px, index) has an effective resolution of 260x260 ppi (< 300) |
| P2 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | RASTER_BELOW_300_DPI: raster image 1 on page 20 (20x406 px, index) has an effective resolution of 260x260 ppi (< 300) |
| P3 | `(environment)` | TOOL_MISSING: drawio is not installed in this environment |
| P3 | `paper/wrr/figures/f1_example.pdf` | TEXT_BOX_PADDING_ONLY: word boxes cross the page edge but the rendered ink stays 1.08 pt inside: Poppler font-descent padding, no clipped glyph |
| P3 | `paper/wrr/figures/f1_system_architecture.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: 5th-percentile word height 7.88 pt x measured placement scale 0.4540 = 3.58 pt on paper (< 4.5 pt) |
| P3 | `paper/wrr/figures/f2_experiment_design.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: 5th-percentile word height 7.88 pt x measured placement scale 0.4445 = 3.50 pt on paper (< 4.5 pt) |
| P3 | `paper/wrr/figures/f3_evidence_chain.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: 5th-percentile word height 8.25 pt x measured placement scale 0.4520 = 3.73 pt on paper (< 4.5 pt) |
| P3 | `paper/wrr/figures/f4_deployment_workflow.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: 5th-percentile word height 7.88 pt x measured placement scale 0.4520 = 3.56 pt on paper (< 4.5 pt) |
| P3 | `paper/wrr/wrr_manuscript.pdf` | TEXT_BOX_PADDING_ONLY: word boxes cross the page edge but the rendered ink stays 29.88 pt inside: Poppler font-descent padding, no clipped glyph |
| P3 | `scratch/figure_qa/recovered/wrr_manuscript_HEAD.pdf` | FONT_UNNAMED: font has no name (Type 3, embedded=True); producer-embedded Type 3 subsets are unnamed by design |

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


# WRR figure and PDF quality assurance

Generated 2026-10-20T13:16:16Z by `python3 scripts/266_wrr_figure_qa.py`.

* JSON: `results/wrr_submission_ready/figure_qa.json`
* Markdown: `results/wrr_submission_ready/figure_qa_report.md`
* tools: `pdffonts` pdffonts version 22.02.0, `pdfinfo` pdfinfo version 22.02.0, `pdftotext` pdftotext version 22.02.0, `pdfimages` pdfimages version 22.02.0, `pdftoppm` pdftoppm version 22.02.0, `rsvg-convert` rsvg-convert version 2.52.5, `drawio` MISSING

## Verdict

**PASS (with warnings)** — 0 hard failure(s) in 0 file/check/page group(s), 21 warning(s).

Exit status is 0 for the strict run (`--report-only` always exits 0 so the regression test is not turned red by a real finding).

| check | hard failures | warnings |
|---|---|---|
| FONT_NOT_EMBEDDED — font not embedded (check a) | 0 | 0 |
| FIGURE_NOT_SINGLE_PAGE — figure page count != 1 (check b) | 0 | 0 |
| TEXT_OUTSIDE_PAGE — text > 1 pt outside the page and ink clipped or unverified (check c) | 0 | 0 |
| TEXT_HEIGHT_BELOW_MINIMUM — line-estimated type size < 4.5 pt (check d) | 0 | 0 |
| OVERLAPPING_TEXT_SAME_BASELINE — overlapping boxes, same baseline (check e) | 0 | 1 |
| OVERLAPPING_WORD_BOXES — overlapping boxes, other geometry (check e) | 0 | 2 |
| MERGED_LABEL_RUN_SUSPECT — labels drawn with no word gap (check e) | 0 | 0 |
| FOOTER_TEXT_COLLISION — page number overprinted by body text (check e) | 0 | 0 |
| SCHEMATIC_WITHOUT_DRAWIO_SOURCE — schematic with no draw.io source (check f) | 0 | 0 |
| PROVENANCE_UNKNOWN — neither draw.io nor python source (check f) | 0 | 0 |
| RASTER_BELOW_300_DPI — raster below 300 dpi effective (check g) | 0 | 0 |
| EFFECTIVE_PRINT_TEXT_TOO_SMALL — derived: printed text below 4.5 pt | 0 | 0 |
| INK_CLIPPED_AT_PAGE_EDGE — derived: rendered ink clipped/flush at the page edge | 0 | 0 |
| TEXT_BOX_PADDING_ONLY — derived: box crosses the edge, ink does not | 0 | 0 |
| INK_CHECK_UNAVAILABLE — derived: the flagged page could not be rendered | 0 | 0 |
| SMALL_RELATIVE_WORD_BOXES — word far smaller than its own line (check d) | 0 | 11 |
| FONT_UNNAMED — embedded font with no BaseFont name | 0 | 0 |
| DEGENERATE_WORD_BOXES — word boxes with non-positive height | 0 | 0 |
| FIGURE_NOT_REFERENCED — figure PDF not referenced by any .tex | 0 | 6 |
| PAGE_SIZE_VARIES — page sizes differ within one PDF | 0 | 0 |
| BBOX_PAGE_COUNT_MISMATCH — pdftotext -bbox page count differs from pdfinfo | 0 | 0 |
| BUILT_PDF_MISSING — a built PDF was not found | 0 | 0 |
| TOOL_MISSING — a required tool is not installed | 0 | 1 |

Thresholds: text outside page > 1.0 pt, line-estimated type size < 4.5 pt, overlap > 25% of the smaller box, raster < 300 dpi.

### Real defects versus box-model artifacts

No hard failure was recorded: every word box that crosses a page edge was shown by the render to keep its ink inside the page, and no line of type is below the size threshold.

No warning-level finding is classified as a real defect.

## Per-figure master table

| figure | pages | page size (in) | fonts | non-embedded | text outside page | min word height (pt) | overlap pairs | of which same baseline | min raster ppi | source | effective print p05 (pt) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `f1_support` | 1 | 5.58x4.49 | 1 | 0 | 0 | 6.29 | 2 | 0 | - | python | - | warn |
| `f2_system_design` | 1 | 5.29x2.58 | 2 | 0 | 0 | 7.18 | 0 | 0 | - | drawio+python | 2.32 | warn |
| `f3_reconstructor` | 1 | 5.38x4.07 | 1 | 0 | 0 | 5.38 | 0 | 0 | - | python | - | warn |
| `f4_mechanism` | 1 | 6.21x4.69 | 1 | 0 | 0 | 6.03 | 0 | 0 | - | python | 23.05 | warn |
| `f5_decision` | 1 | 6.05x4.89 | 1 | 0 | 0 | 5.71 | 0 | 0 | - | python | 4.44 | warn |
| `r3_f1_recovery` | 1 | 7.22x3.37 | 1 | 0 | 0 | 9.32 | 0 | 0 | - | python | 7.10 | ok |
| `r3_f2_channels` | 1 | 7.22x3.37 | 1 | 0 | 0 | 9.32 | 0 | 0 | 400 | python | 7.10 | warn |
| `r3_f3_information` | 1 | 7.70x4.32 | 1 | 0 | 0 | 9.32 | 0 | 0 | - | python | 6.66 | ok |
| `r3_f4_transfer` | 1 | 7.22x3.91 | 1 | 0 | 0 | 9.32 | 0 | 0 | - | python | 7.10 | warn |
| `r3_f5_utility` | 1 | 7.21x3.74 | 1 | 0 | 0 | 9.32 | 0 | 0 | - | python | 7.11 | warn |
| `r3_s1_learning` | 1 | 7.22x3.52 | 1 | 0 | 0 | 9.32 | 0 | 0 | - | python | 7.10 | warn |
| `r3_s2_cofailure` | 1 | 7.22x3.52 | 1 | 0 | 0 | 9.32 | 0 | 0 | - | python | 7.10 | warn |
| `s1_study_design` | 1 | 5.29x1.76 | 2 | 0 | 0 | 7.16 | 0 | 0 | - | drawio+python | - | warn |

"effective print p05" is the 5th-percentile word-box height multiplied by the measured placement scale in the built PDFs (derived, see the print-size section).

## Built documents

| document | pages | page size (pt) | page size (in) | fonts | non-embedded | text outside page | min word height (pt) | overlap pairs | same baseline | min raster ppi |
|---|---|---|---|---|---|---|---|---|---|---|
| `paper/wrr/wrr_manuscript.pdf` | 21 | 612.00 x 792.00 | 8.50 x 11.00 | 25 | 0 | 0 | 4.42 | 8 | 2 | 525 |
| `paper/wrr/wrr_supporting_information.pdf` | 41 | 612.00 x 792.00 | 8.50 x 11.00 | 14 | 0 | 0 | 5.31 | 0 | 0 | - |

## 1. Fonts (check a)

| file | fonts | types | non-embedded | names of non-embedded | unnamed/Type 3 | all embedded |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f1_support.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/f2_system_design.pdf` | 2 | CID TrueType x2 | 0 | none | none | yes |
| `paper/wrr/figures/f3_reconstructor.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/f4_mechanism.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/f5_decision.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/r3_f1_recovery.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/r3_f2_channels.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/r3_f3_information.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/r3_f4_transfer.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/r3_f5_utility.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/r3_s1_learning.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/r3_s2_cofailure.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/s1_study_design.pdf` | 2 | CID TrueType x2 | 0 | none | none | yes |
| `paper/wrr/wrr_manuscript.pdf` | 25 | CID TrueType x5, Type 1 x20 | 0 | none | none | yes |
| `paper/wrr/wrr_supporting_information.pdf` | 14 | CID TrueType x2, Type 1 x12 | 0 | none | none | yes |

`[none]` is the name Poppler reports for a producer-embedded Type 3 subset with no BaseFont entry (matplotlib's default pdf.fonttype=3); the font is embedded even though it is unnamed.

## 2. Page geometry (check b)

| file | pages | page size (pt) | page size (in) | distinct page sizes | single page | text outside page | max overflow (pt) |
|---|---|---|---|---|---|---|---|
| `paper/wrr/figures/f1_support.pdf` | 1 | 401.54 x 323.53 | 5.58 x 4.49 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f2_system_design.pdf` | 1 | 381.12 x 186.00 | 5.29 x 2.58 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f3_reconstructor.pdf` | 1 | 387.49 x 292.94 | 5.38 x 4.07 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f4_mechanism.pdf` | 1 | 446.87 x 337.92 | 6.21 x 4.69 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f5_decision.pdf` | 1 | 435.52 x 351.89 | 6.05 x 4.89 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/r3_f1_recovery.pdf` | 1 | 519.65 x 242.40 | 7.22 x 3.37 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/r3_f2_channels.pdf` | 1 | 519.60 x 242.40 | 7.22 x 3.37 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/r3_f3_information.pdf` | 1 | 554.32 x 310.80 | 7.70 x 4.32 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/r3_f4_transfer.pdf` | 1 | 519.60 x 281.58 | 7.22 x 3.91 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/r3_f5_utility.pdf` | 1 | 519.44 x 269.23 | 7.21 x 3.74 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/r3_s1_learning.pdf` | 1 | 519.60 x 253.20 | 7.22 x 3.52 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/r3_s2_cofailure.pdf` | 1 | 519.60 x 253.20 | 7.22 x 3.52 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/s1_study_design.pdf` | 1 | 381.12 x 126.96 | 5.29 x 1.76 | 1 | yes | 0 | 0.00 |
| `paper/wrr/wrr_manuscript.pdf` | 21 | 612.00 x 792.00 | 8.50 x 11.00 | 1 | no | 0 | 0.00 |
| `paper/wrr/wrr_supporting_information.pdf` | 41 | 612.00 x 792.00 | 8.50 x 11.00 | 1 | no | 0 | 0.00 |

## 3. Text outside the page box (check c)

No word box extends more than 1.0 pt outside its page in any target PDF.

## 4. Minimum text height (check d)

| file | words measured | min box (pt) | 5th pct (pt) | median (pt) | raw boxes < 4.5 pt (literal rule) | lines below threshold (gate) | smaller than their line | degenerate boxes |
|---|---|---|---|---|---|---|---|---|
| `paper/wrr/figures/f1_support.pdf` | 158 | 6.29 | 6.29 | 7.69 | 0 | 0 | 40 | 0 |
| `paper/wrr/figures/f2_system_design.pdf` | 91 | 7.18 | 7.18 | 7.18 | 0 | 0 | 0 | 0 |
| `paper/wrr/figures/f3_reconstructor.pdf` | 90 | 5.38 | 6.06 | 7.69 | 0 | 0 | 23 | 0 |
| `paper/wrr/figures/f4_mechanism.pdf` | 146 | 6.03 | 6.06 | 7.22 | 0 | 0 | 25 | 0 |
| `paper/wrr/figures/f5_decision.pdf` | 206 | 5.71 | 5.71 | 7.69 | 0 | 0 | 30 | 0 |
| `paper/wrr/figures/r3_f1_recovery.pdf` | 62 | 9.32 | 9.32 | 10.19 | 0 | 0 | 0 | 0 |
| `paper/wrr/figures/r3_f2_channels.pdf` | 60 | 9.32 | 9.32 | 9.90 | 0 | 0 | 12 | 0 |
| `paper/wrr/figures/r3_f3_information.pdf` | 65 | 9.32 | 9.32 | 9.90 | 0 | 0 | 0 | 0 |
| `paper/wrr/figures/r3_f4_transfer.pdf` | 68 | 9.32 | 9.32 | 10.48 | 0 | 0 | 8 | 0 |
| `paper/wrr/figures/r3_f5_utility.pdf` | 71 | 9.32 | 9.32 | 9.90 | 0 | 0 | 11 | 0 |
| `paper/wrr/figures/r3_s1_learning.pdf` | 41 | 9.32 | 9.32 | 9.32 | 0 | 0 | 2 | 0 |
| `paper/wrr/figures/r3_s2_cofailure.pdf` | 49 | 9.32 | 9.32 | 10.48 | 0 | 0 | 9 | 0 |
| `paper/wrr/figures/s1_study_design.pdf` | 62 | 7.16 | 7.16 | 7.16 | 0 | 0 | 0 | 0 |
| `paper/wrr/wrr_manuscript.pdf` | 5889 | 4.42 | 7.49 | 8.85 | 1 | 0 | 31 | 0 |
| `paper/wrr/wrr_supporting_information.pdf` | 9083 | 5.31 | 7.08 | 7.08 | 0 | 0 | 11 | 0 |

No word box is below 4.5 pt in any target PDF.

## 5. Overlapping text (check e)

Rule: pairs of word boxes whose intersection area exceeds 25% of the smaller box, exact duplicates and shadow duplicates excluded. **This is a conservative approximation of visual overlap**: it is derived from Poppler word boxes, which are axis-aligned even for rotated text and which include font ascent/descent, and it cannot see text drawn over graphics.

| file | word boxes | candidate pairs | same baseline (real) | adjacent-line padding | atypical box geometry | duplicates ignored (exact/shadow) |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f1_support.pdf` | 158 | 2 | 0 | 0 | 2 | 0/0 |
| `paper/wrr/figures/f2_system_design.pdf` | 91 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f3_reconstructor.pdf` | 90 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f4_mechanism.pdf` | 146 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f5_decision.pdf` | 206 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/r3_f1_recovery.pdf` | 62 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/r3_f2_channels.pdf` | 60 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/r3_f3_information.pdf` | 65 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/r3_f4_transfer.pdf` | 68 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/r3_f5_utility.pdf` | 71 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/r3_s1_learning.pdf` | 41 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/r3_s2_cofailure.pdf` | 49 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/s1_study_design.pdf` | 62 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/wrr_manuscript.pdf` | 5889 | 8 | 2 | 6 | 0 | 0/0 |
| `paper/wrr/wrr_supporting_information.pdf` | 9083 | 0 | 0 | 0 | 0 | 0/0 |

### Flagged pairs

#### `paper/wrr/figures/f1_support.pdf` — 2 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 1 | atypical_box_geometry | 36.4 | `plitude` | (92.1, 290.05, 114.43, 303.78) | `ann` | (103.87, 299.63, 115.69, 309.84) | 9.58 | 7.69 |
| 1 | atypical_box_geometry | 32.7 | `30-day` | (62.65, 289.96, 84.06, 303.46) | `al` | (74.66, 300.55, 80.41, 309.45) | 10.58 | 7.69 |

Pair classification: `atypical_box_geometry` x2.

#### `paper/wrr/wrr_manuscript.pdf` — 8 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 7 | same_baseline_horizontal | 100.0 | `(e` | (235.54, 519.42, 245.36, 528.27) | `y` | (239.41, 519.42, 244.3, 528.27) | 0.00 | 8.85 |
| 7 | same_baseline_horizontal | 100.0 | `(e` | (332.11, 542.34, 341.92, 551.18) | `y` | (335.98, 542.34, 340.87, 551.18) | 0.00 | 8.85 |
| 7 | adjacent_line_padding | 65.5 | `S` | (308.94, 578.15, 313.84, 584.34) | `b` | (309.97, 580.88, 314.48, 585.41) | 2.74 | 8.85 |
| 7 | adjacent_line_padding | 64.6 | `S` | (278.37, 492.61, 284.48, 501.46) | `b` | (279.77, 496.61, 285.31, 502.99) | 4.00 | 8.85 |
| 7 | adjacent_line_padding | 29.9 | `(e` | (332.11, 542.34, 341.92, 551.18) | `t` | (340.87, 545.91, 343.88, 552.1) | 3.57 | 8.85 |
| 7 | adjacent_line_padding | 29.6 | `y` | (157.67, 492.61, 162.55, 501.46) | `e` | (158.07, 499.13, 163.61, 505.51) | 6.52 | 8.85 |
| 7 | adjacent_line_padding | 29.6 | `y` | (303.7, 572.7, 308.59, 581.55) | `e` | (304.11, 579.22, 309.64, 585.59) | 6.52 | 8.85 |
| 7 | adjacent_line_padding | 29.6 | `y` | (326.89, 572.7, 331.78, 581.55) | `e` | (327.3, 579.22, 332.83, 585.59) | 6.52 | 8.85 |

Pair classification: `adjacent_line_padding` x6; `same_baseline_horizontal` x2.

### Page number printed over body text

No body word box bites into a running page-number band, so no page number is overprinted.

### Labels drawn with no word gap (blind spot of the pairwise rule)

No word box repeats a substring, so no row of labels was found drawn edge to edge.

## 6. Source provenance (check f)

| figure | draw.io source at figures/v17/drawio | schematic | python generator(s) under scripts/ | classification | verdict |
|---|---|---|---|---|---|
| `f1_support` | NO | no | `scripts/335_wrr_figures_v2.py` | python | ok |
| `f2_system_design` | yes | yes — system design and admission workflow (drawio, 2026-10-20) | `scripts/335_wrr_figures_v2.py`, `scripts/337_wrr_drawio_figures.py` | drawio+python | ok |
| `f3_reconstructor` | NO | no | `scripts/335_wrr_figures_v2.py` | python | ok |
| `f4_mechanism` | NO | no | `scripts/335_wrr_figures_v2.py`, `scripts/345_wrr_figures_r2.py` | python | ok |
| `f5_decision` | NO | no | `scripts/335_wrr_figures_v2.py`, `scripts/345_wrr_figures_r2.py` | python | ok |
| `r3_f1_recovery` | NO | no | `scripts/368_wrr_revision_figures.py`, `scripts/370_wrr_revision_completion.py` | python | ok |
| `r3_f2_channels` | NO | no | `scripts/368_wrr_revision_figures.py`, `scripts/370_wrr_revision_completion.py` | python | ok |
| `r3_f3_information` | NO | no | `scripts/368_wrr_revision_figures.py`, `scripts/370_wrr_revision_completion.py` | python | ok |
| `r3_f4_transfer` | NO | no | `scripts/368_wrr_revision_figures.py`, `scripts/370_wrr_revision_completion.py` | python | ok |
| `r3_f5_utility` | NO | no | `scripts/368_wrr_revision_figures.py`, `scripts/370_wrr_revision_completion.py` | python | ok |
| `r3_s1_learning` | NO | no | `scripts/368_wrr_revision_figures.py`, `scripts/370_wrr_revision_completion.py` | python | ok |
| `r3_s2_cofailure` | NO | no | `scripts/368_wrr_revision_figures.py`, `scripts/370_wrr_revision_completion.py` | python | ok |
| `s1_study_design` | yes | yes — study design and evidence chain (drawio, 2026-10-20) | `scripts/335_wrr_figures_v2.py`, `scripts/337_wrr_drawio_figures.py` | drawio+python | ok |

The schematic list is explicit (see `SCHEMATIC_FIGURES` in the script, taken from `figures/v17/drawio/README.md`): a new architecture or system-design figure must be added there, otherwise a missing draw.io source cannot be detected.

| figure | figure built elsewhere in `figures/` | identical to the paper copy |
|---|---|---|
| `f1_support` | `figures/wrr/f1_support.pdf` | no |
| `f2_system_design` | `figures/wrr/f2_system_design.pdf` | no |
| `f3_reconstructor` | `figures/wrr/f3_reconstructor.pdf` | no |
| `f4_mechanism` | `figures/wrr/f4_mechanism.pdf` | yes |
| `f5_decision` | `figures/wrr/f5_decision.pdf` | no |
| `r3_f1_recovery` | `figures/wrr/r3_f1_recovery.pdf` | yes |
| `r3_f2_channels` | `figures/wrr/r3_f2_channels.pdf` | yes |
| `r3_f3_information` | `figures/wrr/r3_f3_information.pdf` | yes |
| `r3_f4_transfer` | `figures/wrr/r3_f4_transfer.pdf` | yes |
| `r3_f5_utility` | `figures/wrr/r3_f5_utility.pdf` | yes |
| `r3_s1_learning` | `figures/wrr/r3_s1_learning.pdf` | yes |
| `r3_s2_cofailure` | `figures/wrr/r3_s2_cofailure.pdf` | yes |
| `s1_study_design` | `figures/wrr/s1_study_design.pdf` | no |

## 7. Raster image resolution (check g)

| file | page | image | pixels | colour | effective ppi (x, y) | flag |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/r3_f2_channels.pdf` | 1 | 0 | 1187x1042 | rgb | 400, 400 | ok |
| `paper/wrr/figures/r3_f2_channels.pdf` | 1 | 1 | 1187x1042 | gray | 400, 400 | ok |
| `paper/wrr/wrr_manuscript.pdf` | 12 | 0 | 1187x1042 | rgb | 525, 525 | ok |
| `paper/wrr/wrr_manuscript.pdf` | 12 | 1 | 1187x1042 | gray | 525, 525 | ok |

## 8. Printed size and effective text size (derived)

Method: the scale at which each figure is placed in the built PDFs is measured by matching the figure's distinctive words against the words of the built pages (all pairs of unambiguous matches give a distance ratio; the largest tight cluster is the estimate). `scale x figure width` is the printed width, and raw text heights times the scale give the size the reader sees on paper. These values are derived, never hard failures.

| figure | width (pt) | measured scale | printed width (pt) | printed width (in) | raw min (pt) | raw p05 (pt) | effective min (pt) | effective p05 (pt) | confidence |
|---|---|---|---|---|---|---|---|---|---|
| `f1_support` | 401.54 | - | - | - | 6.29 | 6.29 | - | - | unavailable |
| `f2_system_design` | 381.12 | 0.3224 | 122.89 | 1.707 | 7.18 | 7.18 | 2.32 | 2.32 | low |
| `f3_reconstructor` | 387.49 | - | - | - | 5.38 | 6.06 | - | - | unavailable |
| `f4_mechanism` | 446.87 | 3.8046 | 1700.13 | 23.613 | 6.03 | 6.06 | 22.96 | 23.05 | low |
| `f5_decision` | 435.52 | 0.7785 | 339.04 | 4.709 | 5.71 | 5.71 | 4.44 | 4.44 | low |
| `r3_f1_recovery` | 519.65 | 0.7621 | 396.00 | 5.500 | 9.32 | 9.32 | 7.10 | 7.10 | measured |
| `r3_f2_channels` | 519.60 | 0.7621 | 396.01 | 5.500 | 9.32 | 9.32 | 7.10 | 7.10 | measured |
| `r3_f3_information` | 554.32 | 0.7144 | 396.02 | 5.500 | 9.32 | 9.32 | 6.66 | 6.66 | measured |
| `r3_f4_transfer` | 519.60 | 0.7621 | 396.01 | 5.500 | 9.32 | 9.32 | 7.10 | 7.10 | measured |
| `r3_f5_utility` | 519.44 | 0.7624 | 396.00 | 5.500 | 9.32 | 9.32 | 7.11 | 7.11 | measured |
| `r3_s1_learning` | 519.60 | 0.7621 | 396.01 | 5.500 | 9.32 | 9.32 | 7.10 | 7.10 | measured |
| `r3_s2_cofailure` | 519.60 | 0.7621 | 396.01 | 5.500 | 9.32 | 9.32 | 7.10 | 7.10 | measured |
| `s1_study_design` | 381.12 | - | - | - | 7.16 | 7.16 | - | - | unavailable |

Implied printed width across the 10 figures with a measured scale: median 396.01 pt (5.500 in), range 122.89-1700.13 pt. Corroboration: the AGU class file sets `\textwidth 5.5in` = 396 pt (`paper/wrr/template/agujournal2025.cls:958`), consistent with a full-width placement.

AGU/WRR ask for figure text that stays legible in print; a text height below 4.5 pt at printed size is the practical red line used here.

Advisory (not a failure): the following figures pass the 4.5 pt rule but their 5th percentile word box prints below 6 pt, which is small even for a journal figure: `f2_system_design` 2.32 pt, `f5_decision` 4.44 pt.

## 9. Prioritised fix list

| priority | file | finding |
|---|---|---|
| P1 | `paper/wrr/figures/f2_system_design.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 7.18 pt x placement scale 0.3224 = 2.32 pt on paper (< 4.5 pt); the figure is drawn 381 pt wide and printed 123 pt wide |
| P1 | `paper/wrr/figures/f5_decision.pdf` | EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height 5.71 pt x placement scale 0.7785 = 4.44 pt on paper (< 4.5 pt); the figure is drawn 436 pt wide and printed 339 pt wide |
| P1 | `paper/wrr/wrr_manuscript.pdf` | OVERLAPPING_TEXT_SAME_BASELINE: 2 word-box pair(s) share a baseline and overlap horizontally (real text collision candidates) |
| P2 | `paper/wrr/figures/f1_support.pdf` | OVERLAPPING_WORD_BOXES: 2 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/wrr_manuscript.pdf` | OVERLAPPING_WORD_BOXES: 6 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P3 | `(environment)` | TOOL_MISSING: drawio is not installed in this environment |
| P3 | `paper/wrr/figures/f1_support.pdf` | FIGURE_NOT_REFERENCED: no \includegraphics in paper/wrr/*.tex refers to this figure PDF |
| P3 | `paper/wrr/figures/f1_support.pdf` | SMALL_RELATIVE_WORD_BOXES: 40 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/f2_system_design.pdf` | FIGURE_NOT_REFERENCED: no \includegraphics in paper/wrr/*.tex refers to this figure PDF |
| P3 | `paper/wrr/figures/f3_reconstructor.pdf` | FIGURE_NOT_REFERENCED: no \includegraphics in paper/wrr/*.tex refers to this figure PDF |
| P3 | `paper/wrr/figures/f3_reconstructor.pdf` | SMALL_RELATIVE_WORD_BOXES: 23 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/f4_mechanism.pdf` | FIGURE_NOT_REFERENCED: no \includegraphics in paper/wrr/*.tex refers to this figure PDF |
| P3 | `paper/wrr/figures/f4_mechanism.pdf` | SMALL_RELATIVE_WORD_BOXES: 25 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/f5_decision.pdf` | FIGURE_NOT_REFERENCED: no \includegraphics in paper/wrr/*.tex refers to this figure PDF |
| P3 | `paper/wrr/figures/f5_decision.pdf` | SMALL_RELATIVE_WORD_BOXES: 30 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/r3_f2_channels.pdf` | SMALL_RELATIVE_WORD_BOXES: 12 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/r3_f4_transfer.pdf` | SMALL_RELATIVE_WORD_BOXES: 8 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/r3_f5_utility.pdf` | SMALL_RELATIVE_WORD_BOXES: 11 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/r3_s1_learning.pdf` | SMALL_RELATIVE_WORD_BOXES: 2 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/r3_s2_cofailure.pdf` | SMALL_RELATIVE_WORD_BOXES: 9 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/s1_study_design.pdf` | FIGURE_NOT_REFERENCED: no \includegraphics in paper/wrr/*.tex refers to this figure PDF |
| P3 | `paper/wrr/wrr_manuscript.pdf` | SMALL_RELATIVE_WORD_BOXES: 31 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/wrr_supporting_information.pdf` | SMALL_RELATIVE_WORD_BOXES: 11 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |

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


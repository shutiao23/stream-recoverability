# WRR figure and PDF quality assurance

Generated 2026-10-19T19:12:52Z by `python3 scripts/266_wrr_figure_qa.py`.

* JSON: `results/wrr_submission_ready/figure_qa.json`
* Markdown: `results/wrr_submission_ready/figure_qa_report.md`
* tools: `pdffonts` pdffonts version 22.02.0, `pdfinfo` pdfinfo version 22.02.0, `pdftotext` pdftotext version 22.02.0, `pdfimages` pdfimages version 22.02.0, `pdftoppm` pdftoppm version 22.02.0, `rsvg-convert` rsvg-convert version 2.52.5, `drawio` [2363159:1019/191250.693879:ERROR:ui/ozone/platform/x11/ozone_platform_x11.cc:257] Missing X server or $DISPLAY

## Verdict

**PASS (with warnings)** — 0 hard failure(s) in 0 file/check/page group(s), 7 warning(s).

Exit status is 0 for the strict run (`--report-only` always exits 0 so the regression test is not turned red by a real finding).

| check | hard failures | warnings |
|---|---|---|
| FONT_NOT_EMBEDDED — font not embedded (check a) | 0 | 0 |
| FIGURE_NOT_SINGLE_PAGE — figure page count != 1 (check b) | 0 | 0 |
| TEXT_OUTSIDE_PAGE — text > 1 pt outside the page and ink clipped or unverified (check c) | 0 | 0 |
| TEXT_HEIGHT_BELOW_MINIMUM — line-estimated type size < 4.5 pt (check d) | 0 | 0 |
| OVERLAPPING_TEXT_SAME_BASELINE — overlapping boxes, same baseline (check e) | 0 | 0 |
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
| SMALL_RELATIVE_WORD_BOXES — word far smaller than its own line (check d) | 0 | 5 |
| FONT_UNNAMED — embedded font with no BaseFont name | 0 | 0 |
| DEGENERATE_WORD_BOXES — word boxes with non-positive height | 0 | 0 |
| FIGURE_NOT_REFERENCED — figure PDF not referenced by any .tex | 0 | 0 |
| PAGE_SIZE_VARIES — page sizes differ within one PDF | 0 | 0 |
| BBOX_PAGE_COUNT_MISMATCH — pdftotext -bbox page count differs from pdfinfo | 0 | 0 |
| BUILT_PDF_MISSING — a built PDF was not found | 0 | 0 |
| TOOL_MISSING — a required tool is not installed | 0 | 0 |

Thresholds: text outside page > 1.0 pt, line-estimated type size < 4.5 pt, overlap > 25% of the smaller box, raster < 300 dpi.

### Real defects versus box-model artifacts

No hard failure was recorded: every word box that crosses a page edge was shown by the render to keep its ink inside the page, and no line of type is below the size threshold.

No warning-level finding is classified as a real defect.

## Per-figure master table

| figure | pages | page size (in) | fonts | non-embedded | text outside page | min word height (pt) | overlap pairs | of which same baseline | min raster ppi | source | effective print p05 (pt) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `f1_support` | 1 | 5.58x4.49 | 1 | 0 | 0 | 6.29 | 2 | 0 | - | python | 6.20 | warn |
| `f2_system_design` | 1 | 5.29x2.58 | 2 | 0 | 0 | 7.18 | 0 | 0 | - | drawio+python | 7.46 | ok |
| `f3_reconstructor` | 1 | 5.01x4.07 | 1 | 0 | 0 | 5.38 | 0 | 0 | - | python | 6.91 | warn |
| `f4_mechanism` | 1 | 5.62x4.49 | 1 | 0 | 0 | 6.03 | 0 | 0 | - | python | 6.61 | warn |
| `f5_decision` | 1 | 5.87x4.69 | 1 | 0 | 0 | 6.06 | 0 | 0 | - | python | 5.67 | warn |
| `s1_study_design` | 1 | 5.29x1.76 | 2 | 0 | 0 | 7.16 | 0 | 0 | - | drawio+python | 7.44 | ok |

"effective print p05" is the 5th-percentile word-box height multiplied by the measured placement scale in the built PDFs (derived, see the print-size section).

## Built documents

| document | pages | page size (pt) | page size (in) | fonts | non-embedded | text outside page | min word height (pt) | overlap pairs | same baseline | min raster ppi |
|---|---|---|---|---|---|---|---|---|---|---|
| `paper/wrr/wrr_manuscript.pdf` | 28 | 612.00 x 792.00 | 8.50 x 11.00 | 27 | 0 | 0 | 4.70 | 2 | 0 | - |
| `paper/wrr/wrr_supporting_information.pdf` | 13 | 612.00 x 792.00 | 8.50 x 11.00 | 24 | 0 | 0 | 4.70 | 0 | 0 | - |

## 1. Fonts (check a)

| file | fonts | types | non-embedded | names of non-embedded | unnamed/Type 3 | all embedded |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f1_support.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/f2_system_design.pdf` | 2 | CID TrueType x2 | 0 | none | none | yes |
| `paper/wrr/figures/f3_reconstructor.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/f4_mechanism.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/f5_decision.pdf` | 1 | CID TrueType x1 | 0 | none | none | yes |
| `paper/wrr/figures/s1_study_design.pdf` | 2 | CID TrueType x2 | 0 | none | none | yes |
| `paper/wrr/wrr_manuscript.pdf` | 27 | CID TrueType x6, Type 1 x21 | 0 | none | none | yes |
| `paper/wrr/wrr_supporting_information.pdf` | 24 | CID TrueType x2, Type 1 x22 | 0 | none | none | yes |

`[none]` is the name Poppler reports for a producer-embedded Type 3 subset with no BaseFont entry (matplotlib's default pdf.fonttype=3); the font is embedded even though it is unnamed.

## 2. Page geometry (check b)

| file | pages | page size (pt) | page size (in) | distinct page sizes | single page | text outside page | max overflow (pt) |
|---|---|---|---|---|---|---|---|
| `paper/wrr/figures/f1_support.pdf` | 1 | 401.54 x 323.53 | 5.58 x 4.49 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f2_system_design.pdf` | 1 | 381.12 x 186.00 | 5.29 x 2.58 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f3_reconstructor.pdf` | 1 | 360.75 x 292.94 | 5.01 x 4.07 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f4_mechanism.pdf` | 1 | 404.84 x 323.52 | 5.62 x 4.49 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/f5_decision.pdf` | 1 | 422.75 x 337.70 | 5.87 x 4.69 | 1 | yes | 0 | 0.00 |
| `paper/wrr/figures/s1_study_design.pdf` | 1 | 381.12 x 126.96 | 5.29 x 1.76 | 1 | yes | 0 | 0.00 |
| `paper/wrr/wrr_manuscript.pdf` | 28 | 612.00 x 792.00 | 8.50 x 11.00 | 1 | no | 0 | 0.00 |
| `paper/wrr/wrr_supporting_information.pdf` | 13 | 612.00 x 792.00 | 8.50 x 11.00 | 1 | no | 0 | 0.00 |

## 3. Text outside the page box (check c)

No word box extends more than 1.0 pt outside its page in any target PDF.

## 4. Minimum text height (check d)

| file | words measured | min box (pt) | 5th pct (pt) | median (pt) | raw boxes < 4.5 pt (literal rule) | lines below threshold (gate) | smaller than their line | degenerate boxes |
|---|---|---|---|---|---|---|---|---|
| `paper/wrr/figures/f1_support.pdf` | 158 | 6.29 | 6.29 | 7.69 | 0 | 0 | 40 | 0 |
| `paper/wrr/figures/f2_system_design.pdf` | 86 | 7.18 | 7.18 | 7.18 | 0 | 0 | 0 | 0 |
| `paper/wrr/figures/f3_reconstructor.pdf` | 78 | 5.38 | 6.29 | 8.04 | 0 | 0 | 14 | 0 |
| `paper/wrr/figures/f4_mechanism.pdf` | 125 | 6.03 | 6.76 | 7.69 | 0 | 0 | 18 | 0 |
| `paper/wrr/figures/f5_decision.pdf` | 191 | 6.06 | 6.06 | 7.69 | 0 | 0 | 55 | 0 |
| `paper/wrr/figures/s1_study_design.pdf` | 58 | 7.16 | 7.16 | 7.16 | 0 | 0 | 0 | 0 |
| `paper/wrr/wrr_manuscript.pdf` | 9507 | 4.70 | 7.20 | 8.85 | 0 | 0 | 127 | 0 |
| `paper/wrr/wrr_supporting_information.pdf` | 3587 | 4.70 | 7.08 | 8.85 | 0 | 0 | 0 | 0 |

No word box is below 4.5 pt in any target PDF.

## 5. Overlapping text (check e)

Rule: pairs of word boxes whose intersection area exceeds 25% of the smaller box, exact duplicates and shadow duplicates excluded. **This is a conservative approximation of visual overlap**: it is derived from Poppler word boxes, which are axis-aligned even for rotated text and which include font ascent/descent, and it cannot see text drawn over graphics.

| file | word boxes | candidate pairs | same baseline (real) | adjacent-line padding | atypical box geometry | duplicates ignored (exact/shadow) |
|---|---|---|---|---|---|---|
| `paper/wrr/figures/f1_support.pdf` | 158 | 2 | 0 | 0 | 2 | 0/0 |
| `paper/wrr/figures/f2_system_design.pdf` | 86 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f3_reconstructor.pdf` | 78 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f4_mechanism.pdf` | 125 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/f5_decision.pdf` | 191 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/figures/s1_study_design.pdf` | 58 | 0 | 0 | 0 | 0 | 0/0 |
| `paper/wrr/wrr_manuscript.pdf` | 9507 | 2 | 0 | 0 | 2 | 0/0 |
| `paper/wrr/wrr_supporting_information.pdf` | 3587 | 0 | 0 | 0 | 0 | 0/0 |

### Flagged pairs

#### `paper/wrr/figures/f1_support.pdf` — 2 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 1 | atypical_box_geometry | 36.4 | `plitude` | (92.1, 290.05, 114.43, 303.78) | `ann` | (103.87, 299.63, 115.69, 309.84) | 9.58 | 7.69 |
| 1 | atypical_box_geometry | 32.7 | `30-day` | (62.65, 289.96, 84.06, 303.46) | `al` | (74.66, 300.55, 80.41, 309.45) | 10.58 | 7.69 |

Pair classification: `atypical_box_geometry` x2.

#### `paper/wrr/wrr_manuscript.pdf` — 2 pair(s)

| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |
|---|---|---|---|---|---|---|---|---|
| 6 | atypical_box_geometry | 32.7 | `30-da` | (158.99, 412.89, 176.61, 425.0) | `al` | (170.83, 422.13, 176.5, 430.91) | 9.24 | 7.96 |
| 6 | atypical_box_geometry | 25.4 | `nnual` | (203.33, 417.43, 220.96, 430.1) | `e` | (206.39, 411.77, 210.06, 419.35) | 5.66 | 7.96 |

Pair classification: `atypical_box_geometry` x2.

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
| `f4_mechanism` | NO | no | `scripts/335_wrr_figures_v2.py` | python | ok |
| `f5_decision` | NO | no | `scripts/335_wrr_figures_v2.py` | python | ok |
| `s1_study_design` | yes | yes — study design and evidence chain (drawio, 2026-10-20) | `scripts/335_wrr_figures_v2.py`, `scripts/337_wrr_drawio_figures.py` | drawio+python | ok |

The schematic list is explicit (see `SCHEMATIC_FIGURES` in the script, taken from `figures/v17/drawio/README.md`): a new architecture or system-design figure must be added there, otherwise a missing draw.io source cannot be detected.

| figure | figure built elsewhere in `figures/` | identical to the paper copy |
|---|---|---|
| `f1_support` | `figures/wrr/f1_support.pdf` | no |
| `f2_system_design` | `figures/wrr/f2_system_design.pdf` | no |
| `f3_reconstructor` | `figures/wrr/f3_reconstructor.pdf` | no |
| `f4_mechanism` | `figures/wrr/f4_mechanism.pdf` | yes |
| `f5_decision` | `figures/wrr/f5_decision.pdf` | no |
| `s1_study_design` | `figures/wrr/s1_study_design.pdf` | no |

## 7. Raster image resolution (check g)

| file | page | image | pixels | colour | effective ppi (x, y) | flag |
|---|---|---|---|---|---|---|
| - | - | - | no raster images in any target PDF | - | - | - |

## 8. Printed size and effective text size (derived)

Method: the scale at which each figure is placed in the built PDFs is measured by matching the figure's distinctive words against the words of the built pages (all pairs of unambiguous matches give a distance ratio; the largest tight cluster is the estimate). `scale x figure width` is the printed width, and raw text heights times the scale give the size the reader sees on paper. These values are derived, never hard failures.

| figure | width (pt) | measured scale | printed width (pt) | printed width (in) | raw min (pt) | raw p05 (pt) | effective min (pt) | effective p05 (pt) | confidence |
|---|---|---|---|---|---|---|---|---|---|
| `f1_support` | 401.54 | 0.9862 | 396.01 | 5.500 | 6.29 | 6.29 | 6.20 | 6.20 | measured |
| `f2_system_design` | 381.12 | 1.0391 | 396.01 | 5.500 | 7.18 | 7.18 | 7.46 | 7.46 | measured |
| `f3_reconstructor` | 360.75 | 1.0977 | 396.01 | 5.500 | 5.38 | 6.29 | 5.91 | 6.91 | measured |
| `f4_mechanism` | 404.84 | 0.9782 | 396.01 | 5.500 | 6.03 | 6.76 | 5.90 | 6.61 | measured |
| `f5_decision` | 422.75 | 0.9368 | 396.02 | 5.500 | 6.06 | 6.06 | 5.67 | 5.67 | measured |
| `s1_study_design` | 381.12 | 1.0391 | 396.01 | 5.500 | 7.16 | 7.16 | 7.44 | 7.44 | measured |

Implied printed width across the 6 figures with a measured scale: median 396.01 pt (5.500 in), range 396.01-396.02 pt. Corroboration: the AGU class file sets `\textwidth 5.5in` = 396 pt (`paper/wrr/template/agujournal2025.cls:958`), consistent with a full-width placement.

AGU/WRR ask for figure text that stays legible in print; a text height below 4.5 pt at printed size is the practical red line used here.

Advisory (not a failure): the following figures pass the 4.5 pt rule but their 5th percentile word box prints below 6 pt, which is small even for a journal figure: `f5_decision` 5.67 pt.

## 9. Prioritised fix list

| priority | file | finding |
|---|---|---|
| P2 | `paper/wrr/figures/f1_support.pdf` | OVERLAPPING_WORD_BOXES: 2 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P2 | `paper/wrr/wrr_manuscript.pdf` | OVERLAPPING_WORD_BOXES: 2 further word-box pair(s) overlap above 25% of the smaller box; box padding/rotated-text artifacts, verify against the render |
| P3 | `paper/wrr/figures/f1_support.pdf` | SMALL_RELATIVE_WORD_BOXES: 40 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/f3_reconstructor.pdf` | SMALL_RELATIVE_WORD_BOXES: 14 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/f4_mechanism.pdf` | SMALL_RELATIVE_WORD_BOXES: 18 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/figures/f5_decision.pdf` | SMALL_RELATIVE_WORD_BOXES: 55 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |
| P3 | `paper/wrr/wrr_manuscript.pdf` | SMALL_RELATIVE_WORD_BOXES: 127 word box(es) are below 0.45 of their own line height (superscripts, subscripts or fragmented runs); the line itself is at or above 4.5 pt |

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


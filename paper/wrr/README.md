# Water Resources Research submission

The journal-format rendering of the aligned-policy study, typeset with AGU's own
document class. The article is written in the four-step argument used by Yang
Dawen's group: phenomenon, conditional response, mechanism, and decision
consequence. Four main figures carry the argument, one per step; everything else
belongs to the supporting information or to the repository.

Since 2026-10-20 every number in the article and the SI is derived from the
aligned-policy round (`results/wrr_submission_ready/major_revision_20261020/`),
in which the admitted object, the failure event and the tie rule are the same at
calibration, evaluation and deployment. The point-by-point answer to the
2026-10-19 review is `RESPONSE_TO_REVIEW.md`.

| file | what it is |
|---|---|
| `wrr_manuscript.tex` | the article |
| `wrr_manuscript.pdf` | **the submission copy**: AGU's `draft` layout, double-spaced |
| `wrr_manuscript_published.pdf` | the same source in AGU's `published` layout; generated, not the file to submit |
| `wrr_supporting_information.tex` | supporting information, S-numbered as AGU requires |
| `wrr_supporting_information.pdf` | supporting information PDF |
| `RESPONSE_TO_REVIEW.md` | point-by-point response to the 2026-10-19 review |
| `references.bib` | the bibliography (apacite), now the single source; `references_additions.bib` is a comment-only provenance note |
| `figures/f1_support.pdf` | Figure 1: hidden support orders the error, and the order reverses by statistic |
| `figures/f2_system_design.pdf` | Figure 2: system design (draw.io) |
| `figures/f3_reconstructor.pdf` | Figure 3: the reconstructor sets the height of the effect |
| `figures/f4_mechanism.pdf` | Figure 4: placement, persistence, and the residual information a score reads |
| `figures/f5_decision.pdf` | Figure 5: retention, refusal cost, and the regime boundary |
| `figures/si_design.pdf` | Figure S1: the evidence chain |
| `template/` | AGU's class and its supporting files, vendored unmodified — see `template/PROVENANCE.md` |
| `build_report.json` | the result of the last build, including the desk checks |

Each main figure is generated from versioned artifacts by
`scripts/335_wrr_figures_v2.py`; the table behind every panel is written to
`results/wrr_submission_ready/major_revision_20261020/p0_06_figures/` next to the
figure, and the caption names it.

## Building

```
make wrr-round-20261020   # re-run the analysis chain and build all three documents
make wrr-figures-20261020 # re-render the four data figures, S1, and the schematics
make wrr                  # build all three documents and run the desk checks
make wrr-check            # run the desk checks only, without LaTeX
make wrr-figure-qa        # font embedding, page bounds, overlap and provenance checks
```

Or directly: `python3 scripts/223_wrr_build.py`. The build resolves the class
through `TEXINPUTS` rather than by copying it next to the manuscript, so the
vendored template stays the single copy. It builds the submission copy, the
supporting information and the published layout from one source; the published
layout needs XeLaTeX with the STIX Two and FreeFont families, and is skipped
rather than failing the build if they are absent.

The build refuses to mark the manuscript submission-ready while the author block
is a placeholder. `metadata/submission_author_metadata.json` is a human gate:
names, affiliations, funding and ORCID identifiers are not inferred from a
version-control alias.

## Figure size

The four data figures are drawn at 5.6 in wide, which is the width they are
printed at after `\includegraphics[width=\textwidth]`, so the type size in the
PDF is the type size on the page (6–8 pt). The two schematics (Figure 2 and
Figure S1) are draw.io sources exported at 5.29 in and included at the same
width. Nothing is scaled afterwards. The figure QA script checks page aspect,
font embedding, text size, overlapping text, raster resolution, and that every
schematic has a draw.io source.

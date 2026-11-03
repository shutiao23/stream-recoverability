# EMS manuscript build

## Deliverables

From this directory:

| File | Role |
| --- | --- |
| `main.pdf` | Main article: 37 pages, 7 figures, 4 tables, 52 references |
| `supporting_information.pdf` | Supporting Information: 15 pages, 12 tables (S1--S12) |
| `cover_letter.txt` | One-page cover letter |
| `figures/graphical_abstract.pdf` | Graphical abstract |
| `references_ems.bib` | BibTeX database for the main article |
| `main.tex` | Main article source and preamble |
| `supporting_information.tex` | Supporting Information source |

## Exact build commands

From this directory:

```sh
latexmk -g -pdf -interaction=nonstopmode -halt-on-error main.tex
bibtex main
bibtex main
latexmk -g -pdf -interaction=nonstopmode -halt-on-error main.tex
latexmk -g -pdf -interaction=nonstopmode -halt-on-error supporting_information.tex
```

The final `latexmk` pass for the main article resolves the bibliography and
references after the two explicit BibTeX runs. The Supporting Information has
no bibliography and is built with a single `latexmk` invocation.

The build uses `elsarticle.cls` with the `preprint`, `12pt`, and `authoryear`
options, and `elsarticle-harv.bst` for author-year citations in the main
article. Both files are part of the standard `elsarticle` package in TeX Live.
This build was verified with TeX Live 2022 and `elsarticle-harv.bst` installed
under `~/texmf/bibtex/bst/elsarticle/`.

## Source map

| File | Role |
| --- | --- |
| `main.tex` | Preamble, frontmatter, body inputs, bibliography style and data file |
| `frontmatter.tex` | Title, author and affiliation placeholders |
| `abstract.tex` | Abstract |
| `highlights.txt` | Five highlights |
| `body.tex` | Main text, including inputs for figures and tables |
| `figures.tex` | Seven figure environments and captions |
| `trend_signal.tex` | Two trend-signal tables and their interpretation |
| `open_source_flow.tex` | Open-source sensitivity, flow proxy, and flow-comparator table |
| `decision_table.tex` | Practical decision table |
| `declarations.tex` | CRediT, competing interests, funding, ethics, AI declaration |
| `software_availability.tex` | Software and data availability statement |
| `references_ems.bib` | 52 BibTeX entries |
| `figures/` | Station map and graphical abstract |
| `cover_letter.txt` | One-page cover letter |

Figure PDFs for the architecture, observed-window, archive-factorial,
year-selection, regional-recovery, and budget panels are referenced from
`paper/wrr_tr/figures/`; the station map is local to `figures/`.

## Status

- The main article compiles to 37 pages with 7 figures, 4 tables, and 52
  references; the Supporting Information compiles to 15 pages with 12 tables
  (S1--S12).
- Both PDFs build with 0 undefined citations or references and 0 overfull
  boxes. `pdftotext` finds no `??`, `(author?)`, AGU/Key Points/PLS text,
  "contact the authors", or "available on request".
- The only remaining build warning is the BibTeX database warning
  `empty pages in angelopoulos2024`; it does not affect citations, numbering,
  or pagination.
- The abstract is 185 words (limit 200). Every highlight is at most 85
  characters (longest 83).
- Software: `gapbench` 1.2.0, MIT license, public repository
  `https://github.com/shutiao23/stream-recoverability`.
- Archival software DOI: pending (no Zenodo deposit, GitHub release, or
  `v1.2.0` tag exists). The historical `v1.0.0` tag is not this version.
- Reviewer access: the public repository requires no credentials. Access to the
  restricted LUBW observations is pending provider agreement and
  editorial/legal confirmation.
- Processed annual tables needed for figure and trend reproduction are in the
  public repository; restricted daily observations are not redistributed.

## Remaining external items

These items are external to the manuscript build: the compiled files above are
complete for their current content, but submission remains gated on them.

1. Author names, affiliations, corresponding-author details, funding, and
   CRediT roles (`[AUTHOR TO CONFIRM]`).
2. Editorial/legal confirmation of the LUBW access and ethics wording
   (`[EDITORIAL/LEGAL CONFIRMATION REQUIRED]`).
3. Zenodo DOI for the archived code release and processed tables (`[PENDING]`);
   no DOI or release should be invented.
4. Reviewer access to restricted LUBW material (`[PENDING]` provider agreement
   and editorial/legal confirmation).
5. A locked new-station confirmation that was not part of this study.
6. Program size and full-replay memory measurement (`[PENDING]`).

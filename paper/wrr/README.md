# Water Resources Research submission

The journal-format rendering of `paper_archived/v18/`, typeset with AGU's own document
class. The Markdown in `paper_archived/v18/` remains the source of the prose and of every
number in it, because it is what `scripts/221_v18_audit_manuscript.py` checks
against the analysis artifacts; this directory is what a desk editor would open.

| file | what it is |
|---|---|
| `wrr_manuscript.tex` | the article |
| `wrr_manuscript.pdf` | **the submission copy**: AGU's `draft` layout, double-spaced, 46 pages |
| `wrr_manuscript_published.pdf` | the same source in AGU's `published` layout, which renders close to the version of record: 28 pages. Generated; not the file to submit |
| `wrr_supporting_information.tex` | supporting information, S-numbered as AGU requires |
| `wrr_supporting_information.pdf` | built: 5 pages |
| `references.bib` | 18 entries, rendered by apacite as the class requires |
| `figures/` | the figures, copied from `figures/v17/` and `figures/v18/` |
| `template/` | AGU's class and its supporting files, vendored unmodified — see `template/PROVENANCE.md` |
| `build_report.json` | the result of the last build, including the desk checks |

## Building

```
make wrr-figures    # re-render the figures at page size (only after a figure changes)
make wrr            # build all three documents and run the desk checks
make wrr-check      # run the desk checks only, without LaTeX
```

Or directly: `python3 scripts/223_wrr_build.py`. The build resolves the class
through `TEXINPUTS` rather than by copying it next to the manuscript, so the
vendored template stays the single copy. It builds the submission copy, the
supporting information and the published layout from one source; the published
layout needs XeLaTeX with the STIX Two and FreeFont families, and is skipped
rather than failing the build if they are absent.

## Figures

The figures in `figures/` are **not** the ones in `figures/v17/` and
`figures/v18/`. Those are drawn wide, three or four panels in a row, which is
right for a screen and wrong for a 5.5 inch journal column: scaled into it, a
3.9:1 figure is an inch and a half tall and its tick labels are unreadable.

Setting `WRR_JOURNAL_FIGURES=1` makes the figure scripts stack the same panels
into a page-shaped grid and draw them at the size they will be printed, so
nothing is scaled afterwards. The layout lives in
`src/stream_recoverability/plotting/journal.py`; panel order is unchanged, so a
figure function needs no edit beyond the few places where a label or a legend
has to be shorter at half width. A test fails if any figure here is wider than
2.2:1.

## What the build checks

A manuscript that fails any of these is returned by AGU without review, so the
build fails on them rather than reporting them:

- exactly three Key Points, each 140 characters or fewer;
- an Abstract of 250 words or fewer (WRR's limit);
- a Plain Language Summary of 200 words or fewer, which WRR requires;
- an Open Research Statement, which WRR requires;
- every citation resolving to a bibliography entry, and no uncited entries;
- the bibliography actually rendering all 18 entries.

The current values are 110, 118 and 126 characters; 249 words; and 196 words.

The test suite adds four checks the build does not: that no LaTeX log contains
an error, that every figure is page-shaped, that the figures sit in the text
rather than in a block at the end, and that each table's tabularx weights sum to
its column count so the table fills the text width exactly.

## What is deliberately not filled in

The author block is a placeholder and the build reports
`submission_ready: false` because of it. `paper_archived/author_information_required.md`
records why: the repository does not contain verified personal information, and
legal names, affiliations, ORCID identifiers, funding lines and competing-interest
statements must not be inferred from a version-control alias. Fill
`metadata/submission_author_metadata.json` first; the build will then report the
manuscript as ready.

## Relationship to the other paper directories

- `paper_archived/v18/` — the source of record: Markdown prose, the claim matrix
  (including the claims that did not stand), the protocol, the referee response.
- `paper_archived/v17/` — the previous version, kept because its pre-registered
  confirmation is the one that was scored, and marked as superseded.
- `paper/wrr/` — this directory: the same article in AGU format.

A number that appears in more than one of these is checked in one place only, in
`paper_archived/v18/`. If you change a number, change it there, re-run the audit, and then
carry it here.

# Where these files came from

These are AGU's own LaTeX template files, vendored unmodified so that the
manuscript in this directory builds without a network and so that a reviewer can
see exactly which version of the class it was typeset against.

| field | value |
|---|---|
| source | https://github.com/AGU-Publications/agujournal2025-latex-template |
| commit | `355052226d872cf6b9211c12b73b2ed2da133a7d` |
| commit date | 2026-03-27T13:07:21-04:00 |
| retrieved | 2026-09-24 |

| file | role |
|---|---|
| `agujournal2025.cls` | the document class for all AGU journals, including *Water Resources Research* |
| `wiley-macros.tex` | macros the class expects to find |
| `tweaklist-git-moderncv-fixed.sty` | list-spacing patch the class requires |
| `agu-logo-large.pdf`, `agu-logo-small.pdf` | title-page marks the class draws |
| `agujournaltemplate.tex` | AGU's blank sample article, kept for reference |

**Do not edit these.** If AGU releases a new version, replace the whole
directory and record the new commit here. The manuscript is
`../wrr_manuscript.tex`.

AGU's 2025 class replaces `agujournal2019.cls`; it renders closer to the
typeset version of record, which is what makes its page count meaningful.

## Re-verified 2026-10-20

The class and its supporting files were compared byte for byte with the official
repository at the commit above:

| file | sha256 (local = upstream) |
|---|---|
| `agujournal2025.cls` | `a6645a79392906eb31fd63a4d3f28a2322464c0552f93c4a35da9f4a85067fab` |
| `wiley-macros.tex` | `7ea18648b7bd2c632065d4303830a54192626450139d76db39760516a16ef71c` |
| `tweaklist-git-moderncv-fixed.sty` | `85a31337d69412566a227209ec908f3a3242ecf673819ca86564d9dc23bfbef1` |
| `agujournaltemplate.tex` | `ad077031c061593ef712fc7fb62427ccf31218239e1afdb1ce379cc863f6ec5c` |

All four are identical, so the manuscript is typeset against the official AGU
2025 class at the recorded commit, not a local modification.

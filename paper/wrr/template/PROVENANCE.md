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

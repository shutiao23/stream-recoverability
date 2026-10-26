# Architecture and system-design figures

Both diagrams are **draw.io source files**. The PDFs in this directory are
exports from draw.io Desktop (v32.6.1) and are the files included by
`review_completion_article.tex`.

| Source | Exported PDF | Role | Page size |
|---|---|---|---|
| `fig1_study_architecture.drawio` | `fig1_study_architecture.pdf` | end-to-end evidence architecture | 5.35 x 3.42 in |
| `fig2_release_system.drawio` | `fig2_release_system.pdf` | three-output release-system design | 5.35 x 3.72 in |

## Re-export

Open the `.drawio` file in draw.io, or run the draw.io Desktop CLI:

```bash
drawio -x -f pdf -o fig1_study_architecture.pdf fig1_study_architecture.drawio
drawio -x -f pdf -o fig2_release_system.pdf fig2_release_system.drawio
```

The exports use the diagram page size, embed Liberation Sans as vector text,
and contain no raster images. Keep the page size and font sizes unchanged when
editing; both PDFs are placed at `\textwidth` (5.375 in) so that the smallest
label remains at least 6.7 pt in print.

`fig1_study_architecture.png` and `fig2_release_system.png` are inspection
copies only; the manuscript includes the PDFs.

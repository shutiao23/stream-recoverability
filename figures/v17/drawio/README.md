# draw.io sources for the architecture and system-design figures

These `.drawio` files are the **editable source of truth** for every schematic,
architecture and design figure in `paper/wrr/wrr_manuscript.tex` and
`paper/wrr/wrr_supporting_information.tex`. They open unchanged in draw.io /
diagrams.net (desktop or app.diagrams.net) and are stored uncompressed, so they
diff line by line in git.

| source | figure in the paper | what it shows |
|---|---|---|
| `f0_problem_frame.drawio` | SI Fig. S2 | why one completeness threshold cannot serve two estimands: support, governing axis, and the measured error gradients along each |
| `f1_system_architecture.drawio` | SI Fig. S3 | the screening system: visible features, the information barrier, the estimator library, risk model, selection-conditional conformal calibration, and the two action spaces |
| `f2_experiment_design.drawio` | Fig. 2 | study design and data flow: providers, the river-only and complete-year filters, the network-level split and its retrospective-holdout status, the freeze, the sealed USGS confirmation with its prior-access audit and clean-subset diagnostic, the pre-registered multi-agency transport panel with its primary/secondary strata, and the truth-free deployment on real incomplete years |
| `f3_evidence_chain.drawio` | SI Fig. S1 | the evidence chain: one link per research question, each labelled with the evidence class it rests on |
| `f4_deployment_workflow.drawio` | SI Fig. S6 | what an agency does with the result, including the representativeness guardrail and the abstention alternative |

## Rules

1. **Never edit the PDF or SVG.** Edit the `.drawio`, then re-export. The PDFs
   and SVGs in `figures/v17/` are build products.
2. **Keep the files uncompressed.** In draw.io: *Extras → Edit Diagram* works
   only on uncompressed XML, and a compressed file is an opaque blob in review.
   If you save from the desktop app, uncheck "Compressed" in
   *File → Properties*.
3. **Stay inside the supported shape set** — rectangle, rounded rectangle,
   ellipse, note, and orthogonal edges with explicit waypoints, plus `html=1`
   labels whose lines carry `<b>` / `<i>` runs. The fallback exporter fails
   loudly on anything else rather than dropping it silently, so a figure cannot
   quietly stop matching its PDF.
4. **Numbers inside a figure are claims.** Anything quoted in a box must exist
   in the manuscript or in an artifact under `results/`, and the export is
   checked against the source geometry (see below).
5. **Type must stay legible at the printed width.** The AGU single column is
   5.5 in, so a label of `f` px in a drawing `W` px wide prints at
   `396 * f / W` pt. Every label must print at **at least 5 pt**, which fixes
   `f / W >= 1 / 79.2`; the current sources keep the smallest label at
   5.16–6.17 pt. Add a line, re-wrap it, or shrink the grid — never shrink the
   type.

## Export

```
make figures-drawio           # portable: renders the same XML to SVG and PDF
make figures-drawio-native    # preferred where draw.io desktop is installed
```

`scripts/205_v17_drawio_export.py` parses the `.drawio` XML and renders it
through SVG to PDF with `rsvg-convert`, writing the PDF at the printed width
(`--print-width-in`, 5.5 in by default) so the manuscript includes it at scale
1.0 and the type size in the PDF is the type size on the page. That is the same
rule the analysis figures follow through
`stream_recoverability.plotting.journal`, which draws its panels at
`COLUMN_INCHES = 5.5` for exactly this reason.

`figures-drawio-native` runs the official exporter:

```
drawio -x -f pdf --crop -o figures/v17/<name>.pdf figures/v17/drawio/<name>.drawio
```

The draw.io desktop application is an Electron binary and cannot be installed
in every build environment. It exports at the drawing's natural size rather
than at 5.5 in, so its page is larger; included at `\textwidth` the printed
type is the same, because the ratio of type to page is what the geometry fixes.
Both paths consume the identical source file; neither path is a second copy of
the figure.

## Checks

`python3 scripts/205_v17_drawio_export.py` is followed by the geometry and
PDF checks recorded in `docs/reviews/drawio_figure_update.md`: one page, every
font embedded, no word outside the page box or its own box, no overlapping
words (`pdftotext -bbox`), and a minimum word height of 5 pt at the printed
width.

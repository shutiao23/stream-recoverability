# draw.io sources for the architecture and system-design figures

These `.drawio` files are the **editable source of truth** for every schematic,
architecture and design figure in `paper/v17/manuscript.md`. They open unchanged
in draw.io / diagrams.net (desktop or app.diagrams.net) and are stored
uncompressed, so they diff line by line in git.

| source | figure in the article | what it shows |
|---|---|---|
| `f0_problem_frame.drawio` | Figure 0 | why one completeness threshold cannot serve two estimands: support, governing axis, and the measured error gradients along each |
| `f1_system_architecture.drawio` | Figure 1 | the screening system: visible features, the information barrier, the estimator library, risk model, selection-conditional conformal calibration, and the two action spaces |
| `f2_experiment_design.drawio` | Figure 2 | study design and data flow: providers, quality control, the network-level stratified split, the gate, the freeze, and the single opening of the reserved panel |
| `f3_evidence_chain.drawio` | Figure 3 | the evidence chain by research question, and the two links that are not yet closed |
| `f4_deployment_workflow.drawio` | Figure 4 | what an agency does with the result, including the representativeness guardrail |

## Rules

1. **Never edit the PDF or SVG.** Edit the `.drawio`, then re-export. The PDFs
   and SVGs in `figures/v17/` are build products.
2. **Keep the files uncompressed.** In draw.io: *Extras → Edit Diagram* works
   only on uncompressed XML, and a compressed file is an opaque blob in review.
   If you save from the desktop app, uncheck "Compressed" in
   *File → Properties*.
3. **Stay inside the supported shape set** — rectangle, rounded rectangle,
   ellipse, note, and orthogonal edges with explicit waypoints. The fallback
   exporter fails loudly on anything else rather than dropping it silently, so
   a figure cannot quietly stop matching its PDF.
4. **Numbers inside a figure are claims.** Anything quoted in a box must exist
   in `results/v17_fitness/` and be listed in `evidence_ledger.csv`.

## Export

```
make figures-drawio           # portable: renders the same XML to SVG and PDF
make figures-drawio-native    # preferred where draw.io desktop is installed
```

`figures-drawio-native` runs the official exporter:

```
drawio -x -f pdf --crop -o figures/v17/<name>.pdf figures/v17/drawio/<name>.drawio
```

The draw.io desktop application is an Electron binary and cannot be installed in
every build environment, so `scripts/205_v17_drawio_export.py` parses the same
`.drawio` XML and renders it through SVG to PDF with `rsvg-convert`. Both paths
consume the identical source file; neither path is a second copy of the figure.

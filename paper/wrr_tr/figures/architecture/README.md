# Architecture and decision figures

The current figures are generated from editable Graphviz sources. The earlier
`fig1_study_architecture.drawio` and `fig2_release_system.drawio` and their
exports are historical artifacts; their wording does not describe the current
evaluation paths.

| Source | Exported PDF | Role |
|---|---|---|
| `fig1_evidence_actual.dot` | `fig1_evidence_actual.pdf` | separate observed, single-year and whole-archive evidence paths |
| `fig2_release_actual.dot` | `fig2_release_actual.pdf` | evaluated three-output rule and exploratory selected-trend analysis |

`make review-report` regenerates both vector PDFs. To re-export manually:

```bash
dot -Tpdf fig1_evidence_actual.dot -o fig1_evidence_actual.pdf
dot -Tpdf fig2_release_actual.dot -o fig2_release_actual.pdf
```

The PNG files are inspection copies only. Hidden target days are excluded from
local fitting; unmasked target and donor values can be used. The source annual
models are fitted separately and held fixed during archive reanalysis.

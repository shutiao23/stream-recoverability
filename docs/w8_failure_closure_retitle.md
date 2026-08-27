# W8 failure-closure (development retitle)

Date: 2026-08-27  
Status: development stop-loss. Not confirmatory T2. Not a retune license.

## Decision

The W7 first-layer cheap-model slice on `huc8_01070004` recorded

`operator_incremental_r2_vs_donor_r2_only = 0.03997 < 0.05`.

The locked action is **retitle to predictability**. Do not retune the Schur
operator, Twin E, or isolation/φ to manufacture a 0.05 increment.

`n_networks = 1`. Cluster-bootstrap CIs stay `withheld_n_lt_100_network_interval`.
`go_no_go` remains `NO_GO_T2_PRIMARY_EVIDENCE`. Broader W7 may revise the
increment; it may not retune.

The historical two-network manuscript is unchanged.

## Development title (next paper, not licensed)

Fitting-period covariance as a predictability diagnostic for stream-temperature
gap skill.

Not: operator novelty over donor \(R^2\); a monitoring decision rule;
confirmatory T2.

## Reproduce

```bash
PYTHONPATH=src python scripts/92_write_w8_failure_closure.py
```

Writes `results/framework/w8_failure_closure_v1/w8_failure_closure_manifest.json`.

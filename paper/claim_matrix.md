# Claim-to-evidence matrix

No abstract, Key Point, or conclusion claim may be ticked until the named
artifact exists and the submission gate is `go`.

| Claim | Required artifact | Current status |
| --- | --- | --- |
| Protocol exists | `configs/design_freeze_v3.yaml` | present |
| Split QC fields exist | `metadata/quality_codebook.csv`; `published_v2` | codebook present; version build pending if directory absent |
| Dual frontier contract | `statistics.frontier_denominators` | required in v3 |
| Donor-C falsification contract | `required_protocol_sensitivities.donor_c_falsification_v1` | required in v3 |
| Model roster frozen | `finalized_model_roster_v1` | pending |
| Internal formal evidence | complete core/full/dense/net manifests | pending |
| External confirmation | once-lock + 60/60 confirmatory tables | not opened |
| Any MAE/skill/frontier number | current-protocol formal table row + cluster CI | forbidden until the rows exist |

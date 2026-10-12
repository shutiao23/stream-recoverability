# Pre-fit recoverability operator — v9 main paper lineage

Canonical directory for the cross-network recoverability-operator study (`design_freeze_v9` charter, `design_freeze_v10_executable` protocol).

| Artifact | Path |
| --- | --- |
| Manuscript (draft) | `manuscript.md` |
| Development results | `results.md` |
| Claim matrix | `claim_matrix.md` |
| Results registry | `results_registry.json` |
| Supporting Information | `supporting_information.md` |
| Failure-closure package | `package_manifest.json` |
| Charter freeze | `../../configs/design_freeze_v9.yaml` |
| Executable protocol | `../../configs/design_freeze_v10_executable.yaml` |

**Status:** evaluate-once sealed QC completed and consumed the production
authorization. It read 2,880 registered objects and retained 32 independent
networks (29 HUC8 + 3 FOEN), below the frozen sealed floor of 40. Confirmatory
scoring was therefore not run. The full qualified inventory is 99/100
(67 open + 32 sealed); no network-level interval or C1–C3 claim is licensed.

The frozen v10 YAML intentionally retains its pre-unseal fields. Current state
is recorded in `results_registry.json` and
`../../docs/sealed_t7_qc_failure_closure.md`.

Supersedes `paper/next/`. Do not cite v4 case-study numbers in this lineage.

# Sealed T7 QC failure closure

Date: 2026-08-27
Lineage: `paper/main_v9/`
Protocol: `configs/design_freeze_v10_executable.yaml`

## Outcome

The evaluate-once lock was claimed before any sealed read. The production QC
reader then consumed all 2,880 registered objects. Thirty-two independent
networks passed the frozen QC rules:

| Provider | Eligible networks |
| --- | ---: |
| USGS HUC8 | 29 |
| FOEN | 3 |
| **Total** | **32** |

The sealed absolute floor was 40. Because 32 < 40, confirmatory fixed-model
recovery scoring was not run. There is no sealed Spearman, calibration slope,
incremental comparison, placement result, or triage result. `formal_evidence`
and `headline_claim_licensed` remain false.

The broader qualified inventory is 99/100: 67 open-role networks plus the 32
sealed networks that passed QC. The three FOEN networks count in the inventory
because their daily values were prospectively locked and evaluated under the
same frozen QC rules. This post-QC accounting correction does not make the
sealed floor pass.

## Immutable evidence

- Evaluate-once lock: `results/framework/t2_sealed_confirmatory_v1/evaluate_once_lock.json`
- Run ledger: `results/framework/t2_sealed_confirmatory_v1/evaluate_once_run_ledger.json`
- QC manifest: `results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1/sealed_qc_manifest.json`
- Eligible-network list: `results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1/eligible_networks.csv`
- Current results registry: `paper/main_v9/results_registry.json`

The frozen v10 YAML retains `sealed_outcomes_opened: false` and its 67-network
pre-unseal count deliberately: those fields describe the state at protocol
freeze, not the current execution state. They must not be edited after the
ceremony.

## Prohibited recovery actions

- rerunning or resetting the evaluate-once lock;
- scoring the 32 eligible networks and calling the result confirmatory;
- replacing attrited networks after inspecting their QC;
- lowering the 40-network sealed floor or 100-network interval floor;
- presenting development donor-R² or operator results as sealed evidence.

## Scientific closure

C1–C3 are untested in this lineage. Development evidence continues to favor
simple donor redundancy over operator superiority, but it is not a
confirmatory result. A future test requires a new prospective protocol and
genuinely untouched networks; it cannot reuse or relabel this sealed panel.

#!/usr/bin/env python3
"""Evidence ledger: every claim to the artifact, script and hash behind it.

The audit script checks that the prose agrees with the artifacts. This is the
inverse index: for each claim, where the number came from, which script made
it, and the digest of the file, so a reader can verify provenance without
re-running anything.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import RESULTS_ROOT  # noqa: E402

LEDGER = RESULTS_ROOT / "evidence_ledger.csv"

ENTRIES = [
    ("P1", "Recorded-days metrics cost more than one interannual SD", "182_v17_ceiling", "step4_ceiling/estimator_tolerances.csv", "3.1"),
    ("M1", "Which axis wins depends on the endpoint", "196_v17_metric_generality", "step17_metric_generality/metric_generality.csv", "3.2"),
    ("M2", "The axis ordering is stable across tolerances", "196_v17_metric_generality", "step17_metric_generality/tolerance_sweep.csv", "3.2"),
    ("M3", "The axis contrast is a separation, not an ordering", "202_v17_robustness", "step22_robustness/auc_contrasts.csv", "3.2"),
    ("M4", "The mechanism is measurable: error scales with the covariate the story names", "200_v17_round4_gaps", "step20_round4/mechanism_gradients.csv", "3.2"),
    ("M5", "The timing side is confirmed on both of its members", "200_v17_round4_gaps", "step20_round4/amplitude_screen.json", "3.2"),
    ("G1-G3", "Action-space ceilings against the reserved panel's resolution", "182_v17_ceiling", "step4_ceiling/gate.json", "2.4"),
    ("H1", "Peak-window overlap dominates outage length for the peak", "183_v17_mechanism", "step5_mechanism/permutation_importance.csv", "3.2"),
    ("H1d-e", "Donor quality, and synchronous anomaly information", "183_v17_mechanism", "step5_mechanism/donor_control_contrasts.csv", "3.2"),
    ("H2", "The screen beats fixed-length screening on reserved networks", "187_v17_confirm", "step10_confirmation/verdict.json", "3.3"),
    ("H2b", "The absolute advantage is regime-dependent", "189_v17_arm_robustness", "step11_arm_robustness/arm_contrasts.csv", "3.4"),
    ("H2d", "The incumbent was not handicapped", "194_v17_baseline_strength", "step15_baseline_strength/baseline_strength.csv", "3.6"),
    ("H2e", "The result is not carried by the largest agencies", "198_v17_weighting", "step19_weighting/weighting.csv", "3.3"),
    ("H3", "Conformal coverage, marginal and by stratum", "187_v17_confirm", "step10_confirmation/coverage.csv", "3.7"),
    ("H3c", "Site-level validity is reachable at a stated price", "197_v17_cluster_conformal", "step18_cluster_conformal/summary.json", "3.7"),
    ("H4a", "Per-year judgements, including the hard subset", "200_v17_round4_gaps", "step20_round4/near_threshold.csv", "3.8"),
    ("H4c", "Abstention beats screening for a threshold call", "200_v17_round4_gaps", "step20_round4/abstain_versus_screen.csv", "3.8"),
    ("H5", "Transfer across agencies", "187_v17_confirm", "step10_confirmation/leave_one_provider_out.csv", "3.9"),
    ("H6-H7", "The axis carries most of the benefit; the simple rule is deployable", "190_v17_ablations, 195_v17_simple_rule", "step12_ablations/ablations.csv", "3.5"),
    ("H8", "No dependence on estimators seeing future years", "191_v17_prior_years", "step13_prior_years/protocol_comparison.csv", "3.10"),
    ("R1", "Reference-series measurement error does not move the result", "202_v17_robustness", "step22_robustness/noise_sensitivity.json", "3.11"),
    ("R2", "The exceedance result is not an artefact of the threshold", "202_v17_robustness", "step22_robustness/threshold_sweep.csv", "3.8"),
    ("HY1", "Catchment attribution: which rivers are hard", "201_v17_hydrology", "step21_hydrology/correlations.csv", "3.12"),
    ("HY2", "Directional tests from the literature, including the groundwater claim", "201_v17_hydrology", "step21_hydrology/verdict.json", "3.12"),
]


def digest(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def main() -> int:
    rows = []
    for claim, statement, script, artifact, section in ENTRIES:
        path = RESULTS_ROOT / artifact
        rows.append(
            {
                "claim": claim,
                "statement": statement,
                "produced_by": f"scripts/{script}.py",
                "artifact": f"results/v17_fitness/{artifact}",
                "sha256_16": digest(path),
                "bytes": int(path.stat().st_size) if path.exists() else 0,
                "manuscript_section": section,
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(LEDGER, index=False)
    missing = frame.loc[frame["sha256_16"].eq("MISSING")]
    print(frame[["claim", "artifact", "sha256_16", "manuscript_section"]].to_string(index=False))
    if not missing.empty:
        print(f"\n{len(missing)} artifacts missing:")
        print(missing[["claim", "artifact"]].to_string(index=False))
        return 1
    print(f"\nledger written: {LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

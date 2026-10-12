#!/usr/bin/env python3
"""Steps 9–10: freeze the end-to-end design, then score reserved unseen years.

Tau and hierarchical predictors are taken from the development freeze. This
script does not retune on candidate_unseen.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    NON_INFERIORITY_EPSILON_C,
    STEP5_THERMAL_DECISION,
    STEP9_E2E_FREEZE,
    STEP10_UNSEEN,
    SUCCESS_CRITERION,
)
from stream_recoverability.experiments.wrr_revision.thermal_decision import (  # noqa: E402
    apply_frozen_year_policy,
    compare_eval_policies,
)


def _verdict(comparison: pd.DataFrame, *, confirmation: bool) -> dict[str, object]:
    if comparison.empty:
        return {"claim": "insufficient_eval", "superior_decision_layer": False}
    simple = comparison.loc[comparison["policy"].eq("always_simple")]
    thermal = comparison.loc[comparison["policy"].isin(["year_thermal_tau", "year_thermal_tau_frozen"])]
    random = comparison.loc[comparison["policy"].eq("random_same_rate")]
    seasonal = comparison.loc[comparison["policy"].eq("simple_length_season")]
    if simple.empty:
        return {"claim": "missing_simple_competitor", "superior_decision_layer": False}
    simple_row = simple.iloc[0]
    if thermal.empty:
        return {
            "claim": "training_mismatch_and_simple_applicability",
            "superior_decision_layer": False,
            "reason": "no calibrated thermal policy scored",
        }
    row = thermal.iloc[0]
    noninferior = bool(row["delta_vs_always_simple"] >= -NON_INFERIORITY_EPSILON_C)
    harm_reduced = bool(row["harm_reduced"] == 1.0)
    beats_random = True
    if not random.empty:
        beats_random = bool(row["harm_rate"] < random.iloc[0]["harm_rate"])
    seasonal_noninferior = False
    beats_seasonal = True
    if not seasonal.empty:
        seasonal_noninferior = bool(seasonal.iloc[0]["delta_vs_always_simple"] >= -NON_INFERIORITY_EPSILON_C)
        # A near-zero-adopt length/season rule can post a lower harm rate by
        # not reconstructing. It matches the risk-control package only if it
        # also stays within epsilon of the simple competitor.
        beats_seasonal = (not seasonal_noninferior) or bool(row["harm_rate"] < seasonal.iloc[0]["harm_rate"])
    mean_beats = bool(row["beats_simple_mean"] == 1.0)
    if mean_beats:
        claim = "mean_benefit_superiority"
        flags_pass = True
    elif noninferior and harm_reduced and beats_random and beats_seasonal:
        claim = "risk_control"
        flags_pass = True
    else:
        claim = "training_mismatch_and_simple_applicability"
        flags_pass = False
    superior = bool(confirmation and flags_pass)
    return {
        "claim": claim if confirmation else "pending_unseen_confirmation",
        "panel_claim": claim,
        "superior_decision_layer": superior,
        "confirmation_panel": confirmation,
        "noninferior_eps_0_05": noninferior,
        "harm_reduced_vs_simple": harm_reduced,
        "harm_beats_random": beats_random,
        "harm_beats_length_season": beats_seasonal,
        "length_season_noninferior": seasonal_noninferior,
        "mean_beats_simple": mean_beats,
        "simple_network_equal_Bq": float(simple_row["network_equal_Bq"]),
        "policy_network_equal_Bq": float(row["network_equal_Bq"]),
        "delta_vs_simple": float(row["delta_vs_always_simple"]),
        "policy_harm_rate": float(row["harm_rate"]),
        "simple_harm_rate": float(simple_row["harm_rate"]),
        "mean_abs_default_error": float(row["mean_abs_default_error"]),
        "mean_abs_policy_error": float(row["mean_abs_policy_error"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev-dir", default=str(STEP5_THERMAL_DECISION))
    parser.add_argument("--unseen-dir", default=str(STEP10_UNSEEN))
    parser.add_argument("--skip-unseen", action="store_true")
    args = parser.parse_args()
    dev = Path(args.dev_dir)
    comparison = pd.read_csv(dev / "eval_policy_comparison.csv")
    freeze_tau = json.loads((dev / "tau_freeze.json").read_text())
    criterion = json.loads(SUCCESS_CRITERION.read_text()) if SUCCESS_CRITERION.exists() else {}
    STEP9_E2E_FREEZE.mkdir(parents=True, exist_ok=True)
    design = {
        "recoverer": "information_conditioned_simple",
        "default": "doy_climatology",
        "diagnostics": ["donors_present", "right_present", "air_present", "gap_length", "mean_donor_corr"],
        "calibration": freeze_tau,
        "failure_criteria": {
            "harm": "Bq < 0 versus climatology",
            "severe_underestimate_C": 1.0,
        },
        "weights": "network-equal mean of station-year complete-year Bq; reused masks in one year are one observation",
        "full_default_legal": True,
        "no_reconstruction_budget": True,
        "development_verdict": _verdict(comparison, confirmation=False),
        "success_criterion": criterion,
        "opened_panels_not_unseen": True,
        "deployable_until_unseen": "information_conditioned_simple",
    }
    (STEP9_E2E_FREEZE / "DESIGN_FREEZE.json").write_text(json.dumps(design, indent=2, default=str))
    comparison.to_csv(STEP9_E2E_FREEZE / "development_eval_policy_comparison.csv", index=False)
    (STEP9_E2E_FREEZE / "summary.json").write_text(json.dumps(design["development_verdict"], indent=2))
    print(json.dumps(design["development_verdict"], indent=2))
    if args.skip_unseen:
        return
    unseen_path = Path(args.unseen_dir) / "year_policies_raw.csv"
    if not unseen_path.exists():
        print(f"unseen raw table missing at {unseen_path}; run 173 --evidence-use candidate_unseen first")
        return
    unseen = pd.read_csv(unseen_path)
    history = pd.read_csv(dev / "year_policies.csv")
    scored = apply_frozen_year_policy(unseen, freeze_tau, history=history)
    scored.to_csv(Path(args.unseen_dir) / "year_policies.csv", index=False)
    unseen_cmp = compare_eval_policies(scored)
    unseen_cmp.to_csv(Path(args.unseen_dir) / "eval_policy_comparison.csv", index=False)
    verdict = _verdict(unseen_cmp, confirmation=True)
    verdict["panel"] = "candidate_unseen"
    (Path(args.unseen_dir) / "summary.json").write_text(json.dumps(verdict, indent=2))
    design["confirmation_verdict"] = verdict
    design["superior_decision_layer"] = bool(verdict.get("superior_decision_layer"))
    design["paper_claim"] = verdict.get("claim")
    design["deployable"] = (
        "information_conditioned_simple"
        if not verdict.get("superior_decision_layer")
        else "year_thermal_tau_overlay"
    )
    (STEP9_E2E_FREEZE / "DESIGN_FREEZE.json").write_text(json.dumps(design, indent=2, default=str))
    (STEP9_E2E_FREEZE / "summary.json").write_text(json.dumps({"development": design["development_verdict"], "confirmation": verdict}, indent=2))
    print("unseen", json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()

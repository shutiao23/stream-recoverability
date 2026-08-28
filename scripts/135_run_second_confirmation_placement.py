#!/usr/bin/env python3
"""Run the frozen placement policies on eligible second-confirmation networks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (
    read_temperature_panel,
)
from stream_recoverability.experiments.empirical_placement import (
    pairwise_replay_losses,
    placement_replay_curve,
    training_correlation,
)
from stream_recoverability.experiments.second_confirmation_guard import (
    sha256_file,
    validate_canonical_authorization,
    validate_scored_result_gate,
)

SECOND = ROOT / "results/development_v11/second_confirmation"
SCORING = SECOND / "scoring"


def _panel_path(network_id: str) -> Path:
    second = SECOND / "daily_qc/networks" / network_id / "daily_wide_temperature.csv"
    if second.is_file():
        return second
    first = (
        ROOT
        / "results/development_v11/confirmation_daily_qc/networks"
        / network_id
        / "daily_wide_temperature.csv"
    )
    if first.is_file():
        return first
    raise FileNotFoundError(f"frozen qualified panel absent: {network_id}")


def main() -> None:
    scoring_summary = json.loads((SCORING / "summary.json").read_text(encoding="utf-8"))
    validate_scored_result_gate(scoring_summary)
    readiness_path = SECOND / "readiness.json"
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    validate_canonical_authorization(
        readiness,
        readiness_path=readiness_path,
        canonical_readiness_path=readiness_path,
        root=ROOT,
    )
    placements = pd.read_csv(
        SCORING / "placement_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )
    simple = pd.read_csv(
        SCORING / "simple_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    )
    counts = simple.groupby("network_id")["station_id"].nunique()
    eligible = tuple(sorted(counts.loc[counts.ge(5)].index.astype(str)))
    pairwise_parts = []
    curve_parts = []
    attrition = []
    for ordinal, network in enumerate(eligible, start=1):
        panel = read_temperature_panel(str(_panel_path(network)))
        pairwise = pairwise_replay_losses(network, panel, placements, gap_length=90)
        if pairwise.empty:
            attrition.append(
                {"network_id": network, "reason": "empty_pairwise_replay_matrix"}
            )
            continue
        try:
            curve = placement_replay_curve(
                pairwise, training_correlation(panel), random_repeats=100, seed=0
            )
        except ValueError:
            attrition.append(
                {
                    "network_id": network,
                    "reason": "fewer_than_five_stations_in_complete_pairwise_matrix",
                }
            )
            continue
        pairwise_parts.append(pairwise)
        curve.insert(0, "network_id", network)
        curve_parts.append(curve)
        print(f"second placement {ordinal}/{len(eligible)}: {network}", flush=True)
    pairwise_result = (
        pd.concat(pairwise_parts, ignore_index=True)
        if pairwise_parts
        else pd.DataFrame()
    )
    replay = (
        pd.concat(curve_parts, ignore_index=True) if curve_parts else pd.DataFrame()
    )
    policy = (
        replay.groupby("policy", as_index=False).agg(
            mean_regret=("regret", "mean"),
            median_regret=("regret", "median"),
            mean_worst_target_mae=("worst_target_mae", "mean"),
            n_network_budget_rows=("network_id", "size"),
        )
        if not replay.empty
        else pd.DataFrame()
    )
    random_mean = (
        float(policy.loc[policy["policy"].eq("random"), "mean_regret"].iloc[0])
        if not policy.empty and policy["policy"].eq("random").any()
        else float("nan")
    )
    minimax_mean = (
        float(
            policy.loc[policy["policy"].eq("simple_risk_minimax"), "mean_regret"].iloc[
                0
            ]
        )
        if not policy.empty and policy["policy"].eq("simple_risk_minimax").any()
        else float("nan")
    )
    summary = {
        "evidence_role": "independent_second_confirmation_placement_replay",
        "selection": "all_scored_networks_with_at_least_five_target_stations",
        "gap_length": 90,
        "attempted_networks": len(eligible),
        "scored_complete_matrix_networks": int(replay["network_id"].nunique())
        if not replay.empty
        else 0,
        "attrited_networks": len(attrition),
        "policies_frozen_before_outcomes": [
            "simple_risk_minimax",
            "greedy_mutual_information",
            "qr_pivot",
            "distance_even",
            "random",
            "oracle_for_regret_only",
        ],
        "simple_minimax_mean_regret": minimax_mean,
        "random_mean_regret": random_mean,
        "simple_minimax_improvement_over_random": random_mean - minimax_mean,
        "simple_minimax_relative_regret_reduction_vs_random": (
            float((random_mean - minimax_mean) / random_mean)
            if np.isfinite(random_mean) and random_mean != 0
            else float("nan")
        ),
        "directional_improvement_observed": bool(
            np.isfinite(minimax_mean) and minimax_mean < random_mean
        ),
        "preregistered_margin_or_significance_threshold": False,
        "confirmatory_utility_claim_licensed": False,
        "endpoint_status": "directionally_lower_regret_no_preregistered_margin",
        "input_bindings": {
            "placement_losses_sha256": sha256_file(SCORING / "placement_losses.csv"),
            "frozen_roster_sha256": sha256_file(
                SECOND / "frozen_scoring_roster_v2.csv"
            ),
            "authorization_amendment_sha256": sha256_file(
                ROOT / "configs/route_a_second_confirmation_amendment_v2.yaml"
            ),
        },
    }
    pairwise_result.to_csv(SCORING / "placement_pairwise_losses.csv", index=False)
    replay.to_csv(SCORING / "placement_replay_curve.csv", index=False)
    policy.to_csv(SCORING / "placement_policy_summary.csv", index=False)
    pd.DataFrame(attrition, columns=["network_id", "reason"]).to_csv(
        SCORING / "placement_attrition.csv", index=False
    )
    (SCORING / "placement_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

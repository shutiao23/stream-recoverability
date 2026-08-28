#!/usr/bin/env python3
"""Combine the completed v11 development, confirmation, and decision evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/development_v11"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    development = read_json(RESULTS / "summary.json")
    confirmation = read_json(RESULTS / "route_a_confirmation/summary.json")
    triage = read_json(RESULTS / "route_a_confirmation/triage.json")
    mixed = read_json(RESULTS / "mixed_model_increment.json")
    confirmation_bootstrap = pd.read_csv(
        RESULTS / "route_a_confirmation/network_bootstrap.csv"
    )
    candidate_qc = pd.read_csv(RESULTS / "confirmation_qc_summary.csv")
    qualified = candidate_qc.loc[candidate_qc["qc_status"].eq("qualified")]
    reviewer_path = RESULTS / "reviewer_completion/summary.json"
    reviewer_completion = read_json(reviewer_path) if reviewer_path.is_file() else None
    result = {
        "study": "development_v11_route_a",
        "development": development,
        "mixed_model_increment": mixed,
        "recruited_candidates": int(len(candidate_qc)),
        "qualified_stream_candidates": int(len(qualified)),
        "qualified_by_provider": qualified.groupby("provider").size().to_dict(),
        "confirmation": confirmation,
        "confirmation_network_bootstrap": confirmation_bootstrap.to_dict(
            orient="records"
        ),
        "triage": triage,
        "hypothesis_results": {
            "route_b_operator_advancement": False,
            "route_a_rank_transport": True,
            "route_a_calibration_and_coverage": False,
            "route_a_decision_utility": False,
        },
        "reviewer_completion": reviewer_completion,
        "supported_claim": (
            "Fitting-period empirical error curves are the strongest tested "
            "predictor of later recovery loss. Simple structural descriptors "
            "provide coarse within-network ordering, while analytic covariance "
            "adds little and operational calibration remains domain dependent."
            if reviewer_completion is not None
            else "Simple pre-fit descriptors rank recovery loss on new networks, "
            "but magnitude calibration, whole-network coverage, and safe-fill "
            "triage do not transport reliably."
        ),
    }
    (RESULTS / "final_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["hypothesis_results"], indent=2))


if __name__ == "__main__":
    main()

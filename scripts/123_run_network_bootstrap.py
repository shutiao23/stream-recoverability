#!/usr/bin/env python3
"""Write network-cluster bootstrap intervals for Route A development and confirmation."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.route_a_confirmation import (
    network_bootstrap_intervals,
)

RESULTS = ROOT / "results/development_v11"


def main() -> None:
    development = pd.read_csv(RESULTS / "nested_lono_predictions.csv").rename(
        columns={
            "simple_prediction": "predicted_loss",
            "simple_prediction_lower": "prediction_lower",
            "simple_prediction_upper": "prediction_upper",
        }
    )
    confirmation = pd.read_csv(RESULTS / "route_a_confirmation/predictions.csv")
    network_bootstrap_intervals(development).to_csv(
        RESULTS / "development_network_bootstrap.csv", index=False
    )
    network_bootstrap_intervals(confirmation).to_csv(
        RESULTS / "route_a_confirmation/network_bootstrap.csv", index=False
    )


if __name__ == "__main__":
    main()

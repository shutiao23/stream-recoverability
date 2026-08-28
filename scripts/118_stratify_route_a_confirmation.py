#!/usr/bin/env python3
"""Add provider, geographic-domain, and thermal-state confirmation summaries."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (
    read_temperature_panel,
)
from stream_recoverability.experiments.route_a_confirmation import (
    grouped_confirmation_metrics,
    thermal_state_changes,
)

OUTPUT = ROOT / "results/development_v11/route_a_confirmation"
NETWORK_ROOT = ROOT / "results/development_v11/confirmation_daily_qc/networks"


def main() -> None:
    qualified = pd.read_csv(OUTPUT / "qualified_panel.csv")
    predictions = pd.read_csv(OUTPUT / "predictions.csv", dtype={"station_id": str})
    predictions["station_id"] = predictions["station_id"].astype(str)
    state_columns = [
        "training_thermal_range",
        "evaluation_thermal_range",
        "thermal_range_relative_change",
        "training_acf30",
        "evaluation_acf30",
        "acf30_change",
        "thermal_state_shift",
    ]
    predictions = predictions.drop(
        columns=[
            column
            for column in ("provider", "domain", "domain_group", *state_columns)
            if column in predictions
        ]
    )
    provider = qualified[["network_id", "provider", "domain"]]
    predictions = predictions.merge(provider, on="network_id")
    predictions["domain_group"] = np.where(
        predictions["domain"].eq("united_states"), "united_states", "cross_domain"
    )
    states = pd.concat(
        [
            thermal_state_changes(
                network,
                read_temperature_panel(
                    str(NETWORK_ROOT / network / "daily_wide_temperature.csv")
                ),
                target_stations=tuple(
                    predictions.loc[
                        predictions["network_id"].eq(network), "station_id"
                    ].unique()
                ),
            )
            for network in predictions["network_id"].unique()
        ],
        ignore_index=True,
    )
    states["station_id"] = states["station_id"].astype(str)
    predictions = predictions.merge(states, on=["network_id", "station_id"])
    predictions.to_csv(OUTPUT / "predictions.csv", index=False)
    states.to_csv(OUTPUT / "thermal_state_changes.csv", index=False)
    provider_metrics = grouped_confirmation_metrics(
        predictions, group_column="provider"
    )
    domain_metrics = grouped_confirmation_metrics(
        predictions, group_column="domain_group"
    )
    state_metrics = grouped_confirmation_metrics(
        predictions, group_column="thermal_state_shift"
    )
    provider_metrics.to_csv(OUTPUT / "provider_metrics.csv", index=False)
    domain_metrics.to_csv(OUTPUT / "domain_metrics.csv", index=False)
    state_metrics.to_csv(OUTPUT / "thermal_state_metrics.csv", index=False)
    summary = json.loads((OUTPUT / "summary.json").read_text(encoding="utf-8"))
    summary["domain_metrics"] = domain_metrics.to_dict(orient="records")
    summary["thermal_state_metrics"] = state_metrics.to_dict(orient="records")
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()

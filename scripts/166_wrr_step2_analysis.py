#!/usr/bin/env python3
"""Summarise Step-2 fair recovery and write DESIGN_FREEZE.json when complete."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    FIRST_PLACEMENTS,
    RESULTS_ROOT,
)

STEP2 = RESULTS_ROOT / "step2_fair_recovery"
OUT = STEP2 / "ANALYSIS.md"
FREEZE = RESULTS_ROOT / "DESIGN_FREEZE.json"


def main() -> None:
    placements = pd.read_csv(STEP2 / "placement_scores.csv")
    duration = pd.read_csv(STEP2 / "duration_summary.csv")
    crossing = pd.read_csv(STEP2 / "crossing_days.csv")
    expected = set(
        pd.read_csv(FIRST_PLACEMENTS, usecols=["network_id"])["network_id"].astype(str)
    )
    have = set(placements["network_id"].astype(str))
    complete = expected <= have
    lines = [
        "# Step 2 analysis",
        "",
        f"- networks scored: {len(have)} / {len(expected)}",
        f"- missing: {', '.join(sorted(expected - have)) or 'none'}",
        f"- stations: {placements['station_id'].nunique()}",
        f"- rows: {len(placements)}",
        "",
        "## Mean MAE benefit by duration (same-information recoverers)",
        "",
        duration.loc[
            duration["information_group"].ne("external"),
            ["recoverer", "gap_length", "n_placements", "benefit_mean", "harmful_rate", "hottest_30_benefit"],
        ]
        .to_string(index=False),
        "",
        "## Fraction of stations with an observed MAE-benefit crossing",
        "",
        crossing.groupby("recoverer")
        .agg(
            n_stations=("station_id", "size"),
            frac_crossed=("crossed", "mean"),
            n_right_censored=("censoring", lambda s: float((s == "right_censored").mean())),
        )
        .to_string(),
        "",
    ]
    # Did neighbor boundary uniquely create the long-gap collapse?
    long = duration.loc[duration["gap_length"].ge(180)]
    pivot = long.pivot_table(
        index="gap_length", columns="recoverer", values="benefit_mean", aggfunc="mean"
    )
    lines.extend(["## Long-gap mean benefit", "", pivot.to_string(), ""])
    neighbor_long = float(
        duration.loc[
            duration["recoverer"].eq("xgb_neighbor_boundary") & duration["gap_length"].eq(180),
            "benefit_mean",
        ].mean()
    )
    longblock_long = float(
        duration.loc[
            duration["recoverer"].eq("xgb_longblock_boundary") & duration["gap_length"].eq(180),
            "benefit_mean",
        ].mean()
    )
    donor_long = float(
        duration.loc[
            duration["recoverer"].eq("donor_only_ridge") & duration["gap_length"].eq(180),
            "benefit_mean",
        ].mean()
    )
    withdraw_law = (neighbor_long < 0) and (longblock_long > 0 or donor_long > 0)
    chosen = (
        "xgb_longblock_boundary"
        if longblock_long >= donor_long
        else "donor_only_ridge"
    )
    lines.extend(
        [
            f"- xgb_neighbor_boundary @180d benefit: {neighbor_long:.3f}",
            f"- xgb_longblock_boundary @180d benefit: {longblock_long:.3f}",
            f"- donor_only_ridge @180d benefit: {donor_long:.3f}",
            f"- withdraw universal threshold law: {withdraw_law}",
            f"- development recoverer if freeze now: {chosen}",
            "",
        ]
    )
    OUT.write_text("\n".join(map(str, lines)))
    if complete:
        freeze = {
            "frozen": True,
            "development_panel": "first_42",
            "confirmation_panel": "held_out_qc_not_in_first_or_second",
            "default": "doy_climatology",
            "recoverer": chosen,
            "primary_endpoint": "hottest_30_benefit_on_station_year",
            "secondary_endpoint": "exceed_days_20_benefit",
            "mae_is_diagnostic": True,
            "action_rule": "adopt if predicted_benefit > tau and supported else default",
            "tau_selection": "max net benefit on historical validation vs all-default",
            "unsupported": "reject_to_default",
            "budget": "optional_cap_not_required_to_fill",
            "withdraw_universal_law": withdraw_law,
            "n_development_networks": int(len(have)),
        }
        FREEZE.write_text(json.dumps(freeze, indent=2))
    print(OUT)
    print("complete", complete, "withdraw_law", withdraw_law, "chosen", chosen)


if __name__ == "__main__":
    main()

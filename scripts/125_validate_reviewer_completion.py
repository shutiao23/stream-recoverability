#!/usr/bin/env python3
"""Validate reviewer-completion artifacts and manuscript/result agreement."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/development_v11/reviewer_completion"


def main() -> None:
    summary = json.loads((OUTPUT / "summary.json").read_text(encoding="utf-8"))
    manuscript = (ROOT / "paper/development_v11/manuscript.md").read_text(
        encoding="utf-8"
    )
    references = (ROOT / "paper/references.bib").read_text(encoding="utf-8")
    protocol = yaml.safe_load(
        (ROOT / "configs/route_a_second_confirmation_protocol.yaml").read_text(
            encoding="utf-8"
        )
    )

    empirical = {
        (item["phase"], item["scope"]): item for item in summary["empirical_transfer"]
    }
    supported = empirical[("confirmation", "supported_only")]
    all_cells = empirical[("confirmation", "all_cells_with_network_mean_fallback")]
    assert supported["n"] == 780
    assert round(supported["spearman"], 3) == 0.934
    assert round(supported["r2"], 3) == 0.812
    assert all_cells["n"] == 1440
    assert round(all_cells["spearman"], 3) == 0.633
    assert "0.934" in manuscript and "0.812" in manuscript
    assert "0.0171" in manuscript
    assert "3.247" in manuscript
    assert "second independent confirmation" in manuscript

    roster = pd.read_csv(OUTPUT / "model_roster_metrics.csv")
    assert set(roster["model_family"]) == {
        "seasonal_boundary_ridge",
        "donor_blup_ridge",
        "xgboost_b_d",
    }
    replay = pd.read_csv(OUTPUT / "placement_replay_curve.csv")
    assert replay["independent_realized_outcomes"].all()
    assert replay["network_id"].nunique() >= 14
    assert replay.loc[replay["policy"].eq("oracle"), "regret"].eq(0).all()

    for figure in range(1, 6):
        matches = list(OUTPUT.glob(f"figure_0{figure}_*.png"))
        assert len(matches) == 1 and matches[0].stat().st_size > 10_000

    for key in (
        "caselton1984monitoring",
        "krause2008sensor",
        "pardo1998gauges",
        "alfonso2012voi",
        "oh2025sensors",
        "moffat2007gap",
        "richardson2007longgaps",
        "denhertog2006kriging",
        "yamamoto2000kriging",
        "auer2024uncertainty",
    ):
        assert f"{{{key}," in references
        assert f"@{key}" in manuscript

    for term in ("authorization consumed", "burned", "stop-loss", "BL-016"):
        assert term.lower() not in manuscript.lower()

    assert protocol["minimum_valid_scored_networks"] == 40
    assert protocol["target_scored_networks"] == [60, 80]
    assert (
        protocol["evidence_separation"]["first_confirmation_networks_reusable"] is False
    )
    assert summary["second_confirmation"]["scoring_status"] == "authorized_not_run"
    print("reviewer completion validation passed")


if __name__ == "__main__":
    main()

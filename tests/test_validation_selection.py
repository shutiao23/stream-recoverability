from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.experiments.selection import (
    assess_proposed_go_no_go,
    select_stage2_finalists,
)
from stream_recoverability.experiments.validation import (
    VALIDATION_DEEP_SEEDS,
    VALIDATION_MASK_SEEDS,
    VALIDATION_STATIONS,
    VALIDATION_STRATA,
)


def test_stage2_finalists_apply_tolerance_mandatory_and_diagnostic_rules() -> None:
    ranking = pd.DataFrame(
        {
            "model": ["brits_ref", "saits_ref", "csdi", "proposed"],
            "validation_stage": ["deep_single_seed"] * 4,
            "mean_skill_across_strata": [0.30, 0.27, 0.10, 0.05],
        }
    )
    diagnostics = pd.DataFrame(
        {
            "model": ranking["model"],
            "finite_predictions": [True, True, True, True],
            "finite_validation_score": [True, False, True, True],
            "best_epoch": [4, 3, 5, 2],
            "epochs_run": [10, 10, 10, 10],
        }
    )

    selected = select_stage2_finalists(ranking, diagnostics=diagnostics)
    indexed = selected.set_index("model")
    assert indexed.loc["brits_ref", "selected_for_stability"]
    assert not indexed.loc["saits_ref", "selected_for_stability"]
    assert indexed.loc["csdi", "selected_for_stability"]
    assert indexed.loc["proposed", "selected_for_stability"]
    assert indexed.loc["csdi", "mandatory_diagnostic_candidate"]
    assert "failed diagnostics" in indexed.loc["saits_ref", "selection_reason"]


def test_stage2_diagnostic_booleans_are_parsed_strictly() -> None:
    ranking = pd.DataFrame(
        {
            "model": ["brits_ref", "saits_ref", "csdi", "proposed"],
            "validation_stage": ["deep_single_seed"] * 4,
            "mean_skill_across_strata": [0.30, 0.29, 0.28, 0.27],
        }
    )
    diagnostics = pd.DataFrame(
        {
            "model": ranking["model"],
            "finite_predictions": ["True", "False", "1", "0"],
            "finite_validation_score": ["true", "true", "1", "1"],
            "best_epoch": [1, 1, 1, 1],
            "epochs_run": [2, 2, 2, 2],
        }
    )
    selected = select_stage2_finalists(ranking, diagnostics=diagnostics).set_index(
        "model"
    )
    assert bool(selected.loc["brits_ref", "diagnostic_pass"])
    assert not bool(selected.loc["saits_ref", "diagnostic_pass"])
    assert bool(selected.loc["csdi", "diagnostic_pass"])
    assert not bool(selected.loc["proposed", "diagnostic_pass"])

    diagnostics.loc[0, "finite_predictions"] = "not-a-boolean"
    with pytest.raises(ValueError, match="strict boolean"):
        select_stage2_finalists(ranking, diagnostics=diagnostics)


def _condition_id(station: str, stratum: str) -> str:
    if stratum == "point_30pct":
        return f"VAL-PNT-{station}-T-P30"
    if stratum.startswith("t_block_"):
        days = int(stratum.removeprefix("t_block_").removesuffix("d"))
        return f"VAL-BLK1-{station}-T-D{days:03d}"
    if stratum == "tfl_block_90d":
        return f"VAL-BLK1-{station}-TFL-D090"
    return f"VAL-SITE-{station}-HYDROONLY-D090"


def _validation_events(*, proposed_gain: float = 0.03) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for station in VALIDATION_STATIONS:
        for stratum in VALIDATION_STRATA:
            condition_id = _condition_id(station, stratum)
            for mask_seed in VALIDATION_MASK_SEEDS:
                common = {
                    "condition_id": condition_id,
                    "scenario_id": f"{condition_id}-R{mask_seed:04d}",
                    "mask_seed": mask_seed,
                    "station_id": station,
                    "target": "T",
                    "evaluation_split": "validation",
                    "data_version": "published_v1",
                    "design_hash": "d" * 64,
                }
                rows.append(
                    {
                        **common,
                        "model": "linear",
                        "training_seed": np.nan,
                        "skill": 0.20,
                        "coverage_90": np.nan,
                    }
                )
                for seed in VALIDATION_DEEP_SEEDS:
                    rows.append(
                        {
                            **common,
                            "model": "proposed",
                            "training_seed": seed,
                            "skill": 0.20 + proposed_gain,
                            "coverage_90": 0.90,
                        }
                    )
    return pd.DataFrame(rows)


def _ablations(*, useful: bool = True) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    combinations = (
        "S0+A+B+C+D",
        "S0+B+C+D",
        "S0+A+C+D",
        "S0+A+B+D",
        "S0+A+B+C",
    )
    for seed in VALIDATION_DEEP_SEEDS:
        for station in VALIDATION_STATIONS:
            for mask_seed in VALIDATION_MASK_SEEDS:
                for gap in (10, 90, 180):
                    for combination in combinations:
                        mae = 1.0
                        if useful and gap == 10 and combination == "S0+B+C+D":
                            mae = 1.1
                        if useful and gap >= 90 and combination == "S0+A+C+D":
                            mae = 1.05
                        rows.append(
                            {
                                "training_seed": seed,
                                "station_id": station,
                                "mask_seed": mask_seed,
                                "gap_length": gap,
                                "information_combination": combination,
                                "MAE": mae,
                                "attribution_estimand": "operational_dropout",
                            }
                        )
    return pd.DataFrame(rows)


def test_proposed_go_no_go_passes_only_when_every_frozen_criterion_passes() -> None:
    decision = assess_proposed_go_no_go(
        _validation_events(),
        _ablations(),
        best_traditional_model="linear",
    )

    assert decision.passed
    assert decision.best_traditional_model == "linear"
    assert decision.criteria["passed"].all()
    assert decision.evidence["positive_station_count"] == 3
    assert set(decision.evidence["seed_90_day_skill_gains"]) == {"11", "22", "33"}

    failed = assess_proposed_go_no_go(
        _validation_events(proposed_gain=0.01),
        _ablations(useful=False),
        best_traditional_model="linear",
    )
    assert not failed.passed
    failed_criteria = set(failed.criteria.loc[~failed.criteria["passed"], "criterion"])
    assert {
        "stable_90_day_gain",
        "difficult_case_gain",
        "short_gap_A_ablation",
        "long_gap_nonlocal_ablation",
    }.issubset(failed_criteria)

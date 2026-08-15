from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from stream_recoverability.experiments.validation import (
    DEEP_CANDIDATES,
    TRADITIONAL_CANDIDATES,
    VALIDATION_DEEP_SEEDS,
    VALIDATION_MASK_SEEDS,
    VALIDATION_STATIONS,
    VALIDATION_STRATA,
    build_validation_funnel,
    rank_validation_models,
    select_validation_stage,
    validation_condition_stratum,
    write_validation_model_ranking,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "study_manifest.yaml"
CONFIG = PROJECT_ROOT / "configs/experiments.yaml"


def test_validation_funnel_has_frozen_counts_labels_and_mask_units() -> None:
    funnel = build_validation_funnel(
        MANIFEST,
        CONFIG,
        data_version="no_s2_suspect_v1",
    )

    assert funnel.grid.suite == "validation_funnel"
    assert funnel.grid.mask_seeds == VALIDATION_MASK_SEEDS
    assert funnel.grid.training_seeds == VALIDATION_DEEP_SEEDS
    assert len(funnel.grid.conditions) == 21
    assert len(funnel.grid.scenarios) == 105
    assert len(funnel.mask_units) == 105
    assert not funnel.formal_evidence
    assert funnel.evidence_role == "model_selection_only"

    by_station = Counter(
        condition.station_ids[0] for condition in funnel.grid.conditions
    )
    assert by_station == Counter({station: 7 for station in VALIDATION_STATIONS})
    by_stratum = Counter(
        validation_condition_stratum(condition.condition_id)
        for condition in funnel.grid.conditions
    )
    assert by_stratum == Counter({stratum: 3 for stratum in VALIDATION_STRATA})
    assert all(
        condition.data_version == "no_s2_suspect_v1"
        and condition.evaluation_split == "validation"
        and condition.validation_scope == "internal_validation_model_selection_only"
        and condition.evaluation_variables == ("T",)
        for condition in funnel.grid.conditions
    )

    units_per_condition = Counter(unit.condition_id for unit in funnel.mask_units)
    assert set(units_per_condition.values()) == {5}
    assert len({unit.mask_unit_id for unit in funnel.mask_units}) == 105
    assert {unit.mask_seed_placeholder for unit in funnel.mask_units} == set(
        VALIDATION_MASK_SEEDS
    )
    assert all(
        unit.anchor_id
        and unit.center_date
        and unit.center_index >= 0
        and unit.anchor_data_version == "published_v1"
        and unit.anchor_evaluation_split == "validation"
        and unit.anchor_status == "bound_centered_anchor_v1"
        and unit.scenario_id.endswith(
            f"-R{unit.mask_seed_placeholder:04d}"
        )
        for unit in funnel.mask_units
    )
    assert all(
        "NO_S2_SUSPECT_V1-VALIDATION" in scenario.scenario_id
        for scenario in funnel.grid.scenarios
    )

    unit_frame = funnel.mask_unit_frame()
    assert unit_frame["data_version"].eq("no_s2_suspect_v1").all()
    assert unit_frame["evaluation_split"].eq("validation").all()
    assert unit_frame["evidence_role"].eq("model_selection_only").all()
    assert not unit_frame["formal_evidence"].any()


def test_validation_stages_freeze_candidates_seeds_and_finalist_gate() -> None:
    funnel = build_validation_funnel(MANIFEST, CONFIG)

    traditional, traditional_models = select_validation_stage(
        funnel, "traditional"
    )
    assert traditional.training_seeds == ()
    assert traditional_models == TRADITIONAL_CANDIDATES

    deep_single, deep_models = select_validation_stage(
        funnel, "deep_single_seed"
    )
    assert deep_single.training_seeds == (11,)
    assert deep_models == DEEP_CANDIDATES

    with pytest.raises(ValueError, match="explicit stage-2 finalist"):
        select_validation_stage(funnel, "deep_stability")
    deep_stability, finalists = select_validation_stage(
        funnel,
        "deep_stability",
        models=("proposed", "csdi", "proposed"),
    )
    assert deep_stability.training_seeds == (11, 22, 33)
    assert finalists == ("proposed", "csdi")

    with pytest.raises(ValueError, match="not candidates"):
        select_validation_stage(
            funnel, "deep_single_seed", models=("brits",)
        )


def _ranking_events() -> pd.DataFrame:
    funnel = build_validation_funnel(MANIFEST, CONFIG)
    rows = []
    for scenario in funnel.grid.scenarios:
        stratum = validation_condition_stratum(scenario.condition.condition_id)
        linear_skill = 0.20
        if stratum == "hydro_station_outage_90d":
            linear_skill = -0.20
        elif stratum in {"t_block_90d", "t_block_180d", "tfl_block_90d"}:
            linear_skill = 0.05
        rows.append(
            {
                "condition_id": scenario.condition.condition_id,
                "scenario_id": scenario.scenario_id,
                "model": "linear",
                "training_seed": None,
                "mask_seed": scenario.mask_seed,
                "station_id": scenario.condition.station_ids[0],
                "target": "T",
                "skill": linear_skill,
                "evaluation_split": "validation",
                "data_version": "published_v1",
                "design_hash": "frozen-design-hash",
            }
        )
        for training_seed in VALIDATION_DEEP_SEEDS:
            proposed_skill = 0.45
            if stratum == "hydro_station_outage_90d":
                proposed_skill = 0.15
            elif stratum in {
                "t_block_90d",
                "t_block_180d",
                "tfl_block_90d",
            }:
                proposed_skill = 0.30
            if (
                scenario.condition.condition_id == "VAL-PNT-B1-T-P30"
                and scenario.mask_seed == 101
            ):
                proposed_skill = -0.05
            rows.append(
                {
                    "condition_id": scenario.condition.condition_id,
                    "scenario_id": scenario.scenario_id,
                    "model": "proposed",
                    "training_seed": training_seed,
                    "mask_seed": scenario.mask_seed,
                    "station_id": scenario.condition.station_ids[0],
                    "target": "T",
                    "skill": proposed_skill,
                    "evaluation_split": "validation",
                    "data_version": "published_v1",
                    "design_hash": "frozen-design-hash",
                }
            )
    return pd.DataFrame(rows)


def test_validation_ranking_is_complete_equal_stratum_weighted_and_deterministic(
    tmp_path: Path,
) -> None:
    events = _ranking_events()
    ranking = rank_validation_models(
        events.sample(frac=1.0, random_state=47),
        expected_data_version="published_v1",
        expected_design_hash="frozen-design-hash",
    )

    assert list(ranking["model"]) == ["proposed", "linear"]
    assert list(ranking["rank"]) == [1, 2]
    assert ranking["condition_strata_count"].eq(7).all()
    assert ranking["mask_unit_count"].eq(105).all()
    assert ranking["evaluation_split"].eq("validation").all()
    assert ranking["evidence_role"].eq("model_selection_only").all()
    assert not ranking["formal_evidence"].any()

    proposed = ranking.set_index("model").loc["proposed"]
    linear = ranking.set_index("model").loc["linear"]
    assert proposed["training_seed_count"] == 3
    assert json.loads(proposed["training_seeds"]) == [11, 22, 33]
    assert proposed["negative_skill_count"] == 1
    assert proposed["station_outage_mean_skill"] == pytest.approx(0.15)
    assert linear["training_seed_count"] == 0
    assert linear["negative_skill_count"] == 15
    assert linear["station_outage_mean_skill"] == pytest.approx(-0.20)
    assert (
        proposed["mean_skill_across_strata"]
        > linear["mean_skill_across_strata"]
    )

    output = tmp_path / "validation_model_ranking.csv"
    written = write_validation_model_ranking(
        events,
        output,
        expected_data_version="published_v1",
        expected_design_hash="frozen-design-hash",
    )
    assert output.is_file()
    pdt.assert_frame_equal(pd.read_csv(output), written, check_dtype=False)


def test_validation_ranking_rejects_wrong_labels_and_incomplete_units() -> None:
    events = _ranking_events()
    wrong_split = events.copy()
    wrong_split.loc[wrong_split.index[0], "evaluation_split"] = "test"
    with pytest.raises(ValueError, match="non-validation"):
        rank_validation_models(wrong_split)

    incomplete = events.drop(events.index[0])
    with pytest.raises(ValueError, match="mask placeholders 101..105"):
        rank_validation_models(incomplete)

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.external_validation_uncertainty import (
    EXTERNAL_VALIDATION_MASK_SEEDS,
    EXTERNAL_VALIDATION_SPLIT,
    EXTERNAL_VALIDATION_UNCERTAINTY_ROLE,
    ExternalValidationUncertaintyRunner,
    build_external_validation_uncertainty_grid,
    summarize_external_validation_uncertainty,
)
from stream_recoverability.data.confirmatory import FROZEN_SITE_IDS, FROZEN_VARIABLES
from stream_recoverability.experiments.runner import ExperimentRunner


def test_uncertainty_grid_is_validation_only_and_complete() -> None:
    grid = build_external_validation_uncertainty_grid(training_seeds=(11, 22, 33))

    assert len(grid.conditions) == 15
    assert len(grid.scenarios) == 300
    assert grid.mask_seeds == EXTERNAL_VALIDATION_MASK_SEEDS
    assert {condition.evaluation_split for condition in grid.conditions} == {
        EXTERNAL_VALIDATION_SPLIT
    }
    assert {condition.mask_type for condition in grid.conditions} == {"block"}
    assert {condition.layout for condition in grid.conditions} == {
        "full_information_frontier"
    }
    assert {condition.gap_length for condition in grid.conditions} == {30, 90, 180}
    assert {condition.station_ids[0] for condition in grid.conditions} == set(
        FROZEN_SITE_IDS
    )
    assert "confirmatory" not in {
        condition.evaluation_split for condition in grid.conditions
    }


def test_uncertainty_runner_role_rejects_nonvalidation() -> None:
    assert (
        ExternalValidationUncertaintyRunner._evidence_role("validation")
        == EXTERNAL_VALIDATION_UNCERTAINTY_ROLE
    )
    with pytest.raises(ValueError, match="only permits"):
        ExternalValidationUncertaintyRunner._evidence_role("confirmatory")


def test_uncertainty_runner_reuses_full_information_mask_without_auxiliary_hiding(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    grid = build_external_validation_uncertainty_grid(
        training_seeds=(11,), mask_seeds=tuple(range(101, 121))
    )
    scenario = grid.scenarios[0]
    dates = pd.date_range("2021-01-01", periods=3, freq="D")
    variables = tuple(FROZEN_VARIABLES)
    values = np.ones((3, len(FROZEN_SITE_IDS), len(variables)), dtype=np.float32)
    base_mask = np.zeros_like(values, dtype=bool)
    station_index = FROZEN_SITE_IDS.index(scenario.condition.station_ids[0])
    base_mask[1, station_index, variables.index("T")] = True

    def base_generate(
        _runner: ExperimentRunner, _scenario: Any
    ) -> tuple[np.ndarray, dict[str, Any]]:
        return base_mask.copy(), {"scenario_id": _scenario.scenario_id}

    monkeypatch.setattr(ExperimentRunner, "_generate_mask", base_generate)
    runner = object.__new__(ExternalValidationUncertaintyRunner)
    runner.data = SimpleNamespace(
        dates=dates,
        station_ids=tuple(FROZEN_SITE_IDS),
        variable_names=variables,
        values=values,
        natural_observed=np.ones_like(values, dtype=bool),
        quality_approved=np.ones_like(values, dtype=bool),
    )
    runner.mask_dir = tmp_path / "masks"
    runner._validate_scenario_mask = lambda *_args, **_kwargs: None

    mask, metadata = runner._generate_mask(scenario)

    assert np.array_equal(mask, base_mask)
    assert metadata["information_condition"] == "full_information"
    assert metadata["auxiliary_meteorology_masked_cells"] == 0


def _synthetic_events() -> pd.DataFrame:
    rows = []
    models = ("climatology", "linear")
    for station_index, station in enumerate(FROZEN_SITE_IDS):
        for gap in (30, 90, 180):
            for model_index, model in enumerate(models):
                for seed_index, seed in enumerate(EXTERNAL_VALIDATION_MASK_SEEDS):
                    skill = (
                        0.0
                        if model == "climatology"
                        else (
                            0.2 + station_index * 0.01 + gap / 1000 + seed_index / 100
                        )
                    )
                    rows.append(
                        {
                            "station_id": station,
                            "model": model,
                            "gap_length": gap,
                            "mask_seed": seed,
                            "mask_type": "block",
                            "pattern": "T",
                            "evaluation_split": EXTERNAL_VALIDATION_SPLIT,
                            "evidence_role": EXTERNAL_VALIDATION_UNCERTAINTY_ROLE,
                            "skill": skill,
                            "MAE": 1.0 - skill,
                            "n_evaluated": gap,
                        }
                    )
    return pd.DataFrame(rows)


def test_uncertainty_summary_uses_sample_sd_and_complete_cells() -> None:
    products = summarize_external_validation_uncertainty(
        _synthetic_events(), models=("climatology", "linear")
    )

    assert len(products["seed_cells"]) == 5 * 3 * 2 * 20
    assert len(products["cells"]) == 5 * 3 * 2
    assert products["cells"]["n_mask_seeds"].eq(20).all()
    climatology = products["cells"].loc[products["cells"]["model"].eq("climatology")]
    assert climatology["skill_sd"].eq(0).all()
    linear = products["cells"].loc[products["cells"]["model"].eq("linear")]
    expected = pd.Series(np.arange(20) / 100).std(ddof=1)
    assert np.allclose(linear["skill_sd"], expected)
    assert len(products["envelope"]) == 15
    assert len(products["paired_differences"]) == 4 * 3
    assert products["paired_differences"]["n_mask_seeds"].eq(20).all()


def test_uncertainty_summary_fails_closed_on_missing_seed_cell() -> None:
    with pytest.raises(ValueError, match="inventory is incomplete"):
        summarize_external_validation_uncertainty(
            _synthetic_events().iloc[:-1], models=("climatology", "linear")
        )

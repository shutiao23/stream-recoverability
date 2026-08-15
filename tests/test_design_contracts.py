from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.contracts import (
    build_design_contract,
    canonical_evaluation_split,
)
from stream_recoverability.experiments.grid import build_experiment_grid
from stream_recoverability.experiments.runner import ExperimentRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "study_manifest.yaml"
CONFIG = REPO_ROOT / "configs" / "experiments.yaml"
DESIGN = REPO_ROOT / "configs" / "design_freeze_v1.yaml"
VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "DH")


def _wide(path: Path, *, data_version: str = "published_v1") -> Path:
    dates = pd.date_range("2006-01-01", "2020-12-31", freq="D")
    time = np.arange(len(dates), dtype=float)
    frame = pd.DataFrame(
        {
            "date": dates,
            "split": np.select(
                [dates <= "2015-12-31", dates <= "2017-12-31"],
                ["train", "validation"],
                default="test",
            ),
            "data_version": data_version,
        }
    )
    for offset, station in enumerate(("B1", "S2", "P3")):
        for variable_offset, variable in enumerate(VARIABLES):
            frame[f"{station}_{variable}"] = (
                10.0
                + offset
                + variable_offset / 10.0
                + np.sin(time / (20.0 + variable_offset))
            )
    frame.to_parquet(path, index=False)
    return path


def test_design_hash_changes_with_data_version_and_is_reproducible() -> None:
    first = build_design_contract(
        design_path=DESIGN,
        manifest_path=MANIFEST,
        experiment_config_path=CONFIG,
        data_version="published_v1",
        evaluation_split="validation",
    )
    repeated = build_design_contract(
        design_path=DESIGN,
        manifest_path=MANIFEST,
        experiment_config_path=CONFIG,
        data_version="published_v1",
        evaluation_split="validation",
    )
    changed = build_design_contract(
        design_path=DESIGN,
        manifest_path=MANIFEST,
        experiment_config_path=CONFIG,
        data_version="b1_no_level_v1",
        evaluation_split="validation",
    )
    relative = build_design_contract(
        design_path="configs/design_freeze_v1.yaml",
        manifest_path="study_manifest.yaml",
        experiment_config_path="configs/experiments.yaml",
        data_version="published_v1",
        evaluation_split="validation",
    )

    assert first == repeated
    assert first == relative
    assert first["design_hash"] != changed["design_hash"]
    assert first["mask_schema_version"] == "mask_schema_v2"
    assert first["model_schema_version"] == "model_schema_v2"
    assert first["statistics_schema_version"] == "statistics_schema_v2"


def test_stored_test_alias_is_canonicalised_to_development_test() -> None:
    canonical = build_design_contract(
        design_path=DESIGN,
        manifest_path=MANIFEST,
        experiment_config_path=CONFIG,
        data_version="published_v1",
        evaluation_split="development_test",
    )
    legacy_alias = build_design_contract(
        design_path=DESIGN,
        manifest_path=MANIFEST,
        experiment_config_path=CONFIG,
        data_version="published_v1",
        evaluation_split="test",
    )

    assert canonical_evaluation_split("test") == "development_test"
    assert legacy_alias == canonical


def test_validation_grid_masks_only_validation_and_persists_contract(
    tmp_path: Path,
) -> None:
    wide = _wide(tmp_path / "wide.parquet")
    grid = build_experiment_grid(
        MANIFEST,
        CONFIG,
        suite="smoke",
        data_version="published_v1",
        evaluation_split="validation",
    )
    runner = ExperimentRunner(
        grid,
        wide_path=wide,
        quality_path=None,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        config_path=CONFIG,
        design_path=DESIGN,
        manifest_path=MANIFEST,
        models=("climatology",),
    )
    scenario = grid.scenarios[0]
    mask, metadata = runner._generate_mask(scenario)

    assert "VALIDATION" in scenario.scenario_id
    assert mask[runner.validation_rows].any()
    assert not mask[runner.train_rows].any()
    assert not mask[runner.test_rows].any()
    assert metadata["evaluation_split"] == "validation"
    assert metadata["evidence_role"] == "model_selection_only"
    assert metadata["data_version"] == "published_v1"
    assert metadata["design_hash"] == runner.evidence_contract["design_hash"]

    daily, events = runner.run(max_scenarios=1)
    for frame in (daily, events):
        assert set(frame["evaluation_split"]) == {"validation"}
        assert set(frame["data_version"]) == {"published_v1"}
        assert set(frame["design_hash"]) == {runner.evidence_contract["design_hash"]}


def test_runner_rejects_grid_data_version_mismatch(tmp_path: Path) -> None:
    wide = _wide(tmp_path / "wide.parquet", data_version="published_v1")
    grid = build_experiment_grid(
        MANIFEST,
        CONFIG,
        suite="smoke",
        data_version="b1_no_level_v1",
    )

    try:
        ExperimentRunner(
            grid,
            wide_path=wide,
            quality_path=None,
            output_dir=tmp_path / "results",
            mask_dir=tmp_path / "masks",
            config_path=CONFIG,
            design_path=DESIGN,
            manifest_path=MANIFEST,
            models=("climatology",),
        )
    except ValueError as error:
        assert "data_version differ" in str(error)
    else:
        raise AssertionError("data-version mismatch was accepted")

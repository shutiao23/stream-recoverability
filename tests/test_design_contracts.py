from __future__ import annotations
import json
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from stream_recoverability.experiments.contracts import (
    CODE_PROVENANCE_SCHEMA_VERSION,
    DEFAULT_DESIGN_PATH,
    build_code_provenance,
    build_design_contract,
    canonical_evaluation_split,
)
from stream_recoverability.experiments.grid import build_experiment_grid
from stream_recoverability.experiments.runner import ExperimentRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "study_manifest.yaml"
CONFIG = REPO_ROOT / "configs" / "experiments.yaml"
DESIGN = REPO_ROOT / DEFAULT_DESIGN_PATH
VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "Rs")


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", "-C", str(repository), *arguments), check=True, capture_output=True
    )


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


def test_design_contract_changes_with_data_version_and_is_reproducible() -> None:
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
        design_path=str(DEFAULT_DESIGN_PATH),
        manifest_path="study_manifest.yaml",
        experiment_config_path="configs/experiments.yaml",
        data_version="published_v1",
        evaluation_split="validation",
    )
    assert first == repeated
    assert first == relative
    assert first["data_version"] != changed["data_version"]
    assert first["mask_schema_version"] == "mask_schema_v2"
    assert first["model_schema_version"] == "model_schema_v3"
    assert first["statistics_schema_version"] == "statistics_schema_v3"


def test_design_contract_scientific_fields_ignore_code_provenance_status() -> None:
    first_provenance = {
        "schema_version": CODE_PROVENANCE_SCHEMA_VERSION,
        "tracked_worktree_clean": True,
        "relevant_source_clean": True,
        "relevant_source_file_count": 12,
        "dirty_tracked_paths": [],
        "relevant_untracked_paths": [],
        "external_relevant_input_count": 0,
        "status": "clean",
    }
    docs_only_edit = {
        **first_provenance,
        "tracked_worktree_clean": False,
        "status": "dirty",
        "dirty_tracked_paths": ["README.md"],
    }
    first = build_design_contract(
        design_path=DESIGN,
        manifest_path=MANIFEST,
        experiment_config_path=CONFIG,
        data_version="published_v1",
        evaluation_split="development_test",
        code_provenance=first_provenance,
    )
    second = build_design_contract(
        design_path=DESIGN,
        manifest_path=MANIFEST,
        experiment_config_path=CONFIG,
        data_version="published_v1",
        evaluation_split="development_test",
        code_provenance=docs_only_edit,
    )
    scientific = (
        "design_version",
        "data_version",
        "evaluation_split",
        "mask_schema_version",
        "model_schema_version",
        "statistics_schema_version",
    )
    assert {key: first[key] for key in scientific} == {
        key: second[key] for key in scientific
    }
    assert first["code_provenance"] == first_provenance
    assert first["code_provenance"] != second["code_provenance"]
    changed_source = {
        **docs_only_edit,
        "relevant_source_clean": False,
        "dirty_tracked_paths": ["src/stream_recoverability/experiments/runner.py"],
    }
    changed = build_design_contract(
        design_path=DESIGN,
        manifest_path=MANIFEST,
        experiment_config_path=CONFIG,
        data_version="published_v1",
        evaluation_split="development_test",
        code_provenance=changed_source,
    )
    assert {key: changed[key] for key in scientific} == {
        key: first[key] for key in scientific
    }


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


def _quality_long(wide_path: Path, quality_path: Path) -> Path:
    wide = pd.read_parquet(wide_path)
    frames = [
        pd.DataFrame(
            {
                "date": wide["date"],
                "station_id": station,
                "variable": variable,
                "quality_approved": True,
                "natural_observed": True,
                "data_version": "published_v1",
            }
        )
        for station in ("B1", "S2", "P3")
        for variable in VARIABLES
    ]
    pd.concat(frames, ignore_index=True).to_parquet(quality_path, index=False)
    return quality_path


def test_validation_grid_masks_only_validation_and_persists_contract(
    tmp_path: Path,
) -> None:
    version_root = tmp_path / "published_v1"
    version_root.mkdir()
    wide = _wide(version_root / "daily_wide.parquet")
    quality = _quality_long(wide, version_root / "daily_long.parquet")
    manifest = version_root / "version_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "data_version": "published_v1",
                "artifacts": {
                    "daily_wide.parquet": {"bytes": wide.stat().st_size},
                    "daily_long.parquet": {"bytes": quality.stat().st_size},
                },
            }
        ),
        encoding="utf-8",
    )
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
        quality_path=quality,
        data_version_manifest_path=manifest,
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
    daily, events = runner.run(max_scenarios=1)
    for frame in (daily, events):
        assert set(frame["evaluation_split"]) == {"validation"}
        assert set(frame["data_version"]) == {"published_v1"}


def test_runner_rejects_grid_data_version_mismatch(tmp_path: Path) -> None:
    wide = _wide(tmp_path / "wide.parquet", data_version="published_v1")
    grid = build_experiment_grid(
        MANIFEST, CONFIG, suite="smoke", data_version="b1_no_level_v1"
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

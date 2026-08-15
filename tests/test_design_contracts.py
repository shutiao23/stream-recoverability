from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.contracts import (
    CODE_PROVENANCE_SCHEMA_VERSION,
    build_code_provenance,
    build_design_contract,
    canonical_code_identity,
    canonical_evaluation_split,
)
from stream_recoverability.experiments.grid import build_experiment_grid
from stream_recoverability.experiments.runner import ExperimentRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "study_manifest.yaml"
CONFIG = REPO_ROOT / "configs" / "experiments.yaml"
DESIGN = REPO_ROOT / "configs" / "design_freeze_v1.yaml"
VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "DH")


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
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
    assert len(first["code_identity"]["relevant_source_digest"]) == 64


def test_design_hash_excludes_noncanonical_git_audit_fields() -> None:
    source_digest = "a" * 64
    first_provenance = {
        "schema_version": CODE_PROVENANCE_SCHEMA_VERSION,
        "git_commit": "1" * 40,
        "tracked_worktree_clean": True,
        "relevant_source_clean": True,
        "relevant_source_digest": source_digest,
        "relevant_source_file_count": 12,
        "dirty_tracked_paths": [],
        "relevant_untracked_paths": [],
        "external_relevant_input_count": 0,
        "status": "clean",
    }
    docs_only_commit = {
        **first_provenance,
        "git_commit": "2" * 40,
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
        code_provenance=docs_only_commit,
    )

    assert canonical_code_identity(first_provenance) == canonical_code_identity(
        docs_only_commit
    )
    assert first["design_hash"] == second["design_hash"]
    assert first["code_identity"] == second["code_identity"]
    assert first["code_provenance"] != second["code_provenance"]

    changed_source = {**docs_only_commit, "relevant_source_digest": "b" * 64}
    changed = build_design_contract(
        design_path=DESIGN,
        manifest_path=MANIFEST,
        experiment_config_path=CONFIG,
        data_version="published_v1",
        evaluation_split="development_test",
        code_provenance=changed_source,
    )
    assert changed["design_hash"] != first["design_hash"]


def test_code_provenance_ignores_docs_and_generated_outputs_but_not_source(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "src/stream_recoverability/experiments/runner.py"
    script = repository / "scripts/08_run_experiments.py"
    confirmatory_script = repository / "scripts/20_run_confirmatory_evaluation.py"
    roster_loader = repository / "src/stream_recoverability/data/confirmatory.py"
    config = repository / "configs/design.yaml"
    for path, value in (
        (source, "VALUE = 1\n"),
        (script, "#!/usr/bin/env python3\n"),
        (confirmatory_script, "#!/usr/bin/env python3\n"),
        (roster_loader, "ROSTER_SCHEMA = 1\n"),
        (config, "design: frozen\n"),
        (repository / "pyproject.toml", "[project]\nname='fixture'\n"),
        (repository / "README.md", "first\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    _git(repository, "init")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Test")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial")

    initial = build_code_provenance(
        repository_root=repository,
        additional_relevant_paths=(config,),
    )
    generated = repository / "results/generated.json"
    generated.parent.mkdir(parents=True)
    generated.write_text("{}\n", encoding="utf-8")
    (repository / "README.md").write_text("second\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "docs only")
    docs_only = build_code_provenance(
        repository_root=repository,
        additional_relevant_paths=(config,),
    )

    assert initial["git_commit"] != docs_only["git_commit"]
    assert initial["relevant_source_digest"] == docs_only["relevant_source_digest"]
    assert docs_only["tracked_worktree_clean"] is True
    assert docs_only["relevant_source_clean"] is True

    confirmatory_script.write_text(
        "#!/usr/bin/env python3\nVALUE = 2\n", encoding="utf-8"
    )
    dirty_confirmation = build_code_provenance(
        repository_root=repository,
        additional_relevant_paths=(config,),
    )
    assert dirty_confirmation["dirty_tracked_paths"] == [
        "scripts/20_run_confirmatory_evaluation.py"
    ]
    assert (
        dirty_confirmation["relevant_source_digest"]
        != docs_only["relevant_source_digest"]
    )
    confirmatory_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    roster_loader.write_text("ROSTER_SCHEMA = 2\n", encoding="utf-8")
    dirty_roster_loader = build_code_provenance(
        repository_root=repository,
        additional_relevant_paths=(config,),
    )
    assert dirty_roster_loader["dirty_tracked_paths"] == [
        "src/stream_recoverability/data/confirmatory.py"
    ]
    assert (
        dirty_roster_loader["relevant_source_digest"]
        != docs_only["relevant_source_digest"]
    )
    roster_loader.write_text("ROSTER_SCHEMA = 1\n", encoding="utf-8")

    source.write_text("VALUE = 2\n", encoding="utf-8")
    dirty = build_code_provenance(
        repository_root=repository,
        additional_relevant_paths=(config,),
    )
    assert dirty["tracked_worktree_clean"] is False
    assert dirty["relevant_source_clean"] is False
    assert dirty["dirty_tracked_paths"] == [
        "src/stream_recoverability/experiments/runner.py"
    ]
    assert dirty["relevant_source_digest"] != docs_only["relevant_source_digest"]


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
    version_root = REPO_ROOT / "data_versions" / "published_v1"
    wide = version_root / "daily_wide.parquet"
    quality = version_root / "daily_long.parquet"
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
        data_version_manifest_path=version_root / "version_manifest.json",
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

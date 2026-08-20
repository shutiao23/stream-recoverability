from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

import stream_recoverability.experiments.contracts as contract_module
from stream_recoverability.experiments.contracts import (
    build_code_provenance,
    file_sha256,
)
from stream_recoverability.experiments.grid import build_experiment_grid
from stream_recoverability.experiments.model_registry import (
    load_frozen_model_design,
)
from stream_recoverability.experiments.runner import (
    REFERENCE_MODELS,
    ExperimentRunner,
)
from stream_recoverability.models.reference_baselines import (
    REFERENCE_IMPLEMENTATION,
    PyPOTSReferenceImputer,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "study_manifest.yaml"
CONFIG = REPO_ROOT / "configs" / "experiments.yaml"
DESIGN = REPO_ROOT / "configs" / "design_freeze_v3.yaml"
VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "Rs")
FORMAL_PROVENANCE_GATE = ExperimentRunner._assert_formal_code_provenance


def _clean_code_provenance() -> dict[str, object]:
    provenance = build_code_provenance()
    provenance.update(
        {
            "tracked_worktree_clean": True,
            "relevant_source_clean": True,
            "dirty_tracked_paths": [],
            "relevant_untracked_paths": [],
            "external_relevant_input_count": 0,
            "status": "clean",
        }
    )
    return provenance


def _wide_data(path: Path) -> Path:
    dates = pd.date_range("2006-01-01", "2020-12-31", freq="D")
    day = np.arange(len(dates), dtype=float)
    frame = pd.DataFrame({"date": dates})
    frame["split"] = np.select(
        [dates <= "2015-12-31", dates <= "2017-12-31"],
        ["train", "validation"],
        default="test",
    )
    for station_index, station in enumerate(("B1", "S2", "P3")):
        frame[f"{station}_T"] = 10 + station_index + 5 * np.sin(day / 58.0)
        frame[f"{station}_F"] = 100 + station_index * 10 + 8 * np.cos(day / 23.0)
        frame[f"{station}_L"] = 20 + 0.05 * frame[f"{station}_F"]
        frame[f"{station}_Ta"] = 8 + 7 * np.sin(day / 58.0)
        frame[f"{station}_P"] = np.maximum(0, np.sin(day / 7.0))
        frame[f"{station}_W"] = 2 + 0.2 * np.cos(day / 11.0)
        frame[f"{station}_RH"] = 55 + 4 * np.sin(day / 17.0)
        frame[f"{station}_Rs"] = 8 + 2 * np.cos(day / 58.0)
    frame.to_parquet(path, index=False)
    return path


def _quality_data(wide_path: Path, quality_path: Path) -> Path:
    wide = pd.read_parquet(wide_path)
    rows = []
    for station in ("B1", "S2", "P3"):
        for variable in VARIABLES:
            column = f"{station}_{variable}"
            for date, value in zip(wide["date"], wide[column], strict=True):
                rows.append(
                    {
                        "date": date,
                        "station_id": station,
                        "variable": variable,
                        "value": value,
                        "quality_approved": True,
                    }
                )
    pd.DataFrame(rows).to_parquet(quality_path, index=False)
    return quality_path


def _version_manifest(root: Path, wide_path: Path, quality_path: Path) -> Path:
    path = root / "version_manifest.json"
    path.write_text(
        json.dumps(
            {
                "data_version": "published_v1",
                "artifacts": {
                    "daily_wide.parquet": {"sha256": file_sha256(wide_path)},
                    "daily_long.parquet": {"sha256": file_sha256(quality_path)},
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _runner(
    tmp_path: Path,
    *,
    models: tuple[str, ...] | None,
    suite: str = "smoke",
    evaluation_split: str = "development_test",
) -> ExperimentRunner:
    tmp_path.mkdir(parents=True, exist_ok=True)
    wide_path = _wide_data(tmp_path / "wide.parquet")
    quality_path = None
    data_version_manifest_path = None
    if evaluation_split == "validation":
        quality_path = _quality_data(wide_path, tmp_path / "long.parquet")
        data_version_manifest_path = _version_manifest(
            tmp_path, wide_path, quality_path
        )
    grid = build_experiment_grid(
        MANIFEST,
        CONFIG,
        suite=suite,
        evaluation_split=evaluation_split,
    )
    return ExperimentRunner(
        grid,
        wide_path=wide_path,
        quality_path=quality_path,
        data_version_manifest_path=data_version_manifest_path,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        config_path=CONFIG,
        design_path=DESIGN,
        models=models,
        resume=True,
    )


def test_frozen_registry_separates_formal_reference_and_lite_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = load_frozen_model_design(DESIGN)
    assert REFERENCE_MODELS.issubset(frozen.formal_candidates)
    assert frozen.development_only == ("brits_lite", "saits_lite")
    assert not set(frozen.development_only).intersection(frozen.formal_candidates)

    migration = _runner(
        tmp_path / "migration", models=("brits", "saits"), suite="smoke"
    )
    assert migration.models == ("brits_lite", "saits_lite")
    assert migration.model_request_aliases == {
        "brits": "brits_lite",
        "saits": "saits_lite",
    }
    assert {model for model, _ in migration._run_keys()} == {
        "brits_lite",
        "saits_lite",
    }

    clean_provenance = _clean_code_provenance()
    monkeypatch.setattr(
        contract_module,
        "build_code_provenance",
        lambda **_: clean_provenance,
    )
    formal = _runner(tmp_path / "formal", models=None, suite="core")
    assert formal.models == frozen.formal_candidates
    formal_model, formal_training, formal_context = formal._proposed_contract(
        11, 184, "seen_length"
    )
    assert formal_model.hidden_size == 32
    assert formal_model.dropout == pytest.approx(0.10)
    assert formal_training.epochs == 400
    assert formal_training.patience == 20
    assert formal_training.learning_rate == pytest.approx(0.001)
    assert formal_training.weight_decay == 0.0
    assert formal_training.min_delta == 0.0
    assert formal_context["training_budget_source"] == "design_freeze"
    with pytest.raises(ValueError, match="migration-only"):
        _runner(tmp_path / "legacy-formal", models=("brits",), suite="core")
    with pytest.raises(ValueError, match="formal candidate registry"):
        _runner(
            tmp_path / "lite-formal", models=("brits_lite",), suite="core"
        )


def test_formal_runner_rejects_dirty_relevant_code_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dirty_provenance = _clean_code_provenance()
    dirty_provenance.update(
        {
            "tracked_worktree_clean": False,
            "relevant_source_clean": False,
            "dirty_tracked_paths": [
                "src/stream_recoverability/experiments/runner.py"
            ],
            "status": "dirty",
        }
    )
    monkeypatch.setattr(
        contract_module,
        "build_code_provenance",
        lambda **_: dirty_provenance,
    )
    monkeypatch.setattr(
        ExperimentRunner,
        "_assert_formal_code_provenance",
        staticmethod(FORMAL_PROVENANCE_GATE),
    )

    with pytest.raises(RuntimeError, match="formal runs require clean"):
        _runner(tmp_path, models=("brits_ref",), suite="core")


def test_reference_and_proposed_target_roster_is_t_only_without_training(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(tmp_path, models=("csdi",))
    base = runner.grid.scenarios[0]
    scenario = replace(
        base,
        condition=replace(
            base.condition,
            variables=("F",),
            evaluation_variables=("F",),
        ),
    )
    artificial = np.zeros_like(runner.data.values, dtype=bool)
    station = runner.data.station_ids.index(scenario.condition.station_ids[0])
    variable = runner.data.variable_names.index("F")
    artificial[np.flatnonzero(runner.test_rows)[0], station, variable] = True

    def unexpected_prediction(*args, **kwargs):
        del args, kwargs
        raise AssertionError("an unsupported-only scenario must not train or predict")

    monkeypatch.setattr(runner, "_model_prediction", unexpected_prediction)
    for model_name in (*sorted(REFERENCE_MODELS), "proposed"):
        daily, events, skips = runner._prediction_rows(
            scenario,
            {},
            artificial,
            model_name,
            11,
        )
        assert daily.empty
        assert events.empty
        assert skips == [
            {
                "run_key": f"{model_name}:11",
                "model": model_name,
                "training_seed": 11,
                "station_id": scenario.condition.station_ids[0],
                "target": "F",
                "reason_code": "unsupported_model_target",
                "reason": f"{model_name} does not estimate target F",
            }
        ]

    for model_name in (*REFERENCE_MODELS, "proposed"):
        assert runner._supports_target(model_name, "T") is True
        assert runner._supports_target(model_name, "F") is False
        assert runner._supports_target(model_name, "L") is False
    for model_name in ("brits_lite", "saits_lite"):
        assert runner._supports_target(model_name, "T") is True
        assert runner._supports_target(model_name, "F") is True
        assert runner._supports_target(model_name, "L") is True

    runner.grid = replace(
        runner.grid,
        conditions=(scenario.condition,),
        scenarios=(scenario,),
    )
    daily, events = runner.run(max_scenarios=1)
    assert daily.empty
    assert events.empty
    run_manifest = json.loads(
        (runner.output_dir / "run_manifest.json").read_text(encoding="utf-8")
    )
    expected_unit = f"{scenario.scenario_id}|csdi:11"
    assert run_manifest["complete"] is False
    assert run_manifest["formal_design_complete"] is False
    assert run_manifest["run_complete"] is True
    assert run_manifest["structural_skip_run_unit_keys"] == [expected_unit]
    assert run_manifest["checkpoint_required_run_unit_keys"] == []
    assert run_manifest["checkpoint_contract_complete"] is True


def test_run_contract_stales_on_relevant_identity_not_git_audit(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path, models=("csdi",))
    scenario = runner.grid.scenarios[0]
    current = runner._run_execution_contract(scenario, "csdi", 11)
    docs_only = json.loads(json.dumps(current))
    docs_only["code_provenance"]["git_commit"] = "f" * 40
    docs_only["code_provenance"]["status"] = "historical"
    assert runner._execution_contract_matches(docs_only, current)

    stale_source = json.loads(json.dumps(current))
    stale_source["code_identity"]["relevant_source_digest"] = "0" * 64
    assert not runner._execution_contract_matches(stale_source, current)


def test_proposed_and_reference_contracts_use_the_frozen_design(
    tmp_path: Path,
) -> None:
    runner = _runner(
        tmp_path,
        models=("brits_ref", "saits_ref", "csdi", "proposed"),
    )
    proposed_model, proposed_training, context = runner._proposed_contract(
        11, 184, "seen_length"
    )
    assert proposed_model.hidden_size == 32
    assert proposed_model.dropout == pytest.approx(0.10)
    assert proposed_training.learning_rate == pytest.approx(0.001)
    assert proposed_training.weight_decay == 0.0
    assert proposed_training.min_delta == 0.0
    assert proposed_training.gradient_clip == 1.0
    assert context["frozen_common_training"]["max_epochs"] == 400

    contracts = {
        name: runner._reference_contract(name, 11, 184, "seen_length")
        for name in ("brits_ref", "saits_ref", "csdi")
    }
    protocols = [value[0] for value in contracts.values()]
    assert protocols[0] is protocols[1] is protocols[2]
    assert len(protocols[0].fingerprint) == 64
    assert {value[3]["implementation"] for value in contracts.values()} == {
        REFERENCE_IMPLEMENTATION
    }
    assert contracts["brits_ref"][1]["model_kwargs"] == {
        "rnn_hidden_size": 64
    }
    assert contracts["saits_ref"][1]["model_kwargs"]["d_model"] == 64
    assert contracts["csdi"][1]["model_kwargs"]["n_diffusion_steps"] == 50
    mean, scale = runner._proposed_scaler()
    normalized = (runner.data.values - mean[None]) / scale[None]
    proposed_train = runner._proposed_batches(
        normalized,
        runner.train_rows,
        None,
        protocols[0].window_size,
        curriculum_config=proposed_training.curriculum,
        curriculum_seed=11,
        protocol="seen_length",
        repeats=runner.training_settings["train_mask_repeats"],
    )
    proposed_masks = np.concatenate(
        [batch["artificial_mask"].numpy() for batch in proposed_train], axis=0
    ).reshape(protocols[0].train.artificial_mask.shape)
    np.testing.assert_array_equal(
        proposed_masks, protocols[0].train.artificial_mask
    )
    for _, _, training, reference_context in contracts.values():
        assert training.epochs == 3
        assert training.patience == 2
        assert training.learning_rate == pytest.approx(0.001)
        assert training.weight_decay == 0.0
        assert reference_context["training_budget_source"] == "smoke_profile"


def test_formal_runner_rejects_experiment_budget_drift_from_design_freeze(
    tmp_path: Path,
) -> None:
    frozen = yaml.safe_load(DESIGN.read_text(encoding="utf-8"))
    frozen["training"]["fixed_model_protocols"]["common"]["max_epochs"] = 201
    drifted_design = tmp_path / "drifted_design.yaml"
    drifted_design.write_text(
        yaml.safe_dump(frozen, sort_keys=False), encoding="utf-8"
    )
    grid = build_experiment_grid(MANIFEST, CONFIG, suite="core")
    with pytest.raises(ValueError, match="training budget disagrees"):
        ExperimentRunner(
            grid,
            wide_path=_wide_data(tmp_path / "wide.parquet"),
            quality_path=None,
            output_dir=tmp_path / "results",
            mask_dir=tmp_path / "masks",
            config_path=CONFIG,
            design_path=drifted_design,
            models=("proposed",),
        )


@pytest.mark.parametrize("evaluation_split", ["validation", "development_test"])
def test_reference_protocol_supports_both_development_splits(
    tmp_path: Path, evaluation_split: str
) -> None:
    runner = _runner(
        tmp_path / evaluation_split,
        models=("csdi",),
        evaluation_split=evaluation_split,
    )
    protocol = runner._reference_protocol(11, 184, "seen_length")
    assert runner.evaluation_split == evaluation_split
    assert protocol.train.n_samples > 0
    assert protocol.validation.n_samples > 0
    assert protocol.metadata["score_mask_scope"] == "T_only"


def test_csdi_runner_stitches_samples_and_emits_interval_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(tmp_path, models=("csdi",))
    scenario = runner.grid.scenarios[0]
    artificial, metadata = runner._generate_mask(scenario)
    protocol = runner._reference_protocol(
        11,
        scenario.condition.window_length,
        scenario.condition.training_protocol,
    )
    draws = runner._reference_training_config(11).prediction_sampling_times

    class FakeCSDI:
        model_name = "csdi"
        protocol_fingerprint_ = protocol.fingerprint

        def __init__(self) -> None:
            self.diagnostics_ = {
                "parameter_count": 123,
                "best_epoch": 2,
                "epochs_run": 3,
                "hit_epoch_limit": True,
                "validation_score_by_scenario": {
                    "point": 1.0,
                    "short_block": 1.1,
                    "long_block": 1.2,
                    "station_outage": 1.3,
                },
                "best_validation_score": 1.15,
                "training_time_seconds": 0.5,
                "inference_time_seconds": 0.0,
            }

        def predict(
            self,
            values: np.ndarray,
            artificial_mask: np.ndarray,
            **_: object,
        ) -> SimpleNamespace:
            point = np.nan_to_num(values, nan=0.0).astype(np.float32)
            point[artificial_mask] = 0.0
            samples = np.repeat(point[:, None], draws, axis=1)
            sample_axis = np.linspace(-100.0, 100.0, draws, dtype=np.float32)
            for draw, value in enumerate(sample_axis):
                samples[:, draw][artificial_mask] = value
            return SimpleNamespace(
                point=point,
                samples=samples,
                inference_time_seconds=0.01,
            )

    key = (
        "csdi",
        11,
        scenario.condition.window_length,
        scenario.condition.training_protocol,
    )
    fake = FakeCSDI()
    runner._reference_cache[key] = fake  # type: ignore[assignment]
    monkeypatch.setattr(runner, "_reference_model", lambda *args: fake)

    prediction, quantiles = runner._model_prediction(
        "csdi", 11, scenario, artificial
    )
    assert prediction is not None and quantiles is not None
    assert quantiles["q05"].shape == runner.data.values.shape
    assert np.isfinite(quantiles["q05"][artificial]).all()
    assert np.all(quantiles["q05"][artificial] < quantiles["q95"][artificial])

    daily, events, skipped = runner._prediction_rows(
        scenario, metadata, artificial, "csdi", 11
    )
    assert not skipped
    assert daily[["q05", "q95"]].notna().all().all()
    assert events["coverage_90"].notna().all()
    assert events["reference_implementation"].eq(REFERENCE_IMPLEMENTATION).all()
    assert events["best_epoch"].eq(2).all()
    assert events["finite_predictions"].all()
    assert events["evaluation_split"].eq("development_test").all()


def test_runner_reference_checkpoint_validation_and_contract_are_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(tmp_path, models=("csdi",))
    scenario = runner.grid.scenarios[0]
    checkpoint = runner._checkpoint_path("csdi", 11, scenario)
    assert checkpoint is not None
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"checkpoint")
    Path(str(checkpoint) + ".sha256").write_text("sidecar\n", encoding="ascii")
    captured: dict[str, object] = {}
    loaded = SimpleNamespace(diagnostics_={}, metadata_={})

    def load_checkpoint(cls: type, path: Path, **kwargs: object) -> object:
        del cls
        captured["path"] = path
        captured.update(kwargs)
        return loaded

    monkeypatch.setattr(
        PyPOTSReferenceImputer,
        "load_checkpoint",
        classmethod(load_checkpoint),
    )
    assert runner._strict_checkpoint_valid(scenario, "csdi", 11)
    protocol, adapter_config, training, _ = runner._reference_contract(
        "csdi", 11, scenario.condition.window_length, scenario.condition.training_protocol
    )
    assert captured["expected_model_name"] == "csdi"
    assert captured["expected_protocol_fingerprint"] == protocol.fingerprint
    assert captured["expected_adapter_config"] == adapter_config
    assert captured["expected_training_config"] == asdict(training)
    contract = runner._run_execution_contract(scenario, "csdi", 11)
    assert contract["reference_implementation"] == REFERENCE_IMPLEMENTATION
    assert contract["reference_protocol_fingerprint"] == protocol.fingerprint
    assert contract["checkpoint"]["sha256"]
    assert contract["checkpoint_sidecar"]["sha256"]

    def reject_checkpoint(cls: type, path: Path, **kwargs: object) -> object:
        del cls, path, kwargs
        raise ValueError("tampered")

    monkeypatch.setattr(
        PyPOTSReferenceImputer,
        "load_checkpoint",
        classmethod(reject_checkpoint),
    )
    assert not runner._strict_checkpoint_valid(scenario, "csdi", 11)

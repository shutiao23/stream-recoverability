from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import tomllib
import torch

from stream_recoverability.models import reference_baselines as reference_module
from stream_recoverability.models.proposed_curriculum import (
    FROZEN_VALIDATION_SCENARIOS,
    ProposedCurriculumConfig,
)
from stream_recoverability.models.reference_baselines import (
    PYPOTS_REQUIRED_VERSION,
    PyPOTSReferenceImputer,
    ReferenceProtocolData,
    ReferenceTrainingConfig,
    build_reference_protocol_data,
    require_pypots_15,
)

VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "DH")
STATIONS = ("A", "B", "C")


def _curriculum() -> ProposedCurriculumConfig:
    return replace(
        ProposedCurriculumConfig(),
        gap_lengths=(2, 3, 4),
        unseen_length_max_days=3,
        validation_short_block_days=2,
        validation_long_block_days=3,
        validation_station_outage_days=3,
    )


@pytest.fixture(scope="module")
def protocol() -> ReferenceProtocolData:
    rng = np.random.default_rng(20260815)
    train = rng.normal(size=(14, len(STATIONS), len(VARIABLES))).astype(np.float32)
    validation = rng.normal(size=(14, len(STATIONS), len(VARIABLES))).astype(np.float32)
    train[0, 0, -1] = np.nan
    validation[1, 1, -2] = np.nan
    return build_reference_protocol_data(
        train,
        validation,
        variable_names=VARIABLES,
        station_ids=STATIONS,
        window_size=6,
        protocol="seen_length",
        seed=13,
        train_mask_repeats=1,
        validation_mask_repeats=1,
        curriculum_config=_curriculum(),
    )


def _model_kwargs(name: str) -> dict[str, object]:
    if name == "brits":
        return {"rnn_hidden_size": 4}
    if name == "saits":
        return {
            "n_layers": 1,
            "d_model": 4,
            "n_heads": 1,
            "d_k": 4,
            "d_v": 4,
            "d_ffn": 8,
            "dropout": 0.0,
            "attn_dropout": 0.0,
        }
    return {
        "n_layers": 1,
        "n_heads": 1,
        "n_channels": 4,
        "d_time_embedding": 4,
        "d_feature_embedding": 2,
        "d_diffusion_embedding": 4,
        "n_diffusion_steps": 2,
        "beta_end": 0.1,
    }


@pytest.fixture(scope="module")
def trained_references(
    protocol: ReferenceProtocolData,
) -> dict[str, PyPOTSReferenceImputer]:
    config = ReferenceTrainingConfig(
        epochs=1,
        patience=1,
        batch_size=4,
        seed=17,
        validation_sampling_times=2,
        prediction_sampling_times=3,
    )
    result: dict[str, PyPOTSReferenceImputer] = {}
    for name in ("brits", "saits", "csdi"):
        result[name] = PyPOTSReferenceImputer(
            name,
            protocol.window_size,
            protocol.train.n_features,
            model_kwargs=_model_kwargs(name),
        ).fit(protocol, config)
    return result


def test_reference_extra_pins_exact_pypots_version() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["optional-dependencies"]["reference"] == ["pypots==1.5"]
    assert require_pypots_15().version == PYPOTS_REQUIRED_VERSION


def test_reference_loader_fails_closed_on_missing_or_wrong_version(monkeypatch) -> None:
    monkeypatch.setattr(reference_module.importlib_metadata, "version", lambda _: "1.4")
    with pytest.raises(RuntimeError, match="exactly pypots==1.5"):
        require_pypots_15()

    def missing(_: str) -> str:
        raise reference_module.importlib_metadata.PackageNotFoundError("pypots")

    monkeypatch.setattr(reference_module.importlib_metadata, "version", missing)
    with pytest.raises(ImportError, match="reference.*extra"):
        require_pypots_15()


def test_protocol_is_fixed_equal_budget_target_only_and_right_aligned(
    protocol: ReferenceProtocolData,
) -> None:
    assert protocol.metadata["train_window_starts"] == [0, 3, 6, 8]
    assert protocol.metadata["validation_window_starts"] == [0, 3, 6, 8]
    assert protocol.stride == 3
    assert tuple(dict.fromkeys(protocol.validation.scenario_labels)) == tuple(
        FROZEN_VALIDATION_SCENARIOS
    )
    assert protocol.validation.scenario_counts == {
        scenario: 4 for scenario in FROZEN_VALIDATION_SCENARIOS
    }
    target_features = np.arange(protocol.train.n_features) % len(VARIABLES) == 0
    assert not protocol.train.score_mask[..., ~target_features].any()
    assert not protocol.validation.score_mask[..., ~target_features].any()
    assert np.any(protocol.validation.artificial_mask & ~protocol.validation.score_mask)
    assert np.all(protocol.train.score_mask <= protocol.train.artificial_mask)
    assert protocol.train.X_ori.flags.writeable is False
    assert protocol.validation.artificial_mask.flags.writeable is False
    assert all(
        row["score_mask_scope"] == "T_only" for row in protocol.validation.metadata
    )


def test_protocol_masks_scaler_and_fingerprint_are_deterministic(
    protocol: ReferenceProtocolData,
) -> None:
    train = np.concatenate(
        [row.X_ori[:1] for row in (protocol.train,)], axis=0
    )  # exercise immutable access without changing it
    assert train.shape == (1, protocol.window_size, protocol.train.n_features)

    rng = np.random.default_rng(20260815)
    raw_train = rng.normal(size=(14, len(STATIONS), len(VARIABLES))).astype(np.float32)
    raw_validation = rng.normal(size=(14, len(STATIONS), len(VARIABLES))).astype(
        np.float32
    )
    raw_train[0, 0, -1] = np.nan
    raw_validation[1, 1, -2] = np.nan
    repeated = build_reference_protocol_data(
        raw_train,
        raw_validation,
        variable_names=VARIABLES,
        station_ids=STATIONS,
        window_size=6,
        protocol="seen_length",
        seed=13,
        train_mask_repeats=1,
        validation_mask_repeats=1,
        curriculum_config=_curriculum(),
    )
    assert repeated.fingerprint == protocol.fingerprint
    assert np.array_equal(
        repeated.train.artificial_mask, protocol.train.artificial_mask
    )
    assert np.array_equal(
        repeated.validation.artificial_mask, protocol.validation.artificial_mask
    )
    assert np.array_equal(repeated.feature_mean, protocol.feature_mean)
    assert np.array_equal(repeated.feature_scale, protocol.feature_scale)


@pytest.mark.parametrize("name", ["brits", "saits", "csdi"])
def test_official_cpu_tiny_smoke_and_diagnostics(
    name: str,
    protocol: ReferenceProtocolData,
    trained_references: dict[str, PyPOTSReferenceImputer],
) -> None:
    model = trained_references[name]
    assert model.pypots_model_.__class__.__module__ == (
        f"pypots.imputation.{name}.model"
    )
    assert model.model.__class__.__module__ == f"pypots.imputation.{name}.core"
    assert model.metadata_["implementation"] == "official_pypots_1.5"
    assert "lite" not in json.dumps(model.metadata_).lower()
    required = {
        "parameter_count",
        "best_epoch",
        "epochs_run",
        "hit_epoch_limit",
        "validation_score_by_scenario",
        "training_time_seconds",
        "inference_time_seconds",
    }
    assert required <= model.diagnostics_.keys()
    assert model.diagnostics_["parameter_count"] > 0
    assert model.diagnostics_["best_epoch"] == 1
    assert model.diagnostics_["epochs_run"] == 1
    assert model.diagnostics_["hit_epoch_limit"] is True
    assert tuple(model.diagnostics_["validation_score_by_scenario"]) == tuple(
        FROZEN_VALIDATION_SCENARIOS
    )
    if name == "brits":
        assert model.metadata_["training_objective"] == (
            "official_consistency_and_observed_reconstruction_plus_target_only_MIT"
        )
        assert model.metadata_["target_only_MIT_weight"] == 1.0
        components = model.diagnostics_["history"][0]["train_loss_components"]
        assert tuple(components) == ("official_core_loss", "target_only_MIT_loss")
        assert np.isfinite(tuple(components.values())).all()
    prediction = model.predict(
        protocol.validation.X_ori[:2], protocol.validation.artificial_mask[:2]
    )
    assert prediction.point.shape == (
        2,
        protocol.window_size,
        protocol.train.n_features,
    )
    assert np.isfinite(prediction.point).all()
    observed = (
        np.isfinite(protocol.validation.X_ori[:2])
        & ~protocol.validation.artificial_mask[:2]
    )
    assert np.array_equal(
        prediction.point[observed], protocol.validation.X_ori[:2][observed]
    )
    if name == "csdi":
        assert prediction.samples is not None
        assert prediction.samples.shape == (
            2,
            3,
            protocol.window_size,
            protocol.train.n_features,
        )
        assert tuple(prediction.quantiles) == (0.05, 0.25, 0.5, 0.75, 0.95)
        assert prediction.interval is not None
        repeated = model.predict(
            protocol.validation.X_ori[:2], protocol.validation.artificial_mask[:2]
        )
        assert np.array_equal(prediction.samples, repeated.samples)
        assert np.array_equal(prediction.point, repeated.point)
        assert np.all(prediction.interval_lower <= prediction.interval_upper)
    else:
        assert prediction.samples is None
        assert prediction.quantiles == {}
        assert prediction.interval is None


@pytest.mark.parametrize("name", ["brits", "saits", "csdi"])
def test_reference_checkpoint_round_trip_is_strict(
    name: str,
    tmp_path: Path,
    protocol: ReferenceProtocolData,
    trained_references: dict[str, PyPOTSReferenceImputer],
) -> None:
    model = trained_references[name]
    expected = model.predict(
        protocol.validation.X_ori[:2], protocol.validation.artificial_mask[:2]
    )
    checkpoint = model.save_checkpoint(tmp_path / f"{name}.pt")
    assert Path(str(checkpoint) + ".sha256").is_file()
    loaded = PyPOTSReferenceImputer.load_checkpoint(
        checkpoint,
        expected_model_name=name,
        expected_protocol_fingerprint=protocol.fingerprint,
        expected_adapter_config={
            "n_steps": protocol.window_size,
            "n_features": protocol.train.n_features,
            "model_kwargs": model.model_kwargs,
        },
        expected_training_config=model.training_config_,
    )
    actual = loaded.predict(
        protocol.validation.X_ori[:2], protocol.validation.artificial_mask[:2]
    )
    assert np.array_equal(expected.point, actual.point)
    if name == "csdi":
        assert np.array_equal(expected.samples, actual.samples)


def test_reference_checkpoint_rejects_file_and_state_tampering(
    tmp_path: Path,
    trained_references: dict[str, PyPOTSReferenceImputer],
) -> None:
    checkpoint = trained_references["brits"].save_checkpoint(tmp_path / "brits.pt")
    sidecar = Path(str(checkpoint) + ".sha256")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    state_name = next(
        name
        for name, value in payload["model_state_dict"].items()
        if torch.is_floating_point(value)
    )
    payload["model_state_dict"][state_name] = payload["model_state_dict"][
        state_name
    ].clone()
    payload["model_state_dict"][state_name].reshape(-1)[0] += 1
    torch.save(payload, checkpoint)
    with pytest.raises(ValueError, match="file SHA-256 mismatch"):
        PyPOTSReferenceImputer.load_checkpoint(checkpoint)

    sidecar.write_text(hashlib.sha256(checkpoint.read_bytes()).hexdigest() + "\n")
    with pytest.raises(ValueError, match="state_dict SHA-256 mismatch"):
        PyPOTSReferenceImputer.load_checkpoint(checkpoint)


@pytest.mark.parametrize("name", ["brits", "saits", "csdi"])
def test_hidden_truth_never_enters_official_prediction(
    name: str,
    protocol: ReferenceProtocolData,
    trained_references: dict[str, PyPOTSReferenceImputer],
) -> None:
    values = np.array(protocol.validation.X_ori[:2], copy=True)
    mask = protocol.validation.artificial_mask[:2]
    altered = values.copy()
    altered[mask] += 10_000
    original_prediction = trained_references[name].predict(values, mask)
    altered_prediction = trained_references[name].predict(altered, mask)
    assert np.array_equal(
        original_prediction.point[mask], altered_prediction.point[mask]
    )
    if name == "csdi":
        assert np.array_equal(
            original_prediction.samples[:, :, :, :][
                np.broadcast_to(mask[:, None], original_prediction.samples.shape)
            ],
            altered_prediction.samples[:, :, :, :][
                np.broadcast_to(mask[:, None], altered_prediction.samples.shape)
            ],
        )

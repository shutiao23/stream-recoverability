from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.conditional_observability import (
    information_set_conditionals,
    stationary_covariance,
    var1_gap_conditional_risk,
)
from stream_recoverability.experiments.t2_train_only_predictors import (
    PREDICTOR_COLUMNS,
    PredictorContractError,
    build_train_only_predictor_sidecar,
    predict_network_panel,
)


def test_scalable_var1_risk_matches_dense_public_schur_api() -> None:
    transition = np.array([[0.72, 0.10], [0.04, 0.65]])
    sigma = stationary_covariance(transition, np.array([[0.7, 0.15], [0.15, 0.8]]))
    dense = information_set_conditionals(
        transition, sigma, target=0, donors=[1], gap_length=7
    )["B_union_D"]
    scalable = var1_gap_conditional_risk(
        transition, sigma, target=0, donors=[1], gap_length=7
    )
    assert scalable["predicted_conditional_risk"] == pytest.approx(
        dense["predicted_conditional_risk"], rel=1e-6, abs=1e-7
    )
    assert scalable["recoverability_r"] == pytest.approx(
        dense["recoverability_r"], rel=1e-6, abs=1e-7
    )


def _synthetic_panel() -> pd.DataFrame:
    index = pd.date_range("2001-01-01", "2008-12-31", freq="D")
    rng = np.random.default_rng(91)
    common = np.sin(np.arange(len(index)) * 2.0 * np.pi / 365.25)
    innovations = rng.normal(0.0, 0.3, size=(len(index), 3))
    values = np.empty_like(innovations)
    values[0] = innovations[0]
    for position in range(1, len(index)):
        values[position] = 0.7 * values[position - 1] + innovations[position]
    values += common[:, None] * np.array([4.0, 3.4, 3.8])[None, :]
    return pd.DataFrame(values, index=index, columns=["a", "b", "c"])


def test_test_year_target_perturbation_cannot_change_predictors() -> None:
    original = _synthetic_panel()
    perturbed = original.copy()
    # Eight years -> first six are the rounded 70% fitting window.
    test = perturbed.index.year >= 2007
    perturbed.loc[test, "a"] = perturbed.loc[test, "a"] * -100.0 + 1234.0
    left = predict_network_panel("huc8_test", original, role="validation")
    right = predict_network_panel("huc8_test", perturbed, role="validation")
    pd.testing.assert_frame_equal(
        left[[*PREDICTOR_COLUMNS, "donor_r2_year_block_cv_raw", "acf1_raw"]],
        right[[*PREDICTOR_COLUMNS, "donor_r2_year_block_cv_raw", "acf1_raw"]],
        check_exact=True,
    )


def test_sidecar_builder_refuses_sealed_named_path_before_read(tmp_path: Path) -> None:
    workload = tmp_path / "workload.json"
    design = tmp_path / "design.yaml"
    workload.write_text("not read", encoding="utf-8")
    design.write_text("not read", encoding="utf-8")
    with pytest.raises(PredictorContractError, match="sealed-path"):
        build_train_only_predictor_sidecar(
            repo_root=tmp_path,
            workload_manifest_path=workload,
            design_path=design,
            output_dir=tmp_path / "sealed_outputs",
        )


def test_non_frozen_gap_roster_is_rejected() -> None:
    with pytest.raises(PredictorContractError, match="seven frozen"):
        predict_network_panel(
            "huc8_test", _synthetic_panel(), role="development", gaps=(30, 90)
        )

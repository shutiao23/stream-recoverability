from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.experiments.matched_outage_geometry import (
    EXPECTED_NATURAL_CONTRACT,
    EXPECTED_NATURAL_IMPLEMENTATION,
    nearest_artificial_horizon,
    validate_natural_xgboost_rows,
)

ROOT = Path(__file__).resolve().parents[1]


def test_nearest_grid_horizon_uses_log_distance_and_short_tie() -> None:
    assert nearest_artificial_horizon(7) == 7
    assert nearest_artificial_horizon(20) == 14
    assert nearest_artificial_horizon(45) == 60


def _natural_row() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "network_id": ["n1"],
            "target_station": ["s1"],
            "model": ["xgboost"],
            "information_condition": ["B_union_D"],
            "geometry": ["natural_outage"],
            "geometry_id": ["g1"],
            "truth_start_date": ["2020-01-01"],
            "observed_missing_start_date": ["2000-01-01"],
            "actual_missing_truth_available": [False],
            "benchmark_truth_source": ["held_out_observed_counterpart"],
            "status": ["complete"],
            "implementation": [EXPECTED_NATURAL_IMPLEMENTATION],
            "runner_contract_version": [EXPECTED_NATURAL_CONTRACT],
            "mae_deg_c": [1.0],
        }
    )


def test_natural_validation_requires_counterpart_not_actual_missing_truth() -> None:
    assert len(validate_natural_xgboost_rows(_natural_row())) == 1
    invalid = _natural_row()
    invalid["actual_missing_truth_available"] = True
    with pytest.raises(ValueError, match="actual missing days"):
        validate_natural_xgboost_rows(invalid)


def test_natural_validation_rejects_model_or_outer_contract_drift() -> None:
    invalid = _natural_row()
    invalid["implementation"] = "different_model"
    with pytest.raises(ValueError, match="expected XGBoost"):
        validate_natural_xgboost_rows(invalid)
    invalid = _natural_row()
    invalid["runner_contract_version"] = "different_split"
    with pytest.raises(ValueError, match="outer-fit contract"):
        validate_natural_xgboost_rows(invalid)


def test_stored_matched_geometry_result_is_complete_and_hash_bound() -> None:
    result_root = ROOT / "results/development_v11/matched_outage_geometry"
    summary = json.loads((result_root / "summary.json").read_text())
    assert summary["status"] == "complete_matched_planted_geometry"
    assert summary["actual_missing_days_scored"] is False
    assert summary["v11_empirical_curve_matched_rows"] == 1327
    assert summary["n_networks"] == 49
    assert summary["metrics"]["natural_empirical"]["network_spearman"] == pytest.approx(
        0.5664285714285714
    )
    for relative, expected in summary["input_bindings"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
    for name, expected in summary["output_bindings"].items():
        assert hashlib.sha256((result_root / name).read_bytes()).hexdigest() == expected

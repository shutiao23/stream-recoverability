"""Fault-injection tests for the extension replay comparator."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_replay():
    spec = importlib.util.spec_from_file_location(
        "extension_replay_983_test", ROOT / "scripts/983_verify_extension_replay.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def interval_frame():
    return pd.DataFrame(
        [
            {"family": "calendar", "scheme": "warm90", "n": 818, "stations": 41, "groups": 17,
             "contrast": "reference", "rmse_difference": 0.0, "ci_low": 0.0, "ci_high": 0.0,
             "seed": 20261031, "bootstraps": 10000},
            {"family": "calendar", "scheme": "cdf_all_years", "n": 818, "stations": 41, "groups": 17,
             "contrast": "cdf_all_years minus warm90", "rmse_difference": -0.015166,
             "ci_low": -0.045076, "ci_high": 0.000415, "seed": 20261031, "bootstraps": 10000},
        ]
    )


def write_pair(tmp_path, before, after, name="table.csv"):
    left = tmp_path / ("before_" + name)
    right = tmp_path / ("after_" + name)
    before.to_csv(left, index=False)
    after.to_csv(right, index=False)
    return left, right


def test_normal_interval_table_passes(tmp_path):
    module = load_replay()
    spec = module.revision_table_spec.TABLES["retention_paired_intervals.csv"]
    frame = interval_frame()
    left, right = write_pair(tmp_path, frame, frame)
    result = module.compare_table(left, right, spec)
    assert result["rows"] == 2
    assert result["max_finite_difference"] == 0.0


def test_structural_nan_is_allowed_only_where_declared(tmp_path):
    module = load_replay()
    spec = module.revision_table_spec.TABLES["retention_geometry_cases.csv"]
    row = {column: 0.0 for column in spec["columns"]}
    row.update({
        "family": "calendar", "station_key": "s", "replicate": 0,
        "independence_group": "g", "region": "r", "scheme": "uniform_exact",
        "retained_years": np.nan, "estimate_error": np.nan, "year_set_error": np.nan,
        "reconstruction_error": np.nan, "reference_residual_variance": np.nan,
    })
    frame = pd.DataFrame([row])
    left, right = write_pair(tmp_path, frame, frame)
    result = module.compare_table(left, right, spec)
    assert result["nan_pairs"] == 4


def test_finite_value_change_is_rejected(tmp_path):
    module = load_replay()
    spec = module.revision_table_spec.TABLES["retention_paired_intervals.csv"]
    before = interval_frame()
    after = before.copy()
    after.loc[1, "ci_low"] += 1e-6
    left, right = write_pair(tmp_path, before, after)
    with pytest.raises(module.ReplayComparisonError, match="exceeds tolerance|NaN pattern"):
        module.compare_table(left, right, spec)


def test_label_change_is_rejected(tmp_path):
    module = load_replay()
    spec = module.revision_table_spec.TABLES["retention_paired_intervals.csv"]
    before = interval_frame()
    after = before.copy()
    after.loc[1, "contrast"] = "wrong label"
    left, right = write_pair(tmp_path, before, after)
    with pytest.raises(module.ReplayComparisonError, match="label differs"):
        module.compare_table(left, right, spec)


def test_finite_to_nan_and_nan_to_finite_are_rejected(tmp_path):
    module = load_replay()
    spec = module.revision_table_spec.TABLES["retention_paired_intervals.csv"]
    before = interval_frame()
    after = before.copy()
    after.loc[1, "ci_low"] = np.nan
    left, right = write_pair(tmp_path, before, after, "finite_to_nan.csv")
    with pytest.raises(module.ReplayComparisonError, match="NaN"):
        module.compare_table(left, right, spec)
    before2 = before.copy()
    before2.loc[1, "ci_low"] = np.nan
    left2, right2 = write_pair(tmp_path, before2, before, "nan_to_finite.csv")
    with pytest.raises(module.ReplayComparisonError, match="unexpected NaN|NaN pattern"):
        module.compare_table(left2, right2, spec)


def test_duplicate_and_missing_keys_are_rejected(tmp_path):
    module = load_replay()
    spec = module.revision_table_spec.TABLES["retention_paired_intervals.csv"]
    before = interval_frame()
    duplicate = pd.concat([before, before.iloc[[1]]], ignore_index=True)
    left, right = write_pair(tmp_path, duplicate, before, "duplicate.csv")
    with pytest.raises(module.ReplayComparisonError, match="duplicate primary keys"):
        module.compare_table(left, right, spec)
    left2, right2 = write_pair(tmp_path, before.iloc[:1], before, "missing.csv")
    with pytest.raises(module.ReplayComparisonError, match="key set"):
        module.compare_table(left2, right2, spec)


def test_extra_column_is_rejected(tmp_path):
    module = load_replay()
    spec = module.revision_table_spec.TABLES["retention_paired_intervals.csv"]
    before = interval_frame()
    after = before.copy()
    after["unexpected"] = 1
    left, right = write_pair(tmp_path, before, after)
    with pytest.raises(module.ReplayComparisonError, match="column sets differ"):
        module.compare_table(left, right, spec)


def test_tolerance_is_absolute_not_default_relative(tmp_path):
    module = load_replay()
    spec = module.revision_table_spec.TABLES["retention_paired_intervals.csv"]
    before = interval_frame()
    after = before.copy()
    after.loc[1, "ci_low"] += 1e-13
    left, right = write_pair(tmp_path, before, after, "within.csv")
    assert module.compare_table(left, right, spec)["max_finite_difference"] <= 1e-12
    after2 = before.copy()
    after2.loc[1, "ci_low"] += 1e-6
    left2, right2 = write_pair(tmp_path, before, after2, "outside.csv")
    with pytest.raises(module.ReplayComparisonError, match="exceeds tolerance"):
        module.compare_table(left2, right2, spec)


def test_manifest_self_hash_and_stale_hash_are_rejected(tmp_path):
    module = load_replay()
    relative = Path("results/example")
    (tmp_path / relative).mkdir(parents=True)
    payload = tmp_path / relative / "table.csv"
    payload.write_text("a\n1\n")
    manifest = {"outputs": {"table.csv": module.digest(payload), "data_manifest.json": "0" * 64}}
    (tmp_path / relative / "data_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(module.ReplayComparisonError, match="must not record its own hash"):
        module.verify_manifest(tmp_path, relative)
    manifest["outputs"].pop("data_manifest.json")
    manifest["outputs"]["table.csv"] = "0" * 64
    (tmp_path / relative / "data_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(module.ReplayComparisonError, match="stale"):
        module.verify_manifest(tmp_path, relative)

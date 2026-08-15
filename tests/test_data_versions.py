from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.data.versions import (
    DATA_VERSION_NAMES,
    apply_data_version,
    build_data_versions,
    build_version_frames,
)


def _source_long() -> pd.DataFrame:
    dates = pd.to_datetime(
        [
            "2012-12-31",
            "2013-01-01",
            "2015-06-01",
            "2018-01-01",
            "2019-01-01",
            "2019-12-31",
            "2020-01-01",
        ]
    )
    variables = {
        "B1": ("T", "L"),
        "S2": ("T", "F", "L", "Ta"),
        "P3": ("T",),
    }
    rows = []
    raw = 1.0
    for date in dates:
        split = "train" if date.year <= 2015 else "test"
        for station, station_variables in variables.items():
            for variable in station_variables:
                rows.append(
                    {
                        "date": date,
                        "station_id": station,
                        "variable": variable,
                        "raw_value": raw,
                        "value": raw,
                        "natural_observed": True,
                        "quality_approved": True,
                        "qc_status": "observed_unflagged",
                        "split": split,
                    }
                )
                raw += 1.0
    return pd.DataFrame(rows)


def _unchanged_source_evidence(source: pd.DataFrame, versioned: pd.DataFrame) -> None:
    pd.testing.assert_series_equal(versioned["raw_value"], source["raw_value"])
    pd.testing.assert_series_equal(
        versioned["natural_observed"], source["natural_observed"]
    )
    pd.testing.assert_series_equal(
        versioned.index.to_series(), source.index.to_series()
    )


def test_registered_versions_apply_exact_fixed_transformations() -> None:
    source = _source_long()

    published = apply_data_version(source, "published_v1")
    _unchanged_source_evidence(source, published)
    pd.testing.assert_series_equal(published["value"], source["value"])
    assert set(published["data_version"]) == {"published_v1"}
    assert set(published["data_version_action"]) == {"unchanged"}

    no_s2 = apply_data_version(source, "no_s2_suspect_v1")
    _unchanged_source_evidence(source, no_s2)
    suspect = (
        no_s2["station_id"].eq("S2")
        & no_s2["variable"].isin(["T", "F", "L"])
        & no_s2["date"].between("2013-01-01", "2019-12-31", inclusive="both")
    )
    assert no_s2.loc[suspect, "value"].isna().all()
    assert not no_s2.loc[suspect, "quality_approved"].any()
    assert no_s2.loc[suspect, "qc_status"].eq("excluded_s2_suspect_period").all()
    assert no_s2.query("station_id == 'S2' and variable == 'Ta'")["value"].notna().all()
    assert no_s2.loc[~suspect, "value"].equals(source.loc[~suspect, "value"])

    no_level = apply_data_version(source, "b1_no_level_v1")
    _unchanged_source_evidence(source, no_level)
    b1_level = no_level["station_id"].eq("B1") & no_level["variable"].eq("L")
    assert no_level.loc[b1_level, "value"].isna().all()
    assert not no_level.loc[b1_level, "quality_approved"].any()

    shifted = apply_data_version(source, "b1_shift_sensitivity_v1")
    _unchanged_source_evidence(source, shifted)
    shift_target = (
        shifted["station_id"].eq("B1")
        & shifted["variable"].eq("L")
        & shifted["date"].ge("2019-01-01")
    )
    assert shifted.loc[shift_target, "value"].to_numpy() == pytest.approx(
        source.loc[shift_target, "value"].to_numpy() - 8.48
    )
    assert shifted.loc[~shift_target, "value"].equals(
        source.loc[~shift_target, "value"]
    )
    assert (
        shifted.loc[shift_target, "data_version_action"]
        .eq("hypothetical_b1_level_minus_8.48_m")
        .all()
    )


def test_each_version_refits_train_scaler_and_labels_every_row() -> None:
    source = _source_long()
    published_long, published_wide, published_scaler = build_version_frames(
        source, "published_v1"
    )
    no_s2_long, no_s2_wide, no_s2_scaler = build_version_frames(
        source, "no_s2_suspect_v1"
    )
    no_level_long, no_level_wide, no_level_scaler = build_version_frames(
        source, "b1_no_level_v1"
    )

    for name, long_data, wide_data, scaler in (
        ("published_v1", published_long, published_wide, published_scaler),
        ("no_s2_suspect_v1", no_s2_long, no_s2_wide, no_s2_scaler),
        ("b1_no_level_v1", no_level_long, no_level_wide, no_level_scaler),
    ):
        assert long_data["data_version"].eq(name).all()
        assert wide_data["data_version"].eq(name).all()
        assert scaler["data_version"] == name

    assert (
        no_s2_scaler["features"]["S2_T"]["observed_count"]
        < published_scaler["features"]["S2_T"]["observed_count"]
    )
    assert (
        no_s2_scaler["features"]["S2_T"]["mean"]
        != published_scaler["features"]["S2_T"]["mean"]
    )
    assert "B1_L" not in no_level_scaler["features"]
    assert no_level_scaler["excluded_features"]["B1_L"] == {
        "reason": "no_analysis_values_in_training_split"
    }


def test_builder_writes_immutable_versioned_artifacts_and_manifest(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "daily_long.parquet"
    _source_long().to_parquet(input_path, index=False)
    expected_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    output_root = tmp_path / "data_versions"

    manifests = build_data_versions(input_path, output_root, DATA_VERSION_NAMES)
    assert tuple(manifests) == DATA_VERSION_NAMES
    for name in DATA_VERSION_NAMES:
        version_dir = output_root / name
        expected_files = (
            "daily_long.parquet",
            "daily_wide.parquet",
            "scaler.json",
            "version_manifest.json",
            "splits/train.parquet",
            "splits/validation.parquet",
            "splits/test.parquet",
        )
        assert all((version_dir / relative).is_file() for relative in expected_files)
        stored_long = pd.read_parquet(version_dir / "daily_long.parquet")
        stored_wide = pd.read_parquet(version_dir / "daily_wide.parquet")
        stored_scaler = json.loads(
            (version_dir / "scaler.json").read_text(encoding="utf-8")
        )
        stored_manifest = json.loads(
            (version_dir / "version_manifest.json").read_text(encoding="utf-8")
        )
        assert stored_long["data_version"].eq(name).all()
        assert stored_wide["data_version"].eq(name).all()
        assert stored_scaler["data_version"] == name
        assert stored_manifest["data_version"] == name
        assert stored_manifest["input_sha256"] == expected_hash
        assert stored_manifest["input_counts"]["long_rows"] == len(_source_long())
        assert (
            stored_manifest["output_counts"]["wide_rows"]
            == _source_long()["date"].nunique()
        )
        for split in ("train", "validation", "test"):
            stored_split = pd.read_parquet(version_dir / "splits" / f"{split}.parquet")
            assert (
                stored_split["data_version"].eq(name).all()
                if not stored_split.empty
                else True
            )

    shift_manifest = manifests["b1_shift_sensitivity_v1"]
    assert shift_manifest["definition"]["sensitivity_only"] is True
    assert (
        "not a factual correction"
        in shift_manifest["definition"]["description"].lower()
    )
    assert shift_manifest["transformation_counts"]["analysis_values_adjusted"] > 0
    assert shift_manifest["transformation_counts"]["raw_values_changed"] == 0

    with pytest.raises(
        FileExistsError, match="Immutable data-version directories already exist"
    ):
        build_data_versions(input_path, output_root, ["published_v1"])


def test_unknown_or_derived_source_versions_are_rejected() -> None:
    source = _source_long()
    with pytest.raises(ValueError, match="Unknown data_version"):
        apply_data_version(source, "ad_hoc")
    source["data_version"] = "b1_shift_sensitivity_v1"
    with pytest.raises(ValueError, match="unversioned or published_v1"):
        apply_data_version(source, "published_v1")

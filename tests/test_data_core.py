from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.data.audit import audit_raw_data
from stream_recoverability.data.loading import (
    INCH_TO_MILLIMETRES,
    KNOT_TO_METRES_PER_SECOND,
    load_stations,
)
from stream_recoverability.data.prepare import (
    add_time_features,
    align_daily_calendar,
    build_windows,
    fit_train_scaler,
    prepare_daily_data,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"


def _station_frame(dates: pd.DatetimeIndex) -> pd.DataFrame:
    sequence = np.arange(len(dates), dtype=float)
    return pd.DataFrame(
        {
            "DATE": dates,
            "WTEMP": 10.0 + sequence,
            "WLEVEL": 100.0 + sequence,
            "FLOW": 2.0 * (100.0 + sequence) + 1.0,
            "TEMP": 8.0 + sequence,
            "WDSP": np.full(len(dates), 2.0),
            "PRCP": np.full(len(dates), 1.0),
            "RHMEAN": np.full(len(dates), 50.0),
            "DH": np.full(len(dates), 7.0),
        }
    )


def _write_three_stations(raw_dir: Path, dates: pd.DatetimeIndex) -> None:
    raw_dir.mkdir()
    for filename in ("b1.csv", "s2.csv", "p3.csv"):
        _station_frame(dates).to_csv(raw_dir / filename, index=False)


def test_metadata_conversion_codes_and_raw_values_are_preserved(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    dates = pd.date_range("2006-01-01", periods=3, freq="D")
    _write_three_stations(raw_dir, dates)
    b1 = pd.read_csv(raw_dir / "b1.csv")
    b1.loc[0, "WDSP"] = 999.9
    b1.loc[1, "PRCP"] = 99.99
    b1.to_csv(raw_dir / "b1.csv", index=False)

    dictionary = tmp_path / "data_dictionary.csv"
    pd.DataFrame(
        {
            "raw_name": ["WDSP", "PRCP"],
            "standard_name": ["W", "P"],
            "unit": ["knots", "inches"],
            "standard_unit": ["m/s", "mm"],
            "unit_conversion": ["value * 0.5", "value * 10"],
        }
    ).to_csv(dictionary, index=False)

    long_data = load_stations(raw_dir, dictionary)
    assert set(long_data["station_id"]) == {"B1", "S2", "P3"}
    special_wind = long_data.query("station_id == 'B1' and raw_name == 'WDSP'").iloc[0]
    assert special_wind["raw_value"] == pytest.approx(999.9)
    assert pd.isna(special_wind["value"])
    assert not bool(special_wind["natural_observed"])
    assert not bool(special_wind["quality_approved"])
    assert special_wind["qc_status"] == "source_missing"

    normal_wind = long_data.query("station_id == 'B1' and raw_name == 'WDSP'").iloc[1]
    normal_rain = long_data.query("station_id == 'B1' and raw_name == 'PRCP'").iloc[0]
    assert normal_wind["value"] == pytest.approx(1.0)
    assert normal_rain["value"] == pytest.approx(10.0)
    assert normal_wind["quality_approved"]
    assert normal_wind["analysis_eligible"]
    assert normal_wind["provider_qc_status"] == "unknown"
    assert normal_wind["qc_status"] == "observed_unflagged"


def test_default_conversions_apply_without_creating_metadata(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    _write_three_stations(raw_dir, pd.date_range("2006-01-01", periods=2, freq="D"))
    absent_dictionary = tmp_path / "metadata" / "data_dictionary.csv"
    long_data = load_stations(raw_dir, absent_dictionary)
    b1_wind = long_data.query("station_id == 'B1' and raw_name == 'WDSP'")["value"].iloc[0]
    b1_rain = long_data.query("station_id == 'B1' and raw_name == 'PRCP'")["value"].iloc[0]
    assert b1_wind == pytest.approx(2.0 * KNOT_TO_METRES_PER_SECOND)
    assert b1_rain == pytest.approx(INCH_TO_MILLIMETRES)
    assert not absent_dictionary.exists()


def test_conversion_factor_column_is_honoured(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    _write_three_stations(raw_dir, pd.date_range("2006-01-01", periods=2, freq="D"))
    dictionary = tmp_path / "data_dictionary.csv"
    pd.DataFrame(
        {
            "raw_name": ["WDSP", "PRCP"],
            "standard_name": ["W", "P"],
            "raw_unit": ["knot", "inch"],
            "standard_unit": ["m/s", "mm"],
            "conversion_factor": [0.25, 5.0],
        }
    ).to_csv(dictionary, index=False)
    long_data = load_stations(raw_dir, dictionary)
    assert long_data.query("station_id == 'B1' and raw_name == 'WDSP'")["value"].iloc[0] == pytest.approx(0.5)
    assert long_data.query("station_id == 'B1' and raw_name == 'PRCP'")["value"].iloc[0] == pytest.approx(5.0)


def test_alignment_inserts_source_missing_rows(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    _write_three_stations(raw_dir, pd.to_datetime(["2006-01-01", "2006-01-03"]))
    loaded = load_stations(raw_dir, tmp_path / "missing.csv")
    aligned = align_daily_calendar(loaded)
    inserted = aligned.loc[aligned["date"] == pd.Timestamp("2006-01-02")]
    assert len(inserted) == 3 * 8
    assert inserted["value"].isna().all()
    assert not inserted["natural_observed"].any()
    assert not inserted["quality_approved"].any()
    assert set(inserted["qc_status"]) == {"source_missing"}


def test_actual_audit_outputs_codes_known_events_and_limitations(tmp_path: Path) -> None:
    output_dir = tmp_path / "audit"
    tables = audit_raw_data(
        RAW_DIR,
        tmp_path / "missing-data-dictionary.csv",
        output_dir,
        minimum_constant_run=7,
    )
    assert set(tables) == {
        "variable_summary",
        "missing_code_summary",
        "date_continuity",
        "constant_runs",
        "rating_curve_diagnostics",
    }
    continuity = tables["date_continuity"].set_index("station_id")
    assert continuity["is_daily_continuous"].all()
    assert (continuity["unique_date_count"] == 5479).all()
    codes = tables["missing_code_summary"].set_index(["station_id", "raw_name"])
    assert int(codes.loc[("B1", "WDSP"), "count"]) == 11
    assert int(codes.loc[("B1", "PRCP"), "count"]) == 16
    assert int(codes.loc[("S2", "WDSP"), "count"]) == 5
    assert len(tables["rating_curve_diagnostics"]) == 45

    for name in (*tables, "data_quality_report"):
        suffix = ".md" if name == "data_quality_report" else ".csv"
        assert (output_dir / f"{name}{suffix}").exists()
    report = (output_dir / "data_quality_report.md").read_text(encoding="utf-8")
    assert "+8.48 m step" in report
    assert "November 2018 high-flow event" in report
    assert "neither is silently removed" in report
    assert "no per-value quality flags" in report
    assert "only excludes literal source missing values" in report


def test_prepare_writes_expected_tables_splits_and_train_scaler(tmp_path: Path) -> None:
    output_dir = tmp_path / "processed"
    long_data, wide_data, scaler = prepare_daily_data(
        RAW_DIR,
        tmp_path / "missing-data-dictionary.csv",
        output_dir,
    )
    assert len(wide_data) == 5479
    assert len(long_data) == 5479 * 3 * 8
    assert {
        "raw_value",
        "value",
        "natural_observed",
        "quality_approved",
        "qc_status",
        "analysis_eligible",
        "provider_qc_status",
        "known_issue_flag",
    }.issubset(long_data.columns)
    unflagged = long_data.loc[long_data["qc_status"].eq("observed_unflagged")]
    assert unflagged["provider_qc_status"].eq("unknown").all()
    assert not unflagged["provider_qc_status"].eq("approved").any()
    assert {"B1_T", "S2_F", "P3_Ta", "day_of_year_sin", "is_leap_year", "split"}.issubset(
        wide_data.columns
    )
    assert wide_data["split"].value_counts().to_dict() == {
        "train": 3652,
        "test": 1096,
        "validation": 731,
    }
    assert scaler["fitted_split"] == "train"
    assert scaler["features"]["B1_T"]["mean"] == pytest.approx(
        wide_data.loc[wide_data["split"] == "train", "B1_T"].mean()
    )

    assert (output_dir / "daily_long.parquet").exists()
    assert (output_dir / "daily_wide.parquet").exists()
    assert all((output_dir / "splits" / f"{split}.parquet").exists() for split in ("train", "validation", "test"))
    stored_scaler = json.loads((output_dir / "scaler.json").read_text(encoding="utf-8"))
    assert stored_scaler == scaler


def test_train_scaler_ignores_validation_and_test_values() -> None:
    wide = pd.DataFrame(
        {
            "split": ["train", "train", "validation", "test"],
            "B1_T": [1.0, 3.0, 1000.0, -1000.0],
        }
    )
    scaler = fit_train_scaler(wide, ["B1_T"])
    assert scaler["features"]["B1_T"] == {"mean": 2.0, "scale": 1.0, "observed_count": 2}


def test_time_features_preserve_leap_day() -> None:
    frame = pd.DataFrame({"date": pd.to_datetime(["2020-02-28", "2020-02-29", "2020-03-01"])})
    featured = add_time_features(frame)
    assert featured["is_leap_year"].all()
    assert len(featured) == 3
    angles = np.unwrap(np.arctan2(featured["day_of_year_sin"], featured["day_of_year_cos"]))
    assert np.diff(angles) == pytest.approx([2 * np.pi / 366, 2 * np.pi / 366])


@pytest.mark.parametrize("window_size", [184, 368, 736])
def test_supported_windows_have_expected_shape(window_size: int) -> None:
    length = 800
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2006-01-01", periods=length, freq="D"),
            "split": "train",
            "B1_T": np.arange(length, dtype=float),
            "B1_F": np.arange(length, dtype=float) * 2,
        }
    )
    values, dates, features = build_windows(frame, window_size, ["B1_T", "B1_F"])
    assert values.shape == (length - window_size + 1, window_size, 2)
    assert dates.shape == (length - window_size + 1, window_size)
    assert features == ("B1_T", "B1_F")
    assert values[0, 0, 0] == 0
    assert values[-1, -1, 0] == length - 1


def test_windows_reject_cross_split_input() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2006-01-01", periods=200, freq="D"),
            "split": ["train"] * 100 + ["validation"] * 100,
            "B1_T": np.arange(200, dtype=float),
        }
    )
    with pytest.raises(ValueError, match="single split"):
        build_windows(frame, 184, ["B1_T"])

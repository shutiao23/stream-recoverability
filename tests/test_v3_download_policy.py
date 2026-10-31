from __future__ import annotations

import pandas as pd
import pytest

from stream_recoverability.data.ingest_qc import clean_long_frame, qc_long_frame
from stream_recoverability.data.v3_download_policy import (
    deterministic_stratified_sample,
    plan_v3_development_pilot,
)


def test_development_pilot_is_reproducible() -> None:
    first = plan_v3_development_pilot()
    second = plan_v3_development_pilot()
    assert first == second
    assert first["pilot_size"] == 20
    assert len(first["networks"]) == 20
    assert first["n_validation_selected"] == 0
    assert first["n_sealed_selected"] == 0
    assert first["sealed_temperature_records_read"] is False
    assert first["retired_name_huc2_plan_used"] is False
    assert {row["role"] for row in first["networks"]} == {"development"}
    assert all(len(row["stations"]) >= 3 for row in first["networks"])
    assert all(
        station["start"] <= station["end"]
        for row in first["networks"]
        for station in row["stations"]
    )


def test_stratified_sampler_rejects_non_development_rows() -> None:
    row = {
        "network_id": "huc8_x",
        "role": "sealed",
        "climate_band": "x",
        "regulation_stratum": "x",
        "size_tertile": "x",
        "never_sealed": False,
    }
    with pytest.raises(ValueError, match="non-development"):
        deterministic_stratified_sample([row], n=1)


def test_qc_long_precedes_wide_and_rejected_station_is_absent() -> None:
    dates = pd.date_range("2010-01-01", periods=8 * 365, freq="D")
    good_values = 10.0 + (pd.Series(range(len(dates))) % 200) / 100.0
    frame = pd.concat(
        [
            pd.DataFrame(
                {
                    "site_id": "good",
                    "date": dates,
                    "temperature_c": good_values,
                    "qualifier": "A",
                }
            ),
            pd.DataFrame(
                {
                    "site_id": "sentinel",
                    "date": dates,
                    "temperature_c": [8.0] * (len(dates) - 1) + [-999999.0],
                    "qualifier": "A",
                }
            ),
        ],
        ignore_index=True,
    )
    report = qc_long_frame(frame)
    clean = clean_long_frame(frame, report=report, min_qualified_years=8)
    assert set(clean["site_id"]) == {"good"}
    rejected = report.set_index("site_id").loc["sentinel"]
    assert rejected["verdict"] == "rejected_sentinel"


def test_nonapproved_values_are_removed_from_clean_long() -> None:
    dates = pd.date_range("2020-01-01", periods=301, freq="D")
    frame = pd.DataFrame(
        {
            "site_id": "x",
            "date": dates,
            "temperature_c": 10.0 + pd.Series(range(len(dates))) / 100.0,
            "qualifier": ["A"] * 300 + ["P"],
        }
    )
    report = qc_long_frame(frame)
    clean = clean_long_frame(frame, report=report)
    assert len(clean) == 300
    assert clean["qualifier"].eq("A").all()

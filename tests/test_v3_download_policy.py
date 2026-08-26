from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest
import yaml

from stream_recoverability.data.ingest_qc import clean_long_frame, qc_long_frame
from stream_recoverability.data.v3_download_policy import (
    LOCKED_SPLIT_SHA256,
    deterministic_stratified_sample,
    plan_v3_development_pilot,
    verify_split_lock,
)


def test_repository_split_lock_and_development_pilot_are_exact() -> None:
    assert verify_split_lock() == LOCKED_SPLIT_SHA256
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
    selected_ids = "\n".join(row["network_id"] for row in first["networks"]) + "\n"
    assert hashlib.sha256(selected_ids.encode("utf-8")).hexdigest() == first[
        "sample_network_ids_sha256"
    ]


def test_split_lock_fails_closed_before_planning(tmp_path: Path) -> None:
    canonical = tmp_path / "split.csv"
    canonical.write_text("network_id,role\nx,development\n", encoding="utf-8")
    observed = hashlib.sha256(canonical.read_bytes()).hexdigest()
    split = tmp_path / "split.yaml"
    split.write_text(
        yaml.safe_dump(
            {
                "status": "locked_before_download",
                "temperatures_downloaded": False,
                "sealed_outcomes_opened": False,
                "sha256": observed,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="split lock mismatch"):
        verify_split_lock(
            split_path=split,
            canonical_path=canonical,
            expected_sha256=LOCKED_SPLIT_SHA256,
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

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.data.internal_rs import (
    merge_rs_into_long,
    parse_power_rs_response,
    rebuild_internal_rs_panel,
)


def _payload() -> dict[str, object]:
    return {
        "type": "Feature",
        "header": {
            "time_standard": "UTC",
            "start": "20060101",
            "end": "20060103",
            "fill_value": -999,
            "api": {"name": "POWER Daily API"},
        },
        "geometry": {"type": "Point", "coordinates": [99.08, 29.85]},
        "parameters": {"ALLSKY_SFC_SW_DWN": {"units": "MJ/m^2/day"}},
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": {
                    "20060101": 12.5,
                    "20060102": -999,
                    "20060103": 18.0,
                }
            }
        },
    }


def test_parse_power_rs_keeps_utc_and_marks_fill_missing() -> None:
    frame, metadata = parse_power_rs_response(
        _payload(), start="2006-01-01", end="2006-01-03", time_standard="UTC"
    )
    assert metadata["n_days"] == 3
    assert metadata["n_finite"] == 2
    assert frame.loc[frame["date"].eq("2006-01-02"), "quality_approved"].eq(False).all()
    assert frame.loc[frame["date"].eq("2006-01-01"), "value"].iloc[0] == pytest.approx(
        12.5
    )


def test_merge_does_not_rename_dh_or_edit_hydro() -> None:
    dates = pd.to_datetime(["2006-01-01", "2006-01-02", "2006-01-03"])
    rows = []
    for station in ("B1", "S2", "P3"):
        for date in dates:
            for variable, value in (("T", 4.0), ("Ta", 1.0), ("DH", 8.0)):
                rows.append(
                    {
                        "date": date,
                        "station_id": station,
                        "variable": variable,
                        "raw_name": variable,
                        "raw_value": value,
                        "value": value,
                        "raw_unit": "x",
                        "unit": "x",
                        "natural_observed": True,
                        "quality_approved": True,
                        "qc_status": "observed_unflagged",
                        "source": "legacy",
                        "split": "train",
                    }
                )
    long_data = pd.DataFrame(rows)
    rs = pd.DataFrame(
        {
            "date": np.tile(dates, 3),
            "station_id": np.repeat(["B1", "S2", "P3"], 3),
            "value": 15.0,
            "raw_value": 15.0,
            "natural_observed": True,
            "quality_approved": True,
            "qc_status": "provider_value",
        }
    )
    merged = merge_rs_into_long(long_data, rs)
    assert set(merged["variable"]) == {"T", "Ta", "DH", "Rs"}
    assert merged.loc[merged["variable"].eq("DH"), "value"].eq(8.0).all()
    assert merged.loc[merged["variable"].eq("T"), "value"].eq(4.0).all()
    assert (
        merged.loc[merged["variable"].eq("Rs"), "raw_name"]
        .eq("ALLSKY_SFC_SW_DWN")
        .all()
    )


def test_rebuild_uses_fetcher_not_silent_dh(tmp_path) -> None:
    metadata = tmp_path / "stations.csv"
    pd.DataFrame(
        {
            "station_id": ["B1", "S2", "P3"],
            "latitude": [29.85, 26.9, 26.6],
            "longitude": [99.08, 99.95, 101.74],
        }
    ).to_csv(metadata, index=False)
    dates = pd.to_datetime(["2006-01-01", "2006-01-02", "2006-01-03"])
    rows = []
    for station in ("B1", "S2", "P3"):
        for date in dates:
            rows.append(
                {
                    "date": date,
                    "station_id": station,
                    "variable": "Ta",
                    "raw_name": "TEMP",
                    "raw_value": 1.0,
                    "value": 1.0,
                    "raw_unit": "degC",
                    "unit": "degC",
                    "natural_observed": True,
                    "quality_approved": True,
                    "qc_status": "observed_unflagged",
                    "source": "legacy",
                    "split": "train",
                }
            )
    long_data = pd.DataFrame(rows)

    def fake_fetch(url: str, headers: dict[str, str]) -> tuple[int, bytes, str]:
        payload = _payload()
        return 200, json.dumps(payload).encode("utf-8"), url

    merged, report = rebuild_internal_rs_panel(
        long_data,
        metadata,
        start="2006-01-01",
        end="2006-01-03",
        fetcher=fake_fetch,
    )
    assert report["rs_rows"] == 9
    assert merged["variable"].eq("Rs").sum() == 9
    assert not merged["variable"].eq("DH").any()

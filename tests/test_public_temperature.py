from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.data.public_river_inventory import summarize_river
from stream_recoverability.data.public_temperature import missing_gap_catalog, overlap_report


def test_overlap_and_real_gaps() -> None:
    dates = pd.date_range("2010-01-01", periods=400, freq="D")
    wide = pd.DataFrame(
        {
            "a": np.linspace(1, 2, 400),
            "b": np.linspace(2, 3, 400),
            "c": np.linspace(3, 4, 400),
            "d": np.linspace(4, 5, 400),
        },
        index=dates,
    )
    wide.loc[dates[10:25], "a"] = np.nan
    report = overlap_report(wide, min_stations=3)
    assert report["n_stations"] == 4
    assert report["days_with_min_stations"] == 400
    gaps = missing_gap_catalog(wide)
    assert gaps.loc[gaps["site_id"].eq("a"), "length_days"].iloc[0] == 15


def test_summarize_river_needs_four_long_records() -> None:
    frame = pd.DataFrame(
        {
            "site_id": ["1", "2", "3", "4"],
            "found": [True] * 4,
            "has_daily_temperature": [True] * 4,
            "daily_begin": ["2000-01-01"] * 4,
            "daily_end": ["2012-01-01"] * 4,
            "span_years": [12.0] * 4,
        }
    )
    summary = summarize_river(frame)
    assert summary["enough_stations"]
    assert summary["enough_overlap_years"]

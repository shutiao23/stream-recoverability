from __future__ import annotations

import pandas as pd
import pytest

from stream_recoverability.data.lubw_temperature import (
    candidate_networks,
    station_catalog,
    utm32_to_wgs84,
)


def test_utm_conversion_matches_baden_wuerttemberg_station() -> None:
    latitude, longitude = utm32_to_wgs84(448686.29, 5428914.55)
    assert latitude == pytest.approx(49.012, abs=0.01)
    assert longitude == pytest.approx(8.298, abs=0.01)


def test_station_catalog_and_candidate_grouping() -> None:
    daily = pd.DataFrame(
        {
            "site_id": ["A", "B", "C"],
            "station_name": ["A", "B", "C"],
            "river": ["Rhein", "Rhein", "Rhein"],
            "easting": [448686.29] * 3,
            "northing": [5428914.55] * 3,
            "date": pd.to_datetime(["2020-01-01"] * 3),
            "temperature_c": [1.0, 2.0, 3.0],
            "qualifier": ["A"] * 3,
            "provider_quality_status": ["published_daily_mean"] * 3,
        }
    )
    catalog = station_catalog(daily)
    candidates = candidate_networks(catalog)
    assert len(catalog) == 3
    assert candidates["network_id"].tolist() == ["lubw_rhein"]
    assert candidates["site_ids"].tolist() == ["A|B|C"]

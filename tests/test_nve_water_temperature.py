from __future__ import annotations

import pandas as pd

from stream_recoverability.data.nve_water_temperature import candidate_networks


def test_nve_candidates_require_three_stations_and_eight_common_years() -> None:
    catalog = pd.DataFrame(
        {
            "site_id": ["1.1.0", "1.2.0", "1.3.0", "2.1.0", "2.2.0"],
            "basin_id": ["1", "1", "1", "2", "2"],
            "latitude": [60.0] * 5,
            "longitude": [10.0] * 5,
            "daily_start": pd.to_datetime(["2000-01-01"] * 5, utc=True),
            "daily_end": pd.to_datetime(["2020-01-01"] * 5, utc=True),
        }
    )
    result = candidate_networks(catalog)
    assert tuple(result["network_id"]) == ("nve_basin_1",)
    assert result.iloc[0]["n_catalog_stations"] == 3
    assert result.iloc[0]["catalog_common_years"] >= 11.9

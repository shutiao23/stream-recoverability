from __future__ import annotations

import pandas as pd

from stream_recoverability.data.syke_surface_temperature import candidate_networks


def test_candidate_partition_uses_each_station_once() -> None:
    catalog = pd.DataFrame(
        {
            "site_id": ["1", "2", "3", "4", "5", "6"],
            "subbasin": ["SUB", "SUB", "SUB", "A", "B", "C"],
            "main_basin": ["MAIN"] * 6,
            "latitude": [60.0] * 6,
            "longitude": [25.0] * 6,
        }
    )
    candidates = candidate_networks(catalog)
    assert len(candidates) == 2
    rosters = [set(value.split("|")) for value in candidates["site_ids"]]
    assert rosters[0].isdisjoint(rosters[1])
    assert set.union(*rosters) == set(catalog["site_id"])

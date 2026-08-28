from __future__ import annotations

import pandas as pd

from stream_recoverability.data.smhi_water_temperature import (
    candidate_networks,
    parse_csv,
)


def test_csv_parser_keeps_only_g_quality() -> None:
    payload = """Stationsnamn;StationsId
Station;1

Datum (svensk sommartid);Vattendragstemperatur;Kvalitet;;
2000-01-01;1.2;G;;
2000-01-02;1.3;Y;;
2000-01-03;1.4;O;;
""".encode()
    daily, counts = parse_csv(payload, "1")
    assert daily["temperature_c"].tolist() == [1.2]
    assert daily["qualifier"].tolist() == ["A"]
    assert dict(counts) == {"G": 1, "Y": 1, "O": 1}


def test_candidate_builder_requires_three_stations_with_g() -> None:
    catalog = pd.DataFrame(
        {
            "site_id": ["1", "2", "3", "4"],
            "catchment_name": ["GÖTA ÄLV"] * 4,
            "latitude": [1.0, 2.0, 3.0, 4.0],
            "longitude": [5.0, 6.0, 7.0, 8.0],
        }
    )
    quality = pd.DataFrame(
        {
            "site_id": ["1", "2", "3", "4"],
            "n_g_days": [10, 10, 10, 0],
        }
    )
    candidates = candidate_networks(catalog, quality)
    assert candidates["network_id"].tolist() == ["smhi_goeta_aelv"]
    assert candidates["site_ids"].tolist() == ["1|2|3"]

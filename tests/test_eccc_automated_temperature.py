from __future__ import annotations

import pandas as pd

from stream_recoverability.data.eccc_automated_temperature import (
    candidate_networks,
    daily_mean,
    parse_csv,
    station_file_map,
)


def test_inventory_groups_file_parts_by_station() -> None:
    inventory = [
        {
            "name": "auto-water-qual-eau-NB01AJ0008-2016-present.csv",
            "path": "data/one.csv",
        },
        {
            "name": "auto-water-qual-eau-NB01AJ0008_2012-2015.csv",
            "path": "data/two.csv",
        },
        {"name": "auto-water-qual-eau-stations.csv", "path": "data/stations.csv"},
    ]
    assert station_file_map(inventory) == {
        "NB01AJ0008": ("data/one.csv", "data/two.csv")
    }


def test_parser_keeps_validated_water_temperature_and_makes_daily_mean() -> None:
    payload = b"""STATION_NO,DATE_TIME_HEURE,FLAG_FANION,VALUE_VALEUR,VMV_CODE,UNIT_UNIT,VARIABLE,VARIABLE_FR,STATUS_STATUT,GRADE_COTE
S1,24/06/2014 17:30,,20,4730,DEG C,TEMPERATURE WATER,,V,
S1,24/06/2014 18:00,,22,4730,DEG C,TEMPERATURE WATER,,V,
S1,24/06/2014 18:00,,200,4729,US/CM,SPECIFIC CONDUCTANCE,,V,
S1,06/25/2014 18:00:00,,19,4730,DEG C,TEMPERATURE WATER,,V,
S1,25/06/2014 18:00,,99,4730,DEG C,TEMPERATURE WATER,,R,
"""
    hourly = parse_csv(payload, "S1")
    daily = daily_mean([hourly])
    assert daily["temperature_c"].tolist() == [21.0, 19.0]
    assert daily["hourly_observations"].tolist() == [2, 1]


def test_candidate_networks_are_disjoint_three_station_systems() -> None:
    stations = pd.DataFrame(
        {
            "STATION_NO": ["A", "B", "C", "D"],
            "PEARSEDA": ["SYSTEM ONE", "SYSTEM ONE", "SYSTEM ONE", "OTHER"],
            "LATITUDE": [1.0, 2.0, 3.0, 4.0],
            "LONGITUDE": [-1.0, -2.0, -3.0, -4.0],
        }
    )
    files = {value: (f"{value}.csv",) for value in stations["STATION_NO"]}
    candidates = candidate_networks(stations, files)
    assert candidates["network_id"].tolist() == ["eccc_automated_system_one"]
    assert candidates["site_ids"].tolist() == ["A|B|C"]

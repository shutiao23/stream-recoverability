from __future__ import annotations

import json

import pandas as pd

from stream_recoverability.data.chmi_temperature import candidate_plan, parse_year


def test_parse_year_reads_official_time_series_shape() -> None:
    payload = json.dumps(
        {
            "objID": "station",
            "tsList": [
                {
                    "tsConID": "TO",
                    "unit": "0C",
                    "tsData": {
                        "data": {
                            "values": [
                                ["2020-01-01T00:00:00Z", 1.2],
                                ["2020-01-01T01:00:00Z", 1.3],
                            ]
                        }
                    },
                }
            ],
        }
    ).encode()
    frame = parse_year(payload, "station")
    assert frame["temperature_c"].tolist() == [1.2, 1.3]


def test_candidate_plan_requires_eight_common_file_years() -> None:
    catalog = pd.DataFrame(
        {
            "site_id": ["A", "B", "C", "D"],
            "station_name": ["A", "B", "C", "D"],
            "river": ["River"] * 4,
            "latitude": [1.0] * 4,
            "longitude": [2.0] * 4,
            "basin_code": ["x"] * 4,
        }
    )
    rows = []
    for site_id, years in {
        "A": range(2000, 2010),
        "B": range(2000, 2010),
        "C": range(2000, 2010),
        "D": range(2008, 2010),
    }.items():
        for year in years:
            rows.append(
                {
                    "site_id": site_id,
                    "year": year,
                    "file_name": f"{site_id}_{year}.json",
                }
            )
    candidates, station_files = candidate_plan(catalog, pd.DataFrame(rows))
    assert candidates["site_ids"].tolist() == ["A|B|C"]
    assert candidates["n_common_file_years"].tolist() == [10]
    assert set(station_files) == {"A", "B", "C"}

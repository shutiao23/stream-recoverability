from __future__ import annotations

from pathlib import Path
import json
import urllib.parse

import numpy as np
import pandas as pd

from stream_recoverability.data.confirmation_daily_qc import (
    foen_request,
    hubeau_window_url,
    parse_foen_daily,
    parse_usgs_network,
    qc_candidate_network,
    site_ids,
    usgs_network_url,
)


def test_provider_urls_and_station_roster_are_plain_requests() -> None:
    assert site_ids("01|02|03") == ("01", "02", "03")
    usgs = urllib.parse.urlparse(
        usgs_network_url(("01", "02"), "2000-01-01", "2020-01-01")
    )
    usgs_query = urllib.parse.parse_qs(usgs.query)
    assert usgs_query["sites"] == ["01,02"]
    assert usgs_query["parameterCd"] == ["00010"]
    assert usgs_query["statCd"] == ["00003"]

    hubeau = urllib.parse.urlparse(
        hubeau_window_url("03156350", "2000-01-01", "2020-01-01")
    )
    hubeau_query = urllib.parse.parse_qs(hubeau.query)
    assert hubeau_query["code_station"] == ["03156350"]
    assert hubeau_query["code_qualification"] == ["1"]


def test_parse_usgs_network_retains_each_station_and_approval_code() -> None:
    document = {
        "value": {
            "timeSeries": [
                {
                    "sourceInfo": {"siteCode": [{"value": station}]},
                    "values": [
                        {
                            "value": [
                                {
                                    "dateTime": "2020-01-01T00:00:00.000-05:00",
                                    "value": value,
                                    "qualifiers": ["A"],
                                }
                            ]
                        }
                    ],
                }
                for station, value in (("01", "4.2"), ("02", "5.3"))
            ]
        }
    }
    frame = parse_usgs_network(document)
    assert frame["site_id"].tolist() == ["01", "02"]
    assert frame["temperature_c"].tolist() == [4.2, 5.3]
    assert frame["qualifier"].eq("A").all()
    assert frame["date"].eq(pd.Timestamp("2020-01-01")).all()


def test_foen_query_and_parser_keep_release_states_two_and_three() -> None:
    request = foen_request("2016", "2000-01-01", "2026-01-01")
    body = json.loads(request.data.decode("utf-8"))
    assert "data_1day_mean" in body["query"]
    assert 'parameterName: { _eq: "WT" }' in body["query"]
    assert body["variables"]["station"] == "2016"
    document = {
        "data": {
            "water": {
                "observations": {
                    "data_1day_mean": [
                        {
                            "timestamp": f"2020-01-0{state}T00:00:00Z",
                            "parameterName": "WT",
                            "value": 5.0 + state,
                            "unitSymbol": "°C",
                            "releaseState": state,
                            "station": {"no": "2016"},
                        }
                        for state in (1, 2, 3)
                    ]
                }
            }
        }
    }
    frame = parse_foen_daily(document, "2016")
    assert frame["temperature_c"].tolist() == [7.0, 8.0]
    assert frame["qualifier"].eq("A").all()


def _qualified_daily() -> pd.DataFrame:
    dates = pd.DatetimeIndex(
        np.concatenate(
            [
                pd.date_range(f"{year}-01-01", periods=300, freq="D").to_numpy()
                for year in range(2011, 2020)
            ]
        )
    )
    rows = []
    for offset, station in enumerate(("01", "02", "03")):
        day = np.arange(len(dates), dtype=float)
        rows.append(
            pd.DataFrame(
                {
                    "site_id": station,
                    "date": dates,
                    "temperature_c": 9.0
                    + offset
                    + 5.0 * np.sin(2.0 * np.pi * day / 365.25),
                    "qualifier": "A",
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def test_real_daily_qc_writes_network_tables_and_qualifies_overlap(
    tmp_path: Path,
) -> None:
    candidate = {
        "network_id": "new_river",
        "provider": "usgs",
        "river_group": "new river",
        "site_ids": "01|02|03",
    }
    result = qc_candidate_network(candidate, _qualified_daily(), tmp_path)
    directory = tmp_path / "networks/new_river"
    assert result["complete_enough"] is True
    assert result["n_eligible_stations"] == 3
    assert result["n_concurrent_days"] == 2700
    assert (directory / "daily_wide_temperature.csv").is_file()
    assert (directory / "network_qc.csv").is_file()
    wide = pd.read_csv(directory / "daily_wide_temperature.csv")
    qc = pd.read_csv(directory / "network_qc.csv")
    assert set(wide.columns) == {"date", "01", "02", "03"}
    assert qc["eligible_for_network"].all()


def test_unapproved_hubeau_values_are_measured_but_not_network_eligible(
    tmp_path: Path,
) -> None:
    raw = _qualified_daily()
    raw["qualifier"] = "P"
    candidate = {
        "network_id": "hubeau_new_river",
        "provider": "hubeau",
        "river_group": "new river",
        "site_ids": "01|02|03",
    }
    result = qc_candidate_network(candidate, raw, tmp_path)
    qc = pd.read_csv(tmp_path / "networks/hubeau_new_river/network_qc.csv")
    assert result["n_stations_with_values"] == 3
    assert result["n_eligible_stations"] == 0
    assert result["complete_enough"] is False
    assert qc["n_provisional_dropped"].gt(0).all()

from __future__ import annotations

import inspect
from unittest.mock import patch

import pandas as pd

from stream_recoverability.data.nldi_connectivity import (
    connectivity_from_neighbor_ids,
    nwis_match_key,
    parse_nldi_nwissite_ids,
    pick_median_origin,
)
from stream_recoverability.data.public_river_inventory import (
    cluster_by_huc8,
    cluster_rivers_from_catalog,
    cluster_rivers_from_catalog_v2,
    largest_overlapping_subset,
    official_huc_digits,
    official_huc_prefix,
    naive_huc_zfill_prefix,
)


def test_v1_cluster_defaults_are_unchanged() -> None:
    signature = inspect.signature(cluster_rivers_from_catalog)
    assert signature.parameters["min_stations"].default == 4
    assert signature.parameters["min_overlap_years"].default == 8.0
    assert signature.parameters["min_span_years"].default == 8.0


def test_cluster_by_huc8_signature_defaults() -> None:
    signature = inspect.signature(cluster_by_huc8)
    assert list(signature.parameters)[:5] == [
        "series_df",
        "locations_df",
        "min_stations",
        "min_overlap_years",
        "max_pair_km",
    ]
    assert signature.parameters["locations_df"].default is None
    assert signature.parameters["min_stations"].default == 3
    assert signature.parameters["min_overlap_years"].default == 8
    assert signature.parameters["max_pair_km"].default is None


def test_official_huc_leading_zero_and_naive_zfill_intent() -> None:
    """Reviewer zfill(8)[:8] is the intent; official_huc_prefix is the implementation."""

    assert official_huc_digits("3130004") == "03130004"
    assert official_huc_prefix("3130004", 8) == "03130004"
    assert str("3130004").zfill(8)[:8] == "03130004"
    assert official_huc_prefix("190101060106.0", 8) == "19010106"
    assert official_huc_prefix("3150202", 8) == "03150202"
    assert official_huc_prefix("11000020108", 8) == "01100002"
    assert str("11000020108").zfill(8)[:8] == "11000020"
    assert official_huc_prefix("11000020108", 8) != str("11000020108").zfill(8)[:8]


def test_different_names_same_huc8_form_one_cluster() -> None:
    series = pd.DataFrame(
        {
            "site_id": ["1", "2", "3"],
            "daily_begin": ["2000-01-01"] * 3,
            "daily_end": ["2010-01-01"] * 3,
            "span_years": [10.0] * 3,
            "huc": ["03150202"] * 3,
            "name": [
                "Alpha River at A",
                "Beta Creek near B",
                "Gamma Brook above C",
            ],
            "latitude": [33.0, 33.05, 33.1],
            "longitude": [-86.0, -86.05, -86.1],
            "site_type": ["Stream"] * 3,
        }
    )
    frame = cluster_by_huc8(series, None, min_stations=3, min_overlap_years=8)
    assert len(frame) == 1
    assert str(frame.iloc[0]["grouping"]) == "huc8"
    assert str(frame.iloc[0]["network_id"]) == "huc8_03150202"
    assert int(frame.iloc[0]["n_stations"]) == 3
    names = str(frame.iloc[0]["river_names"])
    assert "Alpha River" in names
    assert "Beta Creek" in names
    assert "Gamma Brook" in names


def test_same_name_two_huc8s_are_two_clusters() -> None:
    series = pd.DataFrame(
        {
            "site_id": list("abcdef"),
            "daily_begin": ["2000-01-01"] * 6,
            "daily_end": ["2012-01-01"] * 6,
            "span_years": [12.0] * 6,
            "huc": ["03150202"] * 3 + ["03170101"] * 3,
            "name": [f"Same River at {item}" for item in "ABCDEF"],
            "latitude": [32.0, 32.05, 32.1, 33.0, 33.05, 33.1],
            "longitude": [-86.0, -86.05, -86.1, -85.0, -85.05, -85.1],
            "site_type": ["ST"] * 6,
        }
    )
    huc8 = cluster_by_huc8(series, None, min_stations=3, min_overlap_years=8)
    assert len(huc8) == 2
    assert set(huc8["network_id"]) == {"huc8_03150202", "huc8_03170101"}
    v2 = cluster_rivers_from_catalog_v2(
        series,
        pd.DataFrame(),
        min_stations=3,
        min_overlap_years=8.0,
        min_span_years=8.0,
        huc_levels=("huc2",),
        include_huc8_only=False,
    )
    name_huc2 = v2.loc[v2["grouping"].eq("name_huc2")]
    assert len(name_huc2) == 1
    assert int(name_huc2.iloc[0]["n_stations"]) == 6


def test_max_pair_km_filters_a_geographically_huge_triple() -> None:
    series = pd.DataFrame(
        {
            "site_id": ["a", "b", "c"],
            "daily_begin": ["2001-01-01"] * 3,
            "daily_end": ["2012-01-01"] * 3,
            "span_years": [11.0] * 3,
            "huc": ["02040101"] * 3,
            "name": ["Wide River at A", "Wide River at B", "Wide River at C"],
            "latitude": [25.0, 40.0, 48.0],
            "longitude": [-80.0, -74.0, -122.0],
            "site_type": ["Streamgage"] * 3,
        }
    )
    unfiltered = cluster_by_huc8(series, None, min_stations=3, min_overlap_years=8)
    assert len(unfiltered) == 1
    assert float(unfiltered.iloc[0]["max_pair_km"]) > 100.0
    filtered = cluster_by_huc8(
        series, None, min_stations=3, min_overlap_years=8, max_pair_km=50
    )
    assert filtered.empty
    nearby = series.copy()
    nearby["latitude"] = [33.0, 33.02, 33.04]
    nearby["longitude"] = [-86.0, -86.02, -86.04]
    kept = cluster_by_huc8(
        nearby, None, min_stations=3, min_overlap_years=8, max_pair_km=50
    )
    assert len(kept) == 1
    assert float(kept.iloc[0]["max_pair_km"]) <= 50.0


def test_largest_overlapping_subset_keeps_thirteen_concurrent_stations() -> None:
    n_stations = 13
    series = pd.DataFrame(
        {
            "site_id": [f"{index:08d}" for index in range(n_stations)],
            "daily_begin": ["2000-01-01"] * n_stations,
            "daily_end": ["2012-06-01"] * n_stations,
            "span_years": [12.4] * n_stations,
            "huc": ["17090001"] * n_stations,
            "name": [f"Long River at {index}" for index in range(n_stations)],
            "latitude": [45.0 + 0.01 * index for index in range(n_stations)],
            "longitude": [-123.0 - 0.01 * index for index in range(n_stations)],
            "site_type": ["Stream"] * n_stations,
        }
    )
    with patch(
        "stream_recoverability.data.public_river_inventory.largest_overlapping_subset",
        wraps=largest_overlapping_subset,
    ) as spy:
        frame = cluster_by_huc8(series, None, min_stations=3, min_overlap_years=8)
    assert spy.called
    assert len(frame) == 1
    assert int(frame.iloc[0]["n_stations"]) == 13
    assert int(frame.iloc[0]["n_stations_available"]) == 13
    chosen, _, _, years = largest_overlapping_subset(
        series["daily_begin"], series["daily_end"], min_overlap_years=8.0
    )
    assert len(chosen) == 13
    assert years >= 8.0


def test_odd_length_huc_groups_under_official_prefix() -> None:
    series = pd.DataFrame(
        {
            "site_id": ["x", "y", "z"],
            "daily_begin": ["2000-01-01"] * 3,
            "daily_end": ["2011-01-01"] * 3,
            "span_years": [11.0] * 3,
            "huc": ["3150202", "3150202.0", 3150202.0],
            "name": ["Pad River at X", "Pad River near Y", "Pad River above Z"],
            "latitude": [33.0, 33.01, 33.02],
            "longitude": [-86.5, -86.51, -86.52],
            "site_type": ["Stream"] * 3,
        }
    )
    frame = cluster_by_huc8(series, None, min_stations=3, min_overlap_years=8)
    assert len(frame) == 1
    assert str(frame.iloc[0]["network_id"]) == "huc8_03150202"
    assert str(frame.iloc[0]["huc8"]) == "03150202"


def test_nldi_parser_fixture_json_no_live_network() -> None:
    document = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "USGS-01434000",
                "properties": {
                    "identifier": "USGS-01434000",
                    "name": "DELAWARE RIVER AT PORT JERVIS NY",
                    "source": "nwissite",
                },
            },
            {
                "type": "Feature",
                "id": "USGS-01427510",
                "properties": {"identifier": "USGS-01427510"},
            },
            {
                "type": "Feature",
                "properties": {
                    "uri": "https://waterdata.usgs.gov/monitoring-location/USGS-01432805"
                },
            },
        ],
    }
    parsed = parse_nldi_nwissite_ids(document)
    keys = {nwis_match_key(item) for item in parsed}
    assert nwis_match_key("01434000") in keys
    assert nwis_match_key("USGS-01427510") in keys
    assert nwis_match_key("1432805") in keys
    origin = pick_median_origin(
        pd.DataFrame(
            {
                "site_id": ["01434000", "01427510", "01432805"],
                "latitude": [41.4, 41.3, 41.5],
                "longitude": [-74.7, -74.8, -74.6],
            }
        )
    )
    assert str(origin["site_id"]) == "01434000"
    connected = connectivity_from_neighbor_ids(
        "01434000",
        ["01434000", "01427510", "09999999"],
        parsed,
        queried=True,
    )
    assert connected["flow_connected"] == "partial"
    assert int(connected["n_connected_stations"]) == 2
    assert connected["spatially_proximate_not_flow_connected"] is True
    missing = connectivity_from_neighbor_ids(
        "01434000",
        ["01434000", "09999999", "08888888"],
        parsed,
        queried=True,
    )
    assert missing["flow_connected"] == "false"
    assert missing["spatially_proximate_not_flow_connected"] is True
    failed = connectivity_from_neighbor_ids(
        "01434000", ["01434000", "01427510"], [], queried=False
    )
    assert failed["flow_connected"] == "not_queried"
    assert failed["spatially_proximate_not_flow_connected"] is False
    all_hit = connectivity_from_neighbor_ids(
        "01434000",
        ["01434000", "01427510", "01432805"],
        parsed,
        queried=True,
    )
    assert all_hit["flow_connected"] == "true"
    assert int(all_hit["n_connected_stations"]) == 3
    assert all_hit["spatially_proximate_not_flow_connected"] is False


def test_naive_zfill_splits_huc12_that_official_prefix_keeps() -> None:
    series = pd.DataFrame(
        {
            "site_id": ["a", "b", "c"],
            "daily_begin": ["2000-01-01"] * 3,
            "daily_end": ["2011-01-01"] * 3,
            "span_years": [11.0] * 3,
            "huc": ["031602040402", "31602040402", "31602040402.0"],
            "name": ["Toy River at A", "Toy River near B", "Toy River above C"],
            "latitude": [31.0, 31.01, 31.02],
            "longitude": [-87.0, -87.01, -87.02],
            "site_type": ["Stream"] * 3,
        }
    )
    official = cluster_by_huc8(series, None, min_stations=3, min_overlap_years=8)
    assert len(official) == 1
    assert str(official.iloc[0]["network_id"]) == "huc8_03160204"
    naive = cluster_by_huc8(
        series,
        None,
        min_stations=3,
        min_overlap_years=8,
        huc_prefix=naive_huc_zfill_prefix,
    )
    assert naive.empty
    assert naive_huc_zfill_prefix("31602040402", 8) != official_huc_prefix(
        "31602040402", 8
    )
    assert naive_huc_zfill_prefix("11000020108", 8) == "11000020"

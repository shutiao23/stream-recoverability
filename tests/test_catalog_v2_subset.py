from __future__ import annotations

import inspect

import pandas as pd

from stream_recoverability.data.public_river_inventory import (
    cluster_rivers_from_catalog,
    cluster_rivers_from_catalog_v2,
    largest_overlapping_subset,
    official_huc_digits,
    official_huc_prefix,
)


def test_v1_cluster_defaults_are_unchanged() -> None:
    signature = inspect.signature(cluster_rivers_from_catalog)
    assert signature.parameters["min_stations"].default == 4
    assert signature.parameters["min_overlap_years"].default == 8.0
    assert signature.parameters["min_span_years"].default == 8.0


def test_official_huc_restores_leading_zero() -> None:
    assert official_huc_digits("3130004") == "03130004"
    assert official_huc_digits("3130004.0") == "03130004"
    assert official_huc_digits(3130004.0) == "03130004"
    assert official_huc_prefix("190101060106.0", 2) == "19"
    assert official_huc_prefix("190101060106.0", 8) == "19010106"
    assert official_huc_prefix("11000020108", 2) == "01"
    assert official_huc_prefix("11000020108", 8) == "01100002"


def test_largest_overlapping_subset_drops_the_short_station() -> None:
    begins = ["2000-01-01", "2000-01-01", "2000-01-01", "2018-01-01"]
    ends = ["2012-01-01", "2012-01-01", "2012-01-01", "2019-06-01"]
    chosen, start, stop, years = largest_overlapping_subset(
        begins, ends, min_overlap_years=8.0
    )
    assert chosen == [0, 1, 2]
    assert start.date().isoformat() == "2000-01-01"
    assert stop.date().isoformat() == "2012-01-01"
    assert years >= 8.0


def test_largest_overlapping_subset_cannot_keep_three_when_intersection_is_six() -> None:
    begins = ["2000-01-01", "2002-01-01", "2004-01-01"]
    ends = ["2010-01-01", "2012-01-01", "2014-01-01"]
    chosen_eight, _, _, _ = largest_overlapping_subset(
        begins, ends, min_overlap_years=8.0
    )
    assert len(chosen_eight) == 2
    chosen_six, _, _, years = largest_overlapping_subset(
        begins, ends, min_overlap_years=6.0
    )
    assert chosen_six == [0, 1, 2]
    assert years >= 6.0


def test_largest_overlapping_subset_prefers_larger_set_over_longer_pair() -> None:
    begins = ["2000-01-01", "2000-01-01", "2000-01-01", "2010-01-01"]
    ends = ["2020-01-01", "2020-01-01", "2020-01-01", "2020-01-01"]
    chosen, start, _, _ = largest_overlapping_subset(
        begins, ends, min_overlap_years=8.0
    )
    assert chosen == [0, 1, 2, 3]
    assert start.date().isoformat() == "2010-01-01"


def test_largest_overlapping_subset_tie_breaks_on_longer_intersection() -> None:
    begins = ["2000-01-01", "2000-01-01", "2000-01-01", "2012-01-01", "2012-01-01", "2012-01-01"]
    ends = ["2010-01-01", "2010-01-01", "2010-01-01", "2018-01-01", "2018-01-01", "2018-01-01"]
    chosen, start, stop, years = largest_overlapping_subset(
        begins, ends, min_overlap_years=6.0
    )
    assert chosen == [0, 1, 2]
    assert start.date().isoformat() == "2000-01-01"
    assert stop.date().isoformat() == "2010-01-01"
    assert years > 8.0


def test_largest_overlapping_subset_empty_when_no_T_year_cover() -> None:
    chosen, start, stop, years = largest_overlapping_subset(
        ["2000-01-01", "2000-01-01"],
        ["2003-01-01", "2003-01-01"],
        min_overlap_years=8.0,
    )
    assert chosen == []
    assert pd.isna(start) and pd.isna(stop)
    assert pd.isna(years)


def _toy_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Three long concurrent stations plus one later station that kills v1 overlap."""

    series = pd.DataFrame(
        {
            "site_id": ["01100001", "01100002", "01100003", "01100004"],
            "daily_begin": ["2000-01-01", "2000-01-01", "2000-01-01", "2018-01-01"],
            "daily_end": ["2015-01-01", "2015-01-01", "2015-01-01", "2026-01-01"],
            "span_years": [15.0, 15.0, 15.0, 8.0],
            "huc": ["03150202", "03150202", "03150202", "03150202"],
            "state_name": ["Alabama"] * 4,
        }
    )
    locations = pd.DataFrame(
        {
            "site_id": ["01100001", "01100002", "01100003", "01100004"],
            "name": [
                "Toy River at Upstream",
                "Toy River near Midreach",
                "Toy River above Town",
                "Toy River below Dam",
            ],
            "latitude": [33.0, 33.1, 33.2, 33.3],
            "longitude": [-86.0, -86.1, -86.2, -86.3],
            "huc": ["03150202"] * 4,
            "site_type": ["Stream"] * 4,
            "found": [True] * 4,
        }
    )
    return series, locations


def test_v1_still_uses_whole_group_overlap() -> None:
    series, locations = _toy_tables()
    v1 = cluster_rivers_from_catalog(
        series, locations, min_stations=4, min_overlap_years=8.0, min_span_years=8.0
    )
    assert len(v1) == 1
    assert bool(v1.loc[0, "enough_overlap_years"]) is False
    assert float(v1.loc[0, "catalog_overlap_years"]) < 8.0


def test_v2_keeps_largest_concurrent_subset() -> None:
    series, locations = _toy_tables()
    v2 = cluster_rivers_from_catalog_v2(
        series,
        locations,
        min_stations=3,
        min_overlap_years=8.0,
        min_span_years=6.0,
        huc_levels=("huc2",),
        include_huc8_only=False,
    )
    name_rows = v2.loc[v2["grouping"].eq("name_huc2")]
    assert len(name_rows) == 1
    assert int(name_rows.iloc[0]["n_stations"]) == 3
    assert "01100004" not in str(name_rows.iloc[0]["site_ids"])
    assert float(name_rows.iloc[0]["catalog_overlap_years"]) >= 8.0
    v2_four = cluster_rivers_from_catalog_v2(
        series,
        locations,
        min_stations=4,
        min_overlap_years=8.0,
        min_span_years=6.0,
        huc_levels=("huc2",),
        include_huc8_only=False,
    )
    assert v2_four.empty


def test_v2_huc8_only_is_labelled_and_not_a_name_group() -> None:
    series = pd.DataFrame(
        {
            "site_id": ["1", "2", "3", "4"],
            "daily_begin": ["2001-01-01"] * 4,
            "daily_end": ["2012-01-01"] * 4,
            "span_years": [11.0] * 4,
            "huc": ["03150202"] * 4,
            "state_name": ["Alabama"] * 4,
        }
    )
    locations = pd.DataFrame(
        {
            "site_id": ["1", "2", "3", "4"],
            "name": [
                "Alpha River at A",
                "Alpha River near B",
                "Alpha River above C",
                "Beta Creek at D",
            ],
            "latitude": [1.0, 1.1, 1.2, 1.3],
            "longitude": [-1.0, -1.1, -1.2, -1.3],
            "huc": ["03150202"] * 4,
            "site_type": ["ST"] * 4,
            "found": [True] * 4,
        }
    )
    frame = cluster_rivers_from_catalog_v2(
        series,
        locations,
        min_stations=3,
        min_overlap_years=8.0,
        min_span_years=6.0,
        huc_levels=("huc2", "huc8"),
        include_huc8_only=True,
    )
    assert set(frame["grouping"]) == {"name_huc2", "name_huc8", "huc8_only"}
    name_huc2 = frame.loc[frame["grouping"].eq("name_huc2")]
    assert set(name_huc2["river_name"]) == {"Alpha River"}
    assert int(name_huc2.iloc[0]["n_stations"]) == 3
    huc8_only = frame.loc[frame["grouping"].eq("huc8_only")]
    assert len(huc8_only) == 1
    assert str(huc8_only.iloc[0]["grouping"]) == "huc8_only"
    assert int(huc8_only.iloc[0]["n_stations"]) == 4
    assert str(huc8_only.iloc[0]["network_id"]).startswith("huc8_")
    assert "name_huc2" not in str(huc8_only.iloc[0]["grouping"])


def test_v2_casefolds_river_names_before_grouping() -> None:
    series = pd.DataFrame(
        {
            "site_id": ["1", "2", "3"],
            "daily_begin": ["2000-01-01"] * 3,
            "daily_end": ["2012-01-01"] * 3,
            "span_years": [12.0] * 3,
            "huc": ["02040101"] * 3,
            "state_name": ["Pennsylvania"] * 3,
        }
    )
    locations = pd.DataFrame(
        {
            "site_id": ["1", "2", "3"],
            "name": [
                "DELAWARE RIVER at Trenton NJ",
                "Delaware River near Philadelphia PA",
                "Delaware River above Trenton NJ",
            ],
            "latitude": [40.0, 40.1, 40.2],
            "longitude": [-75.0, -75.1, -75.2],
            "huc": ["02040101"] * 3,
            "site_type": ["Stream"] * 3,
            "found": [True] * 3,
        }
    )
    frame = cluster_rivers_from_catalog_v2(
        series,
        locations,
        min_stations=3,
        min_overlap_years=8.0,
        min_span_years=6.0,
        huc_levels=("huc2",),
        include_huc8_only=False,
    )
    name_rows = frame.loc[frame["grouping"].eq("name_huc2")]
    assert len(name_rows) == 1
    assert int(name_rows.iloc[0]["n_stations"]) == 3
    assert str(name_rows.iloc[0]["network_id"]) == "delaware_river_huc02"


def test_v2_name_huc4_splits_when_huc4_differs() -> None:
    series = pd.DataFrame(
        {
            "site_id": ["a", "b", "c", "d", "e", "f"],
            "daily_begin": ["2000-01-01"] * 6,
            "daily_end": ["2012-01-01"] * 6,
            "span_years": [12.0] * 6,
            "huc": ["03150202"] * 3 + ["03170101"] * 3,
            "state_name": ["Alabama"] * 6,
        }
    )
    locations = pd.DataFrame(
        {
            "site_id": list("abcdef"),
            "name": [f"Split River at {item}" for item in "ABCDEF"],
            "latitude": [1.0, 1.1, 1.2, 2.0, 2.1, 2.2],
            "longitude": [-1.0, -1.1, -1.2, -2.0, -2.1, -2.2],
            "huc": ["03150202"] * 3 + ["03170101"] * 3,
            "site_type": ["Stream"] * 6,
            "found": [True] * 6,
        }
    )
    frame = cluster_rivers_from_catalog_v2(
        series,
        locations,
        min_stations=3,
        min_overlap_years=8.0,
        min_span_years=6.0,
        huc_levels=("huc2", "huc4"),
        include_huc8_only=False,
    )
    assert len(frame.loc[frame["grouping"].eq("name_huc2")]) == 1
    assert int(frame.loc[frame["grouping"].eq("name_huc2")].iloc[0]["n_stations"]) == 6
    assert len(frame.loc[frame["grouping"].eq("name_huc4")]) == 2

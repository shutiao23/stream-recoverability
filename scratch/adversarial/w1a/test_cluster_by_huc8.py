"""Runnable tests for the competing W1-A HUC8 implementation.

These tests encode the adversarial holes: naive zfill, 12-station truncation,
degree-vs-geodesic caps, missing coordinates, NLDI parse/404, and never_sealed.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE
for parent in (HERE, *HERE.parents):
    if (parent / "src" / "stream_recoverability").is_dir():
        REPO = parent
        break
SRC = REPO / "src"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cluster_by_huc8 import (  # noqa: E402
    assignment_digest,
    cluster_by_huc8,
    geodesic_km,
    largest_overlapping_subset_truncated,
    lock_stratified_split,
    naive_reviewer_huc8,
    pairwise_geodesic_stats,
    tag_never_sealed,
)
from nldi_connectivity import (  # noqa: E402
    annotate_group_connectivity,
    as_site_id,
    nldi_match_keys,
    nldi_navigation_url,
    parse_nldi_feature_collection,
    pick_median_station,
    query_nldi_direction,
)
from stream_recoverability.data.public_river_inventory import (  # noqa: E402
    largest_overlapping_subset,
    official_huc_digits,
    official_huc_prefix,
)


def _sites(
    ids: list[str],
    *,
    huc: list[str] | str,
    names: list[str] | None = None,
    begins: list[str] | str = "2000-01-01",
    ends: list[str] | str = "2012-01-01",
    lats: list[float] | None = None,
    lons: list[float] | None = None,
    site_type: str = "Stream",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = len(ids)
    hucs = [huc] * n if isinstance(huc, str) else list(huc)
    begin = [begins] * n if isinstance(begins, str) else list(begins)
    end = [ends] * n if isinstance(ends, str) else list(ends)
    start = pd.to_datetime(begin)
    stop = pd.to_datetime(end)
    span = [(b - a).days / 365.25 for a, b in zip(start, stop)]
    series = pd.DataFrame(
        {
            "site_id": ids,
            "daily_begin": begin,
            "daily_end": end,
            "span_years": span,
            "huc": hucs,
            "state_name": ["Test"] * n,
        }
    )
    locations = pd.DataFrame(
        {
            "site_id": ids,
            "name": names or [f"Toy River at {item}" for item in ids],
            "latitude": lats if lats is not None else [33.0 + 0.01 * i for i in range(n)],
            "longitude": lons if lons is not None else [-86.0 - 0.01 * i for i in range(n)],
            "huc": hucs,
            "site_type": [site_type] * n,
            "found": [True] * n,
        }
    )
    return series, locations


def test_naive_zfill_fails_on_twelve_digit_hucs_official_prefix_succeeds() -> None:
    """Attack 1: reviewer ``huc.zfill(8)[:8]`` is wrong on HUC12 / float strings."""

    huc12 = "031602040402"
    as_float = float(huc12)  # 31602040402.0 — leading zero dies
    as_float_str = str(as_float)  # "31602040402.0"

    assert official_huc_digits(huc12) == "031602040402"
    assert official_huc_prefix(huc12, 8) == "03160204"
    assert official_huc_prefix(as_float, 8) == "03160204"
    assert official_huc_prefix(as_float_str, 8) == "03160204"
    assert official_huc_prefix("190101060106.0", 8) == "19010106"
    assert official_huc_prefix("11000020108", 8) == "01100002"
    assert official_huc_prefix("3130004", 8) == "03130004"
    assert official_huc_prefix("nan", 8) == ""

    assert naive_reviewer_huc8(huc12) == "03160204"  # leading zero still present
    assert naive_reviewer_huc8(as_float_str) == "31602040"
    assert naive_reviewer_huc8(as_float) != official_huc_prefix(as_float, 8)
    assert naive_reviewer_huc8("190101060106.0") == "19010106"  # coincidentally same
    assert naive_reviewer_huc8("11000020108") == "11000020"
    assert naive_reviewer_huc8("11000020108") != official_huc_prefix("11000020108", 8)
    assert naive_reviewer_huc8("31602040402") == "31602040"
    assert naive_reviewer_huc8("31602040402") != official_huc_prefix("31602040402", 8)
    assert naive_reviewer_huc8("nan") == "00000nan"
    assert official_huc_prefix("nan", 8) == ""

    # Grouping consequence: same three stations, two keys under naive zfill.
    ids = ["a", "b", "c"]
    series, locations = _sites(
        ids,
        huc=["031602040402", "31602040402", "31602040402.0"],
        names=["A Creek at 1", "B Creek at 2", "C Creek at 3"],
    )
    official = cluster_by_huc8(series, locations, min_stations=3, min_overlap_years=8)
    naive = cluster_by_huc8(
        series,
        locations,
        min_stations=3,
        min_overlap_years=8,
        huc_encoder=lambda value, width: naive_reviewer_huc8(value)[:width],
    )
    assert len(official) == 1
    assert str(official.iloc[0]["huc8"]) == "03160204"
    assert len(naive) == 0 or str(naive.iloc[0]["huc8"]) != "03160204" or len(naive) != 1
    # Official keeps one HUC8. Naive splits 03160204 vs 31602040 and drops both (<3).
    assert len(naive) == 0


def test_different_names_same_huc8_make_one_cluster() -> None:
    series, locations = _sites(
        ["1", "2", "3"],
        huc="03150202",
        names=["Alpha River at A", "Beta Creek at B", "Gamma Brook at C"],
    )
    frame = cluster_by_huc8(series, locations, min_stations=3, min_overlap_years=8)
    assert len(frame) == 1
    assert str(frame.iloc[0]["network_id"]) == "huc8_03150202"
    assert int(frame.iloc[0]["n_stations"]) == 3
    assert int(frame.iloc[0]["n_stations_available"]) == 3
    assert "Alpha River" in str(frame.iloc[0]["river_names"])
    assert str(frame.iloc[0]["grouping"]) == "huc8"
    assert frame.iloc[0]["overlap_start"] is not None
    assert frame.iloc[0]["overlap_end"] is not None


def test_same_name_two_huc8s_make_two_clusters() -> None:
    series, locations = _sites(
        ["1", "2", "3", "4", "5", "6"],
        huc=["02040101"] * 3 + ["02040105"] * 3,
        names=["Delaware River at " + x for x in "ABCDEF"],
    )
    frame = cluster_by_huc8(series, locations, min_stations=3, min_overlap_years=8)
    assert len(frame) == 2
    assert set(frame["huc8"]) == {"02040101", "02040105"}


def test_exact_search_keeps_thirteen_concurrent_stations() -> None:
    """Attack 2: no truncation at 12. A 13-station concurrent group keeps 13."""

    ids = [f"{i:08d}" for i in range(13)]
    series, locations = _sites(ids, huc="17090004")
    frame = cluster_by_huc8(series, locations, min_stations=3, min_overlap_years=8)
    assert len(frame) == 1
    assert int(frame.iloc[0]["n_stations"]) == 13
    assert int(frame.iloc[0]["n_stations_available"]) == 13


def test_truncated_combo_undercounts_vs_exact() -> None:
    """12 long isolated stations hide a shorter concurrent triple after truncation."""

    isolated_ids = [f"1{i:07d}" for i in range(12)]
    isolated_begins = [f"{1900 + i * 8:04d}-01-01" for i in range(12)]
    isolated_ends = [f"{1914 + i * 8:04d}-01-01" for i in range(12)]
    triple_ids = ["20000001", "20000002", "20000003"]
    ids = isolated_ids + triple_ids
    begins = isolated_begins + ["2000-01-01"] * 3
    ends = isolated_ends + ["2010-01-01"] * 3
    series, locations = _sites(ids, huc="10190001", begins=begins, ends=ends)
    exact = cluster_by_huc8(
        series, locations, min_stations=3, min_overlap_years=8, overlap_search="exact"
    )
    truncated = cluster_by_huc8(
        series,
        locations,
        min_stations=3,
        min_overlap_years=8,
        overlap_search="truncated_combo",
    )
    assert len(exact) == 1
    assert int(exact.iloc[0]["n_stations"]) == 3
    assert set(str(exact.iloc[0]["site_ids"]).split(",")) == set(triple_ids)
    assert truncated.empty

    chosen, _, _, years = largest_overlapping_subset_truncated(
        begins, ends, min_overlap_years=8.0, max_n=12, min_size=3
    )
    assert chosen == []
    exact_idx, _, _, exact_years = largest_overlapping_subset(
        begins, ends, min_overlap_years=8.0
    )
    assert len(exact_idx) == 3
    assert exact_years >= 8.0


def test_max_pair_km_is_geodesic_not_degree_span() -> None:
    """Attack 4: 0.6° longitude is ~60 km in Florida and ~23 km in Alaska."""

    florida_km = geodesic_km(25.0, -80.0, 25.0, -79.4)
    alaska_km = geodesic_km(70.0, -150.0, 70.0, -149.4)
    assert florida_km > 50.0
    assert alaska_km < 50.0
    assert alaska_km < florida_km

    fl_series, fl_loc = _sites(
        ["f1", "f2", "f3"],
        huc="03090202",
        lats=[25.0, 25.0, 25.0],
        lons=[-80.0, -79.7, -79.4],
    )
    ak_series, ak_loc = _sites(
        ["a1", "a2", "a3"],
        huc="19020101",
        lats=[70.0, 70.0, 70.0],
        lons=[-150.0, -149.7, -149.4],
    )
    fl = cluster_by_huc8(
        fl_series, fl_loc, min_stations=3, min_overlap_years=8, max_pair_km=50.0
    )
    ak = cluster_by_huc8(
        ak_series, ak_loc, min_stations=3, min_overlap_years=8, max_pair_km=50.0
    )
    assert fl.empty, "Florida 0.6° lon exceeds 50 km geodesic"
    assert len(ak) == 1, "Alaska 0.6° lon is under 50 km geodesic"
    assert float(ak.iloc[0]["max_pair_km"]) < 50.0
    # Degree-span of 0.6 is identical; a degree cap cannot distinguish them.
    assert abs((ak_loc["longitude"].max() - ak_loc["longitude"].min()) - 0.6) < 1e-9
    assert abs((fl_loc["longitude"].max() - fl_loc["longitude"].min()) - 0.6) < 1e-9


def test_missing_coords_are_nan_never_zero_or_inf() -> None:
    """Attack 5: unlocated stations do not silently become 0 km or inf km."""

    series, locations = _sites(
        ["1", "2", "3"],
        huc="03130001",
        lats=[33.0, None, 33.2],
        lons=[-86.0, None, -86.2],
    )
    frame = cluster_by_huc8(series, locations, min_stations=3, min_overlap_years=8)
    assert len(frame) == 1
    value = frame.iloc[0]["max_pair_km"]
    assert value is None or pd.notna(value)
    assert math.isfinite(float(value))
    assert float(value) != 0.0 or int(frame.iloc[0]["n_stations_with_coords"]) >= 2
    assert int(frame.iloc[0]["n_stations_missing_coords"]) == 1
    assert bool(frame.iloc[0]["coords_incomplete"]) is True
    assert str(frame.iloc[0]["coord_policy"]) == "partial_coords"

    stats = pairwise_geodesic_stats([None, None, None], [None, None, None])
    assert math.isnan(stats["max_pair_km"])
    assert stats["max_pair_km"] != 0
    assert stats["max_pair_km"] != float("inf")
    assert stats["coord_policy"] == "no_coords"

    one = pairwise_geodesic_stats([33.0, None], [-86.0, None])
    assert math.isnan(one["max_pair_km"])
    assert one["coord_policy"] == "single_coord"

    capped = cluster_by_huc8(
        series, locations, min_stations=3, min_overlap_years=8, max_pair_km=50.0
    )
    # Cap requires located stations; 2 located < 3 after dropping unlocated.
    assert capped.empty


def test_distance_filter_omits_rather_than_silently_shrinking() -> None:
    series, locations = _sites(
        ["1", "2", "3"],
        huc="14010001",
        lats=[39.0, 39.0, 40.5],
        lons=[-106.0, -106.05, -108.0],
    )
    uncapped = cluster_by_huc8(series, locations, min_stations=3, min_overlap_years=8)
    filtered = cluster_by_huc8(
        series, locations, min_stations=3, min_overlap_years=8, max_pair_km=50.0
    )
    shrunk = cluster_by_huc8(
        series,
        locations,
        min_stations=3,
        min_overlap_years=8,
        max_pair_km=50.0,
        distance_mode="shrink",
    )
    assert len(uncapped) == 1
    assert int(uncapped.iloc[0]["n_stations"]) == 3
    assert filtered.empty
    # Shrink still cannot keep 3 stations inside 50 km (the far one must go).
    assert shrunk.empty or int(shrunk.iloc[0]["n_stations"]) < 3


def test_nldi_parser_handles_prefix_int_empty_and_404(tmp_path: Path) -> None:
    """Attack 6: USGS- prefix, int ids, empty FeatureCollection, HTTP 404."""

    document = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"identifier": "USGS-01608500"}},
            {"type": "Feature", "id": "USGS-01608501"},
            {"type": "Feature", "properties": {"identifier": 1608502}},
        ],
    }
    parsed = parse_nldi_feature_collection(document)
    assert "01608500" in parsed
    assert "01608501" in parsed
    assert "1608502" in parsed or "01608502" in parsed
    assert "01608500" in nldi_match_keys("USGS-01608500")
    assert nldi_match_keys("01608500") & nldi_match_keys("USGS-01608500")
    assert nldi_match_keys(1608500) & nldi_match_keys("01608500")

    empty = parse_nldi_feature_collection({"type": "FeatureCollection", "features": []})
    assert empty == set()
    assert parse_nldi_feature_collection({"type": "FeatureCollection", "features": None}) == set()
    assert parse_nldi_feature_collection(None) == set()
    assert parse_nldi_feature_collection("not json") == set()

    def boom_404(url: str, **kwargs: object) -> dict:
        raise RuntimeError(f"HTTP 404 for {url}")

    ids, status = query_nldi_direction(
        "01608500",
        "UM",
        cache_dir=tmp_path,
        get_json=boom_404,
        pause_s=0,
    )
    assert ids == set()
    assert status == "isolated_404"

    def boom_429(url: str, **kwargs: object) -> dict:
        raise RuntimeError(f"HTTP 429 for {url}")

    ids429, status429 = query_nldi_direction(
        "01608500",
        "DM",
        cache_dir=tmp_path,
        get_json=boom_429,
        pause_s=0,
    )
    assert ids429 == set()
    assert status429 == "rate_limited"

    url = nldi_navigation_url("USGS-01608500", "UM")
    assert "nwissite/USGS-01608500/navigation/UM/nwissite" in url
    assert as_site_id("USGS-01427301") == "01427301"
    assert as_site_id(1427301.0) == "1427301" or as_site_id("01427301.0") == "01427301"


def test_disconnected_nldi_group_is_marked_not_deleted(tmp_path: Path) -> None:
    def isolated(url: str, **kwargs: object) -> dict:
        raise RuntimeError(f"HTTP 404 for {url}")

    payload = annotate_group_connectivity(
        ["01100001", "01100002", "01100003"],
        [33.0, 33.1, 33.2],
        [-86.0, -86.1, -86.2],
        cache_dir=tmp_path,
        get_json=isolated,
        pause_s=0,
        query=True,
    )
    assert payload["flow_connected"] == "false"
    assert payload["spatially_proximate_not_flow_connected"] is True
    assert int(payload["n_connected_stations"]) == 1
    # The group itself is still a dict of covariates, not omitted.

    connected_doc = {
        "type": "FeatureCollection",
        "features": [
            {"properties": {"identifier": "USGS-01100001"}},
            {"properties": {"identifier": "USGS-01100002"}},
            {"properties": {"identifier": "USGS-01100003"}},
        ],
    }

    def ok(url: str, **kwargs: object) -> dict:
        return connected_doc

    good = annotate_group_connectivity(
        ["01100001", "01100002", "01100003"],
        [33.0, 33.1, 33.2],
        [-86.0, -86.1, -86.2],
        cache_dir=tmp_path / "ok",
        get_json=ok,
        pause_s=0,
        query=True,
    )
    assert good["flow_connected"] == "true"
    assert good["spatially_proximate_not_flow_connected"] is False
    assert int(good["n_connected_stations"]) == 3


def test_median_station_tie_breaks_on_lon_then_site_id() -> None:
    origin = pick_median_station(
        [10.0, 10.0, 10.0],
        [-1.0, 0.0, 1.0],
        ["c", "a", "b"],
    )
    assert origin == "a"


def test_never_sealed_cannot_be_sealed_and_loire_cannot_fill() -> None:
    """Attack 8: burned rivers stay out of sealed; Loire/Swiss are absent."""

    series, locations = _sites(
        ["01427301", "01427207", "01427510"],
        huc="02040101",
        names=["Delaware River at A", "Delaware River at B", "Delaware River at C"],
    )
    extra, extra_loc = _sites(
        ["x1", "x2", "x3"],
        huc="17090001",
        names=["Other River at A", "Other River at B", "Other River at C"],
        lats=[45.0, 45.1, 45.2],
        lons=[-123.0, -123.1, -123.2],
    )
    series = pd.concat([series, extra], ignore_index=True)
    locations = pd.concat([locations, extra_loc], ignore_index=True)
    frame = cluster_by_huc8(series, locations, min_stations=3, min_overlap_years=8)
    burned = {
        "delaware_river_huc20": {
            "split_role": "development",
            "site_ids": {"01427301", "01427207", "01427510"},
            "historical_seen": False,
        }
    }
    tagged = tag_never_sealed(frame, burned)
    split, digest = lock_stratified_split(tagged, seed=20260826)
    delaware = split.loc[split["huc8"].eq("02040101")].iloc[0]
    assert bool(delaware["never_sealed"]) is True
    assert str(delaware["split_role"]) != "sealed"
    assert "loire_mainstem" not in set(split["network_id"])
    assert "swiss_aar_rhine" not in set(split["network_id"])
    assert len(digest) == 64
    other = split.loc[split["huc8"].eq("17090001")]
    if not other.empty and not bool(other.iloc[0]["never_sealed"]):
        assert str(other.iloc[0]["split_role"]) in {
            "development",
            "validation",
            "sealed",
        }
    assert assignment_digest("huc8_02040101", 20260826) == assignment_digest(
        "huc8_02040101", 20260826
    )
    assert assignment_digest("huc8_02040101", 1) != assignment_digest("huc8_02040101", 2)


def test_cluster_outputs_required_columns() -> None:
    series, locations = _sites(["1", "2", "3"], huc="03130004")
    frame = cluster_by_huc8(series, locations)
    required = {
        "network_id",
        "huc8",
        "n_stations",
        "n_stations_available",
        "site_ids",
        "overlap_start",
        "overlap_end",
        "catalog_overlap_years",
        "max_pair_km",
        "n_stations_with_coords",
        "river_names",
        "grouping",
    }
    assert required.issubset(frame.columns)
    assert str(frame.iloc[0]["network_id"]).startswith("huc8_")


def test_odd_length_hucs_from_on_disk_examples() -> None:
    assert official_huc_prefix("3130004", 8) == "03130004"
    assert official_huc_prefix("3150202", 8) == "03150202"
    assert official_huc_prefix("190101060106.0", 8) == "19010106"
    assert official_huc_prefix("31602040402", 8) == "03160204"
    series, locations = _sites(
        ["023432415", "023432416", "023432417"],
        huc="3130004",
        names=["Chattahoochee River at A", "Chattahoochee River at B", "Chattahoochee River at C"],
    )
    frame = cluster_by_huc8(series, locations, min_stations=3, min_overlap_years=8)
    assert len(frame) == 1
    assert str(frame.iloc[0]["huc8"]) == "03130004"


def test_series_without_locations_df_still_clusters() -> None:
    series, locations = _sites(["1", "2", "3"], huc="05030103")
    combined = series.merge(locations, on="site_id", suffixes=("", "_loc"))
    frame = cluster_by_huc8(combined, None, min_stations=3, min_overlap_years=8)
    assert len(frame) == 1

from __future__ import annotations

from stream_recoverability.data.network_catalog import load_network_catalog
from stream_recoverability.data.v2_download_policy import (
    assign_unique_sites,
    block_reason,
    last_check_site_ids,
    plan_v2_downloads,
    site_set_nested,
)


def test_last_check_ids_include_colorado_and_exclude_delaware() -> None:
    blocked = last_check_site_ids(load_network_catalog())
    assert "09379500" in blocked
    assert "14105700" in blocked
    assert "01427510" not in blocked
    assert "03216600" in blocked


def test_san_juan_is_blocked_because_colorado_site_is_on_the_list() -> None:
    blocked = last_check_site_ids()
    reason = block_reason(
        {
            "network_id": "san_juan_river_huc14",
            "display_name": "San Juan River (HUC2 14)",
            "candidate_station_ids": ["09379500", "09379510"],
            "historical_seen": False,
        },
        last_check_sites=blocked,
    )
    assert reason == "last_check_site"


def test_columbia_name_is_blocked_even_if_ids_are_new() -> None:
    reason = block_reason(
        {
            "network_id": "columbia_river_huc17",
            "display_name": "COLUMBIA RIVER (HUC2 17)",
            "candidate_station_ids": ["99999999", "88888888", "77777777"],
            "historical_seen": False,
        },
        last_check_sites=set(),
    )
    assert reason == "last_check_name"


def test_chattahoochee_is_historical() -> None:
    reason = block_reason(
        {
            "network_id": "chattahoochee_river_huc03",
            "display_name": "Chattahoochee River",
            "candidate_station_ids": ["02334430", "02335000", "02335450"],
            "historical_seen": True,
        },
        last_check_sites=set(),
    )
    assert reason == "historical"


def test_unique_sites_give_the_larger_cluster_the_contested_id() -> None:
    assigned = assign_unique_sites(
        [
            {
                "network_id": "small",
                "candidate_station_ids": ["a", "b", "c"],
            },
            {
                "network_id": "large",
                "candidate_station_ids": ["c", "d", "e", "f"],
            },
        ],
        blocked_sites=set(),
    )
    by_id = {row["network_id"]: row["download_site_ids"] for row in assigned}
    assert "c" in by_id["large"]
    assert "c" not in by_id["small"]


def test_nested_site_sets() -> None:
    assert site_set_nested(["a", "b"], ["a", "b", "c"]) is True
    assert site_set_nested(["a", "b", "c"], ["a", "b", "c"]) is False


def test_plan_does_not_open_last_check_or_rewrite_v1() -> None:
    plan = plan_v2_downloads()
    assert plan["sealed_outcomes_opened"] is False
    assert plan["last_check_temperatures_opened"] is False
    assert plan["network_catalog_v1_rewritten"] is False
    ids = {row["network_id"] for row in plan["downloadable"]}
    assert "columbia_river_huc17" not in ids
    assert "colorado_river_huc14" not in ids
    assert "chattahoochee_river_huc03" not in ids
    assert "delaware_river_huc02" not in ids
    assert "san_juan_river_huc14" not in ids
    assert plan["n_downloadable"] >= 50
    download_sites = {
        site
        for row in plan["downloadable"]
        for site in row["download_site_ids"]
    }
    assert download_sites.isdisjoint(set(plan["last_check_site_ids"]))

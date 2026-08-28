from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.data.development_auxiliary import (
    POWER_VARIABLES,
    Site,
    discover_networks,
    parse_nwis,
    parse_power,
    run_acquisition,
)

ROOT = Path(__file__).resolve().parents[1]


def test_current_open_roster_has_both_roles() -> None:
    networks = discover_networks(ROOT)
    assert len(networks) == 67
    assert sum(len(network.sites) for network in networks) == 340
    assert {network.role for network in networks} == {"development", "validation"}
    assert all(
        site.site_id.isdigit() and len(site.site_id) >= 8
        for network in networks
        for site in network.sites
    )


def test_parse_power_materializes_five_daily_variables() -> None:
    document = {
        "header": {"fill_value": -999.0},
        "geometry": {"coordinates": [-71.5, 42.1, 100]},
        "properties": {
            "parameter": {
                code: {"20200101": 1.5, "20200102": -999.0}
                for code, _, _ in POWER_VARIABLES.values()
            }
        },
    }
    frame = parse_power(
        json.dumps(document).encode(),
        Site("01000000", "2020-01-01", "2020-01-02", -71.5, 42.1),
    )
    assert len(frame) == 10
    assert set(frame["variable"]) == {"Ta", "P", "W", "RH", "Rs"}
    assert frame["natural_observed"].sum() == 5
    assert frame["value"].notna().sum() == 5


def test_parse_nwis_applies_units_and_approval() -> None:
    payload = (
        "# test\n"
        "agency_cd\tsite_no\tdatetime\t123_00060_00003\t123_00060_00003_cd\t124_00065_00003\t124_00065_00003_cd\n"
        "5s\t15s\t20d\t14n\t10s\t14n\t10s\n"
        "USGS\t01000000\t2020-01-01\t10\tA\t2\tP\n"
    ).encode()
    frame = parse_nwis(payload)
    flow = frame.loc[frame["variable"].eq("F")].iloc[0]
    level = frame.loc[frame["variable"].eq("L")].iloc[0]
    assert flow["value"] == pytest.approx(0.28316846592)
    assert flow["quality_approved"]
    assert pd.isna(level["value"])
    assert not level["quality_approved"]


def test_parse_nwis_reads_variable_width_table_segments() -> None:
    payload = (
        "agency_cd\tsite_no\tdatetime\t123_00060_00003\t123_00060_00003_cd\n"
        "5s\t15s\t20d\t14n\t10s\n"
        "USGS\t01000000\t2020-01-01\t10\tA\n"
        "agency_cd\tsite_no\tdatetime\t124_00060_00003\t124_00060_00003_cd\t125_00065_00003\t125_00065_00003_cd\n"
        "5s\t15s\t20d\t14n\t10s\t14n\t10s\n"
        "USGS\t02000000\t2020-01-01\t20\tA\t3\tA\n"
    ).encode()
    frame = parse_nwis(payload)
    assert len(frame) == 3
    assert frame.groupby("site_id")["variable"].apply(set).to_dict() == {
        "01000000": {"F"},
        "02000000": {"F", "L"},
    }


def test_run_overwrites_plain_network_tables(tmp_path: Path) -> None:
    network = next(
        network
        for network in discover_networks(ROOT)
        if network.network_id == "huc8_15030108"
    )

    def fetcher(url: str) -> bytes:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if "sites" in query:
            site = query["sites"][0].split(",")[0]
            return (
                "agency_cd\tsite_no\tdatetime\t123_00060_00003\t123_00060_00003_cd\n"
                "5s\t15s\t20d\t14n\t10s\n"
                f"USGS\t{site}\t2017-01-23\t10\tA\n"
            ).encode()
        document = {
            "header": {"fill_value": -999.0},
            "geometry": {"coordinates": [-110.0, 33.0, 100]},
            "properties": {
                "parameter": {
                    code: {"20170123": 1.0}
                    for code, _, _ in POWER_VARIABLES.values()
                }
            },
        }
        return json.dumps(document).encode()

    first = run_acquisition(
        ROOT,
        tmp_path,
        network_ids=[network.network_id],
        workers=3,
        fetcher=fetcher,
    )
    second = run_acquisition(
        ROOT,
        tmp_path,
        network_ids=[network.network_id],
        workers=2,
        fetcher=fetcher,
    )
    directory = tmp_path / network.role / "networks" / network.network_id
    daily = pd.read_parquet(directory / "daily_long_auxiliary.parquet")
    table = pd.read_csv(directory / "coverage.csv")
    assert first["n_requests"] == second["n_requests"] == 4
    assert len(daily) == 6
    assert len(table) == 21
    assert not list(directory.glob("*.partial"))

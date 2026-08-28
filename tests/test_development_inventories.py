import importlib.util
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).parents[1]


def _script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_open_inventory_reports_every_development_and_validation_role() -> None:
    module = _script("109_build_development_inventory.py")
    module.main()
    inventory = pd.read_csv(module.OUTPUT)
    assert inventory.groupby("role")["network_id"].size().to_dict() == {
        "development": 74,
        "validation": 29,
    }
    assert int(inventory["three_station_eligible"].sum()) == 68
    assert int(inventory["qualified_open_role"].sum()) == 67
    assert int(inventory["auxiliary_present"].sum()) >= 20


def test_new_confirmation_candidate_pool_reaches_recruitment_floor() -> None:
    module = _script("110_build_confirmation_candidates.py")
    module.main()
    candidates = pd.read_csv(module.OUTPUT)
    assert len(candidates) >= 55
    assert candidates["network_id"].is_unique
    assert candidates["n_catalog_stations"].ge(3).all()
    assert candidates["prior_temperature_values_seen"].eq(False).all()
    assert int(candidates.loc[candidates["domain"].ne("united_states")].shape[0]) >= 15

    new_name_huc4 = candidates.loc[candidates["network_id"].str.contains("_huc4_")]
    assert len(new_name_huc4) == 13
    v3 = yaml.safe_load(
        (ROOT / "configs/network_catalog_v3_huc8.yaml").read_text(encoding="utf-8")
    )
    old_stations = {
        str(station)
        for network in v3["networks"]
        for station in network["candidate_station_ids"]
    }
    rosters = [set(value.split("|")) for value in new_name_huc4["site_ids"]]
    assert set().union(*rosters).isdisjoint(old_stations)
    for index, roster in enumerate(rosters):
        assert roster.isdisjoint(set().union(*rosters[:index], *rosters[index + 1 :]))

    expected_huc2 = {
        "usgs_missouri_river_huc10",
        "usgs_rio_grande_huc13",
        "usgs_arkansas_river_huc11",
    }
    new_name_huc2 = candidates.loc[candidates["network_id"].isin(expected_huc2)]
    assert set(new_name_huc2["network_id"]) == expected_huc2
    existing = candidates.loc[~candidates["network_id"].isin(expected_huc2)]
    existing_stations = set("|".join(existing["site_ids"]).split("|"))
    huc2_rosters = [set(value.split("|")) for value in new_name_huc2["site_ids"]]
    assert set().union(*huc2_rosters).isdisjoint(existing_stations)
    assert sum(map(len, huc2_rosters)) == len(set().union(*huc2_rosters))

from __future__ import annotations

import csv
import hashlib
import importlib.util
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/72_build_foen_prospective_lock.py"
SPLIT_CSV = ROOT / "results/framework/public_catalog/foen_prospective_split_v1.csv"
SPLIT_YAML = ROOT / "configs/foen_prospective_split_v1.yaml"
CATALOG_YAML = ROOT / "configs/foen_prospective_catalog_v1.yaml"
QUERY_TEMPLATE = ROOT / "configs/foen_daily_value_query_v1.graphql"


def _load_script():
    spec = importlib.util.spec_from_file_location("foen_prospective_lock", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lock_builder_station_query_cannot_open_values_or_coverage() -> None:
    module = _load_script()
    query = module.STATION_QUERY
    assert " value" not in query
    assert "timestamp" not in query
    assert "coverageFrom" not in query
    assert "coverageTo" not in query
    assert "riverName" in query
    assert "catchmentName" in query
    assert "latitude" in query and "longitude" in query


def test_accent_normalization_merges_rhone_and_burns_whole_aare() -> None:
    module = _load_script()
    rows = []
    for river, catchment, site_ids in (
        ("Rhône", "Rhonegebiet", ["1001", "1002", "1003"]),
        ("Rhone", "Rhonegebiet", ["1004", "1005", "1006"]),
        ("Aare", "Aaregebiet", ["2016", "2017", "2018"]),
    ):
        for index, site_id in enumerate(site_ids):
            rows.append(
                {
                    "site_id": site_id,
                    "name": site_id,
                    "river_name": river,
                    "catchment_name": catchment,
                    "status": "Aufgebaut",
                    "latitude": 46.0 + index / 10,
                    "longitude": 7.0 + index / 10,
                    "river_key": module._key(river),
                    "catchment_key": module._key(catchment),
                }
            )
    candidates = module.build_candidates(pd.DataFrame(rows))
    assert len(candidates) == 2
    rhone = next(row for row in candidates if row["river_key"] == "rhone")
    assert rhone["n_stations"] == 6
    assert rhone["river_labels"] == ["Rhone", "Rhône"]
    aare = next(row for row in candidates if row["river_key"] == "aare")
    assert aare["never_sealed"] is True
    assert aare["development_burned"] is True
    assert aare["probe_station_ids"] == ["2016"]


def test_repository_foen_split_is_locked_before_values() -> None:
    split = yaml.safe_load(SPLIT_YAML.read_text(encoding="utf-8"))
    catalog = yaml.safe_load(CATALOG_YAML.read_text(encoding="utf-8"))
    canonical = SPLIT_CSV.read_bytes()
    assert split["sha256"] == hashlib.sha256(canonical).hexdigest()
    assert (
        split["catalog_sha256"] == hashlib.sha256(CATALOG_YAML.read_bytes()).hexdigest()
    )
    assert split["status"] == "locked_before_temperature_value_query"
    assert split["seed"] == 20260826
    assert split["temperature_values_queried"] is False
    assert split["sealed_outcomes_opened"] is False
    assert split["coverage_fields_used_for_eligibility"] is False
    assert split["qualified_networks_claimed"] == 0
    assert catalog["daily_years_claimed"] == 0
    assert catalog["coverage_fields_requested"] is False
    assert catalog["temperature_values_queried"] is False

    rows = list(csv.DictReader(canonical.decode("utf-8").splitlines()))
    sealed = [row for row in rows if row["role"] == "sealed"]
    burned = [row for row in rows if row["role"] == "never_sealed"]
    assert len(sealed) == 10
    assert len(burned) == 1
    assert burned[0]["network_id"] == "foen_aare_aaregebiet"
    assert burned[0]["development_burned"] == "true"
    assert "2016" in burned[0]["station_ids"].split(",")
    assert all("2016" not in row["station_ids"].split(",") for row in sealed)
    assert all(int(row["n_stations"]) >= 3 for row in rows)
    assert all(row["temperature_values_queried"] == "false" for row in rows)
    assert all(
        row["qualified_8yr_status"] == "unknown_until_post_download_qc" for row in rows
    )


def test_future_query_is_hashed_but_explicitly_unexecuted() -> None:
    split = yaml.safe_load(SPLIT_YAML.read_text(encoding="utf-8"))
    contract = split["future_request_contract"]
    assert contract["status"] == "template_locked_not_executed"
    assert contract["template_executed"] is False
    assert (
        contract["query_template_sha256"]
        == hashlib.sha256(QUERY_TEMPLATE.read_bytes()).hexdigest()
    )
    assert contract["partition"] == "disjoint_calendar_year_windows"
    assert contract["release_states"] == ["2", "3"]
    assert contract["response_handling_for_sealed"].endswith("without_json_decode")


def test_condition_note_and_ledger_withhold_t8() -> None:
    note = (ROOT / "docs/protocol_condition_foen_public_daily_v9_1.md").read_text(
        encoding="utf-8"
    )
    ledger = (ROOT / "paper/boundary_ledger.md").read_text(encoding="utf-8")
    assert "BL-018" in ledger
    assert "zero qualified Swiss networks" in ledger
    assert "No temperature value was queried" in note
    assert "coverageFrom" in note and "cannot be used" in note
    assert "4405cf690ccf9d9b62a8dfa76d2d1d74806e662835bff0043ee9fe1e5619ae59" in note

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/69_download_catalog_v3_pilot.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("download_v3_pilot_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _one_network_plan() -> dict:
    stations = [
        {"site_id": site, "start": "2010-01-01", "end": "2018-12-29"}
        for site in ("s1", "s2", "s3")
    ]
    return {
        "policy": "catalog_v3_huc8_development_only",
        "split_sha256": "locked",
        "pilot_seed": 20260826,
        "pilot_size": 1,
        "sample_network_ids_sha256": "sample",
        "stratification_columns": [
            "climate_band",
            "regulation_stratum",
            "size_tertile",
        ],
        "n_development_available": 1,
        "n_validation_selected": 0,
        "n_sealed_selected": 0,
        "sealed_temperature_records_read": False,
        "retired_name_huc2_plan_used": False,
        "networks": [
            {
                "network_id": "huc8_test",
                "role": "development",
                "climate_band": "test",
                "regulation_stratum": "test",
                "size_tertile": "test",
                "stations": stations,
            }
        ],
    }


def test_runner_writes_qc_attrition_without_network_or_sealed_inference(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_script()
    monkeypatch.setattr(module, "plan_v3_development_pilot", _one_network_plan)
    dates = pd.date_range("2010-01-01", periods=9 * 365, freq="D")

    def fetcher(site_id, start, end, *, cache_dir):
        return pd.DataFrame(
            {
                "site_id": site_id,
                "date": dates,
                "temperature_c": 10.0 + (dates.dayofyear.to_numpy() / 1000.0),
                "qualifier": "A",
            }
        )

    output = tmp_path / "corpus"
    manifest = module.run_pilot(
        output_dir=output,
        cache_dir=tmp_path / "cache",
        fetcher=fetcher,
        sleep=lambda _: None,
        pause_s=0,
    )

    assert manifest["n_networks_complete_enough"] == 1
    assert manifest["n_validation_selected"] == 0
    assert manifest["n_sealed_selected"] == 0
    assert manifest["sealed_temperature_records_read"] is False
    assert manifest["network_interval_reported"] is False
    assert manifest["network_ci_status"] == "withheld_n_lt_100_network_interval"
    assert (output / "ingest_qc_report.csv").is_file()
    assert (output / "attrition_summary.csv").is_file()
    network_manifest = json.loads(
        (output / "networks/huc8_test/network_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert network_manifest["status"] == "complete"
    assert network_manifest["role"] == "development"
    assert network_manifest["sealed_temperature_records_read"] is False

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "scripts/50_check_reservoir_operations.py"
    spec = importlib.util.spec_from_file_location("reservoir_operations_check", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_storage_metadata_does_not_imply_release_temperature() -> None:
    module = _load_module()
    document = {
        "features": [
            {
                "properties": {
                    "monitoring_location_id": "USGS-1",
                    "parameter_code": "00054",
                }
            },
            {
                "properties": {
                    "monitoring_location_id": "USGS-2",
                    "parameter_code": "00010",
                }
            },
        ]
    }
    assert module._storage_sites(document) == {"USGS-1"}


def test_storage_metadata_rejects_non_feature_response() -> None:
    module = _load_module()
    with pytest.raises(TypeError, match="feature list"):
        module._storage_sites({"error": "not a feature collection"})


def test_stored_availability_audit_keeps_causal_claim_fail_closed() -> None:
    manifest = json.loads(
        (
            ROOT
            / "results/framework/public_catalog/reservoir_operations_check.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["nwis_site_service_reachable"] is True
    assert manifest["official_documentation"].startswith(
        "https://api.waterdata.usgs.gov/"
    )
    assert manifest["example_storage_sites_found"] > 0
    assert manifest["parameter_interpretation"] == (
        "reservoir_storage_not_release_temperature"
    )
    assert manifest["release_temperature_found"] is False
    assert manifest["outlet_depth_found"] is False
    assert manifest["can_write_reservoir_cause"] is False

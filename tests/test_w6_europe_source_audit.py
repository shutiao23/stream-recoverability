from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/71_w6_europe_source_audit.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("w6_europe_source_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hubeau_preflight_requires_sandre_correcte() -> None:
    module = _load_script()

    def fake_fetch(url, **kwargs):
        del kwargs
        assert "code_qualification=1" in url
        return {"count": 0, "data": []}

    row = module.hubeau_correct_span("06121500", fetch_json=fake_fetch)
    assert row["n_correct_instantaneous"] == 0
    assert row["quality_code_required"] == "1"
    assert row["daily_download_started"] is False


def test_network_with_raw_but_no_correct_values_is_not_complete() -> None:
    module = _load_script()
    clusters = pd.DataFrame(
        {"river": ["Le Test"], "site_ids": ["1,2,3"], "n_stations": [3]}
    )
    stations = pd.DataFrame(
        {
            "site_id": ["1", "2", "3"],
            "n_correct_instantaneous": [0, 0, 0],
            "error": [None, None, None],
        }
    )
    result = module.summarize_hubeau_networks(clusters, stations).iloc[0]
    assert bool(result["strict_8yr_concurrent_complete"]) is False
    assert bool(result["countable_toward_t8"]) is False
    assert result["reason"] == "fewer_than_3_stations_with_correct_observations"


def test_foen_probe_query_omits_temperature_value_field() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    probe = source.split('daily_query = """', 1)[1].split('"""', 1)[0]
    assert "data_1day_mean" in probe
    assert 'parameterName: { _eq: "WT" }' in probe
    assert " value " not in probe
    assert "releaseState" in probe

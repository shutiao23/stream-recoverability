from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "scripts/126_build_second_confirmation_candidates.py"
    spec = importlib.util.spec_from_file_location("second_candidates", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_concurrent_subset_removes_limiting_station() -> None:
    module = _module()
    frame = pd.DataFrame(
        {
            "site_id": ["a", "b", "c", "late"],
            "daily_begin": pd.to_datetime(
                ["2000-01-01", "2000-01-01", "2000-01-01", "2018-01-01"]
            ),
            "daily_end": pd.to_datetime(
                ["2020-01-01", "2020-01-01", "2020-01-01", "2020-01-01"]
            ),
        }
    )
    result = module._qualified_concurrent_subset(frame)
    assert tuple(result["site_id"]) == ("a", "b", "c")


def test_built_second_candidate_pool_meets_floor_and_excludes_first_panel() -> None:
    module = _module()
    module.main()
    candidates = pd.read_csv(module.OUTPUT, dtype={"site_ids": str})
    first = set(pd.read_csv(module.FIRST_CONFIRMATION)["network_id"].astype(str))
    assert len(candidates) >= 150
    assert not set(candidates["network_id"]).intersection(first)
    new = candidates.loc[
        candidates["candidate_status"].eq("new_metadata_candidate_pending_daily_qc")
    ]
    rosters = [set(value.split("|")) for value in new["site_ids"]]
    assert all(not left.intersection(right) for i, left in enumerate(rosters) for right in rosters[i + 1 :])

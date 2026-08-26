from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/59_run_gap_triage.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_gap_triage_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_t3b_loader_accepts_only_gap_specific_station_scores(tmp_path: Path) -> None:
    module = _load_script()
    path = tmp_path / "scores.csv"
    pd.DataFrame(
        {
            "network_id": ["river"],
            "gap_length": [30],
            "fill_mae": [0.2],
            "predicted_conditional_risk": [0.1],
            "achieved_skill_mode": ["gap_specific"],
        }
    ).to_csv(path, index=False)

    loaded = module._load_scores(path)

    assert loaded.loc[0, "fill_mae"] == pytest.approx(0.2)


def test_t3b_loader_refuses_later_year_scores(tmp_path: Path) -> None:
    module = _load_script()
    path = tmp_path / "scores.csv"
    pd.DataFrame(
        {
            "network_id": ["river"],
            "gap_length": [30],
            "fill_mae": [0.2],
            "predicted_conditional_risk": [0.1],
            "achieved_skill_mode": ["later_year"],
        }
    ).to_csv(path, index=False)

    with pytest.raises(SystemExit, match="refusing non-gap-specific"):
        module._load_scores(path)


def test_t3b_json_output_replaces_nonfinite_diagnostics_with_null() -> None:
    module = _load_script()

    payload = module._jsonable({"undefined": float("nan"), "unbounded": float("inf")})

    assert payload == {"undefined": None, "unbounded": None}
    assert json.dumps(payload, allow_nan=False)

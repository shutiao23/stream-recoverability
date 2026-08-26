from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/64_matched_regulation.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("matched_regulation_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_t6_reuses_frozen_regulation_panel_cache() -> None:
    module = _load_script()
    assert module.GAGES_CACHE == ROOT / "data/cache/regulation_panel_v1"
    assert module.GAGES_ARCHIVE == (
        ROOT
        / "data/cache/regulation_panel_v1"
        / "basinchar_and_report_sept_2011.zip"
    )


def test_seplains_bfi_slice_is_descriptive_and_never_passes() -> None:
    module = _load_script()
    frame = pd.DataFrame(
        {
            "seplains": [True, True, True, True],
            "mean_bfi": [10.0, 20.0, 70.0, 80.0],
            "recoverability_r": [0.9, 0.8, 0.5, 0.4],
        }
    )

    result = module.seplains_bfi_slice(frame)

    assert result["n_seplains_with_bfi"] == 4
    assert result["delta_r_high_minus_low_bfi"] < 0
    assert result["passed"] is False

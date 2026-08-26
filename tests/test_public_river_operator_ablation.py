from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.public_river_operator_ablation import (
    drop_insane_mae_networks,
    load_public_river_panels,
    run_public_river_operator_ablation,
    write_operator_ablation_artifacts,
)


def _toy_wide(
    *,
    n_years: int = 6,
    n_stations: int = 4,
    seed: int = 0,
    start: str = "2000-01-01",
) -> pd.DataFrame:
    dates = pd.date_range(start, periods=365 * n_years, freq="D")
    rng = np.random.default_rng(seed)
    seasonal = 8.0 * np.sin(2.0 * np.pi * dates.dayofyear.to_numpy() / 365.25)
    factor = rng.normal(0.0, 1.2, len(dates))
    data = {
        f"s{index}": seasonal
        + factor
        + (0.15 * index)
        + rng.normal(0.0, 0.35, len(dates))
        for index in range(n_stations)
    }
    return pd.DataFrame(data, index=dates)


def test_synthetic_ablation_is_not_confirmatory() -> None:
    result = run_public_river_operator_ablation(
        {"toy_a": _toy_wide(seed=1), "toy_b": _toy_wide(seed=2, start="2001-01-01")},
        gap_lengths=(7, 14),
    )
    manifest = result["manifest"]
    assert manifest["formal_evidence"] is False
    assert manifest["headline_claim_licensed"] is False
    assert manifest["confirmatory_eligible"] is False
    assert manifest["thresholds_locked"] is True
    assert manifest["evaluate_success"]["n_networks_min"] == 100
    assert manifest["evaluate_success"]["passed"] is False
    assert manifest["n_networks"] >= 2
    assert manifest["donor_r2_estimator"] in {"year_block_cv", "train_in_sample"}
    nested = result["nested"]
    station = nested.loc[nested["level"].eq("station") & nested["scope"].eq("gap_7")]
    assert station["added"].tolist() == [
        "gap_length",
        "acf30",
        "donor_r2",
        "heuristic_explained_variance",
        "recoverability_r",
    ]
    assert np.isfinite(station["delta_r2"]).any()
    operator_delta = float(
        station.loc[station["added"].eq("recoverability_r"), "delta_r2"].iloc[0]
    )
    assert manifest["operator_incremental_r2_le_0"] == (operator_delta <= 0)


def test_insane_mae_network_is_dropped() -> None:
    good = _toy_wide(seed=3)
    broken = good.copy()
    # A constant offset is absorbed by the regression intercept. Scale the
    # target so later-year donor MAE is thousands of °C, like Clearwater.
    broken["s0"] = broken["s0"] * 1.0e4
    result = run_public_river_operator_ablation(
        {"sane_river": good, "broken_river": broken},
        gap_lengths=(7,),
        insane_mae_c=50.0,
    )
    assert "broken_river" in result["manifest"]["dropped_insane_mae_networks"]
    assert "sane_river" in result["manifest"]["primary_networks"]
    assert "broken_river" not in result["manifest"]["primary_networks"]


def test_clearwater_style_mae_uses_the_same_drop_rule() -> None:
    scores = pd.DataFrame(
        {
            "network_id": ["clearwater_river_huc17", "madison_river_huc10"],
            "donor_mae": [66331.0, 1.0],
            "achieved_skill": [-10032.0, 0.8],
        }
    )
    kept, dropped, maxima = drop_insane_mae_networks(scores, threshold=50.0)
    assert dropped == ["clearwater_river_huc17"]
    assert maxima["clearwater_river_huc17"] == 66331.0
    assert kept["network_id"].tolist() == ["madison_river_huc10"]


def test_load_skips_willamette_mainstem(tmp_path: Path) -> None:
    _toy_wide(seed=4).to_csv(tmp_path / "willamette_mainstem_daily_wide.csv")
    _toy_wide(seed=5).to_csv(tmp_path / "madison_river_huc10_daily_wide.csv")
    panels = load_public_river_panels(tmp_path)
    assert "willamette_mainstem" not in panels
    assert "madison_river_huc10" in panels


def test_load_first_directory_wins(tmp_path: Path) -> None:
    left = tmp_path / "a"
    right = tmp_path / "b"
    left.mkdir()
    right.mkdir()
    first = _toy_wide(seed=8)
    first["marker"] = 1.0
    first.to_csv(left / "toy_river_daily_wide.csv")
    second = _toy_wide(seed=9)
    second["marker"] = 2.0
    second.to_csv(right / "toy_river_daily_wide.csv")
    panels = load_public_river_panels([left, right])
    assert float(panels["toy_river"]["marker"].iloc[0]) == 1.0


def test_write_uses_new_filenames_only(tmp_path: Path) -> None:
    result = run_public_river_operator_ablation(
        {"toy_a": _toy_wide(seed=6), "toy_b": _toy_wide(seed=7)},
        gap_lengths=(7,),
    )
    paths = write_operator_ablation_artifacts(result, tmp_path)
    names = {path.name for path in tmp_path.iterdir()}
    assert names == {
        "operator_nested_ablation.csv",
        "operator_vs_univariate_network.csv",
        "operator_ablation_manifest.json",
    }
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["formal_evidence"] is False
    assert manifest["headline_claim_licensed"] is False
    assert manifest["confirmatory_eligible"] is False
    assert "leave_one_river_out.csv" not in names

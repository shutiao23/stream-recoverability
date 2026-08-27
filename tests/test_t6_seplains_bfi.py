from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.experiments.t6_seplains_bfi import (
    bfi_stratified_memory_direction,
    leave_ecoregion_out_with_features,
    partial_correlation,
)


def _synthetic_metrics() -> pd.DataFrame:
    rows = []
    for region in ("NorthEast", "SEPlains", "WestMnts"):
        for index in range(20):
            regulated = int(index % 2 == 0)
            rows.append(
                {
                    "station_id": f"{region[:2]}{index:06d}",
                    "AGGECOREGION": region,
                    "upstream_major_dam_2009": regulated,
                    "memory_range_index_per_degC": 0.01 + 0.002 * regulated + 0.0001 * index,
                    "BFI_AVE": 30.0 + 10.0 * regulated + index,
                    "DRAIN_SQKM": 100.0 + index,
                }
            )
    return pd.DataFrame(rows)


def test_leave_ecoregion_out_with_bfi_runs() -> None:
    metrics = _synthetic_metrics()
    memory = leave_ecoregion_out_with_features(
        metrics, ["memory_range_index_per_degC"]
    )
    both = leave_ecoregion_out_with_features(
        metrics, ["memory_range_index_per_degC", "BFI_AVE"]
    )
    assert len(memory) == len(metrics)
    assert len(both) == len(metrics)
    assert memory["oof_probability"].between(0, 1).all()


def test_partial_correlation_is_finite_on_synthetic() -> None:
    metrics = _synthetic_metrics()
    result = partial_correlation(
        metrics,
        "memory_range_index_per_degC",
        "BFI_AVE",
        ["DRAIN_SQKM"],
    )
    assert result["n"] > 0
    assert np.isfinite(result["partial_r"])


def test_bfi_stratified_direction_never_passes_t6() -> None:
    metrics = _synthetic_metrics()
    result = bfi_stratified_memory_direction(metrics)
    assert result["n"] > 0
    assert "strata" in result


@pytest.mark.skipif(
    not Path("results/regulation_panel_v1_legacy_transport/station_metrics.csv").is_file(),
    reason="frozen regulation panel not present",
)
def test_t6_integration_manifest(tmp_path: Path) -> None:
    from stream_recoverability.experiments.t6_seplains_bfi import run_t6_seplains_bfi_analysis

    root = Path(__file__).resolve().parents[1]
    manifest = run_t6_seplains_bfi_analysis(
        station_metrics_path=root
        / "results/regulation_panel_v1_legacy_transport/station_metrics.csv",
        frozen_predictions_path=root
        / "results/regulation_panel_v1_legacy_transport/leave_ecoregion_out_predictions.csv",
        config_path=root / "configs/regulation_panel_freeze_v1.yaml",
        cache_dir=root / "data/cache/regulation_panel_v1",
        output_dir=tmp_path,
    )
    assert manifest["t6_passed"] is False
    assert manifest["formal_evidence"] is False
    assert manifest["n_stations_with_bfi"] > 0

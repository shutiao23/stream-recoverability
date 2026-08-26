from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.public_river_operator_ablation import (
    ACHIEVED_SKILL_GAP_SPECIFIC,
    ACHIEVED_SKILL_LATER_YEAR,
    W2_PRIMARY_NETWORKS,
    W2_PURPOSE,
    first_plant_start,
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
    phi = 0.9
    data = {}
    for index in range(n_stations):
        shock = rng.normal(0.0, 0.4, len(dates))
        memory = np.zeros(len(dates))
        for step in range(1, len(dates)):
            memory[step] = phi * memory[step - 1] + shock[step]
        data[f"s{index}"] = seasonal + factor + (0.15 * index) + memory
    return pd.DataFrame(data, index=dates)


def _two_river_panels() -> dict[str, pd.DataFrame]:
    return {
        "toy_a": _toy_wide(seed=11),
        "toy_b": _toy_wide(seed=22, start="2001-01-01"),
    }


def test_gap_specific_skill_differs_across_lengths_later_year_does_not() -> None:
    panels = _two_river_panels()
    later = run_public_river_operator_ablation(
        panels,
        gap_lengths=(7, 14),
        achieved_skill_mode=ACHIEVED_SKILL_LATER_YEAR,
    )
    planted = run_public_river_operator_ablation(
        panels,
        gap_lengths=(7, 14),
        achieved_skill_mode=ACHIEVED_SKILL_GAP_SPECIFIC,
    )
    later_scores = later["primary"]
    planted_scores = planted["primary"]
    later_pivot = later_scores.pivot_table(
        index=["network_id", "station_id"],
        columns="gap_length",
        values="achieved_skill",
    )
    planted_pivot = planted_scores.pivot_table(
        index=["network_id", "station_id"],
        columns="gap_length",
        values="achieved_skill",
    )
    later_cols = list(later_pivot.columns)
    planted_cols = list(planted_pivot.columns)
    assert len(later_cols) == 2
    assert len(planted_cols) == 2
    assert np.allclose(
        later_pivot[later_cols[0]], later_pivot[later_cols[1]], equal_nan=True
    )
    both = planted_pivot.dropna()
    assert not both.empty
    assert not np.allclose(both[planted_cols[0]], both[planted_cols[1]])


def test_pooled_gap_length_delta_r2_is_finite_and_not_constant_by_construction() -> None:
    result = run_public_river_operator_ablation(
        _two_river_panels(),
        gap_lengths=(7, 14),
        achieved_skill_mode=ACHIEVED_SKILL_GAP_SPECIFIC,
    )
    complete = result["complete"]
    assert complete["gap_length"].nunique() == 2
    nested = result["nested"]
    pooled = nested.loc[
        nested["scope"].eq("pooled_gaps") & nested["level"].eq("station")
    ]
    gap_row = pooled.loc[pooled["added"].eq("gap_length")]
    assert not gap_row.empty
    delta = float(gap_row["delta_r2"].iloc[0])
    assert np.isfinite(delta)
    assert abs(delta) > 0
    assert result["manifest"]["pipeline_gap_length_delta_r2_nonzero"] is True
    assert bool(result["manifest"]["pipeline_gap_length_delta_r2_nonzero"]) == (
        abs(delta) > 0
    )
    assert result["manifest"]["pipeline_gap_rows_differ"] is True


def test_w2_manifest_is_pipeline_verification_not_evidence() -> None:
    result = run_public_river_operator_ablation(
        _two_river_panels(),
        gap_lengths=(7, 14),
        primary_networks=W2_PRIMARY_NETWORKS,
        achieved_skill_mode=ACHIEVED_SKILL_GAP_SPECIFIC,
    )
    manifest = result["manifest"]
    assert manifest["passed"] is False
    assert manifest["purpose"] == W2_PURPOSE
    assert manifest["achieved_skill_is_later_year_not_gap_specific"] is False
    assert manifest["achieved_skill_is_gap_specific"] is True
    assert manifest["formal_evidence"] is False
    assert manifest["headline_claim_licensed"] is False
    assert manifest["confirmatory_eligible"] is False
    assert manifest["evaluate_success"]["passed"] is False
    assert manifest["evaluate_success"]["confirmatory_eligible"] is False
    assert manifest["evaluate_success"]["n_networks_min"] == 100
    status = manifest["evaluate_success"]["spearman_inference_status"]
    assert status != "tested"
    assert "suwannee_river_huc31" not in manifest["requested_primary_networks"]
    assert list(manifest["requested_primary_networks"]) == list(W2_PRIMARY_NETWORKS)
    assert "ci_lower" not in manifest["evaluate_success"]
    assert "ci_upper" not in manifest["evaluate_success"]


def test_w2_write_does_not_clobber_later_year_or_write_loo(tmp_path: Path) -> None:
    later_dir = tmp_path / "public_rivers"
    later_dir.mkdir()
    later_manifest = later_dir / "operator_ablation_manifest.json"
    later_nested = later_dir / "operator_nested_ablation.csv"
    loo = later_dir / "leave_one_river_out.csv"
    later_manifest.write_text(
        '{"achieved_skill_is_later_year_not_gap_specific": true}\n',
        encoding="utf-8",
    )
    later_nested.write_text("scope,level\nlater,station\n", encoding="utf-8")
    loo.write_text("keep\n", encoding="utf-8")
    later_manifest_text = later_manifest.read_text(encoding="utf-8")
    later_nested_text = later_nested.read_text(encoding="utf-8")
    w2_dir = later_dir / "w2_phase4_gap_specific"
    result = run_public_river_operator_ablation(
        _two_river_panels(),
        gap_lengths=(7, 14),
        achieved_skill_mode=ACHIEVED_SKILL_GAP_SPECIFIC,
    )
    write_operator_ablation_artifacts(
        result, w2_dir, include_station_scores=True
    )
    names = {path.name for path in w2_dir.iterdir()}
    assert "leave_one_river_out.csv" not in names
    assert "operator_nested_ablation.csv" in names
    assert "operator_ablation_manifest.json" in names
    assert "operator_vs_univariate_network.csv" in names
    assert later_manifest.read_text(encoding="utf-8") == later_manifest_text
    assert later_nested.read_text(encoding="utf-8") == later_nested_text
    assert loo.read_text(encoding="utf-8") == "keep\n"
    written = json.loads( (w2_dir / "operator_ablation_manifest.json").read_text(encoding="utf-8") )
    assert written["passed"] is False
    assert written["achieved_skill_is_later_year_not_gap_specific"] is False


def test_suwannee_is_not_a_requested_primary_network() -> None:
    assert "suwannee_river_huc31" not in W2_PRIMARY_NETWORKS
    assert "delaware_river_huc20" in W2_PRIMARY_NETWORKS
    assert len(W2_PRIMARY_NETWORKS) == 6


def test_plant_never_uses_first_365_train_days() -> None:
    n = 800
    target_ok = np.ones(n, dtype=bool)
    donor_ok = np.ones(n, dtype=bool)
    train = np.zeros(n, dtype=bool)
    train[:500] = True
    test = ~train
    forbidden = np.zeros(n, dtype=bool)
    forbidden[np.flatnonzero(train)[:365]] = True
    start = first_plant_start(
        target_ok, donor_ok, length=30, test=test, forbidden=forbidden
    )
    assert start is not None
    assert not forbidden[int(start) : int(start) + 30].any()
    assert bool(np.all(test[int(start) : int(start) + 30]))

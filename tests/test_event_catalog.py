from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from stream_recoverability.evaluation.event_metrics import compute_event_metrics
from stream_recoverability.experiments.grid import build_experiment_grid
from stream_recoverability.experiments.runner import ExperimentRunner
from stream_recoverability.masks import (
    EventCatalogAuditError,
    audit_event_episode_catalog,
    derive_event_day_condition,
    extract_event_windows,
    generate_event_episode_catalog,
    generate_event_mask,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "study_manifest.yaml"
CONFIG = PROJECT_ROOT / "configs/experiments.yaml"


def _event_source() -> pd.DataFrame:
    dates = pd.date_range("2012-01-01", "2020-12-31", freq="D")
    index = np.arange(len(dates), dtype=float)
    day_of_year = dates.dayofyear.to_numpy(dtype=float)
    values = {
        "T": (
            10.0
            + 3.0 * np.sin(2 * np.pi * day_of_year / 365.25)
            + 0.8 * np.sin(2 * np.pi * index / 19.0)
        ),
        "F": (
            100.0
            + 25.0 * np.cos(2 * np.pi * day_of_year / 365.25)
            + 7.0 * np.cos(2 * np.pi * index / 23.0)
        ),
    }
    rows = []
    for variable, series in values.items():
        for date, value in zip(dates, series):
            rows.append(
                {
                    "date": date,
                    "station_id": "B1",
                    "variable": variable,
                    "value": value,
                    "quality_approved": True,
                    "split": "train" if date.year <= 2016 else "test",
                    "data_version": "published_v1",
                }
            )
    return pd.DataFrame(rows)


def _catalog(source: pd.DataFrame | None = None) -> pd.DataFrame:
    return generate_event_episode_catalog(
        _event_source() if source is None else source,
        data_version="published_v1",
        evaluation_split="development_test",
        minimum_training_samples=10,
    )


def _event_arrays(
    source: pd.DataFrame, event_type: str
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray]:
    target = "T" if event_type in {"high_temperature", "rapid_warming"} else "F"
    selected = source.loc[source["variable"].eq(target)].sort_values("date")
    return (
        pd.DatetimeIndex(selected["date"]),
        selected["value"].to_numpy(dtype=float),
        selected["quality_approved"].to_numpy(dtype=bool),
        selected["split"].to_numpy(dtype=str),
    )


def test_high_temperature_uses_train_only_doy_anomaly_and_minimum_duration() -> None:
    dates = pd.date_range("2016-01-01", "2020-12-31", freq="D")
    doys = np.asarray(
        [pd.Timestamp(2000, date.month, date.day).dayofyear for date in dates],
        dtype=float,
    )
    splits = np.where(dates.year <= 2018, "train", "test")
    year_offsets = np.select(
        [dates.year == 2016, dates.year == 2017, dates.year == 2018],
        [-0.2, 0.0, 0.2],
        default=-1.0,
    )
    values = 20.0 * np.sin(2 * np.pi * doys / 366.0) + year_offsets
    run = (dates >= "2019-07-10") & (dates <= "2019-07-12")
    isolated = dates == "2019-08-01"
    values[run] += 5.0
    values[isolated] += 10.0
    quality = np.ones(len(dates), dtype=bool)

    derived = derive_event_day_condition(
        dates,
        values,
        quality,
        splits,
        "high_temperature",
        source_split="test",
        minimum_training_samples=10,
    )
    changed_test = values.copy()
    changed_test[splits == "test"] -= 50.0
    changed = derive_event_day_condition(
        dates,
        changed_test,
        quality,
        splits,
        "high_temperature",
        source_split="test",
        minimum_training_samples=10,
    )
    np.testing.assert_allclose(derived.climatology, changed.climatology)
    np.testing.assert_allclose(derived.threshold, changed.threshold)
    assert derived.condition[run].all()
    assert not derived.condition[isolated].any()
    assert not derived.condition[splits == "train"].any()
    assert derived.definition.threshold_reference_scope == "station_doy_window"
    assert derived.definition.minimum_duration_days == 3


def test_frozen_episode_extraction_locks_merge_peak_center_and_minimum() -> None:
    high_condition = np.zeros(50, dtype=bool)
    high_condition[2:4] = True  # two days: excluded
    high_condition[10:13] = True
    high_condition[15:18] = True  # two-day gap: merged
    high_measure = np.arange(50, dtype=float)
    high_threshold = np.zeros(50, dtype=float)
    high = extract_event_windows(
        high_condition,
        high_measure,
        "high_temperature",
        threshold=high_threshold,
    )
    assert len(high) == 1
    assert (
        high[0].raw_start_index,
        high[0].raw_end_index,
        high[0].window_start_index,
        high[0].window_end_index,
        high[0].component_count,
    ) == (10, 17, 10, 17, 2)
    assert high[0].peak_index == 17

    flood_condition = np.zeros(60, dtype=bool)
    flood_condition[20:23] = True
    flood_condition[25:27] = True
    flood_measure = np.zeros(60, dtype=float)
    flood_measure[[20, 21, 22, 25, 26]] = [5.0, 7.0, 9.0, 15.0, 8.0]
    flood = extract_event_windows(flood_condition, flood_measure, "flood")
    assert len(flood) == 1
    assert (
        flood[0].raw_start_index,
        flood[0].raw_end_index,
        flood[0].peak_index,
        flood[0].window_start_index,
        flood[0].window_end_index,
        flood[0].window_center_index,
    ) == (20, 26, 25, 18, 32, 25)
    assert (flood[0].rising_start_index, flood[0].rising_end_index) == (20, 24)
    assert (flood[0].recession_start_index, flood[0].recession_end_index) == (
        26,
        26,
    )

    low_condition = np.zeros(60, dtype=bool)
    low_condition[2:8] = True  # six days: excluded
    low_condition[30:37] = True
    low_measure = np.full(60, 20.0)
    low_measure[30:37] = [8.0, 7.0, 6.0, 4.0, 1.0, 3.0, 5.0]
    low = extract_event_windows(low_condition, low_measure, "low_flow")
    assert len(low) == 1
    assert (low[0].raw_start_index, low[0].raw_end_index) == (30, 36)
    assert low[0].min_index == 34


def test_event_catalog_is_deterministic_train_referenced_and_matched() -> None:
    source = _event_source()
    first = _catalog(source)
    shuffled = _catalog(source.sample(frac=1.0, random_state=91))
    pdt.assert_frame_equal(first, shuffled)

    assert set(first["event_type"]) == {
        "high_temperature",
        "rapid_warming",
        "flood",
        "low_flow",
    }
    assert first["threshold_reference_split"].eq("train").all()
    assert set(first["threshold_reference_scope"]) == {
        "station_doy_window",
        "station_season",
    }
    assert first["event_id"].is_unique
    assert first["control_id"].is_unique
    assert first["anchor_id"].is_unique
    assert first["pair_id"].is_unique
    assert (
        (first["raw_episode_end_index"] - first["raw_episode_start_index"] + 1)
        .eq(first["raw_episode_length"])
        .all()
    )
    assert (
        (first["window_end_index"] - first["window_start_index"] + 1)
        .eq(first["window_length"])
        .all()
    )
    assert (
        (first["control_end_index"] - first["control_start_index"] + 1)
        .eq(first["window_length"])
        .all()
    )

    flood = first.loc[first["event_type"].eq("flood")]
    assert flood["window_length"].eq(15).all()
    assert flood["window_center_index"].eq(flood["event_peak_index"]).all()
    assert flood["event_peak_date"].ne("").all()
    low = first.loc[first["event_type"].eq("low_flow")]
    assert low["raw_episode_length"].ge(7).all()
    assert low["event_min_date"].ne("").all()
    high = first.loc[first["event_type"].eq("high_temperature")]
    assert high["minimum_duration_days"].eq(3).all()
    assert high["merge_gap_days"].eq(2).all()

    derivations = {}
    for event_type in sorted(first["event_type"].unique()):
        dates, values, quality, splits = _event_arrays(source, event_type)
        derivations[event_type] = derive_event_day_condition(
            dates,
            values,
            quality,
            splits,
            event_type,
            source_split="test",
            minimum_training_samples=10,
        )
    for row in first.itertuples(index=False):
        start = int(row.control_start_index)
        stop = int(row.control_end_index) + 1
        assert stop - start == int(row.window_length)
        assert not derivations[str(row.event_type)].condition[start:stop].any()

    audit = audit_event_episode_catalog(first, source)
    assert audit["status"] == "passed"
    assert audit["episode_pair_count"] == len(first)
    assert (
        audit["control_rule"] == "same_station_same_season_same_window_length_non_event"
    )

    tampered = first.copy()
    tampered.loc[0, "threshold"] += 1.0
    with pytest.raises(EventCatalogAuditError):
        audit_event_episode_catalog(tampered, source)


def test_m7a_singletons_and_m7b_catalog_identity_grid(tmp_path: Path) -> None:
    stress_grid = build_experiment_grid(MANIFEST, CONFIG, suite="full")
    stress = [
        scenario
        for scenario in stress_grid.scenarios
        if scenario.condition.experiment == "M7a"
    ]
    assert len(stress) == 3 * 4
    assert {scenario.mask_seed for scenario in stress} == {0}
    assert len({scenario.scenario_id for scenario in stress}) == len(stress)
    assert all(
        scenario.condition.layout == "deterministic_stress_once"
        and scenario.condition.missing_rate == 1.0
        and scenario.condition.event_id
        and scenario.condition.anchor_id
        and scenario.condition.control_id is None
        and scenario.condition.minimum_training_samples == 30
        for scenario in stress
    )

    catalog = _catalog()
    catalog_path = tmp_path / "event_catalog.csv"
    catalog.to_csv(catalog_path, index=False)
    grid = build_experiment_grid(
        MANIFEST,
        CONFIG,
        suite="full",
        data_version="published_v1",
        evaluation_split="development_test",
        event_catalog_path=catalog_path,
    )
    episode_scenarios = [
        scenario
        for scenario in grid.scenarios
        if scenario.condition.experiment == "M7b"
    ]
    eligible_pairs = int(catalog["analysis_eligible"].sum())
    assert len(episode_scenarios) == 2 * eligible_pairs
    assert {scenario.mask_seed for scenario in episode_scenarios} == {0}
    assert grid.event_catalog_episode_count == len(catalog)
    assert grid.event_catalog_analysis_count == eligible_pairs
    assert grid.event_catalog_sha256
    for scenario in episode_scenarios:
        condition = scenario.condition
        assert condition.event_id and condition.control_id and condition.anchor_id
        assert condition.pair_id and condition.forced_start_index is not None
        assert condition.center_date and condition.analysis_eligible is True
        assert condition.threshold_reference_split == "train"
        assert condition.raw_episode_start_date and condition.window_start_date
        assert condition.event_definition and condition.event_window_length
        assert condition.catalog_role in {"event_episode", "matched_control"}
        expected_start = (
            condition.window_start_index
            if condition.catalog_role == "event_episode"
            else condition.control_start_index
        )
        assert condition.forced_start_index == expected_start


def test_event_masks_and_metrics_preserve_pair_identities_and_full_window() -> None:
    dates = np.arange(np.datetime64("2020-01-01"), np.datetime64("2020-05-01"))
    eligible = np.ones((len(dates), 1, 1), dtype=bool)
    event = np.zeros(len(dates), dtype=bool)
    event[20:23] = True
    identity = {
        "event_id": "EVENT-1",
        "control_id": "CONTROL-1",
        "anchor_id": "ANCHOR-1",
        "pair_id": "PAIR-1",
    }
    event_mask, event_metadata = generate_event_mask(
        eligible,
        event,
        "high_temperature",
        length=5,
        forced_start_index=20,
        dates=dates,
        catalog_role="event_episode",
        event_metadata={
            **identity,
            "catalog_role": "event_episode",
            "raw_episode_start_date": "2020-01-21",
            "window_start_date": "2020-01-21",
            "event_peak_date": "2020-01-22",
            "event_definition": "frozen-test-definition",
        },
        **identity,
    )
    control_mask, control_metadata = generate_event_mask(
        eligible,
        event,
        "high_temperature",
        length=5,
        forced_start_index=40,
        dates=dates,
        catalog_role="matched_control",
        **identity,
    )
    assert np.flatnonzero(event_mask[:, 0, 0]).tolist() == [20, 21, 22, 23, 24]
    assert np.flatnonzero(control_mask[:, 0, 0]).tolist() == [40, 41, 42, 43, 44]
    assert event_metadata["mask_type"] == "event_episode"
    assert event_metadata["event_condition_cells_in_mask"] == 3
    assert event_metadata["event_peak_date"] == "2020-01-22"
    assert control_metadata["mask_type"] == "event_control"
    for metadata in (event_metadata, control_metadata):
        assert metadata["event_id"] == "EVENT-1"
        assert metadata["control_id"] == "CONTROL-1"
        assert metadata["anchor_id"] == "ANCHOR-1"
        assert metadata["pair_id"] == "PAIR-1"

    stress_a, stress_metadata = generate_event_mask(
        eligible, event, "high_temperature", missing_rate=1.0, seed=0
    )
    stress_b, _ = generate_event_mask(
        eligible, event, "high_temperature", missing_rate=1.0, seed=999
    )
    np.testing.assert_array_equal(stress_a, stress_b)
    assert stress_metadata["selection_mode"] == "deterministic_all_event_cells"

    row = compute_event_metrics(
        np.array([1.0, 2.0, 3.0]),
        np.array([1.1, 2.1, 3.1]),
        np.ones(3, dtype=bool),
        np.ones(3, dtype=bool),
        target="T",
        metadata={
            "scenario_id": "SCENARIO-1",
            "station_id": "B1",
            "model": "linear",
            "training_seed": None,
            "mask_seed": 0,
            **identity,
            "catalog_role": "event_episode",
            "event_season": "DJF",
            "raw_episode_start_index": 0,
            "raw_episode_end_index": 2,
            "event_peak_index": 2,
            "event_peak_date": "2020-01-03",
            "event_peak_value": 3.0,
        },
        dates=pd.date_range("2020-01-01", periods=3),
        climatology_pred=np.array([0.0, 0.0, 0.0]),
    )
    assert row["pair_id"] == "PAIR-1"
    assert row["event_id"] == "EVENT-1"
    assert row["control_id"] == "CONTROL-1"
    assert row["anchor_id"] == "ANCHOR-1"
    assert row["event_peak_magnitude_error"] == pytest.approx(0.1)


def _runner_wide(source: pd.DataFrame, path: Path) -> Path:
    wide = source.pivot(index="date", columns="variable", values="value").reset_index()
    split = source[["date", "split"]].drop_duplicates().set_index("date")["split"]
    wide["split"] = wide["date"].map(split)
    day = np.arange(len(wide), dtype=float)
    for variable in ("T", "F"):
        wide[f"B1_{variable}"] = wide.pop(variable)
    wide["B1_L"] = 20.0 + 0.05 * wide["B1_F"]
    wide["B1_Ta"] = wide["B1_T"] - 2.0
    wide["B1_P"] = np.maximum(0.0, np.sin(day / 7.0))
    wide["B1_W"] = 2.0 + 0.1 * np.cos(day / 9.0)
    wide["B1_RH"] = 60.0 + np.sin(day / 11.0)
    wide["B1_Rs"] = 8.0 + np.cos(day / 13.0)
    days_in_year = np.where(pd.DatetimeIndex(wide["date"]).is_leap_year, 366.0, 365.0)
    phase = 2 * np.pi * (pd.DatetimeIndex(wide["date"]).dayofyear - 1) / days_in_year
    wide["day_of_year_sin"] = np.sin(phase)
    wide["day_of_year_cos"] = np.cos(phase)
    wide["month_sin"] = np.sin(
        2 * np.pi * (pd.DatetimeIndex(wide["date"]).month - 1) / 12
    )
    wide["month_cos"] = np.cos(
        2 * np.pi * (pd.DatetimeIndex(wide["date"]).month - 1) / 12
    )
    wide.to_parquet(path, index=False)
    return path


def test_runner_uses_catalog_forced_event_and_control_windows(tmp_path: Path) -> None:
    source = _event_source()
    catalog = _catalog(source)
    catalog_path = tmp_path / "catalog.csv"
    catalog.to_csv(catalog_path, index=False)
    grid = build_experiment_grid(
        MANIFEST,
        CONFIG,
        suite="full",
        evaluation_split="development_test",
        event_catalog_path=catalog_path,
    )
    eligible_row = catalog.loc[catalog["analysis_eligible"]].iloc[0]
    pair_scenarios = tuple(
        scenario
        for scenario in grid.scenarios
        if scenario.condition.experiment == "M7b"
        and scenario.condition.pair_id == eligible_row["pair_id"]
    )
    assert len(pair_scenarios) == 2
    mini_grid = replace(
        grid,
        conditions=tuple(scenario.condition for scenario in pair_scenarios),
        scenarios=pair_scenarios,
        mask_seeds=(0,),
    )
    runner = ExperimentRunner(
        mini_grid,
        wide_path=_runner_wide(source, tmp_path / "wide.parquet"),
        quality_path=None,
        output_dir=tmp_path / "results",
        mask_dir=tmp_path / "masks",
        config_path=CONFIG,
        models=("climatology",),
    )
    generated = {
        scenario.condition.catalog_role: runner._generate_mask(scenario)
        for scenario in pair_scenarios
    }
    event_mask, event_metadata = generated["event_episode"]
    control_mask, control_metadata = generated["matched_control"]
    event_positions = np.flatnonzero(event_mask[:, 0, :].any(axis=1))
    control_positions = np.flatnonzero(control_mask[:, 0, :].any(axis=1))
    assert event_positions.tolist() == list(
        range(
            int(eligible_row.window_start_index), int(eligible_row.window_end_index) + 1
        )
    )
    assert control_positions.tolist() == list(
        range(
            int(eligible_row.control_start_index),
            int(eligible_row.control_end_index) + 1,
        )
    )
    for metadata in (event_metadata, control_metadata):
        assert metadata["pair_id"] == eligible_row["pair_id"]
        assert metadata["event_id"] == eligible_row["event_id"]
        assert metadata["control_id"] == eligible_row["control_id"]
        assert metadata["event_definition"] == eligible_row["event_definition"]
        assert metadata["window_start_date"] == eligible_row["window_start_date"]


def test_script_17_builds_and_audits_deterministically(tmp_path: Path) -> None:
    source_path = tmp_path / "daily_long.parquet"
    catalog_path = tmp_path / "catalog.csv"
    audit_path = tmp_path / "catalog.audit.json"
    _event_source().to_parquet(source_path, index=False)
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts/17_build_event_catalog.py"),
        "build",
        "--input",
        str(source_path),
        "--catalog",
        str(catalog_path),
        "--audit-output",
        str(audit_path),
        "--config",
        str(CONFIG),
        "--minimum-training-samples",
        "10",
    ]
    subprocess.run(
        command, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True
    )
    first_catalog = catalog_path.read_bytes()
    first_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    subprocess.run(
        [*command, "--overwrite"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert catalog_path.read_bytes() == first_catalog
    assert json.loads(audit_path.read_text(encoding="utf-8")) == first_audit
    assert first_audit["status"] == "passed"
    assert first_audit["catalog_schema_version"] == "event_catalog_v2"
    assert first_audit["threshold_reference_split"] == "train"

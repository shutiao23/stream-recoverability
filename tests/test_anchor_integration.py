from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.experiments.grid import build_experiment_grid
from stream_recoverability.experiments.runner import ExperimentRunner
from stream_recoverability.experiments.science import (
    build_dense_science_grid,
    build_resilience_science_grid,
)
from stream_recoverability.experiments.validation import build_validation_funnel
from stream_recoverability.masks import (
    centered_bounds,
    load_validation_anchor_catalog,
    meteorological_season,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "study_manifest.yaml"
CONFIG = PROJECT_ROOT / "configs/experiments.yaml"
DESIGN = PROJECT_ROOT / "configs/design_freeze_v1.yaml"
FRONTIER_ANCHORS = PROJECT_ROOT / "metadata/frontier_anchors.csv"
VALIDATION_ANCHORS = PROJECT_ROOT / "metadata/validation_anchors.csv"
PRIMARY_ROOT = PROJECT_ROOT / "data_versions/published_v1"


def _runner(
    grid: object,
    root: Path,
    *,
    data_version: str = "published_v1",
) -> ExperimentRunner:
    data_root = PROJECT_ROOT / "data_versions" / data_version
    return ExperimentRunner(
        grid,
        wide_path=data_root / "daily_wide.parquet",
        quality_path=data_root / "daily_long.parquet",
        output_dir=root / "results",
        mask_dir=root / "masks",
        config_path=CONFIG,
        design_path=DESIGN,
        manifest_path=MANIFEST,
        models=("climatology",),
        training_seeds=(),
    )


def test_validation_catalog_is_jointly_complete_centered_and_season_auditable(
    tmp_path: Path,
) -> None:
    catalog = load_validation_anchor_catalog(
        VALIDATION_ANCHORS,
        expected_data_version="published_v1",
        required_stations=("B1", "S2", "P3"),
    )
    assert len(catalog) == 15
    assert catalog.groupby("station_id", observed=True).size().eq(5).all()
    assert set(catalog["complete_variables"]) == {"T_F_L"}
    assert set(catalog["max_supported_length"]) == {180}
    for _, group in catalog.groupby("station_id", observed=True):
        assert set(group["season"]) == {"DJF", "MAM", "JJA", "SON"}

    long_data = pd.read_parquet(PRIMARY_ROOT / "daily_long.parquet")
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(long_data["date"]).unique()))
    for row in catalog.itertuples(index=False):
        assert dates[row.center_index].strftime("%Y-%m-%d") == row.center_date
        assert meteorological_season(dates[row.center_index].month) == row.season
        start, stop = centered_bounds(row.center_index, 180, len(dates))
        assert dates[start].month == row.start_month
        selected = long_data.loc[
            long_data["station_id"].eq(row.station_id)
            & long_data["variable"].isin(("T", "F", "L"))
            & long_data["date"].between(dates[start], dates[stop - 1])
        ]
        assert len(selected) == 180 * 3
        assert selected["split"].eq("validation").all()
        assert selected["quality_approved"].all()
        assert selected["natural_observed"].all()
        assert np.isfinite(selected["value"]).all()

    funnel = build_validation_funnel(
        MANIFEST,
        CONFIG,
        anchor_catalog_path=VALIDATION_ANCHORS,
    )
    for station in ("B1", "S2", "P3"):
        for seed in range(101, 106):
            scenarios = [
                scenario
                for scenario in funnel.grid.scenarios
                if scenario.condition.station_ids == (station,)
                and scenario.mask_seed == seed
            ]
            assert len(scenarios) == 7
            assert len({scenario.condition.anchor_id for scenario in scenarios}) == 1
            assert len({scenario.condition.center_date for scenario in scenarios}) == 1
            assert len({scenario.condition.center_index for scenario in scenarios}) == 1

    runner = _runner(funnel.grid, tmp_path)
    scenario = next(
        item
        for item in funnel.grid.scenarios
        if item.condition.mask_type == "block"
        and item.condition.gap_length == 180
        and item.mask_seed == 101
    )
    mask, metadata = runner._generate_mask(scenario)
    assert mask[runner.validation_rows].any()
    assert not mask[runner.train_rows].any()
    assert not mask[runner.test_rows].any()
    assert metadata["anchor_id"] == scenario.condition.anchor_id
    assert metadata["center_date"] == scenario.condition.center_date
    assert metadata["center_index"] == scenario.condition.center_index


def test_core_point_families_and_block_anchors_are_strictly_nested(
    tmp_path: Path,
) -> None:
    grid = build_experiment_grid(
        MANIFEST,
        CONFIG,
        suite="core",
        frontier_anchor_path=FRONTIER_ANCHORS,
    )
    runner = _runner(grid, tmp_path)
    point_scenarios = sorted(
        (
            scenario
            for scenario in grid.scenarios
            if scenario.condition.experiment == "M1"
            and scenario.condition.station_ids == ("B1",)
            and scenario.condition.variables == ("T",)
            and scenario.mask_seed == 101
        ),
        key=lambda value: float(value.condition.missing_rate),
    )
    point_masks = [runner._generate_mask(scenario)[0] for scenario in point_scenarios]
    assert np.all(point_masks[0] <= point_masks[1])
    assert np.all(point_masks[1] <= point_masks[2])

    block_scenarios = sorted(
        (
            scenario
            for scenario in grid.scenarios
            if scenario.condition.experiment == "M2"
            and scenario.condition.station_ids == ("B1",)
            and scenario.condition.variables == ("T",)
            and scenario.mask_seed == 101
        ),
        key=lambda value: int(value.condition.gap_length),
    )
    assert [scenario.condition.gap_length for scenario in block_scenarios] == [
        10,
        30,
        90,
        180,
    ]
    assert len({scenario.condition.anchor_id for scenario in block_scenarios}) == 1
    assert len({scenario.condition.center_index for scenario in block_scenarios}) == 1
    masks = [runner._generate_mask(scenario)[0] for scenario in block_scenarios]
    assert all(np.all(left <= right) for left, right in pairwise(masks))
    assert all(not mask[~runner.test_rows].any() for mask in masks)


def test_dense_and_resilience_suites_reuse_one_target_anchor(
    tmp_path: Path,
) -> None:
    dense = build_dense_science_grid(
        MANIFEST,
        mask_seeds=(101,),
        frontier_anchor_path=FRONTIER_ANCHORS,
    )
    dense_scenarios = [
        scenario
        for scenario in dense.scenarios
        if scenario.condition.station_ids == ("B1",)
        and scenario.condition.variables == ("T",)
    ]
    assert len(dense_scenarios) == 15
    assert len({scenario.condition.anchor_id for scenario in dense_scenarios}) == 1
    assert len({scenario.condition.center_index for scenario in dense_scenarios}) == 1
    dense_runner = _runner(dense, tmp_path / "dense")
    selected = [
        next(
            scenario
            for scenario in dense_scenarios
            if scenario.condition.gap_length == length
        )
        for length in (1, 30, 365)
    ]
    dense_masks = [dense_runner._generate_mask(scenario)[0] for scenario in selected]
    assert np.all(dense_masks[0] <= dense_masks[1])
    assert np.all(dense_masks[1] <= dense_masks[2])

    resilience = build_resilience_science_grid(
        MANIFEST,
        mask_seeds=(101,),
        frontier_anchor_path=FRONTIER_ANCHORS,
    )
    scenarios = [
        scenario
        for scenario in resilience.scenarios
        if scenario.condition.station_ids == ("B1",)
        and scenario.condition.gap_length == 90
    ]
    assert len(scenarios) == 8
    assert len({scenario.condition.anchor_id for scenario in scenarios}) == 1
    assert len({scenario.condition.center_index for scenario in scenarios}) == 1
    resilience_runner = _runner(resilience, tmp_path / "resilience")
    target_station = resilience_runner.data.station_ids.index("B1")
    target_variable = resilience_runner.data.variable_names.index("T")
    target_gaps = [
        np.flatnonzero(
            resilience_runner._generate_mask(scenario)[0][
                :, target_station, target_variable
            ]
        )
        for scenario in scenarios
    ]
    assert all(np.array_equal(target_gaps[0], value) for value in target_gaps[1:])


def test_m6a_and_m6b_have_exact_axis_counts_and_geometry(tmp_path: Path) -> None:
    grid = build_experiment_grid(
        MANIFEST,
        CONFIG,
        suite="full",
        frontier_anchor_path=FRONTIER_ANCHORS,
    )
    m6a = [condition for condition in grid.conditions if condition.experiment == "M6a"]
    m6b = [condition for condition in grid.conditions if condition.experiment == "M6b"]
    assert len(m6a) == 3 * 4 * 4 * 3 == 144
    assert len(m6b) == 3 * 4 * 3 == 36
    assert {condition.variables for condition in m6a} == {
        ("T", "F"),
        ("T", "L"),
        ("F", "L"),
        ("T", "F", "L"),
    }
    assert {condition.async_axis for condition in m6a} == {"variable"}
    assert {condition.async_axis for condition in m6b} == {"station"}
    expected_targets = {
        ("T", "F"): "T",
        ("T", "L"): "T",
        ("F", "L"): "F",
        ("T", "F", "L"): "T",
    }
    for variables, target in expected_targets.items():
        selected = [
            scenario
            for scenario in grid.scenarios
            if scenario.condition.experiment == "M6a"
            and scenario.condition.station_ids == ("B1",)
            and scenario.condition.variables == variables
            and scenario.condition.gap_length == 10
            and scenario.mask_seed == 101
        ]
        assert len(selected) == 3
        assert {scenario.condition.anchor_target for scenario in selected} == {target}
        assert len({scenario.condition.anchor_id for scenario in selected}) == 1
        assert len({scenario.condition.center_index for scenario in selected}) == 1

    runner = _runner(grid, tmp_path)
    variable_scenario = next(
        scenario
        for scenario in grid.scenarios
        if scenario.condition.experiment == "M6a"
        and scenario.condition.variables == ("T", "F")
        and scenario.condition.gap_length == 10
        and scenario.condition.overlap_ratio == 0.5
        and scenario.mask_seed == 101
    )
    variable_mask, variable_metadata = runner._generate_mask(variable_scenario)
    station = runner.data.station_ids.index(variable_scenario.condition.station_ids[0])
    temperature = set(
        np.flatnonzero(variable_mask[:, station, runner.data.variable_names.index("T")])
    )
    flow = set(
        np.flatnonzero(variable_mask[:, station, runner.data.variable_names.index("F")])
    )
    assert len(temperature) == len(flow) == 10
    assert len(temperature & flow) == 5
    assert variable_metadata["overlap_axis"] == "variable"
    variable_family = [
        scenario
        for scenario in grid.scenarios
        if scenario.condition.experiment == "M6a"
        and scenario.condition.station_ids == ("B1",)
        and scenario.condition.variables == ("T", "F")
        and scenario.condition.gap_length == 10
        and scenario.mask_seed == 101
    ]
    variable_family_outputs = [runner._generate_mask(value) for value in variable_family]
    target_index = runner.data.variable_names.index("T")
    target_days = [
        np.flatnonzero(mask[:, station, target_index])
        for mask, _ in variable_family_outputs
    ]
    assert all(np.array_equal(target_days[0], value) for value in target_days[1:])
    assert len(
        {metadata["target_gap_id"] for _, metadata in variable_family_outputs}
    ) == 1
    assert {
        metadata["selection_mode"] for _, metadata in variable_family_outputs
    } == {"fixed_target_center"}

    station_scenario = next(
        scenario
        for scenario in grid.scenarios
        if scenario.condition.experiment == "M6b"
        and scenario.condition.gap_length == 10
        and scenario.condition.overlap_ratio == 0.0
        and scenario.mask_seed == 101
    )
    station_mask, station_metadata = runner._generate_mask(station_scenario)
    first, second = [runner.data.station_ids.index(value) for value in station_scenario.condition.station_ids]
    first_days = set(np.flatnonzero(station_mask[:, first].any(axis=1)))
    second_days = set(np.flatnonzero(station_mask[:, second].any(axis=1)))
    assert len(first_days) == len(second_days) == 10
    assert not first_days.intersection(second_days)
    assert station_metadata["overlap_axis"] == "station"
    station_family = [
        scenario
        for scenario in grid.scenarios
        if scenario.condition.experiment == "M6b"
        and scenario.condition.station_ids == station_scenario.condition.station_ids
        and scenario.condition.gap_length == 10
        and scenario.mask_seed == 101
    ]
    assert len(station_family) == 3
    assert {scenario.condition.anchor_target for scenario in station_family} == {"T"}
    assert len({scenario.condition.anchor_id for scenario in station_family}) == 1
    station_family_outputs = [runner._generate_mask(value) for value in station_family]
    target_days = [
        np.flatnonzero(mask[:, first, target_index])
        for mask, _ in station_family_outputs
    ]
    assert all(np.array_equal(target_days[0], value) for value in target_days[1:])
    assert len(
        {metadata["target_gap_id"] for _, metadata in station_family_outputs}
    ) == 1


def test_sensitivity_reuses_primary_ids_and_reports_no_replacement(
    tmp_path: Path,
) -> None:
    primary = build_experiment_grid(
        MANIFEST,
        CONFIG,
        suite="core",
        data_version="published_v1",
        frontier_anchor_path=FRONTIER_ANCHORS,
    )
    sensitivity = build_experiment_grid(
        MANIFEST,
        CONFIG,
        suite="core",
        data_version="no_s2_suspect_v1",
        frontier_anchor_path=FRONTIER_ANCHORS,
    )
    primary_ids = {
        (scenario.condition.condition_id, scenario.mask_seed): scenario.condition.anchor_id
        for scenario in primary.scenarios
        if scenario.condition.anchor_id is not None
    }
    sensitivity_ids = {
        (scenario.condition.condition_id, scenario.mask_seed): scenario.condition.anchor_id
        for scenario in sensitivity.scenarios
        if scenario.condition.anchor_id is not None
    }
    assert sensitivity_ids == primary_ids

    runner = _runner(
        sensitivity,
        tmp_path,
        data_version="no_s2_suspect_v1",
    )
    report = runner.anchor_availability
    assert not report.empty
    assert set(report["anchor_data_version"]) == {"published_v1"}
    assert set(report["data_version"]) == {"no_s2_suspect_v1"}
    assert not report["replacement_allowed"].any()
    assert (~report["available"]).any()


def test_catalog_identity_mismatch_is_rejected_without_filtering(tmp_path: Path) -> None:
    catalog = pd.read_csv(FRONTIER_ANCHORS)
    catalog["evaluation_split"] = "validation"
    mismatched = tmp_path / "frontier_anchors.csv"
    catalog.to_csv(mismatched, index=False)
    with pytest.raises(ValueError, match="evaluation_split mismatch"):
        build_experiment_grid(
            MANIFEST,
            CONFIG,
            suite="core",
            frontier_anchor_path=mismatched,
        )

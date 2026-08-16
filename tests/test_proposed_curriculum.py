from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from stream_recoverability.models.proposed_curriculum import (
    CURRICULUM_SCENARIOS,
    FROZEN_VALIDATION_SCENARIOS,
    ProposedCurriculumConfig,
    generate_curriculum_mask,
    sample_curriculum_scenarios,
)

VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "Rs")


def test_frozen_curriculum_probabilities_and_schedule_are_deterministic() -> None:
    config = ProposedCurriculumConfig()
    assert config.probability_map == {
        "point": 0.20,
        "single_block": 0.25,
        "multiblock": 0.15,
        "synchronous_variable_group": 0.15,
        "hydrological_station_outage": 0.10,
        "meteorology_dropout": 0.05,
        "same_station_variable_async": 0.05,
        "cross_station_async": 0.05,
    }
    first = sample_curriculum_scenarios(20_000, 17, config)
    second = sample_curriculum_scenarios(20_000, 17, config)
    assert first == second
    observed = Counter(first)
    for scenario, probability in config.probability_map.items():
        assert observed[scenario] / len(first) == pytest.approx(probability, abs=0.01)


def test_each_curriculum_geometry_is_finite_only_and_reproducible() -> None:
    eligible = np.ones((184, 3, len(VARIABLES)), dtype=bool)
    eligible[5:9, 0, 0] = False
    for seed, scenario in enumerate(CURRICULUM_SCENARIOS):
        first = generate_curriculum_mask(
            eligible,
            VARIABLES,
            scenario=scenario,
            protocol="seen_length",
            seed=seed,
        )
        second = generate_curriculum_mask(
            eligible,
            VARIABLES,
            scenario=scenario,
            protocol="seen_length",
            seed=seed,
        )
        assert np.array_equal(first.artificial_mask, second.artificial_mask)
        assert first.metadata == second.metadata
        assert first.artificial_mask.dtype == np.bool_
        assert first.artificial_mask.shape == eligible.shape
        assert not np.any(first.artificial_mask & ~eligible)
        assert first.artificial_mask[..., 0].any()
        assert first.metadata["training_masked_cells"] == int(
            first.artificial_mask.sum()
        )
        assert first.metadata["training_target_masked_cells"] == int(
            first.artificial_mask[..., 0].sum()
        )


def test_curriculum_channel_geometry_matches_scenario_semantics() -> None:
    eligible = np.ones((184, 3, len(VARIABLES)), dtype=bool)
    generated = {
        scenario: generate_curriculum_mask(
            eligible,
            VARIABLES,
            scenario=scenario,
            protocol="seen_length",
            seed=seed,
        )
        for seed, scenario in enumerate(CURRICULUM_SCENARIOS)
    }

    point = generated["point"].artificial_mask
    assert set(np.flatnonzero(point.any(axis=(0, 1)))) == {0}
    assert int(point[..., 0].any(axis=0).sum()) == 1

    single = generated["single_block"].artificial_mask
    assert set(np.flatnonzero(single.any(axis=(0, 1)))) == {0}
    assert int(single[..., 0].any(axis=0).sum()) == 1

    multiblock = generated["multiblock"].artificial_mask
    target_series = multiblock[..., 0].any(axis=1)
    padded = np.pad(target_series.astype(int), (1, 1))
    assert int((np.diff(padded) == 1).sum()) == 3

    synchronous = generated["synchronous_variable_group"].artificial_mask
    sync_channels = np.argwhere(synchronous.any(axis=0))
    assert np.unique(sync_channels[:, 0]).size == 1
    sync_station = int(sync_channels[0, 0])
    sync_variables = np.flatnonzero(synchronous[:, sync_station].any(axis=0))
    supports = [synchronous[:, sync_station, variable] for variable in sync_variables]
    assert all(np.array_equal(supports[0], value) for value in supports[1:])
    assert set(sync_variables).issubset({0, 1, 2}) and 0 in sync_variables

    outage = generated["hydrological_station_outage"].artificial_mask
    outage_channels = np.argwhere(outage.any(axis=0))
    assert np.unique(outage_channels[:, 0]).size == 1
    assert set(outage_channels[:, 1]) == {0, 1, 2}

    weather = generated["meteorology_dropout"].artificial_mask
    weather_channels = np.argwhere(weather.any(axis=0))
    assert np.unique(weather_channels[:, 0]).size == 1
    assert set(weather_channels[:, 1]) == set(range(len(VARIABLES))) - {1, 2}

    same_site = generated["same_station_variable_async"].artificial_mask
    same_channels = np.argwhere(same_site.any(axis=0))
    assert np.unique(same_channels[:, 0]).size == 1
    same_station = int(same_channels[0, 0])
    same_variables = np.flatnonzero(same_site[:, same_station].any(axis=0))
    starts = [
        int(np.flatnonzero(same_site[:, same_station, variable])[0])
        for variable in same_variables
    ]
    same_overlap = generated["same_station_variable_async"].metadata["overlap_ratio"]
    assert same_overlap in {0.0, 0.5, 1.0}
    assert 0 in same_variables
    if same_overlap == 1.0:
        assert len(set(starts)) == 1
    else:
        assert len(set(starts)) == len(starts)

    cross_site = generated["cross_station_async"].artificial_mask
    cross_channels = np.argwhere(cross_site.any(axis=0))
    cross_stations = np.unique(cross_channels[:, 0])
    assert cross_stations.size == 2
    starts = []
    for station in cross_stations:
        assert set(np.flatnonzero(cross_site[:, station].any(axis=0))) == {0, 1, 2}
        torch_support = cross_site[:, station, 0]
        assert np.array_equal(torch_support, cross_site[:, station, 1])
        assert np.array_equal(torch_support, cross_site[:, station, 2])
        starts.append(int(np.flatnonzero(torch_support)[0]))
    cross_overlap = generated["cross_station_async"].metadata["overlap_ratio"]
    assert cross_overlap in {0.0, 0.5, 1.0}
    assert (starts[0] == starts[1]) is (cross_overlap == 1.0)


def test_async_curriculum_covers_all_frozen_overlap_endpoints() -> None:
    eligible = np.ones((368, 3, len(VARIABLES)), dtype=bool)
    for scenario in ("same_station_variable_async", "cross_station_async"):
        ratios = {
            generate_curriculum_mask(
                eligible,
                VARIABLES,
                scenario=scenario,
                protocol="seen_length",
                seed=seed,
            ).metadata["overlap_ratio"]
            for seed in range(100)
        }
        assert ratios == {0.0, 0.5, 1.0}


def test_unseen_curriculum_caps_gaps_and_validation_suite_is_frozen() -> None:
    eligible = np.ones((184, 3, len(VARIABLES)), dtype=bool)
    for scenario in CURRICULUM_SCENARIOS:
        for seed in range(20):
            result = generate_curriculum_mask(
                eligible,
                VARIABLES,
                scenario=scenario,
                protocol="unseen_length",
                seed=seed,
            )
            assert result.metadata["training_gap_length"] <= 90

    expected_lengths = {
        "point": 1,
        "short_block": 14,
        "long_block": 90,
        "station_outage": 90,
    }
    assert FROZEN_VALIDATION_SCENARIOS == tuple(expected_lengths)
    for seed, scenario in enumerate(FROZEN_VALIDATION_SCENARIOS, start=100):
        result = generate_curriculum_mask(
            eligible,
            VARIABLES,
            scenario=scenario,
            protocol="unseen_length",
            seed=seed,
        )
        assert result.metadata["validation_scenario"] == scenario
        assert result.metadata["training_gap_length"] == expected_lengths[scenario]


def test_main_curriculum_requires_rs_and_rejects_silent_dh_fallback() -> None:
    eligible = np.ones((184, 3, 8), dtype=bool)
    dh_only = ("T", "F", "L", "Ta", "P", "W", "RH", "DH")
    with pytest.raises(ValueError, match="requires Rs"):
        generate_curriculum_mask(
            eligible,
            dh_only,
            scenario="point",
            protocol="seen_length",
            seed=0,
        )
    sensitivity = generate_curriculum_mask(
        eligible,
        dh_only,
        scenario="point",
        protocol="seen_length",
        seed=0,
        jinsha_sunshine_sensitivity=True,
    )
    assert sensitivity.artificial_mask[..., 0].any()
    with pytest.raises(ValueError, match="cannot include main Rs"):
        generate_curriculum_mask(
            eligible,
            VARIABLES,
            scenario="point",
            protocol="seen_length",
            seed=0,
            jinsha_sunshine_sensitivity=True,
        )

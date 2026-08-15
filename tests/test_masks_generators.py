from __future__ import annotations

import numpy as np
import pytest

from stream_recoverability.masks import (
    generate_async_mask,
    generate_block_mask,
    generate_event_mask,
    generate_multiblock_mask,
    generate_network_outage_mask,
    generate_point_mask,
    generate_station_outage_mask,
)


STATIONS = ["S1", "S2", "S3"]
VARIABLES = ["T", "F", "L", "Ta"]


def test_point_mask_exact_rate() -> None:
    eligible = np.ones((100, 1, 3), dtype=bool)
    synchronized, _ = generate_point_mask(
        eligible,
        0.30,
        variable_indices=[0, 1, 2],
        synchronized=True,
        seed=7,
    )
    assert synchronized.sum() == 90
    assert np.all(synchronized.sum(axis=0) == 30)

    independent, _ = generate_point_mask(
        eligible,
        0.30,
        variable_indices=[0, 1, 2],
        synchronized=False,
        seed=7,
    )
    assert independent.sum() == 90
    assert np.all(independent.sum(axis=0) == 30)


def test_block_mask_exact_length() -> None:
    dates = np.arange(
        np.datetime64("2020-01-01"), np.datetime64("2021-01-01")
    )
    eligible = np.ones((len(dates), 1, 1), dtype=bool)
    mask, metadata = generate_block_mask(
        eligible, 30, dates=dates, season="summer", seed=3
    )
    positions = np.flatnonzero(mask[:, 0, 0])
    assert len(positions) == 30
    assert np.all(np.diff(positions) == 1)
    assert metadata["gap_lengths"] == [30]
    assert metadata["season"] == "summer"


@pytest.mark.parametrize(
    ("budget", "segments"),
    [(10, [3, 3, 4]), (30, [10, 10, 10]), (90, [30, 30, 30]), (180, [60, 60, 60])],
)
def test_multiblock_total_budget(budget: int, segments: list[int]) -> None:
    eligible = np.ones((800, 1, 1), dtype=bool)
    mask, metadata = generate_multiblock_mask(
        eligible, budget, minimum_gap=30, seed=11
    )
    assert int(mask.sum()) == budget
    assert metadata["gap_lengths"] == segments
    for previous_end, next_start in zip(
        metadata["end_indices"][:-1], metadata["start_indices"][1:], strict=True
    ):
        assert next_start - previous_end - 1 >= 30


def test_variable_pattern_correctness() -> None:
    eligible = np.ones((120, 2, 4), dtype=bool)
    mask, _ = generate_block_mask(
        eligible,
        20,
        station_indices=[1],
        variable_indices=[0, 2],
        seed=5,
    )
    assert mask[:, 1, 0].sum() == 20
    assert mask[:, 1, 2].sum() == 20
    assert not mask[:, 0, :].any()
    assert not mask[:, 1, 1].any()
    assert not mask[:, 1, 3].any()


def test_no_overlap_with_bad_ground_truth() -> None:
    eligible = np.ones((100, 1, 1), dtype=bool)
    eligible[20:30, 0, 0] = False
    point, _ = generate_point_mask(eligible, 0.50, seed=9)
    block, _ = generate_block_mask(eligible, 15, seed=9)
    assert not np.any(point & ~eligible)
    assert not np.any(block & ~eligible)


def test_mask_reproducibility() -> None:
    eligible = np.ones((120, 1, 2), dtype=bool)
    first_mask, first_metadata = generate_point_mask(
        eligible, 0.30, seed=42, synchronized=False
    )
    second_mask, second_metadata = generate_point_mask(
        eligible, 0.30, seed=42, synchronized=False
    )
    assert np.array_equal(first_mask, second_mask)
    assert first_metadata == second_metadata
    different_mask, _ = generate_point_mask(
        eligible, 0.30, seed=43, synchronized=False
    )
    assert not np.array_equal(first_mask, different_mask)


def test_same_mask_across_models() -> None:
    eligible = np.ones((120, 1, 1), dtype=bool)
    shared_mask, metadata = generate_block_mask(eligible, 30, seed=17)
    model_a_mask = shared_mask.copy()
    model_b_mask = shared_mask.copy()
    assert metadata["scenario_id"]
    assert np.array_equal(model_a_mask, model_b_mask)


def test_station_outage_masks_all_required_channels() -> None:
    eligible = np.ones((150, 2, 4), dtype=bool)
    hydro, hydro_metadata = generate_station_outage_mask(
        eligible,
        1,
        30,
        mode="hydro-only",
        seed=4,
        station_ids=["S1", "S2"],
        variable_names=VARIABLES,
    )
    assert hydro[:, 1, :3].sum() == 90
    assert not hydro[:, 1, 3].any()
    assert not hydro[:, 0, :].any()
    assert hydro_metadata["outage_mode"] == "hydro-only"

    full, full_metadata = generate_station_outage_mask(
        eligible,
        1,
        30,
        mode="full-site",
        seed=4,
        station_ids=["S1", "S2"],
        variable_names=VARIABLES,
    )
    assert full[:, 1, :].sum() == 120
    assert full_metadata["outage_mode"] == "full-site"


@pytest.mark.parametrize("overlap", [0.0, 0.5, 1.0])
def test_async_overlap_ratio(overlap: float) -> None:
    eligible = np.ones((200, 2, 1), dtype=bool)
    mask, metadata = generate_async_mask(
        eligible,
        30,
        overlap,
        station_indices=[0, 1],
        variable_indices=[0],
        axis="station",
        seed=8,
    )
    first = set(np.flatnonzero(mask[:, 0, 0]))
    second = set(np.flatnonzero(mask[:, 1, 0]))
    assert len(first) == len(second) == 30
    assert len(first & second) / 30 == overlap
    assert metadata["overlap_ratio"] == overlap


def test_synchronized_multi_station_mask() -> None:
    eligible = np.ones((150, 3, 3), dtype=bool)
    mask, metadata = generate_network_outage_mask(
        eligible,
        [0, 2],
        30,
        variable_indices=[0, 1, 2],
        seed=2,
        station_ids=STATIONS,
        variable_names=VARIABLES[:3],
    )
    assert np.array_equal(mask[:, 0, :], mask[:, 2, :])
    assert not mask[:, 1, :].any()
    assert metadata["overlap_ratio"] == 1.0


def test_event_condition_mask() -> None:
    eligible = np.ones((100, 1, 1), dtype=bool)
    event = np.zeros(100, dtype=bool)
    event[30:70] = True
    eligible[40, 0, 0] = False
    mask, metadata = generate_event_mask(
        eligible, event, "high_temperature", missing_rate=0.5, seed=10
    )
    assert not np.any(mask[:, 0, 0] & ~event)
    assert not np.any(mask & ~eligible)
    assert metadata["event_type"] == "high_temperature"

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.masks import (
    FRONTIER_ANCHOR_COLUMNS,
    AnchorAvailabilityError,
    centered_bounds,
    generate_block_mask,
    generate_frontier_anchor_catalog,
    generate_nested_point_mask_family,
    generate_point_mask,
)


def _long_data() -> pd.DataFrame:
    dates = pd.date_range("2015-01-01", "2021-12-31", freq="D")
    rows: list[dict[str, object]] = []
    for station_offset, station_id in enumerate(("B1", "S2")):
        for variable_offset, variable in enumerate(("T", "F", "L")):
            for index, date in enumerate(dates):
                value = (
                    10.0
                    + station_offset
                    + variable_offset
                    + np.sin(index / (17.0 + variable_offset))
                )
                rows.append(
                    {
                        "date": date,
                        "station_id": station_id,
                        "variable": variable,
                        "value": value,
                        "quality_approved": True,
                        "split": "train" if date.year <= 2017 else "test",
                        "data_version": "published_v1",
                    }
                )
    return pd.DataFrame(rows)


def test_centered_bounds_have_one_even_length_convention_and_strict_nesting() -> None:
    center = 500
    lengths = (1, 3, 7, 10, 14, 21, 30, 45, 60, 90, 180, 365)
    previous: set[int] | None = None
    for length in lengths:
        start, stop = centered_bounds(center, length, 1_000)
        current = set(range(start, stop))
        assert len(current) == length
        assert center in current
        if length % 2 == 0:
            assert center - start == length // 2 - 1
        if previous is not None:
            assert previous < current
        previous = current


def test_block_masks_share_center_and_validate_fixed_locations() -> None:
    dates = np.arange(np.datetime64("2020-01-01"), np.datetime64("2021-02-04"))
    eligible = np.ones((len(dates), 1, 1), dtype=bool)
    center = 200
    masks = []
    for length in (10, 30, 90):
        mask, metadata = generate_block_mask(
            eligible,
            length,
            center_index=center,
            center_date=dates[center],
            dates=dates,
            anchor_id="ANCHOR-1",
            seed=101,
        )
        masks.append(mask)
        assert metadata["selection_mode"] == "fixed_center"
        assert metadata["center_index"] == center
        assert metadata["center_date"] == str(dates[center])
        assert metadata["anchor_id"] == "ANCHOR-1"
    assert np.all(masks[0] <= masks[1])
    assert np.all(masks[1] <= masks[2])
    assert masks[0].sum() < masks[1].sum() < masks[2].sum()

    forced, metadata = generate_block_mask(
        eligible, 10, forced_start_index=25, dates=dates, seed=7
    )
    assert np.flatnonzero(forced[:, 0, 0]).tolist() == list(range(25, 35))
    assert metadata["selection_mode"] == "forced_start"

    centered_start, _ = centered_bounds(center, 10, len(dates))
    combined, metadata = generate_block_mask(
        eligible,
        10,
        forced_start_index=centered_start,
        center_index=center,
        center_date=dates[center],
        dates=dates,
    )
    assert metadata["selection_mode"] == "fixed_center_and_start"
    assert np.flatnonzero(combined[:, 0, 0]).tolist() == list(
        range(centered_start, centered_start + 10)
    )
    with pytest.raises(ValueError, match="inconsistent"):
        generate_block_mask(eligible, 10, forced_start_index=25, center_index=center)
    with pytest.raises(ValueError, match="different positions"):
        generate_block_mask(
            eligible,
            10,
            center_index=center,
            center_date=dates[center + 1],
            dates=dates,
        )
    eligible[25, 0, 0] = False
    with pytest.raises(ValueError, match="not eligible"):
        generate_block_mask(eligible, 10, forced_start_index=25)


def test_legacy_seeded_block_and_point_selection_remain_backward_compatible() -> None:
    eligible = np.ones((100, 1, 1), dtype=bool)
    block, block_metadata = generate_block_mask(eligible, 10, seed=17)
    expected_start = int(np.random.default_rng(17).choice(np.arange(91)))
    assert np.flatnonzero(block[:, 0, 0]).tolist() == list(
        range(expected_start, expected_start + 10)
    )
    assert block_metadata["selection_mode"] == "seeded_random"

    point, point_metadata = generate_point_mask(eligible, 0.30, seed=17)
    expected_points = np.random.default_rng(17).choice(
        np.arange(100), size=30, replace=False
    )
    assert set(np.flatnonzero(point[:, 0, 0])) == set(expected_points)
    assert point_metadata["selection_mode"] == "seeded_random"


def test_nested_point_family_uses_one_season_balanced_prefix_ranking() -> None:
    dates = np.arange(np.datetime64("2020-01-01"), np.datetime64("2021-01-01"))
    eligible = np.ones((len(dates), 1, 1), dtype=bool)
    family = generate_nested_point_mask_family(
        eligible,
        dates=dates,
        seed=29,
        station_ids=["B1"],
        variable_names=["T"],
    )
    repeated = generate_nested_point_mask_family(
        eligible,
        dates=dates,
        seed=29,
        station_ids=["B1"],
        variable_names=["T"],
    )
    masks = [family[rate][0] for rate in (0.10, 0.30, 0.50)]
    assert [int(mask.sum()) for mask in masks] == [37, 110, 183]
    assert np.all(masks[0] <= masks[1])
    assert np.all(masks[1] <= masks[2])
    assert masks[0].sum() < masks[1].sum() < masks[2].sum()
    for rate in family:
        assert np.array_equal(family[rate][0], repeated[rate][0])
        metadata = family[rate][1]
        assert metadata["point_family_id"] == family[0.10][1]["point_family_id"]
        assert metadata["nested_rates"] == [0.10, 0.30, 0.50]
        assert (
            max(metadata["season_counts"].values())
            - min(metadata["season_counts"].values())
            <= 1
        )


def test_supplied_point_ranking_preserves_exact_counts_and_rejects_ineligible_rank() -> (
    None
):
    eligible = np.ones((50, 1, 1), dtype=bool)
    eligible[7, 0, 0] = False
    ranking = np.flatnonzero(eligible[:, 0, 0])[::-1]
    small, _ = generate_point_mask(eligible, 0.10, seed=1, candidate_ranking=ranking)
    large, _ = generate_point_mask(eligible, 0.50, seed=999, candidate_ranking=ranking)
    assert small.sum() == 5
    assert large.sum() == 25
    assert np.all(small <= large)
    with pytest.raises(ValueError, match="every eligible candidate exactly once"):
        generate_point_mask(eligible, 0.30, candidate_ranking=np.arange(len(eligible)))


def test_independent_nested_point_family_preserves_channel_eligibility() -> None:
    dates = np.arange(np.datetime64("2020-01-01"), np.datetime64("2020-04-10"))
    eligible = np.ones((len(dates), 2, 2), dtype=bool)
    eligible[::7, 0, 0] = False
    eligible[::9, 1, 1] = False
    family = generate_nested_point_mask_family(
        eligible,
        dates=dates,
        synchronized=False,
        seed=41,
    )
    small = family[0.10][0]
    medium = family[0.30][0]
    large = family[0.50][0]
    assert np.all(small <= medium)
    assert np.all(medium <= large)
    assert not np.any(large & ~eligible)
    for station in range(2):
        for variable in range(2):
            available = int(eligible[:, station, variable].sum())
            assert int(small[:, station, variable].sum()) == int(
                np.floor(available * 0.10 + 0.5)
            )
            assert int(large[:, station, variable].sum()) == int(
                np.floor(available * 0.50 + 0.5)
            )


def test_frontier_catalog_is_deterministic_balanced_and_quality_eligible() -> None:
    source = _long_data()
    kwargs = {
        "evaluation_split": "development_test",
        "data_version": "published_v1",
        "targets": ("T", "F"),
        "max_supported_length": 365,
    }
    catalog = generate_frontier_anchor_catalog(source, **kwargs)
    shuffled = generate_frontier_anchor_catalog(
        source.sample(frac=1.0, random_state=91).reset_index(drop=True), **kwargs
    )
    pd.testing.assert_frame_equal(catalog, shuffled)
    assert tuple(catalog.columns) == FRONTIER_ANCHOR_COLUMNS
    assert len(catalog) == 2 * 2 * 20
    assert not catalog["anchor_id"].duplicated().any()
    for _, group in catalog.groupby(["station_id", "target"], observed=True):
        assert group["mask_seed"].tolist() == list(range(101, 121))
        assert group["season"].value_counts().to_dict() == {
            "DJF": 5,
            "MAM": 5,
            "JJA": 5,
            "SON": 5,
        }
        assert group["center_date"].nunique() == 20
    assert set(catalog["data_version"]) == {"published_v1"}
    assert set(catalog["evaluation_split"]) == {"development_test"}
    assert set(catalog["source_split"]) == {"test"}
    assert set(catalog["hydrologic_state"]) <= {
        "low_flow",
        "normal_flow",
        "high_flow",
        "unknown",
    }
    dates = pd.DatetimeIndex(sorted(source["date"].unique()))
    for anchor in catalog.itertuples(index=False):
        _, stop = centered_bounds(
            int(anchor.center_index), int(anchor.max_supported_length), len(dates)
        )
        assert stop <= len(dates) - 1

    first = catalog.iloc[0]
    start, stop = centered_bounds(
        int(first["center_index"]), int(first["max_supported_length"]), len(dates)
    )
    truth = source.loc[
        source["station_id"].eq(first["station_id"])
        & source["variable"].eq(first["target"])
    ].sort_values("date")
    assert truth.iloc[start:stop]["quality_approved"].all()
    assert truth.iloc[start:stop]["split"].eq("test").all()


def test_frontier_catalog_fails_with_machine_readable_availability_report() -> None:
    source = _long_data()
    jja = source["date"].dt.month.isin([6, 7, 8])
    target = source["station_id"].eq("B1") & source["variable"].eq("T")
    source.loc[jja & target & source["split"].eq("test"), "quality_approved"] = False
    with pytest.raises(AnchorAvailabilityError) as captured:
        generate_frontier_anchor_catalog(
            source,
            evaluation_split="development_test",
            data_version="published_v1",
            station_ids=("B1",),
            targets=("T",),
            max_supported_length=1,
        )
    report = captured.value.report
    failure = report.loc[report["season"].eq("JJA")].iloc[0]
    assert failure["available_candidate_centers"] == 0
    assert failure["shortfall"] == 5
    assert "B1" in str(captured.value) and "JJA" in str(captured.value)


def test_anchor_metadata_is_validated_and_recorded_by_block_generator() -> None:
    source = _long_data()
    catalog = generate_frontier_anchor_catalog(
        source,
        evaluation_split="development_test",
        data_version="published_v1",
        station_ids=("B1",),
        targets=("T",),
        max_supported_length=30,
    )
    anchor = catalog.iloc[0].to_dict()
    dates = pd.DatetimeIndex(sorted(source["date"].unique())).to_numpy(
        dtype="datetime64[D]"
    )
    eligible = np.ones((len(dates), 1, 1), dtype=bool)
    _, metadata = generate_block_mask(
        eligible,
        10,
        dates=dates,
        seed=int(anchor["mask_seed"]),
        anchor_metadata=anchor,
    )
    assert metadata["anchor_id"] == anchor["anchor_id"]
    assert metadata["center_index"] == anchor["center_index"]
    assert metadata["center_date"] == anchor["center_date"]
    assert metadata["data_version"] == "published_v1"
    assert metadata["evaluation_split"] == "development_test"
    assert metadata["source_split"] == "test"
    with pytest.raises(ValueError, match="mask_seed"):
        generate_block_mask(
            eligible,
            10,
            dates=dates,
            seed=999,
            anchor_metadata=anchor,
        )

"""Pending test for F-1. Copy into tests/test_validation_finalization.py after the source fix."""

from stream_recoverability.experiments import validation_finalization as finalization
from stream_recoverability.experiments.validation import (
    VALIDATION_MASK_SEEDS,
    VALIDATION_STATIONS,
)


def test_expected_scenario_ids_include_validation_split_token() -> None:
    ids = finalization._expected_scenario_ids()
    conditions_per_station = 7
    assert len(ids) == (
        len(VALIDATION_STATIONS) * conditions_per_station * len(VALIDATION_MASK_SEEDS)
    )
    for station in VALIDATION_STATIONS:
        for seed in VALIDATION_MASK_SEEDS:
            assert f"VAL-PNT-{station}-T-P30-VALIDATION-R{seed:04d}" in ids
            assert f"VAL-BLK1-{station}-T-D010-VALIDATION-R{seed:04d}" in ids
            assert f"VAL-PNT-{station}-T-P30-R{seed:04d}" not in ids
    assert all("-VALIDATION-R" in item for item in ids)

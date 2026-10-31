from pathlib import Path
import importlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
S = importlib.import_module("421_wrr_backup_history_upper_bound")


def test_optimistic_union_can_bound_complementary_recorders_without_inventing_a_gap():
    dates = pd.date_range("2020-01-01", "2020-12-31")
    a, b = pd.Series(0., index=dates), pd.Series(20., index=dates)
    a.iloc[::2] = np.nan
    b.iloc[1::2] = np.nan
    assert S.optimistic_complete_years([a, b]) == [2020]
    b.iloc[0] = np.nan
    assert S.optimistic_complete_years([a, b]) == []


def test_target_or_future_complete_years_cannot_supply_prior_history():
    assert S.prior_years([2020, 2021, 2022], 2021) == [2020]
    assert S.optimistic_complete_years([]) == []


def test_complementary_hours_are_not_missed_by_a_whole_day_substitution_bound():
    times = pd.date_range("2020-01-01", "2020-12-31T23:00:00", freq="h", tz="UTC")
    frame = pd.DataFrame({"Time_UTC": times.astype(str), "WaterTemperature_Celsius": 10.})
    settings = {"gross_water_temperature_range_C": [-2, 40],
                "coverage": {"minimum_distinct_hours": 20, "minimum_span_hours": 20}}
    assert S.optimistic_hourly_years(frame.loc[times.hour < 12], settings) == []
    assert S.optimistic_hourly_years(frame.loc[times.hour >= 12], settings) == []
    assert S.optimistic_hourly_years(frame, settings) == [2020]

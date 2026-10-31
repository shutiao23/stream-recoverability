"""Published reference years require one finite value every calendar day."""
import importlib.util
from pathlib import Path
import pandas as pd

spec = importlib.util.spec_from_file_location('bc_qualification', Path(__file__).resolve().parents[1] / 'scripts/543_bc_reference_qualification.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_complete_published_years_do_not_prove_full_hourly_coverage_and_duplicates_are_rejected():
    roster = pd.DataFrame([dict(station_number='X', station_name='X creek', latitude=50., longitude=-120., status='unregulated')])
    dates = pd.date_range('2016-01-01', '2019-12-31', freq='D')
    frame = pd.DataFrame(dict(station_number='X', date=dates, tw_obs=3.))
    station, years, _ = module.qualify(roster, frame)
    assert station.complete_published_daily_years.iloc[0] == 4
    assert bool(station.qualified_exploratory_20h_reference.iloc[0])
    assert not bool(station.strict_24h_reference_qualified.iloc[0])
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    station, years, _ = module.qualify(roster, frame)
    assert station.complete_published_daily_years.iloc[0] == 3
    assert not bool(station.qualified_exploratory_20h_reference.iloc[0])
    assert not bool(years.set_index('year').loc[2016, 'complete_published_daily'])

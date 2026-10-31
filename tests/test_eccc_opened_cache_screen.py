"""Old daily row counts are an upper bound, not proof of unique observations."""
import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location('eccc_prior',Path(__file__).resolve().parents[1]/'scripts/566_eccc_opened_cache_screen.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_one_incomplete_day_removes_possible_year_and_duplicate_day_is_error():
    dates=pd.date_range('2020-01-01','2020-12-31',freq='D')
    f=pd.DataFrame({'date':dates,'hourly_observations':24})
    assert m.screening(f)==[2020]
    f.loc[0,'hourly_observations']=23
    assert m.screening(f)==[]
    f=pd.concat([f,f.iloc[[0]]],ignore_index=True)
    with pytest.raises(ValueError,match='duplicated'):
        m.screening(f)

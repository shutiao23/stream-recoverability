"""Observed windows require consecutive finite days."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('window_reaudit',Path(__file__).resolve().parents[1]/'scripts/570_reaudit_observed_records.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_window_uses_consecutive_observed_values_and_handles_missing():
    x=np.r_[np.ones(30),np.nan,np.full(30,5.)]
    maximum,start=m.maximum_window(x)
    assert maximum==pytest.approx(5.) and start==31
    x[45]=np.nan
    maximum,start=m.maximum_window(x)
    assert maximum==pytest.approx(1.) and start==0
    assert m.maximum_window([1.,float('nan')],window=2)[1] is None

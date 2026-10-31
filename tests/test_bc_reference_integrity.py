"""Independent reference arithmetic detects impossible masks and observed maxima."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('bc_integrity',Path(__file__).resolve().parents[1]/'scripts/554_bc_reference_integrity.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_hidden_heat_is_excluded_from_observed_lower_bound():
    x=np.r_[np.ones(40),np.full(30,8.),np.ones(40)]
    truth,bound,n=m.compute(x,'40:30')
    assert truth==pytest.approx(8.)
    assert bound==pytest.approx(1.)
    assert n==30
    with pytest.raises(ValueError,match='Overlapping'):
        m.compute(x,'40:30;60:10')
    with pytest.raises(ValueError,match='outside'):
        m.compute(x,'100:11')
